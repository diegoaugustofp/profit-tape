"""Deteccao de arquivo Parquet incompleto ou corrompido em uma arvore."""

from __future__ import annotations

from pathlib import Path

import pyarrow.parquet as pq


def varrer(pasta: Path) -> tuple[list[Path], list[Path]]:
    """
    Devolve (corrompidos, inprogress) sob `pasta`.

    `corrompidos`: arquivos .parquet cujo footer nao le — legado de processo
    morto a forca antes da adocao do sufixo .inprogress, ou disco com problema.
    `inprogress`: sobras autoidentificadas de escrita interrompida (ou de um
    processo AINDA rodando — por isso a decisao de apagar e' de quem opera,
    nunca automatica).
    """
    corrompidos: list[Path] = []
    for arq in sorted(pasta.rglob("*.parquet")):
        try:
            pq.read_metadata(arq)
        except Exception:
            corrompidos.append(arq)
    inprogress = sorted(pasta.rglob("*.parquet.inprogress"))
    return corrompidos, inprogress


def relatorio(pasta: Path) -> tuple[list[Path], list[Path]]:
    """Varre e imprime. Devolve o mesmo par para quem quiser decidir programaticamente."""
    corrompidos, inprogress = varrer(pasta)
    if corrompidos:
        print(f"\n  {'!' * 66}")
        print(f"  {len(corrompidos)} ARQUIVO(S) CORROMPIDO(S) — footer ausente/ilegivel.")
        print("  Origem tipica: processo morto a forca durante a escrita.")
        print("  Serao IGNORADOS nesta leitura. Mova para quarentena e registre:")
        for a in corrompidos:
            print(f"    {a}")
        print(f"  {'!' * 66}")
    if inprogress:
        print(f"\n  NOTA: {len(inprogress)} arquivo(s) .inprogress encontrado(s):")
        for a in inprogress:
            print(f"    {a}")
        print("  Ou ha um recorder/backfill RODANDO AGORA nesta pasta, ou e' sobra")
        print("  de escrita interrompida. Confirme que nada esta rodando antes de")
        print("  apagar — o conteudo e' parcial e nao recuperavel.")
    return corrompidos, inprogress
