"""
Executa o PRE-REGISTRO 2 congelado em 2026-08-29b: "expectativa
remanescente a partir do toque" (docs/RESEARCH_PLANO.md).

PERGUNTA (a decisao que um stop realmente toma):

    No instante tau em que eu sairia a -X, qual a expectativa de
    CONTINUAR ate' o fim da janela?

A perda que ja' aconteceu ANTES de tau e' irrelevante para essa decisao
-- e era justamente ela que o estimador ANULADO (research/reversao.py)
contava, produzindo a tautologia `MAE_intrabar >= perda bruta final`.

Estimador: para cada operacao que toca -X dentro da janela,

    remanescente = (close_{t+h} - F) * lado

onde F e' o preenchimento do stop em tau. Operacoes que nunca tocam -X
sao EXCLUIDAS. Nao ha' grupo de comparacao -- e' uma pergunta de UMA
amostra contra zero, o que elimina de raiz o problema de subconjunto vs
superconjunto que contaminou o estimador anterior.

CUSTO MEDIDO BRUTO, de proposito: em tau escolhe-se entre sair e
segurar, e paga-se exatamente um giro nos dois ramos. O custo cancela.
Medir liquido aqui seria conta-lo duas vezes (e, com giro ~11 pts,
empurraria o resultado a favor de (b) de graca).

DOIS LIMITES DE F, com assimetria conhecida e registrada ANTES:
  - PRIMARIO, pessimista: F = extremo da barra de cruzamento (HIGH no
    vendido / LOW no comprado). Mede a partir de um preco pior, o que
    faz o remanescente parecer MAIS POSITIVO => conservador CONTRA (b).
  - SENSIBILIDADE, otimista: F = o proprio nivel do stop. Ignora o
    overshoot do cruzamento, o que faz o remanescente parecer MAIS
    NEGATIVO => anti-conservador, tende A FAVOR de (b).
O preco real de cruzamento fica ENTRE os dois, sempre (a barra cruzou,
mas nao se observa onde dentro dela). Por isso os limites bracketam.

PORTAO DE HONESTIDADE (obrigatorio, nao opcional): o mesmo estimador
roda sobre random walk puro e o resultado sai no MESMO relatorio do
dado real. Se o ruido produzir FAVORAVEL, a rodada real e' NULA. Esta
regra existe porque o estimador anterior estava congelado, parecia
rigoroso, e dava FAVORAVEL para nada -- congelar protege contra ajuste
de criterio, nao certifica que o metodo e' valido.

NAO consome trial: traducao economica condicional sobre sinal ja'
validado pelo IC (regra 2 da skill profit-tape-disciplina).
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
import structlog

from .mae import _sinal_de_entrada
from .reversao import GRADE_X_CONGELADA, N_MINIMO_POR_PONTO
from .trials import limiar_deflacionado
from .walkforward import gerar_folds

log = structlog.get_logger(__name__)


def _p_valor_bicaudal(t: float) -> float:
    return float(2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2)))))


def _uma_amostra_contra_zero(v: np.ndarray) -> dict[str, float]:
    """t de UMA amostra contra zero. Sem grupo de comparacao -- e' essa
    ausencia que elimina o vicio do estimador anterior."""
    n = len(v)
    if n < 2:
        return {"media": float("nan"), "t": float("nan"), "p_valor": float("nan")}
    sd = float(v.std(ddof=1))
    media = float(v.mean())
    if sd <= 0:
        return {"media": media, "t": float("nan"), "p_valor": float("nan")}
    t = media / (sd / math.sqrt(n))
    return {"media": media, "t": t, "p_valor": _p_valor_bicaudal(t)}


def _bootstrap_bloco(r: pd.DataFrame, coluna: str, n_bootstrap: int,
                     semente: int) -> dict[str, float]:
    """Reamostra PREGOES INTEIROS com reposicao, nunca operacoes
    individuais -- operacoes do mesmo dia sao dependentes."""
    rng = np.random.default_rng(semente)
    dias = r["dia"].unique()
    por_dia = {d: r.loc[r["dia"] == d, coluna].to_numpy() for d in dias}
    medias: list[float] = []
    for _ in range(n_bootstrap):
        k = rng.choice(len(dias), size=len(dias), replace=True)
        amostra = np.concatenate([por_dia[dias[j]] for j in k])
        if len(amostra) < 2:
            continue
        medias.append(float(amostra.mean()))
    if len(medias) < n_bootstrap // 10:
        return {"ic95_baixo": float("nan"), "ic95_alto": float("nan")}
    arr = np.array(medias)
    return {"ic95_baixo": float(np.percentile(arr, 2.5)),
            "ic95_alto": float(np.percentile(arr, 97.5))}


def _remanescentes(df: pd.DataFrame, feature: str, horizonte: int,
                   threshold_entrada: float, direcao: str,
                   lado_permitido: str, x: float) -> pd.DataFrame:
    """
    Uma linha por operacao que TOCA -x dentro da janela. Devolve o
    remanescente BRUTO nos dois limites de F, e a barra do cruzamento.
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
        # Purga estrutural de dia inteiro: janela nunca cruza o pregao.
        janela = df.loc[i + 1:i + horizonte]
        janela = janela[janela["dia"] == dia]
        if len(janela) < horizonte:
            continue

        nivel = entrada - x * lado          # venda: entrada+x ; compra: entrada-x
        extremo = janela["high"] if lado < 0 else janela["low"]
        cruzou = (extremo >= nivel) if lado < 0 else (extremo <= nivel)
        if not bool(cruzou.any()):
            continue                        # nunca tocou -x: EXCLUIDA
        pos = int(np.argmax(cruzou.to_numpy()))
        f_pessimista = float(extremo.iloc[pos])
        f_otimista = nivel
        close_fim = float(janela["close"].iloc[-1])

        linhas.append({
            "dia": dia, "lado": lado, "barra_cruzamento": pos + 1,
            # BRUTO de proposito: o custo cancela entre sair e segurar.
            "rem_pessimista": (close_fim - f_pessimista) * lado,
            "rem_otimista": (close_fim - f_otimista) * lado,
        })
    return pd.DataFrame(linhas)


def _avaliar_ponto(r: pd.DataFrame, x: float, limiar_z: float,
                   n_bootstrap: int, semente: int) -> dict[str, Any]:
    ponto: dict[str, Any] = {"x": x, "n": len(r)}
    ponto["n_suficiente"] = len(r) >= N_MINIMO_POR_PONTO
    ponto["barra_cruzamento_media"] = (float(r["barra_cruzamento"].mean())
                                       if len(r) else float("nan"))
    for rotulo, coluna in (("pess", "rem_pessimista"), ("otim", "rem_otimista")):
        v = r[coluna].to_numpy() if len(r) else np.array([])
        est = _uma_amostra_contra_zero(v)
        boot = (_bootstrap_bloco(r, coluna, n_bootstrap, semente)
                if len(r) >= 2 else {"ic95_baixo": float("nan"),
                                     "ic95_alto": float("nan")})
        ic_exclui_zero = bool(
            not math.isnan(boot["ic95_baixo"])
            and (boot["ic95_alto"] < 0 or boot["ic95_baixo"] > 0))
        ponto[f"media_{rotulo}"] = est["media"]
        ponto[f"t_{rotulo}"] = est["t"]
        ponto[f"ic95_baixo_{rotulo}"] = boot["ic95_baixo"]
        ponto[f"ic95_alto_{rotulo}"] = boot["ic95_alto"]
        # Significancia exige as duas evidencias: |t| acima do limiar
        # deflacionado das 7 comparacoes E IC de bloco excluindo zero.
        ponto[f"sig_{rotulo}"] = bool(
            ponto["n_suficiente"] and not math.isnan(est["t"])
            and abs(est["t"]) >= limiar_z and ic_exclui_zero)
    return ponto


def _decidir(pontos: list[dict[str, Any]]) -> tuple[str, str, float | None]:
    """Implementa LITERALMENTE o criterio congelado no pre-registro 2."""
    algum_sig = any(p["sig_pess"] or p["sig_otim"] for p in pontos)
    if not algum_sig:
        curtos = [p["x"] for p in pontos if not p["n_suficiente"]]
        if curtos:
            return ("INCONCLUSIVO",
                    "nenhum ponto significativo, mas "
                    f"{len(curtos)} ponto(s) ficaram abaixo de n="
                    f"{N_MINIMO_POR_PONTO} (X = "
                    f"{', '.join(f'{x:.0f}' for x in curtos)}) — nesses X a "
                    "ausencia de efeito nao foi testada, so' faltou amostra.",
                    None)
        return ("CONTRA (b)",
                "nenhum X produz remanescente distinguivel de zero. O stop "
                "NAO detecta reversao: sair em -X nem ajuda nem atrapalha a "
                "expectativa. (b) e' falso para este sinal, e o stop so' se "
                "justifica como (a), limite de perda — cujo custo em "
                "expectativa exige pre-registro proprio.",
                None)

    for i, p in enumerate(pontos):
        favoravel = (p["sig_pess"] and p["sig_otim"]
                     and p["media_pess"] < 0 and p["media_otim"] < 0)
        if not favoravel:
            continue
        acima = pontos[i + 1:]
        if any(not q["n_suficiente"] for q in acima):
            continue
        if any(not (q["media_pess"] < 0 and q["media_otim"] < 0) for q in acima):
            continue
        return ("FAVORAVEL a (b)",
                f"X* = {p['x']:.0f} pts: remanescente medio negativo e "
                f"significativo nos DOIS limites de F "
                f"(pessimista {p['media_pess']:+.1f}, otimista "
                f"{p['media_otim']:+.1f} pts brutos), n={p['n']}, e todos os X "
                "maiores tambem negativos nos dois limites. O limite "
                "pessimista trabalha CONTRA (b) e ainda assim nao o matou — "
                "por isso o achado e' robusto. X* e' CANDIDATO a stop, NAO "
                "decisao.",
                float(p["x"]))

    invertidos = [p for p in pontos
                  if p["sig_pess"] and p["sig_otim"]
                  and p["media_pess"] > 0 and p["media_otim"] > 0]
    if invertidos:
        p = invertidos[0]
        return ("INVERTIDO",
                f"em X = {p['x']:.0f} pts o remanescente e' significativamente "
                f"POSITIVO nos dois limites (pessimista {p['media_pess']:+.1f}, "
                f"otimista {p['media_otim']:+.1f}). O limite otimista trabalha "
                "A FAVOR de (b) e ainda assim saiu positivo — sair em -X "
                "destroi valor. E' a contra-hipotese contrarian registrada "
                "antes: num fade, movimento adverso pode melhorar a entrada. "
                "Achado genuino, mas NAO autoriza aumentar posicao no adverso "
                "(piramide, proibida por design). Exige pre-registro novo.",
                None)

    discordantes = [p["x"] for p in pontos
                    if p["sig_pess"] and p["sig_otim"]
                    and (p["media_pess"] > 0) != (p["media_otim"] > 0)]
    if discordantes:
        return ("INCONCLUSIVO POR PREENCHIMENTO",
                "os dois limites de F sao significativos mas com SINAIS "
                f"DIFERENTES em X = {', '.join(f'{x:.0f}' for x in discordantes)}"
                " — a resposta depende de onde dentro da barra o cruzamento "
                "ocorreu. Escalonamento ja' definido no pre-registro: SO' "
                "agora vale construir a leitura de F exato a partir do tape "
                "trade a trade. Nao antes.",
                None)

    curtos = [p["x"] for p in pontos if not p["n_suficiente"]]
    detalhe = (f" Pontos abaixo de n={N_MINIMO_POR_PONTO}: X = "
               f"{', '.join(f'{x:.0f}' for x in curtos)}." if curtos else "")
    return ("INCONCLUSIVO",
            "ha' significancia em algum ponto, mas nao nos dois limites de F "
            "simultaneamente, ou a monotonicidade nao se sustenta, ou faltou "
            "n nos pontos acima. Um X isolado numa grade de 7 e' ruido que "
            "esta grade foi desenhada para nao confundir com estrutura. "
            "Registrar, nao decidir." + detalhe,
            None)


def _rodar_grade(df: pd.DataFrame, feature: str, horizonte: int,
                 threshold_entrada: float, direcao: str, lado_permitido: str,
                 grade_x: tuple[float, ...], limiar_z: float,
                 n_bootstrap: int, semente: int,
                 etiqueta: str) -> tuple[list[dict[str, Any]], str, str, float | None]:
    pontos: list[dict[str, Any]] = []
    for idx, x in enumerate(grade_x, start=1):
        r = _remanescentes(df, feature, horizonte, threshold_entrada,
                           direcao, lado_permitido, x)
        p = _avaliar_ponto(r, x, limiar_z, n_bootstrap, semente + idx)
        pontos.append(p)
        log.info("remanescente.ponto_grade", etiqueta=etiqueta,
                 indice=f"{idx}/{len(grade_x)}", x=x, n=p["n"],
                 media_pess=round(p["media_pess"], 2) if p["n"] else None,
                 media_otim=round(p["media_otim"], 2) if p["n"] else None,
                 sig_pess=p["sig_pess"], sig_otim=p["sig_otim"])
    veredito, justificativa, x_estrela = _decidir(pontos)
    return pontos, veredito, justificativa, x_estrela


def _razao_amplitude(df: pd.DataFrame) -> float:
    """
    amplitude media da barra / desvio das variacoes de close, medido
    DENTRO do pregao. A variacao entre o ultimo close de um dia e o
    primeiro do dia seguinte nao e' movimento de mercado observado nesta
    serie -- inclui-la infla o denominador e faz a razao parecer menor
    do que e'. (Peguei isto medindo errado da primeira vez.)

    Num passeio aleatorio a razao vale ~1.596. Razao real MAIOR significa
    barras com mais vaivem interno do que passeio puro produz -- e' o
    ingrediente que alimenta o vies do limite pessimista.
    """
    d = df.groupby("dia")["close"].diff().std()
    if not d or math.isnan(float(d)) or float(d) <= 0:
        return float("nan")
    return float((df["high"] - df["low"]).mean() / float(d))


def gerar_ruido_calibrado(df_real: pd.DataFrame, n_dias: int, barras_por_dia: int,
                          semente: int, sub_passos: int = 40) -> pd.DataFrame:
    """
    Random walk PURO com a MESMA escala do dado real, e — decisivo — com
    caminho COERENTE: cada barra e' simulada em `sub_passos` sub-passos e
    o high/low sao os extremos REAIS desse caminho, que contem o close.

    A primeira versao deste gerador sorteava a amplitude da barra por
    fora, independente do passeio. Isso produzia barras cujo high jamais
    foi visitado por caminho nenhum, e o portao acusava vies onde nao
    havia (e escondia o vies que havia). Um portao de honestidade so'
    vale se o ruido for um caminho de preco de verdade.

    Calibra so' a ESCALA (desvio das variacoes de close); nenhuma
    ESTRUTURA e' importada — drift zero, feature independente do preco.

    Nota registrada: num passeio aleatorio, amplitude media / sd(dclose)
    fica fixa em ~1.596 (E[max-min] = sqrt(8/pi)*sigma). Se o dado real
    tiver razao MAIOR, o ruido subestima a amplitude e portanto
    SUBESTIMA o vies do limite pessimista — o portao fica conservador,
    nunca otimista. A razao real e' reportada junto.
    """
    rng = np.random.default_rng(semente)
    passo_sd = float(df_real["close"].diff().std())
    sd_tick = passo_sd / math.sqrt(sub_passos)
    base = float(df_real["close"].median())

    blocos = []
    for k in range(n_dias):
        m = barras_por_dia * sub_passos
        ticks = base + np.cumsum(rng.normal(0.0, sd_tick, m))   # drift ZERO
        t = ticks.reshape(barras_por_dia, sub_passos)
        blocos.append(pd.DataFrame({
            "dia": [date(2000, 1, 1) + timedelta(days=k)] * barras_por_dia,
            "feature_ruido": rng.normal(0.0, 1.0, barras_por_dia),
            "close": t[:, -1], "high": t.max(axis=1), "low": t.min(axis=1),
        }))
    return pd.concat(blocos, ignore_index=True)


def portao_de_honestidade(df_real: pd.DataFrame, horizonte: int,
                          threshold_entrada: float, direcao: str,
                          lado_permitido: str, grade_x: tuple[float, ...],
                          limiar_z: float, n_bootstrap: int, semente: int,
                          n_dias: int = 80,
                          barras_por_dia: int = 150) -> dict[str, Any]:
    """
    PORTAO OBRIGATORIO. Roda o MESMO estimador sobre ruido puro. Se o
    veredito for FAVORAVEL, a rodada real e' NULA e nao se interpreta.
    """
    ruido = gerar_ruido_calibrado(df_real, n_dias, barras_por_dia, semente)
    pontos, veredito, justificativa, _ = _rodar_grade(
        ruido, "feature_ruido", horizonte, threshold_entrada, direcao,
        lado_permitido, grade_x, limiar_z, n_bootstrap, semente, "portao")

    # O pre-registro 2 escreveu o portao como "reprova se der FAVORAVEL".
    # Isso e' estreito demais, e o proprio portao mostrou por que: sobre
    # ruido puro o estimador devolveu INCONCLUSIVO POR PREENCHIMENTO, que
    # no criterio congelado MANDA construir a leitura do tape. Ou seja, o
    # ruido sozinho dispara uma escalada de infraestrutura. Um estimador
    # calibrado tem que devolver CONTRA (b) -- "nada aqui" -- quando nao
    # ha' nada. Qualquer outro veredito sobre ruido e' reprovacao.
    passou = veredito == "CONTRA (b)"
    return {"pontos": pontos, "veredito": veredito,
            "justificativa": justificativa, "passou": passou,
            "razao_amplitude_ruido": _razao_amplitude(ruido),
            "razao_amplitude_real": _razao_amplitude(df_real),
            "n_dias": n_dias, "barras_por_dia": barras_por_dia}


def analisar_remanescente(
    arquivo_features: Path, feature: str, horizonte: int,
    threshold_entrada: float, direcao: str, saida: Path,
    lado_permitido: str = "venda",
    grade_x: tuple[float, ...] = GRADE_X_CONGELADA,
    treino_min: int = 3, teste_dias: int = 2,
    n_bootstrap: int = 2000, semente: int = 20260829,
) -> dict[str, Any]:
    df = pd.read_parquet(arquivo_features)
    if "dia" not in df.columns:
        df["dia"] = pd.to_datetime(df["ts_close"], unit="ns", utc=True).dt.date

    dias = sorted(df["dia"].unique())
    folds = gerar_folds(dias, treino_min=treino_min, teste_dias=teste_dias)
    dias_teste: set[date] = set()
    for _treino, teste in folds:
        dias_teste.update(teste)
    df = df[df["dia"].isin(dias_teste)].reset_index(drop=True)

    limiar_z = limiar_deflacionado(len(grade_x))

    # O portao roda ANTES e o resultado sai no mesmo relatorio, sempre.
    portao = portao_de_honestidade(df, horizonte, threshold_entrada, direcao,
                                   lado_permitido, grade_x, limiar_z,
                                   max(n_bootstrap // 4, 200), semente + 999)
    log.info("remanescente.portao", veredito=portao["veredito"],
             passou=portao["passou"])

    pontos, veredito, justificativa, x_estrela = _rodar_grade(
        df, feature, horizonte, threshold_entrada, direcao, lado_permitido,
        grade_x, limiar_z, n_bootstrap, semente, "real")

    if not portao["passou"]:
        veredito = "NULO — PORTAO DE HONESTIDADE REPROVOU"
        justificativa = (
            f"sobre RUIDO PURO, sem edge nenhum, o estimador devolveu "
            f"'{portao['veredito']}' em vez de 'CONTRA (b)'. O resultado real "
            "abaixo NAO se interpreta, qualquer que seja. Foi exatamente "
            "assim que o estimador de `reversao.py` produziu um X* falso em "
            "2026-08-29 — a diferenca e' que desta vez o defeito foi pego "
            "ANTES de qualquer numero real ser olhado.")
        x_estrela = None

    resumo: dict[str, Any] = {
        "feature": feature, "horizonte": horizonte,
        "threshold_entrada": threshold_entrada, "direcao": direcao,
        "lado_permitido": lado_permitido,
        "n_dias": int(df["dia"].nunique()),
        "grade_x": list(grade_x), "limiar_deflacionado": limiar_z,
        "n_minimo_por_ponto": N_MINIMO_POR_PONTO,
        "portao": portao, "pontos": pontos, "veredito": veredito,
        "justificativa": justificativa, "x_estrela": x_estrela,
    }
    resumo["relatorio"] = str(_escrever_relatorio(resumo, saida))
    return resumo


def _tabela(pontos: list[dict[str, Any]]) -> list[str]:
    L = ["| X (pts) | n | barra cruz. | rem. PESSIMISTA | t | rem. OTIMISTA | "
         "t | situacao |", "|---|---|---|---|---|---|---|---|"]
    for p in pontos:
        if not p["n"]:
            L.append(f"| {p['x']:.0f} | 0 | — | — | — | — | — | sem operacao |")
            continue
        sit = (f"n<{N_MINIMO_POR_PONTO}" if not p["n_suficiente"]
               else ("ambos SIG" if p["sig_pess"] and p["sig_otim"]
                     else ("so' pessimista" if p["sig_pess"]
                           else ("so' otimista" if p["sig_otim"] else "-"))))
        L.append(
            f"| {p['x']:.0f} | {p['n']} | {p['barra_cruzamento_media']:.2f} | "
            f"{p['media_pess']:+.2f} | {p['t_pess']:.2f} | "
            f"{p['media_otim']:+.2f} | {p['t_otim']:.2f} | {sit} |")
    return L


def _escrever_relatorio(resumo: dict[str, Any], saida: Path) -> Path:
    saida.mkdir(parents=True, exist_ok=True)
    arq = saida / "remanescente_apos_toque.md"
    portao = resumo["portao"]
    L: list[str] = [
        "# Expectativa remanescente a partir do toque\n",
        "Executa o PRE-REGISTRO 2 congelado em 2026-08-29b "
        "(`docs/RESEARCH_PLANO.md`). Substitui o estimador ANULADO de "
        "`reversao.py`, que tinha a tautologia `MAE_intrabar >= perda "
        "bruta final` embutida.\n",
        f"- sinal: {resumo['feature']} @ h={resumo['horizonte']}, "
        f"threshold={resumo['threshold_entrada']}, "
        f"direcao={resumo['direcao']}, lado={resumo['lado_permitido']}",
        f"- pregoes out-of-sample: {resumo['n_dias']}",
        f"- limiar deflacionado ({len(resumo['grade_x'])} comparacoes): "
        f"|t| >= {resumo['limiar_deflacionado']:.3f}",
        f"- n minimo por ponto: {resumo['n_minimo_por_ponto']}\n",
        "Remanescente = `(close_fim - F) * lado`, medido em pontos BRUTOS "
        "de proposito: em tau paga-se um giro tanto para sair quanto para "
        "segurar, entao o custo cancela. Operacoes que nunca tocam -X sao "
        "excluidas; nao ha' grupo de comparacao.\n",
        "F em dois limites: PESSIMISTA = extremo da barra de cruzamento "
        "(conservador CONTRA (b)); OTIMISTA = nivel do stop "
        "(anti-conservador, tende A FAVOR de (b)). O preco real de "
        "cruzamento fica entre os dois.\n",
        "NAO consome trial.\n",
        "## PORTAO DE HONESTIDADE (roda antes, sempre)\n",
        f"Mesmo estimador sobre RANDOM WALK PURO — drift zero, feature "
        f"independente do preco, escala calibrada no dado real "
        f"({portao['n_dias']} dias x {portao['barras_por_dia']} barras).\n",
        f"**{'PASSOU' if portao['passou'] else 'REPROVOU'}** — veredito sobre "
        f"ruido: `{portao['veredito']}`\n",
    ]
    L += _tabela(portao["pontos"])
    L += [
        "\nSob martingal, pela parada opcional, E[S_fim - S_tau] = 0: um "
        "estimador correto devolve ~0 aqui. O limite otimista tende a sair "
        "levemente NEGATIVO mesmo no ruido, porque mede a partir do nivel e "
        "ignora o overshoot do cruzamento — vies conhecido e registrado "
        "antes. E' exatamente por isso que o veredito exige os DOIS limites.\n",
        "## Resultado sobre o dado real\n",
    ]
    if not portao["passou"]:
        L.append("> **NAO INTERPRETAR.** O portao reprovou; a tabela abaixo "
                 "fica registrada apenas para rastro.\n")
    L += _tabela(resumo["pontos"])
    L += [
        f"\n## VEREDITO: {resumo['veredito']}\n",
        resumo["justificativa"] + "\n",
        "## Regra de parada (do pre-registro)\n",
        "Proibido re-rodar com grade ajustada, threshold, horizonte ou lado "
        "diferentes depois de ver este resultado. INCONCLUSIVO so' se "
        "continua acumulando pregoes com a MESMA grade e o MESMO estimador. "
        "Estimador novo exige pre-registro novo.\n",
        "## Fora deste teste\n",
        "- Escolha do numero final do stop (X* e' candidato, nunca decisao).",
        "- Qualquer implementacao em `ea/risco.py`.",
        "- Alvo, em qualquer forma.",
        "- Custo em expectativa do stop-como-(a) — pre-registro separado.",
    ]
    arq.write_text("\n".join(L), encoding="utf-8")
    return arq
