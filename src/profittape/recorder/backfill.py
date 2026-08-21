"""
Backfill do historico de trades.

O QUE DA E O QUE NAO DA PARA PEDIR
----------------------------------
Trades: sim, via GetHistoryTrades. Book: nao — e' realtime puro, e nenhum
backfill traz o livro de ontem de volta.

A PROFUNDIDADE E' UMA PERGUNTA EMPIRICA
---------------------------------------
Quanto historico intradiario o servidor entrega varia por corretora e conta,
e a documentacao nao promete nada. A mesma licao do data_audit do MT5 vale
aqui: peca um intervalo longo e MECA o que veio, em vez de assumir. O resumo
final imprime o primeiro e o ultimo timestamp recebidos por ativo justamente
para isso.

COMO SABER QUE ACABOU
---------------------
A DLL nao emite "fim do historico" confiavel entre versoes. O criterio aqui e'
quiesce: se nenhum evento novo chega por `quiesce_s` segundos depois do
primeiro lote, consideramos completo. Conservador e a prova de versao.
"""

from __future__ import annotations

import time
from datetime import datetime

import structlog

from ..config import Credenciais, RecorderConfig
from ..health.metrics import Metrics
from ..pipeline.bus import EventBus
from ..pipeline.writer import WriterThread
from ..profitdll.client import ProfitClient
from ..storage.parquet_sink import ParquetSink

log = structlog.get_logger(__name__)


def _iso_para_dll(iso: str) -> str:
    """'2026-08-20' -> '20/08/2026'. Falha cedo e com mensagem clara."""
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError as exc:
        raise ValueError(f"Data deve ser YYYY-MM-DD, veio {iso!r}") from exc


def executar(
    cfg: RecorderConfig,
    cred: Credenciais,
    inicio_iso: str,
    fim_iso: str,
    quiesce_s: float = 15.0,
    timeout_s: float = 3600.0,
    dll_injetada: object | None = None,
) -> int:
    inicio = _iso_para_dll(inicio_iso)
    fim = _iso_para_dll(fim_iso)

    metrics = Metrics()
    bus = EventBus(maxsize=cfg.pipeline.fila_maxsize)
    sink = ParquetSink(
        raiz=cfg.storage.raiz,
        max_rows_per_file=cfg.storage.max_rows_per_file,
        compressao=cfg.storage.compressao,
        nivel_compressao=cfg.storage.nivel_compressao,
    )
    writer = WriterThread(
        bus=bus, sink=sink, metrics=metrics,
        batch_max=cfg.pipeline.batch_max,
        poll_timeout=cfg.pipeline.poll_timeout_s,
    )
    client = ProfitClient(
        dll_path=cred.dll_path, activation_key=cred.activation_key,
        user=cred.user, password=cred.password, bus=bus,
        tz_offset_horas=cfg.runtime.tz_offset_horas, dll=dll_injetada,
    )

    writer.start()
    try:
        client.connect()
        for a in cfg.ativos:
            client.request_history(a.ticker, inicio, fim, a.bolsa)
            log.info("backfill.pedido", ticker=a.ticker, inicio=inicio, fim=fim)

        # Quiesce: espera o total parar de crescer. Mesma logica do seu
        # data_audit no MT5 — a primeira resposta de download assincrono e'
        # sempre parcial, e quem le cedo demais subestima o que existe.
        t0 = time.monotonic()
        anterior = -1
        estavel_desde = time.monotonic()
        while time.monotonic() - t0 < timeout_s:
            time.sleep(1.0)
            atual = bus.stats().total_recebido
            if atual != anterior:
                anterior = atual
                estavel_desde = time.monotonic()
            elif atual > 0 and time.monotonic() - estavel_desde >= quiesce_s:
                log.info("backfill.quiesce", eventos=atual)
                break
        else:
            log.warning("backfill.timeout", eventos=anterior,
                        aviso="pode estar incompleto — aumente --timeout")

        if anterior <= 0:
            log.error(
                "backfill.vazio",
                hipoteses="servidor fora do ar (tente em horario comercial), "
                          "conta sem historico provisionado, ou intervalo sem pregao",
            )
    except Exception:
        log.exception("backfill.erro")
        return 1
    finally:
        client.disconnect()
        bus.close()
        writer.join(timeout=300)

    st = bus.stats()
    log.info(
        "backfill.resumo",
        eventos=st.total_recebido, descartados=st.total_descartado,
        raiz=str(cfg.storage.raiz),
        proximo_passo="profit-tape inspect para ver a profundidade REAL entregue, "
                      "e profit-tape curate antes de calcular qualquer feature",
    )
    return 0 if st.total_recebido > 0 else 2
