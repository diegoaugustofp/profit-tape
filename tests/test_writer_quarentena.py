"""Residuo do pregao anterior entregue na assinatura (2026-09-21).

Ao subir, o record gravava eventos com o dia de ONTEM (16/09 e 17/09
confirmados; em 17/09, 9 simbolos com 1 linha cada), criando a pasta
`dt=` do dia anterior no raw -- e uma cura sem `--dia` destruiu um pregao
inteiro. Agora o record ao vivo manda esses eventos para `_quarentena/`.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from profittape.domain.enums import Stream
from profittape.domain.events import Trade
from profittape.health.metrics import Metrics
from profittape.pipeline.bus import Envelope, EventBus
from profittape.pipeline.writer import WriterThread
from profittape.storage.parquet_sink import ParquetSink

NS = 1_000_000_000
TZ = dt.timezone(dt.timedelta(hours=-3))


def _ts(ano: int, mes: int, dia: int, h: int, m: int) -> int:
    return int(dt.datetime(ano, mes, dia, h, m, tzinfo=TZ).timestamp() * NS)


def _trade(ts: int, symbol: str = "WINFUT", recv: int | None = None) -> Trade:
    return Trade(ts_ns=ts, ts_recv_ns=recv if recv is not None else ts, symbol=symbol,
                 exchange="F", trade_id=1, price=188095.0, volume_financeiro=0.0,
                 quantidade=91, agente_comprador=0, agente_vendedor=3, trade_type=3,
                 is_edit=False)


def _writer(raiz: Path, sessao: str | None) -> WriterThread:
    return WriterThread(EventBus(maxsize=100), ParquetSink(raiz), Metrics(),
                        quarentena_antes_de=sessao,
                        quarentena_sink=ParquetSink(raiz / "_quarentena") if sessao else None)


def test_residuo_de_ontem_vai_para_a_quarentena_e_hoje_fica_no_raw(tmp_path: Path) -> None:
    w = _writer(tmp_path, "2026-09-18")
    ontem = _trade(_ts(2026, 9, 17, 18, 24), recv=_ts(2026, 9, 18, 7, 58))  # entregue hoje
    hoje = _trade(_ts(2026, 9, 18, 9, 1))
    w._processar([Envelope(Stream.TRADE, ontem), Envelope(Stream.TRADE, hoje)])
    w.sink.close()
    assert w.quarentena_sink is not None
    w.quarentena_sink.close()
    assert w.quarentenados == {"trade": 1}
    assert not (tmp_path / "trade" / "dt=2026-09-17").exists()   # nada de ontem no raw
    assert (tmp_path / "trade" / "dt=2026-09-18").exists()
    assert list((tmp_path / "_quarentena" / "trade" / "dt=2026-09-17").rglob("*.parquet"))


def test_sem_sessao_nada_muda_e_o_backfill_grava_dias_passados(tmp_path: Path) -> None:
    """O BACKFILL usa o mesmo writer e PRECISA gravar dias passados."""
    w = _writer(tmp_path, None)
    w._processar([Envelope(Stream.TRADE, _trade(_ts(2026, 9, 10, 10, 0)))])
    w.sink.close()
    assert w.quarentenados == {}
    assert (tmp_path / "trade" / "dt=2026-09-10").exists()


def test_after_do_proprio_dia_nao_e_quarentenado(tmp_path: Path) -> None:
    """O dia e' comparado no fuso LOCAL: 18:29 BRT ja' e' 21:29 UTC, mas e'
    o mesmo pregao."""
    w = _writer(tmp_path, "2026-09-18")
    w._processar([Envelope(Stream.TRADE, _trade(_ts(2026, 9, 18, 18, 29)))])
    w.sink.close()
    assert w.quarentenados == {}
