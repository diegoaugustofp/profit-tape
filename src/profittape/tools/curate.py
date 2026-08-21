"""
Curadoria: data/raw -> data/curated.

POR QUE EXISTE UMA CAMADA SEPARADA
----------------------------------
O raw e' o que a DLL entregou, intocado — inclusive duplicata de reconnect,
edicao de negocio e timestamp que nao parseou. Ele nao se corrige nunca: e' a
evidencia. O curated e' o que pode alimentar feature e backtest. Misturar os
dois ("deduplico na leitura, as vezes") e' como cada notebook acaba com uma
versao ligeiramente diferente do mesmo dado.

O QUE A CURADORIA FAZ — E SO ISSO
---------------------------------
  1. Deduplica por (symbol, trade_id), mantendo a versao de MAIOR ts_recv_ns.
     Edicao de negocio chega depois da original; a ultima versao e' a valida.
  2. Exclui linhas com ts_ns == 0 (parse de data falhou) e CONTA quantas foram.
     Sem timestamp o negocio nao serve para nada temporal — mas a contagem
     alta e' sintoma de bug de parse e precisa gritar, nao sumir.
  3. Ordena por ts_ns e grava um arquivo por (dia, simbolo).

Nada de filtro de trade_type aqui: excluir leilao/RLP e' decisao de FEATURE,
nao de curadoria. O curated preserva tudo que e' valido.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from ..storage.validacao import relatorio


def curar_trades(raiz_raw: Path, raiz_curated: Path) -> dict[str, int]:
    """
    Processa particao por particao de dia — nunca o dataset inteiro em memoria.
    Um mes de WINFUT nao cabe, e nao precisa caber.
    """
    # `to_pandas()` abaixo exige pandas, mas o erro nativo de import dentro do
    # pyarrow e' criptico. Checagem explicita com mensagem de correcao.
    if importlib.util.find_spec("pandas") is None:  # pragma: no cover
        raise SystemExit("curate precisa de pandas: pip install -e '.[dev]'")

    origem = raiz_raw / "trade"
    if not origem.exists():
        raise SystemExit(f"Nao ha dado em {origem}. Rode record ou backfill antes.")

    _corrompidos, inprogress = relatorio(origem)
    if inprogress:
        raise SystemExit(
            "Ha arquivos .inprogress na origem — um recorder/backfill pode estar "
            "rodando. Curar no meio de uma escrita produz curated incompleto que "
            "parece completo. Encerre a captura (ou confirme que e' sobra e "
            "remova) antes de curar."
        )

    totais = {"lidas": 0, "duplicatas": 0, "ts_invalido": 0, "gravadas": 0, "particoes": 0}

    for pasta_dia in sorted(origem.glob("dt=*")):
        dia = pasta_dia.name.split("=", 1)[1]
        tabela = ds.dataset(
            pasta_dia, format="parquet", partitioning="hive",
            exclude_invalid_files=True,
        ).to_table()
        if tabela.num_rows == 0:
            continue
        df = tabela.to_pandas()
        totais["lidas"] += len(df)

        invalidos = int((df["ts_ns"] == 0).sum())
        totais["ts_invalido"] += invalidos
        df = df[df["ts_ns"] > 0]

        antes = len(df)
        df = (
            df.sort_values("ts_recv_ns")
              .drop_duplicates(subset=["symbol", "trade_id"], keep="last")
              .sort_values("ts_ns", kind="stable")
        )
        totais["duplicatas"] += antes - len(df)

        for sym, grupo in df.groupby("symbol", observed=True):
            destino = raiz_curated / "trade" / f"dt={dia}" / f"sym={sym}"
            destino.mkdir(parents=True, exist_ok=True)
            # dt e sym vivem no CAMINHO (hive). Duplica-los dentro do arquivo
            # cria conflito de merge na leitura do dataset quando o tipo da
            # coluna difere do inferido da particao (string vs large_string —
            # varia com a versao do pandas). A particao e' a dona dessas duas.
            pq.write_table(
                pa.Table.from_pandas(grupo.drop(columns=["sym", "dt"], errors="ignore"),
                                     preserve_index=False),
                destino / "part-0000.parquet",
                compression="zstd",
            )
            totais["gravadas"] += len(grupo)
        totais["particoes"] += 1

    return totais


def imprimir_relatorio(t: dict[str, int]) -> None:
    print("=" * 60)
    print("CURADORIA raw -> curated")
    print("=" * 60)
    print(f"  particoes de dia    : {t['particoes']}")
    print(f"  linhas lidas        : {t['lidas']:,}")
    print(f"  duplicatas removidas: {t['duplicatas']:,}")
    print(f"  ts invalido excluido: {t['ts_invalido']:,}")
    print(f"  linhas gravadas     : {t['gravadas']:,}")
    if t["lidas"]:
        if t["ts_invalido"] / t["lidas"] > 0.001:
            print("\n  ALERTA: mais de 0,1% com timestamp invalido. Isso e' bug de")
            print("  parse de data (timeparse.py x formato da sua DLL), nao ruido.")
        if t["duplicatas"] / t["lidas"] > 0.10:
            print("\n  NOTA: mais de 10% de duplicata sugere reentrega macica —")
            print("  reconnect no meio da sessao ou backfill sobreposto a gravacao.")
    print("=" * 60)
