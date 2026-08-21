"""
Fila entre o callback da DLL e o writer.

O PROBLEMA QUE ISSO RESOLVE
---------------------------
Os callbacks do ProfitDLL sao chamados de uma thread interna da DLL. Enquanto
o seu codigo Python roda dentro do callback, o feed FICA PARADO. Escrever em
disco ali dentro — ou qualquer coisa que bloqueie por milissegundos — enfileira
eventos no lado da DLL, e quando o buffer dela estoura o dado se perde antes
de chegar ate voce. Nao ha aviso.

A regra e' absoluta: o callback constroi a tupla, empurra na fila e devolve o
controle. Nada mais.

PERDA CONHECIDA E' MELHOR QUE PERDA SILENCIOSA
-----------------------------------------------
Se a fila encher, alguem tem que perder. A escolha aqui e' descartar o evento
NOVO e contabilizar. Alternativa seria bloquear o callback, o que trava o feed
inteiro — troca ruim. O que nao se admite e' perder sem registrar: um buraco
nao contabilizado no dado invalida qualquer analise feita depois sobre ele,
e voce descobre meses adiante.
"""

from __future__ import annotations

import contextlib
import queue
import threading
from typing import Any, NamedTuple

from ..domain.enums import Stream


class Envelope(NamedTuple):
    """Evento etiquetado com o fluxo a que pertence."""

    stream: Stream
    event: Any


class DropStats(NamedTuple):
    total_recebido: int
    total_descartado: int
    profundidade_atual: int
    profundidade_maxima: int

    @property
    def taxa_descarte(self) -> float:
        return self.total_descartado / self.total_recebido if self.total_recebido else 0.0


class EventBus:
    """
    Fila limitada, com contabilidade de descarte.

    `maxsize` deve ser generoso: memoria e' barata comparada a dado perdido.
    500k envelopes ficam na casa de algumas centenas de MB no pior caso, o que
    absorve varios segundos de rajada de abertura mesmo em WIN.
    """

    def __init__(self, maxsize: int = 500_000) -> None:
        self._q: queue.Queue[Envelope | None] = queue.Queue(maxsize=maxsize)
        self._lock = threading.Lock()
        self._recebidos = 0
        self._descartados = 0
        self._pico = 0

    def publish(self, stream: Stream, event: Any) -> bool:
        """
        Chamado DE DENTRO do callback da DLL. Precisa ser rapido e nao levantar.

        Uma excecao que escape daqui atravessa a fronteira ctypes e o
        comportamento e' indefinido — em geral, queda do processo. Por isso o
        try/except abrangente: em caso de erro inesperado, contabilizamos como
        descarte e seguimos, em vez de derrubar a captura do dia.
        """
        try:
            self._q.put_nowait(Envelope(stream, event))
        except queue.Full:
            with self._lock:
                self._recebidos += 1
                self._descartados += 1
            return False
        except Exception:
            with self._lock:
                self._recebidos += 1
                self._descartados += 1
            return False

        with self._lock:
            self._recebidos += 1
            n = self._q.qsize()
            if n > self._pico:
                self._pico = n
        return True

    def drain(self, timeout: float, max_batch: int) -> list[Envelope]:
        """
        Retira um lote. Bloqueia ate `timeout` esperando o primeiro item, depois
        raspa o que ja estiver disponivel sem esperar mais.

        Lote grande e' o que torna a escrita eficiente: um row group Parquet por
        lote, em vez de uma chamada de escrita por evento.

        Um `None` na fila e' a sentinela de encerramento — devolvemos o lote
        parcial acumulado ate ali e sinalizamos com lista vazia na proxima volta.
        """
        lote: list[Envelope] = []
        try:
            primeiro = self._q.get(timeout=timeout)
        except queue.Empty:
            return lote
        if primeiro is None:
            raise _Shutdown(lote)
        lote.append(primeiro)

        while len(lote) < max_batch:
            try:
                item = self._q.get_nowait()
            except queue.Empty:
                break
            if item is None:
                raise _Shutdown(lote)
            lote.append(item)
        return lote

    def close(self) -> None:
        """Injeta a sentinela. Idempotente o suficiente para uso em signal handler."""
        # Fila cheia no encerramento: o writer vai drenar e ver a sentinela na
        # proxima tentativa. Nao bloqueamos aqui — este metodo pode ser chamado
        # de um handler de sinal, onde bloquear trava o processo.
        with contextlib.suppress(queue.Full):
            self._q.put_nowait(None)

    def stats(self) -> DropStats:
        with self._lock:
            return DropStats(self._recebidos, self._descartados, self._q.qsize(), self._pico)


class _Shutdown(Exception):
    """Sentinela interna. Carrega o lote parcial para nao perder o que ja veio."""

    def __init__(self, lote_parcial: list[Envelope]) -> None:
        super().__init__("shutdown")
        self.lote_parcial = lote_parcial
