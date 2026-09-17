"""
AJUSTE E FECHAMENTO — descricao (passo 1, 2026-09-17).

CONTRAPARTE: o preco de AJUSTE do WIN sai da media ponderada dos negocios
no fim do pregao. Quem tem posicao aberta tem consequencia financeira
IMEDIATA (margem) no ajuste -- e quem opera day trade e' obrigado a zerar
antes do fim, queira ou nao o preco. Os dois sao fluxo que nao escolhe
preco, e -- diferente da rolagem, que se espalha por dias e morreu no
passo 1 -- este se concentra numa JANELA ESTREITA do dia. Era o proximo
candidato natural.

ESTE MODULO NAO E' UMA FICHA. Mede se a marca existe. Categoria
`features`, zero trial.

O QUE MEDE -- e o que NAO mede
------------------------------
Por BARRA do fim do pregao: fracao do volume do dia, amplitude e
|retorno| relativos a` barra mediana daquele dia, e a estabilidade disso
por ano. Comparacao com a primeira hora (o outro extremo do dia).
**Nao mede direcao.** A hipotese obvia ("distorcao no fechamento reverte
na abertura seguinte") exige retorno com SINAL e so' se escreve no passo
2, em ficha, com a contraparte acima e criterio declarado.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from .eas_preco import TICK_WIN, carregar_log, indicadores

log = structlog.get_logger(__name__)

BARRAS_FINAIS = 8          # ~2 h de M15
BARRAS_INICIAIS = 4        # a primeira hora, para contraste


def descrever(dump: Path, saida: Path | None = None) -> dict[str, Any]:
    df, meta = carregar_log(dump)
    d = indicadores(df).copy()
    d["amplitude_ticks"] = (d["high"] - d["low"]) / TICK_WIN
    d["retorno_abs_ticks"] = (d["close"] - d["open"]).abs() / TICK_WIN
    d["ano"] = pd.to_datetime(d["dia"].astype(str)).dt.year

    por_dia = d.groupby("dia").agg(vol_dia=("vol_total", "sum"),
                                   ampl_med=("amplitude_ticks", "median"),
                                   ret_med=("retorno_abs_ticks", "median"),
                                   n_barras=("close", "size")).reset_index()
    d = d.merge(por_dia, on="dia")
    d = d[d["n_barras"] >= 30]                     # dia cheio (pregao completo)
    d["frac_vol"] = d["vol_total"] / d["vol_dia"].replace(0, pd.NA)
    d["ampl_rel"] = d["amplitude_ticks"] / d["ampl_med"].replace(0, pd.NA)
    d["ret_rel"] = d["retorno_abs_ticks"] / d["ret_med"].replace(0, pd.NA)
    # posicao da barra dentro do dia, contada do FIM (0 = ultima)
    d = d.sort_values(["dia", "current_bar"])
    d["do_fim"] = d.groupby("dia").cumcount(ascending=False)
    d["do_inicio"] = d.groupby("dia").cumcount()

    def perfil(col: str, ate: int, campo: str) -> dict[str, Any]:
        out = {}
        for k in range(ate):
            sub = d[d[col] == k]
            if sub.empty:
                continue
            out[str(k)] = {
                "n": len(sub),
                "hhmm_p50": int(sub["hhmm"].median()),
                "frac_vol_p50": round(float(sub["frac_vol"].median()), 4),
                "ampl_rel_p50": round(float(sub["ampl_rel"].median()), 3),
                "ret_rel_p50": round(float(sub[campo].median()), 3),
            }
        return out

    fim = perfil("do_fim", BARRAS_FINAIS, "ret_rel")
    inicio = perfil("do_inicio", BARRAS_INICIAIS, "ret_rel")
    # concentracao: fracao do volume do dia nas 2 e nas 4 ultimas barras
    conc: dict[str, float] = {}
    for k in (2, 4):
        sub = d[d["do_fim"] < k].groupby("dia")["frac_vol"].sum()
        conc[f"ultimas_{k}_barras"] = round(float(sub.median()), 4)
        conc[f"ultimas_{k}_barras_uniforme"] = round(k / float(por_dia["n_barras"].median()), 4)
    # estabilidade por ano da concentracao nas 2 ultimas
    por_ano: dict[str, Any] = {}
    duas = d[d["do_fim"] < 2].groupby(["ano", "dia"])["frac_vol"].sum().reset_index()
    for ano in sorted(duas["ano"].unique()):
        sub_ano = duas[duas["ano"] == ano]
        mediana = round(float(sub_ano["frac_vol"].median()), 4)
        por_ano[str(ano)] = {"pregoes": len(sub_ano), "frac_vol_2_ultimas_p50": mediana}

    r = {"dump": meta, "barras_por_dia_p50": int(por_dia["n_barras"].median()),
         "perfil_do_fim": fim, "perfil_do_inicio": inicio,
         "concentracao": conc, "por_ano_2_ultimas": por_ano}
    if saida is not None:
        saida.mkdir(parents=True, exist_ok=True)
        (saida / "fechamento.json").write_text(json.dumps(r, indent=2, default=str),
                                               encoding="utf-8")
    log.info("fechamento.descrito", pregoes=int(por_dia["dia"].nunique()),
             conc_2=conc.get("ultimas_2_barras"),
             uniforme_2=conc.get("ultimas_2_barras_uniforme"))
    return r
