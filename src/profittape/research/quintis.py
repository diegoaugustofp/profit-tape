"""
Tabela de quintis: traducao economica dos 'segue' do IC (ic.py) — sinal
estatisticamente real pode ser economicamente morto. Nao gasta trial nenhum:
e' engenharia sobre trials JA' avaliados, nao uma hipotese estatistica nova.

Metodologia:
  - Pool das observacoes OUT-OF-SAMPLE: uniao dos dias de teste de todos os
    folds walk-forward (contiguos e nao-sobrepostos por construcao de
    gerar_folds — sem dupla contagem).
  - Corta o sinal (feature) em N quintis nesses dias, calcula retorno futuro
    MEDIO EM PONTOS (nao percentual — custo de operacao e' cotado em pontos)
    por quintil.
  - Estrategia implicita: comprar no quintil de sinal mais alto, vender no
    mais baixo, SE E SOMENTE SE o IC apontar a direcao certa — para os dois
    'segue' atuais (IC negativo), a leitura e' o INVERSO do quintil: sinal
    alto -> retorno futuro baixo (contrarian), entao o trade implicito e'
    desvanecer o quintil 5 e seguir o quintil 1.
  - ret_liquido = ret_medio_pontos - custo_ida_volta_pontos, aplicado uma vez
    por observacao (uma entrada e' uma saida).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .retornos import adicionar_ret_futuro_pontos
from .walkforward import gerar_folds


def _dias_de_teste(dias: list, folds: list[tuple[list, list]]) -> set:
    """Uniao dos blocos de teste de todos os folds — o out-of-sample pool."""
    fora = set()
    for _treino, teste in folds:
        fora.update(teste)
    return fora


def _atribuir_quintis(df: pd.DataFrame, feature: str, horizonte: int,
                      dias_teste: set, n_quintis: int) -> pd.DataFrame:
    """Sub-dataframe out-of-sample com a coluna 'quintil' atribuida."""
    col_ret = f"ret_pts_{horizonte}"
    sub = df[df["dia"].isin(dias_teste)][[feature, col_ret]].dropna()
    if len(sub) < n_quintis * 5:
        raise SystemExit(
            f"apenas {len(sub)} observacoes out-of-sample para {feature}@h{horizonte} "
            f"— insuficiente para {n_quintis} quintis confiaveis"
        )
    sub = sub.copy()
    sub["quintil"] = pd.qcut(sub[feature], n_quintis, labels=False,
                             duplicates="drop") + 1
    return sub


def _p_valor_bicaudal(t: float) -> float:
    """P-valor bicaudal via normal padrao (erf) — valido para o df grande de
    Welch aqui (n~330/grupo, gl efetivo bem acima de 100: normal e' precisa)."""
    import math
    return float(2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2)))))


def testar_diferenca_quintis(df: pd.DataFrame, feature: str, horizonte: int,
                             dias_teste: set, custo_pontos: float,
                             q_a: int, q_b: int, n_quintis: int = 5) -> dict:
    """
    Welch's t-test (variancias desiguais, apropriado — quintis do meio tendem
    a ter variancia diferente dos extremos) entre o retorno LIQUIDO (1x custo,
    leitura direcional de perna unica) dos quintis q_a e q_b.

    Pergunta que responde: "e' Q_a estatisticamente diferente de Q_b, ou a
    nao-monotonicidade observada (ex.: Q4 mais negativo que Q5) e' o tipo de
    ruido que uma amostra deste tamanho produz por acaso?" Diagnostico, nao
    hipotese nova — nao consome trial do research (nao e' teste de feature
    contra retorno, e' teste de quintil contra quintil da MESMA feature ja'
    avaliada).
    """
    sub = _atribuir_quintis(df, feature, horizonte, dias_teste, n_quintis)
    col_ret = f"ret_pts_{horizonte}"
    a = sub.loc[sub["quintil"] == q_a, col_ret] - custo_pontos
    b = sub.loc[sub["quintil"] == q_b, col_ret] - custo_pontos
    if len(a) < 2 or len(b) < 2:
        raise SystemExit(f"quintil {q_a} ou {q_b} com menos de 2 observacoes")

    media_a, media_b = float(a.mean()), float(b.mean())
    var_a, var_b = float(a.var(ddof=1)), float(b.var(ddof=1))
    na, nb = len(a), len(b)
    erro_padrao = np.sqrt(var_a / na + var_b / nb)
    diff = media_b - media_a
    t = float(diff / erro_padrao) if erro_padrao > 0 else float("nan")
    gl = (
        (var_a / na + var_b / nb) ** 2
        / ((var_a / na) ** 2 / (na - 1) + (var_b / nb) ** 2 / (nb - 1))
    ) if erro_padrao > 0 else float("nan")
    p = _p_valor_bicaudal(t) if not np.isnan(t) else float("nan")

    return {
        "feature": feature, "horizonte": horizonte,
        "quintil_a": q_a, "quintil_b": q_b,
        "n_a": na, "n_b": nb,
        "media_liquida_a": media_a, "media_liquida_b": media_b,
        "diferenca": diff, "t_welch": t, "gl_welch": gl, "p_valor": p,
        "diferem_5pct": bool(not np.isnan(p) and p < 0.05),
    }


def tabela_quintis(df: pd.DataFrame, feature: str, horizonte: int,
                   dias_teste: set, custo_pontos: float,
                   n_quintis: int = 5) -> pd.DataFrame:
    """
    Uma linha por quintil: n, sinal_medio, ret_medio_pontos, ret_liquido,
    pct_positivo, t_stat (contra ret_liquido, nao ret_bruto — a pergunta que
    importa e' se sobra alguma coisa depois do custo).
    """
    col_ret = f"ret_pts_{horizonte}"
    sub = df[df["dia"].isin(dias_teste)][[feature, col_ret]].dropna()
    if len(sub) < n_quintis * 5:
        raise SystemExit(
            f"apenas {len(sub)} observacoes out-of-sample para {feature}@h{horizonte} "
            f"— insuficiente para {n_quintis} quintis confiaveis"
        )
    sub = sub.copy()
    sub["quintil"] = pd.qcut(sub[feature], n_quintis, labels=False,
                             duplicates="drop") + 1

    linhas = []
    for q, grupo in sub.groupby("quintil"):
        ret = grupo[col_ret]
        liquido = ret - custo_pontos
        n = len(ret)
        desvio = float(liquido.std(ddof=1)) if n > 1 else float("nan")
        t = float(liquido.mean() / (desvio / np.sqrt(n))) if n > 1 and desvio > 0 else float("nan")
        linhas.append({
            "quintil": int(q), "n": n,
            "sinal_medio": float(grupo[feature].mean()),
            "ret_medio_pontos": float(ret.mean()),
            "ret_liquido_pontos": float(liquido.mean()),
            "pct_positivo_liquido": float((liquido > 0).mean()),
            "t_stat_liquido": t,
        })
    tabela = pd.DataFrame(linhas).sort_values("quintil").reset_index(drop=True)
    return tabela


def avaliar_pares(features_parquet: Path, pares: list[tuple[str, int]],
                  saida_dir: Path, custo_pontos: float,
                  treino_min: int = 3, teste_dias: int = 2,
                  n_quintis: int = 5, testar_adjacentes: bool = True) -> dict:
    df = pd.read_parquet(features_parquet)
    if "dia" not in df.columns:
        df["dia"] = pd.to_datetime(df["ts_close"], unit="ns", utc=True).dt.date
    horizontes = sorted({h for _f, h in pares})
    df = adicionar_ret_futuro_pontos(df, horizontes)
    dias = sorted(df["dia"].unique())
    folds = gerar_folds(dias, treino_min=treino_min, teste_dias=teste_dias)
    dias_teste = _dias_de_teste(dias, folds)

    resultados = {}
    diferencas = {}
    for feature, h in pares:
        resultados[(feature, h)] = tabela_quintis(
            df, feature, h, dias_teste, custo_pontos, n_quintis
        )
        if testar_adjacentes:
            # Compara CADA par de quintis adjacentes (1v2, 2v3, ..., (n-1)vn)
            # — nao so' o extremo (1 vs n). A nao-monotonicidade observada em
            # producao (Q4 mais negativo que Q5) so' e' visivel comparando
            # vizinhos, nao so' as pontas.
            testes = [
                testar_diferenca_quintis(df, feature, h, dias_teste,
                                         custo_pontos, q, q + 1, n_quintis)
                for q in range(1, n_quintis)
            ]
            diferencas[(feature, h)] = testes

    saida_dir.mkdir(parents=True, exist_ok=True)
    caminho = saida_dir / "quintis.md"
    _escrever_relatorio(caminho, resultados, custo_pontos, len(dias_teste),
                        diferencas)
    return {"pares": list(resultados.keys()), "custo_pontos": custo_pontos,
            "dias_out_of_sample": len(dias_teste),
            "tabelas": resultados, "diferencas": diferencas,
            "relatorio": str(caminho)}


def _fmt(v: float, casas_min: int = 2) -> str:
    """
    Casas decimais ADAPTATIVAS — bug real (2026-08-26): formatacao fixa
    (.1f/.2f) foi desenhada pensando no WIN (custo ~11 pontos, retorno de
    dezenas de pontos por barra) e ESCONDE a informacao real em ativos de
    preco baixo por barra (acoes como MGLU3 movem R$0.01-0.03 por barra;
    ".2f" mostrava "+0.00" para tudo, e o cabecalho de custo mostrava
    "0.0 pontos" para um custo de 0.026 real, aplicado corretamente por
    baixo mas invisivel na tela — o operador achou que o custo nao tinha
    sido usado). Regra: casas suficientes para o numero nao virar zero
    visualmente (ate um teto razoavel), nunca menos que casas_min.
    """
    if v == 0:
        return f"{v:.{casas_min}f}"
    casas = casas_min
    while round(v, casas) == 0 and casas < 6:
        casas += 1
    return f"{v:.{casas + 1}f}"


def _escrever_relatorio(caminho: Path, resultados: dict, custo_pontos: float,
                        n_dias: int, diferencas: dict | None = None) -> None:
    linhas = [
        "# Tabela de quintis — traducao economica dos vereditos 'segue'\n",
        f"- custo de ida-e-volta assumido: {_fmt(custo_pontos)} pontos "
        f"(AJUSTE com o custo real do seu book: spread + corretagem + "
        f"slippage — o numero aqui e' um placeholder)",
        f"- dias out-of-sample (uniao dos blocos de teste): {n_dias}",
        "\nNao gasta trial: e' leitura economica sobre features JA' avaliadas "
        "pelo IC, nao uma hipotese estatistica nova.\n",
    ]
    for (feature, h), tabela in resultados.items():
        spread_bruto = (tabela.loc[tabela["quintil"] == 1, "ret_medio_pontos"].iloc[0]
                        - tabela.loc[tabela["quintil"] == tabela["quintil"].max(),
                                     "ret_medio_pontos"].iloc[0])
        # A estrategia implicita e' par long-short (compra Q1, vende Q5) — DUAS
        # pernas, DOIS custos de ida-e-volta. Subtrair o custo de CADA perna
        # antes de tirar a diferenca (ret_liquido_pontos) cancela o custo no
        # spread por construcao (mesmo custo nas duas pernas) — bug conceitual
        # pego pelo proprio teste de custo-alto-vs-baixo. O spread liquido
        # correto do PAR e' o spread bruto menos 2x o custo de uma perna.
        spread_liquido = spread_bruto - 2 * custo_pontos
        linhas.append(f"\n## {feature} @ h={h}\n")
        linhas.append("| quintil | n | sinal medio | ret bruto (pts) | "
                      "ret liquido (pts) | %>0 liquido | t (liquido) |")
        linhas.append("|---|---|---|---|---|---|---|")
        for _, r in tabela.iterrows():
            t_txt = "-" if pd.isna(r["t_stat_liquido"]) else f"{r['t_stat_liquido']:.2f}"
            sinal_bruto = "+" if r["ret_medio_pontos"] >= 0 else "-"
            sinal_liq = "+" if r["ret_liquido_pontos"] >= 0 else "-"
            linhas.append(
                f"| {int(r['quintil'])} | {int(r['n'])} | {r['sinal_medio']:.3f} "
                f"| {sinal_bruto}{_fmt(abs(r['ret_medio_pontos']))} "
                f"| {sinal_liq}{_fmt(abs(r['ret_liquido_pontos']))} "
                f"| {r['pct_positivo_liquido']:.1%} | {t_txt} |"
            )
        sinal_b = "+" if spread_bruto >= 0 else "-"
        sinal_l = "+" if spread_liquido >= 0 else "-"
        linhas.append(
            f"\nSpread Q1-Q{int(tabela['quintil'].max())}: "
            f"bruto {sinal_b}{_fmt(abs(spread_bruto))} pts, "
            f"LIQUIDO {sinal_l}{_fmt(abs(spread_liquido))} pts "
            f"apos custo de {_fmt(custo_pontos)} pts."
        )
        veredito = "ECONOMICAMENTE VIVO (spread liquido positivo)" if spread_liquido > 0 \
            else "MORTO PELO CUSTO (spread bruto nao sobrevive a transacao)"
        linhas.append(f"**{veredito}**")

        if diferencas and (feature, h) in diferencas:
            linhas.append(
                "\n**Diferenca entre quintis adjacentes** (Welch, ret liquido "
                "1x custo — diagnostico, nao consome trial):"
            )
            linhas.append("| Qa vs Qb | media A | media B | diferenca | t (Welch) | p-valor | |")
            linhas.append("|---|---|---|---|---|---|---|")
            for teste in diferencas[(feature, h)]:
                marca = "DIFEREM" if teste["diferem_5pct"] else "indistinguivel"
                linhas.append(
                    f"| Q{teste['quintil_a']} vs Q{teste['quintil_b']} "
                    f"| {teste['media_liquida_a']:+.2f} | {teste['media_liquida_b']:+.2f} "
                    f"| {teste['diferenca']:+.2f} | {teste['t_welch']:.2f} "
                    f"| {teste['p_valor']:.3f} | {marca} |"
                )
    linhas.append(
        "\n## Leitura honesta\n"
        "- Esta tabela NAO decide se vira estrategia — decide se o sinal "
        "*poderia* sobreviver ao custo. Robustez fora do WIN, drawdown, e "
        "regime ainda faltam.\n"
        "- O custo assumido e' um NUMERO UNICO fixo; custo real varia com "
        "book (liquidez do momento) e piora em volatilidade — trate este "
        "spread como um teto otimista, nao uma promessa.\n"
        "- DUAS leituras possiveis, escolha a que corresponde a estrategia "
        "real: **par long-short** (compra Q1 E vende Q5 ao mesmo tempo) usa "
        "o 'Spread Q1-Qn LIQUIDO' acima (desconta 2x o custo — duas pernas). "
        "**Direcional de um so' extremo** (ex.: EA que so' desvanece o "
        "quintil mais extremo, sem posicao simultanea no oposto) usa a "
        "coluna `ret_liquido_pontos` do quintil operado DIRETAMENTE na "
        "tabela acima (ja' liquida de UM round-trip) — nao o spread do par."
    )
    caminho.write_text("\n".join(linhas), encoding="utf-8")
