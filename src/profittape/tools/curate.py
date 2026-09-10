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
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq
import structlog

from ..storage.validacao import relatorio

log = structlog.get_logger(__name__)


def curar_trades(raiz_raw: Path, raiz_curated: Path,
                 modo_leitura: str = "lote",
                 diagnostico: bool = False) -> dict[str, int | float]:
    """
    Processa particao por particao de (dia, simbolo) — nunca o dataset
    inteiro em memoria, nem o dia inteiro com todos os simbolos misturados.
    Um mes de WINFUT nao cabe, e nao precisa caber.

    GRANULARIDADE (2026-09-10c): antes lia o dia inteiro (todos os simbolos
    juntos) de uma vez -- ate' 318 arquivos, ~3,9 GB de WorkingSet visto em
    producao. Dois runs de --diagnostico no MESMO dia travaram na MESMA
    posicao da lista (arquivo ~200-225), o segundo MAIS LENTO que o
    primeiro -- descarta cache frio e contencao externa pontual, aponta pra
    algo ligado a ARQUIVOS ESPECIFICOS naquela posicao. Como rglob() perco-
    rre as pastas sym=* em ordem, essa posicao e' um SIMBOLO especifico.
    Ler por (dia, simbolo) faz esse simbolo aparecer NOMEADO no log em vez
    de escondido num indice numerico.

    modo_leitura: "lote" (default, paralelo), "sequencial" (lote sem
    threads) ou "fragmento" (pula o lote, vai direto pro loop antigo --
    ver comentario no loop principal para quando usar cada um).

    diagnostico: forca o loop fragmento-a-fragmento (independente de
    modo_leitura) e loga progresso a cada 25 arquivos
    (curate.leitura_progresso). Use quando uma particao estiver demorando
    e precisar saber se a leitura trava LINEARMENTE (todo arquivo custando
    o mesmo -- suspeita de IO/antivirus) ou NUM ARQUIVO especifico (pulo
    brusco de tempo entre dois checkpoints).

    Os checkpoints curate.leitura_ok / conversao_pandas_ok / dedup_ok /
    particao_ok sao SEMPRE emitidos, com ou sem diagnostico, um por
    (dia, simbolo).
    """
    if modo_leitura not in ("lote", "sequencial", "fragmento"):
        raise ValueError(
            f"modo_leitura invalido: {modo_leitura!r} "
            "(esperado 'lote', 'sequencial' ou 'fragmento')")
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

    dias_totais = sorted(origem.glob("dt=*"))
    # (2026-09-10c) GRANULARIDADE MUDOU DE DIA PARA (DIA, SIMBOLO). Motivo:
    # dois runs completos de --diagnostico no MESMO dia (318 arquivos)
    # travaram na MESMA posicao (arquivo ~200-225), e o SEGUNDO run foi
    # MAIS LENTO que o primeiro (79s contra 39,7s no mesmo intervalo) --
    # isso descarta cache frio esquentando E contencao externa pontual (as
    # duas prediriam melhora ou aleatoriedade na segunda vez). Uma posicao
    # fixa e reproduzivel na lista de arquivos aponta pra ALGO ligado a
    # ARQUIVOS ESPECIFICOS que sempre caem ali -- e como rglob() percorre
    # as pastas sym=* em ordem, essa posicao corresponde a um SIMBOLO
    # especifico. Ler por simbolo, em vez do dia inteiro misturado, faz
    # esse simbolo aparecer NOMEADO no log em vez de escondido num indice
    # numerico -- e' o proprio diagnostico, nao so' contorno do sintoma.
    #
    # Efeito colateral bom: nunca mais 318 arquivos na memoria de uma vez
    # (WorkingSet de 3,9 GB visto em producao) -- agora e' ~28-36 por vez,
    # o tamanho tipico de UM simbolo num pregao.
    trabalho: list[tuple[str, Path, str]] = []
    for pasta_dia in dias_totais:
        dia_nome = pasta_dia.name.split("=", 1)[1]
        simbolos = sorted(
            p.name.split("=", 1)[1] for p in pasta_dia.glob("sym=*") if p.is_dir()
        )
        for simbolo in simbolos:
            trabalho.append((dia_nome, pasta_dia, simbolo))

    log.info("curate.destino", raiz_raw=str(raiz_raw.resolve()),
             raiz_curated=str(raiz_curated.resolve()), dias_encontrados=len(dias_totais),
             particoes_encontradas=len(trabalho))

    totais = {"lidas": 0, "duplicatas": 0, "ts_invalido": 0, "gravadas": 0,
              "particoes": 0, "segundos_leitura": 0.0, "segundos_total": 0.0}

    for idx, (dia, pasta_dia, symbol) in enumerate(trabalho, 1):
        t0 = time.monotonic()
        # Le so' os .parquet finalizados desta (dia, simbolo), fragmento a
        # fragmento se precisar. Dois modos de falha ja' vistos em producao:
        # (1) arquivo sem footer — exclude_invalid_files pula; (2) footer
        # VALIDO mas row group internamente corrompido (ZSTD decompression
        # failed) — passa pelo filtro de footer e explode no to_table. So'
        # lendo fragmento a fragmento da' pra isolar o arquivo podre e pular,
        # salvando os sadios do mesmo simbolo.
        arquivos_symbol = [
            str(p) for p in (pasta_dia / f"sym={symbol}").rglob("*.parquet")
            if not p.name.endswith(".inprogress")
        ]
        if not arquivos_symbol:
            continue
        log.info("curate.processando", dia=dia, symbol=symbol,
                 progresso=f"{idx}/{len(trabalho)}", arquivos=len(arquivos_symbol))
        dataset = ds.dataset(
            arquivos_symbol, format=ds.ParquetFileFormat(),
            partitioning=ds.partitioning(flavor="hive"),
        )
        # PERFORMANCE (2026-09-09): com a rotacao por IDADE do writer (todo
        # arquivo fecha aos 900s de vida, ativo ou nao -- ver
        # storage/parquet_sink.py:close_idle), um dia comum de 6,5h ja' produz
        # ~500-600 arquivos de trade; um dia com reinicio (queda de energia,
        # disco cheio, teste manual) passa de 800. O loop fragmento-a-
        # fragmento abre cada arquivo em Python, um de cada vez -- e' o que
        # fazia um dia de 5,4M linhas / 280 arquivos levar 55 minutos.
        #
        # dataset.to_table() le TODOS os fragmentos de uma vez, em C++, com o
        # pool de threads interno do arrow -- e sem o round-trip Python por
        # arquivo. E' tambem MAIS correto que o concat manual de antes: ele
        # aplica o schema UNIFICADO do dataset a cada fragmento na leitura,
        # em vez de exigir promote_options="permissive" depois (que so'
        # tapava a falta dessa unificacao).
        #
        # Mas o loop fragmento-a-fragmento nao e' so' velocidade -- e' o que
        # ISOLA um arquivo com corrupcao interna (footer valido, row group
        # com ZSTD quebrado; incidente real de 22/08, ver o teste
        # test_curate_pula_arquivo_com_zstd_corrompido). Um to_table() em
        # lote explode no primeiro fragmento podre e perderia o DIA INTEIRO,
        # nao so' o arquivo ruim. Por isso o caminho rapido e' OTIMISTA: cai
        # para o loop antigo, byte a byte identico, so' quando ele falha --
        # o caso raro paga o preco, o caso comum (quase sempre) nao.
        # (2026-09-10) TRES MODOS, do mais rapido ao mais garantido:
        #   "lote"       -- dataset.to_table(use_threads=True), o default.
        #   "sequencial" -- dataset.to_table(use_threads=False). Tente se
        #                   "lote" parecer travado -- threads lendo muitos
        #                   arquivos ao mesmo tempo pode causar thrashing em
        #                   HD mecanico/volume de rede em vez de ganho.
        #   "fragmento"  -- pula o to_table() em lote INTEIRAMENTE, vai
        #                   direto pro loop antigo (fragment.to_table() um
        #                   por vez). Mais lento (55 min no dia real de
        #                   09/09), mas e' o unico modo que ja' terminou de
        #                   verdade em producao -- garantia de progresso
        #                   quando os outros dois nao dao sinal de vida.
        # (2026-09-10b) --diagnostico: forca fragmento-a-fragmento com log de
        # progresso a cada N arquivos. Pedido do operador apos 2 dias sem
        # sinal de onde o tempo ia -- a instrumentacao anterior (so' o total
        # ao FIM do dia) e' inutil quando o dia leva horas: nao ha' "fim" pra
        # reportar. Isto diz se a leitura trava LINEARMENTE (todo arquivo
        # custando o mesmo -- suspeita de IO/antivirus) ou NUM ARQUIVO
        # especifico (um pulo brusco no tempo entre dois checkpoints).
        if modo_leitura == "fragmento" or diagnostico:
            tabela = None
        else:
            try:
                tabela = dataset.to_table(use_threads=(modo_leitura == "lote"))
            except Exception as exc:
                log.warning("curate.leitura_em_lote_falhou", dia=dia, symbol=symbol,
                           erro=f"{type(exc).__name__}: {str(exc)[:150]}",
                           nota="algum arquivo deste dia tem corrupcao interna -- "
                                "isolando fragmento a fragmento (mais lento, "
                                "identifica qual)")
                tabela = None
        if tabela is None:
            partes_ok = []
            t_frag0 = time.monotonic()
            total_frag = len(arquivos_symbol)
            for i, frag in enumerate(dataset.get_fragments(), start=1):
                try:
                    partes_ok.append(frag.to_table())
                except Exception as exc2:
                    log.warning("curate.arquivo_pulado", dia=dia, symbol=symbol, arquivo=frag.path,
                               erro=f"{type(exc2).__name__}: {str(exc2)[:100]}")
                if diagnostico and i % 25 == 0:
                    log.info("curate.leitura_progresso", dia=dia, symbol=symbol,
                            arquivos_lidos=i, arquivos_total=total_frag,
                            segundos_decorridos=round(time.monotonic() - t_frag0, 1))
            if diagnostico and total_frag % 25 != 0:
                log.info("curate.leitura_progresso", dia=dia, symbol=symbol,
                        arquivos_lidos=total_frag, arquivos_total=total_frag,
                        segundos_decorridos=round(time.monotonic() - t_frag0, 1))
            if not partes_ok:
                log.warning("curate.dia_sem_arquivo_legivel", dia=dia, symbol=symbol)
                continue
            tabela = pa.concat_tables(partes_ok, promote_options="permissive")
        if tabela.num_rows == 0:
            continue
        t_leitura = time.monotonic() - t0
        # (2026-09-10b) log ISOLADO da leitura, antes de qualquer coisa em
        # pandas -- ate' agora o tempo de leitura so' aparecia dentro do
        # curate.dia_ok, que so' sai no FIM do dia inteiro (leitura +
        # to_pandas + sort/dedup + escrita). Um dia de horas nunca produzia
        # ESTE numero isolado; agora produz, assim que a leitura termina.
        log.info("curate.leitura_ok", dia=dia, symbol=symbol,
                 arquivos=len(arquivos_symbol),
                 linhas=tabela.num_rows, segundos_leitura=round(t_leitura, 1))
        t_pandas0 = time.monotonic()
        df = tabela.to_pandas()
        log.info("curate.conversao_pandas_ok", dia=dia, symbol=symbol, linhas=len(df),
                 segundos=round(time.monotonic() - t_pandas0, 1))
        totais["lidas"] += len(df)

        invalidos = int((df["ts_ns"] == 0).sum())
        totais["ts_invalido"] += invalidos
        df = df[df["ts_ns"] > 0]

        antes = len(df)
        t_dedup0 = time.monotonic()
        df = (
            df.sort_values("ts_recv_ns")
              .drop_duplicates(subset=["symbol", "trade_id"], keep="last")
              .sort_values("ts_ns", kind="stable")
        )
        log.info("curate.dedup_ok", dia=dia, symbol=symbol, linhas_antes=antes,
                 linhas_depois=len(df), duplicatas=antes - len(df),
                 segundos=round(time.monotonic() - t_dedup0, 1))
        totais["duplicatas"] += antes - len(df)

        # groupby aqui e' DEFESA, nao logica nova: como so' lemos arquivos da
        # pasta sym={symbol}, todo grupo deveria ser esse mesmo simbolo. Mas
        # a garantia de verdade e' a coluna "symbol" dos DADOS, nao o nome da
        # pasta -- se algum dia um arquivo for escrito na particao errada
        # (bug no writer, nunca visto, mas o comportamento ORIGINAL ja' se
        # protegia disso), isto ainda escreve cada linha no destino certo em
        # vez de silenciosamente misturar simbolos.
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
        # PERFORMANCE (2026-09-09/10): quebra leitura x pandas x dedup ao
        # longo do run inteiro (curate.leitura_ok / conversao_pandas_ok /
        # dedup_ok ja' mostram isso por particao, em tempo real -- isto e' so'
        # o acumulado pro relatorio final).
        segundos_total = round(time.monotonic() - t0, 1)
        # max(0, ...): em particoes muito pequenas (testes), o ruido de
        # sub-milissegundo entre chamadas a time.monotonic() pode deixar
        # segundos_total < t_leitura por uma fracao inexistente, o que
        # arredondaria para -0.0 -- sem sentido nenhum de "processamento
        # negativo". Numa particao real a diferenca e' ordens de magnitude
        # maior que esse ruido.
        segundos_processamento = round(max(0.0, segundos_total - t_leitura), 1)
        totais["segundos_leitura"] += t_leitura
        totais["segundos_total"] += segundos_total
        log.info("curate.particao_ok", dia=dia, symbol=symbol, linhas_lidas=len(df),
                 duplicatas=antes - len(df), segundos=segundos_total,
                 segundos_leitura=round(t_leitura, 1),
                 segundos_processamento=segundos_processamento)

    return totais


def imprimir_relatorio(t: dict[str, int | float]) -> None:
    print("=" * 60)
    print("CURADORIA raw -> curated")
    print("=" * 60)
    print(f"  particoes (dia+simbolo): {t['particoes']}")
    print(f"  linhas lidas        : {t['lidas']:,}")
    print(f"  duplicatas removidas: {t['duplicatas']:,}")
    print(f"  ts invalido excluido: {t['ts_invalido']:,}")
    print(f"  linhas gravadas     : {t['gravadas']:,}")
    if t.get("segundos_total", 0) > 0:
        pct_leitura = 100 * t["segundos_leitura"] / t["segundos_total"]
        print(f"  tempo total         : {t['segundos_total']:.1f}s "
              f"(leitura {pct_leitura:.0f}% / processamento {100-pct_leitura:.0f}%)")
        if t["segundos_total"] > 300 and pct_leitura < 30:
            print("\n  NOTA: leitura e' fracao pequena do tempo mas o total e'")
            print("  alto -- suspeite de algo FORA do Python (antivirus, disco,")
            print("  pasta sincronizada) antes de otimizar o codigo de novo.")
    if t["lidas"]:
        if t["ts_invalido"] / t["lidas"] > 0.001:
            print("\n  ALERTA: mais de 0,1% com timestamp invalido. Isso e' bug de")
            print("  parse de data (timeparse.py x formato da sua DLL), nao ruido.")
        if t["duplicatas"] / t["lidas"] > 0.10:
            print("\n  NOTA: mais de 10% de duplicata sugere reentrega macica —")
            print("  reconnect no meio da sessao ou backfill sobreposto a gravacao.")
    print("=" * 60)
