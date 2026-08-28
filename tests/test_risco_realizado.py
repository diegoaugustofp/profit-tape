"""
Testes de research/risco_realizado.py -- valores conferidos a mao antes
de confiar no calculo (mesmo padrao de mae.py e curva_patrimonio.py).
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from profittape.research.risco_realizado import (
    nivel_implicado_por_limiar,
    var_es_por_faixa_horario,
    var_es_realizado,
)


def test_var_es_conferido_a_mao() -> None:
    """
    m=[1..10]. VaR90 (quantil 0.9, interpolacao linear padrao do pandas):
    posicao=0.9*9=8.1 -> interpola indice8(9) e indice9(10) = 9.1.
    ES90 = media dos valores >= 9.1 -> so' o 10 qualifica -> ES90=10.
    """
    m = pd.Series(range(1, 11), dtype=float)
    r = var_es_realizado(m, niveis_confianca=(0.9,))
    assert r["var_pontos"].iloc[0] == pytest.approx(9.1)
    assert r["es_pontos"].iloc[0] == 10.0
    assert r["n_na_cauda"].iloc[0] == 1


def test_multiplos_niveis_de_confianca_ordenados_corretamente() -> None:
    m = pd.Series(range(1, 101), dtype=float)   # 1..100
    r = var_es_realizado(m, niveis_confianca=(0.90, 0.99))
    # quantil mais alto tem que dar VaR maior (ou igual) e ES maior (ou igual)
    assert r["var_pontos"].iloc[1] >= r["var_pontos"].iloc[0]
    assert r["es_pontos"].iloc[1] >= r["es_pontos"].iloc[0]
    # ES sempre >= VaR no mesmo nivel (media da cauda >= o proprio limite)
    for _, row in r.iterrows():
        assert row["es_pontos"] >= row["var_pontos"]


def test_nivel_implicado_por_limiar_conferido_a_mao() -> None:
    """m=[1..10], limiar=9: abaixo estrito = [1..8] = 8/10 = 0.8.
    Excedem (>=9): [9,10] -> es_no_limiar = mean([9,10]) = 9.5."""
    m = pd.Series(range(1, 11), dtype=float)
    r = nivel_implicado_por_limiar(m, limiar=9.0)
    assert r["nivel_confianca_implicado"] == pytest.approx(0.8)
    assert r["pct_barras_que_excedem"] == pytest.approx(0.2)
    assert r["n_barras_que_excedem"] == 2
    assert r["es_no_limiar_pontos"] == pytest.approx(9.5)


def test_limiar_maior_que_tudo_nao_tem_cauda() -> None:
    m = pd.Series([1.0, 2.0, 3.0])
    r = nivel_implicado_por_limiar(m, limiar=1000.0)
    assert r["nivel_confianca_implicado"] == 1.0
    assert r["n_barras_que_excedem"] == 0
    assert pd.isna(r["es_no_limiar_pontos"])


def test_serie_vazia_recusa() -> None:
    with pytest.raises(ValueError, match="vazio"):
        nivel_implicado_por_limiar(pd.Series([], dtype=float), limiar=100.0)


def test_por_faixa_horario_segmenta_corretamente() -> None:
    """
    Barras de 09h (mais volateis, movimento grande) vs barras de 14h
    (mais calmas, movimento pequeno) tem que dar VaR bem diferentes --
    prova que a segmentacao por horario nao mistura os dois regimes.
    """
    n_por_faixa = 50
    base_abertura = int(datetime(2026, 8, 27, 9, 15, tzinfo=UTC).timestamp() * 1e9)
    base_meio = int(datetime(2026, 8, 27, 14, 15, tzinfo=UTC).timestamp() * 1e9)
    passo_ns = 60 * 10**9   # 1 minuto
    ts_abertura = base_abertura + np.arange(n_por_faixa) * passo_ns
    ts_meio = base_meio + np.arange(n_por_faixa) * passo_ns

    rng = np.random.default_rng(1)
    # abertura: movimento GRANDE; meio: movimento PEQUENO -- diferenca proposital
    close_abertura = 100.0 + np.cumsum(rng.choice([-50.0, 50.0], n_por_faixa))
    close_meio = 100.0 + np.cumsum(rng.choice([-1.0, 1.0], n_por_faixa))

    df = pd.DataFrame({
        "ts_ns": np.concatenate([ts_abertura, ts_meio]),
        "close": np.concatenate([close_abertura, close_meio]),
    })

    r = var_es_por_faixa_horario(df, "ts_ns", "close",
                                 faixas=(("abertura", 9, 10), ("meio", 14, 15)),
                                 niveis_confianca=(0.9,), tz_offset_horas=0)
    var_abertura = r[r["faixa"] == "abertura"]["var_pontos"].iloc[0]
    var_meio = r[r["faixa"] == "meio"]["var_pontos"].iloc[0]
    assert var_abertura > var_meio * 5   # abertura claramente mais volatil


def test_faixa_sem_nenhuma_barra_e_ignorada_sem_falhar() -> None:
    base = int(datetime(2026, 8, 27, 14, 0, tzinfo=UTC).timestamp() * 1e9)
    df = pd.DataFrame({
        "ts_ns": base + np.arange(10) * 60 * 10**9,
        "close": np.arange(10, dtype=float),
    })
    r = var_es_por_faixa_horario(df, "ts_ns", "close",
                                 faixas=(("abertura", 9, 10), ("meio", 14, 15)),
                                 tz_offset_horas=0)
    assert set(r["faixa"]) == {"meio"}   # abertura nao tinha barra, sumiu sem erro
