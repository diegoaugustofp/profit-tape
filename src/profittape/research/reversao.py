"""
Teste da hipotese (b) do PRE-REGISTRO congelado em 2026-08-29
("existe reversao condicional em z_agf_3?", docs/RESEARCH_PLANO.md).

PERGUNTA: existe uma magnitude de excursao adversa X tal que, condicionado
a a posicao ter atingido -X pontos em algum momento da janela de holding, a
expectativa liquida remanescente ate' o fim da janela e' pior que a
expectativa das operacoes que NAO atingiram -X -- e pior de forma
sistematica (monotonica na grade), nao pontual?

O que isto NAO e': nao e' escolha de stop, nao e' mudanca de comportamento
do EA, nao testa alvo (alvo foi descartado como conceito para z_agf_3 na
revisao de desenho de 2026-08-29 -- incompativel com edge de cauda).

NAO consome trial: traducao economica condicional sobre um sinal JA'
validado pelo IC -- mesma familia de mae.py/quintis.py/risco_realizado.py
(regra 2 da skill profit-tape-disciplina). O limiar deflacionado usado aqui
corrige as 7 comparacoes DESTA grade; nao mexe em trials.json.

DECISOES METODOLOGICAS CONGELADAS (nao alterar sem pre-registro novo):
  - Excursao adversa medida INTRABAR (HIGH no lado vendido, LOW no
    comprado), nao por close. Correcao direta do erro de Rota B: mede-se do
    jeito que se pretende EXECUTAR (um stop real e' continuo), nao se
    executa do jeito que por acaso se mediu.
  - Resultado medido = P&L LIQUIDO no fechamento de t+horizonte, ou seja o
    que a Rota A de fato entrega. A pergunta e' "dado que tocou -X, o que a
    Rota A realiza no fim da janela?", nao "quanto um stop teria salvado".
  - Grade X fixada ANTES: {40, 60, 80, 100, 120, 150, 200}.
  - n < 30 no subgrupo => ponto REPORTADO mas marcado inconclusivo por
    construcao, nunca interpretado.
  - Todos os 7 pontos sao sempre reportados, inclusive os que nao deram
    nada -- reportar so' o melhor seria a mesma p-hacking que o
    pre-registro original de Rota B existia para evitar.

PONTO ESTATISTICO REGISTRADO (2026-08-29, ao implementar): o pre-registro
descreve a comparacao como "condicional vs INCONDICIONAL". Implementado
como "tocou -X" vs "NAO tocou -X" (grupos DISJUNTOS), porque o grupo
incondicional CONTEM o condicional -- um Welch entre subconjunto e
superconjunto tem amostras dependentes, subestima o erro padrao da
diferenca e infla o t (anti-conservador). A media incondicional continua
sendo reportada como referencia descritiva; o TESTE roda entre disjuntos.
Isto e' correcao de implementacao da mesma intencao, nao mudanca de
criterio -- registrado aqui explicitamente para nao virar ajuste silencioso.
"""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
import structlog

from .mae import _sinal_de_entrada
from .trials import limiar_deflacionado
from .walkforward import gerar_folds

log = structlog.get_logger(__name__)

# Grade CONGELADA pelo pre-registro de 2026-08-29. Alterar exige
# pre-registro novo, com secao e data proprias.
GRADE_X_CONGELADA: tuple[float, ...] = (40.0, 60.0, 80.0, 100.0, 120.0, 150.0, 200.0)

# Abaixo disto o ponto e' inconclusivo por construcao, nunca interpretado.
N_MINIMO_POR_PONTO = 30


def _p_valor_bicaudal(t: float) -> float:
    """P-valor bicaudal via normal padrao (erf) -- mesma funcao de
    quintis.py, replicada aqui para o modulo ser lido isolado."""
    return float(2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2)))))


def _welch(a: np.ndarray, b: np.ndarray) -> dict[str, float]:
    """
    Welch (variancias desiguais) da diferenca media_a - media_b.

    'a' = grupo que TOCOU -X, 'b' = grupo que NAO tocou. Sinal negativo da
    diferenca == o grupo condicionado e' PIOR, que e' a direcao prevista
    pela hipotese (b).
    """
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return {"diferenca": float("nan"), "t_welch": float("nan"),
                "gl_welch": float("nan"), "p_valor": float("nan")}
    var_a, var_b = float(a.var(ddof=1)), float(b.var(ddof=1))
    erro_padrao = math.sqrt(var_a / na + var_b / nb)
    diff = float(a.mean()) - float(b.mean())
    if erro_padrao <= 0:
        return {"diferenca": diff, "t_welch": float("nan"),
                "gl_welch": float("nan"), "p_valor": float("nan")}
    t = diff / erro_padrao
    gl = ((var_a / na + var_b / nb) ** 2
          / ((var_a / na) ** 2 / (na - 1) + (var_b / nb) ** 2 / (nb - 1)))
    return {"diferenca": diff, "t_welch": t, "gl_welch": gl,
            "p_valor": _p_valor_bicaudal(t)}


def _bootstrap_por_pregao(r: pd.DataFrame, coluna_grupo: str,
                          n_bootstrap: int, semente: int) -> dict[str, float]:
    """
    Bootstrap de BLOCO: reamostra PREGOES INTEIROS com reposicao, nunca
    operacoes individuais. Operacoes do mesmo dia sao dependentes (mesmo
    regime, mesma sazonalidade intradiaria em U ja' documentada no projeto);
    reamostrar operacao a operacao trataria essa dependencia como informacao
    independente e estreitaria o intervalo artificialmente.

    Devolve IC 95% percentil da diferenca (tocou - nao_tocou) e a fracao de
    replicas em cada lado de zero (p bicaudal empirico).
    """
    rng = np.random.default_rng(semente)
    dias = r["dia"].unique()
    por_dia = {d: r[r["dia"] == d] for d in dias}
    diffs: list[float] = []
    for _ in range(n_bootstrap):
        escolhidos = rng.choice(len(dias), size=len(dias), replace=True)
        amostra = pd.concat([por_dia[dias[k]] for k in escolhidos])
        a = amostra.loc[amostra[coluna_grupo], "pnl_liquido"].to_numpy()
        b = amostra.loc[~amostra[coluna_grupo], "pnl_liquido"].to_numpy()
        if len(a) < 2 or len(b) < 2:
            continue   # replica degenerada (grupo vazio) -- descartada
        diffs.append(float(a.mean() - b.mean()))
    if len(diffs) < n_bootstrap // 10:
        return {"ic95_baixo": float("nan"), "ic95_alto": float("nan"),
                "p_bootstrap": float("nan"), "n_replicas": len(diffs)}
    arr = np.array(diffs)
    frac_ge0 = float((arr >= 0).mean())
    return {
        "ic95_baixo": float(np.percentile(arr, 2.5)),
        "ic95_alto": float(np.percentile(arr, 97.5)),
        "p_bootstrap": float(2 * min(frac_ge0, 1 - frac_ge0)),
        "n_replicas": len(diffs),
    }


def _extrair_operacoes(df: pd.DataFrame, feature: str, horizonte: int,
                       threshold_entrada: float, direcao: str,
                       lado_permitido: str, custo_pontos: float) -> pd.DataFrame:
    """
    Uma linha por trigger com janela COMPLETA dentro do pregao: excursao
    adversa intrabar maxima e P&L liquido no fechamento de t+horizonte.
    """
    lado_series = _sinal_de_entrada(df[feature], threshold_entrada, direcao)
    lado_alvo = {"venda": -1, "compra": 1, "ambos": 0}[lado_permitido]
    triggers = (df.index[lado_series != 0] if lado_alvo == 0
                else df.index[lado_series == lado_alvo])

    linhas: list[dict[str, Any]] = []
    for i in triggers:
        dia = cast(date, df.at[i, "dia"])
        lado = int(cast(Any, lado_series.at[i]))
        entrada = float(cast(Any, df.at[i, "close"]))
        # Purge estrutural de dia inteiro: a janela nunca cruza o pregao
        # (mesma regra de retornos.py e mae.py). Janela incompleta =
        # descartada, nao completada com barra do dia seguinte.
        janela = df.loc[i + 1:i + horizonte]
        janela = janela[janela["dia"] == dia]
        if len(janela) < horizonte:
            continue

        # INTRABAR, nao close: HIGH machuca quem esta vendido, LOW machuca
        # quem esta comprado. Ver docstring do modulo.
        pior_preco = janela["low"] if lado > 0 else janela["high"]
        mae_intrabar = float(((entrada - pior_preco) * lado).max())
        pnl_liquido = float((janela["close"].iloc[-1] - entrada) * lado - custo_pontos)

        linhas.append({"dia": dia, "lado": lado, "mae_intrabar": mae_intrabar,
                       "pnl_liquido": pnl_liquido})
    return pd.DataFrame(linhas)


def analisar_reversao_condicional(
    arquivo_features: Path, feature: str, horizonte: int,
    threshold_entrada: float, direcao: str, custo_pontos: float,
    saida: Path, lado_permitido: str = "venda",
    grade_x: tuple[float, ...] = GRADE_X_CONGELADA,
    treino_min: int = 3, teste_dias: int = 2,
    n_bootstrap: int = 2000, semente: int = 20260829,
) -> dict[str, Any]:
    df = pd.read_parquet(arquivo_features)
    if "dia" not in df.columns:
        df["dia"] = pd.to_datetime(df["ts_close"], unit="ns", utc=True).dt.date

    # Pool out-of-sample, nunca a amostra inteira -- mesma disciplina de
    # quintis.py/mae.py (o bug real corrigido em mae.py em 2026-08-27 foi
    # exatamente rodar sobre a amostra cheia, contaminada com in-sample).
    dias = sorted(df["dia"].unique())
    folds = gerar_folds(dias, treino_min=treino_min, teste_dias=teste_dias)
    dias_teste: set[date] = set()
    for _treino, teste in folds:
        dias_teste.update(teste)
    df = df[df["dia"].isin(dias_teste)].reset_index(drop=True)

    r = _extrair_operacoes(df, feature, horizonte, threshold_entrada,
                           direcao, lado_permitido, custo_pontos)
    if r.empty:
        raise SystemExit(
            f"nenhuma operacao com janela completa para {feature}@h{horizonte} "
            f"threshold={threshold_entrada} direcao={direcao} lado={lado_permitido}"
        )

    n_total = len(r)
    media_incondicional = float(r["pnl_liquido"].mean())
    limiar_z = limiar_deflacionado(len(grade_x))
    alfa_bonferroni = 0.05 / len(grade_x)

    pontos: list[dict[str, Any]] = []
    for idx, x in enumerate(grade_x, start=1):
        coluna = "tocou"
        r[coluna] = r["mae_intrabar"] >= x
        a = r.loc[r[coluna], "pnl_liquido"].to_numpy()
        b = r.loc[~r[coluna], "pnl_liquido"].to_numpy()
        n_tocou, n_nao = len(a), len(b)

        w = _welch(a, b)
        boot = (_bootstrap_por_pregao(r, coluna, n_bootstrap, semente + idx)
                if n_tocou >= 2 and n_nao >= 2
                else {"ic95_baixo": float("nan"), "ic95_alto": float("nan"),
                      "p_bootstrap": float("nan"), "n_replicas": 0})

        n_suficiente = n_tocou >= N_MINIMO_POR_PONTO and n_nao >= N_MINIMO_POR_PONTO
        ic_exclui_zero = bool(
            not math.isnan(boot["ic95_baixo"])
            and (boot["ic95_alto"] < 0 or boot["ic95_baixo"] > 0)
        )
        # Significancia exige as DUAS evidencias: t acima do limiar
        # deflacionado das 7 comparacoes E intervalo de bloco que exclui
        # zero. A intersecao e' conservadora de proposito -- o bootstrap por
        # pregao e' quem trata a dependencia intradiaria, o Welch sozinho a
        # ignora.
        significativo = bool(
            n_suficiente
            and not math.isnan(w["t_welch"])
            and abs(w["t_welch"]) >= limiar_z
            and ic_exclui_zero
        )

        ponto = {
            "x": x,
            "n_tocou": n_tocou, "n_nao_tocou": n_nao,
            "pct_tocou": n_tocou / n_total,
            "media_tocou": float(a.mean()) if n_tocou else float("nan"),
            "media_nao_tocou": float(b.mean()) if n_nao else float("nan"),
            "n_suficiente": n_suficiente,
            "significativo": significativo,
            "ic_exclui_zero": ic_exclui_zero,
            **w, **boot,
        }
        pontos.append(ponto)
        log.info("reversao.ponto_grade", indice=f"{idx}/{len(grade_x)}", x=x,
                 n_tocou=n_tocou, media_tocou=round(ponto["media_tocou"], 2)
                 if n_tocou else None,
                 t_welch=round(w["t_welch"], 2) if not math.isnan(w["t_welch"]) else None,
                 significativo=significativo, n_suficiente=n_suficiente)

    r.drop(columns=["tocou"], inplace=True, errors="ignore")
    veredito, justificativa, x_estrela = _decidir(pontos)

    resumo: dict[str, Any] = {
        "feature": feature, "horizonte": horizonte,
        "threshold_entrada": threshold_entrada, "direcao": direcao,
        "lado_permitido": lado_permitido, "custo_pontos": custo_pontos,
        "n_operacoes": n_total,
        "n_dias": int(r["dia"].nunique()),
        "media_incondicional": media_incondicional,
        "grade_x": list(grade_x),
        "limiar_deflacionado": limiar_z,
        "alfa_bonferroni": alfa_bonferroni,
        "n_minimo_por_ponto": N_MINIMO_POR_PONTO,
        "pontos": pontos,
        "veredito": veredito,
        "justificativa": justificativa,
        "x_estrela": x_estrela,
    }
    resumo["relatorio"] = str(_escrever_relatorio(resumo, saida))
    return resumo


def _decidir(pontos: list[dict[str, Any]]) -> tuple[str, str, float | None]:
    """
    Implementa LITERALMENTE o criterio congelado no pre-registro de
    2026-08-29. Nao ha' criterio novo aqui, nem grau de liberdade: as tres
    condicoes de FAVORAVEL, e os dois desfechos alternativos.

      FAVORAVEL: existe X* com (1) media condicional negativa e
      significativa, (2) MONOTONICIDADE -- todos os X > X* tambem negativos,
      (3) n >= 30 em X* e em todos os pontos acima dele.

      CONTRA: nenhum X da grade produz diferenca significativa.

      INCONCLUSIVO: qualquer outra coisa (efeito nao monotonico, ou n
      insuficiente nos pontos que decidiriam).
    """
    algum_significativo = any(p["significativo"] for p in pontos)
    if not algum_significativo:
        pontos_curtos = [p["x"] for p in pontos if not p["n_suficiente"]]
        if pontos_curtos:
            return ("INCONCLUSIVO",
                    "nenhum ponto significativo, mas "
                    f"{len(pontos_curtos)} ponto(s) da grade ficaram abaixo de "
                    f"n={N_MINIMO_POR_PONTO} (X = "
                    f"{', '.join(f'{x:.0f}' for x in pontos_curtos)}) -- a "
                    "ausencia de efeito nesses X nao foi testada de verdade, "
                    "so' nao houve amostra. Acumular mais pregoes e rodar de "
                    "novo com a MESMA grade.",
                    None)
        return ("CONTRA (b)",
                "nenhum X da grade produz expectativa condicional "
                "distinguivel da dos que nao tocaram, com n suficiente em "
                "todos os pontos. (b) e' falso para este sinal: stop so' se "
                "justifica como (a), limite de perda -- e o custo em "
                "expectativa precisa de pre-registro proprio.",
                None)

    for i, p in enumerate(pontos):
        if not (p["significativo"] and p["media_tocou"] < 0):
            continue
        acima = pontos[i + 1:]
        if any(not q["n_suficiente"] for q in acima):
            continue
        if any(not (q["media_tocou"] < 0) for q in acima):
            continue
        return ("FAVORAVEL a (b)",
                f"X* = {p['x']:.0f} pts: media condicional "
                f"{p['media_tocou']:+.1f} pts (vs {p['media_nao_tocou']:+.1f} "
                f"nos que nao tocaram), significativa, com n={p['n_tocou']}, e "
                "todos os X maiores tambem negativos e com n suficiente "
                "(monotonicidade satisfeita). X* e' CANDIDATO a stop, NAO "
                "decisao -- a escolha do numero final esta explicitamente "
                "fora do pre-registro.",
                float(p["x"]))

    sig_positivos = [p for p in pontos if p["significativo"] and p["media_tocou"] > 0]
    if sig_positivos:
        return ("INCONCLUSIVO (direcao invertida)",
                "ha' ponto(s) significativo(s) mas na direcao OPOSTA a (b): "
                "a expectativa condicionada a ter tocado -X e' MAIOR, nao "
                "menor. E' exatamente a contra-hipotese contrarian registrada "
                "antes (num fade, movimento adverso pode melhorar a entrada). "
                "Achado genuino, deve ser registrado -- mas NAO autoriza "
                "aumentar posicao no adverso (pirimide, proibida por design). "
                "Exige pre-registro novo.",
                None)

    curtos = [p["x"] for p in pontos if not p["n_suficiente"]]
    detalhe_n = (
        f" Pontos abaixo de n={N_MINIMO_POR_PONTO} (nao interpretados): X = "
        f"{', '.join(f'{x:.0f}' for x in curtos)} — nesses X a ausencia de "
        "efeito nao foi testada, so' faltou amostra."
    ) if curtos else ""
    return ("INCONCLUSIVO",
            "ha' ponto(s) significativo(s) e negativo(s), mas a "
            "monotonicidade nao se sustenta ou faltou n nos pontos acima. Um "
            "X isolado numa grade de 7 e' o tipo de ruido que esta grade foi "
            "desenhada para nao confundir com estrutura (mesmo raciocinio que "
            "concluiu que Q4->Q5 era ruido e Q3->Q4 era degrau real). "
            "Registrar, nao decidir." + detalhe_n,
            None)


def _escrever_relatorio(resumo: dict[str, Any], saida: Path) -> Path:
    saida.mkdir(parents=True, exist_ok=True)
    arq = saida / "reversao_condicional.md"
    L: list[str] = [
        "# Reversao condicional — teste da hipotese (b)\n",
        "Executa o PRE-REGISTRO congelado em 2026-08-29 "
        "(`docs/RESEARCH_PLANO.md`). Nenhum criterio foi escolhido depois "
        "de ver estes numeros.\n",
        f"- sinal: {resumo['feature']} @ h={resumo['horizonte']}, "
        f"threshold={resumo['threshold_entrada']}, direcao={resumo['direcao']}",
        f"- lado: {resumo['lado_permitido']}   custo: "
        f"{resumo['custo_pontos']:.1f} pts",
        f"- operacoes (janela completa, out-of-sample): {resumo['n_operacoes']} "
        f"em {resumo['n_dias']} pregoes",
        f"- media INCONDICIONAL (referencia descritiva): "
        f"{resumo['media_incondicional']:+.2f} pts liquidos",
        f"- limiar deflacionado ({len(resumo['grade_x'])} comparacoes): "
        f"|t| >= {resumo['limiar_deflacionado']:.3f}  "
        f"(Bonferroni equivalente: alfa = {resumo['alfa_bonferroni']:.4f})",
        f"- n minimo por ponto: {resumo['n_minimo_por_ponto']} "
        "(abaixo disso o ponto e' reportado mas NAO interpretado)\n",
        "Excursao adversa medida INTRABAR (HIGH no vendido / LOW no "
        "comprado), nao por close — correcao direta do erro de desenho da "
        "Rota B. Resultado medido = P&L liquido no fechamento de "
        "t+horizonte, ou seja o que a Rota A de fato entrega.\n",
        "Teste entre grupos DISJUNTOS (tocou vs nao tocou), nao contra o "
        "incondicional que os contem — ver docstring de `reversao.py`.\n",
        "NAO consome trial.\n",
        "## Todos os pontos da grade\n",
        "Reportados TODOS, inclusive os que nao deram nada — reportar so' o "
        "melhor seria a p-hacking que este pre-registro existe para evitar.\n",
        "| X (pts) | n tocou | % | media tocou | media nao tocou | dif | "
        "t (Welch) | IC95 bloco | signif. |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for p in resumo["pontos"]:
        ic = ("—" if math.isnan(p["ic95_baixo"])
              else f"[{p['ic95_baixo']:+.1f}, {p['ic95_alto']:+.1f}]")
        marca = "SIM" if p["significativo"] else (
            f"n<{N_MINIMO_POR_PONTO}" if not p["n_suficiente"] else "nao")
        L.append(
            f"| {p['x']:.0f} | {p['n_tocou']} | {p['pct_tocou']:.0%} | "
            f"{p['media_tocou']:+.2f} | {p['media_nao_tocou']:+.2f} | "
            f"{p['diferenca']:+.2f} | {p['t_welch']:.2f} | {ic} | {marca} |"
        )
    L += [
        f"\n## VEREDITO: {resumo['veredito']}\n",
        resumo["justificativa"] + "\n",
        "## Regra de parada (do pre-registro)\n",
        "Proibido re-rodar com grade ajustada, threshold diferente, outro "
        "horizonte ou outro lado depois de ver este resultado. Se deu "
        "INCONCLUSIVO, a unica continuacao legitima e' acumular mais pregoes "
        "e rodar de novo com a MESMA grade. Grade nova exige pre-registro "
        "novo, do zero.\n",
        "## Fora deste teste\n",
        "- Escolha do numero final do stop (X* e' candidato, nao decisao).",
        "- Qualquer implementacao em `ea/risco.py`.",
        "- Alvo, em qualquer forma (descartado como conceito para este sinal).",
        "- Custo em expectativa do stop-como-(a) — pre-registro separado.",
    ]
    arq.write_text("\n".join(L), encoding="utf-8")
    return arq
