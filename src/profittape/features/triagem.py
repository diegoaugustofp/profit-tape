"""
Triagem de uma feature candidata, ANTES de gastar trial.

CATEGORIA `features`: olha so' a FORMA da variavel — redundancia,
cauda, construcao. **Nunca toca em retorno.** Nao consome trial, nao
contamina amostra, e por isso pode rodar quantas vezes quiser.

POR QUE EXISTE
--------------
Em 2026-08-30/31 duas formalizacoes minhas morreram, e as duas por
propriedades que uma correlacao teria revelado em segundos:

  `absorcao_dir = imbalance - desloc_norm`
      Gastou 12 trials e levou CONTRA nas 12 celulas. Depois, medido:
      corr(absorcao_dir, -desloc_norm) = **0,9883**. Era `desloc_norm`
      renomeado. A checagem custaria uma linha e teria vindo antes do
      pre-registro.

  `esforco = vol_agr / amplitude_ticks`
      Registrada como "a direcao certa, porque e' ILIMITADA". Medido:
      p99/p50 = 1,70x — sem cauda nenhuma. Causa: corr(vol_agr,
      amplitude) = +0,892, e razao entre quantidades que ja' andam
      juntas e' quase constante POR CONSTRUCAO.

A licao que as duas compartilham: **eu previ uma propriedade e conclui
outra**. "Ilimitado" nao implica "tem cauda"; "combina dois termos" nao
implica "mede algo novo". Prever nao e' verificar.

O QUE ESTA TRIAGEM NAO FAZ
--------------------------
Nao diz se a feature PREDIZ alguma coisa. Passar aqui nao autoriza nada
— so' evita gastar trial com candidata que ja' da' para descartar
olhando a forma. Reprovar aqui, sim, e' motivo suficiente para nao
pre-registrar.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog

log = structlog.get_logger(__name__)

# Acima disto, a candidata e' a mesma coisa que uma feature existente
# (ou o negativo dela) com outro nome. 0,95 e' folgado de proposito: o
# caso que motivou a triagem deu 0,9883.
LIMITE_REDUNDANCIA = 0.95

# Fracao de |z| >= 2,5 sob normal. A comparacao e' com ESTE numero, nao
# com um limiar absoluto.
#
# A primeira versao usava a razao p99/p50 do |z| com corte em 2,0, e ela
# ERRAVA OS DOIS CASOS REAIS: aprovava `absorcao_dir` (2,34x) e dava ao
# `esforco` MAIS cauda que uma normal (4,30x contra 3,85x). A razao entre
# dois quantis e' instavel e nao se compara a referencia nenhuma.
#
# A fracao acima de 2,5 desvios acerta os dois: 0,00% para
# `absorcao_dir` contra 1,53% de uma normal de mesmo tamanho.
PCT_NORMAL_ACIMA_2_5SD = 1.24

# Abaixo de metade do esperado sob normal, a variavel e' sub-gaussiana e
# uma hipotese sobre eventos extremos nao tem o que medir.
FRACAO_MINIMA_DA_NORMAL = 0.5


def _pares_redundantes(candidata: pd.Series,
                       existentes: pd.DataFrame) -> list[dict[str, Any]]:
    """
    Correlacao com cada feature existente E com o NEGATIVO dela.

    O sinal importa pouco e engana muito: `absorcao_dir` correlaciona
    -0,988 com `desloc_norm`, o que parece "oposto, logo diferente".
    E' a mesma informacao com o sinal trocado. Por isso o modulo.
    """
    fora = []
    for col in existentes.columns:
        outro = existentes[col]
        d = pd.concat([candidata, outro], axis=1).dropna()
        if len(d) < 30 or d.iloc[:, 0].std() == 0 or d.iloc[:, 1].std() == 0:
            continue
        r = float(np.corrcoef(d.iloc[:, 0], d.iloc[:, 1])[0, 1])
        fora.append({
            "feature": col,
            "correlacao": round(r, 4),
            "redundante": abs(r) >= LIMITE_REDUNDANCIA,
        })
    return sorted(fora, key=lambda x: -abs(x["correlacao"]))


def _forma_da_cauda(candidata: pd.Series) -> dict[str, Any]:
    """
    Mede cauda pelo |z| padronizado, para comparar com a normal.

    Reporta a fracao observada acima de 2,5 desvios contra os 1,24% de
    uma normal. `absorcao_dir` deu 6% do esperado — sub-gaussiana, e a
    hipotese era justamente sobre barras extremas.
    """
    v = candidata.dropna().to_numpy(dtype=float)
    if len(v) < 30 or v.std(ddof=1) == 0:
        return {"situacao": "amostra pequena ou variavel constante"}
    z = np.abs((v - v.mean()) / v.std(ddof=1))
    pct = float((z >= 2.5).mean() * 100)
    return {
        "n": len(v),
        "min": round(float(v.min()), 6),
        "max": round(float(v.max()), 6),
        "pct_acima_de_2_5_sd": round(pct, 3),
        "pct_esperado_sob_normal": PCT_NORMAL_ACIMA_2_5SD,
        "razao_com_a_normal": round(pct / PCT_NORMAL_ACIMA_2_5SD, 2),
        "tem_cauda": bool(
            pct >= FRACAO_MINIMA_DA_NORMAL * PCT_NORMAL_ACIMA_2_5SD),
    }


def _diagnostico_de_razao(numerador: pd.Series | None,
                          denominador: pd.Series | None) -> dict[str, Any]:
    """
    Se a candidata e' uma RAZAO, mede a correlacao entre as partes.

    Razao entre quantidades que andam juntas e' quase constante por
    construcao — foi o que matou `esforco` (corr 0,892 entre volume e
    amplitude). Isso NAO aparece olhando so' a razao pronta: e' preciso
    olhar as partes.
    """
    if numerador is None or denominador is None:
        return {"situacao": "nao declarada como razao"}
    d = pd.concat([numerador, denominador], axis=1).dropna()
    if len(d) < 30:
        return {"situacao": "amostra pequena"}
    r = float(np.corrcoef(d.iloc[:, 0], d.iloc[:, 1])[0, 1])
    return {
        "correlacao_numerador_denominador": round(r, 4),
        "atenua_a_variacao": bool(abs(r) >= 0.7),
        "nota": ("numerador e denominador andam juntos: a razao tem MENOS "
                 "variacao que as partes. Isto ATENUA, nao anula — "
                 "confira a cauda antes de descartar"
                 if abs(r) >= 0.7 else "partes suficientemente independentes"),
    }


def triar(candidata: pd.Series, existentes: pd.DataFrame,
          numerador: pd.Series | None = None,
          denominador: pd.Series | None = None) -> dict[str, Any]:
    """
    Devolve o diagnostico e um veredito. `REPROVA` e' bloqueante para
    pre-registro; `PASSA` nao autoriza nada.
    """
    pares = _pares_redundantes(candidata, existentes)
    cauda = _forma_da_cauda(candidata)
    razao = _diagnostico_de_razao(numerador, denominador)

    motivos = []
    redundantes = [p for p in pares if p["redundante"]]
    if redundantes:
        pior = redundantes[0]
        motivos.append(
            f"REDUNDANTE com `{pior['feature']}` (correlacao "
            f"{pior['correlacao']:+.4f}): e' a mesma informacao com outro "
            "nome")
    if cauda.get("tem_cauda") is False:
        motivos.append(
            f"SEM CAUDA: {cauda['pct_acima_de_2_5_sd']}% das barras acima "
            f"de 2,5 desvios, contra {cauda['pct_esperado_sob_normal']}% de "
            f"uma normal ({cauda['razao_com_a_normal']}x). Hipotese sobre "
            "eventos extremos nao tem o que medir")
    # A CORRELACAO ENTRE AS PARTES NAO REPROVA. E' DIAGNOSTICO.
    #
    # Eu criei este criterio afirmando que razao entre quantidades
    # correlacionadas fica "quase constante por construcao", e reprovei
    # `esforco` por corr(vol, amplitude) = +0,888. Duas medicoes
    # derrubaram isso:
    #
    #   1. Sobre 2.723 barras, `esforco` tem 1,33x a cauda de uma normal
    #      e vai de 290 a 5.198 contratos/tick — 18x entre extremos.
    #      Atenuar nao e' anular.
    #   2. Uma razao construida quase CONSTANTE de proposito (ruido de
    #      0,2%) tambem passa no teste de cauda, porque o z-score e'
    #      INVARIANTE A ESCALA: padronizar apaga justamente a informacao
    #      de "quao pequena e' a variacao".
    #
    # O criterio nao estava mal calibrado — media a coisa errada, e
    # nenhum limiar conserta isso. Fica como diagnostico reportado, sem
    # peso de veredito. Remover e' melhor que remendar: criterio que
    # reprova por motivo errado gasta a confianca de todos os outros.

    return {
        "veredito": "REPROVA" if motivos else "PASSA",
        "motivos": motivos,
        "redundancia": pares,
        "cauda": cauda,
        "razao": razao,
    }


def _serie(df: pd.DataFrame, nome_ou_expr: str) -> pd.Series:
    """
    Resolve um nome de coluna OU uma expressao sobre as colunas.

    Uma triagem que so' aceita coluna GRAVADA nao serve para o caso de
    uso principal — triar candidata NOVA, que por definicao ainda nao
    esta no parquet. `esforco` e `amplitude` sao derivadas, e a primeira
    versao deste comando falhava com "nao tem a coluna `esforco`".

    Usa `DataFrame.eval`, cujo parser e' restrito a operacoes sobre
    colunas: nao aceita import, chamada de funcao arbitraria nem acesso a
    atributo.
    """
    if nome_ou_expr in df.columns:
        return df[nome_ou_expr]
    try:
        valor = df.eval(nome_ou_expr)
    except Exception as erro:
        raise SystemExit(
            f"`{nome_ou_expr}` nao e' coluna do parquet nem expressao "
            f"valida sobre as colunas.\n  erro: {erro}\n"
            f"  colunas disponiveis: {sorted(df.columns)[:20]}..."
        ) from erro
    if not isinstance(valor, pd.Series):
        raise SystemExit(f"`{nome_ou_expr}` nao resultou numa serie")
    return valor


def triar_parquet(features_parquet: Path, coluna: str,
                  contra: list[str] | None = None,
                  numerador: str | None = None,
                  denominador: str | None = None,
                  expr: str | None = None) -> dict[str, Any]:
    df = pd.read_parquet(features_parquet)
    candidata = _serie(df, expr or coluna)
    candidata.name = coluna

    if contra:
        faltando = [c for c in contra if c not in df.columns]
        if faltando:
            raise SystemExit(f"colunas ausentes: {faltando}")
        outras = df[contra]
    else:
        # Todas as numericas, menos a propria e menos os z dela — comparar
        # a candidata com o proprio z-score dela daria ~1,0 e viraria
        # falso positivo de redundancia.
        excluir = {coluna, f"z_{coluna}"}
        outras = df.select_dtypes("number").drop(
            columns=[c for c in excluir if c in df.columns])

    r = triar(candidata, outras,
              _serie(df, numerador) if numerador else None,
              _serie(df, denominador) if denominador else None)
    r["expressao"] = expr or coluna
    log.info("triagem.resumo", coluna=coluna, veredito=r["veredito"])
    return r
