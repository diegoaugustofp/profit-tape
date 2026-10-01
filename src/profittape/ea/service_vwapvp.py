"""
EA VWAP + VP (continuacao a tarde) na esteira multi-EA (E5), fast-track.

Mesma interface duck-typed que o `EABridge` e o `RegistroDeEAs` esperam
(`config.symbol`, `processar_trade_bruto`, `tick`, `encerrar_dia`, `_hb`).

FLUXO
  trade -> VWAPSessao.registrar (O(1))           -> VWAP e SD por negocio
        -> ConstrutorDeBarraDeTempo.processar     -> barra M5 fechada?
           -> decisor.avaliar_barra(b, vwap, sd)  -> COMPRAR/VENDER (pendente)
        -> com pendente: o PROXIMO negocio e' o fill em dry_run (preco do
           negocio); com executor (E4 demo), ordem a mercado e o preco do
           fill substitui.
        -> com posicao: decisor.avaliar_preco(price) -> ZERAR por alvo /
           stop / tempo / zeragem; saida a mercado.

QUEM FECHA BARRA E' O TRADE (licao do 123, 17/09): nao se chama
`avancar_relogio` nem ao vivo nem em replay. A ultima barra do dia fica
em formacao; `encerrar_dia` zera a posicao se houver.

ORDEM DO FLUXO (cuidado): o negocio que abre a barra seguinte fecha a
anterior; a decisao e' tomada ANTES de registrar esse negocio na VWAP,
para que o z do fechamento use a VWAP ate' o ultimo negocio da barra
fechada -- identico ao replay (`_construir_barras`), cujos z foram
batidos no grafico. O mesmo negocio e' o fill em dry_run.
"""

from __future__ import annotations

import datetime as dt
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from .barra_tempo import ConstrutorDeBarraDeTempo
from .config_vwapvp import EAVwapVpConfig
from .decisao import Acao, Decisao
from .execucao import executar
from .sinal import BarraFechada
from .sinal_vwapvp import DecisorVwapVp, hhmm_de
from .vwap_sessao import VWAPSessao

log = structlog.get_logger(__name__)
_TZ = ZoneInfo("America/Sao_Paulo")
_NS = 1_000_000_000


def _carimbo_codigo() -> str:
    try:
        from ..research.fase2 import _carimbo
        return _carimbo()
    except Exception:
        return "desconhecido"


class EAVwapVpService:
    def __init__(self, config: EAVwapVpConfig, executor: Any | None = None,
                 vagas: Any | None = None, nome: str | None = None,
                 relogio: Callable[[], int] = time.time_ns,
                 carimbo: str | None = None) -> None:
        if not config.dry_run and executor is None:
            raise SystemExit("dry_run=False exige um ExecutorDeOrdens construido")
        self.config = config
        self.executor = executor
        self.vagas = vagas
        self.nome = nome or config.nome or "ea_vwapvp"
        self._relogio = relogio
        self.decisor = DecisorVwapVp(config)
        self.vwap = VWAPSessao()
        self.construtor = ConstrutorDeBarraDeTempo(config.periodo_barra_s,
                                                    fim_sessao_hhmm=config.fim_sessao_hhmm)
        self.trades = 0
        self.barras = 0
        self.sem_vaga = 0
        self._ultimo_ts_ns = 0
        self._ultimo_preco: float | None = None
        self.operacoes: list[dict[str, Any]] = []     # fechamentos do dia (replay/teste)
        self.carimbo = {"codigo": carimbo or _carimbo_codigo(), "config_sha": config.sha256()}
        log.warning("ea.vwapvp.iniciado", nome=self.nome, symbol=config.symbol,
                    dry_run=config.dry_run, z_banda=config.z_banda,
                    janela=(config.janela_inicio_hhmm, config.janela_fim_hhmm),
                    alvo_sd=config.alvo_sd, stop_frac_dist=config.stop_frac_dist,
                    tempo_max_s=config.tempo_max_s, **self.carimbo)

    # ------------------------------------------------------------ bridge
    def processar_trade_bruto(self, t: Any) -> None:
        self.trades += 1
        ts, price = int(t.ts_ns), float(t.price)
        self._ultimo_ts_ns = ts
        self._ultimo_preco = price
        # 1. barra: o negocio que abre a barra seguinte FECHA a anterior. A
        #    decisao ve a VWAP ate' o ultimo negocio da barra fechada (este
        #    negocio ainda nao entrou) -- identico ao replay.
        b = self.construtor.processar_trade(ts, price, int(t.quantidade), int(t.trade_type))
        if b is not None:
            self._barra(b)
        # 2. pendente de fill: este negocio e' o primeiro apos o fechamento
        if self.decisor._pendente is not None and self.decisor.posicao is None:
            self._entrar(price, ts)
        # 3. VWAP por negocio
        self.vwap.registrar(price, int(t.quantidade))
        # 4. posicao aberta: alvo / stop / tempo / zeragem
        if self.decisor.posicao is not None:
            av = self.decisor.avaliar_preco(price, ts)
            if av.acao == Acao.ZERAR:
                self._sair(price, ts, av.motivo)

    def _barra(self, b: BarraFechada) -> None:
        self.barras += 1
        av = self.decisor.avaliar_barra(b, self.vwap.vwap, self.vwap.desvio)
        if av.acao in (Acao.COMPRAR, Acao.VENDER):
            log.info("ea.vwapvp.sinal", nome=self.nome, lado=av.lado, close=b.close,
                     vwap=round(self.vwap.vwap or 0.0, 1), sd=round(av.sd or 0.0, 1),
                     z=round(av.z or 0.0, 3), dist=round(av.dist or 0.0, 1),
                     alvo_px=av.alvo_px, stop_px=av.stop_px,
                     hhmm=hhmm_de(b.ts_open_ns), **self.carimbo)
        elif av.motivo not in ("fora_da_banda",):
            log.debug("ea.vwapvp.sinal_filtrado", nome=self.nome, motivo=av.motivo,
                      hhmm=hhmm_de(b.ts_open_ns))

    def tick(self) -> None:
        """Saida por tempo/zeragem mesmo sem negocio novo (raro no WIN)."""
        if self.decisor.posicao is None or self._ultimo_preco is None:
            return
        agora = self._relogio()
        if agora - self._ultimo_ts_ns < 2 * _NS:
            return
        av = self.decisor.avaliar_preco(self._ultimo_preco, agora)
        if av.acao == Acao.ZERAR and av.motivo in ("tempo", "zeragem"):
            self._sair(self._ultimo_preco, agora, av.motivo + " (tick)")

    # ------------------------------------------------------------ execucao
    def _executar(self, acao: Acao, motivo: str, valor: float,
                  preco_ref: float | None) -> float | None:
        r = executar(Decisao(acao, motivo, valor, "vwap_vp"),
                     dry_run=self.config.dry_run, executor=self.executor,
                     preco_referencia=preco_ref)
        preco = getattr(r, "preco_fill", None) if r is not None else None
        return float(preco) if preco else None

    def _entrar(self, preco_negocio: float, ts_ns: int) -> None:
        av = self.decisor._pendente
        assert av is not None
        if self.vagas is not None and not self.vagas.tentar_ocupar(
                self.config.symbol, self.nome, simulado=self.config.dry_run):
            self.sem_vaga += 1
            self.decisor.cancelar_pendente()
            return
        fill = self._executar(av.acao, av.motivo, av.z or 0.0, preco_negocio)
        preco = fill if fill is not None else preco_negocio
        p = self.decisor.abrir(preco, ts_ns)
        log.info("ea.vwapvp.entrada", nome=self.nome, lado=p.lado, preco=preco,
                 preco_negocio=preco_negocio, alvo_px=p.alvo_px, stop_px=p.stop_px,
                 z=round(p.z_sinal, 3), sd=round(p.sd_sinal, 1), dist=round(p.dist_sinal, 1),
                 **self.carimbo)

    def _sair(self, preco_negocio: float, ts_ns: int, motivo: str) -> None:
        if self.decisor.posicao is None:
            return
        fill = self._executar(Acao.ZERAR, motivo, 0.0, preco_negocio)
        preco = fill if fill is not None else preco_negocio
        campos = self.decisor.fechar(preco, ts_ns, motivo)
        if self.vagas is not None:
            self.vagas.liberar(self.config.symbol, self.nome)
        campos["dia"] = dt.datetime.fromtimestamp(ts_ns / 1e9, tz=_TZ).date().isoformat()
        self.operacoes.append(campos)
        log.info("ea.vwapvp.saida", nome=self.nome, **campos,
                 pnl_dia=round(self.decisor.stats.pnl_liquido, 1),
                 bloqueado=self.decisor.stats.bloqueado, **self.carimbo)

    def encerrar_dia(self) -> None:
        if self.decisor._pendente is not None:
            self.decisor.cancelar_pendente()
        if self.decisor.posicao is not None and self._ultimo_preco is not None:
            self._sair(self._ultimo_preco, max(self._ultimo_ts_ns, self._relogio()),
                       "encerramento do dia")
        elif self.vagas is not None:
            self.vagas.liberar(self.config.symbol, self.nome)
        log.warning("ea.vwapvp.resumo", nome=self.nome, **self._hb(), **self.carimbo)

    def _hb(self) -> dict[str, Any]:
        return {"trades": self.trades, "barras": self.barras, "sinais_sem_vaga": self.sem_vaga,
                "vwap": round(self.vwap.vwap or 0.0, 1), "sd": round(self.vwap.desvio or 0.0, 1),
                **self.decisor.resumo()}


# ----------------------------------------------------------------------
# REPLAY do SERVICO num dia do curated: o mesmo codigo do vivo, dry_run,
# relogio = ts do dado. Serve para bater com `ea-vwapvp-regra` no mesmo dia
# (a diferenca esperada: entrada no 1o negocio apos a barra, e saidas por
# negocio em vez de high/low de barra).
# ----------------------------------------------------------------------
def replay_servico_do_dia(config: EAVwapVpConfig, dia: dt.date, curated: Path,
                          carimbo: str = "replay") -> EAVwapVpService:
    from ..features.pipeline import _carregar_dia

    cfg = config.model_copy(update={"dry_run": True})
    relogio = [0]
    svc = EAVwapVpService(cfg, relogio=lambda: relogio[0], carimbo=carimbo)
    pasta = curated / "trade" / f"dt={dia.isoformat()}"
    t = _carregar_dia(pasta, config.symbol)
    if t.empty:
        raise SystemExit(f"{dia}: sem tape no curated")

    from .service import _TradeBruto

    for ts_ns, price, qtd, tipo in t[["ts_ns", "price", "quantidade",
                                      "trade_type"]].itertuples(index=False):
        relogio[0] = int(ts_ns)
        svc.processar_trade_bruto(_TradeBruto(int(ts_ns), float(price), int(qtd), int(tipo),
                                              0, 0))
    svc.encerrar_dia()
    return svc
