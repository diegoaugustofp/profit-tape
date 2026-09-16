"""O grafico substitui o tape? (exploracao declarada, categoria features)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from profittape.research import fluxo_vs_grafico as fg

NS = 1_000_000_000


def _tape(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, trades: pd.DataFrame,
          dia: dt.date) -> Path:
    curated = tmp_path / "curated"
    (curated / "trade" / f"dt={dia.isoformat()}" / "sym=WINFUT").mkdir(parents=True)
    monkeypatch.setattr(fg, "_carregar_dia", lambda pasta, sym: trades)
    return curated


def _gera(dia: dt.date, n_barras: int, seed: int, razao_agr: float,
          imbalance_da_geometria: bool) -> pd.DataFrame:
    """Um fluxo sintetico com razao vol_agr/vol_total CONTROLADA e imbalance
    ligado (ou nao) ao deslocamento da barra."""
    rng = np.random.default_rng(seed)
    t0 = int(pd.Timestamp(f"{dia} 12:00:00", tz="UTC").value)
    linhas = []
    preco = 140000.0
    for b in range(n_barras):
        alvo = preco + rng.choice([-1, 1]) * rng.integers(0, 40) * 5.0
        n = 200
        for i in range(n):
            ts = t0 + b * 900 * NS + int(i * 4 * NS)      # <= 5 s: barra confiavel
            px = preco + (alvo - preco) * (i / n)
            # trade_type: 2 (compra), 3 (venda), 13 (RLP, fora da agressao)
            if rng.random() > razao_agr:
                tipo = 13
            elif imbalance_da_geometria:
                tipo = 2 if alvo > preco else 3
            else:
                tipo = int(rng.choice([2, 3]))
            linhas.append({"ts_ns": ts, "price": round(px / 5) * 5.0,
                           "quantidade": int(rng.integers(1, 10)), "trade_type": tipo})
        preco = alvo
    return pd.DataFrame(linhas)


def test_razao_estavel_faz_o_proxy_de_absorcao_funcionar(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dia = dt.date(2026, 8, 3)
    curated = _tape(monkeypatch, tmp_path, _gera(dia, 120, 1, 0.8, True), dia)
    r = fg.medir(curated, "WINFUT", [dia])
    rz = r["razao_vol_agr_sobre_vol_total"]
    assert 0.7 < rz["p50"] < 0.9 and rz["cv"] < 0.2          # razao estavel por construcao
    nd = r["nao_direcional_absorcao"]
    assert nd["spearman_proxy_x_tape"] > 0.9
    assert nd["concordancia_decil"]["taxa"] > 0.5            # bem acima do acaso (0,1)


def test_imbalance_ligado_a_geometria_e_detectado(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dia = dt.date(2026, 8, 4)
    curated = _tape(monkeypatch, tmp_path, _gera(dia, 120, 2, 0.9, True), dia)
    di = fg.medir(curated, "WINFUT", [dia])["direcional_imbalance"]
    assert di["fracao_mesmo_sinal"] > 0.8 and di["r2_da_geometria"] > 0.4


def test_imbalance_aleatorio_nao_e_explicado_pela_geometria(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dia = dt.date(2026, 8, 5)
    curated = _tape(monkeypatch, tmp_path, _gera(dia, 120, 3, 0.9, False), dia)
    di = fg.medir(curated, "WINFUT", [dia])["direcional_imbalance"]
    assert abs(di["r2_da_geometria"]) < 0.2
    assert abs(di["spearman_desloc_x_imbalance"]) < 0.35


def test_barras_nao_confiaveis_ficam_fora(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dia = dt.date(2026, 8, 6)
    t = _gera(dia, 40, 4, 0.9, True)
    # abre um buraco de 5 min no meio: as barras afetadas saem
    t = t[(t["ts_ns"] < int(pd.Timestamp(f"{dia} 12:30:00", tz="UTC").value))
          | (t["ts_ns"] > int(pd.Timestamp(f"{dia} 12:36:00", tz="UTC").value))]
    curated = _tape(monkeypatch, tmp_path, t.reset_index(drop=True), dia)
    r = fg.medir(curated, "WINFUT", [dia])
    assert r["barras_usadas"] < r["barras"]


def test_sem_tape_recusa(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="nenhum dia com tape"):
        fg.medir(tmp_path, "WINFUT", [dt.date(2026, 8, 3)])
