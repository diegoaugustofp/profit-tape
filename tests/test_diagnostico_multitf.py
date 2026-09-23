"""
Armadilhas do modelo de dois timeframes.

A principal: durante 24 barras de 15s o contexto de 6 min fica
CONGELADO, entao os sinais vem em RAJADAS e as operacoes NAO sao
independentes -- o que todos os IC desta familia assumiram.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from profittape.research.diagnostico_multitf import ic_corrigido, medir

_BASE = int(pd.Timestamp("2026-09-01 09:00:00").timestamp()) * 10**9
_P15 = 15 * 10**9


def _barras(n: int, sinais_em: list[int]) -> pd.DataFrame:
    v = np.arange(n, dtype=float)
    x = pd.DataFrame({
        "ts_ini_ns": _BASE + np.arange(n) * _P15,
        "ts": pd.to_datetime([(_BASE + i * _P15) // 10**9 for i in range(n)], unit="s"),
        "dia": "2026-09-01", "open": v, "high": v + 2, "low": v - 1, "close": v + 1,
        "sinal_compra": False, "sinal_venda": False})
    x.loc[sinais_em, "sinal_compra"] = True
    return x


def test_sinais_espalhados_NAO_formam_cluster() -> None:
    """Um sinal por janela de 6 min (24 barras) -> cluster medio 1,0, e
    o deff nao infla nada."""
    d = medir(_barras(24 * 10, [0, 24, 48, 72, 96]))
    assert d.operacoes == 5 and d.janelas_com_sinal == 5
    assert d.tamanho_medio_cluster == pytest.approx(1.0)
    assert d.deff_conservador == pytest.approx(1.0)
    assert d.n_efetivo == pytest.approx(5.0)


def test_sinais_na_MESMA_janela_formam_cluster() -> None:
    """A armadilha: 4 sinais dentro da mesma janela de 6 min compartilham
    o MESMO contexto -- valem menos que 4 observacoes independentes."""
    d = medir(_barras(24 * 10, [0, 5, 10, 15]))
    assert d.operacoes == 4 and d.janelas_com_sinal == 1
    assert d.tamanho_medio_cluster == pytest.approx(4.0)
    assert d.maior_cluster == 4
    assert d.n_efetivo == pytest.approx(1.0), (
        "4 sinais no mesmo contexto valem ~1 observacao no pior caso")


def test_deff_infla_o_IC_e_pode_virar_o_veredito() -> None:
    """Numeros REAIS da sessao: o CONTRA da variante limitada foi
    -26,0 com IC95 (-43,8; -8,2). Se o cluster medio for grande o
    bastante, esse IC cruza zero e o veredito vira INCONCLUSIVO."""
    lo1, hi1 = ic_corrigido(-26.0, -43.8, -8.2, 320, deff=1.0)
    assert hi1 == pytest.approx(-8.2, abs=0.1), "deff=1 nao muda nada"
    lo3, hi3 = ic_corrigido(-26.0, -43.8, -8.2, 320, deff=3.0)
    assert hi3 > 0, "com deff=3 o IC cruza zero"
    assert lo3 < lo1, "o IC so' pode ALARGAR, nunca estreitar"


def test_ic_corrigido_nunca_estreita() -> None:
    for deff in (0.5, 1.0, 2.0):     # 0,5 e' invalido e deve ser tratado como 1
        lo, hi = ic_corrigido(-10.0, -20.0, 0.0, 100, deff)
        assert hi - lo >= 20.0 - 1e-9


def test_aquecimento_do_contexto_e_reportado() -> None:
    """O contexto so' existe apos 10 barras de 6 min = 60 min. Com o
    pregao comecando 09:00, o 1o sinal possivel e' ~10:00 -- 26% do
    pregao util fica sem sinal, e isso precisa aparecer."""
    d = medir(_barras(24 * 15, [300]))
    # 09:00 + 10 barras de 6 min = 10:00 e' quando a 10a barra FECHA;
    # `ts_fim` da 11a (indice 10, a primeira com estocastico definido)
    # e' 10:06. A diferenca de 6 min e' a propria latencia do contexto.
    assert d.primeira_hora_com_contexto == "10:06"


def test_barras_de_contexto_incompletas_sao_contadas() -> None:
    """Balde sem negocio nao existe no dado, entao uma 'barra de 6 min'
    pode ter menos de 24 barras de 15s -- e o estocastico sobre ela
    mistura periodos de liquidez diferentes, sem nada acusar."""
    x = _barras(24 * 5, [100])
    x = x.drop(index=range(24, 44))        # buraco no meio
    d = medir(x)
    assert d.barras_contexto_incompletas >= 1
    assert d.barras15_mediana <= 24
