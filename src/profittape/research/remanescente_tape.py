"""
Expectativa remanescente a partir de τ, com `F` EXATO lido do tape.

Implementa LITERALMENTE o pre-registro 3 da Rota B, congelado em
2026-08-30d. Nenhuma escolha aqui e' livre: grade, fronteiras
temporais, criterio e regra de parada vieram congelados.

POR QUE UM MODULO NOVO, E NAO UMA EDICAO DE `remanescente.py`
------------------------------------------------------------
`remanescente.py` implementa o estimador REPROVADO pelo portao em
2026-08-29c (F = extremo da barra). Ele fica no repositorio, intacto,
porque o historico de um estimador invalido e' parte da auditoria — e
porque a comparacao entre os dois e' o que documenta a correcao.

A DIFERENCA QUE IMPORTA
-----------------------
La', `F` era o extremo da barra de cruzamento. O extremo de uma barra
so' e' conhecido quando ela FECHA: usa informacao do futuro dentro da
propria barra, e nao e' tempo de parada. Sobre ruido puro aquilo
devolveu +30 pontos com t entre 8 e 13.

Aqui, `F` e' o preco do PRIMEIRO NEGOCIO que atinge o nivel
(`preenchimento.localizar_toque`). Isso e' tempo de parada legitimo na
filtracao dos negocios, e pelo teorema da parada opcional, sob
martingal, `E[preco_final - F] = 0`.

O portao muda de papel: e' CONFIRMACAO DE IMPLEMENTACAO, nao descoberta
de vies. Se reprovar, o bug esta no codigo, nao no desenho.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
import structlog

from ..features import bars, flow
from .mae import _sinal_de_entrada
from .preenchimento import localizar_toque, preparar_tape
from .remanescente import _bootstrap_bloco, _uma_amostra_contra_zero
from .reversao import GRADE_X_CONGELADA, N_MINIMO_POR_PONTO
from .trials import limiar_deflacionado

log = structlog.get_logger(__name__)


def descobrir_volume_barra(features_parquet: Path,
                           barras: pd.DataFrame) -> tuple[int, str]:
    """
    Descobre o `volume_barra` usado ao gerar as features.

    POR QUE PRECISA DESCOBRIR
    -------------------------
    O portao monta barras de volume sobre o ruido e precisa da MESMA
    granularidade do real — geometria diferente compara outra coisa. Mas
    o valor so' era impresso na tela ao gerar as features, nunca gravado.
    Pedir ao operador um numero que so' existe no scroll de um terminal
    antigo e' defeito de desenho, nao falha de memoria dele.

    Duas fontes, nesta ordem:

    1. `resumo.json` ao lado do parquet (gravado a partir de 2026-08-30).
       Exato.
    2. INFERIDO de `vol_agr`. Uma barra de volume so' fecha quando a
       agressao acumulada cruza o limiar, entao todo `vol_agr >= limiar`
       e o MINIMO entre as barras e' o estimador mais proximo por cima.
       Aproximado, e reportado como tal.
    """
    resumo = features_parquet.parent / "resumo.json"
    if resumo.exists():
        dados = json.loads(resumo.read_text(encoding="utf-8"))
        if "volume_barra" in dados:
            return int(dados["volume_barra"]), "resumo.json (exato)"

    if "vol_agr" not in barras.columns:
        raise SystemExit(
            "sem resumo.json e sem coluna vol_agr: informe --volume-barra")
    minimo = int(barras["vol_agr"].min())
    return minimo, f"inferido de min(vol_agr)={minimo} (aproximado)"


def _com_dia(barras: pd.DataFrame) -> pd.DataFrame:
    """
    Mesma derivacao de `dia` usada em retornos.py, mae.py e quintis.py.
    Reproduzida e' melhor que reinventada: uma quinta definicao de "dia"
    no projeto seria uma quinta chance de divergir.
    """
    if "dia" not in barras.columns:
        barras = barras.copy()
        barras["dia"] = pd.to_datetime(
            barras["ts_close"], unit="ns", utc=True).dt.date
    return barras


def checagem_de_prevoo(df: pd.DataFrame, feature: str, horizonte: int,
                       threshold: float, direcao: str,
                       lado_permitido: str) -> dict[str, Any]:
    """
    BLOQUEANTE (pre-registro 3). Reconcilia a contagem da populacao.

    A rodada anulada deu 162 operacoes em 22 pregoes; a analise de MAE de
    2026-08-27 falava em 336 gatilhos em 26 dias. A hipotese natural e'
    que la' fossem compra+venda somados — mas o pre-registro exige
    CONFIRMAR, nao assumir: se a populacao mudou por outro motivo, nada
    mais no teste e' interpretavel.

    Devolve as contagens dos DOIS lados separadas, para a reconciliacao
    ser aritmetica em vez de argumentativa.
    """
    lado_series = _sinal_de_entrada(df[feature], threshold, direcao)
    validos: dict[str, int] = {}
    for rotulo, alvo in (("compra", 1), ("venda", -1)):
        idx = df.index[lado_series == alvo]
        n_ok = 0
        for i in idx:
            dia = df.at[i, "dia"]
            janela = df.loc[i + 1:i + horizonte]
            if len(janela[janela["dia"] == dia]) == horizonte:
                n_ok += 1
        validos[rotulo] = n_ok

    alvo = {"venda": -1, "compra": 1, "ambos": 0}[lado_permitido]
    usados = (validos["compra"] + validos["venda"] if alvo == 0
              else validos["compra" if alvo > 0 else "venda"])
    return {
        "pregoes": int(df["dia"].nunique()),
        "gatilhos_brutos": int((lado_series != 0).sum()),
        "validos_compra": validos["compra"],
        "validos_venda": validos["venda"],
        "validos_ambos": validos["compra"] + validos["venda"],
        "usados_neste_teste": usados,
        "lado_permitido": lado_permitido,
    }


def _remanescentes_tape(barras: pd.DataFrame, tape: pd.DataFrame,
                        feature: str, horizonte: int, threshold: float,
                        direcao: str, lado_permitido: str,
                        x: float) -> pd.DataFrame:
    """
    Uma linha por operacao que TOCA -x. Operacoes que nunca tocam sao
    EXCLUIDAS — nao ha grupo de comparacao, e' uma amostra contra zero.

    Fronteiras temporais como congeladas no pre-registro:
        ts_entrada = ts_close da barra t
        ts_limite  = ts_close da barra t+h
    Intervalo aberto no inicio (a entrada nao dispara o proprio stop) e
    janela que nunca atravessa o pregao.
    """
    lado_series = _sinal_de_entrada(barras[feature], threshold, direcao)
    alvo = {"venda": -1, "compra": 1, "ambos": 0}[lado_permitido]
    gatilhos = (barras.index[lado_series != 0] if alvo == 0
                else barras.index[lado_series == alvo])

    linhas: list[dict[str, Any]] = []
    for i in gatilhos:
        dia = barras.at[i, "dia"]
        lado = int(cast(Any, lado_series.at[i]))
        entrada = float(cast(Any, barras.at[i, "close"]))
        janela = barras.loc[i + 1:i + horizonte]
        janela = janela[janela["dia"] == dia]
        if len(janela) < horizonte:
            continue

        ts_entrada = int(cast(Any, barras.at[i, "ts_close"]))
        ts_limite = int(cast(Any, janela["ts_close"].iloc[-1]))
        nivel = entrada - x * lado      # venda: entrada+x ; compra: entrada-x

        toque = localizar_toque(tape, ts_entrada, ts_limite, nivel, lado)
        if toque is None:
            continue
        ts_toque, f = toque
        close_fim = float(cast(Any, janela["close"].iloc[-1]))

        linhas.append({
            "dia": dia,
            "lado": lado,
            # BRUTO de proposito: em τ a escolha e' sair ou segurar, e os
            # dois ramos pagam um giro. O custo cancela.
            "remanescente": (close_fim - f) * lado,
            "F": f,
            "overshoot": abs(f - nivel),
            # Diagnostico (nao criterio): fracao da janela ja' percorrida
            # quando o stop disparou.
            "fracao_da_janela": ((ts_toque - ts_entrada)
                                 / max(ts_limite - ts_entrada, 1)),
        })
    return pd.DataFrame(linhas)


def _avaliar_ponto(r: pd.DataFrame, x: float, limiar_z: float,
                   n_bootstrap: int, semente: int) -> dict[str, Any]:
    ponto: dict[str, Any] = {"x": x, "n": len(r)}
    ponto["n_suficiente"] = len(r) >= N_MINIMO_POR_PONTO
    v = r["remanescente"].to_numpy() if len(r) else np.array([])
    est = _uma_amostra_contra_zero(v)
    boot = (_bootstrap_bloco(r, "remanescente", n_bootstrap, semente)
            if len(r) >= 2 else {"ic95_baixo": float("nan"),
                                 "ic95_alto": float("nan")})
    ic_exclui_zero = bool(
        not math.isnan(boot["ic95_baixo"])
        and (boot["ic95_alto"] < 0 or boot["ic95_baixo"] > 0))
    ponto["media"] = est["media"]
    ponto["t"] = est["t"]
    ponto["ic95_baixo"] = boot["ic95_baixo"]
    ponto["ic95_alto"] = boot["ic95_alto"]
    ponto["overshoot_medio"] = (float(r["overshoot"].mean()) if len(r)
                                else float("nan"))
    ponto["fracao_da_janela_media"] = (float(r["fracao_da_janela"].mean())
                                       if len(r) else float("nan"))
    # Significancia exige AS DUAS evidencias, como congelado.
    ponto["sig"] = bool(
        ponto["n_suficiente"] and not math.isnan(est["t"])
        and abs(est["t"]) >= limiar_z and ic_exclui_zero)
    return ponto


def decidir(pontos: list[dict[str, Any]]) -> tuple[str, str]:
    """
    Implementa LITERALMENTE o criterio congelado.

    A monotonicidade nao e' mecanica: a grade e' aninhada (quem tocou
    -200 tocou -40 antes), o que garante que o `n` cai conforme X sobe,
    mas NAO que a media siga direcao alguma. Registrado no pre-registro
    antes de olhar qualquer numero.
    """
    significativos = [p for p in pontos if p["sig"]]
    if not significativos:
        curtos = [p["x"] for p in pontos if not p["n_suficiente"]]
        if curtos:
            return "INCONCLUSIVO", (
                f"nenhum ponto significativo, e n < {N_MINIMO_POR_PONTO} "
                f"em X={curtos}")
        return "CONTRA", (
            "nenhum X produz remanescente distinguivel de zero: o stop nao "
            "detecta reversao. So' se justifica como (a), controle de "
            "drawdown, com custo em expectativa medido a parte")

    negativos = [p for p in significativos if p["media"] < 0]
    positivos = [p for p in significativos if p["media"] > 0]

    if positivos and not negativos:
        return "INVERTIDO", (
            "remanescente significativamente POSITIVO: sair a -X destroi "
            "valor. Achado genuino; NAO autoriza aumentar posicao no "
            "adverso (piramide proibida por design)")
    if negativos and positivos:
        return "INCONCLUSIVO", "pontos significativos com sinais opostos"

    x_estrela = min(p["x"] for p in negativos)
    acima = [p for p in pontos if p["x"] >= x_estrela]
    if not all(p["media"] < 0 for p in acima):
        return "INCONCLUSIVO", (
            f"efeito presente em X*={x_estrela:.0f} mas NAO monotonico: "
            "ha X maior com media >= 0")
    if not all(p["n_suficiente"] for p in acima):
        return "INCONCLUSIVO", (
            f"monotonico a partir de X*={x_estrela:.0f}, mas n < "
            f"{N_MINIMO_POR_PONTO} em algum ponto acima")
    return "FAVORAVEL", (
        f"X*={x_estrela:.0f}: remanescente negativo, significativo e "
        "monotonico. X* e' CANDIDATO a stop, nunca decisao")


def rodar_grade(barras: pd.DataFrame, tape: pd.DataFrame, feature: str,
                horizonte: int, threshold: float, direcao: str,
                lado_permitido: str, limiar_z: float,
                n_bootstrap: int = 2000, semente: int = 20260830,
                ) -> list[dict[str, Any]]:
    pontos = []
    for x in GRADE_X_CONGELADA:
        r = _remanescentes_tape(barras, tape, feature, horizonte, threshold,
                                direcao, lado_permitido, x)
        pontos.append(_avaliar_ponto(r, x, limiar_z, n_bootstrap, semente))
        log.info("remanescente_tape.ponto", x=x, n=len(r))
    return pontos


def gerar_ruido(volume_barra: int, barras_por_dia: int = 100,
                negocios_por_barra: int = 200, n_dias: int = 100,
                tick: float = 5.0, preco_inicial: float = 140_000.0,
                semente: int = 20260830) -> pd.DataFrame:
    """
    Passeio aleatorio simetrico, negocio a negocio, sem edge nenhum.

    DUAS ESCALAS INDEPENDENTES, E CONFUNDI-LAS QUEBRA O PORTAO
    ----------------------------------------------------------
    - **Geometria do preco**: quantos NEGOCIOS cabem numa barra. Com
      passo de um tick, a amplitude vai com `tick * raiz(N)`, e ~200
      negocios poem a amplitude na faixa da grade de X (40 a 200 pts).
    - **Escala de volume**: quantos CONTRATOS fecham a barra. E' o
      `volume_barra` das features reais, e nao tem relacao nenhuma com a
      geometria.

    A primeira versao fixava 20.000 negocios de 1 contrato por pregao.
    Com o `volume_barra` real (119.504 no WINFUT), o dia inteiro somava
    20.000 de volume e **nenhuma barra fechava** — tudo virava parcial,
    era descartado, e o `groupby` vazio estourava dentro de
    `flow.calcular` com um erro do pandas que nao dizia nada sobre a
    causa.

    Corrigido separando as duas: o numero de negocios controla a
    geometria, e a QUANTIDADE por negocio e derivada de `volume_barra`
    para a barra fechar onde deve.
    """
    rng = np.random.default_rng(semente)
    quantidade = max(1, round(volume_barra / negocios_por_barra))
    negocios_por_dia = negocios_por_barra * barras_por_dia

    partes = []
    t0 = 0
    for d in range(n_dias):
        passos = rng.choice([-tick, tick], size=negocios_por_dia)
        precos = preco_inicial + np.cumsum(passos)
        partes.append(pd.DataFrame({
            "ts_ns": t0 + np.arange(negocios_por_dia, dtype=np.int64) * 1_000_000,
            "price": precos,
            "quantidade": np.full(negocios_por_dia, quantidade, dtype=np.int64),
            "trade_type": 2,
            "agente_comprador": 1,
            "agente_vendedor": 2,
            "dt": f"2026-01-{d + 1:02d}",
        }))
        t0 += 86_400 * 1_000_000_000
    df = pd.concat(partes, ignore_index=True)
    df["dt"] = pd.Categorical(df["dt"])
    return df


def portao_de_honestidade(volume_barra: int, horizonte: int, threshold: float,
                          direcao: str, lado_permitido: str, limiar_z: float,
                          n_dias: int = 100, semente: int = 20260830,
                          ) -> dict[str, Any]:
    """
    CONFIRMACAO DE IMPLEMENTACAO, nao descoberta de vies.

    A validade do estimador vem do teorema da parada opcional. Este
    portao verifica se o CODIGO corresponde ao teorema. Exigencia do
    pre-registro: veredito CONTRA sobre ruido puro. Qualquer outro
    reprova — e se reprovar, o bug esta aqui, nao no desenho.

    A feature de entrada e' ruido INDEPENDENTE do preco: se o gatilho
    carregasse informacao, o teste nao seria sobre zero edge.
    """
    tape_bruto = gerar_ruido(volume_barra=volume_barra, n_dias=n_dias,
                             semente=semente)
    barras_id, _ = bars.atribuir_barras(tape_bruto, volume_barra)
    if barras_id.empty:
        raise SystemExit(
            f"nenhuma barra de ruido fechou com volume_barra={volume_barra:,}. "
            "O gerador escala a quantidade por negocio a partir do "
            "volume_barra; se isto aconteceu, ha' incompatibilidade entre os "
            "dois — nao interprete nada."
        )
    barras = flow.calcular(barras_id, agentes=[], tick=5.0)
    barras = _com_dia(barras)

    # Feature de entrada e' ruido INDEPENDENTE do preco: se o gatilho
    # carregasse informacao, o teste deixaria de ser sobre zero edge.
    rng = np.random.default_rng(semente + 1)
    barras["z_ruido"] = rng.normal(size=len(barras))

    tape = preparar_tape(tape_bruto)
    pontos = rodar_grade(barras, tape, "z_ruido", horizonte, threshold,
                         direcao, lado_permitido, limiar_z, semente=semente)
    veredito, motivo = decidir(pontos)

    # UM PORTAO QUE NAO CONSEGUE PASSAR NAO E' PORTAO.
    #
    # `decidir` devolve INCONCLUSIVO quando algum ponto tem n < 30. Se a
    # amostra de ruido for pequena, o ponto mais esparso da grade (X=200,
    # que exige o maior deslocamento) nunca junta 30 operacoes — e o
    # veredito CONTRA fica inatingivel POR CONSTRUCAO, qualquer que seja
    # o estimador. Medido: com 25 dias de ruido, X=200 dava n=18 e o
    # portao reprovava um estimador comprovadamente calibrado.
    #
    # O default de 100 dias e' derivado disso, nao escolhido por
    # resultado: e' o que faz o ponto mais esparso passar de 30. Se algum
    # ponto ainda ficar curto, o problema e' de amostra sintetica e tem
    # que aparecer como ERRO, nao virar reprovacao silenciosa.
    curtos = [p["x"] for p in pontos if not p["n_suficiente"]]
    if curtos:
        raise SystemExit(
            f"amostra de ruido insuficiente em X={curtos} "
            f"(n < {N_MINIMO_POR_PONTO}). O portao nao pode reprovar por "
            "falta de dado sintetico: aumente `n_dias`."
        )

    return {
        "passou": veredito == "CONTRA",
        "veredito": veredito,
        "motivo": motivo,
        "pontos": pontos,
        "barras": len(barras),
    }


def rodar(features_parquet: Path, curated: Path, symbol: str,
          saida_dir: Path, feature: str = "z_agf_3", horizonte: int = 3,
          threshold: float = 1.4, direcao: str = "contrarian",
          lado_permitido: str = "venda", trials_previstos: int = 7,
          so_agressao: bool = True, volume_barra: int | None = None,
          n_dias_ruido: int = 25, semente: int = 20260830) -> dict[str, Any]:
    """
    Ordem OBRIGATORIA, na sequencia congelada no pre-registro:

      1. checagem de pre-voo   (BLOQUEANTE)
      2. portao de honestidade (BLOQUEANTE)
      3. so' entao o dado real

    A ordem esta no CODIGO, nao na disciplina de quem roda: se o pre-voo
    nao reconciliar ou o portao nao devolver CONTRA, a funcao levanta
    antes de tocar o estimador sobre dado real. Deixar isso a cargo de
    lembrar seria confiar no ponto exatamente onde este projeto ja'
    falhou antes.
    """
    from ..features.pipeline import _carregar_dia, _dias_do_symbol

    barras = _com_dia(pd.read_parquet(features_parquet))
    limiar_z = limiar_deflacionado(trials_previstos)

    # ---- 1. pre-voo (bloqueante) -------------------------------------
    prevoo = checagem_de_prevoo(barras, feature, horizonte, threshold,
                                direcao, lado_permitido)
    log.info("remanescente_tape.prevoo", **prevoo)

    # ---- 2. portao (bloqueante) --------------------------------------
    origem_vb = "informado na linha de comando"
    if volume_barra is None:
        volume_barra, origem_vb = descobrir_volume_barra(features_parquet,
                                                         barras)
    log.info("remanescente_tape.volume_barra", valor=volume_barra,
             origem=origem_vb)
    portao = portao_de_honestidade(volume_barra, horizonte, threshold,
                                   direcao, lado_permitido, limiar_z,
                                   n_dias=n_dias_ruido, semente=semente)
    log.info("remanescente_tape.portao", passou=portao["passou"],
             veredito=portao["veredito"])
    if not portao["passou"]:
        raise SystemExit(
            f"PORTAO REPROVOU (veredito {portao['veredito']} sobre ruido "
            f"puro): {portao['motivo']}\n"
            "O estimador e' nao-enviesado POR TEOREMA, entao reprovacao "
            "aqui indica bug de implementacao — nao interprete dado real."
        )

    # ---- 3. dado real -------------------------------------------------
    dias = _dias_do_symbol(curated / "trade", symbol)
    if not dias:
        raise SystemExit(f"nenhum trade de {symbol} — rode curate antes")
    tape = preparar_tape(
        pd.concat([_carregar_dia(p, symbol) for p in dias], ignore_index=True),
        so_agressao=so_agressao)
    log.info("remanescente_tape.tape", negocios=len(tape), dias=len(dias))

    pontos = rodar_grade(barras, tape, feature, horizonte, threshold,
                         direcao, lado_permitido, limiar_z, semente=semente)
    veredito, motivo = decidir(pontos)

    saida_dir.mkdir(parents=True, exist_ok=True)
    tabela = pd.DataFrame(pontos)
    tabela.to_csv(saida_dir / "rota_b_remanescente_tape.csv", index=False)

    return {
        "volume_barra": volume_barra,
        "volume_barra_origem": origem_vb,
        "prevoo": prevoo,
        "portao": {k: portao[k] for k in ("passou", "veredito", "motivo")},
        "limiar_deflacionado": round(limiar_z, 3),
        "so_agressao": so_agressao,
        "veredito": veredito,
        "motivo": motivo,
        "tabela": tabela,
    }
