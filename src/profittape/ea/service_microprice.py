"""
EA de MICROPRICE / QUEUE IMBALANCE na esteira multi-EA (E5), fast-track.

Mesma interface duck-typed que o `EABridge` e o `RegistroDeEAs` esperam
(`config.symbol`, `processar_trade_bruto`, `tick`, `encerrar_dia`, `_hb`).

POR QUE DECIDE NO `tick()`, NAO NO TRADE
-----------------------------------------
O sinal e' o LIVRO, e o `EstadoDoLivro` e' atualizado no hot path (fresco
por construcao). A fila de trades do bridge pode andar ATRAS do mercado
(2-5 s medidos no WINFUT em 22/09). Decidir "no trade" amarraria um sinal
de sub-segundo a essa fila; aqui o trade so' marca o relogio, e cada
`tick` le o topo de AGORA, limitado a uma avaliacao por `avaliacao_ms`.

PRE-REQUISITO: record com `--ea-livro-ao-vivo`. Sem ele o `EstadoDoLivro`
existe mas nunca e' alimentado, e o EA passa o dia em `sem_livro`
(avisado no log uma vez por minuto, nunca opera).

EXECUCAO: dry_run simula fill TAKER no topo (compra no ask, venda no
bid). Com executor (E4, demo), ordens a mercado pelo `ExecutorDeOrdens`,
que bloqueia esta thread ate' o fill -- aceitavel: e' a thread do bridge,
nao o callback da DLL -- e o preco do fill substitui o do topo.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from typing import Any

import structlog

from ..domain.events import TinyBook
from .config_microprice import EAMicropriceConfig
from .decisao import Acao, Decisao
from .execucao import executar
from .livro_ao_vivo import EstadoDoLivro
from .sinal_microprice import Avaliacao, DecisorMicroprice

log = structlog.get_logger(__name__)


def _carimbo_codigo() -> str:
    try:
        from ..research.fase2 import _carimbo
        return _carimbo()
    except Exception:
        return "desconhecido"


class EAMicropriceService:
    def __init__(self, config: EAMicropriceConfig, executor: Any | None = None,
                 vagas: Any | None = None, nome: str | None = None,
                 livro: EstadoDoLivro | None = None,
                 relogio: Callable[[], int] = time.time_ns,
                 carimbo: str | None = None) -> None:
        if not config.dry_run and executor is None:
            raise SystemExit("dry_run=False exige um ExecutorDeOrdens construido")
        self.config = config
        self.executor = executor
        self.vagas = vagas
        self.nome = nome or config.nome or "ea_microprice"
        self.livro = livro
        self._relogio = relogio
        self.decisor = DecisorMicroprice(config)
        self.trades = 0
        self.sem_vaga = 0
        self._ultima_aval_ns = 0
        self._ultimo_aviso_sem_livro_ns = 0
        self.carimbo = {"codigo": carimbo or _carimbo_codigo(),
                        "config_sha": config.sha256()}
        log.warning("ea.micro.iniciado", nome=self.nome, symbol=config.symbol,
                    dry_run=config.dry_run, sem_livro=(livro is None),
                    limiar=config.limiar_entrada, persistencia_ms=config.persistencia_ms,
                    alvo_ticks=config.alvo_ticks, stop_ticks=config.stop_ticks,
                    **self.carimbo)

    # ------------------------------------------------------------ bridge
    def processar_trade_bruto(self, t: Any) -> list[Decisao]:
        # O trade nao decide nada aqui (ver docstring); o bridge chama
        # `tick()` logo em seguida.
        self.trades += 1
        return []

    def tick(self) -> Avaliacao | None:
        agora = self._relogio()
        if agora - self._ultima_aval_ns < self.config.avaliacao_ms * 1_000_000:
            return None
        self._ultima_aval_ns = agora
        topo = self.livro.ler(self.config.symbol) if self.livro is not None else None
        if topo is None and agora - self._ultimo_aviso_sem_livro_ns > 60 * 1_000_000_000:
            self._ultimo_aviso_sem_livro_ns = agora
            log.warning("ea.micro.sem_livro", nome=self.nome, symbol=self.config.symbol,
                        nota="topo do livro vazio -- o record subiu com "
                             "--ea-livro-ao-vivo? Sem ele este EA nunca opera.")
        return self.avaliar_e_agir(topo, agora)

    # ------------------------------------------------------------ nucleo
    def avaliar_e_agir(self, topo: Any, agora_ns: int) -> Avaliacao:
        av = self.decisor.avaliar(topo, agora_ns)
        if av.acao in (Acao.COMPRAR, Acao.VENDER):
            self._entrar(av, agora_ns)
        elif av.acao == Acao.ZERAR:
            self._sair(av.preco, agora_ns, av.motivo, av)
        return av

    def _executar(self, acao: Acao, motivo: str, valor: float,
                  preco_ref: float | None) -> float | None:
        """Devolve o preco de fill confirmado (so' com executor), senao None."""
        r = executar(Decisao(acao, motivo, valor, "microprice"),
                     dry_run=self.config.dry_run, executor=self.executor,
                     preco_referencia=preco_ref)
        preco = getattr(r, "preco_fill", None) if r is not None else None
        return float(preco) if preco else None

    def _entrar(self, av: Avaliacao, agora_ns: int) -> None:
        if self.vagas is not None and not self.vagas.tentar_ocupar(
                self.config.symbol, self.nome, simulado=self.config.dry_run):
            self.sem_vaga += 1
            return
        assert av.preco is not None and av.imbalance is not None
        fill = self._executar(av.acao, av.motivo, av.imbalance, av.preco)
        preco = fill if fill is not None else av.preco
        self.decisor.abrir(av.lado, preco, agora_ns, av.imbalance)
        log.info("ea.micro.entrada", nome=self.nome, lado=av.lado, preco=preco,
                 preco_topo=av.preco, imbalance=round(av.imbalance, 3),
                 micro=round(av.micro or 0.0, 2), spread=av.spread, **self.carimbo)

    def _sair(self, preco_topo: float | None, agora_ns: int, motivo: str,
              av: Avaliacao | None = None) -> None:
        if self.decisor.posicao is None:
            return
        fill = self._executar(Acao.ZERAR, motivo, 0.0, preco_topo)
        preco = fill if fill is not None else preco_topo
        if preco is None:           # encerramento sem livro nenhum no dia
            preco = self.decisor.posicao.preco_entrada
            motivo = f"{motivo} (sem marcacao: P&L zero ASSUMIDO)"
        campos = self.decisor.fechar(preco, agora_ns, motivo)
        if self.vagas is not None:
            self.vagas.liberar(self.config.symbol, self.nome)
        log.info("ea.micro.saida", nome=self.nome, **campos,
                 imbalance_saida=(round(av.imbalance, 3) if av and av.imbalance is not None
                                  else None),
                 pnl_dia=round(self.decisor.stats.pnl_liquido, 1),
                 bloqueado=self.decisor.stats.bloqueado, **self.carimbo)

    def encerrar_dia(self) -> None:
        if self.decisor.posicao is not None:
            agora = self._relogio()
            topo = self.livro.ler(self.config.symbol) if self.livro is not None else None
            p = self.decisor.posicao
            marca = None
            if topo is not None and topo.preco_bid is not None and topo.preco_ask is not None:
                marca = topo.preco_bid if p.lado > 0 else topo.preco_ask
            self._sair(marca, agora, "encerramento do dia")
        elif self.vagas is not None:
            self.vagas.liberar(self.config.symbol, self.nome)
        log.warning("ea.micro.resumo", nome=self.nome, **self._hb(), **self.carimbo)

    def _hb(self) -> dict[str, Any]:
        return {"trades": self.trades, "sinais_sem_vaga": self.sem_vaga,
                **self.decisor.resumo()}


# ----------------------------------------------------------------------
# REPLAY sobre o tiny_book gravado (raw): mesmo nucleo, relogio = ts_recv_ns
# ----------------------------------------------------------------------
def replay_tiny_book(cfg: EAMicropriceConfig,
                     eventos: Iterable[tuple[int, int, float, int]],
                     carimbo: str = "replay") -> EAMicropriceService:
    """
    `eventos`: (ts_recv_ns, side, price, quantidade) EM ORDEM de tempo.
    Cada evento atualiza o livro; avalia no maximo a cada `avaliacao_ms`
    do relogio do proprio dado (o `tick` ao vivo faz o mesmo com o relogio
    de parede). Sempre dry_run: replay nunca envia ordem.

    Diferenca conhecida em relacao ao vivo: aqui a avaliacao acontece a
    cada mudanca do topo; ao vivo, a cada trade/0,5 s. E o fill simulado
    e' o topo no instante da decisao -- sem latencia de roteamento, que
    so' o E4 em demo mede. O replay e' portanto o TETO do que o vivo faz.
    """
    cfg_replay = cfg.model_copy(update={"dry_run": True})
    livro = EstadoDoLivro()
    relogio_atual = [0]
    svc = EAMicropriceService(cfg_replay, livro=livro,
                              relogio=lambda: relogio_atual[0], carimbo=carimbo)
    sym = cfg.symbol
    for ts, side, price, qtd in eventos:
        livro.atualizar(TinyBook(ts, sym, "F", int(side), float(price), int(qtd)))
        relogio_atual[0] = int(ts)
        svc.tick()
    svc.encerrar_dia()
    return svc
