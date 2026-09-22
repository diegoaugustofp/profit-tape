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


def test_preco_colado_nos_strikes_da_razao_alta(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Metade do volume em cima de um strike, metade em cima de outro: as
    duas pontas da grade sao negociadas (o placebo, no meio, recebe pouco),
    entao a comparacao e' justa E a razao e' alta."""
    dia = dt.date(2026, 9, 17)
    precos = ([47.86, 47.87] * 50) + ([48.86, 48.85] * 50)
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


def test_preco_espalhado_pela_grade_da_razao_perto_de_um(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Preco passeando por toda a grade, sem preferir strike: a razao tem
    que ficar perto de 1 -- e' o caso que o placebo existe para pegar."""
    dia = dt.date(2026, 9, 17)
    rng = np.random.default_rng(1)
    precos = list(rng.uniform(47.86, 48.86, 2000))
    c = _tape(monkeypatch, tmp_path, {dia: _dia(precos, dia)})
    r = ov.medir_dia(c, "PETR4", dia, STRIKES, dt.date(2026, 9, 18))
    assert 0.5 < r["razao_strike_vs_placebo"] < 2.0, r["razao_strike_vs_placebo"]


def test_placebo_fora_da_faixa_negociada_da_razao_INDEFINIDA(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """O DEFEITO que o ensaio de setembro achou: com o placebo fora do
    intervalo do dia ele recebe volume ZERO por construcao, e a razao
    explodia (310 milhoes). Agora sai INDEFINIDA, com o motivo."""
    dia = dt.date(2026, 9, 17)
    # negocios so' em torno de 47.86; os placebos (48.11 e 48.61) ficam fora
    precos = [47.86, 47.87, 47.85] * 50
    c = _tape(monkeypatch, tmp_path, {dia: _dia(precos, dia)})
    r = ov.medir_dia(c, "PETR4", dia, STRIKES, dt.date(2026, 9, 18))
    assert r["razao_strike_vs_placebo"] is None
    assert "nao e' justa" in r["razao_indefinida_porque"]


def test_faixa_nunca_engole_o_intervalo_entre_strikes(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A v1 usava +-0,4% (= +-0,19 em PETR4) com strikes a 0,25: a faixa
    cobria quase tudo. Agora a largura e' fracao do espacamento."""
    dia = dt.date(2026, 9, 17)
    c = _tape(monkeypatch, tmp_path, {dia: _dia(list(np.linspace(47.8, 48.9, 500)), dia)})
    r = ov.medir_dia(c, "PETR4", dia, STRIKES, dt.date(2026, 9, 18))
    assert r["tolerancia"] == pytest.approx(0.2 * 0.5, abs=1e-6)   # espacamento 0.5
    assert r["strikes"]["cobertura_da_faixa_do_dia"] < 0.5
    assert r["strikes_PLACEBO"]["cobertura_da_faixa_do_dia"] < 0.5


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
