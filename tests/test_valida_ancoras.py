"""
Testes da regra de ancora do GitHub.

O caso que motivou tudo: travessao entre espacos vira hifen DUPLO. Um
validador que colapsa hifens aprova o link errado e reprova o certo — e
foi por isso que 15 links ficaram quebrados no RESEARCH_PLANO.md apesar
de "validar ancoras programaticamente" ja ser licao registrada.
"""

from __future__ import annotations

from pathlib import Path

from tools.valida_ancoras import ancora, conferir, corrigir


def test_travessao_vira_hifen_duplo() -> None:
    assert ancora("Segunda rodada — z_agf_3 h=1") == "segunda-rodada--z_agf_3-h1"


def test_mais_tambem_vira_hifen_duplo() -> None:
    assert ancora("Resultado do MAE + assimetria") == "resultado-do-mae--assimetria"


def test_acentos_sao_preservados() -> None:
    """O GitHub mantem acento; remover quebraria os titulos em portugues."""
    assert ancora("custo real de ações") == "custo-real-de-ações"


def test_barra_e_parenteses_somem_sem_deixar_hifen() -> None:
    assert ancora("compra/venda (2026-08-27)") == "compravenda-2026-08-27"
    assert ancora("WINFUT 1m/5m") == "winfut-1m5m"


def test_detecta_link_quebrado() -> None:
    doc = "- [T](#a--b)\n- [U](#a-b)\n\n## A — B\n"
    quebrados, validas = conferir(doc)
    assert "a--b" in validas
    assert [alvo for _, alvo in quebrados] == ["a-b"]


def test_corrige_a_partir_do_titulo_real() -> None:
    doc = "- [Indice](#segunda-rodada-z_agf_3)\n\n## Segunda rodada — z_agf_3\n"
    novo, n, sem = corrigir(doc)
    assert n == 1 and not sem
    assert "#segunda-rodada--z_agf_3" in novo
    assert conferir(novo)[0] == []


def test_documentos_vivos_do_repositorio_estao_integros() -> None:
    """Regressao: os docs do repo nao podem voltar a ter link quebrado."""
    raiz = Path(__file__).resolve().parents[1] / "docs"
    for md in sorted(raiz.glob("*.md")):
        quebrados, _ = conferir(md.read_text(encoding="utf-8"))
        assert not quebrados, f"{md.name}: {[a for _, a in quebrados]}"
