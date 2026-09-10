"""
Compactacao de raw: reescreve particoes fechadas com poucos row groups grandes.

POR QUE EXISTE (incidente 2026-09-10)
-------------------------------------
`ParquetWriter.write_batch()` fecha UM row group por chamada. O sink
(storage/parquet_sink.py) chama write_batch uma vez por lote do writer, e o
backfill entregava em micro-lotes de ~15 linhas (causa raiz: drain() com
get_nowait() apos o 1o item, corrigida em 72734a7). Resultado real:
part-0000.parquet do WINFUT com 519.764 linhas em 34.525 row groups de 15
linhas. Cada row group carrega header, footer-entry e estatistica proprios;
ler 34 mil deles e' ordens de grandeza mais lento que ler um so' -- e' o que
fazia dataset.to_table() do curate demorar horas.

O writer ja' nao gera mais assim. Mas os arquivos JA' GRAVADOS continuam
fragmentados e nao se consertam sozinhos. Este comando reescreve-os.

O QUE FAZ -- E SO' ISSO
-----------------------
Le todos os part-*.parquet finalizados de uma particao (dt, sym), descarta
as fronteiras de row group da origem (a leitura ja' faz isso: uma Table nao
tem row group) e grava a tabela INTEIRA de uma vez com row_group_size
GRANDE e EXPLICITO. O conteudo (linhas, colunas, tipos, ordem) e' o mesmo;
so' a organizacao fisica muda: menos arquivos, row groups maiores.

NAO e' curadoria: nada de dedup, nada de sort, nada de ts_ns == 0. O raw
continua sendo a evidencia intocada do que a DLL entregou -- so' que em
menos pedacos. Curadoria segue exclusiva do `curate`.

ATOMICIDADE (commit em duas fases, com manifesto)
-------------------------------------------------
Nao existe rename atomico de VARIOS arquivos. Uma interrupcao no meio nao
pode (a) perder dado nem (b) deixar a particao com originais E compactados
visiveis ao mesmo tempo -- o segundo caso DUPLICARIA cada linha no curate,
silenciosamente. Sequencia:

  1. grava os novos como part-NNNN.parquet.compacting (invisivel a qualquer
     leitor: todos globam *.parquet), fsync + footer relido do disco;
  2. verifica os novos (linhas batem, row groups cairam);
  3. grava _compact.manifest.json listando originais consumidos + novos;
  4. remove os originais;
  5. renomeia .compacting -> .parquet;
  6. remove o manifesto.

Interrupcao antes de (3): originais intactos, sobras .compacting sao
descartadas na proxima rodada. Interrupcao entre (3) e (6): o manifesto diz
exatamente o que falta e a proxima rodada TERMINA o commit antes de tocar
em qualquer outra coisa. Em nenhum ponto um leitor ve duplicata.

Sufixo .compacting, e nao .inprogress, de proposito: .inprogress significa
"writer vivo ou sobra de crash de captura", e a resposta operacional a ele
(encerrar a captura, ou apagar) e' a errada para uma compactacao
interrompida, que se resolve simplesmente rodando compact de novo.
"""

from __future__ import annotations

import json
import math
import os
import time
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq
import structlog

from ..storage.validacao import relatorio

log = structlog.get_logger(__name__)

SUFIXO_TEMP = ".compacting"
MANIFESTO = "_compact.manifest.json"

# Mesmo limite do sink (parquet_sink.py: max_rows_per_file=5_000_000) para o
# numero de linhas por ARQUIVO. row_group_size e' o tamanho do row group
# DENTRO do arquivo -- sempre <= max_rows_per_file. 1 Mi linhas e' o teto
# default do proprio arrow; um dia cheio de WINFUT (~500k-5M) vira 1-5 row
# groups por arquivo em vez de dezenas de milhares.
ROW_GROUP_SIZE_DEFAULT = 1_048_576
MAX_ROWS_PER_FILE_DEFAULT = 5_000_000


def compactar_raw(raiz_raw: Path,
                  row_group_size: int = ROW_GROUP_SIZE_DEFAULT,
                  max_rows_per_file: int = MAX_ROWS_PER_FILE_DEFAULT,
                  modo_leitura: str = "lote",
                  dia_filtro: str | None = None,
                  simbolo_filtro: str | None = None,
                  hoje: date | None = None) -> dict[str, int | float]:
    """
    Compacta, particao por particao de (stream, dia, simbolo), todos os
    streams presentes em raiz_raw (trade, book_*). Nunca o dataset inteiro
    em memoria -- uma particao por vez, como o curate.

    So' dias JA' FECHADOS: a particao do dia corrente (dt >= hoje) e' pulada
    sempre, com ou sem .inprogress -- o recorder pode abrir um arquivo novo
    nela a qualquer momento. Particao de dia passado com .inprogress e'
    pulada tambem (backfill rodando, ou sobra de crash que o operador ainda
    nao triou) -- compactar no meio de uma escrita corrompe dado.

    Arquivo que nao le (footer ausente ou row group ZSTD podre) e' PULADO e
    FICA NO DISCO: a compactacao so' remove o que conseguiu ler por inteiro.
    Perder um arquivo ruim nao pode custar a particao inteira, e apagar
    evidencia nao e' papel desta ferramenta (e' da quarentena).
    """
    if modo_leitura not in ("lote", "sequencial", "fragmento"):
        raise ValueError(
            f"modo_leitura invalido: {modo_leitura!r} "
            "(esperado 'lote', 'sequencial' ou 'fragmento')")
    if row_group_size <= 0 or max_rows_per_file <= 0:
        raise ValueError("row_group_size e max_rows_per_file precisam ser > 0")
    if row_group_size > max_rows_per_file:
        raise ValueError(
            f"row_group_size ({row_group_size}) nao pode exceder "
            f"max_rows_per_file ({max_rows_per_file}) -- o row group vive DENTRO "
            "do arquivo")
    if hoje is None:
        hoje = date.today()

    streams = sorted(p for p in raiz_raw.iterdir() if p.is_dir()) if raiz_raw.exists() else []
    if not streams:
        raise SystemExit(f"Nao ha dado em {raiz_raw}. Rode record ou backfill antes.")

    # Mesma varredura do curate: lista corrompidos e .inprogress no console.
    # Diferenca: aqui .inprogress NAO aborta o comando -- so' a particao
    # onde esta. O caso comum e' o recorder vivo no dia de HOJE enquanto se
    # compactam os dias passados; abortar tudo tornaria o comando inutil
    # em dia de pregao.
    particoes_com_inprogress: set[Path] = set()
    for stream in streams:
        _corrompidos, inprogress = relatorio(stream)
        for p in inprogress:
            particoes_com_inprogress.add(p.parent)

    trabalho: list[tuple[str, str, Path]] = []
    dias_vistos: set[str] = set()
    for stream in streams:
        for pasta_dia in sorted(stream.glob("dt=*")):
            dia = pasta_dia.name.split("=", 1)[1]
            if dia_filtro is not None and dia != dia_filtro:
                continue
            dias_vistos.add(dia)
            for pasta_sym in sorted(p for p in pasta_dia.glob("sym=*") if p.is_dir()):
                sym = pasta_sym.name.split("=", 1)[1]
                if simbolo_filtro is not None and sym != simbolo_filtro:
                    continue
                trabalho.append((dia, sym, pasta_sym))

    if dia_filtro is not None and dia_filtro not in dias_vistos:
        raise SystemExit(f"--dia {dia_filtro} nao encontrado em {raiz_raw}")
    if simbolo_filtro is not None and not trabalho:
        raise SystemExit(
            f"--simbolo {simbolo_filtro} nao encontrado "
            f"{'em ' + dia_filtro if dia_filtro else 'em nenhum dia'}")

    log.info("compact.destino", raiz_raw=str(raiz_raw.resolve()),
             streams=[s.name for s in streams], particoes_encontradas=len(trabalho),
             row_group_size=row_group_size, max_rows_per_file=max_rows_per_file)

    totais: dict[str, int | float] = {
        "particoes": 0, "puladas_dia_corrente": 0, "puladas_inprogress": 0,
        "ja_compactas": 0, "arquivos_pulados": 0,
        "arquivos_antes": 0, "arquivos_depois": 0,
        "row_groups_antes": 0, "row_groups_depois": 0,
        "linhas": 0, "segundos_total": 0.0,
    }

    for idx, (dia, sym, pasta) in enumerate(trabalho, 1):
        progresso = f"{idx}/{len(trabalho)}"
        stream_nome = pasta.parent.parent.name

        # Commit inacabado de uma rodada anterior tem prioridade absoluta:
        # enquanto o manifesto existir, a particao esta' num estado
        # intermediario que so' ele sabe desfazer.
        if (pasta / MANIFESTO).exists():
            _retomar_commit(pasta, dia, sym)

        if dia >= hoje.isoformat():
            log.info("compact.particao_pulada_dia_corrente", stream=stream_nome,
                     dia=dia, symbol=sym, progresso=progresso)
            totais["puladas_dia_corrente"] += 1
            continue
        # Reconfere no disco, nao so' na varredura inicial: um backfill pode
        # ter comecado depois dela.
        if pasta in particoes_com_inprogress or any(pasta.glob("*.parquet.inprogress")):
            log.warning("compact.particao_pulada_inprogress", stream=stream_nome,
                        dia=dia, symbol=sym, progresso=progresso,
                        nota="ha escrita em andamento (ou sobra de crash nao triada) "
                             "nesta particao -- compactar agora corromperia dado. "
                             "Encerre a captura/backfill ou trie o .inprogress e "
                             "rode de novo.")
            totais["puladas_inprogress"] += 1
            continue

        # Sobra .compacting SEM manifesto = crash antes do commit comecar:
        # os originais estao intactos, a sobra e' lixo.
        for sobra in pasta.glob(f"*{SUFIXO_TEMP}"):
            sobra.unlink()
            log.info("compact.temporario_descartado", dia=dia, symbol=sym, arquivo=sobra.name)

        arquivos = sorted(p for p in pasta.glob("*.parquet") if p.is_file())
        if not arquivos:
            continue

        # Inventario ANTES de ler: quantos row groups cada arquivo tem, e
        # quais nem footer tem (esses nao entram no dataset -- o construtor
        # do dataset ja' explodiria neles).
        legiveis: list[Path] = []
        rg_antes = 0
        linhas_antes = 0
        for arq in arquivos:
            try:
                meta = pq.read_metadata(arq)
            except Exception as exc:
                log.warning("compact.arquivo_pulado", dia=dia, symbol=sym, arquivo=arq.name,
                            erro=f"{type(exc).__name__}: {str(exc)[:100]}",
                            nota="sem footer legivel -- fica no disco como esta")
                totais["arquivos_pulados"] += 1
                continue
            legiveis.append(arq)
            rg_antes += meta.num_row_groups
            linhas_antes += meta.num_rows
        if not legiveis:
            log.warning("compact.particao_sem_arquivo_legivel", dia=dia, symbol=sym)
            continue

        arquivos_esperados = max(1, math.ceil(linhas_antes / max_rows_per_file))
        rg_esperados = _row_groups_esperados(linhas_antes, max_rows_per_file, row_group_size)
        if len(legiveis) <= arquivos_esperados and rg_antes <= rg_esperados:
            log.info("compact.particao_ja_compacta", stream=stream_nome, dia=dia,
                     symbol=sym, progresso=progresso, arquivos=len(legiveis),
                     row_groups=rg_antes, linhas=linhas_antes)
            totais["ja_compactas"] += 1
            continue

        log.info("compact.processando", stream=stream_nome, dia=dia, symbol=sym,
                 progresso=progresso, arquivos=len(legiveis),
                 row_groups=rg_antes, linhas=linhas_antes)
        t0 = time.monotonic()

        # SEM partitioning hive: dt e sym vivem no caminho e NAO podem entrar
        # no arquivo (o curate ja' aprendeu isso: conflito de tipo na leitura
        # do dataset). Lendo sem partitioning, a tabela sai com o schema dos
        # arquivos e nada mais.
        dataset = ds.dataset([str(p) for p in legiveis], format=ds.ParquetFileFormat())
        tabela: pa.Table | None = None
        lidos: list[Path] = list(legiveis)
        if modo_leitura != "fragmento":
            # Otimista, como o curate: to_table() em lote e' o caminho rapido
            # e o que descarta as fronteiras de row group da origem. So' cai
            # pro fragmento-a-fragmento se algum arquivo estiver podre por
            # dentro (footer ok, ZSTD quebrado -- incidente de 22/08).
            try:
                tabela = dataset.to_table(use_threads=(modo_leitura == "lote"))
            except Exception as exc:
                log.warning("compact.leitura_em_lote_falhou", dia=dia, symbol=sym,
                            erro=f"{type(exc).__name__}: {str(exc)[:150]}",
                            nota="algum arquivo tem corrupcao interna -- isolando "
                                 "fragmento a fragmento")
                tabela = None
        if tabela is None:
            partes_ok: list[pa.Table] = []
            lidos = []
            for frag in dataset.get_fragments():
                caminho = Path(frag.path)
                try:
                    partes_ok.append(frag.to_table())
                    lidos.append(caminho)
                except Exception as exc2:
                    log.warning("compact.arquivo_pulado", dia=dia, symbol=sym,
                                arquivo=caminho.name,
                                erro=f"{type(exc2).__name__}: {str(exc2)[:100]}",
                                nota="row group corrompido -- fica no disco como esta")
                    totais["arquivos_pulados"] += 1
            if not partes_ok:
                log.warning("compact.particao_sem_arquivo_legivel", dia=dia, symbol=sym)
                continue
            tabela = pa.concat_tables(partes_ok, promote_options="permissive")

        # Sem os arquivos pulados, o "antes" que faz sentido comparar e' so'
        # dos que entraram na reescrita.
        rg_antes_lidos = sum(pq.read_metadata(p).num_row_groups for p in lidos)
        if tabela.num_rows == 0:
            continue

        novos = _escrever_compactado(pasta, tabela, lidos, row_group_size, max_rows_per_file)
        rg_depois = sum(pq.ParquetFile(p).metadata.num_row_groups for p in novos)
        segundos = round(time.monotonic() - t0, 1)

        totais["particoes"] += 1
        totais["arquivos_antes"] += len(lidos)
        totais["arquivos_depois"] += len(novos)
        totais["row_groups_antes"] += rg_antes_lidos
        totais["row_groups_depois"] += rg_depois
        totais["linhas"] += tabela.num_rows
        totais["segundos_total"] += segundos
        log.info("compact.particao_ok", stream=stream_nome, dia=dia, symbol=sym,
                 progresso=progresso, linhas=tabela.num_rows,
                 arquivos_antes=len(lidos), arquivos_depois=len(novos),
                 row_groups_antes=rg_antes_lidos, row_groups_depois=rg_depois,
                 segundos=segundos)

    return totais


def _row_groups_esperados(linhas: int, max_rows_per_file: int, row_group_size: int) -> int:
    """Quantos row groups uma escrita compacta de `linhas` produz."""
    if linhas <= 0:
        return 0
    total = 0
    restante = linhas
    while restante > 0:
        n = min(restante, max_rows_per_file)
        total += math.ceil(n / row_group_size)
        restante -= n
    return total


def _proximo_indice(pasta: Path) -> int:
    """Mesma regra do sink: numeracao pertence ao DIRETORIO. Olha todo
    part-*.parquet* (inclusive .inprogress e .compacting) para nunca colidir."""
    usados = []
    for arq in pasta.glob("part-*.parquet*"):
        try:
            usados.append(int(arq.name.split("-")[1].split(".")[0]))
        except (IndexError, ValueError):
            continue
    return max(usados) + 1 if usados else 0


def _escrever_compactado(pasta: Path, tabela: pa.Table, originais: list[Path],
                         row_group_size: int, max_rows_per_file: int) -> list[Path]:
    """
    Fase 1 (temporarios + verificacao) e fase 2 (commit via manifesto).
    Devolve os caminhos finais (.parquet) dos arquivos novos.

    Qualquer falha ANTES do manifesto apaga os temporarios e relanca --
    originais intactos, nada mudou no disco visivel.
    """
    # combine_chunks: a tabela lida de 34 mil row groups tem 34 mil chunks
    # por coluna. write_table consolida de qualquer jeito (medido: 2000
    # chunks -> 1 row group), mas coalescer antes torna a escrita
    # sequencial em vez de um mosaico de copias pequenas.
    tabela = tabela.combine_chunks()
    seq = _proximo_indice(pasta)
    temporarios: list[Path] = []
    finais: list[Path] = []
    try:
        for inicio in range(0, tabela.num_rows, max_rows_per_file):
            fatia = tabela.slice(inicio, max_rows_per_file)
            final = pasta / f"part-{seq:04d}.parquet"
            temp = pasta / f"part-{seq:04d}.parquet{SUFIXO_TEMP}"
            seq += 1
            # Registra ANTES de gravar: se a escrita ou a verificacao
            # falharem no meio, o except abaixo ainda encontra o temporario
            # para apagar (pego por teste: registrar so' depois deixava
            # sobra .compacting na falha).
            temporarios.append(temp)
            # O QUE CORRIGE O PROBLEMA: a tabela inteira numa chamada, com
            # row_group_size explicito. NUNCA write_batch em loop, nunca
            # confiar so' no default -- e' exatamente o que recriaria os
            # row groups de 15 linhas.
            pq.write_table(
                fatia, temp,
                row_group_size=row_group_size,
                compression="zstd",
                # Estatistica por coluna e' o que permite pular row group por
                # janela de tempo na leitura -- o filtro mais comum em tape.
                write_statistics=True,
            )
            _fsync(temp)
            if not _footer_ok(temp):
                raise RuntimeError(f"footer nao confirmado no disco: {temp}")
            # VERIFICACAO do que motivou o comando: se o numero de row groups
            # nao caiu, o arquivo novo nao e' melhor que o velho e nao deve
            # substitui-lo.
            meta = pq.ParquetFile(temp).metadata
            esperado = math.ceil(fatia.num_rows / row_group_size)
            if meta.num_rows != fatia.num_rows:
                raise RuntimeError(
                    f"{temp.name}: gravou {meta.num_rows} linhas, esperava {fatia.num_rows}")
            if meta.num_row_groups > esperado:
                raise RuntimeError(
                    f"{temp.name}: {meta.num_row_groups} row groups para "
                    f"{fatia.num_rows} linhas (esperava <= {esperado}) -- row_group_size "
                    "nao foi respeitado; a escrita reencaminhou em micro-lotes")
            finais.append(final)
        if not temporarios:
            raise RuntimeError("nenhum arquivo gerado para tabela nao vazia")
    except Exception:
        for t in temporarios:
            t.unlink(missing_ok=True)
        raise

    # Fase 2: a partir daqui, o manifesto e' a fonte de verdade.
    manifesto = pasta / MANIFESTO
    conteudo = {
        "originais": [p.name for p in originais],
        "temporarios": [p.name for p in temporarios],
        "finais": [p.name for p in finais],
        "linhas": tabela.num_rows,
    }
    manifesto.write_text(json.dumps(conteudo, indent=1), encoding="utf-8")
    _fsync(manifesto)
    _commit(pasta, conteudo)
    return finais


def _commit(pasta: Path, conteudo: dict[str, object]) -> None:
    """Remove originais, promove temporarios, remove manifesto. Idempotente:
    cada passo confere o disco antes de agir, para poder ser retomado."""
    originais = conteudo["originais"]
    temporarios = conteudo["temporarios"]
    finais = conteudo["finais"]
    assert isinstance(originais, list)
    assert isinstance(temporarios, list)
    assert isinstance(finais, list)
    for nome in originais:
        (pasta / nome).unlink(missing_ok=True)
    for temp_nome, final_nome in zip(temporarios, finais, strict=True):
        temp, final = pasta / temp_nome, pasta / final_nome
        if temp.exists():
            temp.rename(final)
        elif not final.exists():
            raise RuntimeError(
                f"commit inconsistente em {pasta}: nem {temp_nome} nem {final_nome} "
                "existem -- o manifesto aponta para um arquivo que sumiu")
    (pasta / MANIFESTO).unlink(missing_ok=True)


def _retomar_commit(pasta: Path, dia: str, sym: str) -> None:
    conteudo = json.loads((pasta / MANIFESTO).read_text(encoding="utf-8"))
    log.warning("compact.retomando_commit", dia=dia, symbol=sym,
                originais=len(conteudo["originais"]), novos=len(conteudo["finais"]),
                nota="rodada anterior foi interrompida entre gravar os compactados "
                     "e promove-los -- terminando o commit antes de qualquer outra coisa")
    _commit(pasta, conteudo)


def _fsync(caminho: Path) -> None:
    # "rb+" e nao "rb": no Windows, FlushFileBuffers exige handle de escrita
    # (armadilha real de 2026-08-22 em parquet_sink.py).
    with open(caminho, "rb+") as fh:
        fh.flush()
        os.fsync(fh.fileno())


def _footer_ok(caminho: Path) -> bool:
    """Rele os 4 bytes finais do DISCO e confere os magic bytes PAR1."""
    try:
        with caminho.open("rb") as f:
            f.seek(-4, 2)
            return f.read(4) == b"PAR1"
    except OSError:
        return False


def imprimir_relatorio(t: dict[str, int | float]) -> None:
    print("=" * 60)
    print("COMPACTACAO de raw (row groups minusculos -> grandes)")
    print("=" * 60)
    print(f"  particoes reescritas       : {t['particoes']}")
    print(f"  particoes ja compactas     : {t['ja_compactas']}")
    print(f"  puladas (dia corrente)     : {t['puladas_dia_corrente']}")
    print(f"  puladas (.inprogress)      : {t['puladas_inprogress']}")
    print(f"  arquivos ilegiveis (ficam) : {t['arquivos_pulados']}")
    print(f"  linhas reescritas          : {t['linhas']:,}")
    print(f"  arquivos   antes -> depois : {t['arquivos_antes']:,} -> {t['arquivos_depois']:,}")
    print(f"  row groups antes -> depois : {t['row_groups_antes']:,} -> "
          f"{t['row_groups_depois']:,}")
    if t["segundos_total"]:
        print(f"  tempo total                : {t['segundos_total']:.1f}s")
    if t["puladas_inprogress"]:
        print("\n  NOTA: particoes com .inprogress foram puladas. Se a captura ja")
        print("  terminou, trie a sobra (quarentena) e rode compact de novo.")
    if t["arquivos_pulados"]:
        print("\n  NOTA: arquivos ilegiveis NAO foram removidos -- continuam na")
        print("  particao ao lado dos compactados. Mova-os para quarentena.")
    print("=" * 60)
