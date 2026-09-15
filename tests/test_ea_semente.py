"""ea/semente.py -- semente da MME80 (passo 2 do F5 do 123)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from profittape.ea import semente as sm

NS = 1_000_000_000


def _parquet(tmp_path: Path, dias: list[dt.date], closes_por_dia: int = 37,
             seed: int = 1) -> tuple[Path, pd.DataFrame]:
    """Historico 'do grafico': closes aleatorios e mme80_ntsl calculada com
    a mesma recursao (semeada no primeiro close, como o Profit)."""
    rng = np.random.default_rng(seed)
    linhas = []
    for d in dias:
        h, m = 9, 0
        for _ in range(closes_por_dia):
            linhas.append({"dia": d, "hhmm": h * 100 + m,
                           "close": 0.0, "mme80_ntsl": 0.0})
            m += 15
            if m == 60:
                h, m = h + 1, 0
    df = pd.DataFrame(linhas)
    df["close"] = 140000.0 + np.cumsum(rng.normal(0, 40, len(df)))
    alpha = 2 / 81
    v = df["close"].iloc[0]
    out = []
    for c in df["close"]:
        v = alpha * c + (1 - alpha) * v
        out.append(v)
    df["mme80_ntsl"] = out
    p = tmp_path / "barras_123.parquet"
    df.to_parquet(p, index=False)
    return p, df


def _tape_fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
               barras_por_dia: dict[dt.date, list[float]]) -> Path:
    """Curated falso: um trade por barra M15, no open da barra, com o close dado."""
    curated = tmp_path / "curated"

    def _carregar(pasta: Path, sym: str) -> pd.DataFrame:
        dia = dt.date.fromisoformat(pasta.name.split("=")[1])
        closes = barras_por_dia.get(dia, [])
        t0 = int(pd.Timestamp(f"{dia} 12:00:00", tz="UTC").value)      # 09:00 BRT
        return pd.DataFrame({"ts_ns": [t0 + i * 900 * NS + NS for i in range(len(closes))],
                             "price": closes, "quantidade": [1] * len(closes),
                             "trade_type": [2] * len(closes)})
    for dia in barras_por_dia:
        (curated / "trade" / f"dt={dia}" / "sym=WINFUT").mkdir(parents=True)
    monkeypatch.setattr(sm, "_carregar_dia", _carregar)
    return curated


def test_indicador_mme_recursao() -> None:
    m = sm.IndicadorMME(2, 10.0)           # alpha 2/3
    assert m.atualizar(13.0) == pytest.approx(12.0)
    assert m.n == 1


def test_semente_exata_do_parquet_sem_ponte(tmp_path: Path) -> None:
    dias = [dt.date(2026, 9, 8), dt.date(2026, 9, 9), dt.date(2026, 9, 10)]
    p, df = _parquet(tmp_path, dias)
    s = sm.construir_semente(p, dt.date(2026, 9, 11))         # sexta; parquet ate' quinta
    assert s.valida and s.ponte_dias == []
    assert s.valor == pytest.approx(df["mme80_ntsl"].iloc[-1])
    assert s.ultima_barra == "2026-09-10 1800"
    assert s.parquet_ate == "2026-09-10"


def test_ponte_pelo_tape_continua_a_recursao(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dias = [dt.date(2026, 9, 8), dt.date(2026, 9, 9)]
    p, df = _parquet(tmp_path, dias)
    closes_10 = [140000.0 + i for i in range(37)]
    curated = _tape_fake(monkeypatch, tmp_path, {dt.date(2026, 9, 10): closes_10})
    s = sm.construir_semente(p, dt.date(2026, 9, 11), curated)
    assert s.valida and s.ponte_dias == ["2026-09-10"]
    m = sm.IndicadorMME(80, float(df["mme80_ntsl"].iloc[-1]))
    for c in closes_10:
        m.atualizar(c)
    assert s.valor == pytest.approx(m.valor)
    assert s.ultima_barra == "2026-09-10 1800"


def test_dia_util_sem_tape_invalida_e_feriado_declarado_passa(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p, _ = _parquet(tmp_path, [dt.date(2026, 9, 8)])
    curated = _tape_fake(monkeypatch, tmp_path, {dt.date(2026, 9, 10): [140000.0] * 37})
    s = sm.construir_semente(p, dt.date(2026, 9, 11), curated)          # falta 09/09
    assert not s.valida and "2026-09-09" in s.motivo
    s2 = sm.construir_semente(p, dt.date(2026, 9, 11), curated,
                              feriados=(dt.date(2026, 9, 9),))
    assert s2.valida and s2.ponte_dias == ["2026-09-10"]


def test_dia_com_tape_fino_invalida(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p, _ = _parquet(tmp_path, [dt.date(2026, 9, 9)])
    curated = _tape_fake(monkeypatch, tmp_path, {dt.date(2026, 9, 10): [140000.0] * 5})
    s = sm.construir_semente(p, dt.date(2026, 9, 11), curated)
    assert not s.valida and "5 barras" in s.motivo
    assert s.barras_por_dia_ponte == {"2026-09-10": 5}


def test_sem_parquet_ou_sem_historico_antes_do_dia(tmp_path: Path) -> None:
    s = sm.construir_semente(tmp_path / "nao.parquet", dt.date(2026, 9, 11))
    assert not s.valida and "nao existe" in s.motivo
    p, _ = _parquet(tmp_path, [dt.date(2026, 9, 11)])
    s = sm.construir_semente(p, dt.date(2026, 9, 11))
    assert not s.valida and "antes de" in s.motivo


def test_conferir_no_dia_bate_com_o_grafico(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Semente do parquet ate' D-1, tape de D com os MESMOS closes do
    grafico: a recursao tem que reproduzir o mme80_ntsl de D ao centesimo."""
    dias = [dt.date(2026, 9, 8), dt.date(2026, 9, 9), dt.date(2026, 9, 10)]
    p, df = _parquet(tmp_path, dias)
    closes_10 = df[df["dia"] == dt.date(2026, 9, 10)]["close"].tolist()
    curated = _tape_fake(monkeypatch, tmp_path, {dt.date(2026, 9, 10): closes_10})
    r = sm.conferir_no_dia(p, dt.date(2026, 9, 10), curated)
    assert r["semente"]["valida"] and r["comparaveis"] == 37
    assert r["dif_max"] == 0.0


def test_conferir_no_dia_sem_tape_devolve_so_a_semente(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bug real (2026-09-14, `--dia 2026-09-15` na vespera): dia sem tape
    quebrava com KeyError('dif'). Agora devolve a semente e uma nota."""
    p, _ = _parquet(tmp_path, [dt.date(2026, 9, 10), dt.date(2026, 9, 11)])
    curated = _tape_fake(monkeypatch, tmp_path, {dt.date(2026, 9, 14): [140000.0] * 34})
    r = sm.conferir_no_dia(p, dt.date(2026, 9, 15), curated)
    assert r["semente"]["valida"] and r["semente"]["ponte_dias"] == ["2026-09-14"]
    assert r["barras"] == 0 and r["dif_max"] is None and "sem tape" in r["nota"]
