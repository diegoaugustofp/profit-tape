"""
Volume bars com relogio de AGRESSAO.

POR QUE VOLUME BARS
-------------------
Barra de tempo fixo amostra o mercado no ritmo do relogio; informacao chega no
ritmo da atividade. Amostrar por volume (Lopez de Prado, cap. 2) aproxima as
barras de retornos mais bem-comportados e evita que a madrugada do after e o
leilao de abertura tenham o mesmo peso.

O DETALHE B3: SO AGRESSAO AVANCA O RELOGIO
------------------------------------------
RLP e' ~25% do volume do WIN e NAO e' agressao em livro — e' varejo
internalizado. Se RLP avancasse o relogio, as barras encolheriam nos horarios
de pico de varejo sem que houvesse mais informacao de microestrutura. Leilao
idem. Regra: o relogio conta apenas AGGRESSOR_BUYER/SELLER; os demais negocios
sao ATRIBUIDOS a barra corrente (para features auxiliares como fracao RLP),
mas nao a fecham.

FRONTEIRA DE SESSAO
-------------------
Barra nunca atravessa dia: o resto incompleto do fim do pregao e' DESCARTADO
(flag `descartadas_parciais` no resumo). Barra parcial tem variancia de outro
regime e contaminaria qualquer estatistica por barra.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..domain.enums import TradeType

_AGRESSAO = (int(TradeType.AGGRESSOR_BUYER), int(TradeType.AGGRESSOR_SELLER))


def sugerir_volume_barra(df: pd.DataFrame, barras_por_dia: int = 100) -> int:
    """
    Threshold = mediana do volume de agressao diario / alvo de barras.

    Mediana, nao media: um vencimento de opcoes no meio da amostra nao deve
    ditar o tamanho da barra dos dias normais.
    """
    agr = df[df["trade_type"].isin(_AGRESSAO)]
    por_dia = agr.groupby(agr["dt"], observed=True)["quantidade"].sum()
    alvo = float(por_dia.median()) / barras_por_dia
    # Arredonda para 2 algarismos significativos: threshold "bonito" facilita
    # comparar rodadas e evita falsa precisao.
    if alvo <= 0:
        raise ValueError("sem volume de agressao no dataset")
    magnitude = 10 ** (int(np.floor(np.log10(alvo))) - 1)
    return int(round(alvo / magnitude) * magnitude)


def atribuir_barras(df: pd.DataFrame, volume_barra: int) -> tuple[pd.DataFrame, int]:
    """
    Adiciona a coluna `bar_id` (global, crescente atraves dos dias) e devolve
    (df_sem_parciais, n_barras_parciais_descartadas).

    Convencao de fechamento: o negocio cuja soma cumulativa CRUZA o threshold
    pertence a barra que ele completa (bar_id = cum_anterior // T).
    """
    if not df["ts_ns"].is_monotonic_increasing:
        df = df.sort_values("ts_ns", kind="stable").reset_index(drop=True)

    vol_clock = np.where(df["trade_type"].isin(_AGRESSAO), df["quantidade"], 0)

    partes: list[pd.DataFrame] = []
    descartadas = 0
    offset = 0
    for _, grupo in df.groupby("dt", observed=True, sort=True):
        vc = vol_clock[grupo.index]
        cum_prev = np.cumsum(vc) - vc          # exclusivo: soma ANTES do negocio
        bar_local = (cum_prev // volume_barra).astype(np.int64)

        # Descarta a ultima barra do dia se incompleta.
        total = cum_prev[-1] + vc[-1]
        completas = int(total // volume_barra)
        mask = bar_local < completas
        descartadas += int((~mask).any())

        g = grupo.loc[mask].copy()
        g["bar_id"] = bar_local[mask] + offset
        offset += completas
        partes.append(g)

    if not partes:
        raise ValueError("nenhuma barra completa — volume_barra grande demais?")
    return pd.concat(partes, ignore_index=True), descartadas


def inferir_tick(df: pd.DataFrame) -> float:
    """
    Tick = menor variacao de preco positiva observada na agressao.

    Inferido do dado em vez de tabelado: sobrevive a mudanca de regra da B3 e
    a simbolos que nao previmos. Mediana por dia para robustez a outlier.
    """
    agr = df[df["trade_type"].isin(_AGRESSAO)]
    ticks = []
    for _, g in agr.groupby("dt", observed=True):
        difs = g["price"].diff().abs()
        positivos = difs[difs > 0]
        if len(positivos):
            ticks.append(positivos.min())
    if not ticks:
        raise ValueError("impossivel inferir tick: sem variacao de preco")
    return float(np.median(ticks))
