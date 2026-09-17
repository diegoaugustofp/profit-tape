"""
EA do 123 (passo 7 do F5, EAS_DE_PRECO.md 5.4): o servico que a esteira
multi-EA (E5) liga por YAML, com a MESMA interface duck-typed que o
`EABridge` e o `RegistroDeEAs` esperam do `EAService`:
`config.symbol`, `processar_trade_bruto`, `encerrar_dia`, `_hb`, e --
novidade -- `tick()` (chamado pelo bridge a cada ~0,5 s), porque o 123
tem duas coisas que o EA de fluxo nao tem: barra que fecha pelo
relogio e ordens vivas na corretora cujos callbacks chegam fora do
fluxo de trades.

ARRANQUE
--------
1. Semente da MME80 (`semente.construir_semente`) para o dia de HOJE
   com o parquet + ponte pelo tape. Invalida -> o EA sobe SEM armar
   (`ea.123.sem_semente`) e so' atualiza a MME. E' regra da ficha.
2. `SinalPreco123` com a MME semeada; `CicloDeOrdens123` com o executor
   (None em dry_run), o gate (`filtro_fluxo`), as vagas do modo
   exclusivo e o registro JSONL (passo 6).
3. Carimbo: tag do codigo + sha256 do YAML, em cada linha do registro.

RECONEXAO (4b)
--------------
`tick()` observa `client.corretora_pronta`; na transicao False -> True
(a corretora voltou) chama `ciclo.reconciliar_apos_reconexao()`. Em
dry_run o client pode nao existir (replay) -- nada a reconciliar.
"""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from ..research.fase2 import _carimbo
from .barra_tempo import ConstrutorDeBarraDeTempo
from .ciclo_123 import CicloDeOrdens123
from .config_123 import EA123Config
from .diario import DiarioDeSinais
from .gate_fluxo import construir_gate
from .perfil_volume import construir_perfil
from .registro_123 import RegistroDeSinais123
from .semente import IndicadorMME, Semente, construir_semente
from .sinal_123 import SinalPreco123

log = structlog.get_logger(__name__)
_TZ = ZoneInfo("America/Sao_Paulo")
_NS = 1_000_000_000


@dataclass
class _TradeBruto:
    ts_ns: int
    price: float
    quantidade: int
    trade_type: int
    agente_comprador: int = 0
    agente_vendedor: int = 0


class EA123Service:
    def __init__(self, config: EA123Config, executor: Any | None = None,
                 vagas: Any | None = None, nome: str | None = None,
                 client: Any | None = None, dia: dt.date | None = None,
                 curated: Path | None = None) -> None:
        if not config.dry_run and executor is None:
            raise SystemExit("dry_run=False exige um ExecutorDeOrdens construido")
        self.config = config
        self.nome = nome or config.nome or "ea_123"
        self.client = client
        self.dia = dia or dt.datetime.now(_TZ).date()
        # inicio_ns: o que decide se a primeira barra e' parcial (16/09). So'
        # vale quando o dia operado e' HOJE -- reproduzir um dia passado pelo
        # servico e' replay, e ai' o relogio de parede nao diz nada (cai no
        # criterio do primeiro trade).
        hoje = dt.datetime.now(_TZ).date()
        self.ao_vivo = self.dia == hoje
        inicio_ns = int(time.time() * _NS) if self.ao_vivo else None
        self.construtor = ConstrutorDeBarraDeTempo(config.periodo_barra_s,
                                                    fim_sessao_hhmm=config.fim_sessao_hhmm,
                                                    inicio_ns=inicio_ns)
        self.carimbo = {"codigo": _carimbo(), "yaml_sha256": config.sha256(),
                        "nome": self.nome, "dry_run": config.dry_run}
        self.semente: Semente = construir_semente(
            Path(config.semente_parquet), self.dia,
            curated if curated is not None else Path(config.curated),
            symbol=config.symbol, periodo_s=config.periodo_barra_s,
            feriados=tuple(dt.date.fromisoformat(f) for f in config.feriados))
        valor = self.semente.valor if self.semente.valida and self.semente.valor else 0.0
        self.sinal = SinalPreco123(IndicadorMME(80, valor), config.periodo_barra_s)
        if not self.semente.valida:
            log.error("ea.123.sem_semente", motivo=self.semente.motivo, **self.carimbo,
                      nota="EA sobe SEM armar sinal; a MME so' e' atualizada")
            self.sinal.dia_completo = False
        registro = None
        self.diario: DiarioDeSinais | None = None
        if config.registro_dir:
            registro = RegistroDeSinais123(Path(config.registro_dir), self.carimbo)
            self.diario = DiarioDeSinais(Path(config.registro_dir), self.nome, self.carimbo)
        perfil = None
        if config.filtro_fluxo and config.filtro_fluxo.get("tipo") == "volume_baixo":
            perfil = construir_perfil(
                Path(config.semente_parquet), self.dia,
                curated if curated is not None else Path(config.curated),
                symbol=config.symbol, periodo_s=config.periodo_barra_s,
                janela_pregoes=int(config.filtro_fluxo.get("janela_pregoes", 20)))
        if not self.semente.valida and config.filtro_fluxo is not None:
            raise SystemExit(
                f"{self.nome}: semente da MME80 INVALIDA ({self.semente.motivo}) e o yaml pede "
                "`filtro_fluxo`. Sem semente o EA sobe inerte (nao arma nenhum sinal) e o dia "
                "se perde -- melhor nao subir. Corrija a semente (backfill + cura do dia que "
                "falta, ou dump novo do grafico) e suba de novo.")
        if perfil is not None and perfil.resumo()["horarios_com_perfil"] == 0:
            raise SystemExit(
                f"{self.nome}: `filtro_fluxo` pede o gate de volume, mas o perfil esta' VAZIO "
                f"(parquet={config.semente_parquet}, curated={config.curated}). Sem perfil o "
                "gate reprova TUDO e o EA sobe inerte -- confira os caminhos do yaml (relativos "
                "sao resolvidos pela pasta do proprio yaml).")
        self.perfil = perfil
        self.ciclo = CicloDeOrdens123(
            self.sinal, executor=None if config.dry_run else executor,
            quantidade=config.tamanho_posicao, zeragem_hhmm=config.zeragem_hhmm,
            slack_limite_pts=config.slack_limite_pts,
            gate=construir_gate(config.filtro_fluxo, perfil, lambda: self.dia),
            vagas=vagas, symbol=config.symbol, nome=self.nome, registro=registro,
            infra_extra=self._infra, diario=self.diario)
        self._corretora_pronta_antes: bool | None = None
        self._ultimo_tick = 0.0
        self.trades = 0
        self.barras = 0
        self._ultimo_ts_ns = 0
        log.warning("ea.123.iniciado", **self.carimbo, semente=self.semente.resumo(),
                    filtro_fluxo=config.filtro_fluxo,
                    perfil_volume=(perfil.resumo() if perfil is not None else None),
                    symbol=config.symbol, periodo_s=config.periodo_barra_s,
                    capital_recomendado_informativo=config.capital_recomendado_informativo())

    # ------------------------------------------------------------------
    def processar_trade_bruto(self, t: _TradeBruto) -> None:
        self.trades += 1
        self._ultimo_ts_ns = t.ts_ns
        b = self.construtor.processar_trade(t.ts_ns, t.price, t.quantidade, t.trade_type)
        if b is not None:
            self._barra(b)
        self.ciclo.on_trade(t.ts_ns, t.price)

    def _barra(self, b: Any) -> None:
        self.barras += 1
        if not self.semente.valida:
            self.sinal.mme.atualizar(b.close)          # so' converge; nao arma
            return
        self.ciclo.on_barra(b)

    def tick(self) -> None:
        """A cada ~0,5 s (bridge): fecha barra pelo relogio, le callbacks das
        ordens, detecta reconexao."""
        agora = time.time()
        if agora - self._ultimo_tick < 0.4:
            return
        self._ultimo_tick = agora
        # BUG REAL (17/09), duas tentativas erradas antes desta: em REPLAY
        # o `avancar_relogio` NAO deve ser chamado. Quem fecha barra ali e'
        # o fluxo de TRADES (medido no dado real de 16/09: 37 barras, o
        # numero certo); `avancar_relogio` existe para o AO VIVO, onde o
        # tempo passa sem negocio. Chamando nos dois, o replay picava o dia
        # em 3.022 fragmentos, marcava a 1a barra parcial e o dia inteiro
        # ficava sem sinal. A ultima barra do replay fica em formacao, como
        # deve ser -- `encerrar_dia` cuida da posicao.
        if self.ao_vivo:
            b = self.construtor.avancar_relogio(int(agora * _NS))
            if b is not None:
                self._barra(b)
        if self.client is not None and not self.config.dry_run:
            pronta = bool(getattr(self.client, "corretora_pronta", True))
            if self._corretora_pronta_antes is False and pronta:
                log.warning("ea.123.reconectado", nota="reconciliando ordens e posicao")
                self.ciclo.reconciliar_apos_reconexao()
            self._corretora_pronta_antes = pronta
        self.ciclo.tick()

    def _infra(self) -> dict[str, Any]:
        """Estado da infra no momento de armar (vai para o JSONL): separa
        "execucao" de "minha rede caiu" quando o slippage sair."""
        pronta = (bool(getattr(self.client, "corretora_pronta", True))
                  if self.client is not None else None)
        return {"corretora_pronta": pronta, "dia_completo": self.sinal.dia_completo,
                "semente_valida": self.semente.valida, "barras_no_dia": self.barras,
                "perfil_volume": (self.perfil.resumo() if self.perfil is not None else None)}

    def encerrar_dia(self) -> None:
        self.ciclo.encerrar_dia()
        log.info("ea.123.encerramento_dia", **self._hb())

    def _hb(self) -> dict[str, Any]:
        return {"trades": self.trades, "barras": self.barras, "semente_valida": self.semente.valida,
                "mme80": round(self.sinal.mme.valor, 1), "dia_completo": self.sinal.dia_completo,
                **self.ciclo.hb()}


def replay_do_dia(config: EA123Config, dia: dt.date, curated: Path | None = None,
                  tick_a_cada: int = 2000) -> EA123Service:
    """
    REPLAY do EA de preco sobre um dia ja' CURADO (2026-09-17).

    Exercita o caminho inteiro -- semente, perfil de volume, gate, sinal,
    ciclo em dry_run, diario -- com barras REAIS, sem esperar pregao. E' o
    que transforma "torcer para funcionar amanha" em verificacao hoje.

    Duas coisas de proposito:
      - `dry_run` e' FORCADO: replay nunca manda ordem, mesmo se o yaml
        disser o contrario.
      - o construtor cai no criterio ANTIGO de barra parcial (o servico
        so' usa o relogio quando o dia operado e' hoje), que e' o que
        conferiu 69/69 contra o grafico.

    `tick_a_cada`: o `tick()` fecha barra pelo relogio e le callbacks; no
    replay nao ha' callback, mas chamar de vez em quando exercita o mesmo
    caminho do ao vivo.
    """
    from ..features.pipeline import _carregar_dia

    cfg = config.model_copy(update={"dry_run": True})
    raiz = curated if curated is not None else Path(cfg.curated)
    pasta = raiz / "trade" / f"dt={dia.isoformat()}"
    if not (pasta / f"sym={cfg.symbol}").exists():
        raise SystemExit(f"sem tape curado para {cfg.symbol} em {dia}: {pasta}")
    t = _carregar_dia(pasta, cfg.symbol)
    if t.empty:
        raise SystemExit(f"tape vazio em {pasta}")
    s = EA123Service(cfg, dia=dia, curated=raiz)
    cols = ["ts_ns", "price", "quantidade", "trade_type", "agente_comprador", "agente_vendedor"]
    faltando = [c for c in cols if c not in t.columns]
    if faltando:
        cols = [c for c in cols if c not in faltando]
    dados = t[cols].to_dict("records")
    for i, linha in enumerate(dados, start=1):
        s.processar_trade_bruto(_TradeBruto(
            ts_ns=int(linha["ts_ns"]), price=float(linha["price"]),
            quantidade=int(linha["quantidade"]), trade_type=int(linha["trade_type"]),
            agente_comprador=int(linha.get("agente_comprador") or 0),
            agente_vendedor=int(linha.get("agente_vendedor") or 0)))
        if i % tick_a_cada == 0:
            s._ultimo_tick = 0.0      # o tick tem cadencia de 0,4 s no ao vivo
            s.tick()
    s.encerrar_dia()
    log.warning("ea.123.replay_concluido", dia=dia.isoformat(), **s._hb())
    return s
