"""Orquestracao: curated -> barras -> features -> z-scores -> labels -> parquet."""

from __future__ import annotations

from pathlib import Path

import pyarrow.dataset as ds

from . import bars, flow, labels, normalize

COLUNAS_Z = ["imbalance", "tick_imbalance", "absorcao", "rlp_frac"]


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
    dataset = ds.dataset(origem, format="parquet", partitioning="hive",
                         exclude_invalid_files=True)
    tabela = dataset.to_table(
        filter=ds.field("sym") == symbol,
        columns=["ts_ns", "symbol", "trade_id", "price", "quantidade",
                 "agente_comprador", "agente_vendedor", "trade_type", "dt"],
    )
    if tabela.num_rows == 0:
        raise SystemExit(f"nenhum trade de {symbol} em {origem} — rode curate antes")
    df = tabela.to_pandas()

    if volume_barra is None:
        volume_barra = bars.sugerir_volume_barra(df, barras_por_dia)
    tick = bars.inferir_tick(df)
    df_barrado, parciais = bars.atribuir_barras(df, volume_barra)

    agentes = flow.top_agentes(df_barrado, top_n_agentes)
    barras_df = flow.calcular(df_barrado, agentes, tick)
    colunas_z = COLUNAS_Z + [f"agf_{a}" for a in agentes]
    barras_df = normalize.aplicar(barras_df, colunas_z, janela_z)
    barras_df = labels.triple_barrier(barras_df, k=label_k, h=label_h)

    destino = saida / f"sym={symbol}"
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / "features.parquet"
    barras_df.to_parquet(arquivo, compression="zstd", index=False)

    return {
        "symbol": symbol,
        "trades": len(df),
        "volume_barra": volume_barra,
        "tick_inferido": tick,
        "barras": len(barras_df),
        "barras_parciais_descartadas": parciais,
        "agentes_top": agentes,
        "labels": barras_df.loc[barras_df["label_valida"], "label"]
                  .value_counts().to_dict(),
        "ambiguas": int(barras_df["label_ambigua"].sum()),
        "arquivo": str(arquivo),
    }
