"""
Decomposicao diagnostica: ONDE o efeito esta', nao SE ele existe.

FASE DE ENTENDIMENTO
--------------------
Nomeada pelo operador em 2026-09-04, e ela nao existia. Tudo que o
pipeline fazia respondia **aprova ou reprova**; nada respondia **onde e
quando**.

Uma media de -4,55 sobre 10.305 barras pode ser duas coisas opostas:

    (a) -4,5 em quase toda barra  -> efeito difuso, nao operavel
    (b) -40 nos dias que andam,
        0 nos dias parados       -> efeito CONCENTRADO

A media nao distingue, e o pre-registro nao foi feito para explicar.

REGRA DA FASE
-------------
**Diagnostico em amostra QUEIMADA e' ilimitado.** Pode decompor por lado,
por tipo de dia, por hora, quantas vezes quiser — nao gasta trial.

**O que ele NAO pode e' validar.** Qualquer numero achado aqui e'
HIPOTESE, nunca evidencia. Testar exige declaracao propria e amostra que
nao seja esta.

A ARMADILHA QUE ESTE MODULO TEM QUE ADMITIR
-------------------------------------------
Decompor em muitas celulas **garante** que alguma pareca significativa.
Com 12 celulas independentes sob H0, a chance de ao menos uma passar de
|t| 1,96 e' 46%.

Por isso `resumir` reporta quantas celulas foram olhadas e quantas seriam
esperadas por acaso. Uma celula extrema entre doze nao e' achado — e'
aritmetica.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import structlog

log = structlog.get_logger(__name__)


def classificar_dias(barras: pd.DataFrame) -> pd.DataFrame:
    """
    Um rotulo por pregao, a partir da FORMA do dia.

    `direcionalidade` = |close_dia - open_dia| / range_dia, entre 0 e 1:
      perto de 1  o dia andou e ficou (tendencia)
      perto de 0  o dia andou e voltou (lateral / oscilacao)

    Isto e' calculado com o dia INTEIRO, entao **nao serve para decidir
    em tempo real** — serve para explicar. Se o efeito se concentrar num
    tipo, a pergunta seguinte e' se da' para identificar o tipo ANTES, e
    essa e' outra hipotese.
    """
    g = barras.groupby("dia")
    dia = pd.DataFrame({
        "abertura": g["open"].first(),
        "fechamento": g["close"].last(),
        "maxima": g["high"].max(),
        "minima": g["low"].min(),
        "volume": g["vol_agr"].sum(),
    })
    dia["range_dia"] = dia["maxima"] - dia["minima"]
    dia["desloc_dia"] = (dia["fechamento"] - dia["abertura"]).abs()
    dia["direcionalidade"] = (
        dia["desloc_dia"] / dia["range_dia"].where(dia["range_dia"] > 0))
    # tercis: rotulos sao do PROPRIO periodo, entao comparaveis so' dentro
    # dele. Um tercil nao e' um limiar transferivel.
    dia["tipo"] = pd.qcut(dia["direcionalidade"], 3,
                          labels=["oscilou", "misto", "andou"])
    dia["tamanho"] = pd.qcut(dia["range_dia"], 3,
                             labels=["parado", "medio", "amplo"])
    return dia


def decompor(retornos: pd.DataFrame, dias: pd.DataFrame,
             por: str) -> pd.DataFrame:
    """
    Media e `t` por celula. **Sem veredito** — de proposito.

    `retornos` precisa de `dia`, `lado` e `retorno`.
    """
    r = retornos.join(dias[[por]], on="dia")
    linhas = []
    for valor, grupo in r.groupby(por, observed=True):
        for lado, rotulo in ((-1, "AQUA"), (1, "FUCSIA")):
            v = grupo.loc[grupo["lado"] == lado, "retorno"].to_numpy(dtype=float)
            v = v[np.isfinite(v)]
            if len(v) < 2:
                linhas.append({por: valor, "lado": rotulo, "n": len(v)})
                continue
            dp = float(v.std(ddof=1))
            t = float(v.mean() / (dp / np.sqrt(len(v)))) if dp > 0 else 0.0
            linhas.append({
                por: str(valor), "lado": rotulo, "n": len(v),
                "media": round(float(v.mean()), 1),
                "t": round(t, 2),
            })
    return pd.DataFrame(linhas)


def resumir(tabelas: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """
    Conta as celulas olhadas e quantas seriam extremas POR ACASO.

    Sem isto, olhar doze celulas e destacar a mais forte parece achado —
    e e' aritmetica. Com 12 celulas sob H0, a chance de ao menos uma
    passar de |t| 1,96 e' 46%.
    """
    total = sum(int((t["n"] >= 2).sum()) for t in tabelas.values())
    extremas = sum(
        int((t.get("t", pd.Series(dtype=float)).abs() >= 1.96).sum())
        for t in tabelas.values())
    esperadas = total * 0.05
    return {
        "celulas": total,
        "celulas_extremas": extremas,
        "esperadas_por_acaso": round(esperadas, 1),
        "chance_de_ao_menos_uma": (
            f"{(1 - 0.95 ** total) * 100:.0f}%" if total else "—"),
        "leitura": (
            "extremas <= esperadas: nada aqui distingue de ruido"
            if extremas <= esperadas else
            "extremas > esperadas: vale formular hipotese, NAO concluir"),
    }
