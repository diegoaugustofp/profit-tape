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
import time
from datetime import UTC, datetime
from typing import Any

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
        # ATRASO (17/09): medido no ponto onde o trade SAI da fila -- vale para
        # os DOIS EAs. Foi atraso de processamento que fragmentou a barra do
        # EA de preco; no EA de FLUXO o efeito e' pior e nao foi medido: a
        # barra de VOLUME fecha por contagem de contratos, entao atraso/perda
        # muda ONDE a barra fecha, ou seja o proprio evento.
        self.atraso_alerta_s = 5.0
        self._ultimo_alerta_atraso = 0.0
        self._ultimo_periodico = time.time()
        self._atraso_max_s = 0.0
        self._atraso_soma = 0.0
        self._atraso_n = 0
        self._fila_pico = 0
        # DO DIA, nunca zerados: o resumo final so' via a ultima janela de
        # 5 min (mercado fechado -> atraso 0, medidos 0) -- mentia.
        self._atraso_max_dia_s = 0.0
        self._atraso_n_dia = 0
        # QUEM fez o maximo do dia (2026-09-22): em 22/09 o resumo trouxe
        # `atraso_max_dia_s=5575` com o WINFUT rodando a 2-5 s o dia inteiro,
        # e nao houve como investigar -- as duas hipoteses que levantei
        # (print de leilao; negocio de outro ticker) foram DERRUBADAS pelo
        # dado: nao ha' negocio antes das 09:02:41 e a fila ja' e' filtrada
        # por simbolo antes de enfileirar. Agora o maximo diz de QUE negocio
        # veio.
        self._atraso_max_dia_info: dict[str, Any] = {}
        self._edicoes_ignoradas = 0
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
        log.warning("ea_bridge.finalizado", descartados=self._descartados,
                    filtrados_outro_simbolo=self._filtrados_outro_simbolo,
                    atraso_max_dia_s=round(self._atraso_max_dia_s, 3),
                    atraso_max_dia_info=self._atraso_max_dia_info or None,
                    trades_medidos_dia=self._atraso_n_dia,
                    edicoes_ignoradas=self._edicoes_ignoradas,

                    **self.atraso(), **self.ea_service._hb())

    def _medir_atraso(self, trade: Trade) -> None:
        # EDICAO NAO ENTRA (2026-09-23): a B3 corrige negocios e a DLL entrega
        # a correcao com o TIMESTAMP ORIGINAL (`is_edit`). Uma correcao que
        # chega 8 min depois vira "atraso de 509 s" em UM negocio, enquanto os
        # 33 mil da mesma janela ficam em 2,3 s -- foi esse o padrao de 22 e
        # 23/09. Correcao nao atrasa sinal: o EA ja' processou o negocio
        # original. A metrica existe para explicar atraso de SINAL.
        if getattr(trade, "is_edit", False):
            self._edicoes_ignoradas += 1
            return
        ts = getattr(trade, "ts_ns", 0) or 0
        if not ts:
            return
        atraso = time.time() - ts / 1e9
        if atraso < 0:                      # relogio do feed a` frente: ignora
            return
        self._atraso_max_s = max(self._atraso_max_s, atraso)
        self._atraso_soma += atraso
        self._atraso_n += 1
        if atraso > self._atraso_max_dia_s:
            self._atraso_max_dia_s = atraso
            self._atraso_max_dia_info = {
                "symbol": getattr(trade, "symbol", None),
                "ts_evento": datetime.fromtimestamp(ts / 1e9, tz=UTC).isoformat(),
                "ts_medido": datetime.now(tz=UTC).isoformat(),
                "trade_id": getattr(trade, "trade_id", None),
                "trade_type": getattr(trade, "trade_type", None),
                "is_edit": getattr(trade, "is_edit", None),
            }
        self._atraso_n_dia += 1
        self._fila_pico = max(self._fila_pico, self._fila.qsize())

    def _alertar_atraso(self) -> None:
        """O atraso precisa aparecer DURANTE o pregao. No maximo uma linha a
        cada 60 s, so' quando passa do limite."""
        agora = time.time()
        # linha PERIODICA (5 min), sempre: sem o nivel normal medido, nao da'
        # para saber se 5 s e' pico ou rotina.
        if agora - self._ultimo_periodico > 300:
            self._ultimo_periodico = agora
            log.info("ea_bridge.atraso", symbol=self._simbolo, **self.atraso())
            self._atraso_max_s = 0.0          # maximo por JANELA, nao do dia
            self._atraso_soma = 0.0
            self._atraso_n = 0
        if self._atraso_max_s <= self.atraso_alerta_s:
            return
        if agora - self._ultimo_alerta_atraso < 60:
            return
        self._ultimo_alerta_atraso = agora
        log.warning("ea_bridge.atrasado", symbol=self._simbolo, **self.atraso(),
                    nota=("o EA processa a fila atras do mercado: em barra de TEMPO isso "
                          "atrasa o sinal; em barra de VOLUME muda ONDE a barra fecha"))

    def atraso(self) -> dict[str, Any]:
        """Atraso entre o trade ACONTECER e o EA processa-lo. `p50` nao, porque
        guardar a serie custaria memoria: media, MAXIMO e o pico da fila."""
        n = self._atraso_n
        return {"atraso_medio_s": (round(self._atraso_soma / n, 3) if n else None),
                "atraso_max_s": round(self._atraso_max_s, 3),
                "fila_agora": self._fila.qsize(), "fila_pico_ea": self._fila_pico,
                "trades_medidos": n}

    def _tick(self) -> None:
        """EA com `tick()` (o 123: barra pelo relogio, callbacks de ordem,
        reconexao). Chamado a cada volta do laco; o servico decide a
        cadencia. Protegido: um erro no tick nao derruba a thread."""
        tick = getattr(self.ea_service, "tick", None)
        if tick is None:
            return
        try:
            tick()
        except Exception:
            log.exception("ea_bridge.erro_no_tick")

    def _loop(self) -> None:
        while not self._parar_evento.is_set():
            try:
                trade = self._fila.get(timeout=0.5)
            except queue.Empty:
                self._tick()
                continue
            self._medir_atraso(trade)
            self._alertar_atraso()
            self._tick()
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
