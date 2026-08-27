"""
Curva de patrimonio e drawdown maximo -- responde a pergunta real do
operador (2026-08-27): "qual o tamanho de conta (saldo) necessario para
essa estrategia?".

Deliberadamente FORA de escopo aqui (registrado como pendente separada,
mais complexa): zeragem por CONSUMO DE GARANTIA (a B3/XP pode exigir mais
margem por contrato num dia de volatilidade alta, mesmo com saldo
positivo e folgado) -- isso exige cruzar com a tabela de margem real da
B3/XP, dado que este modulo nao tem. Aqui so' responde a ruina por P&L
(saldo cair a zero ou perto disso), que e' o que o historico de
operacoes ja simuladas permite medir diretamente.

Tamanho de posicao FIXO (1 contrato, ver ea/config.py) durante toda a
amostra -- o drawdown em REAIS calculado aqui e' INDEPENDENTE do
capital_inicial escolhido (e' so' funcao do historico de pnl em pontos x
valor_ponto_reais). capital_inicial so' entra para saber SE aquele
drawdown, aplicado aquele capital especifico, teria zerado a conta.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CurvaPatrimonio:
    saldos: list[float] = field(default_factory=list)   # inclui capital_inicial em [0]
    saldo_final: float = 0.0
    retorno_total_reais: float = 0.0
    retorno_total_pct: float = 0.0

    drawdown_maximo_reais: float = 0.0
    drawdown_maximo_pct: float = 0.0        # relativo ao PICO daquele drawdown especifico
    saldo_no_pico: float = 0.0
    saldo_no_vale: float = 0.0
    indice_operacao_pico: int = -1          # -1 = capital inicial, antes de qualquer operacao
    indice_operacao_vale: int = -1

    ficou_negativo_ou_zero: bool = False
    capital_minimo_sugerido: float = 0.0    # drawdown_maximo_reais * multiplicador
    calmar_ratio: float = 0.0               # retorno_total_reais / drawdown_maximo_reais


def calcular_curva_patrimonio(historico_pnl_pontos: list[float], capital_inicial: float,
                              valor_ponto_reais: float,
                              multiplicador_seguranca: float = 1.5) -> CurvaPatrimonio:
    """
    Algoritmo padrao de drawdown maximo (peak-to-trough), aplicado sobre o
    historico de P&L LIQUIDO ja simulado pelo EA (mesma ordem cronologica
    em que as operacoes aconteceram -- nunca reordenar/agrupar por lado
    antes de chamar isto, senao o drawdown deixa de refletir a experiencia
    real de quem estaria operando).
    """
    if capital_inicial <= 0:
        raise ValueError("capital_inicial precisa ser positivo")
    if valor_ponto_reais <= 0:
        raise ValueError("valor_ponto_reais precisa ser positivo")

    saldo = capital_inicial
    saldos = [capital_inicial]
    pico_corrente = capital_inicial
    indice_pico_corrente = -1

    dd_max_reais = 0.0
    saldo_no_pico_do_dd_max = capital_inicial
    idx_pico_do_dd_max = -1
    idx_vale_do_dd_max = -1

    for i, pnl_pts in enumerate(historico_pnl_pontos):
        saldo += pnl_pts * valor_ponto_reais
        saldos.append(saldo)

        if saldo > pico_corrente:
            pico_corrente = saldo
            indice_pico_corrente = i

        dd_atual = pico_corrente - saldo
        if dd_atual > dd_max_reais:
            dd_max_reais = dd_atual
            saldo_no_pico_do_dd_max = pico_corrente
            idx_pico_do_dd_max = indice_pico_corrente
            idx_vale_do_dd_max = i

    saldo_final = saldos[-1]
    retorno_total_reais = saldo_final - capital_inicial
    dd_max_pct = (dd_max_reais / saldo_no_pico_do_dd_max
                 if saldo_no_pico_do_dd_max > 0 else 0.0)

    return CurvaPatrimonio(
        saldos=saldos,
        saldo_final=saldo_final,
        retorno_total_reais=retorno_total_reais,
        retorno_total_pct=retorno_total_reais / capital_inicial,
        drawdown_maximo_reais=dd_max_reais,
        drawdown_maximo_pct=dd_max_pct,
        saldo_no_pico=saldo_no_pico_do_dd_max,
        saldo_no_vale=saldo_no_pico_do_dd_max - dd_max_reais,
        indice_operacao_pico=idx_pico_do_dd_max,
        indice_operacao_vale=idx_vale_do_dd_max,
        ficou_negativo_ou_zero=any(s <= 0 for s in saldos),
        capital_minimo_sugerido=dd_max_reais * multiplicador_seguranca,
        calmar_ratio=(retorno_total_reais / dd_max_reais if dd_max_reais > 0
                     else 0.0),
    )
