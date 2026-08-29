"""
Testes de research/remanescente.py (PRE-REGISTRO 2, 2026-08-29b).

Os numeros foram conferidos A MAO antes destes testes existirem. O teste
mais importante do arquivo e' `test_portao_reprova_este_desenho`: ele
CONGELA como regressao o achado de que o limite pessimista tem vies
estrutural de ~+30 pts sobre ruido puro. Se um dia ele passar a falhar,
alguem mexeu no estimador — e a pergunta certa e' "onde esta o
pre-registro novo?", nao "como faco o teste passar?".
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from profittape.research.remanescente import (
    GRADE_X_CONGELADA,
    _decidir,
    _razao_amplitude,
    _remanescentes,
    _uma_amostra_contra_zero,
    gerar_ruido_calibrado,
    portao_de_honestidade,
)
from profittape.research.trials import limiar_deflacionado


def _df() -> pd.DataFrame:
    d = date(2026, 8, 3)
    return pd.DataFrame({
        "dia": [d] * 5,
        "z": [2.0, 0.0, 0.0, 0.0, 0.0],
        "close": [100.0, 90.0, 80.0, 70.0, 60.0],
        "high": [101.0, 140.0, 115.0, 75.0, 65.0],
        "low": [99.0, 85.0, 78.0, 68.0, 58.0],
    })


# ------------------------------------------------------------ estimador
def test_remanescente_confere_com_calculo_a_mao() -> None:
    """A MAO (h=3, venda, X=30): entrada=100, nivel=130. Highs da janela
    140/115/75 -> cruza na barra 1. F_pess = 140, F_otim = 130,
    close_fim = 70. rem = (70 - F) * (-1): pess=+70, otim=+60."""
    r = _remanescentes(_df(), "z", 3, 1.4, "contrarian", "venda", 30.0)
    assert len(r) == 1
    assert r.iloc[0]["barra_cruzamento"] == 1
    assert r.iloc[0]["rem_pessimista"] == pytest.approx(70.0)
    assert r.iloc[0]["rem_otimista"] == pytest.approx(60.0)


def test_pessimista_nunca_e_menor_que_otimista() -> None:
    """Assimetria registrada ANTES: o pessimista mede a partir de um
    preco pior, entao o remanescente sai MAIOR. Se esta ordem inverter,
    algum sinal foi trocado."""
    for x in (20.0, 30.0, 40.0):
        r = _remanescentes(_df(), "z", 3, 1.4, "contrarian", "venda", x)
        if r.empty:
            continue
        assert (r["rem_pessimista"] >= r["rem_otimista"]).all()


def test_operacao_que_nunca_toca_e_excluida() -> None:
    assert _remanescentes(_df(), "z", 3, 1.4, "contrarian", "venda", 200.0).empty


def test_compra_usa_low_nao_high() -> None:
    """A MAO: comprado em 100, X=20 -> nivel=80. Lows 85/78/68 -> cruza
    na barra 2 (78 <= 80). F_pess=78, F_otim=80, close_fim=70.
    rem = (70 - F) * (+1): pess=-8, otim=-10."""
    df = _df()
    df["z"] = [-2.0, 0.0, 0.0, 0.0, 0.0]
    r = _remanescentes(df, "z", 3, 1.4, "contrarian", "compra", 20.0)
    assert r.iloc[0]["barra_cruzamento"] == 2
    assert r.iloc[0]["rem_pessimista"] == pytest.approx(-8.0)
    assert r.iloc[0]["rem_otimista"] == pytest.approx(-10.0)


def test_purge_estrutural_descarta_janela_incompleta() -> None:
    df = _df()
    df["z"] = [0.0, 0.0, 0.0, 2.0, 0.0]
    assert _remanescentes(df, "z", 3, 1.4, "contrarian", "venda", 30.0).empty


def test_uma_amostra_contra_zero_a_mao() -> None:
    """A MAO: media=10; desvios -5,0,+5,0 -> soma dos quadrados 50;
    var(ddof=1) = 50/3 = 16.6667; sd = 4.082483; erro padrao =
    4.082483/2 = 2.041241; t = 10/2.041241 = 4.898979.
    (Errei esta conta na primeira escrita — pus sd=5 e esperei t=4. O
    codigo estava certo; o teste e' que estava.)"""
    v = np.array([5.0, 10.0, 15.0, 10.0])
    est = _uma_amostra_contra_zero(v)
    assert est["media"] == pytest.approx(10.0)
    assert est["t"] == pytest.approx(4.898979, abs=1e-6)


# -------------------------------------------------------------- decisao
def _p(x: float, pess: float, otim: float, sp: bool, so: bool,
       n: int = 50) -> dict[str, object]:
    return {"x": x, "n": n, "n_suficiente": n >= 30,
            "media_pess": pess, "media_otim": otim,
            "sig_pess": sp, "sig_otim": so}


def test_contra_quando_nada_significativo() -> None:
    pontos = [_p(x, 1.0, -1.0, False, False) for x in GRADE_X_CONGELADA]
    assert _decidir(pontos)[0] == "CONTRA (b)"


def test_favoravel_exige_os_dois_limites_negativos() -> None:
    pontos = [_p(40, 5.0, 2.0, False, False), _p(60, 3.0, 1.0, False, False),
              _p(80, -10.0, -20.0, True, True)] + \
             [_p(x, -15.0, -25.0, False, False) for x in (100, 120, 150, 200)]
    veredito, _, x_estrela = _decidir(pontos)
    assert veredito == "FAVORAVEL a (b)"
    assert x_estrela == 80.0


def test_nao_e_favoravel_se_so_um_limite_e_significativo() -> None:
    """Um limite so' nao basta: o pessimista sozinho tem vies conhecido."""
    pontos = [_p(x, -10.0, -20.0, True, False) for x in GRADE_X_CONGELADA]
    assert _decidir(pontos)[0] != "FAVORAVEL a (b)"


def test_invertido_reconhecido() -> None:
    pontos = [_p(x, 1.0, -1.0, False, False) for x in GRADE_X_CONGELADA[:-1]]
    pontos.append(_p(200, 30.0, 20.0, True, True))
    veredito, justificativa, _ = _decidir(pontos)
    assert veredito == "INVERTIDO"
    assert "piramide" in justificativa


def test_inconclusivo_por_preenchimento_quando_limites_discordam() -> None:
    """Os dois significativos com SINAIS opostos -> a resposta depende de
    onde na barra o cruzamento ocorreu. So' entao vale o tape."""
    pontos = [_p(x, 1.0, -1.0, False, False) for x in GRADE_X_CONGELADA[:-1]]
    pontos.append(_p(200, +30.0, -20.0, True, True))
    veredito, justificativa, _ = _decidir(pontos)
    assert veredito == "INCONCLUSIVO POR PREENCHIMENTO"
    assert "tape" in justificativa


# --------------------------------------------------------------- portao
def test_razao_amplitude_ignora_virada_de_pregao() -> None:
    """A variacao entre o ultimo close de um dia e o primeiro do seguinte
    nao e' movimento observado. Incluir infla o denominador."""
    df = pd.DataFrame({
        "dia": [date(2026, 8, 3)] * 3 + [date(2026, 8, 4)] * 3,
        "close": [100.0, 102.0, 104.0, 900.0, 902.0, 904.0],
        "high": [101.0, 103.0, 105.0, 901.0, 903.0, 905.0],
        "low": [99.0, 101.0, 103.0, 899.0, 901.0, 903.0],
    })
    # dentro do dia: variacoes todas = 2.0 -> sd = 0. Com o salto de 796
    # entre os dias, sd explodiria e a razao despencaria.
    assert math.isnan(_razao_amplitude(df))


def test_ruido_calibrado_tem_caminho_coerente() -> None:
    """high/low precisam ser extremos REAIS do caminho que contem o
    close. A primeira versao sorteava amplitude por fora — barras cujo
    high nunca foi visitado por caminho nenhum."""
    base = pd.DataFrame({"dia": [date(2026, 1, 1)] * 500,
                         "close": np.cumsum(np.random.default_rng(3).normal(0, 70, 500)) + 130000})
    base["high"] = base["close"] + 30
    base["low"] = base["close"] - 30
    r = gerar_ruido_calibrado(base, n_dias=3, barras_por_dia=50, semente=1)
    assert (r["high"] >= r["close"]).all()
    assert (r["low"] <= r["close"]).all()
    assert (r["high"] > r["low"]).all()


def test_portao_reprova_este_desenho() -> None:
    """
    REGRESSAO DO ACHADO de 2026-08-29: sobre RANDOM WALK PURO, o limite
    PESSIMISTA devolve remanescente fortemente POSITIVO (~+30 pts, t>8),
    porque mede a partir do EXTREMO da barra de cruzamento — selecionar
    num extremo garante que o resto do caminho pareca favoravel. E' a
    imagem espelhada da tautologia que anulou `reversao.py`.

    Consequencia: o veredito sobre ruido nao e' CONTRA (b), logo o portao
    REPROVA, logo nenhum resultado real deste desenho se interpreta.

    Se este teste falhar, o estimador mudou e precisa de pre-registro
    novo — nao de um teste ajustado.
    """
    rng = np.random.default_rng(1)
    n, sub = 2000, 40
    ticks = 130000 + np.cumsum(rng.normal(0, 11.0, n * sub))
    t = ticks.reshape(n, sub)
    df_real = pd.DataFrame({"dia": [date(2026, 1, 1)] * n, "close": t[:, -1],
                            "high": t.max(axis=1), "low": t.min(axis=1)})
    p = portao_de_honestidade(
        df_real, 3, 1.4, "contrarian", "venda", GRADE_X_CONGELADA,
        limiar_deflacionado(len(GRADE_X_CONGELADA)), 150, 20260829,
        n_dias=60, barras_por_dia=150)

    com_n = [q for q in p["pontos"] if q["n"] >= 30]
    assert com_n, "portao sem amostra: o achado nao foi testado"
    assert all(q["media_pess"] > 15.0 for q in com_n), \
        "vies do limite pessimista sumiu — estimador mudou?"
    assert all(q["sig_pess"] for q in com_n)
    assert p["veredito"] != "CONTRA (b)"
    assert p["passou"] is False
