"""
TRIAGEM DA ABSORCAO DE GRAFICO (7.2) — 2026-09-16.

Por que esta etapa existe ANTES da ficha: em 31/08 a linha de fluxo
matou a `absorcao_dir` com um diagnostico — ela correlacionava 0,988 com
`-desloc_norm`, era DESLOCAMENTO DISFARCADO. A absorcao crua tem um
risco irmao:

    absorcao = volume / range_em_ticks

`range` esta' no DENOMINADOR e varia muito mais que volume. Se a
variancia de log(absorcao) vier quase toda de log(range), "absorcao
alta" e' so' "BARRA ESTREITA" — e qualquer sinal em cima disso e' sinal
de barra estreita, nao de fluxo. A triagem mede isso antes de qualquer
ficha, e usa o dump do GRAFICO (dez anos), nao o tape.

O que mede, em log (a absorcao e' um quociente; em log a decomposicao e'
exata):

  1. decomposicao da variancia: var(log A) = var(log V) + var(log R)
     - 2 cov(log V, log R). Quanto de log A vem de cada lado.
  2. concordancia no DECIL (o que importa para gate): das barras no
     decil superior de absorcao, quantas estao no decil superior de
     1/range (= barra mais estreita) e quantas no decil superior de
     volume. Acaso = 10%.
  3. o mesmo DEPOIS de normalizar por HORARIO (z por hhmm): volume e
     range tem padrao intradiario forte; sem tirar isso, "absorcao alta"
     pode ser so' "meio do dia".

LEITURA: concordancia com 1/range >> concordancia com volume e variancia
dominada por log(range) = absorcao e' range disfarcado; a ficha NAO se
escreve nessa forma. O contrario (ou equilibrio) = a feature carrega
informacao de volume e a ficha faz sentido.

Categoria `features`: zero trial, nenhum retorno olhado.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog

from .eas_preco import TICK_WIN, carregar_log, indicadores

log = structlog.get_logger(__name__)


def _z_por_hhmm(s: pd.Series, hhmm: pd.Series) -> pd.Series:
    g = s.groupby(hhmm)
    return (s - g.transform("mean")) / g.transform("std").replace(0, np.nan)


def _concordancia(verdade: pd.Series, candidato: pd.Series, q: float = 0.9) -> dict[str, Any]:
    top_v = verdade >= verdade.quantile(q)
    top_c = candidato >= candidato.quantile(q)
    n_top = int(top_v.sum())
    return {"no_decil": n_top, "tambem": int((top_v & top_c).sum()),
            "taxa": round(int((top_v & top_c).sum()) / max(n_top, 1), 3)}


def triar(dump: Path, saida: Path | None = None) -> dict[str, Any]:
    df, meta = carregar_log(dump)
    d = indicadores(df)
    d = d[(d["vol_total"] > 0) & (d["high"] > d["low"])].copy()
    d["range_ticks"] = (d["high"] - d["low"]) / TICK_WIN
    d["absorcao"] = d["vol_total"] / d["range_ticks"]
    lv, lr = np.log(d["vol_total"]), np.log(d["range_ticks"])
    la = lv - lr
    var_a = float(la.var())
    var_v, var_r = float(lv.var()), float(lr.var())
    cov = float(np.cov(lv, lr)[0, 1])
    inv_range = -d["range_ticks"]           # decil superior = barra mais estreita

    bruto: dict[str, Any] = {
        "var_log_absorcao": round(var_a, 4),
        "var_log_volume": round(var_v, 4),
        "var_log_range": round(var_r, 4),
        "cov_log_v_log_r": round(cov, 4),
        "fracao_da_var_vinda_do_range": round(var_r / (var_v + var_r), 4),
        "corr_log_absorcao_com_log_volume": round(float(np.corrcoef(la, lv)[0, 1]), 4),
        "corr_log_absorcao_com_menos_log_range": round(float(np.corrcoef(la, -lr)[0, 1]), 4),
        "decil_tambem_em_barra_estreita": _concordancia(d["absorcao"], inv_range),
        "decil_tambem_em_volume_alto": _concordancia(d["absorcao"], d["vol_total"]),
    }

    # depois de tirar o padrao intradiario
    za = _z_por_hhmm(la, d["hhmm"])
    zv, zr = _z_por_hhmm(lv, d["hhmm"]), _z_por_hhmm(-lr, d["hhmm"])
    m = za.notna() & zv.notna() & zr.notna()
    por_hora: dict[str, Any] = {
        "n": int(m.sum()),
        "corr_z_absorcao_com_z_volume": round(float(np.corrcoef(za[m], zv[m])[0, 1]), 4),
        "corr_z_absorcao_com_z_menos_range": round(float(np.corrcoef(za[m], zr[m])[0, 1]), 4),
        "decil_tambem_em_barra_estreita": _concordancia(za[m], zr[m]),
        "decil_tambem_em_volume_alto": _concordancia(za[m], zv[m]),
    }
    r: dict[str, Any] = {"dump": meta, "barras": len(d), "bruto": bruto,
                         "normalizado_por_horario": por_hora}
    if saida is not None:
        saida.mkdir(parents=True, exist_ok=True)
        (saida / "triagem_absorcao.json").write_text(json.dumps(r, indent=2, default=str),
                                                     encoding="utf-8")
    log.info("triagem_absorcao", barras=len(d),
             fracao_range=bruto["fracao_da_var_vinda_do_range"],
             decil_estreita=bruto["decil_tambem_em_barra_estreita"]["taxa"],
             decil_volume=bruto["decil_tambem_em_volume_alto"]["taxa"])
    return r
