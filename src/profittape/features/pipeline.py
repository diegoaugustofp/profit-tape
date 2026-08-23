"""
Orquestracao: curated -> barras -> features -> z-scores -> labels -> parquet.

STREAMING POR DIA (2026-08-23): a versao original carregava o dataset inteiro
num unico DataFrame — com 21 pregoes (~85M linhas de WINFUT) o pico de memoria
passava de 20 GB e estourou na maquina do operador. Como a barra NAO cruza o
dia por definicao (bars.py), o processamento e' dia a dia sem NENHUMA mudanca
semantica: duas passadas sobre as particoes dt=, memoria limitada a ~1 dia.

  Passada 1 (leve)  : agregados globais — volume de agressao por dia (para o
                      threshold), soma por agente (top-N), tick por dia.
  Passada 2 (plena) : barras + features por dia, com bar_id deslocado para
                      continuar crescente atraves dos dias.

Normalize (z rolante) e labels rodam sobre o dataframe de BARRAS (~100/dia,
minusculo), depois do concat — identico a versao original.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

from . import bars, flow, labels, normalize

COLUNAS_Z = ["imbalance", "tick_imbalance", "absorcao", "rlp_frac"]
_AGRESSAO = (2, 3)
# SEM "dt": o curate nao grava dt como coluna fisica — ele vive so' no
# CAMINHO (particao hive). Ao montar o dataset a partir da pasta do dia,
# dt= e' a raiz e deixa de ser coluna de particao (bug real: ArrowInvalid
# "No match for FieldRef.Name(dt)" na primeira rodada de producao). O dia
# e' derivado do nome da pasta em _carregar_dia.
_COLS = ["ts_ns", "symbol", "trade_id", "price", "quantidade",
         "agente_comprador", "agente_vendedor", "trade_type"]


def _dias_do_symbol(origem: Path, symbol: str) -> list[Path]:
    return sorted(
        p for p in origem.glob("dt=*")
        if (p / f"sym={symbol}").exists()
    )


def _carregar_dia(pasta_dia: Path, symbol: str) -> pd.DataFrame:
    dataset = ds.dataset(pasta_dia, format="parquet", partitioning="hive",
                         exclude_invalid_files=True)
    df = dataset.to_table(
        filter=ds.field("sym") == symbol, columns=_COLS
    ).to_pandas()
    df = df.sort_values("ts_ns", kind="stable").reset_index(drop=True)
    dia = pasta_dia.name.split("=", 1)[1]
    df["dt"] = pd.Categorical([dia] * len(df))
    return df


def gerar(
    curated: Path,
    saida: Path,
    symbol: str,
    volume_barra: int | None = None,
    barras_por_dia: int = 100,
    top_n_agentes: int = 10,
    janela_z: int = 50,
    label_k: float = 2.0,
    label_h: int = 10,
) -> dict:
    origem = curated / "trade"
    dias = _dias_do_symbol(origem, symbol)
    if not dias:
        raise SystemExit(f"nenhum trade de {symbol} em {origem} — rode curate antes")

    # ---- Passada 1: agregados globais, um dia por vez ---------------------
    vol_agr_por_dia: list[float] = []
    soma_agente: dict[int, float] = {}
    tick_por_dia: list[float] = []
    total_trades = 0
    for pasta in dias:
        df = _carregar_dia(pasta, symbol)
        total_trades += len(df)
        agr = df[df["trade_type"].isin(_AGRESSAO)]
        if len(agr):
            vol_agr_por_dia.append(float(agr["quantidade"].sum()))
            for lado in ("agente_comprador", "agente_vendedor"):
                for ag, q in agr.groupby(lado)["quantidade"].sum().items():
                    soma_agente[int(ag)] = soma_agente.get(int(ag), 0.0) + float(q)
            difs = agr["price"].diff().abs()
            positivos = difs[difs > 0]
            if len(positivos):
                tick_por_dia.append(float(positivos.min()))
        del df, agr

    if volume_barra is None:
        # Mesma formula de bars.sugerir_volume_barra, sobre os agregados:
        # mediana do volume diario / alvo, arredondada a 2 algarismos.
        alvo = float(np.median(vol_agr_por_dia)) / barras_por_dia
        if alvo <= 0:
            raise ValueError("sem volume de agressao no dataset")
        magnitude = 10 ** (int(np.floor(np.log10(alvo))) - 1)
        volume_barra = int(round(alvo / magnitude) * magnitude)
    if not tick_por_dia:
        raise ValueError("impossivel inferir tick: sem variacao de preco")
    tick = float(np.median(tick_por_dia))
    agentes = [a for a, _ in sorted(soma_agente.items(),
                                    key=lambda kv: -kv[1])[:top_n_agentes]]

    # ---- Passada 2: barras + features por dia, bar_id continuo ------------
    partes: list[pd.DataFrame] = []
    parciais_total = 0
    offset_bar = 0
    for pasta in dias:
        df = _carregar_dia(pasta, symbol)
        df_barrado, parciais = bars.atribuir_barras(df, volume_barra)
        parciais_total += parciais
        if df_barrado.empty:
            del df, df_barrado
            continue
        barras_dia = flow.calcular(df_barrado, agentes, tick)
        barras_dia["bar_id"] = barras_dia["bar_id"] + offset_bar
        offset_bar = int(barras_dia["bar_id"].max()) + 1
        partes.append(barras_dia)
        del df, df_barrado

    if not partes:
        raise SystemExit("nenhuma barra completa gerada — volume_barra alto demais?")
    barras_df = pd.concat(partes, ignore_index=True)

    colunas_z = COLUNAS_Z + [f"agf_{a}" for a in agentes]
    barras_df = normalize.aplicar(barras_df, colunas_z, janela_z)
    barras_df = labels.triple_barrier(barras_df, k=label_k, h=label_h)

    destino = saida / f"sym={symbol}"
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / "features.parquet"
    barras_df.to_parquet(arquivo, compression="zstd", index=False)

    return {
        "symbol": symbol,
        "trades": total_trades,
        "dias": len(dias),
        "volume_barra": volume_barra,
        "tick_inferido": tick,
        "barras": len(barras_df),
        "barras_parciais_descartadas": parciais_total,
        "agentes_top": agentes,
        "labels": barras_df.loc[barras_df["label_valida"], "label"]
                  .value_counts().to_dict(),
        "ambiguas": int(barras_df["label_ambigua"].sum()),
        "arquivo": str(arquivo),
    }
