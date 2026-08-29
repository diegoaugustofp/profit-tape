"""Orquestracao: features.parquet -> retornos -> folds -> IC -> veredito -> relatorio."""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from .ic import avaliar
from .retornos import adicionar_ret_futuro
from .trials import RegistroTrials, limiar_deflacionado, t_critico
from .walkforward import gerar_folds

HORIZONTES_PADRAO = [1, 3, 10]
MIN_FOLDS_PARA_VEREDITO = 4
MIN_CONSISTENCIA = 0.7
# PRE-REGISTRO 3, congelado em 2026-08-29i. Deliberadamente MAIS ALTO que
# MIN_CONSISTENCIA: a barra de 0,7 nao separa "faltou fold" de "desvio alto
# entre folds", e desvio alto e' instabilidade real, nao falta de poder. Com
# 11 folds, 0,85 exige 10 sinais iguais em 11 (p = 0,006 sob moeda honesta);
# com 23 folds, 20 em 23 (p = 0,0002).
MIN_CONSISTENCIA_PODER = 0.85


def _veredito(linha: pd.Series, limiar_z: float,
              promover_por_poder: bool = False) -> str:
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

    `promover_por_poder` (PRE-REGISTRO 3, congelado 2026-08-29i, OPT-IN):
    uma celula que passa em MAGNITUDE e falha SO em ESTABILIDADE, com
    consistencia de sinal >= 0,85, vira `inconclusivo` em vez de
    `descarta`. ESTABILIDADE e' a unica das tres barras cujo limiar depende
    do numero de folds (t_critico cai de 4,03 com 11 folds para 3,50 com 23
    SEM nada mudar no dado), entao falhar so' nela e' afirmacao sobre poder
    amostral, nao sobre ausencia de efeito.

    Default `False` de proposito: o historico de barra de volume (492
    trials, incluindo os dois `segue` de 2026-08-23) foi julgado pela regra
    antiga, e mudar a funcao para todos reclassificaria retroativamente
    celulas que ninguem rerodou.

    A regra so' pode mover celula de `descarta` para `inconclusivo` —
    nunca para `segue`, nunca o contrario. `segue` e' identico nos dois
    modos.
    """
    if linha["folds_validos"] < MIN_FOLDS_PARA_VEREDITO or pd.isna(linha["t_stat"]):
        return "inconclusivo"
    piso_magnitude = 2.0 / max(linha["n_obs_teste"], 1) ** 0.5
    barra_t = t_critico(limiar_z, int(linha["folds_validos"]) - 1)
    magnitude_ok = abs(linha["ic_medio"]) >= piso_magnitude
    estabilidade_ok = abs(linha["t_stat"]) >= barra_t
    if (magnitude_ok and estabilidade_ok
            and linha["consistencia_sinal"] >= MIN_CONSISTENCIA):
        return "segue"
    if (promover_por_poder and magnitude_ok and not estabilidade_ok
            and linha["consistencia_sinal"] >= MIN_CONSISTENCIA_PODER):
        return "inconclusivo"
    return "descarta"


def rodar(features_parquet: Path, saida_dir: Path,
          horizontes: list[int] | None = None,
          treino_min: int = 3, teste_dias: int = 2,
          trials_previstos: int | None = None,
          promover_por_poder: bool = False) -> dict[str, Any]:
    """
    `trials_previstos`: total de trials contra o qual DEFLACIONAR, em vez do
    total apos esta rodada. Existe para uma hipotese que se resolve em MAIS
    DE UMA invocacao — caso real: o pre-registro de 2026-08-29e gasta 12
    trials, 6 no arquivo de 5m e 6 no de 1m, dois arquivos separados e
    portanto duas chamadas. Sem isto, a rodada que acontecesse PRIMEIRO
    seria julgada contra 498 trials e a segunda contra 504: o mesmo
    pre-registro com duas barras diferentes, e um desconto para quem correu
    na frente.

    O contador em disco continua somando normalmente — isto muda so' contra
    QUE numero se deflaciona, nunca quanto se cobra. E so' pode ENDURECER a
    barra: se o valor informado for menor que o total real, o real prevalece.
    """
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
    # max(): o valor informado so' pode ENDURECER. Se alguem passar um
    # numero menor que o total real, o real vale — deflacao nunca baixa a
    # barra (mesma regra do piso de 1.96 em limiar_deflacionado).
    limiar = limiar_deflacionado(max(total, trials_previstos or 0))
    resultado["veredito"] = resultado.apply(
        _veredito, axis=1, limiar_z=limiar,
        promover_por_poder=promover_por_poder)

    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    relatorio = saida_dir / f"relatorio_{ts}.md"
    _escrever_relatorio(relatorio, resultado, dias, folds, total, limiar,
                        str(features_parquet), promover_por_poder)
    return {
        "features": len(features), "horizontes": horizontes,
        "dias": len(dias), "folds": len(folds),
        "trials_rodada": n_trials_rodada, "trials_acumulados": total,
        "limiar_deflacionado": round(limiar, 3),
        "promover_por_poder": promover_por_poder,
        "segue": int((resultado["veredito"] == "segue").sum()),
        "descarta": int((resultado["veredito"] == "descarta").sum()),
        "inconclusivo": int((resultado["veredito"] == "inconclusivo").sum()),
        "relatorio": str(relatorio),
        "tabela": resultado,
    }


def _escrever_relatorio(caminho: Path, resultado: pd.DataFrame, dias: list[date],
                        folds: list[tuple[list[date], list[date]]], total_trials: int,
                        limiar: float, origem: str,
                        promover_por_poder: bool = False) -> None:
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
        # Sem esta linha, um `inconclusivo` de origem "faltou fold" fica
        # indistinguivel de um de origem "promovido por poder" na leitura
        # de um relatorio antigo — e os dois significam coisas diferentes.
        "- regra de veredito: "
        + ("PRE-REGISTRO 3 (promocao por poder ATIVA, consistencia >= "
           f"{MIN_CONSISTENCIA_PODER})"
           if promover_por_poder else "classica (tres barras, sem promocao)"),
        "\n## Vereditos (regras pre-registradas em RESEARCH_PLANO.md)\n",
        "| feature | h | folds | IC medio | desvio | t | consist. | veredito |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for _, r in resultado.sort_values(["veredito", "t_stat"],
                                      ascending=[True, False]).iterrows():
        def _f(v: float, nd: int = 4) -> str:
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
