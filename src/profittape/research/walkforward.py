"""Folds walk-forward por dias inteiros, janela expansiva."""

from __future__ import annotations


def gerar_folds(dias: list, treino_min: int = 3, teste_dias: int = 2) -> list[tuple[list, list]]:
    """
    Janela EXPANSIVA: treino comeca com treino_min dias e cresce; teste anda
    em blocos de teste_dias. Ex.: 10 dias, treino_min=3, teste=2 ->
    (d0-2 | d3-4), (d0-4 | d5-6), (d0-6 | d7-8), (d0-8 | d9).

    Por que dias inteiros: retornos sao intra-dia (retornos.py), entao a
    fronteira por dia garante purge estrutural — sem parametro para errar.
    """
    dias = sorted(dias)
    folds = []
    i = treino_min
    while i < len(dias):
        treino = dias[:i]
        teste = dias[i:i + teste_dias]
        if teste:
            folds.append((treino, teste))
        i += teste_dias
    return folds
