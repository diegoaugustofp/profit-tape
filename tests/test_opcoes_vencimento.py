"""Opcao sobre acao, passo 1: concentracao nos strikes contra o PLACEBO."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from profittape.research import opcoes_vencimento as ov

NS = 1_000_000_000
STRIKES = [47.86, 48.36, 48.86]


def _tape(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, por_dia: dict[dt.date, pd.DataFrame],
          papel: str = "PETR4") -> Path:
    curated = tmp_path / "curated"
    for d in por_dia:
        (curated / "trade" / f"dt={d.isoformat()}" / f"sym={papel}").mkdir(parents=True,
                                                                          exist_ok=True)

    def _carregar(pasta: Path, sym: str) -> pd.DataFrame:
        d = dt.date.fromisoformat(pasta.name.split("=")[1])
        return por_dia[d] if sym == papel else pd.DataFrame()

    monkeypatch.setattr(ov, "_carregar_dia", _carregar)
    return curated


def _dia(precos: list[float], dia: dt.date) -> pd.DataFrame:
    t0 = int(pd.Timestamp(f"{dia} 13:00", tz="UTC").value)
    return pd.DataFrame({"ts_ns": [t0 + i * NS for i in range(len(precos))],
                         "price": precos, "quantidade": 100, "trade_type": 2})


def test_preco_colado_no_strike_da_razao_alta(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dia = dt.date(2026, 9, 17)
    precos = [48.36, 48.37, 48.35, 48.36, 48.34] * 20      # em cima de um strike
    c = _tape(monkeypatch, tmp_path, {dia: _dia(precos, dia)})
    r = ov.medir_dia(c, "PETR4", dia, STRIKES, dt.date(2026, 9, 18))
    assert r["strikes"]["fracao_do_volume_perto"] == 1.0
    assert r["strikes_PLACEBO"]["fracao_do_volume_perto"] == 0.0
    assert r["razao_strike_vs_placebo"] > 100


def test_preco_longe_dos_strikes_nao_acusa(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dia = dt.date(2026, 9, 17)
    precos = [50.0 + 0.01 * i for i in range(50)]          # longe de tudo
    c = _tape(monkeypatch, tmp_path, {dia: _dia(precos, dia)})
    r = ov.medir_dia(c, "PETR4", dia, STRIKES, dt.date(2026, 9, 18))
    assert r["strikes"]["fracao_do_volume_perto"] == 0.0


def test_placebo_pega_o_caso_em_que_o_preco_so_andou_ali(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """O preco passou o dia num nivel que por acaso esta' perto de um strike
    FALSO tambem: a razao tem que ficar perto de 1, nao acusar atracao."""
    dia = dt.date(2026, 9, 17)
    rng = np.random.default_rng(1)
    # meio do caminho entre um strike (48.36) e o seu placebo (48.36*1.017)
    centro = (48.36 + 48.36 * 1.017) / 2
    precos = list(centro + rng.normal(0, 0.25, 300))
    c = _tape(monkeypatch, tmp_path, {dia: _dia(precos, dia)})
    r = ov.medir_dia(c, "PETR4", dia, STRIKES, dt.date(2026, 9, 18))
    assert 0.3 < r["razao_strike_vs_placebo"] < 3.0, r["razao_strike_vs_placebo"]


def test_pregoes_ate_o_vencimento_e_a_separacao_da_semana(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    venc = dt.date(2026, 10, 16)
    dias = [dt.date(2026, 10, 5), dt.date(2026, 10, 14), dt.date(2026, 10, 15)]
    c = _tape(monkeypatch, tmp_path, {d: _dia([48.36] * 10, d) for d in dias})
    r = ov.descrever(c, "PETR4", dias, STRIKES, venc)
    assert r["por_dia"][0]["pregoes_ate_o_vencimento"] == 9     # 05/10 -> 16/10
    assert r["semana_do_vencimento"]["pregoes"] == 2            # 14 e 15/10
    assert r["demais_pregoes"]["pregoes"] == 1


def test_atividade_das_series_entra_no_relatorio(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dia = dt.date(2026, 9, 17)
    papel = _dia([48.36] * 10, dia)
    serie = _dia([2.10] * 4, dia)
    curated = tmp_path / "curated"
    for sym in ("PETR4", "PETRV494"):
        (curated / "trade" / f"dt={dia.isoformat()}" / f"sym={sym}").mkdir(parents=True,
                                                                          exist_ok=True)
    monkeypatch.setattr(ov, "_carregar_dia",
                        lambda pasta, sym: papel if sym == "PETR4" else serie)
    r = ov.medir_dia(curated, "PETR4", dia, STRIKES, dt.date(2026, 9, 18),
                     series=["PETRV494"])
    assert r["negocios_nas_series"] == 4 and r["series"]["PETRV494"]["volume"] == 400


def test_sem_tape_recusa(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="nenhum dia"):
        ov.descrever(tmp_path, "PETR4", [dt.date(2026, 9, 17)], STRIKES,
                     dt.date(2026, 9, 18))
