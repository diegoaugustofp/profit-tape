"""
Gera docs/REFERENCIA_CLI.md a partir de src/profittape/cli.py.

POR QUE E' GERADO, E NAO ESCRITO A MAO
--------------------------------------
A CLI tem ~70 comandos e ganha um novo a cada poucas sessoes. Uma tabela
escrita a mao morre em duas semanas. Este script le o `cli.py` com `ast`
(nao importa o modulo -- nao precisa de DLL, de typer nem de ambiente),
tira o nome e a primeira frase do docstring de cada `@app.command`, e
monta a tabela agrupada por categoria.

A CATEGORIA e a nota de TRIAL vem do dicionario abaixo, que e' a unica
parte manual. Comando que aparece no cli.py e nao esta' no dicionario
cai em "sem categoria (classifique em tools/gera_referencia_cli.py)" --
visivel, para ser corrigido na proxima entrega, em vez de sumir.

Uso:
    python tools/gera_referencia_cli.py            # reescreve o .md
    python tools/gera_referencia_cli.py --check    # sai com 1 se o .md
                                                   # esta' desatualizado
"""
from __future__ import annotations

import ast
import re
import sys
import textwrap
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CLI = RAIZ / "src" / "profittape" / "cli.py"
SAIDA = RAIZ / "docs" / "REFERENCIA_CLI.md"

# categoria -> (titulo, nota sobre trial)
CATEGORIAS: dict[str, tuple[str, str]] = {
    "captura": ("Captura (todo pregao)", "nao consome trial"),
    "dado": ("Dado: curadoria, integridade, historico", "nao consome trial"),
    "features": ("Features e triagem (categoria features)", "nao consome trial"),
    "trial": ("Pesquisa que CONSOME trial", "cada rodada sobe o limiar deflacionado"),
    "traducao": ("Traducao economica e entendimento de sinal ja' validado", "nao consome trial"),
    "preco": ("EAs de PRECO (M15): fichas, funis, testes",
              "`eas-preco-teste` consome trial; funis e combinar, nao"),
    "bollinger": ("Scalp de Bollinger (15 s)",
                  "replay e funis nao consomem; o veredito e' pela ficha"),
    "deepscalper": ("DeepScalper (Fases 0-2)", "score de forward: uma ficha, um trial em curso"),
    "contraparte": ("Descricoes por contraparte / anomalia medida (passo 1)", "nao consome trial"),
    "ea": ("EA: forward, replay, execucao, diagnostico", "nao consome trial"),
    "infra": ("Infraestrutura e operacao", "nao consome trial"),
}

# comando -> (categoria, documento de referencia)
COMANDOS: dict[str, tuple[str, str]] = {
    "record": ("captura", "OPERACAO.md"),
    "doctor": ("captura", "README.md"),
    "inspect": ("captura", "OPERACAO.md"),
    "backfill": ("captura", "OPERACAO.md"),
    "agents": ("captura", "RESEARCH_PLANO.md"),
    "bench": ("captura", "ARQUITETURA.md"),
    "duplicatas": ("dado", "INTEGRIDADE_DOS_DADOS.md"),
    "quarentena": ("dado", "OPERACAO.md"),
    "triagem-inprogress": ("dado", "OPERACAO.md"),
    "curate": ("dado", "RESEARCH_PLANO.md (DECOMPOSICAO RODOU, 2026-08-31)"),
    "compact": ("dado", "REVISAO_STORAGE.md"),
    "features": ("features", "FEATURES.md"),
    "features-tempo": ("features", "RESEARCH_PLANO.md"),
    "triagem": ("features", "skill profit-tape-disciplina 7.2"),
    "perfil-validar": ("features", "RESEARCH_PLANO.md"),
    "perfil-volume-horario": ("features", "eas/123_volume_baixo.md"),
    "ntsl-equivalencia": ("features", "NTSL_ABSORCAO.md"),
    "fluxo-vs-grafico": ("features", "RESEARCH_PLANO.md (O grafico substitui o tape?)"),
    "triagem-absorcao": ("features", "RESEARCH_PLANO.md (TRIAGEM 7.2 da absorcao)"),
    "regime-funil": ("features", "BOLLINGER_SCALP.md"),
    "curva-poder": ("features", "DESENHO_2_absorcao_com_risco.md"),
    "desenho2-emd": ("features", "DESENHO_2_absorcao_com_risco.md"),
    "research": ("trial", "RESEARCH_PLANO.md (topo)"),
    "absorcao-barra": ("trial", "RESEARCH_PLANO.md (pre-registro 2026-08-31)"),
    "absorcao-grafico": ("trial", "RESEARCH_PLANO.md"),
    "portao-absorcao": ("trial", "RESEARCH_PLANO.md (portao 2026-08-29e)"),
    "reversao-condicional": ("trial", "eas/z_agf_3.md"),
    "remanescente-apos-toque": ("trial", "eas/z_agf_3.md"),
    "rota-b-remanescente": ("trial", "eas/z_agf_3.md"),
    "quintis": ("traducao", "RESEARCH_PLANO.md (quintis)"),
    "mae-analise": ("traducao", "eas/z_agf_3.md"),
    "risco-realizado": ("traducao", "RESEARCH_PLANO.md"),
    "decomposicao-drawdown": ("traducao", "eas/z_agf_3.md"),
    "decompor-efeito": ("traducao", "RESEARCH_PLANO.md"),
    "absorcao-diagnostico": ("traducao", "RESEARCH_PLANO.md"),
    "absorcao-inspecionar": ("traducao", "NTSL_ABSORCAO.md"),
    "custo-acoes": ("traducao", "EAS_DE_PRECO.md 8.2"),
    "eas-preco": ("preco", "EAS_DE_PRECO.md; eas/*.md"),
    "eas-preco-teste": ("preco", "EAS_DE_PRECO.md; eas/*.md"),
    "eas-preco-combinar": ("preco", "EAS_DE_PRECO.md"),
    "bollinger-scalp": ("bollinger", "eas/bollinger_scalp.md"),
    "bollinger-replay": ("bollinger", "BOLLINGER_SCALP.md 5"),
    "bollinger-contexto": ("bollinger", "BOLLINGER_SCALP.md 8"),
    "bollinger-direcao": ("bollinger", "BOLLINGER_SCALP.md 5.6"),
    "valida-ohlc-6min": ("bollinger", "BOLLINGER_SCALP.md 14-15"),
    "diagnostico-multitf": ("bollinger", "BOLLINGER_SCALP.md 11-12"),
    "inventario-deepscalper": ("deepscalper", "eas/deepscalper_fase2.md"),
    "simulador-conferir": ("deepscalper", "eas/deepscalper_fase2.md"),
    "fase2-preparar": ("deepscalper", "eas/deepscalper_fase2.md"),
    "fase2-score": ("deepscalper", "eas/deepscalper_fase2.md"),
    "rolagem": ("contraparte", "RESEARCH_PLANO.md (ROLAGEM)"),
    "rolagem-par": ("contraparte", "RESEARCH_PLANO.md (RECLASSIFICACAO rolagem)"),
    "fechamento": ("contraparte", "RESEARCH_PLANO.md (AJUSTE/FECHAMENTO)"),
    "defasagem": ("contraparte", "RESEARCH_PLANO.md (DEFASAGEM)"),
    "leadlag": ("contraparte", "research/leadlag.py (docstring); HISTORICO 2026-09-25"),
    "ignicao": ("contraparte", "research/ignicao.py (docstring); HISTORICO 2026-09-25"),
    "m1-valida": ("contraparte", "research/m1_historico.py (docstring); HISTORICO 2026-09-25"),
    "iceberg": ("contraparte", "RESEARCH_PLANO.md (ICEBERG)"),
    "book-recomposicao": ("contraparte", "RESEARCH_PLANO.md (RECOMPOSICAO NO LIVRO)"),
    "opcoes-vencimento": ("contraparte", "RESEARCH_PLANO.md (Opcao sobre acao)"),
    "ea": ("ea", "EA_ARQUITETURA.md"),
    "ea-replay": ("ea", "EA_ARQUITETURA.md"),
    "ea-replay-lote": ("ea", "EA_ARQUITETURA.md; BOAS_PRATICAS_PROGRESSO.md"),
    "ea-123-replay": ("ea", "eas/123_m15.md"),
    "ea-micro-replay": ("ea", "eas/microprice.md"),
    "ea-ignicao-replay": ("ea", "eas/ignicao.md"),
    "barra-tempo-conferir": ("ea", "EAS_DE_PRECO.md 5.4"),
    "semente-conferir": ("ea", "EAS_DE_PRECO.md 5.4"),
    "diario": ("ea", "EA_ARQUITETURA.md 6"),
    "e4-comparar": ("ea", "RUNBOOK_E4.md"),
    "ea-ordem-teste": ("ea", "EA_ARQUITETURA.md 2 (E2)"),
    "ea-contas": ("ea", "EA_ARQUITETURA.md 2 (E1)"),
    "alertas-testar": ("infra", "OPERACAO.md"),
    "vigia": ("infra", "OPERACAO.md"),
}


def comandos_do_cli(fonte: str) -> list[tuple[str, str]]:
    """(nome, primeira frase do docstring) de cada @app.command, na ordem do arquivo."""
    arvore = ast.parse(fonte)
    saida: list[tuple[str, str]] = []
    for no in arvore.body:
        if not isinstance(no, ast.FunctionDef):
            continue
        for dec in no.decorator_list:
            if not (isinstance(dec, ast.Call) and getattr(dec.func, "attr", "") == "command"):
                continue
            nome = None
            for kw in dec.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                    nome = str(kw.value.value)
            nome = nome or no.name.replace("_", "-")
            doc = textwrap.dedent(ast.get_docstring(no) or "").strip()
            saida.append((nome, resumo(doc)))
    return saida


def resumo(doc: str) -> str:
    """Primeira frase do docstring (duas, se a primeira for curta), ate' 220 chars, sem `|`."""
    if not doc:
        return "(sem docstring)"
    paragrafo = doc.split("\n\n")[0].replace("\n", " ").strip()
    frases = [f for f in re.split(r"(?<=[.?!])\s+", paragrafo) if f]
    texto = frases[0]
    if len(texto) < 25 and len(frases) > 1:
        texto = texto + " " + frases[1]
    if len(texto) > 220:
        texto = texto[:217].rstrip() + "..."
    return texto.replace("|", "\\|")


def gerar(fonte: str) -> str:
    cmds = comandos_do_cli(fonte)
    por_cat: dict[str, list[tuple[str, str, str]]] = {c: [] for c in CATEGORIAS}
    sem_cat: list[tuple[str, str]] = []
    for nome, doc in cmds:
        if nome in COMANDOS:
            cat, ref = COMANDOS[nome]
            por_cat[cat].append((nome, doc, ref))
        else:
            sem_cat.append((nome, doc))
    orfaos = sorted(set(COMANDOS) - {n for n, _ in cmds})

    linhas = [
        "# Referencia da CLI `profit-tape`",
        "",
        "> **Status:** vivo (GERADO) — **Revisado:** pela ultima execucao de "
        "`tools/gera_referencia_cli.py` — **Assunto:** todos os comandos de "
        "`src/profittape/cli.py`, agrupados por categoria, com a nota de trial e "
        "o documento de referencia. NAO EDITE A MAO: rode o script.",
        "",
        f"{len(cmds)} comandos. Categoria e documento vem do dicionario no script; "
        "nome e descricao vem do docstring do proprio comando (`profit-tape <cmd> --help` "
        "mostra as opcoes).",
        "",
        "A distincao que mais importa: comandos que **consomem trial** sobem o limiar "
        "deflacionado a cada rodada e so' devem rodar com dado NOVO suficiente; os que "
        "nao consomem podem rodar quando quiser (skill `profit-tape-disciplina`, 2).",
        "",
    ]
    for cat, (titulo, nota) in CATEGORIAS.items():
        itens = por_cat[cat]
        if not itens:
            continue
        linhas += [f"## {titulo}", "", f"*{nota}.*", "",
                   "| comando | o que faz | referencia |", "|---|---|---|"]
        for nome, doc, ref in sorted(itens):
            linhas.append(f"| `{nome}` | {doc} | {ref} |")
        linhas.append("")
    if sem_cat:
        linhas += ["## Sem categoria (classifique em `tools/gera_referencia_cli.py`)", "",
                   "| comando | o que faz |", "|---|---|"]
        for nome, doc in sorted(sem_cat):
            linhas.append(f"| `{nome}` | {doc} |")
        linhas.append("")
    if orfaos:
        linhas += ["## No dicionario, mas nao mais no cli.py (remova do script)", ""]
        linhas += [f"- `{n}`" for n in orfaos] + [""]
    return "\n".join(linhas)


def main(argv: list[str]) -> int:
    texto = gerar(CLI.read_text(encoding="utf-8"))
    if "--check" in argv:
        atual = SAIDA.read_text(encoding="utf-8") if SAIDA.exists() else ""
        if atual != texto:
            print(f"{SAIDA.relative_to(RAIZ)} desatualizado: "
                  "rode python tools/gera_referencia_cli.py")
            return 1
        print(f"{SAIDA.relative_to(RAIZ)} em dia")
        return 0
    SAIDA.write_text(texto, encoding="utf-8")
    n = texto.count("\n| `")
    print(f"{SAIDA.relative_to(RAIZ)}: {n} comandos")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
