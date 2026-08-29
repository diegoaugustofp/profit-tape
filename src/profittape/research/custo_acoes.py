"""
Custo de transacao de acoes, calculado a partir da planilha REAL da XP
(docs/referencias/custos_acoes_xp.xlsx) -- nao um numero fixo generico.

CONTEXTO (2026-08-28): um custo unico (`0.026 pts/acao`) foi usado
inicialmente para VALE3 e MGLU3 no teste de quintis de `z_agf_8` -- e
produziu um padrao suspeito (MGLU3 com `%>0 liquido` uniformemente
baixo em todos os quintis). Decodificando a planilha real, confirmou-se
a causa: o custo tem um componente FIXO (corretagem, por ORDEM) e um
componente PROPORCIONAL ao financeiro (taxas B3) -- NAO e' constante
por acao entre ativos de precos diferentes, mesmo mantendo o mesmo
risco (financeiro exposto). Refazer o teste com o custo correto (~5x
menor para MGLU3) normalizou o padrao.

REGRA: nunca reusar um `--custo-pontos` calculado para um ativo em
outro ativo com preco muito diferente -- sempre recalcular aqui, com o
preco e a quantidade (ou financeiro-alvo) do ativo especifico sendo
testado.

Day trade APENAS: o EA nunca carrega posicao overnight, entao aluguel
BTC nunca se aplica -- as formulas aqui assumem sempre "day trade" nas
taxas de liquidacao/negociacao.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import openpyxl

# Celulas da aba "Parametros" da planilha -- se a XP mudar taxas,
# atualize a planilha e rode de novo; nao tem numero fixo aqui.
_CELULAS = {
    "corretagem_day": "C6",
    "imposto_corretagem": "C7",
    "taxa_operacional_xp": "C8",
    "taxa_negociacao_b3": "C10",
    "taxa_liquidacao_day": "C12",
}


def carregar_parametros_xp(caminho_xlsx: Path) -> dict[str, float]:
    """Le os parametros de custo da aba 'Parametros' da planilha real."""
    wb = openpyxl.load_workbook(caminho_xlsx, data_only=True)
    p = wb["Parametros"]
    return {nome: float(p[celula].value) for nome, celula in _CELULAS.items()}


def custo_giro_dia_trade(preco: float, quantidade: float,
                         parametros: dict[str, float]) -> dict[str, Any]:
    """
    Custo de IDA E VOLTA (abre + fecha) para um day trade de acoes,
    replicando exatamente a secao 1-4 da aba "Calculadora" da planilha
    (Tipo de operacao = Day Trade -- nunca ha aluguel BTC em day trade,
    a posicao nunca carrega overnight).

    Devolve financeiro exposto, custo total do giro em R$, custo por
    ACAO em R$ (o numero a usar como --custo-pontos no quintis -- 1
    "ponto" de acao = R$1/acao, diferente do WIN onde 1 ponto =
    R$0.20), e o custo como % do financeiro (util para comparar entre
    ativos de preco muito diferente).
    """
    financeiro = preco * quantidade
    corretagem = parametros["corretagem_day"]
    imposto = corretagem * parametros["imposto_corretagem"]
    b3_negociacao = financeiro * parametros["taxa_negociacao_b3"]
    b3_liquidacao = financeiro * parametros["taxa_liquidacao_day"]
    taxa_op = ((corretagem + b3_negociacao + b3_liquidacao)
              * parametros["taxa_operacional_xp"])
    custo_1_ordem = corretagem + imposto + b3_negociacao + b3_liquidacao + taxa_op
    custo_giro = custo_1_ordem * 2   # abre + fecha
    return {
        "financeiro": financeiro,
        "custo_giro_total_reais": custo_giro,
        "custo_por_acao_reais": custo_giro / quantidade,
        "custo_pct_financeiro": custo_giro / financeiro,
    }


def custo_pontos_para_quintis(preco: float, financeiro_alvo: float,
                              caminho_xlsx: Path) -> float:
    """
    Atalho pronto para uso: dado o preco do ativo e o financeiro que
    voce pretende expor (mesmo criterio de risco entre ativos
    diferentes), devolve o numero para passar direto em
    `--custo-pontos` do comando `quintis`.

    Exemplo: MGLU3 a R$4.59, expondo R$10.000 -> quantidade implicita
    de 2179 acoes (fracionaria, so' para o calculo -- na pratica
    arredonde para lote de 100 na execucao real).
    """
    quantidade = financeiro_alvo / preco
    r = custo_giro_dia_trade(preco, quantidade, carregar_parametros_xp(caminho_xlsx))
    return float(r["custo_por_acao_reais"])
