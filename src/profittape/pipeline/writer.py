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
from datetime import UTC, datetime, timedelta, timezone
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
        quarentena_antes_de: str | None = None,
        quarentena_sink: ParquetSink | None = None,
        tz_offset_horas: int = -3,
    ) -> None:
        super().__init__(name="parquet-writer", daemon=False)
        # QUARENTENA DO DIA ANTERIOR (2026-09-21). Ao subir, o record gravava
        # um RESIDUO do pregao anterior (16/09 e 17/09 confirmados; 9
        # simbolos com 1 linha cada em 17/09), criando a pasta `dt=` de ONTEM
        # no raw -- e uma cura sem `--dia` destruiu um pregao inteiro por
        # causa disso. Evento cujo dia LOCAL e' anterior ao dia da sessao vai
        # para `raiz/_quarentena/`, que a cura nao le, e os primeiros sao
        # logados POR INTEIRO (`recorder.evento_de_dia_anterior`) -- e' esse
        # log que vai dizer O QUE a DLL entrega na assinatura.
        # OPCIONAL (None = desligado): o BACKFILL usa este mesmo writer e
        # precisa gravar dias passados.
        self.quarentena_antes_de = quarentena_antes_de
        self.quarentena_sink = quarentena_sink
        self._tz = timezone(timedelta(hours=tz_offset_horas))
        self.quarentenados: dict[str, int] = {}
        self._logados_quarentena = 0
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
        # A raiz no log de partida: sem isto, nao ha' como saber DEPOIS em
        # que disco o pregao foi gravado -- e a nota de `lote_lento`
        # afirmava "disco USB" sem checar nada, o que enganou o
        # diagnostico de 24/09 (o storage estava em C:).
        raiz = getattr(self.sink, "raiz", None)
        log.info("writer.iniciado", batch_max=self.batch_max,
                 raiz=str(raiz) if raiz else None,
                 drive=(str(raiz)[:2] if raiz and len(str(raiz)) > 1 else None))
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
            if self.quarentena_sink is not None:
                self.quarentena_sink.close()
            log.info("writer.encerrado", arquivos_fechados=len(caminhos),
                     quarentenados=self.quarentenados or None)

    def parar(self) -> None:
        self._parar.set()

    # ------------------------------------------------------------------
    def _e_de_dia_anterior(self, ts_ns: int) -> bool:
        dia_local = datetime.fromtimestamp(ts_ns / 1e9, tz=self._tz).date().isoformat()
        return bool(self.quarentena_antes_de and dia_local < self.quarentena_antes_de)

    def _quarentenar(self, stream: Stream, ev: Any, ts_ns: int) -> None:
        self.quarentenados[stream.value] = self.quarentenados.get(stream.value, 0) + 1
        if self._logados_quarentena < 50:
            self._logados_quarentena += 1
            detalhe = {k: getattr(ev, k) for k in ("trade_id", "price", "quantidade",
                                                    "trade_type", "action", "side")
                       if hasattr(ev, k)}
            log.warning("recorder.evento_de_dia_anterior", stream=stream.value,
                        symbol=ev.symbol,
                        ts_evento=datetime.fromtimestamp(ts_ns / 1e9, tz=self._tz).isoformat(),
                        ts_recebido=datetime.fromtimestamp(ev.ts_recv_ns / 1e9,
                                                           tz=self._tz).isoformat(),
                        sessao=self.quarentena_antes_de, **detalhe,
                        nota="gravado em _quarentena/, fora do raw normal (a cura nao le)")
        if self.quarentena_sink is not None:
            colunas = self._colunizar(stream, [ev])
            self.quarentena_sink.write(stream, _dia_de(ts_ns), ev.symbol, colunas)

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
            if self.quarentena_antes_de is not None and self._e_de_dia_anterior(ts):
                self._quarentenar(env.stream, ev, ts)
                continue
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
                         nota="lote lento COM criacao de arquivo. Em disco "
                              "externo/USB isto e' spin-up esperado; em disco "
                              "INTERNO nao e' -- ai' investigue I/O. O codigo "
                              "NAO sabe em que disco esta' gravando (a nota "
                              "anterior afirmava USB e enganava: 24/09 o "
                              "storage estava em C:)")
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
