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


def calcular(df: pd.DataFrame, agentes: list[int], tick: float,
            agentes_nacionais: set[int] | None = None,
            incluir_absorcao_dir: bool = False) -> pd.DataFrame:
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
      fluxo_nacional = (comprado - vendido pelos agentes NACIONAL) / vol_agr
                       So' calculada se agentes_nacionais for passado — feature
                       de PERFIL validada contra a serie oficial da B3 antes de
                       entrar aqui (docs/RESEARCH_PLANO.md, 2026-08-23):
                       ESTRANGEIRO nao validou (baixo volume nos codigos
                       classificados) e fica de fora; NACIONAL validou
                       (pearson 0.524) e e' a unica agregacao de perfil que
                       entra no research por ora.

    Fluxo por agente usa APENAS negocios de agressao: em RLP o "agente" da
    ponta provedora e' o internalizador e misturaria dois fenomenos distintos.

    Com `incluir_absorcao_dir=True` (default False, para nao alterar nenhuma
    saida existente), acrescenta as duas colunas do pre-registro de
    2026-08-29e:

      desloc_norm  = (close - open) / (high - low)     em [-1, 1]
      absorcao_dir = imbalance - desloc_norm

    A frase inteira do mecanismo: o esforco foi para um lado e o preco fechou
    para o outro. Positivo = compradores agrediram e nao levaram.

    Guarda `high == low`: `desloc_norm := 0`. Uma barra que nao andou nao
    tem "para onde o preco fechou"; 0 e' o unico valor que nao inventa
    direcao. Sem a guarda seria 0/0 = NaN, que o z-score propagaria.
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
    def _vwap(x: pd.DataFrame) -> float:
        return float(np.average(x["price"], weights=x["quantidade"]))

    # Entrada sem nenhum negocio de agressao produz um groupby vazio, e
    # `apply` sobre ele devolve um DataFrame com as colunas ORIGINAIS —
    # que ao ser atribuido a uma coluna unica estoura com "Cannot set a
    # DataFrame with multiple columns". O erro do pandas nao diz nada
    # sobre a causa. Caso real (2026-08-30): o gerador de ruido do portao
    # da Rota B produzia menos volume por dia que o `volume_barra`, entao
    # nenhuma barra fechava.
    if agr.empty:
        raise ValueError(
            "nenhum negocio de agressao apos o corte de barras: verifique "
            "se `volume_barra` nao esta maior que o volume disponivel por "
            "pregao (todas as barras viraram parciais e foram descartadas)"
        )

    # Ignorar tipo, justificado (2026-08-28): limitacao conhecida do
    # pandas-stubs -- os overloads de DataFrameGroupBy.apply() nao casam
    # bem com include_groups=False + uma callable com assinatura concreta
    # (Callable[[DataFrame], float]), mesmo sendo exatamente o uso correto
    # e documentado da API do pandas. Nao e' um erro de tipo real no
    # nosso codigo.
    barras["vwap"] = g.apply(_vwap, include_groups=False)  # type: ignore[call-overload]

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
    amplitude = barras["high"] - barras["low"]
    range_ticks = amplitude / tick
    barras["absorcao"] = barras["vol_agr"] / np.maximum(range_ticks, 1.0)

    if incluir_absorcao_dir:
        desloc = (barras["close"] - barras["open"]) / amplitude
        barras["desloc_norm"] = desloc.where(amplitude > 0, 0.0)
        barras["absorcao_dir"] = barras["imbalance"] - barras["desloc_norm"]

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

    if agentes_nacionais:
        # Mesma logica do agf_id, mas somando TODOS os agentes do perfil de
        # uma vez (nao precisa que estejam no top-N individual — um agente
        # pequeno mas classificado ainda entra na soma do perfil).
        mask_compra_nac = agr["agente_comprador"].isin(agentes_nacionais)
        mask_venda_nac = agr["agente_vendedor"].isin(agentes_nacionais)
        comprado_nac = (
            agr[mask_compra_nac].groupby("bar_id", observed=True)["quantidade"].sum()
            .reindex(barras.index, fill_value=0)
        )
        vendido_nac = (
            agr[mask_venda_nac].groupby("bar_id", observed=True)["quantidade"].sum()
            .reindex(barras.index, fill_value=0)
        )
        barras["fluxo_nacional"] = (comprado_nac - vendido_nac) / barras["vol_agr"]

    return barras.reset_index()
