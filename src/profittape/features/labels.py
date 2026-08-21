"""
Rotulagem Triple-Barrier (Lopez de Prado, cap. 3), sobre barras.

Para cada barra t: barreiras horizontais em close_t * exp(±k*sigma_t), onde
sigma_t e' a volatilidade rolante dos retornos de barra COM SHIFT (so passado);
barreira vertical h barras a frente. Label:

  +1  tocou a superior primeiro
  -1  tocou a inferior primeiro
   0  venceu a vertical sem tocar, OU toque ambiguo (ver abaixo)

AMBIGUIDADE INTRA-BARRA
-----------------------
Se high e low da MESMA barra futura cruzam as duas barreiras, a ordem dos
toques e' indecidivel sem olhar dentro da barra. Rotulamos 0 e marcamos
`ambigua=True` em vez de escolher um lado — escolher seria injetar um vies
que nenhum backtest detectaria depois. A coluna `ret_h` (retorno ate o evento
que encerrou) fica disponivel para quem preferir re-rotular pelo sinal.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def triple_barrier(
    barras: pd.DataFrame,
    k: float = 2.0,
    h: int = 10,
    janela_vol: int = 50,
) -> pd.DataFrame:
    close = barras["close"].to_numpy(dtype=float)
    high = barras["high"].to_numpy(dtype=float)
    low = barras["low"].to_numpy(dtype=float)

    ret = pd.Series(np.log(close)).diff()
    sigma = ret.rolling(janela_vol, min_periods=max(2, janela_vol // 2)).std().shift(1)
    sigma = sigma.to_numpy()

    n = len(barras)
    label = np.zeros(n, dtype=np.int8)
    ret_h = np.full(n, np.nan)
    t_evento = np.full(n, -1, dtype=np.int64)
    ambigua = np.zeros(n, dtype=bool)
    valida = np.zeros(n, dtype=bool)

    for i in range(n):
        if not np.isfinite(sigma[i]) or sigma[i] <= 0 or i + 1 >= n:
            continue
        sup = close[i] * np.exp(k * sigma[i])
        inf = close[i] * np.exp(-k * sigma[i])
        fim = min(i + h, n - 1)
        valida[i] = True
        for j in range(i + 1, fim + 1):
            toca_sup = high[j] >= sup
            toca_inf = low[j] <= inf
            if toca_sup and toca_inf:
                label[i], ambigua[i] = 0, True
            elif toca_sup:
                label[i] = 1
            elif toca_inf:
                label[i] = -1
            else:
                continue
            ret_h[i] = np.log(close[j] / close[i])
            t_evento[i] = j
            break
        else:
            label[i] = 0                      # barreira vertical
            ret_h[i] = np.log(close[fim] / close[i])
            t_evento[i] = fim

    saida = barras.copy()
    saida["label"] = label
    saida["ret_h"] = ret_h
    saida["t_evento"] = t_evento
    saida["label_ambigua"] = ambigua
    saida["label_valida"] = valida
    return saida
