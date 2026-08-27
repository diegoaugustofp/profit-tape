"""
Testes de research/curva_patrimonio.py -- valores conferidos a mao antes
de confiar no calculo (mesmo padrao de mae.py).
"""

from __future__ import annotations

import pytest

from profittape.research.curva_patrimonio import calcular_curva_patrimonio


def test_drawdown_calculado_a_mao() -> None:
    """
    capital=1000, valor_ponto=1, pnl=[100,-50,-80,30,-200,150]
    saldos: 1000,1100,1050,970,1000,800,950
    pico sobe pra 1100 apos op0; pior dd = 1100-800=300 (apos op4)
    """
    c = calcular_curva_patrimonio([100, -50, -80, 30, -200, 150],
                                  capital_inicial=1000.0, valor_ponto_reais=1.0,
                                  multiplicador_seguranca=1.5)
    assert c.saldos == [1000.0, 1100.0, 1050.0, 970.0, 1000.0, 800.0, 950.0]
    assert c.saldo_final == 950.0
    assert c.retorno_total_reais == -50.0
    assert c.retorno_total_pct == pytest.approx(-0.05)
    assert c.drawdown_maximo_reais == 300.0
    assert c.drawdown_maximo_pct == pytest.approx(300 / 1100)
    assert c.saldo_no_pico == 1100.0
    assert c.saldo_no_vale == 800.0
    assert c.indice_operacao_pico == 0
    assert c.indice_operacao_vale == 4
    assert c.capital_minimo_sugerido == 450.0
    assert c.calmar_ratio == pytest.approx(-50 / 300)
    assert not c.ficou_negativo_ou_zero


def test_serie_sempre_em_alta_tem_drawdown_zero() -> None:
    c = calcular_curva_patrimonio([10, 20, 30], capital_inicial=1000.0,
                                  valor_ponto_reais=1.0)
    assert c.drawdown_maximo_reais == 0.0
    assert c.drawdown_maximo_pct == 0.0
    assert c.calmar_ratio == 0.0   # divisao por zero evitada, nao explode


def test_conta_zera_e_marcada_corretamente() -> None:
    c = calcular_curva_patrimonio([-600, -600], capital_inicial=1000.0,
                                  valor_ponto_reais=1.0)
    assert c.saldos == [1000.0, 400.0, -200.0]
    assert c.ficou_negativo_ou_zero


def test_valor_ponto_reais_diferente_de_1_escala_corretamente() -> None:
    """WIN a R$0,20/ponto: 100 pts de perda = R$20, nao R$100."""
    c = calcular_curva_patrimonio([-100], capital_inicial=5000.0,
                                  valor_ponto_reais=0.20)
    assert c.saldos == [5000.0, 4980.0]
    assert c.drawdown_maximo_reais == 20.0


def test_capital_inicial_nao_afeta_o_drawdown_em_reais() -> None:
    """Tamanho de posicao e' FIXO -- o drawdown em R$ e' funcao so' do
    historico de pnl x valor_ponto, independente do capital_inicial
    escolhido. So' 'ficou_negativo_ou_zero' e retorno_pct dependem dele."""
    pnl = [50, -300, 100, -600, 200]
    c1 = calcular_curva_patrimonio(pnl, capital_inicial=500.0, valor_ponto_reais=1.0)
    c2 = calcular_curva_patrimonio(pnl, capital_inicial=50000.0, valor_ponto_reais=1.0)
    # pico sobe para capital+50 apos a op0; vale e' capital+50-300+100-600
    # = capital-750 apos a op3 -> dd_max = (capital+50) - (capital-750) = 800,
    # IGUAL nos dois capitais, confirmando independencia do capital_inicial.
    assert c1.drawdown_maximo_reais == c2.drawdown_maximo_reais == 800.0
    assert c1.ficou_negativo_ou_zero   # capital pequeno demais, zera
    assert not c2.ficou_negativo_ou_zero   # capital grande, sobrevive


def test_capital_inicial_invalido_recusa() -> None:
    with pytest.raises(ValueError, match="capital_inicial"):
        calcular_curva_patrimonio([10], capital_inicial=0, valor_ponto_reais=1.0)
    with pytest.raises(ValueError, match="capital_inicial"):
        calcular_curva_patrimonio([10], capital_inicial=-100, valor_ponto_reais=1.0)


def test_valor_ponto_invalido_recusa() -> None:
    with pytest.raises(ValueError, match="valor_ponto_reais"):
        calcular_curva_patrimonio([10], capital_inicial=1000, valor_ponto_reais=0)
