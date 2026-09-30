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

PARALELISMO E MEMORIA (2026-09-29)
----------------------------------
Medido em sandbox com uma particao no formato do incidente (519.600 linhas
em 34.640 row groups): leitura 43,7 s, combine_chunks() 0,5 s,
write_table() 0,5 s. As 8h+ de um lote grande sao ~98% LEITURA. A v3.84
concluiu "custo do Arrow que nenhum leitor muda" -- ERRADO: o sandbox
so' tinha um nucleo e particoes pequenas. Na maquina do operador (v3.85,
comentario no laco de leitura) o culpado era ds.dataset().to_table(),
7x mais lento que ParquetFile.read(use_threads=True) e superlinear em
particao grande. A leitura e a escrita soltam o GIL (medido), entao
`workers>1` roda particoes inteiras em ThreadPoolExecutor -- util para
muitas particoes; a particao gigante isolada e' o ParquetFile que
resolve. Cada particao e' independente no disco (.compacting e
manifesto vivem no proprio diretorio), entao nao ha corrida; os totais
saem de cada worker como dict e o chamador soma.

A escrita e' ParquetWriter + write_table por FATIA de row_group_size, com
combine_chunks() da fatia (nao da tabela inteira): mesma velocidade do
combine total, memoria extra limitada a um row group em vez de dobrar a
tabela. NUNCA to_batches()/write_batch(): to_batches nao funde chunks
pequenos, e a tabela lida de 34 mil row groups tem 34 mil chunks --
write_batch por chunk recriaria exatamente o incidente (medido: 34.640
batches -> 34.640 row groups).
"""

from __future__ import annotations

import json
import math
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import structlog

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
                  modo_leitura: str = "sequencial",
                  dia_filtro: str | None = None,
                  simbolo_filtro: str | None = None,
                  hoje: date | None = None,
                  workers: int = 1,
                  stream_filtro: str | None = None) -> dict[str, int | float]:
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

    `workers` > 1 processa particoes em paralelo (threads; ver docstring do
    modulo). Com 1, o laco e' sequencial e identico ao de antes. A ordem em
    que as particoes terminam nao importa: o resultado por particao e' o
    mesmo, e os totais sao somados.
    """
    if modo_leitura not in ("lote", "sequencial", "fragmento"):
        raise ValueError(
            f"modo_leitura invalido: {modo_leitura!r} "
            "(esperado 'lote', 'sequencial' ou 'fragmento')")
    if row_group_size <= 0 or max_rows_per_file <= 0:
        raise ValueError("row_group_size e max_rows_per_file precisam ser > 0")
    if workers < 1:
        raise ValueError(f"workers precisa ser >= 1 (recebido {workers})")
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

    if stream_filtro is not None:
        streams = [s for s in streams if s.name == stream_filtro]
        if not streams:
            raise SystemExit(f"--stream {stream_filtro} nao encontrado em {raiz_raw}")

    # SEM a varredura de footers da arvore inteira (validacao.relatorio) que
    # existia ate' a v3.87: ela abria o footer de TODOS os ~5.000 arquivos do
    # backup (8-17 min por rodada, medido) e o resultado era descartado --
    # corrompido e' detectado pelo inventario da propria particao, e
    # .inprogress e' reconferido no disco antes de ler. Aqui so' um glob de
    # diretorio: nada de abrir arquivo. `.inprogress` NAO aborta o comando,
    # so' a particao onde esta' (recorder vivo no dia de HOJE enquanto se
    # compactam os passados).
    particoes_com_inprogress: set[Path] = {
        p.parent for stream in streams for p in stream.glob("dt=*/sym=*/*.parquet.inprogress")
    }

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
             row_group_size=row_group_size, max_rows_per_file=max_rows_per_file,
             modo_leitura=modo_leitura, workers=workers)

    totais = _totais_zerados()
    params = _Params(row_group_size=row_group_size, max_rows_per_file=max_rows_per_file,
                     modo_leitura=modo_leitura, hoje=hoje,
                     particoes_com_inprogress=particoes_com_inprogress)
    n = len(trabalho)

    if workers == 1:
        # Laco sequencial, identico ao de antes: nada de executor no caminho
        # default (mesma ordem de log, mesma ordem de disco).
        for idx, (dia, sym, pasta) in enumerate(trabalho, 1):
            _somar(totais, _processar_particao(dia, sym, pasta, f"{idx}/{n}", params))
        return totais

    # Paralelo: cada future e' UMA particao inteira (checagens + inventario +
    # leitura + escrita + commit). O `progresso` e' o indice de submissao --
    # aproximado, ja' que as particoes terminam fora de ordem. Uma falha em
    # qualquer particao aborta o comando como antes: as que ja' estavam
    # rodando terminam (cada uma limpa os proprios temporarios), as
    # enfileiradas sao canceladas, e a excecao sobe.
    executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="compact")
    futures: list[Future[dict[str, int | float]]] = []
    try:
        for idx, (dia, sym, pasta) in enumerate(trabalho, 1):
            futures.append(executor.submit(
                _processar_particao, dia, sym, pasta, f"{idx}/{n}", params))
        for fut in futures:
            _somar(totais, fut.result())
    except BaseException:
        executor.shutdown(wait=True, cancel_futures=True)
        raise
    executor.shutdown(wait=True)
    return totais


@dataclass(frozen=True)
class _Params:
    row_group_size: int
    max_rows_per_file: int
    modo_leitura: str
    hoje: date
    particoes_com_inprogress: set[Path] = field(default_factory=set)


def _totais_zerados() -> dict[str, int | float]:
    return {
        "particoes": 0, "puladas_dia_corrente": 0, "puladas_inprogress": 0,
        "ja_compactas": 0, "arquivos_pulados": 0,
        "arquivos_antes": 0, "arquivos_depois": 0,
        "row_groups_antes": 0, "row_groups_depois": 0,
        "linhas": 0, "segundos_total": 0.0,
    }


def _somar(acumulado: dict[str, int | float], parcial: dict[str, int | float]) -> None:
    for chave, valor in parcial.items():
        acumulado[chave] += valor


def _processar_particao(dia: str, sym: str, pasta: Path, progresso: str,
                        p: _Params) -> dict[str, int | float]:
    """
    Uma particao do inicio ao fim, devolvendo os totais DELA (o chamador
    soma). E' a unidade de trabalho do worker: tudo o que toca o disco desta
    particao acontece aqui, na mesma thread, na mesma ordem de sempre --
    inclusive a reconferencia de .inprogress imediatamente antes de ler.
    """
    t = _totais_zerados()
    stream_nome = pasta.parent.parent.name
    row_group_size, max_rows_per_file = p.row_group_size, p.max_rows_per_file

    # Commit inacabado de uma rodada anterior tem prioridade absoluta:
    # enquanto o manifesto existir, a particao esta' num estado
    # intermediario que so' ele sabe desfazer.
    if (pasta / MANIFESTO).exists():
        _retomar_commit(pasta, dia, sym)

    if dia >= p.hoje.isoformat():
        log.info("compact.particao_pulada_dia_corrente", stream=stream_nome,
                 dia=dia, symbol=sym, progresso=progresso)
        t["puladas_dia_corrente"] += 1
        return t
    # Reconfere no disco, nao so' na varredura inicial: um backfill pode
    # ter comecado depois dela.
    if pasta in p.particoes_com_inprogress or any(pasta.glob("*.parquet.inprogress")):
        log.warning("compact.particao_pulada_inprogress", stream=stream_nome,
                    dia=dia, symbol=sym, progresso=progresso,
                    nota="ha escrita em andamento (ou sobra de crash nao triada) "
                         "nesta particao -- compactar agora corromperia dado. "
                         "Encerre a captura/backfill ou trie o .inprogress e "
                         "rode de novo.")
        t["puladas_inprogress"] += 1
        return t

    # Sobra .compacting SEM manifesto = crash antes do commit comecar:
    # os originais estao intactos, a sobra e' lixo.
    for sobra in pasta.glob(f"*{SUFIXO_TEMP}"):
        sobra.unlink()
        log.info("compact.temporario_descartado", dia=dia, symbol=sym, arquivo=sobra.name)

    arquivos = sorted(q for q in pasta.glob("*.parquet") if q.is_file())
    if not arquivos:
        return t

    # Inventario ANTES de ler: quantos row groups cada arquivo tem, e
    # quais nem footer tem (esses nao entram no dataset -- o construtor
    # do dataset ja' explodiria neles). O num_row_groups fica guardado
    # por arquivo para nao reler o footer depois da leitura.
    rg_por_arquivo: dict[Path, int] = {}
    linhas_antes = 0
    for arq in arquivos:
        try:
            meta = pq.read_metadata(arq)
        except Exception as exc:
            log.warning("compact.arquivo_pulado", dia=dia, symbol=sym, arquivo=arq.name,
                        erro=f"{type(exc).__name__}: {str(exc)[:100]}",
                        nota="sem footer legivel -- fica no disco como esta")
            t["arquivos_pulados"] += 1
            continue
        rg_por_arquivo[arq] = meta.num_row_groups
        linhas_antes += meta.num_rows
    legiveis = list(rg_por_arquivo)
    rg_antes = sum(rg_por_arquivo.values())
    if not legiveis:
        log.warning("compact.particao_sem_arquivo_legivel", dia=dia, symbol=sym)
        return t

    arquivos_esperados = max(1, math.ceil(linhas_antes / max_rows_per_file))
    rg_esperados = _row_groups_esperados(linhas_antes, max_rows_per_file, row_group_size)
    if len(legiveis) <= arquivos_esperados and rg_antes <= rg_esperados:
        log.info("compact.particao_ja_compacta", stream=stream_nome, dia=dia,
                 symbol=sym, progresso=progresso, arquivos=len(legiveis),
                 row_groups=rg_antes, linhas=linhas_antes)
        t["ja_compactas"] += 1
        return t

    log.info("compact.processando", stream=stream_nome, dia=dia, symbol=sym,
             progresso=progresso, arquivos=len(legiveis),
             row_groups=rg_antes, linhas=linhas_antes)
    t0 = time.monotonic()

    # Leitura ARQUIVO A ARQUIVO com ParquetFile.read, nunca
    # ds.dataset(...).to_table(): medido pelo operador em 2026-09-29 num
    # part-*.parquet de 28.780 row groups (12 colunas), Windows, pyarrow
    # 25.0.1 -- ParquetFile.read(use_threads=True) 0,08 ms/rg; o scanner do
    # dataset 0,57 ms/rg com threads e 0,30 SEM (as threads do scanner
    # PIORAM: 10^4-10^6 batches de 7-10 linhas serializados num laco
    # proprio, um nucleo em 100% e os outros parados). Em particao de book
    # com 37 arquivos e 390 mil row groups o scanner chegou a 20 ms/rg
    # (2h09 numa particao). ParquetFile.read e' linear (0,19 -> 0,21 ms/rg
    # de 2.500 a 20.000 row groups) e paraleliza DENTRO do arquivo.
    #
    # Ler por arquivo tambem dispensa a antiga segunda passada "fragmento a
    # fragmento": um arquivo com ZSTD podre por dentro (footer ok --
    # incidente de 22/08) explode so' na propria leitura, e' pulado e fica
    # no disco. `modo_leitura` sobrevive so' como use_threads:
    # 'lote' = True; 'sequencial' e 'fragmento' = False.
    #
    # Sem partitioning hive: dt e sym vivem no caminho e NAO podem entrar
    # no arquivo (o curate ja' aprendeu isso: conflito de tipo na leitura
    # do dataset). ParquetFile le so' o schema do arquivo, nada mais.
    # Default 'sequencial' desde a v3.88: na maquina do operador (Windows,
    # 8 nucleos) threads DENTRO do arquivo e workers entre particoes foram
    # medidos prejudiciais -- 4 leituras concorrentes 2,6x mais lentas que
    # as 4 em sequencia (diag_pool, 2026-09-29).
    use_threads = p.modo_leitura == "lote"
    partes_ok: list[pa.Table] = []
    lidos: list[Path] = []
    for arq in legiveis:
        try:
            partes_ok.append(pq.ParquetFile(arq).read(use_threads=use_threads))
            lidos.append(arq)
        except Exception as exc:
            log.warning("compact.arquivo_pulado", dia=dia, symbol=sym, arquivo=arq.name,
                        erro=f"{type(exc).__name__}: {str(exc)[:100]}",
                        nota="row group corrompido -- fica no disco como esta")
            t["arquivos_pulados"] += 1
    if not partes_ok:
        log.warning("compact.particao_sem_arquivo_legivel", dia=dia, symbol=sym)
        return t
    tabela = pa.concat_tables(partes_ok, promote_options="permissive")
    del partes_ok
    seg_leitura = round(time.monotonic() - t0, 1)

    # Sem os arquivos pulados, o "antes" que faz sentido comparar e' so'
    # dos que entraram na reescrita -- do inventario, sem reler footer.
    rg_antes_lidos = sum(rg_por_arquivo[q] for q in lidos)
    if tabela.num_rows == 0:
        return t

    t1 = time.monotonic()
    novos = _escrever_compactado(pasta, tabela, lidos, row_group_size, max_rows_per_file)
    rg_depois = sum(pq.ParquetFile(q).metadata.num_row_groups for q in novos)
    seg_escrita = round(time.monotonic() - t1, 1)
    segundos = round(time.monotonic() - t0, 1)

    t["particoes"] += 1
    t["arquivos_antes"] += len(lidos)
    t["arquivos_depois"] += len(novos)
    t["row_groups_antes"] += rg_antes_lidos
    t["row_groups_depois"] += rg_depois
    t["linhas"] += tabela.num_rows
    t["segundos_total"] += segundos
    log.info("compact.particao_ok", stream=stream_nome, dia=dia, symbol=sym,
             progresso=progresso, linhas=tabela.num_rows,
             arquivos_antes=len(lidos), arquivos_depois=len(novos),
             row_groups_antes=rg_antes_lidos, row_groups_depois=rg_depois,
             segundos=segundos, seg_leitura=seg_leitura, seg_escrita=seg_escrita,
             ms_por_row_group=round(seg_leitura * 1000 / max(1, rg_antes_lidos), 2))
    return t


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
            _gravar_arquivo(fatia, temp, row_group_size)
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


def _gravar_arquivo(tabela: pa.Table, destino: Path, row_group_size: int) -> None:
    """
    O QUE CORRIGE O PROBLEMA: um row group por fatia de row_group_size
    linhas, explicito. A tabela chega com um chunk por row group de ORIGEM
    (34 mil, no incidente); cada fatia e' coalescida sozinha
    (combine_chunks da fatia, nao da tabela) e entregue ao writer numa
    unica chamada de write_table, que grava exatamente um row group.
    Memoria extra: uma fatia, nao a tabela inteira.

    NUNCA to_batches()/write_batch() em loop: to_batches nao funde chunks
    pequenos, e write_batch fecha um row group por chunk -- e' exatamente
    o que recriaria os row groups de 15 linhas (medido em 2026-09-29:
    34.640 batches -> 34.640 row groups).
    """
    # Estatistica por coluna e' o que permite pular row group por janela
    # de tempo na leitura -- o filtro mais comum em tape.
    writer = pq.ParquetWriter(destino, tabela.schema, compression="zstd",
                              write_statistics=True)
    try:
        for inicio in range(0, tabela.num_rows, row_group_size):
            fatia = tabela.slice(inicio, row_group_size).combine_chunks()
            writer.write_table(fatia, row_group_size=row_group_size)
    finally:
        writer.close()


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
