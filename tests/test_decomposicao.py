"""
Testes da decomposicao diagnostica (fase de ENTENDIMENTO).

O modulo nao produz veredito de proposito. Os testes protegem justamente
isso: que ele explique sem parecer que decide.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from profittape.research.decomposicao import classificar_dias, decompor, resumir


def _barras(n_dias: int = 30, por_dia: int = 40, semente: int = 2) -> pd.DataFrame:
    rng = np.random.default_rng(semente)
    linhas = []
    for k in range(n_dias):
        dia = (pd.Timestamp("2026-01-05") + pd.Timedelta(days=k)).date()
        preco = 140_000.0
        # metade dos dias com deriva, metade sem
        deriva = 40.0 if k % 2 == 0 else 0.0
        for _ in range(por_dia):
            o = preco
            c = o + rng.normal(deriva, 150)
            linhas.append({"dia": dia, "open": o, "close": c,
                           "high": max(o, c) + 60, "low": min(o, c) - 60,
                           "vol_agr": float(rng.gamma(20, 50))})
            preco = c
    return pd.DataFrame(linhas)


def test_classifica_dia_por_forma_e_por_tamanho() -> None:
    d = classificar_dias(_barras())
    assert set(d["tipo"].cat.categories) == {"oscilou", "misto", "andou"}
    assert set(d["tamanho"].cat.categories) == {"parado", "medio", "amplo"}
    # direcionalidade e' razao, entao vive em [0, 1]
    assert d["direcionalidade"].between(0, 1).all()


def test_dia_que_anda_tem_direcionalidade_MAIOR() -> None:
    """
    |close - open| / range. Perto de 1 o dia andou e ficou; perto de 0
    andou e voltou.
    """
    b = pd.DataFrame({
        "dia": ["A"] * 3 + ["B"] * 3,
        # A: sobe direto.  B: sobe e volta.
        "open": [100.0, 110.0, 120.0, 100.0, 110.0, 120.0],
        "close": [110.0, 120.0, 130.0, 110.0, 120.0, 100.0],
        "high": [111.0, 121.0, 131.0, 111.0, 121.0, 121.0],
        "low": [99.0, 109.0, 119.0, 99.0, 109.0, 99.0],
        "vol_agr": [100.0] * 6,
    })
    d = classificar_dias(b)
    assert d.loc["A", "direcionalidade"] > d.loc["B", "direcionalidade"]


def test_decompor_separa_por_celula_e_NAO_da_veredito() -> None:
    """
    Sem coluna de veredito, de proposito: a fase de entendimento explica,
    nao decide. Qualquer numero daqui e' HIPOTESE.
    """
    b = _barras()
    dias = classificar_dias(b)
    r = pd.DataFrame({
        "dia": list(dias.index) * 2,
        "lado": [-1] * len(dias) + [1] * len(dias),
        "retorno": np.linspace(-100, 100, len(dias) * 2),
    })
    t = decompor(r, dias, "tipo")
    assert {"tipo", "lado", "n", "media", "t"} <= set(t.columns)
    assert "sig" not in t.columns and "veredito" not in t.columns


def test_resumo_ADMITE_a_multiplicidade() -> None:
    """
    Decompor em muitas celulas GARANTE que alguma pareca significativa.
    Com 12 celulas sob H0, a chance de ao menos uma passar de |t| 1,96 e'
    46%. Sem admitir isso, olhar doze e destacar a mais forte parece
    achado -- e e' aritmetica.
    """
    tab = pd.DataFrame({"n": [50] * 12, "t": [0.5] * 11 + [2.4]})
    s = resumir({"x": tab})
    assert s["celulas"] == 12
    assert s["celulas_extremas"] == 1
    assert s["esperadas_por_acaso"] == 0.6
    assert "46%" in s["chance_de_ao_menos_uma"]


def test_resumo_reconhece_quando_nada_distingue_de_ruido() -> None:
    tab = pd.DataFrame({"n": [50] * 12, "t": [0.5] * 12})
    s = resumir({"x": tab})
    assert "nada aqui distingue de ruido" in s["leitura"]
