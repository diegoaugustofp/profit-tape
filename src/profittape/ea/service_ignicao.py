"""
EA de IGNICAO na esteira multi-EA (fast-track, v3.68).

Mesma interface duck-typed do microprice (`config.symbol`,
`processar_trade_bruto`, `tick`, `encerrar_dia`, `_hb`). Ficha:
docs/eas/ignicao.md.

DECIDE NO TRADE, PELO RELOGIO DA BOLSA: o evento e' do tape (preco do
negocio contra o de 60 s antes), entao e' o `ts_ns` de cada negocio que
conta, nao o relogio de parede. A fila do bridge anda 2-5 s ATRAS do
mercado (22/09): a deteccao e' correta em relacao ao dado, mas a ordem
sai com esse atraso. Por isso o fill simulado nao usa o preco do negocio.

FILL SIMULADO (dry_run), TAKER no topo do livro AO VIVO no momento do
processamento: compra no ask, venda no bid. O log registra o
DESLIZAMENTO contra o preco de deteccao e o ATRASO (relogio de parede -
ts do negocio). E' a primeira medida, ainda no dry_run, do que pode
derrubar o resultado: o estudo aguenta ~55 pts por entrada. Sem livro
(record sem `--ea-livro-ao-vivo`) ou topo velho/cruzado, cai para o
preco do negocio, marcado `fill=tape` -- e ai' o deslizamento e' zero
POR CONSTRUCAO, nao medido.

EXECUCAO REAL (E4, demo): ordem a mercado pelo `ExecutorDeOrdens`; o
preco confirmado substitui o do topo.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from typing import Any

import structlog

from .config_ignicao import EAIgnicaoConfig
from .decisao import Acao, Decisao
from .execucao import executar
from .livro_ao_vivo import EstadoDoLivro
from .sinal_ignicao import DecisorIgnicao, Entrada, Saida

log = structlog.get_logger(__name__)
_NS = 1_000_000_000
TOPO_VELHO_NS = 2 * _NS


def _carimbo_codigo() -> str:
    try:
        from ..research.fase2 import _carimbo
        return _carimbo()
    except Exception:
        return "desconhecido"


class EAIgnicaoService:
    def __init__(self, config: EAIgnicaoConfig, executor: Any | None = None,
                 vagas: Any | None = None, nome: str | None = None,
                 livro: EstadoDoLivro | None = None,
                 relogio: Callable[[], int] = time.time_ns,
                 carimbo: str | None = None) -> None:
        if not config.dry_run and executor is None:
            raise SystemExit("dry_run=False exige um ExecutorDeOrdens construido")
        self.config = config
        self.executor = executor
        self.vagas = vagas
        self.nome = nome or config.nome or "ea_ignicao"
        self.livro = livro
        self._relogio = relogio
        self.decisor = DecisorIgnicao(config)
        self.trades = 0
        self.sem_vaga = 0
        self.fills: dict[str, int] = {"livro": 0, "tape": 0, "executor": 0}
        self.atraso_max_s = 0.0
        self._ultimo_tick_ns = 0
        self.operacoes: list[dict[str, Any]] = []
        self.carimbo = {"codigo": carimbo or _carimbo_codigo(),
                        "config_sha": config.sha256()}
        log.warning("ea.ign.iniciado", nome=self.nome, symbol=config.symbol,
                    dry_run=config.dry_run, sem_livro=(livro is None),
                    limiar_pts=config.limiar_pts, janela_s=config.janela_s,
                    alvo_pts=config.alvo_pts, stop_pts=config.stop_pts,
                    tempo_max_s=config.tempo_max_s, **self.carimbo)

    # ------------------------------------------------------------ bridge
    def processar_trade_bruto(self, t: Any) -> list[Decisao]:
        self.trades += 1
        for acao in self.decisor.novo_trade(int(t.ts_ns), float(t.price)):
            if isinstance(acao, Saida):
                self._sair(acao)
            else:
                self._entrar(acao)
        return []

    def tick(self) -> None:
        """Saida por TEMPO/fim do dia quando nao chega negocio (raro no WIN,
        mas o laco do bridge chama tick a cada 0,5 s sem fila). Relogio de
        parede x ts da bolsa: diferenca de segundos num timer de 60 min."""
        agora = self._relogio()
        if agora - self._ultimo_tick_ns < _NS:
            return
        self._ultimo_tick_ns = agora
        s = self.decisor.checar_saida(agora, None)
        if s is not None:
            self._sair(s)

    # ------------------------------------------------------------ fill
    def _topo(self, compra: bool) -> float | None:
        if self.livro is None:
            return None
        topo = self.livro.ler(self.config.symbol)
        if topo is None or topo.preco_bid is None or topo.preco_ask is None:
            return None
        if topo.preco_ask <= topo.preco_bid:                 # travado/cruzado
            return None
        if self._relogio() - topo.ts_recv_ns > TOPO_VELHO_NS:
            return None
        return float(topo.preco_ask if compra else topo.preco_bid)

    def _executar(self, acao: Acao, motivo: str, compra: bool,
                  preco_tape: float) -> tuple[float, str]:
        ref = self._topo(compra)
        r = executar(Decisao(acao, motivo, 0.0, "ignicao"), dry_run=self.config.dry_run,
                     executor=self.executor,
                     preco_referencia=ref if ref is not None else preco_tape)
        preco_exec = getattr(r, "preco_fill", None) if r is not None else None
        if preco_exec:
            origem, preco = "executor", float(preco_exec)
        elif ref is not None:
            origem, preco = "livro", ref
        else:
            origem, preco = "tape", preco_tape
        self.fills[origem] += 1
        return preco, origem

    # ------------------------------------------------------------ acoes
    def _entrar(self, e: Entrada) -> None:
        ign = e.ignicao
        if self.vagas is not None and not self.vagas.tentar_ocupar(
                self.config.symbol, self.nome, simulado=self.config.dry_run):
            self.sem_vaga += 1
            log.info("ea.ign.sem_vaga", nome=self.nome, ts_ns=ign.ts_ns)
            return
        compra = ign.direcao > 0
        atraso_s = (self._relogio() - ign.ts_ns) / _NS
        self.atraso_max_s = max(self.atraso_max_s, atraso_s)
        preco, origem = self._executar(Acao.COMPRAR if compra else Acao.VENDER,
                                       f"ignicao {ign.mov_pts:+.0f} pts", compra, ign.preco)
        self.decisor.abrir(ign, preco, ign.ts_ns)
        log.info("ea.ign.entrada", nome=self.nome, lado=ign.direcao, mov_pts=ign.mov_pts,
                 referencia=ign.referencia, preco_deteccao=ign.preco, fill=preco,
                 fill_origem=origem, desliz=(preco - ign.preco) * ign.direcao,
                 atraso_s=round(atraso_s, 3), ancora=ign.ancora,
                 alvo=ign.preco + ign.direcao * self.config.alvo_pts,
                 stop=ign.preco - ign.direcao * self.config.stop_pts, **self.carimbo)

    def _sair(self, s: Saida) -> None:
        p = self.decisor.posicao
        if p is None:
            return
        compra = p.lado < 0                        # zerar vendido = comprar
        preco, origem = self._executar(Acao.ZERAR, s.motivo, compra, s.preco_tape)
        campos = self.decisor.fechar(preco, s.ts_ns, s.motivo, s.preco_tape)
        campos["fill_origem"] = origem
        self.operacoes.append(campos)
        if self.vagas is not None:
            self.vagas.liberar(self.config.symbol, self.nome)
        log.info("ea.ign.saida", nome=self.nome, **campos,
                 pnl_dia=round(self.decisor.stats.pnl_liquido, 1), **self.carimbo)

    def encerrar_dia(self) -> None:
        p = self.decisor.posicao
        if p is not None:
            ultimo = self.decisor.detector._hist[-1] if self.decisor.detector._hist else None
            preco = ultimo[1] if ultimo else p.ignicao.preco
            self._sair(Saida("encerramento", preco, self._relogio()))
        elif self.vagas is not None:
            self.vagas.liberar(self.config.symbol, self.nome)
        log.warning("ea.ign.resumo", nome=self.nome, **self._hb(), **self.carimbo)

    def _hb(self) -> dict[str, Any]:
        return {"trades": self.trades, "sinais_sem_vaga": self.sem_vaga,
                "fills": dict(self.fills), "atraso_entrada_max_s": round(self.atraso_max_s, 3),
                **self.decisor.resumo()}


# ----------------------------------------------------------------------
# REPLAY sobre o tape gravado: mesmo nucleo, relogio = ts do negocio
# ----------------------------------------------------------------------
class _T:
    __slots__ = ("price", "ts_ns")

    def __init__(self, ts_ns: int, price: float) -> None:
        self.ts_ns, self.price = ts_ns, price


def replay_trades(cfg: EAIgnicaoConfig, trades: Iterable[tuple[int, float]],
                  carimbo: str = "replay") -> EAIgnicaoService:
    """`trades`: (ts_ns, preco) em ORDEM. Sempre dry_run, sem livro: o fill e'
    o preco do negocio (deslizamento zero POR CONSTRUCAO) -- o replay mede
    a REGRA, nao a execucao. Serve para conferir o EA contra o estudo."""
    relogio = [0]
    svc = EAIgnicaoService(cfg.model_copy(update={"dry_run": True}),
                           relogio=lambda: relogio[0], carimbo=carimbo)
    for ts, px in trades:
        relogio[0] = int(ts)
        svc.processar_trade_bruto(_T(int(ts), float(px)))
    svc.encerrar_dia()
    return svc
