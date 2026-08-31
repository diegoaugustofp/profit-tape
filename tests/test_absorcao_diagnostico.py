"""
Testes do diagnostico de absorcao (categoria `features`, zero trial).

O caso que motivou o modulo: uma barra real pintada AQUA em que os
COMPRADORES levaram o preco embora — o oposto da leitura que a cor
sugeria.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from profittape.research.absorcao_diagnostico import (
    calcular_esforco,
    classificar,
    esforco_de_uma_barra,
    resumir,
)


def test_a_barra_real_de_31_08_e_caso_B() -> None:
    """
    Barra de 2026-08-31, 09:03-09:05, reconstruida do tape:

        imbalance    +0,0486   (agressao praticamente empatada)
        desloc_norm  +0,9509   (quase marubozu de alta, +326 ticks)
        absorcao_dir -0,9023   -> familia aqua

    Nao houve vendedor agredindo: o preco subiu porque o livro estava
    fino. Tem que sair como B, nao como A.
    """
    r = classificar(pd.Series([-2.0]), pd.Series([0.05]),
                    limiar=1.75, limiar_imb=1.0)
    assert r.iloc[0] == "B_alta_sem_esforco"


def test_as_quatro_leituras_e_a_fronteira() -> None:
    za = pd.Series([-2.0, -2.0, 2.0, 2.0, 0.0, -2.0, 2.0])
    zi = pd.Series([-1.5, 0.05, 1.5, 0.05, 3.0, -1.0, 1.0])
    r = classificar(za, zi, limiar=1.75, limiar_imb=1.0)
    assert list(r) == [
        "A_venda_absorvida", "B_alta_sem_esforco",
        "A_compra_absorvida", "B_queda_sem_esforco",
        "nao_pintou",
        "A_venda_absorvida",   # fronteira: |z_imb| == limiar entra em A
        "A_compra_absorvida",
    ]


def test_esforco_e_ilimitado_ao_contrario_dos_outros_termos() -> None:
    """
    E' a propriedade que falta a `imbalance` e `desloc_norm`, ambos
    presos em [-1,+1]. Uma barra pode ter cinco vezes o volume normal na
    mesma amplitude.
    """
    normal = esforco_de_uma_barra(vol_agr=100_000, high=100_500, low=100_000)
    concentrada = esforco_de_uma_barra(vol_agr=500_000, high=100_500,
                                       low=100_000)
    assert concentrada == pytest.approx(5 * normal)
    assert concentrada > 1.0  # sem teto


def test_amplitude_zero_vira_nan_e_nao_infinito() -> None:
    """
    Barra com todos os negocios no mesmo preco e' o esforco MAXIMO
    concebivel, nao um erro. Mas `inf` contamina qualquer media, entao
    fica NaN e sai das estatisticas — com a contagem reportada a parte.
    """
    b = pd.DataFrame({"high": [100.0, 100.0], "low": [100.0, 95.0],
                      "vol_agr": [5000.0, 5000.0]})
    e = calcular_esforco(b, tick=5.0)
    assert np.isnan(e.iloc[0])
    assert e.iloc[1] == pytest.approx(5000.0)


def test_resumo_separa_as_leituras() -> None:
    rng = np.random.default_rng(3)
    n = 400
    b = pd.DataFrame({
        "z_absorcao_dir": rng.normal(size=n),
        "z_imbalance": rng.normal(size=n),
        "imbalance": rng.normal(0, 0.1, n),
        "desloc_norm": rng.normal(0, 0.4, n),
        "high": 100_500.0, "low": 100_000.0,
        "vol_agr": rng.integers(50_000, 200_000, n).astype(float),
    })
    r = resumir(b, tick=5.0, limiar=1.0, limiar_imb=1.0)
    assert r["barras"] == n
    assert r["amplitude_zero"] == 0
    rotulos = {x["leitura"] for x in r["por_leitura"]}
    assert "nao_pintou" in rotulos
    assert sum(x["n"] for x in r["por_leitura"]) == n
    # quantis ordenados
    q = r["esforco_geral"]
    assert q["p5"] <= q["p50"] <= q["p95"]
