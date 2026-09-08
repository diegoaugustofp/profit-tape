"""
E0 (2026-09-08): inventario dos exports de execucao.

O que se testa e' o CLASSIFICADOR, contra fakes -- a resposta real so'
existe rodando `doctor` na maquina com a DLL. Os fakes cobrem os tres
cenarios que o E0 distingue: so' legado, so' V2, nenhum.
"""
from __future__ import annotations

from types import SimpleNamespace

from profittape.profitdll.bindings import (
    EXPORTS_EXECUCAO,
    MINIMO_E2_LEGADO,
    MINIMO_E2_V2,
    inventario_exports_execucao,
)


def _dll_com(*nomes: str) -> SimpleNamespace:
    return SimpleNamespace(**{n: object() for n in nomes})


def test_dll_so_com_legado_da_caminho_legado_completo() -> None:
    dll = _dll_com(*MINIMO_E2_LEGADO)
    inv = inventario_exports_execucao(dll)
    assert inv["caminho_legado_completo"]
    assert not inv["caminho_v2_completo"]
    assert inv["minimo_legado_ausente"] == []
    assert set(inv["minimo_v2_ausente"]) == set(MINIMO_E2_V2)


def test_dll_so_com_v2_da_caminho_v2_completo() -> None:
    dll = _dll_com(*MINIMO_E2_V2)
    inv = inventario_exports_execucao(dll)
    assert inv["caminho_v2_completo"]
    assert not inv["caminho_legado_completo"]
    # ordem_legada_plana inteira ausente
    assert inv["familias"]["ordem_legada_plana"]["presentes"] == []


def test_dll_sem_nada_de_ordem_nao_completa_nenhum_caminho() -> None:
    """O cenario que reordena tudo: a DLL so-market-data do record."""
    dll = _dll_com("DLLInitializeMarketLogin", "SetTradeCallback")
    inv = inventario_exports_execucao(dll)
    assert not inv["caminho_legado_completo"]
    assert not inv["caminho_v2_completo"]
    for r in inv["familias"].values():
        assert r["presentes"] == []


def test_um_ausente_no_minimo_quebra_o_caminho() -> None:
    """Sem o callback de ordem nao da para confirmar preenchimento -- o E2
    nao e' possivel mesmo com todas as funcoes de envio presentes."""
    sem_callback = [n for n in MINIMO_E2_LEGADO if n != "SetOrderCallback"]
    inv = inventario_exports_execucao(_dll_com(*sem_callback))
    assert not inv["caminho_legado_completo"]
    assert inv["minimo_legado_ausente"] == ["SetOrderCallback"]


def test_presentes_e_ausentes_particionam_cada_familia() -> None:
    dll = _dll_com("SendOrder", "GetPositionV2")
    inv = inventario_exports_execucao(dll)
    for familia, nomes in EXPORTS_EXECUCAO.items():
        r = inv["familias"][familia]
        assert set(r["presentes"]) | set(r["ausentes"]) == set(nomes)
        assert not (set(r["presentes"]) & set(r["ausentes"]))
    assert inv["familias"]["ordem_v2_struct"]["presentes"] == ["SendOrder"]
    assert inv["familias"]["posicao"]["presentes"] == ["GetPositionV2"]


def test_minimos_sao_subconjunto_das_familias() -> None:
    """Guarda contra typo: todo nome do minimo precisa existir no catalogo,
    senao o veredito 'INCOMPLETO' seria por erro de digitacao nosso."""
    todos = {n for nomes in EXPORTS_EXECUCAO.values() for n in nomes}
    assert set(MINIMO_E2_LEGADO) <= todos
    assert set(MINIMO_E2_V2) <= todos


def test_inventario_e_puro_hasattr_nao_chama_nada() -> None:
    """A garantia que permite rodar com o record ATIVO: nenhum atributo e'
    invocado. Um fake que explode se chamado prova isso."""
    class Bomba:
        def __call__(self, *a: object, **k: object) -> None:
            raise AssertionError("inventario chamou uma funcao da DLL")
    dll = SimpleNamespace(**{n: Bomba() for nomes in EXPORTS_EXECUCAO.values() for n in nomes})
    inv = inventario_exports_execucao(dll)
    assert inv["caminho_legado_completo"] and inv["caminho_v2_completo"]
