"""
Auditoria do dado gravado.

Mesma filosofia do seu data_audit.py: mede o DADO, nao a estrategia. A pergunta
que responde e' "posso confiar nesta particao?", e ela precisa ser respondida
ANTES de qualquer feature ser calculada em cima.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds

from ..domain.enums import TradeType
from ..profitdll.timeparse import formatar
from ..storage.validacao import relatorio


def _agrupar_contando(tabela: pa.Table, coluna: str) -> list[dict]:
    """
    Contagem por coluna, robusta a dicionarios divergentes.

    Arquivos Parquet distintos carregam dicionarios distintos para a mesma
    coluna. `group_by` sobre isso levanta `ArrowNotImplementedError: Unifying
    differing dictionaries` — falha que so aparece quando ha MAIS DE UM arquivo,
    ou seja, nunca no teste pequeno e sempre no dado real.
    """
    col = tabela[coluna]
    if pa.types.is_dictionary(col.type):
        tabela = tabela.set_column(
            tabela.column_names.index(coluna), coluna, col.cast(pa.string())
        )
    return tabela.group_by(coluna).aggregate([([], "count_all")]).to_pylist()


def resumir(caminho: Path, stream: str = "trade") -> None:
    candidato = caminho / stream
    if candidato.exists():
        alvo = candidato
    elif any(caminho.glob("dt=*")):
        alvo = caminho          # o proprio caminho ja e' um diretorio de stream
    else:
        # Incidente real: o fallback silencioso auditou data/raw INTEIRO —
        # trade+book+tiny unificados numa tabela sem sentido — e o usuario
        # levou um relatorio errado sem nenhum aviso. Mistura silenciosa e'
        # pior que erro: agora falha listando o que existe.
        disponiveis = (
            sorted(d.name for d in caminho.iterdir() if d.is_dir())
            if caminho.exists() else []
        )
        raise SystemExit(
            f"stream '{stream}' nao encontrado em {caminho}. "
            f"Diretorios disponiveis: {disponiveis or '(nenhum)'}"
        )

    corrompidos, _ = relatorio(alvo)
    extras = {"exclude_invalid_files": True} if corrompidos else {}
    dataset = ds.dataset(alvo, format="parquet", partitioning="hive", **extras)
    # So as colunas que o resumo usa: numa arvore de milhoes de linhas, carregar
    # price/quantidade/flags que ninguem le e' o que tornava o inspect lento —
    # junto com a dupla varredura de footer (exclude_invalid_files repete a
    # validacao; agora so entra quando a varredura achou podre).
    desejadas = [c for c in ("ts_ns", "ts_recv_ns", "symbol", "trade_type",
                             "trade_id", "agente_comprador", "agente_vendedor", "dt")
                 if c in dataset.schema.names]
    tabela = dataset.to_table(columns=desejadas)
    n = tabela.num_rows

    print("=" * 78)
    print(f"AUDITORIA — {alvo}")
    print("=" * 78)
    print(f"  linhas            : {n:,}")
    if n == 0:
        print("  particao vazia.")
        return

    col_ts = "ts_ns" if "ts_ns" in tabela.column_names else "ts_recv_ns"
    ts = tabela[col_ts]
    print(f"  primeiro evento   : {formatar(pc.min(ts).as_py())}")
    print(f"  ultimo evento     : {formatar(pc.max(ts).as_py())}")

    if "ts_ns" in tabela.column_names:
        invalidos = pc.sum(pc.equal(tabela["ts_ns"], 0)).as_py() or 0
        if invalidos:
            print(f"  TIMESTAMP INVALIDO: {invalidos:,} ({invalidos/n:.2%}) — parse falhou;")
            print("                      confira o formato de data da sua versao da DLL.")

    # Latencia do feed: quanto tempo entre o evento acontecer e chegar aqui.
    if "ts_ns" in tabela.column_names and "ts_recv_ns" in tabela.column_names:
        validos = tabela.filter(pc.greater(tabela["ts_ns"], 0))
        if validos.num_rows:
            lat_ms = pc.divide(
                pc.subtract(validos["ts_recv_ns"], validos["ts_ns"]), 1_000_000.0
            )
            p50 = pc.approximate_median(lat_ms).as_py()
            if p50 < 0:
                # Recebido ANTES de acontecer e' impossivel. Significa que o
                # timestamp do evento e o relogio local discordam — quase sempre
                # `tz_offset_horas` errado no config, ou relogio da maquina fora
                # de sincronia. Qualquer analise que junte os dois vai errar.
                print(f"  latencia feed p50 : {p50:,.0f} ms  <-- NEGATIVA, IMPOSSIVEL")
                print("      Confira runtime.tz_offset_horas e o relogio da maquina.")
            elif p50 > 3_600_000:
                # Backfill: ts_recv e' de agora, o evento e' do passado. A
                # "latencia" vira idade do dado e nao diz nada sobre o feed.
                print(f"  idade do dado p50 : {p50 / 3_600_000:,.1f} h (backfill; "
                      f"latencia de feed nao se aplica)")
            elif p50 > 5_000:
                print(f"  latencia feed p50 : {p50:,.0f} ms  <-- alta demais, investigar")
            else:
                print(f"  latencia feed p50 : {p50:.1f} ms")

    if "symbol" in tabela.column_names:
        print("\n  por simbolo:")
        for row in _agrupar_contando(tabela, "symbol"):
            print(f"    {row['symbol']:<12} {row['count_all']:>12,}")

    if "trade_type" in tabela.column_names:
        print("\n  por tipo de negocio:")
        continuo = 0
        for row in sorted(_agrupar_contando(tabela, "trade_type"), key=lambda r: -r["count_all"]):
            codigo = row["trade_type"]
            try:
                nome = TradeType(codigo).name
                if TradeType(codigo).is_agressao_continua:
                    continuo += row["count_all"]
            except ValueError:
                nome = "*** CODIGO DESCONHECIDO ***"
            print(f"    {codigo:>4} {nome:<24} {row['count_all']:>12,}")
        print(f"\n  agressao em mercado continuo: {continuo:,} ({continuo/n:.1%})")
        print("  (o resto — leilao, RLP, balcao — deve ser excluido do calculo de OFI)")

    if "agente_comprador" in tabela.column_names:
        # O gate do Tier 1: sem identificacao de corretora nao ha estrategia
        # de fluxo por agente. Medimos preenchimento e concentracao.
        n_validos = tabela.num_rows
        zer_c = pc.sum(pc.equal(tabela["agente_comprador"], 0)).as_py() or 0
        zer_v = pc.sum(pc.equal(tabela["agente_vendedor"], 0)).as_py() or 0
        print("\n  identificacao de corretora (agente):")
        print(f"    comprador preenchido : {1 - zer_c / n_validos:.1%}")
        print(f"    vendedor  preenchido : {1 - zer_v / n_validos:.1%}")
        distintos = pc.count_distinct(tabela["agente_comprador"]).as_py()
        print(f"    agentes distintos    : {distintos}")
        top = sorted(_agrupar_contando(tabela, "agente_comprador"),
                     key=lambda r: -r["count_all"])[:5]
        print("    top 5 compradores    : "
              + ", ".join(f"{r['agente_comprador']}({r['count_all']:,})" for r in top))
        if zer_c / n_validos > 0.5:
            print("    ATENCAO: maioria sem identificacao — fluxo por corretora")
            print("    fica inviavel nesta conta/segmento. Confirme no manual se o")
            print("    campo e' disseminado para o seu perfil.")

    if "trade_id" in tabela.column_names:
        # A sequencia de trade_id reinicia POR SIMBOLO E POR DIA. Duas camadas
        # de falso positivo ja cairam aqui: contar globalmente acusou colisao
        # entre simbolos (621.412 num pregao), e contar por (symbol, trade_id)
        # acusou colisao entre DIAS (214.349 — os ids de hoje dentro da faixa
        # de ontem). A chave de unicidade e' (symbol, dt, trade_id) — a mesma
        # que o curate sempre usou, por deduplicar dentro da particao de dia.
        nomes = ["symbol", "trade_id"] + (["dt"] if "dt" in tabela.column_names else [])
        chaves = tabela.select(nomes)
        for idx, nome in enumerate(nomes):
            col = chaves[nome]
            if pa.types.is_dictionary(col.type):
                chaves = chaves.set_column(idx, nome, col.cast(pa.string()))
        distintos = chaves.group_by(nomes).aggregate([]).num_rows
        repetidos = n - distintos
        if repetidos:
            print(f"\n  ATENCAO: {repetidos:,} chaves {tuple(nomes)} repetidas.")
            print("  Pode ser edicao de negocio (is_edit) ou reentrega no reconnect.")
            print("  O curate deduplica mantendo a versao de maior ts_recv.")
        else:
            print(f"\n  trade_id: sem duplicidade por {tuple(nomes)}.")
    print("=" * 78)
