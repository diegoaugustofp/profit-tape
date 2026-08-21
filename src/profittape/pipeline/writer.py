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
    ) -> None:
        super().__init__(name="parquet-writer", daemon=False)
        self.bus = bus
        self.sink = sink
        self.metrics = metrics
        self.batch_max = batch_max
        self.poll_timeout = poll_timeout
        self.idle_close_s = idle_close_s
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
            if ts is None:  # tiny book so tem ts_recv_ns
                ts = ev.ts_recv_ns
            grupos[(env.stream, _dia_de(ts), ev.symbol)].append(ev)

        linhas = 0
        for (stream, dia, symbol), eventos in grupos.items():
            colunas = self._colunizar(stream, eventos)
            linhas += self.sink.write(stream, dia, symbol, colunas)

        dt = time.perf_counter() - t0
        self.metrics.registrar_escrita(linhas, dt, self.sink.arquivos_abertos)

        if dt > 1.0:
            # Sinal de alerta: escrita lenta empurra a fila para cima.
            log.warning("writer.lote_lento", linhas=linhas, segundos=round(dt, 3))

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
