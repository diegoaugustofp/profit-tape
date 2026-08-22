"""
Diagnostico de trade_id repetido: edicao de negocio x reentrega benigna.

CONTEXTO (2026-08-22): o inspect acusou 50% de chaves (symbol, dt, trade_id)
repetidas num UNICO dia de um UNICO simbolo — nao e' mistura de dias. O
callback de historico V1 (THistoryTradeCallback) NAO traz o flag TC_IS_EDIT
que o V2 (TConnectorTradeCallback) traria, entao no V1 uma edicao de negocio
chega como um segundo evento indistinguivel do original.

A pergunta que esta ferramenta responde, com DADO e nao suposicao: quando um
trade_id se repete no mesmo dia, os campos (preco, qtd, agentes, tipo) DIFEREM
entre as ocorrencias?
  - DIFEREM  -> sao edicoes reais; precisamos do callback V2 para saber qual e'
               a versao corrigida, e o curate nao pode deduplicar as cegas.
  - IDENTICOS -> e' reentrega benigna; o curate pode manter qualquer uma.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds


def _carregar_dia(raiz: Path, symbol: str, dia: str | None) -> pa.Table:
    alvo = raiz / "trade"
    arquivos = [
        str(p) for p in alvo.rglob("*.parquet")
        if not p.name.endswith(".inprogress")
        and f"sym={symbol}" in str(p)
        and (dia is None or f"dt={dia}" in str(p))
    ]
    if not arquivos:
        raise SystemExit(
            f"nenhum arquivo para symbol={symbol}"
            + (f" dia={dia}" if dia else "")
            + f" em {alvo.resolve()}"
        )
    dataset = ds.dataset(
        arquivos, format=ds.ParquetFileFormat(),
        partitioning=ds.partitioning(flavor="hive"),
    )
    return dataset.to_table()


def diagnosticar(raiz: Path, symbol: str, dia: str | None = None,
                 amostras: int = 10) -> None:
    """
    Acha trade_ids repetidos e mostra as ocorrencias lado a lado, classificando
    cada par como IDENTICO (reentrega) ou DIFERE (edicao real).
    """
    tabela = _carregar_dia(raiz, symbol, dia)
    n = tabela.num_rows
    print(f"Carregado: {n:,} linhas de {symbol}" + (f" em {dia}" if dia else ""))

    # Contar ocorrencias por (dt, trade_id) — dentro do dia, trade_id e' a chave.
    chave_cols = ["trade_id"] + (["dt"] if "dt" in tabela.column_names else [])
    for c in chave_cols:
        if pa.types.is_dictionary(tabela[c].type):
            idx = tabela.column_names.index(c)
            tabela = tabela.set_column(idx, c, tabela[c].cast(pa.string()))

    grupos = tabela.group_by(chave_cols).aggregate([("trade_id", "count")])
    contagem_col = grupos["trade_id_count"]
    repetidos_mask = pc.greater(contagem_col, 1)
    n_repetidos = pc.sum(pc.cast(repetidos_mask, pa.int64())).as_py() or 0

    total_linhas_dup = (
        pc.sum(pc.filter(contagem_col, repetidos_mask)).as_py() or 0
    )
    print(f"trade_ids que se repetem: {n_repetidos:,}")
    print(f"linhas envolvidas em repeticao: {total_linhas_dup:,} "
          f"({total_linhas_dup / n:.1%} do dia)\n")

    if n_repetidos == 0:
        print("Nenhuma repeticao — nada a diagnosticar.")
        return

    # Pega os primeiros trade_ids repetidos para inspecao lado a lado.
    ids_repetidos = pc.filter(grupos["trade_id"], repetidos_mask)
    campos = ["price", "quantidade", "agente_comprador", "agente_vendedor",
              "trade_type", "volume_financeiro", "ts_ns", "ts_recv_ns"]
    campos = [c for c in campos if c in tabela.column_names]

    identicos = 0
    diferentes = 0
    exemplos_mostrados = 0

    for i in range(min(len(ids_repetidos), 2000)):  # varre ate' 2000 p/ estatistica
        tid = ids_repetidos[i].as_py()
        sub = tabela.filter(pc.equal(tabela["trade_id"], ids_repetidos[i]))
        if sub.num_rows < 2:
            continue

        # Compara os campos-chave entre as ocorrencias.
        difere = False
        for campo in campos:
            if campo in ("ts_recv_ns",):   # ts_recv sempre difere (momento de captura)
                continue
            valores = sub[campo].to_pylist()
            if len(set(valores)) > 1:
                difere = True
                break

        if difere:
            diferentes += 1
        else:
            identicos += 1

        # Mostra os primeiros N como exemplo visual.
        if exemplos_mostrados < amostras:
            exemplos_mostrados += 1
            marca = "DIFERE (edicao?)" if difere else "IDENTICO (reentrega)"
            print(f"── trade_id {tid}  [{marca}] ──")
            for campo in campos:
                valores = sub[campo].to_pylist()
                mudou = len(set(valores)) > 1 and campo != "ts_recv_ns"
                distintos = "  <<< DIFERE" if mudou else ""
                print(f"    {campo:20}: {valores}{distintos}")
            print()

    total = identicos + diferentes
    print("=" * 60)
    print(f"VEREDITO (amostra de {total:,} pares repetidos):")
    print(f"  IDENTICOS (reentrega benigna) : {identicos:,} ({identicos/total:.1%})")
    print(f"  DIFEREM   (edicao de negocio) : {diferentes:,} ({diferentes/total:.1%})")
    print("=" * 60)
    if diferentes > identicos:
        print("PREDOMINA EDICAO: o callback V1 nao distingue original de editado.")
        print("Recomendado migrar para SetHistoryTradeCallbackV2 (flag TC_IS_EDIT)")
        print("antes de tratar essas linhas como fluxo — senao OFI/volume/agentes")
        print("ficam inflados e o curate deduplica sem saber qual versao manter.")
    elif identicos > 0 and diferentes == 0:
        print("TUDO REENTREGA: os pares sao identicos byte a byte (menos ts_recv).")
        print("O curate pode deduplicar com seguranca mantendo qualquer ocorrencia.")
    else:
        print("MISTO: ha reentrega e edicao. A presenca de QUALQUER edicao ja'")
        print("justifica o V2 para nao deduplicar as cegas.")
