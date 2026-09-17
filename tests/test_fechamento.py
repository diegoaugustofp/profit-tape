"""Ajuste/fechamento: a marca do fluxo obrigatorio existe? (zero trial)."""

from __future__ import annotations

from pathlib import Path

from profittape.research.fechamento import descrever
from tests.test_eas_preco import _dia, _dump


def _dias(tmp_path: Path, nome: str, vol_final: int, vol_normal: int,
          ampl_final: float = 10.0, n_dias: int = 20) -> Path:
    barras, cb = [], 1
    for k in range(n_dias):
        data = 1260401 + k
        dia = _dia(data, cb)
        for i, b in enumerate(dia):
            final = i >= len(dia) - 2
            b["vol_total"] = vol_final if final else vol_normal
            if final:
                b["high"], b["low"] = 140000.0 + ampl_final, 140000.0 - ampl_final
                b["close"] = 140000.0 + ampl_final
        cb += 37
        barras += dia
    return _dump(tmp_path, barras, nome)


def test_sem_marca_a_concentracao_fica_no_uniforme(tmp_path: Path) -> None:
    d = _dias(tmp_path, "plano.txt", vol_final=1000, vol_normal=1000, ampl_final=50.0)
    r = descrever(d)
    c = r["concentracao"]
    assert abs(c["ultimas_2_barras"] - c["ultimas_2_barras_uniforme"]) < 0.005
    assert abs(r["perfil_do_fim"]["0"]["ampl_rel_p50"] - 1.0) < 0.05


def test_marca_clara_aparece_na_concentracao_e_na_amplitude(tmp_path: Path) -> None:
    d = _dias(tmp_path, "marca.txt", vol_final=10000, vol_normal=1000, ampl_final=200.0)
    r = descrever(d, tmp_path / "s")
    assert (tmp_path / "s" / "fechamento.json").exists()
    c = r["concentracao"]
    assert c["ultimas_2_barras"] > 3 * c["ultimas_2_barras_uniforme"]
    assert r["perfil_do_fim"]["0"]["ampl_rel_p50"] > 3.0
    assert r["perfil_do_fim"]["0"]["frac_vol_p50"] > r["perfil_do_inicio"]["0"]["frac_vol_p50"]


def test_estabilidade_por_ano_e_contraste_com_o_inicio(tmp_path: Path) -> None:
    d = _dias(tmp_path, "ano.txt", vol_final=3000, vol_normal=1000)
    r = descrever(d)
    assert set(r["por_ano_2_ultimas"]) == {"2026"}
    assert r["por_ano_2_ultimas"]["2026"]["pregoes"] == 20
    assert len(r["perfil_do_inicio"]) == 4 and len(r["perfil_do_fim"]) == 8
    # a saida NAO traz retorno com sinal
    assert all("retorno_p50" not in e for e in r["perfil_do_fim"].values())
