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
import time
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
        self.maxsize = maxsize
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
        continua aceitando itens DENTRO DO MESMO ORCAMENTO DE TEMPO (nao mais
        get_nowait() -- ver BUG abaixo) ate max_batch ou o tempo acabar.

        Lote grande e' o que torna a escrita eficiente: um row group Parquet por
        lote, em vez de uma chamada de escrita por evento.

        BUG REAL, ativo desde o primeiro commit do projeto (2026-08-21) ate'
        2026-09-10: a versao anterior usava `get_nowait()` (espera ZERO) para
        todo item apos o primeiro, contradizendo o proprio docstring ("Lote
        grande..."). Isso so' produz lote grande quando itens chegam em RAJADA
        instantanea (varios ja' na fila no mesmo instante). Para um produtor de
        alta frequencia mas CADENCIA REGULAR -- o padrao real de WINFUT, o
        ativo mais liquido -- o consumidor "vencia a corrida" quase sempre:
        acordava no primeiro item, checava get_nowait(), achava vazio (o
        proximo evento ainda nao tinha chegado), devolvia lote de 1. Descoberto
        via row groups por arquivo: WINFUT em 08/09 tinha ~15 linhas por row
        group (34.525 row groups para 519.764 linhas) contra o esperado de
        milhares de linhas por row group -- overhead de metadado por row group
        multiplicado por dezenas de milhares fazia UM SIMBOLO levar 4h48min
        pra ler (90 KB/s efetivo) onde deveria levar segundos. Nao e' bug
        exclusivo de ontem: qualquer dia de producao com WINFUT tem o mesmo
        padrao, ja que a causa e' estrutural na cadencia de escrita, nao no
        teste do E1 nem em nada externo (antivirus, backup, disco -- todos
        investigados e descartados antes de chegar aqui).

        CORRECAO: apos o primeiro item, cada get() subsequente usa o TEMPO
        RESTANTE do mesmo orcamento (nao zero) -- deixa o produtor ter a
        MESMA janela de `timeout` pra empilhar itens que o primeiro item ja'
        teve, em vez de dar zero chance pros seguintes. Numa fila QUIETA
        (eventos esporadicos), o comportamento nao piora: se nada mais
        chegar, o timeout estoura naturalmente e devolve o que tem, dentro do
        mesmo limite de latencia de sempre -- so' que agora genuinamente ate'
        o fim da janela, nao "ate' a fila parecer vazia num instante".

        Um `None` na fila e' a sentinela de encerramento — devolvemos o lote
        parcial acumulado ate ali e sinalizamos com lista vazia na proxima volta.
        """
        lote: list[Envelope] = []
        prazo = time.monotonic() + timeout
        try:
            primeiro = self._q.get(timeout=timeout)
        except queue.Empty:
            return lote
        if primeiro is None:
            raise _Shutdown(lote)
        lote.append(primeiro)

        while len(lote) < max_batch:
            restante = prazo - time.monotonic()
            if restante <= 0:
                break
            try:
                item = self._q.get(timeout=restante)
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


def nivel_ocupacao(fila_atual: int, maxsize: int) -> str | None:
    """
    Classificacao padronizada da ocupacao da fila, para alerta ANTES do
    descarte. Descarte so' acontece a 100% — avisar a 10% e 50% da' tempo de
    reagir (tipicamente: disco lento segurando o writer). Um unico criterio
    aqui evita que record e backfill divirjam no que consideram 'alerta'.
    """
    if maxsize <= 0:
        return None
    ocupacao = fila_atual / maxsize
    if ocupacao >= 0.50:
        return "critico"
    if ocupacao >= 0.10:
        return "atencao"
    return None


class _Shutdown(Exception):
    """Sentinela interna. Carrega o lote parcial para nao perder o que ja veio."""

    def __init__(self, lote_parcial: list[Envelope]) -> None:
        super().__init__("shutdown")
        self.lote_parcial = lote_parcial
