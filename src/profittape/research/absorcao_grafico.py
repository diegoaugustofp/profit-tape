"""
Le' o log `ABSBARRA|` do grafico e roda o pre-registro congelado nele.

PARA QUE ISTO EXISTE
--------------------
O teste de absorcao deu INCONCLUSIVO sobre os 25 pregoes capturados (28
e 20 eventos, minimo 30). Esperar acumular custaria ~12 pregoes.

O grafico tem historico profundo e o evento so' precisa de OHLC +
volume TOTAL de agressao — que `QuantityVol(False, True)` entrega em
anos, ao contrario de `AgressionVolBuy/Sell` (retido por uma semana).

Decisao do operador (2026-08-31): tratar o historico do grafico como
**amostra INDEPENDENTE**, nao como continuacao do pool. Um tiro, com o
pre-registro ja' congelado, consumindo trial. Duas amostras separadas
que concordem valem mais que uma maior.

REGRA QUE ACOMPANHA
-------------------
O periodo dumpado NAO pode se sobrepor a 24/07-27/08, que ja' esta no
parquet. Sobreposicao criaria dado duplicado com medicao ligeiramente
diferente, e destruiria a independencia que e' a unica razao de usar
esta fonte.

A funcao `checar_sobreposicao` recusa antes de rodar.

O QUE E' RECALCULADO, E POR QUE
-------------------------------
O `.ntsl` ja' loga `desloc_norm`, `z_amp`, `z_vol` e `mov_contexto`. Aqui
eles sao **recalculados em Python** a partir do OHLC e do volume, e os
valores logados servem de CONFERENCIA.

E' o mesmo desenho da equivalencia NTSL de 2026-08-31: usar o numero
logado seria confiar que os dois lados concordam; recalcular e comparar
MEDE se concordam. Em 2026-08-31 essa distincao pegou que o indicador
emitia 17 campos enquanto o parser exigia 18, com a suite verde.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog

log = structlog.get_logger(__name__)

PREFIXO = "ABSBARRA|"

# Ordem CONGELADA, igual a' do `ntsl/absorcao_barra.ntsl`. Mudar exige
# mudar nos DOIS lados na mesma entrega.
CAMPOS = [
    "data", "hora", "hora_bolsa",
    "open", "high", "low", "close",
    "vol_total", "vol_agr",
    "desloc_norm_ntsl", "z_amplitude_ntsl", "z_vol_agr_ntsl",
    "mov_contexto_ntsl", "lado_ntsl",
]

# Periodo ja' presente em `data/features_tempo` (25 pregoes).
CURATED_INICIO = pd.Timestamp("2026-07-24").date()
CURATED_FIM = pd.Timestamp("2026-08-27").date()


def _numero(txt: str) -> float:
    """
    Formato pt-BR do Profit: milhar com ponto, decimal com virgula.

    Devolver NaN em silencio aqui seria pior que falhar: o campo sumiria
    das estatisticas em vez de acusar. Foi um erro real em 2026-08-30.
    """
    t = txt.strip()
    if not t:
        raise ValueError("campo vazio")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    return float(t)


def carregar_log(caminho: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not caminho.exists():
        raise SystemExit(f"nao achei {caminho}")
    bruto = caminho.read_text(encoding="utf-8", errors="replace")
    linhas = [x.strip().replace("\r", "") for x in bruto.splitlines()
              if PREFIXO in x]
    if not linhas:
        pistas = []
        if "ABSDIAG|" in bruto:
            pistas.append(
                "  Ha' linhas ABSDIAG: o `LogDiagnostico` ficou em 1, e "
                "nesse modo\n"
                "  o indicador NAO emite ABSBARRA. Ponha LogDiagnostico(0) "
                "e redumpe.")
        if "ABSDIR|" in bruto:
            pistas.append(
                "  Ha' linhas ABSDIR: o grafico esta com o "
                "`absorcao_dir.ntsl`,\n"
                "  que implementa a formula ANTIGA. Cole o "
                "`absorcao_barra.ntsl`.")
        if "ABSVIDA|" in bruto and not pistas:
            pistas.append(
                "  Ha' ABSVIDA (o indicador rodou), mas nenhuma barra "
                "passou na\n"
                "  janela de data. Confira LogDataInicio/LogDataFim no "
                "formato 1AnoMesDia.")
        if not pistas:
            pistas.append(
                "  Nem ABSVIDA aparece: o indicador nao compilou ou nao "
                "esta aplicado\n"
                "  no grafico.")
        raise SystemExit(
            f"nenhuma linha '{PREFIXO}' em {caminho}.\n" + "\n".join(pistas))

    registros, larguras = [], set()
    for linha in linhas:
        campos = linha.split(PREFIXO, 1)[1].split("|")
        larguras.add(len(campos))
        if len(campos) != len(CAMPOS):
            continue
        registros.append(campos)

    if len(larguras) != 1 or len(CAMPOS) not in larguras:
        vistas = sorted(larguras)
        faltando = ""
        if vistas and vistas[-1] < len(CAMPOS):
            faltando = ("\n  Faltam os campos: "
                        + ", ".join(CAMPOS[vistas[-1]:]))
        raise SystemExit(
            f"formato incompativel em {caminho}:\n"
            f"  vi {vistas} campos DEPOIS do prefixo '{PREFIXO}', "
            f"esperava {len(CAMPOS)}.\n"
            f"  Atencao: a LINHA tem um token a mais, porque o proprio\n"
            f"  'ABSBARRA' conta na separacao por '|'.{faltando}"
        )

    df = pd.DataFrame(registros, columns=CAMPOS)
    for c in CAMPOS[3:]:
        df[c] = df[c].map(_numero)
    # Date do NTSL vem em 1AnoMesDia (ano deslocado de 1900).
    d = df["data"].astype(int)
    df["dia"] = pd.to_datetime(
        (1900 + d // 10000).astype(str) + "-"
        + ((d // 100) % 100).astype(str).str.zfill(2) + "-"
        + (d % 100).astype(str).str.zfill(2)).dt.date
    df["hora_int"] = df["hora"].astype(int)
    df = df.sort_values(["dia", "hora_int"]).reset_index(drop=True)

    n_dup = int(df.duplicated(["dia", "hora_int"]).sum())
    if n_dup:
        raise SystemExit(
            f"{n_dup} barras duplicadas (mesmo dia e hora) em {caminho}.\n"
            "  Dumps sobrepostos duplicam barras e inflam o n sem "
            "acrescentar informacao."
        )
    return df, {"linhas": len(linhas), "barras": len(df),
                "pregoes": int(df["dia"].nunique()),
                "inicio": str(df["dia"].min()), "fim": str(df["dia"].max())}


def checar_sobreposicao(df: pd.DataFrame) -> None:
    """
    Recusa se o dump invade o periodo ja' capturado.

    A independencia e' a UNICA razao de usar esta fonte. Sobrepor
    transformaria "duas amostras que concordam" em "a mesma amostra
    contada duas vezes", e o segundo resultado pareceria confirmacao.
    """
    dias = pd.Series(sorted(df["dia"].unique()))
    invasores = dias[(dias >= CURATED_INICIO) & (dias <= CURATED_FIM)]
    if len(invasores):
        raise SystemExit(
            f"{len(invasores)} pregoes do dump estao entre "
            f"{CURATED_INICIO} e {CURATED_FIM}, que JA' ESTA no parquet "
            f"(de {invasores.min()} a {invasores.max()}).\n"
            "  A amostra do grafico so' vale como INDEPENDENTE. "
            "Redumpe fora dessa janela."
        )


ARQUIVO_PERIODOS = Path("docs/PERIODOS_DECLARADOS.json")


def checar_periodo_declarado(df: pd.DataFrame,
                             arquivo: Path = ARQUIVO_PERIODOS) -> dict[str, Any]:
    """
    Recusa dump de periodo que nao foi DECLARADO antes.

    Recusar sobreposicao com o capturado nao basta. Nada impediria
    dumpar maio, ver o resultado, e depois dumpar marco: cada dump seria
    "um tiro", mas o CONJUNTO seria uma busca, e o ultimo resultado
    pareceria confirmacao.

    A protecao e' declarar o periodo ANTES de extrair o dado, com o
    arquivo commitado. O git carimba a ordem — a declaracao precede o
    dado, e isso e' verificavel por terceiro.

    Cada periodo declarado consome trial, tenha sido rodado ou nao:
    declarar cinco e rodar um ainda e' escolher entre cinco.
    """
    import json

    if not arquivo.exists():
        raise SystemExit(
            f"nao achei {arquivo}. O periodo tem que ser DECLARADO e "
            "commitado ANTES do dump."
        )
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except json.JSONDecodeError as erro:
        raise SystemExit(
            f"{arquivo} nao e' JSON valido: {erro}\n"
            "  Caso real (2026-09-01): a entrada foi acrescentada DEPOIS\n"
            "  do `}` final, e o arquivo virou dois objetos colados.\n"
            "  A entrada vai DENTRO da lista `periodos`, no topo do "
            "arquivo."
        ) from erro
    declarados = dados.get("periodos", [])

    faltando = [p for p in declarados
                if not {"inicio", "fim", "motivo"} <= set(p)]
    if faltando:
        raise SystemExit(
            f"{len(faltando)} periodo(s) em {arquivo} sem `inicio`, `fim` "
            "ou `motivo`.\n"
            "  O motivo e' obrigatorio: se nao puder ser dito ANTES de ver "
            "o dado, nao e' criterio."
        )
    if not declarados:
        raise SystemExit(
            f"nenhum periodo declarado em {arquivo}.\n"
            "  Acrescente a entrada com `inicio`, `fim` e `motivo`, e "
            "COMMITE antes de gerar o dump.\n"
            "  O motivo e' cobravel: se nao puder ser dito antes de ver o "
            "dado, nao e' criterio."
        )

    # CADA PREGAO tem que estar declarado, e TODOS no MESMO trial.
    #
    # A primeira versao comparava [min, max] do dump contra UM periodo, e
    # recusava o combinado das duas partes de 2026 (02/01 a 23/07) — que
    # e' exatamente o uso previsto na declaracao: "parte 1 e 2 contam
    # como UM trial, executado em varios dumps por limite de buffer".
    #
    # E checar so' dia a dia criaria outro furo: MAIO tambem esta
    # declarado, num trial proprio e ja' queimado. Um dump com maio no
    # meio passaria, misturando amostras de trials diferentes. Um dump e'
    # UMA rodada de UM trial.
    def _trial(periodo: dict[str, Any]) -> str:
        return str(periodo.get("trial") or f"{periodo['inicio']}..{periodo['fim']}")

    dias = sorted({pd.Timestamp(str(x)).date() for x in df["dia"]})
    cobertura: dict[Any, str] = {}
    for dia in dias:
        for periodo in declarados:
            if (pd.Timestamp(periodo["inicio"]).date() <= dia
                    <= pd.Timestamp(periodo["fim"]).date()):
                cobertura[dia] = _trial(periodo)
                break

    fora = [d for d in dias if d not in cobertura]
    if fora:
        faixas = ", ".join(f"{p['inicio']}..{p['fim']}" for p in declarados)
        raise SystemExit(
            f"{len(fora)} pregoes do dump NAO estao declarados em {arquivo} "
            f"(de {fora[0]} a {fora[-1]}).\n"
            f"  declarados: {faixas}\n"
            "  Declarar depois de extrair o dado anula a protecao: seria "
            "escolher o periodo\n  sabendo o que ha' nele."
        )

    trials = sorted(set(cobertura.values()))
    if len(trials) > 1:
        raise SystemExit(
            f"o dump mistura {len(trials)} TRIALS diferentes: {trials}.\n"
            "  Um dump e' UMA rodada de UM trial. Misturar junta amostras "
            "que foram\n"
            "  declaradas separadamente — e uma delas pode ja' ter sido "
            "queimada.\n"
            "  Separe os dumps por trial."
        )

    usados = [p for p in declarados if _trial(p) == trials[0]]
    return {"trial": trials[0], "pregoes": len(dias),
            "periodos": [f"{p['inicio']}..{p['fim']}" for p in usados],
            "motivo": usados[0]["motivo"]}


def para_barras(df: pd.DataFrame) -> pd.DataFrame:
    """
    Formato que `absorcao_barra.preparar` espera.

    `desloc_norm` precisa ser DERIVADO aqui: no parquet ele ja' vem
    pronto do `pipeline_tempo`, mas o dump do grafico so' traz OHLC.
    `preparar` assume a coluna existente e falharia com KeyError.

    Calculado a partir do OHLC de proposito, e NAO copiado do
    `desloc_norm_ntsl` logado — este ultimo serve de CONFERENCIA. Copiar
    seria confiar que os dois lados concordam; derivar e comparar MEDE se
    concordam.
    """
    b = df[["dia", "open", "high", "low", "close", "vol_agr"]].copy()
    amplitude = b["high"] - b["low"]
    b["desloc_norm"] = ((b["close"] - b["open"]) / amplitude).where(
        amplitude > 0, 0.0)
    return b


def conferir_contra_o_ntsl(d: pd.DataFrame, df: pd.DataFrame) -> dict[str, Any]:
    """
    Compara o que o Python calculou com o que o `.ntsl` logou.

    Divergencia aqui nao e' detalhe: significa que o indicador que voce
    OLHA e o estimador que DECIDE nao sao a mesma coisa.
    """
    fora: dict[str, dict[str, Any]] = {}
    for py, ntsl in (("desloc_norm", "desloc_norm_ntsl"),
                     ("z_amplitude", "z_amplitude_ntsl"),
                     ("z_vol_agr", "z_vol_agr_ntsl"),
                     ("mov_contexto", "mov_contexto_ntsl")):
        a = d[py].to_numpy(dtype=float)
        b = df[ntsl].to_numpy(dtype=float)
        val = np.isfinite(a) & np.isfinite(b)
        if not val.any():
            fora[py] = {"comparaveis": 0}
            continue
        dif = np.abs(a[val] - b[val])
        fora[py] = {
            "comparaveis": int(val.sum()),
            "dif_mediana": float(round(float(np.median(dif)), 8)),
            "dif_max": float(round(float(dif.max()), 8)),
        }
    return fora


def rodar(caminho_log: Path, saida_dir: Path,
          n_dias_ruido: int = 900, semente: int = 20260831) -> dict[str, Any]:
    """
    Ordem: carrega, RECUSA sobreposicao, portao, dado do grafico.

    O portao roda de novo mesmo ja' tendo passado no parquet: e' a mesma
    geometria de barra, mas rodar e' barato e nao rodar seria supor.
    """
    from .absorcao_barra import (
        avaliar_tudo,
        decidir,
        marcar_eventos,
        portao_de_honestidade,
        preparar,
    )
    from .trials import limiar_deflacionado

    df, diag = carregar_log(caminho_log)
    checar_sobreposicao(df)
    declarado = checar_periodo_declarado(df)
    log.info("absorcao_grafico.log", **diag,
             periodo_declarado=declarado.get("motivo", ""))

    limiar_z = limiar_deflacionado(2)
    portao = portao_de_honestidade(limiar_z, n_dias=n_dias_ruido,
                                   semente=semente)
    if not portao["passou"]:
        raise SystemExit(
            f"PORTAO REPROVOU ({portao['veredito']}): {portao['motivo']}")

    d = marcar_eventos(preparar(para_barras(df)))
    conferencia = conferir_contra_o_ntsl(d, df)
    pontos = avaliar_tudo(d, limiar_z, semente=semente)
    veredito, motivo = decidir(pontos)

    saida_dir.mkdir(parents=True, exist_ok=True)
    tabela = pd.DataFrame(pontos)
    tabela.to_csv(saida_dir / "absorcao_grafico.csv", index=False)
    return {
        "log": diag,
        "periodo_declarado": declarado,
        "portao": portao["veredito"],
        "conferencia_ntsl": conferencia,
        "eventos": int((d["evento"] & d["contexto_ok"]).sum()),
        "veredito": veredito,
        "motivo": motivo,
        "tabela": tabela,
    }
