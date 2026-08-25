"""
Thread de escrita. Drena o EventBus e materializa em Parquet.

Roda EM SEPARADO da thread de callback, por construcao. Se esta thread engasgar
(disco lento, GC longo), a fila cresce — e isso e' visivel na metrica de
profundidade. O feed nao para.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import structlog

from ..domain.enums import Stream
from ..domain.schema import schema_for
from ..health.metrics import Metrics
from ..storage.parquet_sink import ParquetSink
from .bus import Envelope, EventBus, _Shutdown

log = structlog.get_logger(__name__)


def _dia_de(ts_ns: int) -> str:
    """
    Data de particao, derivada do timestamp do EVENTO.

    Usar a data local do processo aqui seria um bug sutil: eventos que chegam
    logo apos a virada de dia cairiam na particao errada, e a reconstrucao
    ficaria com buraco no comeco e duplicata no fim.
    """
    return datetime.fromtimestamp(ts_ns / 1e9, tz=UTC).strftime("%Y-%m-%d")


class WriterThread(threading.Thread):
    def __init__(
        self,
        bus: EventBus,
        sink: ParquetSink,
        metrics: Metrics,
        batch_max: int = 50_000,
        poll_timeout: float = 0.5,
        idle_close_s: float = 900.0,
        limiar_lote_lento_s: float = 1.0,
    ) -> None:
        super().__init__(name="parquet-writer", daemon=False)
        self.bus = bus
        self.sink = sink
        self.metrics = metrics
        self.batch_max = batch_max
        self.poll_timeout = poll_timeout
        self.idle_close_s = idle_close_s
        self.limiar_lote_lento_s = limiar_lote_lento_s
        self._parar = threading.Event()
        self._ultimo_idle_check = time.monotonic()

    # ------------------------------------------------------------------
    def run(self) -> None:
        log.info("writer.iniciado", batch_max=self.batch_max)
        try:
            while not self._parar.is_set():
                try:
                    lote = self.bus.drain(self.poll_timeout, self.batch_max)
                except _Shutdown as fim:
                    self._processar(fim.lote_parcial)
                    break
                self._processar(lote)
                self._talvez_fechar_ociosos()
        except Exception:
            log.exception("writer.falha_fatal")
            raise
        finally:
            caminhos = self.sink.close()
            log.info("writer.encerrado", arquivos_fechados=len(caminhos))

    def parar(self) -> None:
        self._parar.set()

    # ------------------------------------------------------------------
    def _processar(self, lote: list[Envelope]) -> None:
        if not lote:
            return
        t0 = time.perf_counter()

        # Agrupa por (stream, dia, symbol) — a granularidade de arquivo.
        grupos: dict[tuple[Stream, str, str], list[Any]] = defaultdict(list)
        for env in lote:
            ev = env.event
            ts = getattr(ev, "ts_ns", None)
            # ts_ns=0 e' o caso NORMAL de offer book sem bHasDate (maioria
            # dos deltas — ver profitdll/client.py) — NAO e' epoch valido.
            # BUG REAL, ativo desde sempre (2026-08-26): so' checavamos
            # "ts is None" (cobria tiny_book, que nem tem o campo), mas
            # ts_ns=0 passava direto e datetime.fromtimestamp(0) produz
            # literalmente 1970-01-01 — uma particao fossil que a limpeza
            # manual anterior tratou como resíduo de uma versao velha, mas
            # na verdade era gerada TODO dia, silenciosamente, por qualquer
            # delta de offer book sem data. Corrigido: 0 tambem cai no
            # fallback de ts_recv_ns, igual None ja fazia.
            if ts is None or ts == 0:
                ts = ev.ts_recv_ns
            grupos[(env.stream, _dia_de(ts), ev.symbol)].append(ev)

        linhas = 0
        aberturas_antes = self.sink.aberturas
        por_stream: dict[str, int] = {}
        for (stream, dia, symbol), eventos in grupos.items():
            colunas = self._colunizar(stream, eventos)
            escritas = self.sink.write(stream, dia, symbol, colunas)
            linhas += escritas
            por_stream[stream.value] = por_stream.get(stream.value, 0) + escritas

        dt = time.perf_counter() - t0
        self.metrics.registrar_lote(por_stream)
        self.metrics.registrar_escrita(linhas, dt, self.sink.arquivos_abertos)

        if dt > self.limiar_lote_lento_s:
            if self.sink.aberturas > aberturas_antes:
                # Lote lento COINCIDINDO com criacao de arquivo: em HDD
                # USB/spin-down e' o disco acordando — esperado, nao e'
                # gargalo de vazao. INFO, nao WARNING: alarme para
                # comportamento esperado ensina a ignorar alarmes
                # (observacao do operador, 2026-08-21).
                log.info("writer.lote_lento_criacao_de_arquivo",
                         linhas=linhas, segundos=round(dt, 3),
                         nota="abertura de arquivo novo (spin-up?) — esperado "
                              "em disco USB; nao indica vazao insuficiente")
            else:
                # Sinal de alerta de verdade: lento SEM arquivo novo e' vazao,
                # e vazao insuficiente empurra a fila para cima.
                log.warning("writer.lote_lento", linhas=linhas,
                            segundos=round(dt, 3),
                            nota="sem criacao de arquivo — se recorrente, "
                                 "a fila vai subir")

    @staticmethod
    def _colunizar(stream: Stream, eventos: list[Any]) -> dict[str, list[Any]]:
        """
        Transposicao linha -> coluna.

        `zip(*eventos)` sobre NamedTuple e' C puro e bem mais rapido que
        list comprehension por campo. Os nomes vem do schema, garantindo que
        schema e evento nao divirjam sem quebrar em teste.
        """
        campos = [f.name for f in schema_for(stream)]
        transposto = list(zip(*eventos, strict=True))
        return dict(zip(campos, (list(c) for c in transposto), strict=True))

    def _talvez_fechar_ociosos(self) -> None:
        agora = time.monotonic()
        if agora - self._ultimo_idle_check < 60.0:
            return
        self._ultimo_idle_check = agora
        fechados = self.sink.close_idle(self.idle_close_s)
        if fechados:
            log.info("writer.rotacao_por_ociosidade", arquivos=len(fechados))
