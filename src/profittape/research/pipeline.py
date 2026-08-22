"""Orquestracao: features.parquet -> retornos -> folds -> IC -> veredito -> relatorio."""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from .ic import avaliar
from .retornos import adicionar_ret_futuro
from .trials import RegistroTrials, limiar_deflacionado, t_critico
from .walkforward import gerar_folds

HORIZONTES_PADRAO = [1, 3, 10]
MIN_FOLDS_PARA_VEREDITO = 4
MIN_CONSISTENCIA = 0.7


def _veredito(linha: pd.Series, limiar_z: float) -> str:
    """
    Regras PRE-REGISTRADAS (docs/RESEARCH_PLANO.md), tres barras cumulativas:

      1. MAGNITUDE : |IC medio| >= 2/sqrt(n_obs de teste) — o IC precisa
                     superar o ruido amostral das proprias observacoes. Furo
                     real pego pelo teste de honestidade: ruido com IC -0.05
                     consistente em todos os folds (azar de seed) passava so'
                     com t+consistencia; magnitude dentro da banda nula e'
                     indistinguivel de zero, consistente ou nao.
      2. ESTABILIDADE: |t entre folds| >= t-critico(limiar deflacionado, k-1)
      3. DIRECAO   : mesmo sinal em >= 70% dos folds

      inconclusivo: folds < 4 ou t incalculavel; descarta: falhou 1-3.
    """
    if linha["folds_validos"] < MIN_FOLDS_PARA_VEREDITO or pd.isna(linha["t_stat"]):
        return "inconclusivo"
    piso_magnitude = 2.0 / max(linha["n_obs_teste"], 1) ** 0.5
    barra_t = t_critico(limiar_z, int(linha["folds_validos"]) - 1)
    if (abs(linha["ic_medio"]) >= piso_magnitude
            and abs(linha["t_stat"]) >= barra_t
            and linha["consistencia_sinal"] >= MIN_CONSISTENCIA):
        return "segue"
    return "descarta"


def rodar(features_parquet: Path, saida_dir: Path,
          horizontes: list[int] | None = None,
          treino_min: int = 3, teste_dias: int = 2) -> dict:
    horizontes = horizontes or HORIZONTES_PADRAO
    df = pd.read_parquet(features_parquet)
    df = adicionar_ret_futuro(df, horizontes)

    # Features avaliadas: as z-scored (anti-lookahead por construcao, ver
    # normalize.py). As cruas ficam de fora — escala nao-estacionaria.
    features = [c for c in df.columns if c.startswith("z_")]
    dias = sorted(df["dia"].unique())
    folds = gerar_folds(dias, treino_min=treino_min, teste_dias=teste_dias)
    if not folds:
        raise SystemExit(
            f"dados insuficientes para walk-forward: {len(dias)} dia(s), "
            f"minimo = treino_min({treino_min}) + 1 de teste"
        )

    resultado = avaliar(df, features, horizontes, folds)

    registro = RegistroTrials(saida_dir / "trials.json")
    n_trials_rodada = len(resultado)
    total = registro.registrar_rodada(
        n_trials_rodada,
        {"features": features, "horizontes": horizontes,
         "dias": [str(d) for d in dias], "arquivo": str(features_parquet)},
    )
    limiar = limiar_deflacionado(total)
    resultado["veredito"] = resultado.apply(_veredito, axis=1, limiar_z=limiar)

    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    relatorio = saida_dir / f"relatorio_{ts}.md"
    _escrever_relatorio(relatorio, resultado, dias, folds, total, limiar,
                        str(features_parquet))
    return {
        "features": len(features), "horizontes": horizontes,
        "dias": len(dias), "folds": len(folds),
        "trials_rodada": n_trials_rodada, "trials_acumulados": total,
        "limiar_deflacionado": round(limiar, 3),
        "segue": int((resultado["veredito"] == "segue").sum()),
        "descarta": int((resultado["veredito"] == "descarta").sum()),
        "inconclusivo": int((resultado["veredito"] == "inconclusivo").sum()),
        "relatorio": str(relatorio),
        "tabela": resultado,
    }


def _escrever_relatorio(caminho: Path, resultado: pd.DataFrame, dias: list,
                        folds: list, total_trials: int, limiar: float,
                        origem: str) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    linhas = [
        "# Relatorio de research — IC walk-forward\n",
        f"- gerado: {time.strftime('%Y-%m-%d %H:%M:%SZ', time.gmtime())}",
        f"- origem: `{origem}`",
        f"- dias: {len(dias)} ({dias[0]} a {dias[-1]})",
        f"- folds walk-forward: {len(folds)} (dias inteiros; purge estrutural — "
        f"retornos intra-dia nunca cruzam a fronteira)",
        f"- trials desta rodada: {len(resultado)} | ACUMULADOS: {total_trials}",
        f"- limiar deflacionado E[max Z de {total_trials} ruidos]: {limiar:.3f}",
        "\n## Vereditos (regras pre-registradas em RESEARCH_PLANO.md)\n",
        "| feature | h | folds | IC medio | desvio | t | consist. | veredito |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for _, r in resultado.sort_values(["veredito", "t_stat"],
                                      ascending=[True, False]).iterrows():
        def _f(v, nd=4):
            return "-" if pd.isna(v) else f"{v:.{nd}f}"
        linhas.append(
            f"| {r['feature']} | {r['horizonte']} | {r['folds_validos']} "
            f"| {_f(r['ic_medio'])} | {_f(r['ic_desvio'])} | {_f(r['t_stat'], 2)} "
            f"| {_f(r['consistencia_sinal'], 2)} | **{r['veredito']}** |"
        )
    linhas += [
        "\n## Leitura honesta",
        "- `descarta` significa: nao supera o que RUIDO produziria apos "
        f"{total_trials} tentativas. Nao significa 'a feature e' inutil para sempre'.",
        "- `inconclusivo` significa: amostra pequena demais para afirmar qualquer coisa.",
        "- `segue` NAO significa 'estrategia pronta' — significa 'merece o proximo "
        "teste (custo de transacao, robustez fora do WIN)'.",
        "- ICs por fold no JSON de trials para auditoria.",
    ]
    caminho.write_text("\n".join(linhas), encoding="utf-8")
