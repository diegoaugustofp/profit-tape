"""
Varre a arvore de dados por arquivos .parquet sem footer (magic bytes finais
ausentes) e opcionalmente os remove.

CONTEXTO (2026-08-22): a era do fsync quebrado (O_RDONLY no Windows, v0.26)
gravou part-0000 sem footer em varios dias. A recaptura com fsync corrigido
(v0.27+) NAO sobrescreve esses arquivos — a numeracao de part e' descoberta no
disco e incrementa para nao colidir, entao cada dia recapturado ficou com o
part-0000 FOSSIL podre ao lado do part-0001 novo e bom. O curate/inspect leem
o bom e ignoram o podre, mas o podre polui os relatorios e ocupa espaco.

Um parquet valido termina com os 4 magic bytes 'PAR1'. Esta ferramenta acha os
que nao terminam e, com --remover, os apaga. Sem --remover, so' lista (dry-run
por padrao — nunca apaga sem o operador pedir explicitamente).
"""

from __future__ import annotations

import time
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

PAR1 = b"PAR1"


def _sem_footer(arquivo: Path) -> bool:
    """True se o arquivo NAO termina com os magic bytes PAR1."""
    try:
        tam = arquivo.stat().st_size
        if tam < 8:                      # menor que header+footer: invalido
            return True
        with arquivo.open("rb") as f:
            f.seek(-4, 2)                # 4 bytes antes do fim
            return f.read(4) != PAR1
    except OSError:
        return True                      # ilegivel conta como suspeito


def _corrompido_profundo(arquivo: Path) -> bool:
    """
    True se o arquivo tem footer valido mas falha ao DESCOMPRIMIR — o modo de
    falha 'ZSTD decompression failed: Data corruption detected'. Mais caro que
    _sem_footer (le e descomprime o arquivo inteiro), so' usado com --profundo.
    Um footer intacto sobre um row group podre passa por _sem_footer mas
    derruba qualquer leitura real.
    """
    import pyarrow.parquet as pq

    try:
        pq.read_table(arquivo)   # forca a descompressao de todos os row groups
        return False
    except Exception:
        return True


def varrer(raiz: Path, remover: bool = False, profundo: bool = False) -> None:
    """
    Lista (e opcionalmente remove) todos os .parquet sem footer sob a raiz.
    Ignora .inprogress (sao escrita em andamento legitima, nao fossil).

    profundo=True tambem descomprime cada arquivo para pegar corrupcao INTERNA
    (ZSTD failed) que o footer intacto esconde — mais lento, mas e' o unico
    jeito de achar os arquivos que passam pelo footer e derrubam o curate.
    """
    if not raiz.exists():
        raise SystemExit(f"caminho nao existe: {raiz.resolve()}")

    candidatos = [
        p for p in raiz.rglob("*.parquet")
        if not p.name.endswith(".inprogress")
    ]
    modo = "footer + descompressao (profundo)" if profundo else "footer"
    log.info("quarentena.plano", raiz=str(raiz.resolve()), arquivos=len(candidatos),
             modo=modo)
    print(f"Varrendo {len(candidatos)} arquivo(s) .parquet em {raiz.resolve()} "
          f"[{modo}] ...")

    def _suspeito(p: Path) -> bool:
        if _sem_footer(p):
            return True
        return bool(profundo and _corrompido_profundo(p))

    # Sem feedback durante o loop, --profundo em milhares de arquivos fica
    # SILENCIOSO POR HORAS -- indistinguivel de travado (incidente real:
    # operador esperou 6h sem nenhuma mensagem e nao sabia se seguia rodando).
    # Loga a cada arquivo (nivel debug, para --log-level DEBUG acompanhar
    # arquivo a arquivo) e a cada N arquivos ou T segundos (nivel info, o
    # ritmo normal de acompanhamento).
    fosseis: list[Path] = []
    t0 = time.monotonic()
    ultimo_relato = t0
    for i, p in enumerate(sorted(candidatos), 1):
        log.debug("quarentena.verificando", arquivo=str(p), progresso=f"{i}/{len(candidatos)}")
        if _suspeito(p):
            fosseis.append(p)
        agora = time.monotonic()
        if i == len(candidatos) or agora - ultimo_relato >= 5.0 or i % 100 == 0:
            log.info("quarentena.progresso", verificados=i, total=len(candidatos),
                     suspeitos_ate_agora=len(fosseis),
                     segundos_decorridos=round(agora - t0, 1))
            ultimo_relato = agora

    log.info("quarentena.varredura_concluida", verificados=len(candidatos),
             suspeitos=len(fosseis), segundos=round(time.monotonic() - t0, 1))

    if not fosseis:
        print("Nenhum arquivo sem footer. Tudo integro.")
        return

    total_bytes = sum(p.stat().st_size for p in fosseis)
    print(f"\n{len(fosseis)} arquivo(s) SEM footer ({total_bytes/1e9:.2f} GB):")
    # Agrupa por dia para o operador ver quais pregoes ficam so' com fossil.
    por_dia: dict[str, list[Path]] = {}
    for p in sorted(fosseis):
        dia = next((parte for parte in p.parts if parte.startswith("dt=")), "?")
        por_dia.setdefault(dia, []).append(p)
    for dia, arquivos in sorted(por_dia.items()):
        print(f"  {dia}: {len(arquivos)} arquivo(s)")
        for p in arquivos:
            print(f"      {p}")

    # Alerta: dias em que TODOS os parquet sao fosseis ficam sem dado apos a
    # remocao — precisam de recaptura.
    dias_perdidos = []
    for dia, arquivos_fosseis in por_dia.items():
        todos_do_dia = [p for p in candidatos
                        if f"{dia}" in str(p)]
        if len(arquivos_fosseis) == len(todos_do_dia):
            dias_perdidos.append(dia)
    if dias_perdidos:
        print(f"\n  ATENCAO: estes dias ficam SEM dado apos a remocao "
              f"(so' tem fossil, precisam recapturar): {sorted(dias_perdidos)}")

    if not remover:
        print("\n(dry-run — nada foi apagado. Use --remover para apagar.)")
        return

    apagados = 0
    for p in fosseis:
        try:
            p.unlink()
            apagados += 1
        except OSError as exc:
            print(f"  falha ao apagar {p}: {exc}")
    print(f"\n{apagados} arquivo(s) removido(s).")
    if dias_perdidos:
        print(f"Recapture os dias sem dado: {sorted(dias_perdidos)}")
