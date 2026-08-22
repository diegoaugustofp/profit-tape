"""Retornos futuros por horizonte, SEM cruzar o dia."""

from __future__ import annotations

import pandas as pd


def adicionar_ret_futuro(barras: pd.DataFrame, horizontes: list[int]) -> pd.DataFrame:
    """
    ret_fut_{h} = close[t+h]/close[t] - 1, calculado DENTRO de cada dia.

    As ultimas h barras de cada pregao ficam NaN — nao ha futuro intra-dia
    para elas. Isso e' o que torna o purging do walk-forward estrutural:
    nenhuma janela de retorno atravessa a fronteira de dias, logo nenhuma
    atravessa a fronteira treino/teste (que e' sempre em dia inteiro).
    """
    df = barras.copy()
    if "dia" not in df.columns:
        df["dia"] = pd.to_datetime(df["ts_close"], unit="ns", utc=True).dt.date
    for h in horizontes:
        df[f"ret_fut_{h}"] = (
            df.groupby("dia", observed=True)["close"].shift(-h) / df["close"] - 1
        )
    return df
