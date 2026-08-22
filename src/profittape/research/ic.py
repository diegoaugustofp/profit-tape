"""IC de Spearman por feature x horizonte, avaliado nos dias de TESTE."""

from __future__ import annotations

import numpy as np
import pandas as pd


def ic_spearman(x: pd.Series, y: pd.Series) -> float:
    """Correlacao de postos; NaN-safe; NaN se amostra < 10 (sem fingir precisao)."""
    m = x.notna() & y.notna()
    if int(m.sum()) < 10:
        return float("nan")
    return float(x[m].rank().corr(y[m].rank()))


def avaliar(df: pd.DataFrame, features: list[str], horizontes: list[int],
            folds: list[tuple[list, list]]) -> pd.DataFrame:
    """
    Para cada (feature, horizonte): IC de Spearman em cada fold de teste.
    Agrega media, desvio ENTRE folds, t-stat (media/erro-padrao) e
    consistencia de sinal. O desvio entre folds e' a medida honesta de
    estabilidade — um IC medio alto com sinal trocando de fold a fold e'
    ruido, nao sinal.
    """
    linhas = []
    for feat in features:
        for h in horizontes:
            alvo = f"ret_fut_{h}"
            ics = []
            n_obs = 0
            for _treino, teste in folds:
                bloco = df[df["dia"].isin(teste)]
                ics.append(ic_spearman(bloco[feat], bloco[alvo]))
                n_obs += int((bloco[feat].notna() & bloco[alvo].notna()).sum())
            ics_arr = np.array([v for v in ics if not np.isnan(v)])
            k = len(ics_arr)
            if k == 0:
                media = desvio = t = consist = float("nan")
            else:
                media = float(ics_arr.mean())
                desvio = float(ics_arr.std(ddof=1)) if k > 1 else float("nan")
                t = float(media / (desvio / np.sqrt(k))) if k > 1 and desvio > 0 else float("nan")
                consist = float((np.sign(ics_arr) == np.sign(media)).mean()) if media != 0 else 0.0
            linhas.append({
                "feature": feat, "horizonte": h, "folds_validos": k,
                "n_obs_teste": n_obs,
                "ic_medio": media, "ic_desvio": desvio, "t_stat": t,
                "consistencia_sinal": consist,
                "ics_por_fold": [round(v, 4) if not np.isnan(v) else None for v in ics],
            })
    return pd.DataFrame(linhas)
