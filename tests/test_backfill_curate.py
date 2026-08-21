"""Backfill (quiesce) e curadoria (dedup, exclusao de ts invalido)."""

from __future__ import annotations

from pathlib import Path

import pyarrow.dataset as ds
import pytest

from profittape.config import (
    AtivoConfig,
    Credenciais,
    PipelineConfig,
    RecorderConfig,
    RuntimeConfig,
    StorageConfig,
)
from profittape.domain.enums import Stream
from profittape.domain.events import Trade
from profittape.recorder.backfill import _iso_para_dll, executar
from profittape.storage.parquet_sink import ParquetSink
from profittape.tools.curate import curar_trades
from tests.fakes.fake_dll import FakeProfitDLL


def test_conversao_de_data() -> None:
    assert _iso_para_dll("2026-08-20") == "20/08/2026"
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        _iso_para_dll("20/08/2026")


def test_backfill_ponta_a_ponta(tmp_raiz: Path) -> None:
    cfg = RecorderConfig(
        ativos=[AtivoConfig(ticker="PETR4"), AtivoConfig(ticker="VALE3")],
        storage=StorageConfig(raiz=tmp_raiz),
        pipeline=PipelineConfig(poll_timeout_s=0.1),
        runtime=RuntimeConfig(),
    )
    cred = Credenciais(activation_key="k", user="u", password="p", dll_path="fake")
    fake = FakeProfitDLL(eventos_por_ativo=300)

    rc = executar(cfg, cred, "2026-08-18", "2026-08-19",
                  quiesce_s=1.5, timeout_s=20, dll_injetada=fake)
    assert not fake.erros, f"thread emissora do fake morreu: {fake.erros[0]!r}"
    assert rc == 0

    tabela = ds.dataset(tmp_raiz / "trade", format="parquet", partitioning="hive").to_table()
    assert tabela.num_rows == 600
    assert set(tabela["symbol"].to_pylist()) == {"PETR4", "VALE3"}
    # O quiesce nao pode cortar cedo: os 300 de cada ativo tem que estar la.
    assert max(tabela["trade_id"].to_pylist()) == 300


def _trade(i: int, trade_id: int, ts: int, recv: int, sym: str = "PETR4") -> Trade:
    return Trade(ts_ns=ts, ts_recv_ns=recv, symbol=sym, exchange="B",
                 trade_id=trade_id, price=30.0 + i * 0.01, volume_financeiro=3000.0,
                 quantidade=100, agente_comprador=3, agente_vendedor=8,
                 trade_type=2, is_edit=i % 2 == 1)


def test_curadoria_deduplica_e_exclui_ts_invalido(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    curated = tmp_path / "curated"
    base = 1_704_193_200_000_000_000
    sink = ParquetSink(raw)

    eventos = [
        _trade(0, trade_id=1, ts=base, recv=base + 100),
        _trade(1, trade_id=1, ts=base, recv=base + 900),      # edicao: vence (preco 30.01)
        _trade(2, trade_id=2, ts=base + 5_000, recv=base + 5_100),
        _trade(3, trade_id=3, ts=0, recv=base + 6_000),        # parse falhou: excluir
        _trade(4, trade_id=4, ts=base + 1_000, recv=base + 1_100),
    ]
    cols = dict(zip(Trade._fields, (list(c) for c in zip(*eventos, strict=True)), strict=True))
    sink.write(Stream.TRADE, "2024-01-02", "PETR4", cols)
    sink.close()

    t = curar_trades(raw, curated)
    assert t == {"lidas": 5, "duplicatas": 1, "ts_invalido": 1, "gravadas": 3, "particoes": 1}

    tabela = ds.dataset(curated / "trade", format="parquet", partitioning="hive").to_table()
    ids = tabela["trade_id"].to_pylist()
    assert ids == [1, 4, 2]                       # ordenado por ts_ns
    assert 0 not in tabela["ts_ns"].to_pylist()
    linha_1 = tabela.to_pylist()[0]
    assert linha_1["price"] == pytest.approx(30.01)  # a EDICAO venceu, nao a original


def test_ticker_recusado_nao_aborta_os_demais(tmp_raiz: Path) -> None:
    """
    Regressao do incidente real: GetHistoryTrades devolveu NL desconhecido para
    WINFUT e o backfill abortou sem tentar PETR4/VALE3 — jogando fora justamente
    o padrao diferencial que diagnostica a causa.
    """
    cfg = RecorderConfig(
        ativos=[
            AtivoConfig(ticker="FAILHIST_WINFUT", bolsa="F"),
            AtivoConfig(ticker="PETR4"),
        ],
        storage=StorageConfig(raiz=tmp_raiz),
        pipeline=PipelineConfig(poll_timeout_s=0.1),
        runtime=RuntimeConfig(),
    )
    cred = Credenciais(activation_key="k", user="u", password="p", dll_path="fake")
    fake = FakeProfitDLL(eventos_por_ativo=100)

    rc = executar(cfg, cred, "2026-08-18", "2026-08-19",
                  quiesce_s=1.5, timeout_s=20, dll_injetada=fake)
    assert rc == 0

    tabela = ds.dataset(tmp_raiz / "trade", format="parquet", partitioning="hive").to_table()
    assert set(tabela["symbol"].to_pylist()) == {"PETR4"}
    assert tabela.num_rows == 100


def test_todos_recusados_devolve_2(tmp_raiz: Path) -> None:
    cfg = RecorderConfig(
        ativos=[AtivoConfig(ticker="FAILHIST_A"), AtivoConfig(ticker="FAILHIST_B")],
        storage=StorageConfig(raiz=tmp_raiz),
        pipeline=PipelineConfig(poll_timeout_s=0.1),
        runtime=RuntimeConfig(),
    )
    cred = Credenciais(activation_key="k", user="u", password="p", dll_path="fake")
    rc = executar(cfg, cred, "2026-08-18", "2026-08-19",
                  quiesce_s=1.0, timeout_s=10,
                  dll_injetada=FakeProfitDLL(eventos_por_ativo=10))
    assert rc == 2


def test_describe_codigo_desconhecido_da_offset() -> None:
    from profittape.profitdll.errors import describe

    msg = describe(-2147483602)
    assert "base+46" in msg
    assert "0x8000002e" in msg
