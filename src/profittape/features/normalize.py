"""
Normalizacao temporal — o UNICO modulo com janela rolante.

A concentracao e' deliberada: janela rolante e' onde lookahead se esconde, e
um lugar so e' auditavel. A regra inegociavel: estatistica de normalizacao do
instante t usa dados ATE t-1 (shift(1) antes de aplicar). Um z-score que
inclui a propria observacao na media ja vaza o presente; incluir o futuro nem
se discute.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def zscore_rolante(serie: pd.Series, janela: int) -> pd.Series:
    """
    z_t = (x_t - media_{t-J..t-1}) / desvio_{t-J..t-1}

    O shift(1) e' a garantia anti-lookahead: a barra t e' avaliada contra o
    passado ESTRITO. min_periods = metade da janela: as primeiras barras saem
    NaN em vez de sairem com estatistica de amostra minuscula.
    """
    media = serie.rolling(janela, min_periods=max(2, janela // 2)).mean().shift(1)
    desvio = serie.rolling(janela, min_periods=max(2, janela // 2)).std().shift(1)
    return (serie - media) / desvio.replace(0.0, np.nan)


def aplicar(barras: pd.DataFrame, colunas: list[str], janela: int) -> pd.DataFrame:
    """Adiciona z_{col} para cada coluna pedida. Janela em BARRAS, nao em tempo."""
    saida = barras.copy()
    for col in colunas:
        saida[f"z_{col}"] = zscore_rolante(barras[col], janela)
    return saida
