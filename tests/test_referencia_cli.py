"""
Testes do gerador da referencia de CLI.

A referencia (docs/REFERENCIA_CLI.md) e' GERADA a partir do cli.py, e o
teste que mais importa e' o ultimo: se alguem adiciona um comando e nao
roda o script, a suite acusa — o mesmo papel do validador de ancoras.
"""

from __future__ import annotations

import textwrap

from tools.gera_referencia_cli import CLI, COMANDOS, SAIDA, comandos_do_cli, gerar, resumo

FONTE_FALSA = textwrap.dedent('''
    import typer
    app = typer.Typer()

    @app.command()
    def doctor() -> None:
        """
        Diagnostico antes de gravar. Segunda frase que nao entra.

        Paragrafo seguinte, ignorado.
        """

    @app.command(name="eas-preco")
    def eas_preco(x: int) -> None:
        """Funil da ficha (`--ficha ifr2` | orb)."""

    @app.command()
    def novo_sem_categoria() -> None:
        """Comando que ninguem classificou ainda."""

    def nao_e_comando() -> None:
        """Nao tem decorator."""
''')


def test_extrai_nome_e_docstring_na_ordem() -> None:
    assert comandos_do_cli(FONTE_FALSA) == [
        ("doctor", "Diagnostico antes de gravar."),
        ("eas-preco", "Funil da ficha (`--ficha ifr2` \\| orb)."),
        ("novo-sem-categoria", "Comando que ninguem classificou ainda."),
    ]


def test_resumo_pega_duas_frases_se_a_primeira_e_curta_e_limita_tamanho() -> None:
    assert resumo("Curto. Segunda frase completa. Terceira.") == "Curto. Segunda frase completa."
    assert resumo("") == "(sem docstring)"
    longo = resumo("x" * 300 + ".")
    assert len(longo) == 220 and longo.endswith("...")


def test_comando_desconhecido_aparece_em_sem_categoria_nao_some() -> None:
    texto = gerar(FONTE_FALSA)
    assert "## Sem categoria" in texto
    assert "| `novo-sem-categoria` |" in texto
    assert "| `doctor` |" in texto and "| `eas-preco` |" in texto


def test_dicionario_nao_tem_comando_orfao() -> None:
    reais = {n for n, _ in comandos_do_cli(CLI.read_text(encoding="utf-8"))}
    assert set(COMANDOS) <= reais, sorted(set(COMANDOS) - reais)


def test_referencia_gerada_esta_em_dia() -> None:
    """Falhou? `python tools/gera_referencia_cli.py` e commite o .md junto."""
    assert SAIDA.read_text(encoding="utf-8") == gerar(CLI.read_text(encoding="utf-8"))
