"""
Historico M1 do WIN exportado do Profit (`data/winfut_m1_historico.csv`,
27/09/2021 em diante) -- CARGA e VALIDACAO, sem teste de hipotese nenhum.

A SERIE E' AJUSTADA MULTIPLICATIVAMENTE (achado de 2026-09-25): so' 9 de
50 precos da amostra eram multiplos de 5, e os menores degraus entre
precos eram 8/9, 17, 25/26, 34, 43 -- o tick de 5 pts vezes ~1,71,
arredondado. 195.629 / 1,7146 ~ 114.093: o WIN real de fim de set/2021.

Consequencias:
- PONTOS DO PASSADO SAO INFLADOS pelo fator do dia (~1,7 em 2021 -> ~1,0
  hoje). Regra em pontos fixos nao pode ser aplicada direto.
- Regra NORMALIZADA (limiar e barreira em fracao da amplitude) e'
  invariante: movimento e amplitude escalam pelo mesmo fator.
- Nao ha' salto nos vencimentos (ganho do ajuste).
- CUSTO em pontos reais vira custo x fator em pontos ajustados.

FATOR POR DIA, pela GRANULARIDADE (dois estagios):
  1. f0 = media dos menores degraus entre precos distintos do dia / 5
  2. n_i = round(degrau_i / (5 f0)) ticks em cada degrau;
     f = (max - min) / (5 * soma n_i)
  O 1o estagio sozinho erra (~1,729 na amostra de 22 linhas, por causa da
  proporcao 8/9); o 2o usa a faixa inteira: erro ~1 tick em centenas.

CONFERENCIA CONTRA O TAPE (dias em comum): candles de 1 min montados do
tape (rotulo = INICIO do minuto, horario de Brasilia) comparados ao
export em deslocamentos -1/0/+1 min. Duas medidas independentes:
  - PRECO: razao mediana export/tape (o fator MEDIDO) e fracao de
    fechamentos com |export - razao*tape| <= 1 tick ajustado. Usa a razao
    do proprio dia, NAO o fator da granularidade: 0,1% de erro no fator,
    a 188 mil, sao 188 pts -- a comparacao mediria o erro do fator, nao o
    alinhamento (pego pelo teste em 2026-09-25). O fator da granularidade
    e' conferido a' parte, contra a razao, em erro RELATIVO;
  - CONTAGEM: correlacao entre negocios por minuto do tape e a coluna
    `volume_ticks` do export -- nao depende do fator.
Se as duas apontarem o mesmo deslocamento, o alinhamento esta' provado
por dois caminhos.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .ignicao import Tape

_NS = 1_000_000_000
_BRT = dt.timezone(dt.timedelta(hours=-3))
COLUNAS = ["data_hora", "abertura", "maxima", "minima", "fechamento", "volume",
           "volume_ticks"]


def carregar_m1(caminho: Path) -> pd.DataFrame:
    """CSV exportado -> DataFrame com `data_hora` (naive, Brasilia), `dia`
    (YYYY-MM-DD) e as colunas numericas. Falha ALTO se o cabecalho mudar."""
    df = pd.read_csv(caminho)
    faltando = [c for c in COLUNAS if c not in df.columns]
    if faltando:
        raise ValueError(f"{caminho}: colunas ausentes {faltando}; esperado {COLUNAS}")
    df["data_hora"] = pd.to_datetime(df["data_hora"], format="%Y-%m-%d %H:%M:%S")
    df["dia"] = df["data_hora"].dt.strftime("%Y-%m-%d")
    return df


def fator_por_granularidade(precos: np.ndarray) -> float | None:
    """Fator do ajuste multiplicativo (1,0 = preco real). None se ha' niveis
    de preco de menos para medir."""
    nv = np.unique(precos[np.isfinite(precos)])
    if len(nv) < 10:
        return None
    d = np.diff(nv)
    m = d.min()
    if m <= 0:
        return None
    f0 = float(d[d <= m * 1.5].mean()) / 5.0
    n = np.maximum(1.0, np.round(d / (5.0 * f0)))
    return float((nv[-1] - nv[0]) / (5.0 * n.sum()))


def inventario_dia(g: pd.DataFrame) -> dict[str, Any]:
    t = g["data_hora"]
    minutos = (t.dt.hour * 60 + t.dt.minute).to_numpy()
    uni = np.unique(minutos)
    lacunas = int((np.diff(uni) > 1).sum())
    precos = g[["abertura", "maxima", "minima", "fechamento"]].to_numpy().ravel()
    return {"barras": len(g), "duplicatas": int(len(minutos) - len(uni)),
            "primeira": t.iloc[0].strftime("%H:%M"), "ultima": t.iloc[-1].strftime("%H:%M"),
            "lacunas": lacunas, "fator": fator_por_granularidade(precos)}


def barras_do_tape(tape: Tape) -> pd.DataFrame:
    """Candles de 1 min do tape, rotulo = INICIO do minuto (Brasilia, naive)."""
    if len(tape) == 0:
        return pd.DataFrame(columns=["abertura", "maxima", "minima", "fechamento",
                                     "negocios", "contratos"])
    t = pd.to_datetime(tape.ts, unit="ns", utc=True).tz_convert(_BRT).tz_localize(None)
    df = pd.DataFrame({"t": t.floor("min"), "p": tape.px, "q": tape.qtd})
    g = df.groupby("t", sort=True)
    return pd.DataFrame({"abertura": g["p"].first(), "maxima": g["p"].max(),
                         "minima": g["p"].min(), "fechamento": g["p"].last(),
                         "negocios": g["p"].size(), "contratos": g["q"].sum()})


def comparar_com_tape(exp_dia: pd.DataFrame, tape_barras: pd.DataFrame
                      ) -> dict[int, dict[str, Any]]:
    """Por deslocamento s (min): o candle do export rotulado T contra o
    candle do tape que COMECA em T + s. O deslocamento certo e' o que
    maximiza as duas medidas."""
    e = exp_dia.set_index("data_hora")
    out: dict[int, dict[str, Any]] = {}
    for s in (-1, 0, 1):
        tb = tape_barras.copy()
        tb.index = pd.DatetimeIndex(tb.index) - pd.Timedelta(minutes=s)
        j = e.join(tb, how="inner", rsuffix="_tape")
        if len(j) < 10:
            out[s] = {"n": len(j)}
            continue
        razao = float((j["fechamento"] / j["fechamento_tape"]).median())
        diff = (j["fechamento"] - razao * j["fechamento_tape"]).abs()
        tick = 5.0 * razao
        a, b = j["volume_ticks"].to_numpy(float), j["negocios"].to_numpy(float)
        # sem variancia a correlacao e' INDEFINIDA: None, nunca NaN, para nao
        # vencer nem perder a escolha do deslocamento por acaso
        corr = (float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0
                else None)
        out[s] = {"n": len(j), "fech_ok_pct": round(100 * float((diff <= tick + 1).mean()), 1),
                  "razao_mediana": round(razao, 5),
                  "corr_negocios_x_volume_ticks": None if corr is None else round(corr, 3)}
    return out


def melhor_deslocamento(comp: dict[int, dict[str, Any]]) -> dict[str, int | None]:
    def arg(chave: str) -> int | None:
        c = {s: v[chave] for s, v in comp.items() if v.get(chave) is not None}
        return max(c, key=lambda s: c[s]) if c else None
    return {"por_preco": arg("fech_ok_pct"), "por_contagem": arg("corr_negocios_x_volume_ticks")}
