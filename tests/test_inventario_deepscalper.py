"""Inventario DeepScalper (Fase 0) -- numeros conferidos no papel."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from profittape.research.inventario_deepscalper import (
    barras_de_um_dia,
    book_de_um_dia,
    gravar,
    inventario,
    spread_de_um_dia,
)

_NS = 10**9
_BASE = int(pd.Timestamp("2026-09-01 12:00:00", tz="UTC").timestamp()) * _NS


def _trades() -> pd.DataFrame:
    """5 agressoes de 09:00 a 11:00 (250 contratos) + 1 RLP que nao conta.
    Precos 100000/100005/100005/100015/100010 -> tick 5."""
    return pd.DataFrame({
        "ts_ns": [_BASE, _BASE + 1800 * _NS, _BASE + 3600 * _NS,
                  _BASE + 5400 * _NS, _BASE + 7200 * _NS, _BASE + 1000 * _NS],
        "price": [100000.0, 100005.0, 100005.0, 100015.0, 100010.0, 99990.0],
        "quantidade": [50, 70, 30, 60, 40, 999],
        "trade_type": [2, 3, 2, 3, 2, 13],
    })


def _tiny() -> pd.DataFrame:
    """bid 100000 / ask 100010 -> 2 ticks; bid 100005 -> 1 tick; ask 100005
    -> 0 (invalido); ask 0 -> lado vazio (fora); ask 100015 -> 2 ticks."""
    return pd.DataFrame({
        "ts_recv_ns": [1, 2, 3, 4, 5, 6],
        "side": [0, 1, 0, 1, 1, 1],
        "price": [100000.0, 100010.0, 100005.0, 100005.0, 0.0, 100015.0],
    })


def test_barras_a_mao() -> None:
    """250 // 100 = 2 barras em 2 h -> 1 barra/h -> h_120min = 2; tick 5."""
    b = barras_de_um_dia(_trades(), 100)
    assert b["vol_agr"] == 250.0
    assert b["negocios_agr"] == 5.0
    assert b["barras"] == 2.0
    assert b["horas"] == 2.0
    assert b["barras_por_hora"] == 1.0
    assert b["h_120min"] == 2.0
    assert b["tick"] == 5.0


def test_barras_sem_agressao() -> None:
    b = barras_de_um_dia(_trades().iloc[[5]], 100)
    assert b["barras"] == 0.0 and np.isnan(b["h_120min"])


def test_volume_barra_invalido() -> None:
    with pytest.raises(ValueError):
        barras_de_um_dia(_trades(), 0)


def test_spread_a_mao() -> None:
    """validos [2, 1, 2] -> mediana 2, 1/3 em 1 tick; 1 invalido; vazio fora."""
    s = spread_de_um_dia(_tiny(), 5.0)
    assert s["spread_mediana_ticks"] == 2.0
    assert s["spread_n"] == 3.0
    assert s["spread_invalidos"] == 1.0
    assert s["spread_frac_1tick"] == pytest.approx(1 / 3)


def test_lado_vazio_nao_arrasta_cotacao_velha() -> None:
    """Se o ask esvazia (price 0), a proxima observacao nao pode usar o ask
    anterior: e' NaN ate' chegar ask novo."""
    t = _tiny().iloc[:5]                      # termina no ask = 0
    s = spread_de_um_dia(t, 5.0)
    assert s["spread_n"] == 2.0 and s["spread_invalidos"] == 1.0


def test_spread_sem_tiny_ou_sem_tick() -> None:
    vazio = pd.DataFrame(columns=["ts_recv_ns", "side", "price"])
    assert spread_de_um_dia(vazio, 5.0)["spread_n"] == 0.0
    assert np.isnan(spread_de_um_dia(_tiny(), float("nan"))["spread_mediana_ticks"])


def _grava(pasta, df) -> None:  # type: ignore[no-untyped-def]
    pasta.mkdir(parents=True)
    pq.write_table(pa.table(df), pasta / "part-0000.parquet")


def _monta(tmp_path, dias):  # type: ignore[no-untyped-def]
    """Um pregao por item de `dias` = (dia, tem_offer, tem_price, tem_tiny)."""
    curated, raw = tmp_path / "curated", tmp_path / "raw"
    for k, (dia, offer, price, tiny) in enumerate(dias):
        d = _trades().copy()
        d["ts_ns"] = d["ts_ns"] + k * 86400 * _NS
        n = len(d)
        _grava(curated / "trade" / f"dt={dia}" / "sym=WINFUT", pd.DataFrame({
            "ts_ns": d["ts_ns"], "symbol": "WINFUT", "exchange": "F",
            "trade_id": np.arange(n), "price": d["price"], "volume_financeiro": 1.0,
            "quantidade": d["quantidade"], "agente_comprador": 3,
            "agente_vendedor": 85, "trade_type": d["trade_type"], "is_edit": False,
        }))
        book = pd.DataFrame({"ts_ns": [1], "ts_recv_ns": [1], "symbol": ["WINFUT"],
                             "exchange": ["F"], "side": [0], "price": [1.0]})
        if offer:
            _grava(raw / "book_offer" / f"dt={dia}" / "sym=WINFUT", book)
        if price:
            _grava(raw / "book_price" / f"dt={dia}" / "sym=WINFUT", book)
        if tiny:
            t = _tiny()
            t["symbol"], t["exchange"] = "WINFUT", "F"
            _grava(raw / "tiny_book" / f"dt={dia}" / "sym=WINFUT", t)
    return curated, raw


def test_book_integro_exige_data_e_os_dois_streams(tmp_path) -> None:  # type: ignore[no-untyped-def]
    _, raw = _monta(tmp_path, [
        ("2026-08-25", True, True, True),    # antes da correcao: nao confiavel
        ("2026-08-26", True, True, False),   # integro
        ("2026-08-27", True, False, True),   # sem book_price: nao integro
    ])
    assert book_de_um_dia(raw, "WINFUT", "2026-08-25")["book_integro"] is False
    assert book_de_um_dia(raw, "WINFUT", "2026-08-25")["book_confiavel_por_data"] is False
    assert book_de_um_dia(raw, "WINFUT", "2026-08-26")["book_integro"] is True
    assert book_de_um_dia(raw, "WINFUT", "2026-08-27")["book_integro"] is False
    assert book_de_um_dia(raw, "WINFUT", "2026-08-27")["n_book_offer"] == 1.0


def test_inventario_agrega_e_conta_faltantes(tmp_path) -> None:  # type: ignore[no-untyped-def]
    curated, raw = _monta(tmp_path, [
        ("2026-08-25", True, True, True),
        ("2026-08-26", True, True, False),
        ("2026-08-27", True, True, True),
    ])
    r = inventario(curated, raw, "WINFUT", 100)
    s = r["resumo"]
    assert s["pregoes_trade"] == 3
    assert s["pregoes_book_integro"] == 2
    assert s["faltam_para_portao_fase3"] == 158
    assert s["barras_por_pregao_mediana"] == 2.0
    assert s["barras_por_hora_mediana"] == 1.0
    assert s["h_120min"] == 2
    assert s["tick_mediana"] == 5.0
    assert s["spread_mediana_ticks"] == 2.0
    assert s["pregoes_com_tiny_book"] == 2
    assert list(r["por_dia"]["dia"]) == ["2026-08-25", "2026-08-26", "2026-08-27"]

    gravar(r, tmp_path / "saida")
    assert (tmp_path / "saida" / "por_dia.parquet").exists()
    with open(tmp_path / "saida" / "resumo.json", encoding="utf-8") as f:
        assert json.load(f)["h_120min"] == 2


def test_sem_pregao_falha_alto(tmp_path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "curated" / "trade").mkdir(parents=True)
    with pytest.raises(SystemExit, match="nenhum pregao"):
        inventario(tmp_path / "curated", tmp_path / "raw", "WINFUT", 100)
