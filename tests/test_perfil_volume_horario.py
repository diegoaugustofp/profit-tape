"""Perfil de volume por faixa horaria -- numeros conferidos no papel."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from profittape.research.perfil_volume_horario import perfil, perfil_de_um_dia

_NS = 10**9
# 2026-09-01 12:00:00 UTC == 09:00 em UTC-3
_BASE = int(pd.Timestamp("2026-09-01 12:00:00", tz="UTC").timestamp())


def _t(hh: int, mm: int, ss: int = 0) -> int:
    return (_BASE + (hh - 9) * 3600 + mm * 60 + ss) * _NS


def _dia() -> pd.DataFrame:
    rows = [
        (_t(9, 0, 5), 10, 2), (_t(9, 10), 20, 3), (_t(9, 20), 5, 13),   # RLP fora
        (_t(9, 31), 15, 2),
        (_t(10, 5), 60, 3), (_t(10, 15), 30, 2), (_t(10, 25), 30, 4),   # leilao fora
    ]
    return pd.DataFrame(rows, columns=["ts_ns", "quantidade", "trade_type"])


def test_perfil_de_um_dia_a_mao() -> None:
    """09:00 = 30 contratos/2 negocios; 09:30 = 15/1; 10:00 = 90/2.
    total 135 -> 22,2% / 11,1% / 66,7%; abertura completa -> 1 / 0,5 / 3."""
    p = perfil_de_um_dia(_dia(), 30)
    assert list(p["faixa"]) == ["09:00", "09:30", "10:00"]
    assert list(p["contratos"]) == [30.0, 15.0, 90.0]
    assert list(p["negocios"]) == [2.0, 1.0, 2.0]
    assert list(p["pct_do_dia"].round(4)) == [0.2222, 0.1111, 0.6667]
    assert list(p["pct_da_abertura"]) == [1.0, 0.5, 3.0]
    assert p["por_barra_15s"].iloc[0] == pytest.approx(2 / 120)


def test_abertura_parcial_usa_a_proxima_faixa_como_referencia() -> None:
    """Primeiro negocio de agressao as 09:20 -> a faixa 09:00 e' parcial e
    a referencia passa a ser 09:30."""
    d = _dia()
    d.loc[0, "ts_ns"] = _t(9, 20, 30)          # o primeiro agressor cai em 09:20
    d = d.drop(index=1).reset_index(drop=True)  # some o das 09:10
    p = perfil_de_um_dia(d, 30)
    assert list(p["faixa"]) == ["09:00", "09:30", "10:00"]
    assert p["pct_da_abertura"].iloc[1] == 1.0
    assert p["pct_da_abertura"].iloc[2] == 6.0


def test_faixa_precisa_dividir_60() -> None:
    with pytest.raises(ValueError):
        perfil_de_um_dia(_dia(), 45)


def test_perfil_mediana_entre_pregoes(tmp_path) -> None:  # type: ignore[no-untyped-def]
    curated = tmp_path / "curated"
    for k, dia in enumerate(("2026-09-01", "2026-09-02", "2026-09-03")):
        d = _dia().copy()
        d["ts_ns"] = d["ts_ns"] + k * 86400 * _NS
        d["quantidade"] = d["quantidade"] * (k + 1)      # 1x, 2x, 3x -> mediana = 2x
        n = len(d)
        df = pd.DataFrame({
            "ts_ns": d["ts_ns"], "symbol": "WINFUT", "exchange": "F",
            "trade_id": np.arange(n), "price": 140000.0, "volume_financeiro": 1.0,
            "quantidade": d["quantidade"], "agente_comprador": 3,
            "agente_vendedor": 85, "trade_type": d["trade_type"], "is_edit": False,
        })
        pasta = curated / "trade" / f"dt={dia}" / "sym=WINFUT"
        pasta.mkdir(parents=True)
        pq.write_table(pa.table(df), pasta / "part-0000.parquet")
    r = perfil(curated, "WINFUT", 30)
    assert r["pregoes"] == 3
    m = r["mediana"].set_index("faixa")
    assert m.loc["09:00", "contratos"] == 60.0          # 30 x 2
    assert m.loc["10:00", "pct_da_abertura"] == 3.0     # razao nao muda com a escala
    assert list(m["pregoes"]) == [3, 3, 3]


def test_sem_pregao_falha_alto(tmp_path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "curated" / "trade").mkdir(parents=True)
    with pytest.raises(SystemExit, match="nenhum pregao"):
        perfil(tmp_path / "curated", "WINFUT")
