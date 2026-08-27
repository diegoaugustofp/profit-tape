"""
Triagem automatica de .parquet.inprogress orfaos apos travamento de maquina.

Incidente real (2026-08-27): a maquina do operador travou durante o pregao,
exigindo reinicio. O `record` novo comecou um processo diferente -- todos
os writers (um por stream x simbolo) que estavam abertos no instante do
travamento ficaram orfaos SIMULTANEAMENTE, ao mesmo sequencial, em todos os
streams e ativos. Passos manuais (achar, verificar, mover, registrar) um a
um nao escalam para esse padrao -- automatizado aqui.

DUAS SEGURANCAS antes de tocar em qualquer arquivo:
  1. Idade minima (--idade-min-min, default 15min): um .inprogress
     ATIVAMENTE sendo escrito por um record de verdade e' tocado a cada
     poucos segundos/minutos (flush do writer). Um arquivo parado ha' mais
     tempo que isso NAO tem escritor vivo -- e' seguro tocar. Arquivo mais
     recente que o limiar e' PULADO, nunca mexido -- por design, prefere
     nao agir a agir errado.
  2. O footer decide o destino, nao a idade: mesmo um .inprogress orfao
     PODE ter footer valido (crash aconteceu DEPOIS do footer ser escrito,
     ANTES do rename -- janela pequena mas real, ver parquet_sink.py). Se
     tem footer, PROMOVE (rename para .parquet, dado recuperado de verdade).
     Se nao tem (o caso comum apos crash), PONE EM QUARENTENA (move para
     fora da arvore de dado, preserva caminho relativo) -- nunca apaga.
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from ..storage.parquet_sink import ParquetSink

log = structlog.get_logger(__name__)


@dataclass
class ResultadoTriagem:
    recuperados: list[Path] = field(default_factory=list)      # tinha footer -> promovido
    quarentenados: list[Path] = field(default_factory=list)    # sem footer -> movido
    pulados_recentes: list[Path] = field(default_factory=list)  # idade < limiar -> intocado


def triagem(raiz_raw: Path, destino_quarentena: Path,
           idade_min_min: float = 15.0, mover: bool = False) -> ResultadoTriagem:
    """
    dry-run por padrao (mover=False): so' lista o que faria. --mover de
    verdade promove/quarentena.

    destino_quarentena: pasta FORA de raiz_raw (nunca dentro -- senao um
    glob futuro de raiz_raw encontraria os proprios arquivos em
    quarentena). Estrutura relativa preservada (stream/dt=.../sym=...) pra
    ficar claro de onde cada arquivo veio.
    """
    resultado = ResultadoTriagem()
    agora = time.time()
    limiar_s = idade_min_min * 60

    candidatos = sorted(raiz_raw.rglob("*.parquet.inprogress"))
    log.info("triagem.encontrados", total=len(candidatos), raiz=str(raiz_raw.resolve()))

    for arq in candidatos:
        idade_s = agora - arq.stat().st_mtime
        if idade_s < limiar_s:
            resultado.pulados_recentes.append(arq)
            log.info("triagem.pulado_recente", arquivo=str(arq),
                    idade_min=round(idade_s / 60, 1),
                    msg="mais recente que o limiar -- pode ter escritor vivo, nao tocado")
            continue

        tem_footer = ParquetSink._footer_ok(arq)
        caminho_relativo = arq.relative_to(raiz_raw)

        if tem_footer:
            destino = arq.with_suffix("")   # tira so' o ".inprogress" final
            resultado.recuperados.append(destino)
            log.info("triagem.recuperado", origem=str(arq), destino=str(destino),
                    msg="footer valido apesar do sufixo -- crash aconteceu "
                        "APOS o footer, ANTES do rename. Dado intacto.")
            if mover:
                arq.rename(destino)
        else:
            destino = destino_quarentena / caminho_relativo
            resultado.quarentenados.append(destino)
            log.warning("triagem.quarentenado", origem=str(arq), destino=str(destino),
                       msg="sem footer -- dado NAO recuperavel. Movido para "
                           "fora da arvore, nunca apagado.")
            if mover:
                destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(arq), str(destino))

    return resultado


def gerar_resumo_para_integridade(resultado: ResultadoTriagem, raiz_raw: Path) -> str:
    """
    Bloco markdown pronto para colar em docs/INTEGRIDADE_DOS_DADOS.md --
    NAO escreve no arquivo sozinho (decisao editorial fica com quem revisa
    o incidente), so' organiza os fatos por stream/dia/simbolo.
    """
    if not resultado.quarentenados:
        return "Nenhum arquivo quarentenado -- nada a registrar."

    por_stream_dia: dict[tuple[str, str], list[str]] = {}
    for p in resultado.quarentenados:
        partes = p.parts
        stream = next((x for x in partes if x in
                      ("trade", "book_offer", "book_price", "tiny_book")), "?")
        dia = next((x for x in partes if x.startswith("dt=")), "?")
        simbolo = next((x for x in partes if x.startswith("sym=")), "?")
        por_stream_dia.setdefault((stream, dia), []).append(simbolo)

    linhas = [
        f"## Dados perdidos por travamento de maquina — "
        f"{len(resultado.quarentenados)} arquivo(s) sem footer\n",
    ]
    for (stream, dia), simbolos in sorted(por_stream_dia.items()):
        linhas.append(f"- **{stream}**, {dia}: {', '.join(sorted(set(simbolos)))}")
    if resultado.recuperados:
        linhas.append(f"\n{len(resultado.recuperados)} arquivo(s) RECUPERADOS "
                      f"(tinham footer valido, so' faltava o rename).")
    return "\n".join(linhas)
