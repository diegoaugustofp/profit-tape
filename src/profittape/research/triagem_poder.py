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


def curva_de_poder(d: pd.DataFrame, ks: tuple[float, ...],
                   unidade: float = 244.0) -> pd.DataFrame:
    """
    EMD em funcao do limiar de contexto `K`.

    POR QUE ISTO NAO E' CALIBRAR OLHANDO RESULTADO
    ----------------------------------------------
    Cada linha usa **desvio e n** — a media do retorno nao entra em
    nenhuma delas. A curva responde "com que K este desenho consegue
    detectar algo", nunca "com que K o resultado fica bom".

    O DIAGNOSTICO QUE ELA RESOLVE
    -----------------------------
    No trial 2026, as tres condicoes de absorcao marcaram **326 barras**
    (2,7 por pregao). A conjuncao com `|mov6| >= 3` derrubou para 62.
    **O contexto e' responsavel por quase toda a escassez de amostra**, e
    e' a escassez que torna o desenho incapaz de responder.

    Baixar `K` NAO elimina a direcao: `sign(mov6)` existe em toda barra.
    Some so' a exigencia de que o movimento seja GRANDE — o que enfraquece
    a hipotese ("absorcao apos movimento forte" vira "absorcao apos
    movimento"), e essa e' a troca a decidir.

    O QUE ESTA CURVA NAO AUTORIZA
    -----------------------------
    Rodar varios `K` no dado de teste e ficar com o melhor. **Um K, um
    pre-registro.** A curva serve para escolher ANTES, por poder, e a
    escolha tem que ser declarada com a hipotese que ela implica.
    """
    from .absorcao_barra import retornos

    linhas = []
    for k in ks:
        mascara = (d["evento"] & (d["mov_contexto"].abs() >= k)
                   & (d["lado"] != 0))
        r = retornos(d, mascara)
        if len(r) < 4:
            linhas.append({"K": k, "n": len(r), "situacao": "poucos eventos"})
            continue
        por_lado = []
        for lado in (-1, 1):
            s = r.loc[r["lado"] == lado, "retorno"]
            if len(s) >= 2:
                por_lado.append(avaliar_desenho(s, unidade, f"lado {lado}"))
        pior = max((x["emd_em_unidades"] for x in por_lado), default=float("nan"))
        linhas.append({
            "K": k,
            "n": len(r),
            "n_menor_lado": int(min((x["n"] for x in por_lado), default=0)),
            "desvio": round(float(r["retorno"].std(ddof=1)), 1),
            # o que vale e' o PIOR lado: o veredito precisa dos dois
            "emd_pior_lado_em_unidades": round(pior, 2),
        })
    return pd.DataFrame(linhas)
