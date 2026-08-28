"""
Auditoria do dado gravado.

Mesma filosofia do seu data_audit.py: mede o DADO, nao a estrategia. A pergunta
que responde e' "posso confiar nesta particao?", e ela precisa ser respondida
ANTES de qualquer feature ser calculada em cima.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds

from ..domain.enums import TradeType
from ..profitdll.timeparse import formatar
from ..storage.validacao import relatorio


def _agrupar_contando(tabela: pa.Table, coluna: str) -> list[dict[str, Any]]:
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
    return cast(list[dict[str, Any]],
               tabela.group_by(coluna).aggregate([([], "count_all")]).to_pylist())


def _msg(texto: str) -> None:
    """print com flush: sem isto, output fica preso em buffer e o comando
    parece travado durante etapas longas (achado real: usuario sem certeza
    se o inspect estava rodando)."""
    print(texto, flush=True)


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

    # Caminho RESOLVIDO e absoluto: um caminho relativo aqui e' a origem mais
    # provavel de auditar o diretorio ERRADO quando storage.raiz muda (ex.:
    # dado movido para outro volume). Incidente real: apos mover a captura
    # para G:\data\raw, `inspect data/raw` continuou lendo o C:\...\data\raw
    # antigo, esquecido, e devolveu um relatorio de dado JA CORRIGIDO parecendo
    # o incidente antigo — sem erro, sem aviso, so' silenciosamente errado.
    _msg(f"Escaneando arquivos parquet em {alvo.resolve()} ...")
    corrompidos, _ = relatorio(alvo)
    # ds.dataset varre QUALQUER arquivo no diretorio, inclusive os
    # .parquet.inprogress (escrita interrompida) — o relatorio acima ja os
    # detecta e avisa, mas o pyarrow tenta le-los como parquet e morre com
    # "magic bytes not found". Incidente real: sobras dos dias interrompidos
    # por Ctrl+C duplo travaram o inspect inteiro. A defesa: enumerar so' os
    # .parquet exatos e montar o dataset a partir dessa lista, nunca do
    # diretorio cru (a particao hive dt=/sym= ainda e' inferida do caminho).
    arquivos_validos = [
        str(p) for p in alvo.rglob("*.parquet")
        if not p.name.endswith(".inprogress")
    ]
    if not arquivos_validos:
        raise SystemExit(
            f"nenhum arquivo .parquet finalizado em {alvo.resolve()} "
            f"(apenas .inprogress? rode `curate` ou remova as sobras)"
        )
    dataset = ds.dataset(
        arquivos_validos,
        format=ds.ParquetFileFormat(),
        partitioning=ds.partitioning(flavor="hive"),
        exclude_invalid_files=bool(corrompidos),
    )
    n_arquivos = len(list(dataset.files))
    _msg(f"Carregando {n_arquivos} arquivo(s)...")
    # So as colunas que o resumo usa: numa arvore de milhoes de linhas, carregar
    # price/quantidade/flags que ninguem le e' o que tornava o inspect lento —
    # junto com a dupla varredura de footer (exclude_invalid_files repete a
    # validacao; agora so entra quando a varredura achou podre).
    desejadas = [c for c in ("ts_ns", "ts_recv_ns", "symbol", "trade_type",
                             "trade_id", "agente_comprador", "agente_vendedor",
                             "has_date", "dt")
                 if c in dataset.schema.names]
    # to_table sobre a arvore inteira assume schema uniforme — inferido do
    # PRIMEIRO arquivo. Incidente real: 19 dias vindos de rodadas diferentes
    # (backfill de hoje + sobras da rodada interrompida) podem ter schema
    # sutilmente divergente (coluna a mais/menos, tipo diferente), e ai o
    # to_table morre com um traceback cru no meio de 100 arquivos, sem dizer
    # QUAL arquivo. Lemos fragmento a fragmento: o que casa entra, o que
    # diverge e' reportado por nome e pulado — auditoria nao pode morrer por
    # causa de um arquivo torto entre noventa e nove sadios.
    fragmentos_ok = []
    problemas: list[tuple[str, str]] = []
    import re as _re

    import pyarrow as _pa
    for frag in dataset.get_fragments():
        try:
            # Cada fragmento pode ter schema proprio (rodadas diferentes). Pede
            # so' as colunas que ELE tem, entre as desejadas — evita derrubar o
            # arquivo inteiro por causa de uma coluna ausente (has_date/
            # trade_type surgiram em versoes diferentes do gravador).
            cols_frag = frag.physical_schema.names
            pedir = [c for c in desejadas if c in cols_frag]
            t = frag.to_table(columns=pedir)
            # 'dt' e 'sym' vem do CAMINHO (particao hive), nao do arquivo — ao
            # ler fragmento a fragmento eles nao se materializam sozinhos.
            # Recupera 'dt' do path para as estatisticas por dia funcionarem.
            if "dt" in desejadas and "dt" not in t.column_names:
                m = _re.search(r"dt=([0-9-]+)", frag.path)
                if m:
                    t = t.append_column(
                        "dt", _pa.array([m.group(1)] * t.num_rows, _pa.string())
                    )
            fragmentos_ok.append(t)
        except Exception as exc:
            problemas.append((frag.path, type(exc).__name__ + ": " + str(exc)[:120]))
    if problemas:
        print(f"\n  ATENCAO: {len(problemas)} arquivo(s) ilegiveis, PULADOS:")
        for caminho_arquivo, erro in problemas[:10]:
            print(f"    {caminho_arquivo}\n      -> {erro}")
        if len(problemas) > 10:
            print(f"    ... e mais {len(problemas) - 10}.")
        print("  (arquivo corrompido na interrupcao. Mova para quarentena ou "
              "remova a particao do dia e re-rode o backfill dela.)")
    if not fragmentos_ok:
        raise SystemExit("nenhum arquivo legivel apos filtrar os problematicos.")
    tabela = _pa.concat_tables(fragmentos_ok, promote_options="permissive")
    n = tabela.num_rows
    _msg(f"Carregado. Calculando estatisticas sobre {n:,} linhas...\n")

    print("=" * 78)
    print(f"AUDITORIA — {alvo.resolve()}")
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
        if invalidos and "has_date" in tabela.column_names:
            # book_offer: ts_ns=0 e' predominantemente DESIGN (bHasDate=False
            # no evento, manual), nao erro de parse — a maioria dos deltas de
            # livro nao carrega data propria. Distinguir evita alarme falso
            # numa situacao normal e esperada.
            sem_data_flag = pc.sum(pc.equal(tabela["has_date"], False)).as_py() or 0
            print(f"  sem data por evento : {sem_data_flag:,} ({sem_data_flag/n:.1%}) "
                  f"— normal para deltas de book (bHasDate=False); use ts_recv_ns")
            inexplicados = invalidos - sem_data_flag
            if inexplicados > 0:
                print(f"  TIMESTAMP INVALIDO : {inexplicados:,} SEM has_date=False "
                      f"correspondente — isso sim e' parse falhando, investigar.")
        elif invalidos:
            print(f"  TIMESTAMP INVALIDO: {invalidos:,} ({invalidos/n:.2%}) — parse falhou;")
            print("                      confira o formato de data da sua versao da DLL.")

    # Latencia do feed: quanto tempo entre o evento acontecer e chegar aqui.
    if "ts_ns" in tabela.column_names and "ts_recv_ns" in tabela.column_names:
        # ts_ns==0 e' a sentinela de parse-falhou. Mas existe uma SEGUNDA
        # classe de invalido, descoberta em producao: um pacote atFullBook
        # (agora descartado na origem, ver profitdll/client.py) gravava um
        # timestamp PEQUENO MAS NAO-ZERO — memoria obsoleta lida como se
        # fosse data valida, produzindo eventos com "primeiro evento:
        # 1990-01-01". Um ts_ns assim escapa do filtro > 0 e, ao ser
        # subtraido de ts_recv_ns (~2026, em ns desde 1970), gera uma
        # diferenca tao grande que o cast seguro int64->float64 do pyarrow
        # REJEITA — e foi exatamente isso que derrubou o inspect. A defesa e'
        # dupla: (1) tratar a subtracao em Python/numpy, sem o cast-seguro do
        # pyarrow, e (2) reportar quantos timestamps sao implausiveis em vez
        # de deixa-los contaminar silenciosamente a mediana.
        ts_ns = tabela["ts_ns"].to_numpy(zero_copy_only=False)
        ts_recv = tabela["ts_recv_ns"].to_numpy(zero_copy_only=False)
        HOJE_NS = int(pd.Timestamp.now(tz="UTC").value)
        UM_ANO_NS = 365 * 86_400 * 1_000_000_000
        plausivel = (ts_ns > HOJE_NS - 5 * UM_ANO_NS) & (ts_ns <= ts_recv)
        implausiveis = int((~plausivel & (ts_ns != 0)).sum())
        if implausiveis:
            exemplo = formatar(int(ts_ns[~plausivel & (ts_ns != 0)][0]))
            print(f"  timestamps implausiveis : {implausiveis:,} "
                  f"(ex.: {exemplo} — dado LEGADO gravado antes das correcoes "
                  f"de timestamp desta sessao [ver docs/OPERACAO.md]; capturas "
                  f"novas ja saem sem isso. Se a particao mistura sessao antiga "
                  f"e nova, remova a antiga em vez de investigar mais)")
        if plausivel.any():
            lat_ms = (ts_recv[plausivel] - ts_ns[plausivel]) / 1_000_000.0
            p50 = float(np.median(lat_ms))
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
        _msg("  por simbolo:")
        for row in _agrupar_contando(tabela, "symbol"):
            print(f"    {row['symbol']:<12} {row['count_all']:>12,}")

    if "trade_type" in tabela.column_names:
        _msg("\n  por tipo de negocio:")
        continuo = 0
        for row in sorted(_agrupar_contando(tabela, "trade_type"), key=lambda r: -r["count_all"]):
            codigo = row["trade_type"]
            if codigo is None:
                # Linhas de arquivos gravados antes da coluna trade_type
                # existir (rodada antiga). Contamos como sem-classificacao em
                # vez de quebrar a formatacao.
                print(f"    {'?':>4} {'(sem trade_type gravado)':<24} {row['count_all']:>12,}")
                continue
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

    _msg("")
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
