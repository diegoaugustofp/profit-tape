"""
Testes de research/custo_acoes.py -- valores conferidos a mao (mesmo
exemplo ja' presente na propria planilha, e ja' conferido manualmente
em sessao anterior antes de confiar no codigo).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from profittape.research.custo_acoes import (
    carregar_parametros_xp,
    custo_giro_dia_trade,
    custo_pontos_para_quintis,
)

_XLSX = Path(__file__).parent.parent / "docs" / "referencias" / "custos_acoes_xp.xlsx"


@pytest.fixture(scope="module")
def parametros() -> dict[str, float]:
    if not _XLSX.exists():
        pytest.skip(f"planilha real nao encontrada em {_XLSX}")
    return carregar_parametros_xp(_XLSX)


def test_parametros_tem_as_chaves_esperadas(parametros: dict[str, float]) -> None:
    assert set(parametros) == {
        "corretagem_day", "imposto_corretagem", "taxa_operacional_xp",
        "taxa_negociacao_b3", "taxa_liquidacao_day",
    }
    # sanidade: corretagem_day e' valor FIXO em R$ (nao uma taxa) --
    # as demais sao taxas percentuais, sempre entre 0 e 1
    assert 0 < parametros["corretagem_day"] < 100   # R$, faixa plausivel
    for nome, v in parametros.items():
        if nome != "corretagem_day":
            assert 0 <= v < 1, f"{nome}={v} fora da faixa esperada de taxa"


def test_exemplo_da_propria_planilha_conferido_a_mao(parametros: dict[str, float]) -> None:
    """
    Exemplo ja' preenchido na aba Calculadora da planilha real
    (preco=37.52, qtd=300, day trade): D31 (custo do giro) = 12.18514784,
    D33 (custo por acao) = 0.04061715946666667 -- conferido a mao
    ANTES de confiar no codigo (disciplina do projeto).
    """
    r = custo_giro_dia_trade(37.52, 300, parametros)
    assert r["custo_giro_total_reais"] == pytest.approx(12.18514784, abs=1e-6)
    assert r["custo_por_acao_reais"] == pytest.approx(0.04061715946666667, abs=1e-8)
    assert r["financeiro"] == pytest.approx(37.52 * 300)


def test_custo_por_acao_diminui_com_mais_acoes_mesmo_financeiro(
    parametros: dict[str, float],
) -> None:
    """
    O achado real que motivou este modulo: custo por acao NAO e'
    constante entre ativos de preco diferente, mesmo com o MESMO
    financeiro exposto -- a corretagem fixa se dilui mais quanto mais
    acoes. VALE3 (caro, poucas acoes p/ o mesmo financeiro) deve ter
    custo por acao MAIOR que MGLU3 (barato, muitas acoes).
    """
    financeiro = 10_000.0
    preco_vale3, preco_mglu3 = 78.02, 4.59

    r_vale3 = custo_giro_dia_trade(preco_vale3, financeiro / preco_vale3, parametros)
    r_mglu3 = custo_giro_dia_trade(preco_mglu3, financeiro / preco_mglu3, parametros)

    assert r_vale3["custo_por_acao_reais"] > r_mglu3["custo_por_acao_reais"]
    # custo TOTAL em R$ (nao por acao) e' igual pro mesmo financeiro --
    # so' a parte proporcional (B3) depende do financeiro, a fixa
    # (corretagem) e' a mesma nos dois; a diferenca esperada e' pequena
    # (a taxa operacional tambem incide sobre a parte B3, que e' igual)
    assert r_vale3["custo_giro_total_reais"] == pytest.approx(
        r_mglu3["custo_giro_total_reais"], rel=1e-9
    )
    # mas o PERCENTUAL do financeiro e' identico (mesmo financeiro,
    # mesmo custo total em R$)
    assert r_vale3["custo_pct_financeiro"] == pytest.approx(
        r_mglu3["custo_pct_financeiro"], rel=1e-9
    )


def test_custo_pontos_para_quintis_atalho(parametros: dict[str, float]) -> None:
    """O atalho de conveniencia bate com o calculo explicito equivalente."""
    preco, financeiro = 4.59, 10_000.0
    esperado = custo_giro_dia_trade(preco, financeiro / preco, parametros)
    obtido = custo_pontos_para_quintis(preco, financeiro, _XLSX)
    assert obtido == pytest.approx(esperado["custo_por_acao_reais"])
