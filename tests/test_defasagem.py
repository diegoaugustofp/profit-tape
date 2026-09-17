"""Defasagem WIN x cesta: ha' ordem de chegada? (zero trial)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from profittape.research import defasagem as dfg

NS = 1_000_000_000


def _curated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
             series: dict[str, np.ndarray], dia: dt.date, periodo_s: int = 60) -> Path:
    """Um trade por barra, por ativo, no mesmo relogio."""
    t0 = int(pd.Timestamp(f"{dia} 12:00:00", tz="UTC").value)
    tabelas = {}
    for sym, precos in series.items():
        tabelas[sym] = pd.DataFrame({
            "ts_ns": [t0 + i * periodo_s * NS + NS for i in range(len(precos))],
            "price": precos, "quantidade": 1, "trade_type": 2})
    curated = tmp_path / "curated"
    for sym in series:
        (curated / "trade" / f"dt={dia.isoformat()}" / f"sym={sym}").mkdir(parents=True,
                                                                          exist_ok=True)

    def _carregar(pasta: Path, sym: str) -> pd.DataFrame:
        return tabelas[sym]

    monkeypatch.setattr(dfg, "_carregar_dia", _carregar)
    return curated


def test_sem_ordem_de_chegada_as_duas_defasadas_ficam_perto_de_zero(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rng = np.random.default_rng(1)
    n = 300
    comum = rng.normal(0, 0.001, n)
    win = 140000 * np.exp(np.cumsum(comum + rng.normal(0, 0.0003, n)))
    petr = 40 * np.exp(np.cumsum(comum + rng.normal(0, 0.0003, n)))
    dia = dt.date(2026, 8, 3)
    c = _curated(monkeypatch, tmp_path, {"WINFUT": win, "PETR4": petr}, dia)
    r = dfg.descrever(c, [dia], ("PETR4",))["por_papel"]["PETR4"]
    assert r["contemporanea_p50"] > 0.8
    assert abs(r["papel_antecipa_p50"]) < 0.2 and abs(r["win_antecipa_p50"]) < 0.2
    assert abs(r["assimetria_p50"]) < 0.2


def test_papel_na_frente_aparece_na_assimetria(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """O WIN copia o papel com UMA barra de atraso: papel->WIN tem que ser
    muito maior que WIN->papel."""
    rng = np.random.default_rng(2)
    n = 300
    r_papel = rng.normal(0, 0.001, n)
    r_win = np.concatenate([[0.0], r_papel[:-1]]) + rng.normal(0, 0.0001, n)
    dia = dt.date(2026, 8, 4)
    c = _curated(monkeypatch, tmp_path,
                 {"WINFUT": 140000 * np.exp(np.cumsum(r_win)),
                  "PETR4": 40 * np.exp(np.cumsum(r_papel))}, dia)
    r = dfg.descrever(c, [dia], ("PETR4",))["por_papel"]["PETR4"]
    assert r["papel_antecipa_p50"] > 0.8
    assert r["win_antecipa_p50"] < 0.2
    assert r["assimetria_p50"] > 0.6


def test_varios_dias_reportam_fracao_de_dias_e_gravam(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rng = np.random.default_rng(3)
    dias = [dt.date(2026, 8, 3), dt.date(2026, 8, 4), dt.date(2026, 8, 5)]
    n = 200
    tabelas: dict[dt.date, dict[str, np.ndarray]] = {}
    for d in dias:
        rp = rng.normal(0, 0.001, n)
        rw = np.concatenate([[0.0], rp[:-1]]) + rng.normal(0, 0.0002, n)
        tabelas[d] = {"WINFUT": 140000 * np.exp(np.cumsum(rw)),
                      "PETR4": 40 * np.exp(np.cumsum(rp))}
    t0 = {d: int(pd.Timestamp(f"{d} 12:00:00", tz="UTC").value) for d in dias}
    curated = tmp_path / "curated"
    for d in dias:
        for sym in ("WINFUT", "PETR4"):
            (curated / "trade" / f"dt={d.isoformat()}" / f"sym={sym}").mkdir(parents=True)

    def _carregar(pasta: Path, sym: str) -> pd.DataFrame:
        d = dt.date.fromisoformat(pasta.name.split("=")[1])
        precos = tabelas[d][sym]
        return pd.DataFrame({"ts_ns": [t0[d] + i * 60 * NS + NS for i in range(len(precos))],
                             "price": precos, "quantidade": 1, "trade_type": 2})

    monkeypatch.setattr(dfg, "_carregar_dia", _carregar)
    r = dfg.descrever(curated, dias, ("PETR4",), saida=tmp_path / "s")
    e = r["por_papel"]["PETR4"]
    assert e["dias"] == 3 and e["fracao_dias_papel_na_frente"] == 1.0
    assert (tmp_path / "s" / "defasagem.json").exists()
    assert (tmp_path / "s" / "defasagem_por_dia.csv").exists()


def test_sem_dados_recusa(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="nenhum dia"):
        dfg.descrever(tmp_path, [dt.date(2026, 8, 3)], ("PETR4",))
