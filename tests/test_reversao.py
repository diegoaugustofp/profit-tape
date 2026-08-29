"""
Testes de research/reversao.py -- executa o PRE-REGISTRO congelado em
2026-08-29. Os numeros abaixo foram conferidos A MAO antes destes testes
existirem (regra 4 da disciplina), incluindo a assimetria HIGH/LOW por lado,
que e' exatamente a classe de bug de sinal invertido que ja' apareceu no
projeto em formula de MFE.
"""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from profittape.research.reversao import (
    GRADE_X_CONGELADA,
    N_MINIMO_POR_PONTO,
    _decidir,
    _extrair_operacoes,
    _welch,
    analisar_reversao_condicional,
)


# --------------------------------------------------------------- Welch
def test_welch_confere_com_calculo_a_mao() -> None:
    """A MAO: media_a=-20, media_b=+20, var_a=100, var_b=200/3,
    ep=sqrt(100/3 + (200/3)/4)=sqrt(50)=7.0710678, dif=-40,
    t=-5.656854, gl=3.8571."""
    a = np.array([-30.0, -10.0, -20.0])
    b = np.array([10.0, 20.0, 30.0, 20.0])
    w = _welch(a, b)
    assert w["diferenca"] == pytest.approx(-40.0)
    assert w["t_welch"] == pytest.approx(-5.656854, abs=1e-6)
    assert w["gl_welch"] == pytest.approx(3.8571, abs=1e-4)
    assert w["p_valor"] < 0.001


def test_welch_sinal_negativo_quando_condicionado_e_pior() -> None:
    """A convencao de sinal e' load-bearing: a hipotese (b) preve
    diferenca NEGATIVA (grupo que tocou -X e' pior)."""
    pior = np.array([-10.0, -20.0, -15.0])
    melhor = np.array([10.0, 20.0, 15.0])
    assert _welch(pior, melhor)["diferenca"] < 0
    assert _welch(melhor, pior)["diferenca"] > 0


def test_welch_grupo_degenerado_nao_explode() -> None:
    w = _welch(np.array([1.0]), np.array([1.0, 2.0, 3.0]))
    assert math.isnan(w["t_welch"])


# ------------------------------------------------- extracao de operacoes
def _df_venda() -> pd.DataFrame:
    """A MAO (h=2, custo=10, lado venda): entrada=close[0]=100.
    Janela = barras 1 e 2. Vendido machuca no HIGH:
    max(130-100, 115-100) = 30. pnl bruto = (80-100)*(-1) = +20,
    liquido = +10."""
    d = date(2026, 8, 3)
    return pd.DataFrame({
        "dia": [d] * 5,
        "z": [2.0, 0.0, 0.0, 0.0, 0.0],
        "close": [100.0, 90.0, 80.0, 70.0, 60.0],
        "high": [101.0, 130.0, 115.0, 75.0, 65.0],
        "low": [99.0, 85.0, 78.0, 68.0, 58.0],
    })


def test_extracao_venda_usa_high_e_confere_a_mao() -> None:
    r = _extrair_operacoes(_df_venda(), "z", 2, 1.4, "contrarian", "venda", 10.0)
    assert len(r) == 1
    assert r.iloc[0]["mae_intrabar"] == pytest.approx(30.0)
    assert r.iloc[0]["pnl_liquido"] == pytest.approx(10.0)
    assert r.iloc[0]["lado"] == -1


def test_extracao_compra_usa_low_nao_high() -> None:
    """A MAO: comprado em 100, janela barras 1-2, machuca no LOW:
    max(100-85, 100-78) = 22. pnl bruto = (80-100)*(+1) = -20, liq = -30.
    Se o codigo usasse HIGH aqui o MAE sairia 30 -- o bug de sinal
    invertido que este teste existe para pegar."""
    df = _df_venda()
    df["z"] = [-2.0, 0.0, 0.0, 0.0, 0.0]
    r = _extrair_operacoes(df, "z", 2, 1.4, "contrarian", "compra", 10.0)
    assert r.iloc[0]["mae_intrabar"] == pytest.approx(22.0)
    assert r.iloc[0]["pnl_liquido"] == pytest.approx(-30.0)


def test_purge_estrutural_descarta_janela_incompleta() -> None:
    """Trigger perto do fim do pregao nao tem h barras de futuro no MESMO
    dia -- descartado, nunca completado com barra do dia seguinte."""
    df = _df_venda()
    df["z"] = [0.0, 0.0, 0.0, 2.0, 0.0]
    assert _extrair_operacoes(df, "z", 2, 1.4, "contrarian", "venda", 10.0).empty


def test_janela_nao_atravessa_o_pregao() -> None:
    df = _df_venda()
    df["dia"] = [date(2026, 8, 3), date(2026, 8, 3),
                 date(2026, 8, 4), date(2026, 8, 4), date(2026, 8, 4)]
    # trigger na barra 0 precisa das barras 1 e 2, mas a 2 e' de outro dia
    assert _extrair_operacoes(df, "z", 2, 1.4, "contrarian", "venda", 10.0).empty


# ------------------------------------------------------------- veredito
def _ponto(x: float, media: float, sig: bool, n: int = 50) -> dict[str, object]:
    return {"x": x, "media_tocou": media, "media_nao_tocou": 5.0,
            "n_tocou": n, "significativo": sig,
            "n_suficiente": n >= N_MINIMO_POR_PONTO}


def test_veredito_contra_quando_nada_e_significativo() -> None:
    pontos = [_ponto(x, -1.0, False) for x in GRADE_X_CONGELADA]
    veredito, _, x_estrela = _decidir(pontos)
    assert veredito == "CONTRA (b)"
    assert x_estrela is None


def test_veredito_favoravel_exige_monotonicidade() -> None:
    """X*=100 significativo e negativo, e TODOS os X acima tambem
    negativos com n suficiente."""
    pontos = [_ponto(40, 2.0, False), _ponto(60, 1.0, False),
              _ponto(80, -1.0, False), _ponto(100, -20.0, True),
              _ponto(120, -25.0, False), _ponto(150, -30.0, False),
              _ponto(200, -40.0, False)]
    veredito, _, x_estrela = _decidir(pontos)
    assert veredito == "FAVORAVEL a (b)"
    assert x_estrela == 100.0


def test_veredito_inconclusivo_quando_quebra_monotonicidade() -> None:
    """Mesmo cenario, mas X=200 volta a ser POSITIVO -- buraco isolado,
    nao estrutura. Mesmo raciocinio que concluiu Q4->Q5 = ruido."""
    pontos = [_ponto(40, 2.0, False), _ponto(60, 1.0, False),
              _ponto(80, -1.0, False), _ponto(100, -20.0, True),
              _ponto(120, -25.0, False), _ponto(150, -30.0, False),
              _ponto(200, +15.0, False)]
    veredito, _, x_estrela = _decidir(pontos)
    assert veredito == "INCONCLUSIVO"
    assert x_estrela is None


def test_veredito_inconclusivo_quando_falta_n_acima_do_x_estrela() -> None:
    """Condicao 3 do pre-registro: n>=30 em X* E em todos os pontos
    acima. Este e' o desfecho ESPERADO com poucos pregoes."""
    pontos = [_ponto(40, 2.0, False), _ponto(60, 1.0, False),
              _ponto(80, -1.0, False), _ponto(100, -20.0, True),
              _ponto(120, -25.0, False), _ponto(150, -30.0, False, n=8),
              _ponto(200, -40.0, False, n=3)]
    veredito, justificativa, x_estrela = _decidir(pontos)
    assert veredito == "INCONCLUSIVO"
    assert x_estrela is None
    assert "150" in justificativa and "200" in justificativa


def test_veredito_direcao_invertida_e_reconhecido_nao_descartado() -> None:
    """Contra-hipotese contrarian registrada ANTES: se a expectativa
    condicionada for MAIOR, e' achado genuino, nao anomalia a ignorar."""
    pontos = [_ponto(x, 1.0, False) for x in GRADE_X_CONGELADA[:-1]]
    pontos.append(_ponto(200, +30.0, True))
    veredito, justificativa, _ = _decidir(pontos)
    assert veredito == "INCONCLUSIVO (direcao invertida)"
    assert "pirimide" in justificativa or "pre-registro novo" in justificativa


# ------------------------------------------------------- ponta a ponta
def test_analise_ponta_a_ponta_gera_relatorio(tmp_path: Path) -> None:
    """Amostra sintetica pequena: o objetivo e' provar que o pipeline
    inteiro roda, reporta os 7 pontos SEMPRE, e nao inventa veredito
    favoravel com n minusculo."""
    rng = np.random.default_rng(7)
    blocos = []
    for k in range(12):
        d = date(2026, 8, 3 + k)
        n = 20
        close = 100000 + np.cumsum(rng.normal(0, 50, n))
        blocos.append(pd.DataFrame({
            "dia": [d] * n,
            "z_agf_3": rng.normal(0, 1.2, n),
            "close": close,
            "high": close + rng.uniform(10, 120, n),
            "low": close - rng.uniform(10, 120, n),
        }))
    df = pd.concat(blocos, ignore_index=True)
    arq = tmp_path / "features.parquet"
    df.to_parquet(arq)

    r = analisar_reversao_condicional(
        arq, "z_agf_3", 3, 1.4, "contrarian", 11.0, tmp_path / "out",
        lado_permitido="venda", n_bootstrap=120)

    assert len(r["pontos"]) == len(GRADE_X_CONGELADA)   # TODOS reportados
    assert r["limiar_deflacionado"] >= 1.96             # deflacao so' sobe
    assert r["veredito"].startswith(("CONTRA", "INCONCLUSIVO", "FAVORAVEL"))
    relatorio = Path(r["relatorio"])
    assert relatorio.exists()
    texto = relatorio.read_text(encoding="utf-8")
    assert "NAO consome trial" in texto
    assert "Regra de parada" in texto
    for x in GRADE_X_CONGELADA:
        assert f"| {x:.0f} |" in texto


def test_grade_esta_congelada() -> None:
    """Guarda de regressao: a grade e o n minimo foram CONGELADOS pelo
    pre-registro. Mudar qualquer um exige pre-registro novo -- se este
    teste falhar, a pergunta certa e' 'onde esta o pre-registro novo?',
    nao 'como faco o teste passar?'."""
    assert GRADE_X_CONGELADA == (40.0, 60.0, 80.0, 100.0, 120.0, 150.0, 200.0)
    assert N_MINIMO_POR_PONTO == 30
