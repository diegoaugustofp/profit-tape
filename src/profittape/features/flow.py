"""
Features de fluxo por barra.

Todas calculadas SOMENTE com informacao interna a barra — nenhuma olha para
frente. Normalizacao temporal (z-score) mora em normalize.py, separada de
proposito: la e' o unico lugar com janela rolante, e portanto o unico lugar
onde lookahead poderia se esconder.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..domain.enums import TradeType

_BUY = int(TradeType.AGGRESSOR_BUYER)
_SELL = int(TradeType.AGGRESSOR_SELLER)
_RLP = int(TradeType.RLP)


def top_agentes(df: pd.DataFrame, n: int = 10) -> list[int]:
    """Top-N por volume de agressao somando as duas pontas, no dataset todo."""
    agr = df[df["trade_type"].isin((_BUY, _SELL))]
    volume = (
        agr.groupby("agente_comprador")["quantidade"].sum()
        .add(agr.groupby("agente_vendedor")["quantidade"].sum(), fill_value=0)
        .sort_values(ascending=False)
    )
    return [int(a) for a in volume.head(n).index]


def calcular(df: pd.DataFrame, agentes: list[int], tick: float) -> pd.DataFrame:
    """
    Uma linha por bar_id. Colunas:

      ts_open/ts_close/duracao_s; open/high/low/close/vwap (SO agressao);
      vol_buy/vol_sell/vol_agr; n_buy/n_sell;
      imbalance      = (vol_buy - vol_sell) / vol_agr           em [-1, 1]
      tick_imbalance = (n_buy - n_sell) / (n_buy + n_sell)
      absorcao       = vol_agr / max(range_em_ticks, 1)
                       (muito volume andando pouco preco = absorcao alta)
      rlp_frac       = vol_rlp / (vol_rlp + vol_agr)            proxy varejo
      agf_{id}       = (comprado - vendido pelo agente id) / vol_agr

    Fluxo por agente usa APENAS negocios de agressao: em RLP o "agente" da
    ponta provedora e' o internalizador e misturaria dois fenomenos distintos.
    """
    agr = df[df["trade_type"].isin((_BUY, _SELL))]
    rlp = df[df["trade_type"] == _RLP]

    g = agr.groupby("bar_id", observed=True)
    barras = pd.DataFrame({
        "ts_open": g["ts_ns"].first(),
        "ts_close": g["ts_ns"].last(),
        "open": g["price"].first(),
        "high": g["price"].max(),
        "low": g["price"].min(),
        "close": g["price"].last(),
        "vol_agr": g["quantidade"].sum(),
        "n_trades": g.size(),
    })
    barras["duracao_s"] = (barras["ts_close"] - barras["ts_open"]) / 1e9
    barras["vwap"] = g.apply(
        lambda x: np.average(x["price"], weights=x["quantidade"]),
        include_groups=False,
    )

    compras = agr[agr["trade_type"] == _BUY].groupby("bar_id", observed=True)
    vendas = agr[agr["trade_type"] == _SELL].groupby("bar_id", observed=True)
    barras["vol_buy"] = compras["quantidade"].sum().reindex(barras.index, fill_value=0)
    barras["vol_sell"] = vendas["quantidade"].sum().reindex(barras.index, fill_value=0)
    barras["n_buy"] = compras.size().reindex(barras.index, fill_value=0)
    barras["n_sell"] = vendas.size().reindex(barras.index, fill_value=0)

    barras["imbalance"] = (barras["vol_buy"] - barras["vol_sell"]) / barras["vol_agr"]
    barras["tick_imbalance"] = (barras["n_buy"] - barras["n_sell"]) / (
        barras["n_buy"] + barras["n_sell"]
    )
    range_ticks = (barras["high"] - barras["low"]) / tick
    barras["absorcao"] = barras["vol_agr"] / np.maximum(range_ticks, 1.0)

    vol_rlp = rlp.groupby("bar_id", observed=True)["quantidade"].sum()
    barras["vol_rlp"] = vol_rlp.reindex(barras.index, fill_value=0)
    barras["rlp_frac"] = barras["vol_rlp"] / (barras["vol_rlp"] + barras["vol_agr"])

    for aid in agentes:
        comprado = (
            agr[agr["agente_comprador"] == aid]
            .groupby("bar_id", observed=True)["quantidade"].sum()
            .reindex(barras.index, fill_value=0)
        )
        vendido = (
            agr[agr["agente_vendedor"] == aid]
            .groupby("bar_id", observed=True)["quantidade"].sum()
            .reindex(barras.index, fill_value=0)
        )
        barras[f"agf_{aid}"] = (comprado - vendido) / barras["vol_agr"]

    return barras.reset_index()
