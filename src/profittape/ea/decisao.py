"""
Decisao pura: sinal (valor numerico) -> acao. Zero I/O, zero estado — a
unica parte do EA que da' para testar exaustivamente sem DLL nenhuma.

REGRA DE ENTRADA — por que "extremo", nao "threshold no meio":
O teste de significancia entre quintis (docs/RESEARCH_PLANO.md, 2026-08-23)
mostrou Q4 vs Q5 INDISTINGUIVEL nos dois sinais que temos (p=0.74, p=0.76).
A tentacao seria usar um threshold "mais sensivel" (early entry na fronteira
Q3/Q4) para operar mais vezes — mas isso e' precisamente o padrao que o
teste mostrou nao ter base estatistica: a diferenca entre "sinal moderado"
e "sinal extremo" e' ruido nesta amostra. A entrada aqui usa o EXTREMO
(quintil mais distante of zero), que e' onde a evidencia de fato se
sustenta — nao o ponto mais sensivel que capturaria mais sinais com menos
base.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .config import SinalConfig


class Acao(Enum):
    NADA = "nada"
    COMPRAR = "comprar"
    VENDER = "vender"
    ZERAR = "zerar"


@dataclass(frozen=True)
class Decisao:
    acao: Acao
    motivo: str
    sinal_valor: float
    feature: str


def decidir(sinal_config: SinalConfig, valor_atual: float,
           posicao_atual: int) -> Decisao:
    """
    valor_atual: o z-score mais recente da feature (mesma normalizacao do
                 research -- rolling z-score anti-lookahead, normalize.py).
    posicao_atual: contratos abertos AGORA (positivo=comprado,
                   negativo=vendido, 0=zerado). Decisao NUNCA abre posicao
                   nova sem antes considerar zerar a atual -- ver logica
                   abaixo, uma linha por vez, sem pilha de posicoes.

    Contrarian (IC negativo, ex.: z_agf_3, z_agf_4090): sinal ALTO ->
    esperado retorno NEGATIVO -> vende. Sinal BAIXO -> esperado retorno
    POSITIVO -> compra. So' entra no threshold (o extremo, ver docstring
    do modulo); no meio, NADA -- essa e' a zona onde nao ha base para agir.
    """
    limiar = abs(sinal_config.threshold_entrada)
    extremo_alto = valor_atual >= limiar
    extremo_baixo = valor_atual <= -limiar

    if sinal_config.direcao == "contrarian":
        quer_vender = extremo_alto
        quer_comprar = extremo_baixo
    elif sinal_config.direcao == "momentum":
        quer_vender = extremo_baixo
        quer_comprar = extremo_alto
    else:
        raise ValueError(f"direcao desconhecida: {sinal_config.direcao!r}")

    if quer_vender and posicao_atual > 0:
        return Decisao(Acao.ZERAR, "sinal virou contra posicao comprada",
                       valor_atual, sinal_config.feature)
    if quer_comprar and posicao_atual < 0:
        return Decisao(Acao.ZERAR, "sinal virou contra posicao vendida",
                       valor_atual, sinal_config.feature)
    if quer_vender and posicao_atual == 0:
        return Decisao(Acao.VENDER, f"{sinal_config.feature}={valor_atual:.2f} "
                       f">= limiar {limiar:.2f} (contrarian: vende no extremo alto)",
                       valor_atual, sinal_config.feature)
    if quer_comprar and posicao_atual == 0:
        return Decisao(Acao.COMPRAR, f"{sinal_config.feature}={valor_atual:.2f} "
                       f"<= -{limiar:.2f} (contrarian: compra no extremo baixo)",
                       valor_atual, sinal_config.feature)
    return Decisao(Acao.NADA, "sinal dentro da zona neutra ou posicao ja alinhada",
                   valor_atual, sinal_config.feature)
