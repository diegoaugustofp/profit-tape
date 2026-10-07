"""
Guarda ESTATICA dos tres .ntsl de EXECUCAO (v4.33): vwapvp_continuacao,
ignicao, ea_123_vb.

NAO prova que compilam nem que operam -- nao existe interpretador NTSL fora
do Profit. Pega so' os defeitos que a skill de engenharia (3.1) ja' custou
caro: Abs(), acesso posicional dentro de condicao, Integer concatenado no
ConsoleLog, begin/end desbalanceado, e a trava mais importante deste porte:
nenhum arquivo manda ordem sem declarar que e' so' SIMULADOR.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

NTSL = Path(__file__).resolve().parents[1] / "ntsl"
ARQUIVOS = ["vwapvp_continuacao.ntsl", "ignicao.ntsl", "ea_123_vb.ntsl"]


def _codigo(nome: str) -> list[str]:
    """Linhas sem comentario `//` (nao ha' `//` dentro de string nestes arquivos)."""
    linhas = (NTSL / nome).read_text(encoding="utf-8").splitlines()
    return [ln.split("//", 1)[0] for ln in linhas]


def _inteiros(nome: str) -> set[str]:
    achados: set[str] = set()
    for ln in _codigo(nome):
        m = re.match(r"\s*([\w,\s]+?)\s*:\s*Integer\s*;", ln, re.IGNORECASE)
        if m:
            achados.update(v.strip() for v in m.group(1).split(","))
    return achados


@pytest.mark.parametrize("nome", ARQUIVOS)
def test_sem_abs(nome: str) -> None:
    assert not any(re.search(r"\bAbs\s*\(", ln, re.IGNORECASE) for ln in _codigo(nome))


@pytest.mark.parametrize("nome", ARQUIVOS)
def test_begin_end_balanceados(nome: str) -> None:
    texto = "\n".join(_codigo(nome))
    abre = len(re.findall(r"\bbegin\b", texto, re.IGNORECASE))
    fecha = len(re.findall(r"\bend\b", texto, re.IGNORECASE))
    assert abre == fecha, f"{nome}: {abre} begin x {fecha} end"


@pytest.mark.parametrize("nome", ARQUIVOS)
def test_sem_acesso_posicional_em_condicao(nome: str) -> None:
    """`if x[1] > 0 then` e' comportamento indefinido (skill 3.1). Vale para
    as linhas de condicao: if / else if / while / until."""
    ruins = [ln.strip() for ln in _codigo(nome)
             if re.match(r"\s*(else\s+)?(if|while|until)\b", ln, re.IGNORECASE)
             and re.search(r"\w\s*\[", ln)]
    assert not ruins, ruins


@pytest.mark.parametrize("nome", ARQUIVOS)
def test_integer_nao_entra_no_consolelog(nome: str) -> None:
    inteiros = _inteiros(nome)
    # junta cada ConsoleLog (pode ocupar varias linhas ate' o `;`)
    texto = "\n".join(_codigo(nome))
    for chamada in re.findall(r"ConsoleLog\((.*?)\);", texto, re.DOTALL | re.IGNORECASE):
        sem_string = re.sub(r'"[^"]*"', "", chamada)
        usados = set(re.findall(r"[A-Za-z_]\w*", sem_string))
        assert not (usados & inteiros), f"{nome}: Integer no ConsoleLog: {usados & inteiros}"


@pytest.mark.parametrize("nome", ARQUIVOS)
def test_declara_que_e_so_simulador_e_nao_compilado(nome: str) -> None:
    texto = (NTSL / nome).read_text(encoding="utf-8")
    assert "SIMULADOR" in "\n".join(texto.splitlines()[:60])
    assert "NAO COMPILEI" in texto


@pytest.mark.parametrize("nome", ARQUIVOS)
def test_toda_variavel_do_consolelog_esta_declarada(nome: str) -> None:
    """O compilador do Profit recusa identificador nao declarado, e erro de
    compilacao so' aparece com o mercado aberto. Confere o que da' para
    conferir de fora: nomes `s*`/`b*`/`n*` usados no arquivo existem em
    `input` ou `var`."""
    texto = "\n".join(_codigo(nome))
    m_in = re.search(r"\binput\b(.*?)\bvar\b", texto, re.DOTALL | re.IGNORECASE)
    m_var = re.search(r"\bvar\b(.*?)\bbegin\b", texto, re.DOTALL | re.IGNORECASE)
    assert m_in and m_var
    declarados = set(re.findall(r"\b([A-Za-z_]\w*)\s*\(", m_in.group(1)))
    for bloco in m_var.group(1).split(";"):
        if ":" in bloco:
            declarados.update(v.strip() for v in bloco.split(":", 1)[0].split(","))
    corpo = texto[m_var.end():]
    corpo = re.sub(r'"[^"]*"', '""', corpo)
    usados = set(re.findall(r"\b([sbn][A-Z]\w*|vals)\b", corpo))
    faltam = sorted(usados - declarados)
    assert not faltam, f"{nome}: nao declaradas: {faltam}"


def test_ordens_so_com_quantidade_explicita() -> None:
    """Todo envio de ordem leva `Lote` (o valor que o operador configurou no
    input), nunca depende do default da automacao."""
    padrao = re.compile(
        r"\b(BuyAtMarket|SellShortAtMarket|BuyStop|SellShortStop|SellToCoverStop|"
        r"SellToCoverLimit|BuyToCoverStop|BuyToCoverLimit)\b\s*(\(([^;]*)\))?", re.IGNORECASE)
    for nome in ARQUIVOS:
        texto = "\n".join(_codigo(nome))
        for m in padrao.finditer(texto):
            assert m.group(3) and "Lote" in m.group(3), f"{nome}: {m.group(0)!r} sem Lote"
