"""Rolagem pelo PAR CASADO entre os dois contratos (zero trial)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from profittape.research import rolagem_par as rp

NS = 1_000_000_000


def _tape(monkeypatch: pytest.MonkeyPatch, tabelas: dict[str, pd.DataFrame],
          tmp_path: Path, dia: dt.date) -> Path:
    curated = tmp_path / "curated"
    for sym in tabelas:
        (curated / "trade" / f"dt={dia.isoformat()}" / f"sym={sym}").mkdir(parents=True,
                                                                          exist_ok=True)
    monkeypatch.setattr(rp, "_carregar_dia", lambda pasta, sym: tabelas[sym])
    return curated


def _ruido(n: int, seed: int, t0: int, preco: float) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "ts_ns": np.sort(rng.integers(t0, t0 + 6 * 3600 * NS, n)),
        "price": preco + rng.integers(-20, 20, n) * 0.5,
        "quantidade": rng.integers(1, 6, n),
        "agente_comprador": rng.integers(1, 40, n),
        "agente_vendedor": rng.integers(1, 40, n),
        "trade_type": 2})


def test_sem_rolagem_a_razao_fica_perto_de_um(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dia = dt.date(2026, 9, 28)
    t0 = int(pd.Timestamp(f"{dia} 12:00", tz="UTC").value)
    c = _tape(monkeypatch, {"WDOV26": _ruido(4000, 1, t0, 5125.0),
                            "WDOX26": _ruido(4000, 2, t0, 5153.0)}, tmp_path, dia)
    r = rp.medir_dia(c, "WDOV26", "WDOX26", dia)
    for nome in ("vende_A_compra_B", "compra_A_vende_B"):
        assert 0.5 < r[nome]["razao"] < 2.0, (nome, r[nome])


def test_rolagem_plantada_aparece_contra_o_baseline(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """O agente 7 rola 300 vezes: vende no que vence e compra no proximo,
    1 s depois."""
    dia = dt.date(2026, 9, 29)
    t0 = int(pd.Timestamp(f"{dia} 12:00", tz="UTC").value)
    a, b = _ruido(4000, 3, t0, 5125.0), _ruido(4000, 4, t0, 5153.0)
    extras_a, extras_b = [], []
    for k in range(300):
        ts = t0 + (600 + k * 3) * NS
        extras_a.append({"ts_ns": ts, "price": 5125.0, "quantidade": 5,
                         "agente_comprador": 11, "agente_vendedor": 7, "trade_type": 3})
        extras_b.append({"ts_ns": ts + NS, "price": 5153.0, "quantidade": 5,
                         "agente_comprador": 7, "agente_vendedor": 12, "trade_type": 2})
    a = pd.concat([a, pd.DataFrame(extras_a)], ignore_index=True).sort_values("ts_ns")
    b = pd.concat([b, pd.DataFrame(extras_b)], ignore_index=True).sort_values("ts_ns")
    c = _tape(monkeypatch, {"WDOV26": a, "WDOX26": b}, tmp_path, dia)
    r = rp.medir_dia(c, "WDOV26", "WDOX26", dia)
    assert r["vende_A_compra_B"]["pares"] >= 300
    assert r["vende_A_compra_B"]["razao"] > 1.5, r["vende_A_compra_B"]
    # o sentido contrario NAO foi plantado
    assert r["compra_A_vende_B"]["razao"] < 1.5


def test_janela_separa_o_par_do_acaso() -> None:
    ts_a = np.array([0, 10 * NS], dtype=np.int64)
    ag_a = np.array([7, 7], dtype=np.int64)
    ts_b = np.array([NS], dtype=np.int64)          # 1 s depois do primeiro
    ag_b = np.array([7], dtype=np.int64)
    assert rp._casar(ts_a, ag_a, ts_b, ag_b, 2 * NS).tolist() == [True, False]


def test_agente_diferente_nao_casa() -> None:
    ts_a, ts_b = np.array([0], dtype=np.int64), np.array([NS], dtype=np.int64)
    assert not rp._casar(ts_a, np.array([7]), ts_b, np.array([9]), 2 * NS)[0]


def test_agregado_e_saida(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dia = dt.date(2026, 9, 30)
    t0 = int(pd.Timestamp(f"{dia} 12:00", tz="UTC").value)
    c = _tape(monkeypatch, {"WDOV26": _ruido(500, 5, t0, 5125.0),
                            "WDOX26": _ruido(500, 6, t0, 5153.0)}, tmp_path, dia)
    r = rp.descrever(c, "WDOV26", "WDOX26", [dia], saida=tmp_path / "s")
    assert (tmp_path / "s" / "rolagem_par.json").exists() and r["dias"] == 1


def test_sem_os_dois_contratos_recusa(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="nenhum dia"):
        rp.descrever(tmp_path, "WDOV26", "WDOX26", [dt.date(2026, 9, 28)])
