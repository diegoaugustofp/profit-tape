"""
Valida (e opcionalmente corrige) ancoras de indice nos documentos vivos.

POR QUE ISTO EXISTE COMO FERRAMENTA, E NAO COMO SCRIPT DE UMA VEZ
-----------------------------------------------------------------
"Ancoras devem ser geradas e validadas programaticamente" ja era licao
registrada do projeto. Mesmo assim 15 links do RESEARCH_PLANO.md
estavam quebrados — porque o validador que se usava colapsava hifens
consecutivos e o GitHub NAO colapsa.

    titulo : "Segunda rodada de quintis — z_agf_3 h=1 ..."
    GitHub : "segunda-rodada-de-quintis--z_agf_3-h1-..."   (hifen DUPLO)
    escrito: "segunda-rodada-de-quintis-z_agf_3-h1-..."    (hifen simples)

Travessao e `+` viram hifen duplo porque o caractere e' removido e os
espacos dos dois lados viram hifens. Um validador que colapsa aprova o
link errado e reprova o certo — pior que nao ter validador, porque da
confianca falsa.

REGRA DO GITHUB, reproduzida aqui:
  1. minusculas
  2. remove tudo que nao for [palavra, espaco, hifen] — acentos FICAM
  3. espacos viram hifen, um para um, SEM colapsar

Uso:
    python tools/valida_ancoras.py docs/*.md          # valida
    python tools/valida_ancoras.py --corrigir docs/*.md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RE_TITULO = re.compile(r"^#{2,} (.+)$", re.M)
RE_LINK = re.compile(r"\[([^\]]+)\]\(#([^)]+)\)")


def ancora(titulo: str) -> str:
    """Reproduz a regra do GitHub. NAO colapsa hifens (ver docstring)."""
    limpo = re.sub(r"[^\w\s\-]", "", titulo.strip().lower(), flags=re.UNICODE)
    return re.sub(r"\s", "-", limpo)


def conferir(texto: str) -> tuple[list[tuple[str, str]], dict[str, str]]:
    """Devolve (links_quebrados, mapa_ancora_valida -> titulo)."""
    validas = {ancora(t): t for t in RE_TITULO.findall(texto)}
    quebrados = [(txt, alvo) for txt, alvo in RE_LINK.findall(texto)
                 if alvo not in validas]
    return quebrados, validas


def corrigir(texto: str) -> tuple[str, int, list[str]]:
    """
    Reescreve o alvo a partir do TITULO REAL mais parecido, nao do texto
    do link: os dois divergem quando o indice abrevia o titulo, e usar o
    texto do link so' trocaria um alvo errado por outro.
    """
    import difflib

    _, validas = conferir(texto)
    corrigidos, sem_solucao = 0, []

    def troca(m: re.Match[str]) -> str:
        nonlocal corrigidos
        txt, alvo = m.group(1), m.group(2)
        if alvo in validas:
            return m.group(0)
        perto = difflib.get_close_matches(alvo, list(validas), n=1, cutoff=0.6)
        if perto:
            corrigidos += 1
            return f"[{txt}](#{perto[0]})"
        sem_solucao.append(alvo)
        return m.group(0)

    return RE_LINK.sub(troca, texto), corrigidos, sem_solucao


def main(argv: list[str]) -> int:
    modo_corrigir = "--corrigir" in argv
    caminhos = [a for a in argv if not a.startswith("--")]
    if not caminhos:
        print("uso: valida_ancoras.py [--corrigir] <arquivos.md>")
        return 2

    falhou = False
    for nome in caminhos:
        p = Path(nome)
        texto = p.read_text(encoding="utf-8")
        if modo_corrigir:
            texto, n, sem = corrigir(texto)
            if n:
                p.write_text(texto, encoding="utf-8")
            print(f"{nome}: {n} corrigidos" + (f", {len(sem)} sem solucao" if sem else ""))
        quebrados, _ = conferir(texto)
        total = len(RE_LINK.findall(texto))
        print(f"{nome}: {total} links, {len(quebrados)} quebrados")
        for txt, alvo in quebrados:
            print(f"   QUEBRADO  #{alvo}\n             (texto: {txt[:60]})")
            falhou = True
    return 1 if falhou else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
