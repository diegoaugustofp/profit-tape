"""
Triagem de PODER: o desenho consegue responder a pergunta?

Categoria `features`. Mede **variancia**, nunca a media do retorno — e
por isso pode rodar na amostra de depuracao sem queimar nada.

POR QUE EXISTE
--------------
O pre-registro de absorcao (congelado 2026-08-31) foi executado ate o
fim e o veredito nao respondia a pergunta:

    desvio dos eventos:   319 pts
    EMD = 1,96 x dp/rn:   107 pts em 2 barras
    amplitude media 5m:   244 pts

O desenho so' enxergava efeito de **0,44 amplitude de barra, liquido, em
10 minutos**. Nenhum sinal razoavel produz isso. Ele nunca teve como
responder — e isso so' foi descoberto DEPOIS de gastar o trial.

A triagem de feature (`features/triagem.py`) impede que uma feature
redundante chegue ao pre-registro. Esta impede que um DESENHO SEM PODER
chegue la'.

O QUE E' E O QUE NAO E' OLHAR RESULTADO
---------------------------------------
O EMD sai de `desvio` e `n`. **A media observada nao entra na conta** — o
mesmo EMD valeria se o resultado tivesse dado positivo, negativo ou
zero.

Isso e' o que separa "abandonar desenho impossivel" de "abandonar
desenho que deu resultado ruim". A primeira e' legitima; a segunda e'
p-hacking com outro nome.

**NAO chame nada daqui de evidencia sobre a hipotese.** A saida diz o que
o desenho CONSEGUIRIA detectar, nunca o que ele detectou.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
import structlog

log = structlog.get_logger(__name__)

# 1,96 = normal a 95%. O limiar deflacionado real e' maior, entao o EMD
# calculado aqui e' OTIMISTA -- se ja' for implausivel com 1,96, sera'
# pior no teste de verdade.
Z_95 = 1.96


def emd(desvio: float, n: int) -> float:
    """Efeito minimo detectavel. So' variancia e tamanho de amostra."""
    if n < 2 or not math.isfinite(desvio) or desvio <= 0:
        return float("nan")
    return Z_95 * desvio / math.sqrt(n)


def avaliar_desenho(retornos: pd.Series, unidade: float,
                    rotulo: str) -> dict[str, Any]:
    """
    `unidade` e' a escala do instrumento em que o EMD fica interpretavel
    — para o WIN no 5m, a amplitude media da barra (~244 pts).

    Sem ela o EMD e' um numero solto: "107" nao diz nada, "0,44 de uma
    barra inteira" diz tudo. A regra registrada exige o argumento **em
    unidade do instrumento**, nao "achei alto".
    """
    v = retornos.dropna().to_numpy(dtype=float)
    n = len(v)
    if n < 2:
        return {"desenho": rotulo, "n": n, "situacao": "amostra pequena"}
    dp = float(v.std(ddof=1))
    e = emd(dp, n)
    return {
        "desenho": rotulo,
        "n": n,
        "desvio": round(dp, 1),
        "emd": round(e, 1),
        "emd_em_unidades": round(e / unidade, 2) if unidade > 0 else float("nan"),
        # Quantos eventos para o EMD cair a UMA unidade do instrumento.
        "n_para_emd_1_unidade": (
            round((Z_95 * dp / unidade) ** 2) if unidade > 0 else -1),
    }


def comparar(candidatos: dict[str, pd.Series], unidade: float,
             emd_maximo_em_unidades: float = 0.25) -> dict[str, Any]:
    """
    Compara desenhos pelo EMD, e REPROVA os implausiveis.

    `emd_maximo_em_unidades` = 0,25: exigir que o sinal produza mais de
    um quarto da amplitude de uma barra, liquido e em media, ja' e'
    exigente. O desenho de 2026-08-31 pedia 0,44 e por isso nao
    respondia.

    O limiar e' julgamento sobre o INSTRUMENTO, nao sobre o resultado —
    pode e deve ser discutido antes, nunca depois.
    """
    linhas = [avaliar_desenho(s, unidade, nome)
              for nome, s in candidatos.items()]
    for x in linhas:
        u = x.get("emd_em_unidades")
        x["viavel"] = bool(u is not None and np.isfinite(u)
                           and u <= emd_maximo_em_unidades)
    return {
        "unidade": unidade,
        "emd_maximo_em_unidades": emd_maximo_em_unidades,
        "candidatos": sorted(linhas, key=lambda x: x.get("emd_em_unidades",
                                                         float("inf"))),
        "algum_viavel": any(x["viavel"] for x in linhas),
    }
