"""
Decomposicao do drawdown maximo -- PRE-VOO da pergunta de drawdown
(2026-08-30). Descritivo. NAO consome trial.

A pergunta que este modulo responde vem ANTES de escolher mecanismo, pela
regra 0 (valide o MECANISMO antes de calibrar NUMEROS):

    De onde vem o drawdown? Poucas operacoes grandes, uma sequencia de
    perdas medias, ou um ou dois dias ruins?

Cada resposta aponta para um mecanismo DIFERENTE:

    poucas operacoes grandes  -> stop por operacao (mais apertado que 500)
    sequencia de perdas       -> circuit breaker / dimensionamento
    um ou dois dias ruins     -> limite de perda diaria

Calibrar X ou L antes de saber qual e' a fonte real seria exatamente o
erro que a regra 0 existe para pegar.

REGRA DE CLASSIFICACAO, fixada ANTES de ver qualquer numero:
  - Para o drawdown maximo (pico -> vale), medem-se tres PARCELAS, cada
    uma como fracao do drawdown:
      * concentracao em OPERACOES: soma das 3 piores operacoes do
        trecho, sobre o drawdown;
      * concentracao em DIAS: soma do pior dia do trecho, sobre o
        drawdown (o P&L do dia CONTADO SO' dentro do trecho);
      * concentracao em SEQUENCIA: perda acumulada na maior sequencia
        de perdas consecutivas do trecho, sobre o drawdown.
  - As tres parcelas NAO somam 1 (sobrepoem-se: uma operacao grande
    pode ser ao mesmo tempo o pior dia e parte da sequencia). Sao
    reportadas TODAS, sempre. A "fonte dominante" e' a maior das tres,
    e so' e' declarada dominante se ficar >= 0,50. Abaixo disso o
    drawdown e' DIFUSO e nenhum mecanismo pontual o ataca sozinho.
  - Reportam-se os 3 maiores drawdowns, nao so' o maximo -- com 25
    pregoes o maximo e' UM evento.
  - Robustez: jackknife por pregao (drawdown maximo recalculado
    removendo um dia de cada vez -> minimo e maximo) e bootstrap por
    bloco de pregao (IC do drawdown maximo). Com um dia valendo +629
    numa serie de +418, a curva inteira depende de poucos dias, e isto
    tem que aparecer em vez de ser inferido.

O que este modulo NAO faz: nao simula stop, nao simula limite diario,
nao escolhe numero. Isso e' o passo seguinte, pre-registrado.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog

log = structlog.get_logger(__name__)

LIMIAR_DOMINANTE = 0.50


@dataclass(frozen=True)
class Trecho:
    """Um drawdown: do indice do pico ao indice do vale (inclusive)."""
    i_pico: int
    i_vale: int
    profundidade: float      # em pontos, positiva
    pico: float
    vale: float


def _curva(pnl: np.ndarray) -> np.ndarray:
    """Saldo acumulado com um zero na frente (o pico pode ser o inicio)."""
    return np.concatenate([[0.0], np.cumsum(pnl)])


def drawdowns(pnl: np.ndarray, quantos: int = 3) -> list[Trecho]:
    """
    Todos os drawdowns pico->vale da curva, ordenados por profundidade,
    os `quantos` maiores. Um trecho comeca num maximo historico e termina
    no minimo antes do PROXIMO maximo historico (ou no fim da serie).
    """
    c = _curva(pnl)
    trechos: list[Trecho] = []
    i_pico = 0
    i_vale = 0
    for i in range(1, len(c)):
        if c[i] >= c[i_pico]:
            if i_vale > i_pico:
                trechos.append(Trecho(i_pico, i_vale, float(c[i_pico] - c[i_vale]),
                                      float(c[i_pico]), float(c[i_vale])))
            i_pico = i
            i_vale = i
        elif c[i] < c[i_vale]:
            i_vale = i
    if i_vale > i_pico:
        trechos.append(Trecho(i_pico, i_vale, float(c[i_pico] - c[i_vale]),
                              float(c[i_pico]), float(c[i_vale])))
    trechos.sort(key=lambda t: t.profundidade, reverse=True)
    return trechos[:quantos]


def drawdown_maximo(pnl: np.ndarray) -> float:
    t = drawdowns(pnl, quantos=1)
    return t[0].profundidade if t else 0.0


def _maior_sequencia_de_perdas(pnl: np.ndarray) -> tuple[int, float]:
    """(tamanho, perda acumulada) da maior sequencia de pnl < 0."""
    melhor_n, melhor_soma = 0, 0.0
    n, soma = 0, 0.0
    for x in pnl:
        if x < 0:
            n += 1
            soma += float(x)
            if -soma > -melhor_soma:
                melhor_n, melhor_soma = n, soma
        else:
            n, soma = 0, 0.0
    return melhor_n, melhor_soma


def decompor_trecho(ops: pd.DataFrame, t: Trecho) -> dict[str, Any]:
    """
    As tres parcelas do drawdown de um trecho. `ops` em ordem
    cronologica; o trecho cobre as operacoes de indice i_pico .. i_vale-1
    (a curva tem um zero na frente, entao operacao k move a curva de k
    para k+1).
    """
    sub = ops.iloc[t.i_pico:t.i_vale]
    pnl = sub["pnl_liquido"].to_numpy(dtype=float)
    dd = t.profundidade
    if dd <= 0 or len(sub) == 0:
        raise ValueError("trecho sem profundidade")

    piores3 = np.sort(pnl)[:3]
    parcela_ops = float(-piores3[piores3 < 0].sum() / dd)

    por_dia = sub.groupby("dia")["pnl_liquido"].sum()
    pior_dia = por_dia.idxmin()
    parcela_dia = float(-min(por_dia.min(), 0.0) / dd)

    seq_n, seq_soma = _maior_sequencia_de_perdas(pnl)
    parcela_seq = float(-seq_soma / dd)

    parcelas = {"operacoes": parcela_ops, "dias": parcela_dia, "sequencia": parcela_seq}
    dominante = max(parcelas, key=lambda k: parcelas[k])
    if parcelas[dominante] < LIMIAR_DOMINANTE:
        dominante = "difuso"

    return {
        "profundidade": dd,
        "n_operacoes": len(sub),
        "n_dias": int(por_dia.size),
        "dia_inicio": sub["dia"].iloc[0],
        "dia_fim": sub["dia"].iloc[-1],
        "piores_3_operacoes": [float(x) for x in piores3],
        "pior_dia": pior_dia,
        "pior_dia_pnl": float(por_dia.min()),
        "sequencia_tamanho": seq_n,
        "sequencia_perda": float(seq_soma),
        "parcela_operacoes": parcela_ops,
        "parcela_dias": parcela_dia,
        "parcela_sequencia": parcela_seq,
        "fonte_dominante": dominante,
    }


def _jackknife_por_dia(ops: pd.DataFrame) -> dict[str, Any]:
    """Drawdown maximo recalculado removendo UM pregao de cada vez."""
    dias = list(ops["dia"].unique())
    valores = []
    for d in dias:
        pnl = ops.loc[ops["dia"] != d, "pnl_liquido"].to_numpy(dtype=float)
        valores.append((d, drawdown_maximo(pnl)))
    valores.sort(key=lambda x: x[1])
    return {
        "minimo": valores[0][1], "dia_removido_minimo": valores[0][0],
        "maximo": valores[-1][1], "dia_removido_maximo": valores[-1][0],
    }


def _bootstrap_por_dia(ops: pd.DataFrame, n_bootstrap: int,
                       semente: int) -> dict[str, float]:
    rng = np.random.default_rng(semente)
    dias = list(ops["dia"].unique())
    por_dia = {d: ops.loc[ops["dia"] == d, "pnl_liquido"].to_numpy(dtype=float)
               for d in dias}
    vals = []
    for _ in range(n_bootstrap):
        k = rng.choice(len(dias), size=len(dias), replace=True)
        pnl = np.concatenate([por_dia[dias[j]] for j in k])
        vals.append(drawdown_maximo(pnl))
    arr = np.array(vals)
    return {"ic95_baixo": float(np.percentile(arr, 2.5)),
            "mediana": float(np.median(arr)),
            "ic95_alto": float(np.percentile(arr, 97.5))}


def decompor_drawdown(arquivo_operacoes: Path, saida: Path,
                      n_bootstrap: int = 2000, semente: int = 20260830) -> dict[str, Any]:
    ops = pd.read_parquet(arquivo_operacoes)
    if "dia" not in ops.columns or "pnl_liquido" not in ops.columns:
        raise SystemExit("arquivo de operacoes sem as colunas dia/pnl_liquido")
    ops = ops.sort_values(["dia", "seq_no_dia"]).reset_index(drop=True)
    if len(ops) < 2:
        raise SystemExit("menos de 2 operacoes: nao ha' curva para decompor")

    pnl = ops["pnl_liquido"].to_numpy(dtype=float)
    trechos = drawdowns(pnl, quantos=3)
    if not trechos:
        raise SystemExit("curva sem drawdown (nunca caiu de um pico)")

    decomposicoes = [decompor_trecho(ops, t) for t in trechos]
    for i, d in enumerate(decomposicoes, start=1):
        log.info("drawdown.trecho", ordem=i, profundidade=round(d["profundidade"], 1),
                 operacoes=round(d["parcela_operacoes"], 2),
                 dias=round(d["parcela_dias"], 2),
                 sequencia=round(d["parcela_sequencia"], 2),
                 dominante=d["fonte_dominante"])

    resumo: dict[str, Any] = {
        "n_operacoes": len(ops),
        "n_dias": int(ops["dia"].nunique()),
        "pnl_total": float(pnl.sum()),
        "drawdown_maximo": trechos[0].profundidade,
        "calmar": float(pnl.sum() / trechos[0].profundidade),
        "trechos": decomposicoes,
        "jackknife": _jackknife_por_dia(ops),
        "bootstrap": _bootstrap_por_dia(ops, n_bootstrap, semente),
        "limiar_dominante": LIMIAR_DOMINANTE,
    }
    resumo["relatorio"] = str(_escrever_relatorio(resumo, saida))
    return resumo


def _fmt_dia(d: Any) -> str:
    return d.isoformat() if isinstance(d, date) else str(d)


def _escrever_relatorio(r: dict[str, Any], saida: Path) -> Path:
    saida.mkdir(parents=True, exist_ok=True)
    arq = saida / "decomposicao_drawdown.md"
    jk, bt = r["jackknife"], r["bootstrap"]
    L: list[str] = [
        "# Decomposicao do drawdown maximo (pre-voo)\n",
        "Descritivo, nao consome trial. Regra de classificacao fixada ANTES "
        "de ver os numeros (ver docstring de `decomposicao_drawdown.py`).\n",
        f"- operacoes: {r['n_operacoes']} em {r['n_dias']} pregoes",
        f"- P&L total: {r['pnl_total']:+.1f} pts",
        f"- drawdown maximo: {r['drawdown_maximo']:.1f} pts  ->  Calmar {r['calmar']:.2f}\n",
        "## Quao frageis sao esses numeros (25 pregoes)\n",
        f"- jackknife por pregao: removendo um dia de cada vez, o drawdown "
        f"maximo vai de **{jk['minimo']:.1f}** (sem {_fmt_dia(jk['dia_removido_minimo'])}) "
        f"a **{jk['maximo']:.1f}** (sem {_fmt_dia(jk['dia_removido_maximo'])})",
        f"- bootstrap por bloco de pregao: mediana {bt['mediana']:.1f}, "
        f"IC95 [{bt['ic95_baixo']:.1f} ; {bt['ic95_alto']:.1f}]\n",
        "Se o intervalo do jackknife for largo, o drawdown maximo e' "
        "estatistica de UM evento e qualquer mecanismo calibrado nele esta "
        "sendo calibrado num evento.\n",
        "## Os tres maiores drawdowns, decompostos\n",
        "As tres parcelas se SOBREPOEM e nao somam 1 (uma parcela pode ate' "
        "passar de 1: as 3 piores operacoes podem perder mais que o drawdown, "
        "compensadas por ganhos no meio do trecho). Fonte dominante = a "
        f"maior, so' se >= {r['limiar_dominante']:.2f}; senao DIFUSO.\n",
        "| # | profundidade | ops | dias | 3 piores ops | pior dia | maior sequencia | "
        "parcela OPS | parcela DIA | parcela SEQ | dominante |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, d in enumerate(r["trechos"], start=1):
        p3 = ", ".join(f"{x:+.0f}" for x in d["piores_3_operacoes"])
        L.append(
            f"| {i} | {d['profundidade']:.1f} | {d['n_operacoes']} | {d['n_dias']} | "
            f"{p3} | {_fmt_dia(d['pior_dia'])} ({d['pior_dia_pnl']:+.0f}) | "
            f"{d['sequencia_tamanho']} ops ({d['sequencia_perda']:+.0f}) | "
            f"{d['parcela_operacoes']:.2f} | {d['parcela_dias']:.2f} | "
            f"{d['parcela_sequencia']:.2f} | **{d['fonte_dominante']}** |")
    L += [
        "\n## Leitura (fixada antes)\n",
        "- dominante **operacoes** -> o mecanismo candidato e' stop por operacao "
        "mais apertado que 500; a Rota B CONTRA diz que o custo esperado em "
        "expectativa e' ~0 (IC +-50/op).",
        "- dominante **dias** -> limite de perda diaria.",
        "- dominante **sequencia** -> circuit breaker / dimensionamento "
        "(lembrando: o freio atual deu -328 em 7 disparos).",
        "- **difuso** -> nenhum mecanismo pontual ataca sozinho; a discussao "
        "vira dimensionamento de posicao, nao stop.\n",
        "Nada aqui escolhe numero. O passo seguinte e' pre-registro do "
        "trade-off para o mecanismo que a fonte dominante apontar.",
    ]
    arq.write_text("\n".join(L), encoding="utf-8")
    return arq
