"""
Perfil de volume por faixa horaria -- para a regra de horario do scalp.

POR QUE EXISTE
--------------
O operador (2026-09-05) limitou as entradas do scalp de Bollinger a ate'
13h porque "a estrategia precisa de volume", e pediu: "se tiver uma
metrica de volume por horario seria melhor; senao fixa as 13h".

Este modulo MEDE o perfil; nao escolhe o corte. A regra de horario e'
declarada pelo operador, em cima destes numeros, ANTES de qualquer
replay que olhe resultado -- escolher o corte olhando retorno seria
calibrar a' amostra. Categoria `features`: zero trial.

O QUE MEDE, POR FAIXA DE `minutos` (default 30) E POR PREGAO
-------------------------------------------------------------
- contratos      : soma de `quantidade` dos negocios de AGRESSAO
                   (trade_type 2 e 3; RLP e leilao fora, como no resto
                   do projeto)
- negocios       : numero de negocios de agressao
- por_barra_15s  : negocios por barra de 15s (negocios / (minutos*4)).
                   E' a metrica que importa para um scalp de 15s: uma
                   barra com 3 negocios nao tem OHLC que mereca o nome.
- pct_do_dia     : fracao do volume do pregao que caiu na faixa
- pct_da_abertura: contratos da faixa / contratos da PRIMEIRA faixa
                   completa do dia -- a metrica que o operador pode usar
                   numa regra do tipo "opera enquanto >= X% da abertura"

O agregado entre pregoes e' a MEDIANA (um dia de vencimento ou de
evento nao pode puxar o perfil).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from ..features.pipeline import _carregar_dia, _dias_do_symbol

log = structlog.get_logger(__name__)

_AGRESSAO = (2, 3)
_NS_POR_S = 1_000_000_000


def perfil_de_um_dia(df: pd.DataFrame, minutos: int = 30,
                     tz_offset_horas: int = -3) -> pd.DataFrame:
    """
    `df` = negocios de UM pregao (colunas ts_ns, quantidade, trade_type).
    `ts_ns` e' epoch UTC; a faixa e' em hora LOCAL (B3 = UTC-3).
    """
    if minutos <= 0 or 60 % minutos != 0:
        raise ValueError("minutos deve dividir 60")
    agr = df[df["trade_type"].isin(_AGRESSAO)]
    if agr.empty:
        return pd.DataFrame(columns=["faixa", "contratos", "negocios",
                                     "por_barra_15s", "pct_do_dia",
                                     "pct_da_abertura"])
    seg_local = (agr["ts_ns"] // _NS_POR_S + tz_offset_horas * 3600) % 86400
    faixa_idx = seg_local // (minutos * 60)
    g = agr.groupby(faixa_idx)
    out = pd.DataFrame({
        "contratos": g["quantidade"].sum().astype(float),
        "negocios": g.size().astype(float),
    })
    out.index.name = "faixa_idx"
    out = out.reset_index()
    ini = out["faixa_idx"] * minutos
    out["faixa"] = (ini // 60).astype(int).astype(str).str.zfill(2) + ":" + \
                   (ini % 60).astype(int).astype(str).str.zfill(2)
    out["por_barra_15s"] = out["negocios"] / (minutos * 4)
    total = float(out["contratos"].sum())
    out["pct_do_dia"] = out["contratos"] / total if total > 0 else 0.0
    # Primeira faixa COMPLETA: a faixa em que o pregao abre pode ser
    # parcial (abertura 9:00 numa faixa 9:00 e' completa; abertura 9:05
    # numa faixa de 30 min nao e'). Se o primeiro negocio cai no inicio
    # da faixa (ate' 1/10 dela), consideramos completa; senao a proxima.
    primeiro_seg = int(seg_local.min())
    ini_faixa0 = int(out["faixa_idx"].iloc[0]) * minutos * 60
    completa0 = (primeiro_seg - ini_faixa0) <= (minutos * 60) // 10
    ref_pos = 0 if completa0 or len(out) == 1 else 1
    ref = float(out["contratos"].iloc[ref_pos])
    out["pct_da_abertura"] = out["contratos"] / ref if ref > 0 else 0.0
    return out[["faixa", "contratos", "negocios", "por_barra_15s",
                "pct_do_dia", "pct_da_abertura"]]


def perfil(curated: Path, symbol: str, minutos: int = 30,
           tz_offset_horas: int = -3) -> dict[str, Any]:
    origem = curated / "trade"
    dias = _dias_do_symbol(origem, symbol)
    if not dias:
        raise SystemExit(f"nenhum pregao de {symbol} em {origem}")
    partes = []
    for i, pasta in enumerate(dias, 1):
        dia = pasta.name.split("=", 1)[1]
        log.info("perfil_volume.pregao", i=i, n=len(dias), dia=dia)
        df = _carregar_dia(pasta, symbol)
        p = perfil_de_um_dia(df, minutos, tz_offset_horas)
        p["dia"] = dia
        partes.append(p)
    por_dia = pd.concat(partes, ignore_index=True)
    cols = ["contratos", "negocios", "por_barra_15s", "pct_do_dia",
            "pct_da_abertura"]
    mediana = (por_dia.groupby("faixa")[cols].median()
               .reset_index().sort_values("faixa").reset_index(drop=True))
    mediana["pregoes"] = por_dia.groupby("faixa").size().reindex(mediana["faixa"]).to_numpy()
    return {"por_dia": por_dia, "mediana": mediana, "pregoes": len(dias),
            "minutos": minutos, "symbol": symbol}
