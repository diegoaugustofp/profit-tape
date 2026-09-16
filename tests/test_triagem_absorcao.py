"""Triagem (7.2) da absorcao de grafico: ela e' volume ou e' range?"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from profittape.research.triagem_absorcao import triar
from tests.test_eas_preco import _barra, _dump


def _dump_sintetico(tmp_path: Path, nome: str, var_range: float, var_vol: float,
                    seed: int = 1, n_dias: int = 30) -> Path:
    """Barras com variancia CONTROLADA em range e volume: a triagem tem que
    apontar de onde vem a absorcao."""
    rng = np.random.default_rng(seed)
    barras, cb = [], 1
    for k in range(n_dias):
        data = 1260101 + k
        h, m = 9, 0
        for _ in range(37):
            rng_ticks = float(np.exp(rng.normal(2.5, var_range)))     # range em ticks
            vol = float(np.exp(rng.normal(9.0, var_vol)))
            base = 140000.0
            barras.append(_barra(data, h * 100 + m, cb, base, base + rng_ticks * 5,
                                 base, base + rng_ticks * 2.5))
            barras[-1]["vol_total"] = round(vol)
            cb += 1
            m += 15
            if m == 60:
                h, m = h + 1, 0
    return _dump(tmp_path, barras, nome)


def test_absorcao_dominada_pelo_range_e_acusada(tmp_path: Path) -> None:
    d = _dump_sintetico(tmp_path, "r.txt", var_range=0.9, var_vol=0.05)
    r = triar(d)
    b = r["bruto"]
    assert b["fracao_da_var_vinda_do_range"] > 0.9
    assert b["decil_tambem_em_barra_estreita"]["taxa"] > 0.8
    assert b["decil_tambem_em_volume_alto"]["taxa"] < 0.3
    assert b["corr_log_absorcao_com_menos_log_range"] > 0.95


def test_absorcao_dominada_pelo_volume_e_acusada(tmp_path: Path) -> None:
    d = _dump_sintetico(tmp_path, "v.txt", var_range=0.05, var_vol=0.9, seed=2)
    b = triar(d)["bruto"]
    assert b["fracao_da_var_vinda_do_range"] < 0.1
    assert b["decil_tambem_em_volume_alto"]["taxa"] > 0.8
    assert b["decil_tambem_em_barra_estreita"]["taxa"] < 0.3


def test_normalizacao_por_horario_roda_e_grava(tmp_path: Path) -> None:
    d = _dump_sintetico(tmp_path, "h.txt", var_range=0.5, var_vol=0.5, seed=3)
    r = triar(d, tmp_path / "s")
    assert (tmp_path / "s" / "triagem_absorcao.json").exists()
    h = r["normalizado_por_horario"]
    assert h["n"] > 0 and -1.0 <= h["corr_z_absorcao_com_z_volume"] <= 1.0
