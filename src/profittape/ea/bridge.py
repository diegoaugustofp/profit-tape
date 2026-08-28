"""
Ponte entre a captura (record) e o EA -- fila PROPRIA, independente do
EventBus do writer (2026-08-27, decisao de arquitetura: EA roda DENTRO
do processo do record, mesma conexao/mesma chave de ativacao -- licenca
Nelogica so' permite UMA, validado com o time comercial deles).

Por que fila SEPARADA, nao a mesma do writer: EventBus e' de UM
consumidor -- dois consumidores nela competiriam pelos mesmos eventos,
nao veriam cada um a copia inteira (ver EA_ARQUITETURA.md). Mesma
filosofia de "perda contabilizada > perda silenciosa" ja usada no
EventBus: se a fila do EA encher, descarta e conta, NUNCA bloqueia o
hot path da captura -- a captura e' sempre prioridade absoluta, o EA e'
secundario.

GARANTIA DE SEGURANCA (ja testada na fundacao, client.py::on_trade_extra):
qualquer excecao aqui e' contida -- nunca propaga de volta para o
callback da DLL. Reforcada aqui de novo, numa segunda camada: mesmo que
o hook em si nao falhe, um erro DENTRO do processamento do EA (thread
separada, consumidor) tambem nao pode derrubar nada alem de si mesmo.
"""

from __future__ import annotations

import queue
import threading

import structlog

from ..domain.events import Trade
from .service import EAService, _TradeBruto

log = structlog.get_logger(__name__)


class EABridge:
    """Uma instancia por simbolo (o mesmo simbolo do EAService). Trades de
    OUTROS simbolos (o record tipicamente assina varios) sao filtrados
    fora ja' em publicar(), antes mesmo de entrar na fila."""

    def __init__(self, ea_service: EAService, maxsize: int = 100_000) -> None:
        self.ea_service = ea_service
        self._simbolo = ea_service.config.symbol
        self._fila: queue.Queue[Trade] = queue.Queue(maxsize=maxsize)
        self._descartados = 0
        self._filtrados_outro_simbolo = 0
        self._parar_evento = threading.Event()
        self._thread: threading.Thread | None = None

    def publicar(self, trade: Trade) -> None:
        """
        Chamado do HOT PATH (callback da DLL, via ProfitClient.
        on_trade_extra) -- NUNCA pode bloquear nem levantar. Filtra por
        simbolo cedo (antes de enfileirar) e descarta com contagem se a
        fila estiver cheia, mesma filosofia do EventBus.
        """
        if trade.symbol != self._simbolo:
            self._filtrados_outro_simbolo += 1
            return
        try:
            self._fila.put_nowait(trade)
        except queue.Full:
            self._descartados += 1

    def iniciar(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="ea-bridge", daemon=True)
        self._thread.start()
        log.info("ea_bridge.iniciado", symbol=self._simbolo)

    def parar(self, timeout_s: float = 5.0) -> None:
        self._parar_evento.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout_s)
        # Encerramento do dia (zera posicao aberta, se houver) -- protegido:
        # um erro aqui nunca pode impedir o record de terminar o SEU proprio
        # encerramento (arquivos/footer/alerta), que e' sempre prioridade.
        try:
            self.ea_service.encerrar_dia()
        except Exception:
            log.exception("ea_bridge.erro_ao_encerrar_dia")
        log.info("ea_bridge.finalizado", descartados=self._descartados,
                 filtrados_outro_simbolo=self._filtrados_outro_simbolo,
                 **self.ea_service._hb())

    def _loop(self) -> None:
        while not self._parar_evento.is_set():
            try:
                trade = self._fila.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self.ea_service.processar_trade_bruto(_TradeBruto(
                    ts_ns=trade.ts_ns, price=trade.price,
                    quantidade=trade.quantidade, trade_type=trade.trade_type,
                    agente_comprador=trade.agente_comprador,
                    agente_vendedor=trade.agente_vendedor,
                ))
            except Exception:
                # Um trade com bug de processamento nao pode derrubar a
                # thread inteira -- perde SO' aquele trade para o EA
                # (nao para a captura, que nem passa por aqui), loga, segue.
                log.exception("ea_bridge.erro_processando_trade")
