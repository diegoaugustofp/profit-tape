"""
Pipeline de features em BARRA DE TEMPO — pre-registro de 2026-08-29e.

Separado de `pipeline.py` de proposito, por instrucao explicita do operador
("a estrategia e' validada em barra de tempo, sem misturar"). A separacao nao
e' cosmetica; ela tem duas consequencias operacionais:

1. SO as tres colunas pre-registradas sao normalizadas (`absorcao_dir`,
   `desloc_norm`, `imbalance`). O `research` avalia TODA coluna `z_` que
   encontrar no arquivo: se este pipeline gerasse o conjunto completo, a
   rodada cobraria 14 features x 2 horizontes = 28 trials por timeframe em
   vez dos 6 pre-registrados — e reintroduziria justamente as features de
   barra de volume que se quer manter fora.
2. Saida em `data/features_tempo/sym=X/tf=Nm/`, nunca sobrescrevendo
   `data/features/`.

JANELA DE Z CASADA EM TEMPO DE RELOGIO, NAO EM BARRAS
-----------------------------------------------------
`janela_minutos` (nao `janela_z`) e' o parametro exposto. Com 250 minutos,
o 5m usa 50 barras e o 1m usa 250 — os dois normalizam contra o MESMO
passado em minutos. Fixar o numero de barras nos dois faria a comparacao
entre timeframes medir passados de duracao diferente, o que a tornaria sem
sentido antes mesmo de olhar o resultado.

STREAMING POR DIA: mesma razao de `pipeline.py` (o dataset inteiro estourou
20 GB na maquina do operador). A barra nao cruza o dia, entao processar dia
a dia nao muda nada semanticamente.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog

from . import bars, flow, normalize
from .pipeline import _carregar_dia, _dias_do_symbol

log = structlog.get_logger(__name__)

# CONGELADAS pelo pre-registro de 2026-08-29e. Ordem: primaria, depois os
# dois controles. Mudar esta lista muda o numero de trials da rodada e
# exige pre-registro novo.
COLUNAS_Z_TEMPO = ["absorcao_dir", "desloc_norm", "imbalance"]

_AGRESSAO = (2, 3)
PERIODOS = {60: "1m", 300: "5m"}


def gerar_tempo(
    curated: Path,
    saida: Path,
    symbol: str,
    segundos: int,
    janela_minutos: int = 250,
) -> dict[str, Any]:
    if segundos not in PERIODOS:
        raise SystemExit(
            f"periodo {segundos}s fora do pre-registro — use "
            f"{sorted(PERIODOS)} (ver docs/RESEARCH_PLANO.md 2026-08-29e)"
        )
    rotulo = PERIODOS[segundos]
    janela_barras = max(2, (janela_minutos * 60) // segundos)

    origem = curated / "trade"
    dias = _dias_do_symbol(origem, symbol)
    if not dias:
        raise SystemExit(f"nenhum trade de {symbol} em {origem} — rode curate antes")

    # ---- Passada 1: tick inferido (mesma regra de sempre) -----------------
    tick_por_dia: list[float] = []
    total_trades = 0
    for i, pasta in enumerate(dias, 1):
        df = _carregar_dia(pasta, symbol)
        total_trades += len(df)
        agr = df[df["trade_type"].isin(_AGRESSAO)]
        difs = agr["price"].diff().abs()
        positivos = difs[difs > 0]
        if len(positivos):
            tick_por_dia.append(float(positivos.min()))
        log.info("features_tempo.tick", passada=1, i=i, n=len(dias),
                 dia=pasta.name, trades=len(df))
        del df, agr
    if not tick_por_dia:
        raise ValueError("impossivel inferir tick: sem variacao de preco")
    tick = float(np.median(tick_por_dia))

    # ---- Passada 2: barras de tempo + features, bar_id continuo -----------
    partes: list[pd.DataFrame] = []
    descartadas_total = 0
    offset_bar = 0
    for i, pasta in enumerate(dias, 1):
        df = _carregar_dia(pasta, symbol)
        df_barrado, descartadas = bars.atribuir_barras_tempo(df, segundos)
        descartadas_total += descartadas
        if df_barrado.empty:
            del df, df_barrado
            continue
        barras_dia = flow.calcular(df_barrado, agentes=[], tick=tick,
                                   incluir_absorcao_dir=True)
        barras_dia["bar_id"] = barras_dia["bar_id"] + offset_bar
        offset_bar = int(barras_dia["bar_id"].max()) + 1
        partes.append(barras_dia)
        log.info("features_tempo.barras", passada=2, i=i, n=len(dias),
                 dia=pasta.name, barras=len(barras_dia))
        del df, df_barrado

    if not partes:
        raise SystemExit("nenhuma barra de tempo gerada")
    barras_df = pd.concat(partes, ignore_index=True)
    barras_df = normalize.aplicar(barras_df, COLUNAS_Z_TEMPO, janela_barras)

    destino = saida / f"sym={symbol}" / f"tf={rotulo}"
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / "features.parquet"
    barras_df.to_parquet(arquivo, compression="zstd", index=False)

    return {
        "symbol": symbol,
        "tf": rotulo,
        "trades": total_trades,
        "dias": len(dias),
        "tick_inferido": tick,
        "barras": len(barras_df),
        "barras_finais_descartadas": descartadas_total,
        "janela_z_barras": janela_barras,
        "janela_z_minutos": janela_minutos,
        "buracos": _contar_buracos(barras_df),
        "range_ticks_mediano": _range_mediano_ticks(barras_df, tick),
        "colunas_z": COLUNAS_Z_TEMPO,
        "arquivo": str(arquivo),
    }


def _contar_buracos(barras: pd.DataFrame) -> int:
    """
    Baldes de tempo sem negocio de agressao — barras que nao existem.

    Reportado, nao corrigido: preencher criaria barra com `range = 0` e
    `vol_agr = 0`, e `desloc_norm` degenerado. O numero importa porque com
    buracos "h barras a frente" deixa de ser exatamente "h periodos a
    frente"; se for grande, o horizonte perde o significado de relogio que
    o pre-registro assume, e isso tem que estar visivel.
    """
    if barras.empty:
        return 0
    ids = barras["bar_id"].to_numpy()
    return int((np.diff(ids) - 1).clip(min=0).sum())


def _range_mediano_ticks(barras: pd.DataFrame, tick: float) -> float:
    """Geometria observada da barra — serve para calibrar o portao de ruido."""
    if barras.empty:
        return float("nan")
    amplitude = (barras["high"] - barras["low"]) / tick
    return float(amplitude.median())
