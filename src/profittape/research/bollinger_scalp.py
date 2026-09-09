"""
Scalp de Bollinger modificada (15s) -- formalizacao, equivalencia e contagem.

O QUE ESTE MODULO E'
--------------------
E' a etapa ANTES do pre-registro (skill disciplina, 7.2 a 7.4) para a
hipotese que o operador trouxe em 2026-09-04 (docs/BOLLINGER_SCALP.md):

1. `carregar_log`   -- le o dump do `ntsl/bollinger_scalp.ntsl`.
2. `indicadores`    -- recalcula, do mesmo OHLC, TODAS as variantes que o
                       manual do NTSL deixa em aberto (desvio populacional
                       ou amostral; %K lento ou %D; ATR aritmetica ou
                       Wilder).
3. `equivalencia`   -- MEDE qual variante e' a que o Profit calcula.
                       Recalcular e comparar mede; copiar o logado so'
                       confia (skill engenharia, 3.2).
4. `marcar_sinais`  -- a regra de entrada consolidada, os dois lados
                       espelhados, e o preco da ordem limitada.
5. `contar_clausulas` -- quantos gatilhos cada clausula deixa passar
                       (7.4). A hipotese pode ser restritiva demais; isso
                       tem que ser visto ANTES de congelar.

Nada aqui olha RETORNO. Categoria `features`: nao consome trial.

OS INDICADORES SAO ARITMETICA SIMPLES, NAO "BIBLIOTECA"
-------------------------------------------------------
Verificado em 3.000 barras sinteticas (sessao 2026-09-04):
    close > banda superior  <=>  (close - SMA_n) / DP_n > desvio
                                 (0 divergencias, ddof 0 ou 1)
    %K rapido               ==   100 + Williams %R   (erro 1e-14)
    True Range              ==   (H - L) + gap contra o close anterior
O `zscore_rolante` do projeto NAO serve: usa shift(1) e ddof=1, e o
sinal (>k) divergiu em 43 de 2.980 barras.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog

from .absorcao_grafico import _numero

log = structlog.get_logger(__name__)

PREFIXO = "BBSBARRA|"

# Ordem CONGELADA, espelho do ConsoleLog em `ntsl/bollinger_scalp.ntsl`.
# Mudar aqui exige mudar la' na MESMA entrega.
CAMPOS = [
    "data", "hora", "hora_bolsa", "current_bar",
    "open", "high", "low", "close", "vol_total",
    "bb_sup_ntsl", "bb_inf_ntsl", "est_ntsl", "atr_ntsl", "tr_ntsl",
]

# PARAMETROS DA HIPOTESE -- do operador, nao calibrados. Mudar = hipotese
# nova, nao ajuste.
BB_DESVIO = 0.38
BB_PERIODO = 21
EST_PERIODO = 8
EST_MEDIA = 3
EST_SOBREVENDIDO = 20.0
EST_SOBRECOMPRADO = 80.0
ATR_PERIODO = 21

TICK_WIN = 5.0                 # pontos por tick
SEGUNDOS_BARRA = 15


# ---------------------------------------------------------------------
# 1. Parser
# ---------------------------------------------------------------------
def carregar_log(caminho: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Le as linhas BBSBARRA e devolve as barras ordenadas.

    IDENTIDADE DA BARRA: (dia, current_bar), nao (dia, hora). Em 15s,
    quatro barras podem compartilhar a mesma `hora` se `Time` vier em
    HHMM. `current_bar` e' unico dentro de um dump; entre dumps de
    historicos diferentes ele muda, por isso a desduplicacao entre dumps
    fica a cargo das janelas de data/hora do indicador, nao daqui.
    """
    if not caminho.exists():
        raise SystemExit(f"nao achei {caminho}")
    bruto = caminho.read_text(encoding="utf-8", errors="replace")
    linhas = [x.strip().replace("\r", "") for x in bruto.splitlines()
              if PREFIXO in x]
    if not linhas:
        pista = ("  Ha' BBSVIDA (o indicador rodou), mas nenhuma barra passou "
                 "na janela.\n  Confira LogDataInicio/Fim (1AnoMesDia) e "
                 "LogHoraInicio/Fim (formato de Time)."
                 if "BBSVIDA|" in bruto else
                 "  Nem BBSVIDA aparece: o indicador nao compilou ou nao "
                 "esta aplicado.")
        raise SystemExit(f"nenhuma linha '{PREFIXO}' em {caminho}.\n{pista}")

    registros, larguras = [], set()
    for linha in linhas:
        campos = linha.split(PREFIXO, 1)[1].split("|")
        larguras.add(len(campos))
        if len(campos) == len(CAMPOS):
            registros.append(campos)
    if len(larguras) != 1 or len(CAMPOS) not in larguras:
        raise SystemExit(
            f"formato incompativel em {caminho}: vi {sorted(larguras)} campos "
            f"depois do prefixo, esperava {len(CAMPOS)}.\n"
            "  O .ntsl e o parser divergiram -- os dois saem na mesma entrega.")

    df = pd.DataFrame(registros, columns=CAMPOS)
    for c in CAMPOS[3:]:
        df[c] = df[c].map(_numero)
    d = df["data"].astype(int)
    df["dia"] = pd.to_datetime(
        (1900 + d // 10000).astype(str) + "-"
        + ((d // 100) % 100).astype(str).str.zfill(2) + "-"
        + (d % 100).astype(str).str.zfill(2)).dt.date
    df["hora_int"] = df["hora"].astype(int)
    df["current_bar"] = df["current_bar"].astype(int)
    df = df.sort_values(["dia", "current_bar"]).reset_index(drop=True)

    n_dup = int(df.duplicated(["dia", "current_bar"]).sum())
    if n_dup:
        raise SystemExit(
            f"{n_dup} barras duplicadas (mesmo dia e current_bar) em "
            f"{caminho}. Dumps sobrepostos inflam o n sem informacao nova.")

    # Formato de Time: HHMM (<= 2359) ou HHMMSS. Com HHMM a barra so' tem
    # segundos se o minuto estiver completo no dump; o `seq_min` e' a
    # posicao dentro do minuto, e so' vale como segundos quando o dump
    # e' continuo. Um minuto com mais de 4 barras e' dump sobreposto.
    hhmmss = bool(df["hora_int"].max() > 2359)
    df["seq_min"] = df.groupby(["dia", "hora_int"]).cumcount()
    por_min = df.groupby(["dia", "hora_int"]).size()
    if (not hhmmss) and int(por_min.max()) > 4:
        raise SystemExit(
            "um minuto tem mais de 4 barras de 15s: dumps sobrepostos ou "
            "grafico fora de 15s.")
    if hhmmss:
        h, m, s = df["hora_int"] // 10000, (df["hora_int"] // 100) % 100, df["hora_int"] % 100
    else:
        h, m, s = df["hora_int"] // 100, df["hora_int"] % 100, df["seq_min"] * SEGUNDOS_BARRA
    df["ts"] = (pd.to_datetime(df["dia"].astype(str))
                + pd.to_timedelta(h * 3600 + m * 60 + s, unit="s"))

    # Bloco CONTIGUO: current_bar consecutivo. Rolling so' vale dentro
    # dele -- atravessar um buraco de dump misturaria barras que nao sao
    # vizinhas. O Profit roda continuo atraves dos dias, entao o bloco
    # tambem pode.
    salto = df["current_bar"].diff().fillna(1) != 1
    df["bloco"] = salto.cumsum().astype(int) + 1

    por_pregao = len(df) / max(df["dia"].nunique(), 1)
    return df, {"linhas": len(linhas), "barras": len(df),
                "barras_por_pregao": round(por_pregao, 1),
                "pregoes": int(df["dia"].nunique()),
                "blocos": int(df["bloco"].nunique()),
                "time_com_segundos": hhmmss,
                "inicio": str(df["dia"].min()), "fim": str(df["dia"].max())}


# ---------------------------------------------------------------------
# 2. Indicadores (todas as variantes em aberto)
# ---------------------------------------------------------------------
def _por_bloco(df: pd.DataFrame, col: str, fn: Any) -> pd.Series:
    return df.groupby("bloco", group_keys=False)[col].apply(fn)


def indicadores(df: pd.DataFrame) -> pd.DataFrame:
    """
    Recalcula do OHLC. A barra ATUAL entra na janela (e' o que o grafico
    plota na propria barra) -- diferente do `zscore_rolante`.
    """
    d = df.copy()
    n, k = BB_PERIODO, BB_DESVIO
    d["sma"] = _por_bloco(d, "close", lambda s: s.rolling(n).mean())
    d["dp0"] = _por_bloco(d, "close", lambda s: s.rolling(n).std(ddof=0))
    d["dp1"] = _por_bloco(d, "close", lambda s: s.rolling(n).std(ddof=1))
    d["bb_sup_ddof0"] = d["sma"] + k * d["dp0"]
    d["bb_inf_ddof0"] = d["sma"] - k * d["dp0"]
    d["bb_sup_ddof1"] = d["sma"] + k * d["dp1"]
    d["bb_inf_ddof1"] = d["sma"] - k * d["dp1"]

    p, m = EST_PERIODO, EST_MEDIA
    hh = _por_bloco(d, "high", lambda s: s.rolling(p).max())
    ll = _por_bloco(d, "low", lambda s: s.rolling(p).min())
    faixa = hh - ll
    d["k_rapido"] = np.where(faixa > 0, 100.0 * (d["close"] - ll) / faixa, np.nan)
    d["k_lento"] = _por_bloco(d, "k_rapido", lambda s: s.rolling(m).mean())
    d["d_lento"] = _por_bloco(d, "k_lento", lambda s: s.rolling(m).mean())

    cp = _por_bloco(d, "close", lambda s: s.shift(1))
    d["tr"] = pd.concat([d["high"] - d["low"], (d["high"] - cp).abs(),
                         (d["low"] - cp).abs()], axis=1).max(axis=1)
    # Primeira barra do bloco: o Profit tem o close anterior (do dia
    # anterior, ou da barra antes do dump); o Python nao. Medido em
    # 01/09/2026: gap de 625 pts so' nessa barra, e o ATR21 arrastando
    # ate' a 21a. Fica NaN -- honesto, e tira o artefato da comparacao.
    d.loc[cp.isna(), "tr"] = np.nan
    a = ATR_PERIODO
    d["atr_sma"] = _por_bloco(d, "tr", lambda s: s.rolling(a).mean())
    d["atr_wilder"] = _por_bloco(
        d, "tr", lambda s: s.ewm(alpha=1.0 / a, adjust=False, min_periods=a).mean())
    return d


# ---------------------------------------------------------------------
# 3. Equivalencia Python x Profit
# ---------------------------------------------------------------------
CANDIDATOS: dict[str, list[str]] = {
    "bb_sup_ntsl": ["bb_sup_ddof0", "bb_sup_ddof1"],
    "bb_inf_ntsl": ["bb_inf_ddof0", "bb_inf_ddof1"],
    "est_ntsl": ["k_lento", "d_lento", "k_rapido"],
    "atr_ntsl": ["atr_sma", "atr_wilder"],
    "tr_ntsl": ["tr"],
}


def equivalencia(d: pd.DataFrame, tolerancia: float = 0.5) -> dict[str, Any]:
    """
    Para cada campo do Profit, qual variante Python bate.

    `tolerancia` em unidades do campo (pontos para bandas/ATR/TR; 0-100
    para o estocastico). 0,5 pt = um decimo de tick: abaixo disso a
    diferenca e' arredondamento do log, nao formula. O veredito por campo
    e' `bate=True` so' se a MELHOR variante fica dentro da tolerancia em
    TODAS as barras comparaveis -- uma barra fora ja' e' formula
    diferente, nao ruido.
    """
    saida: dict[str, Any] = {}
    for campo, cands in CANDIDATOS.items():
        melhor: dict[str, Any] | None = None
        detalhe: dict[str, Any] = {}
        for c in cands:
            m = d[campo].notna() & d[c].notna()
            if int(m.sum()) == 0:
                detalhe[c] = {"comparaveis": 0}
                continue
            dif = (d.loc[m, campo] - d.loc[m, c]).abs()
            r = {"comparaveis": int(m.sum()),
                 "dif_max": round(float(dif.max()), 4),
                 "dif_mediana": round(float(dif.median()), 4)}
            detalhe[c] = r
            if melhor is None or r["dif_max"] < melhor["dif_max"]:
                melhor = {"variante": c, **r}
        saida[campo] = {
            "melhor": melhor["variante"] if melhor else None,
            "bate": bool(melhor and melhor["dif_max"] <= tolerancia),
            "detalhe": detalhe,
        }
    return saida


# ---------------------------------------------------------------------
# 4. Regra de entrada consolidada (2026-09-04, os dois lados espelhados)
# ---------------------------------------------------------------------
def marcar_sinais(d: pd.DataFrame, col_sup: str = "bb_sup_ntsl",
                  col_inf: str = "bb_inf_ntsl",
                  col_est: str = "est_ntsl") -> pd.DataFrame:
    """
    Barra t e' a de ENTRADA. Compra:
        t-2  vermelha (close<open)  e close > banda superior
        t-1  branca   (close>open)  e close > banda superior
             e estocastico(t-1) < 20
        t    ordem LIMITADA de compra em high(t-2), valida so' em t
    Venda e' o espelho (banda inferior, > 80, limitada em low(t-2)).
    Doji nao e' vermelho nem branco. As tres barras no mesmo dia e no
    mesmo bloco contiguo.

    `executou`: a limitada foi TOCADA em t (low <= limite na compra).
    Toque nao e' preenchimento garantido -- na fila da B3 o limite pode
    ser tocado sem executar. E' o melhor que o OHLC permite; o replay
    pelo tape resolve o resto.
    `tipo_execucao`: "abertura" (limite ja' estava a favor na abertura,
    executa como mercado) ou "recuo" (o preco teve que voltar ate' ele).
    Sao dois regimes de preenchimento diferentes e sao contados separados.
    """
    x = d.copy()
    vermelha = x["close"] < x["open"]
    branca = x["close"] > x["open"]
    acima = x["close"] > x[col_sup]
    abaixo = x["close"] < x[col_inf]
    est = x[col_est]

    def lag(s: pd.Series, k: int) -> pd.Series:
        # shift DENTRO do bloco contiguo: a barra vizinha de outro bloco
        # nao e' vizinha de verdade.
        return s.groupby(x["bloco"]).shift(k)

    mesmo_dia = (lag(x["dia"].astype(str), 2) == x["dia"].astype(str))

    x["c_compra_t2"] = (lag(vermelha, 2) & lag(acima, 2)).fillna(False).astype(bool)
    x["c_compra_t1"] = (lag(branca, 1) & lag(acima, 1)).fillna(False).astype(bool)
    x["c_compra_est"] = (lag(est, 1) < EST_SOBREVENDIDO).fillna(False).astype(bool)
    x["sinal_compra"] = (x["c_compra_t2"] & x["c_compra_t1"]
                         & x["c_compra_est"] & mesmo_dia).astype(bool)

    x["c_venda_t2"] = (lag(branca, 2) & lag(abaixo, 2)).fillna(False).astype(bool)
    x["c_venda_t1"] = (lag(vermelha, 1) & lag(abaixo, 1)).fillna(False).astype(bool)
    x["c_venda_est"] = (lag(est, 1) > EST_SOBRECOMPRADO).fillna(False).astype(bool)
    x["sinal_venda"] = (x["c_venda_t2"] & x["c_venda_t1"]
                        & x["c_venda_est"] & mesmo_dia).astype(bool)

    x["preco_limite"] = np.nan
    x.loc[x["sinal_compra"], "preco_limite"] = lag(x["high"], 2)[x["sinal_compra"]]
    x.loc[x["sinal_venda"], "preco_limite"] = lag(x["low"], 2)[x["sinal_venda"]]

    x["executou"] = False
    x["tipo_execucao"] = ""
    c = x["sinal_compra"]
    x.loc[c, "executou"] = x.loc[c, "low"] <= x.loc[c, "preco_limite"]
    x.loc[c & x["executou"], "tipo_execucao"] = np.where(
        x.loc[c & x["executou"], "open"] <= x.loc[c & x["executou"], "preco_limite"],
        "abertura", "recuo")
    v = x["sinal_venda"]
    x.loc[v, "executou"] = x.loc[v, "high"] >= x.loc[v, "preco_limite"]
    x.loc[v & x["executou"], "tipo_execucao"] = np.where(
        x.loc[v & x["executou"], "open"] >= x.loc[v & x["executou"], "preco_limite"],
        "abertura", "recuo")
    return x


# ---------------------------------------------------------------------
# 5. Contagem por clausula (7.4)
# ---------------------------------------------------------------------
def cobertura_por_pregao(x: pd.DataFrame, fracao_inteiro: float = 0.8) -> pd.DataFrame:
    """
    Quantas barras cada pregao trouxe e de que hora a que hora. Um
    pregao e' INTEIRO se tem >= `fracao_inteiro` das barras do pregao
    mais cheio do dump. Medido em 2026-09-08: um dump de 4 dias saiu com
    01 e 02 inteiros e 03 e 04 so' de 12:24 em diante -- e o "por
    pregao" dividia por 4.
    """
    g = x.groupby("dia")
    c = pd.DataFrame({"barras": g.size(), "inicio": g["hora_int"].min(),
                      "fim": g["hora_int"].max()})
    c["inteiro"] = c["barras"] >= fracao_inteiro * c["barras"].max()
    return c.reset_index()


def contar_clausulas(x: pd.DataFrame) -> pd.DataFrame:
    """
    Funil, por lado: quantas barras sobrevivem a cada clausula, em
    absoluto e por pregao. E' o numero que decide se a hipotese tem
    TAXA para um forward (skill disciplina-forward: horizonte por
    TAXA x EFEITO) ou se uma clausula seca tudo.

    `por_pregao` divide so' pelos pregoes INTEIROS do dump, e conta so'
    as barras deles -- um pregao pela metade nao e' meio pregao de
    sinais, e' um pregao com a manha faltando.
    """
    cob = cobertura_por_pregao(x)
    inteiros = set(cob.loc[cob["inteiro"], "dia"])
    x = x[x["dia"].isin(inteiros)]
    pregoes = max(len(inteiros), 1)
    linhas = []
    for lado, pref, sinal in (("compra", "c_compra", "sinal_compra"),
                              ("venda", "c_venda", "sinal_venda")):
        etapas = [
            ("barras", pd.Series(True, index=x.index)),
            ("t-1 fora da banda e cor de sinal", x[f"{pref}_t1"]),
            ("+ t-2 correcao fora da banda", x[f"{pref}_t1"] & x[f"{pref}_t2"]),
            ("+ estocastico(t-1) extremo", x[sinal]),
            ("+ limitada tocada em t", x[sinal] & x["executou"]),
            ("   ... executada na abertura",
             x[sinal] & x["executou"] & (x["tipo_execucao"] == "abertura")),
            ("   ... executada no recuo",
             x[sinal] & x["executou"] & (x["tipo_execucao"] == "recuo")),
        ]
        for nome, mask in etapas:
            n = int(mask.sum())
            linhas.append({"lado": lado, "clausula": nome, "n": n,
                           "por_pregao": round(n / pregoes, 2)})
    return pd.DataFrame(linhas)


def diagnostico_clausulas(x: pd.DataFrame, stop_pts: float = 40.0) -> dict[str, Any]:
    """
    O que o funil nao mostra sozinho: ONDE o estocastico dos candidatos
    esta' (se a clausula nunca dispara, e' o desenho, nao o azar -- 7.6),
    e quanto o stop cabe dentro de uma barra (TR >= stop).

    Medido em 01/09/2026: Est(t-1) dos candidatos a compra tem mediana 72
    e p5 = 41; abaixo de 20, 1 em 164. Um branco fechando acima da banda
    superior fecha no topo da faixa de 8 barras por construcao.
    """
    est1 = x["est_ntsl"].groupby(x["bloco"]).shift(1)
    est2 = x["est_ntsl"].groupby(x["bloco"]).shift(2)
    q = [0.05, 0.25, 0.5, 0.75, 0.95]
    out: dict[str, Any] = {}
    for lado, pref in (("compra", "c_compra"), ("venda", "c_venda")):
        cand = x[f"{pref}_t1"] & x[f"{pref}_t2"]
        e1, e2 = est1[cand].dropna(), est2[cand].dropna()
        if e1.empty:
            out[lado] = {"candidatos": 0}
            continue
        out[lado] = {
            "candidatos": int(cand.sum()),
            "est_t1_quantis_5_25_50_75_95": [round(float(v), 1) for v in e1.quantile(q)],
            "est_t1_abaixo_20": int((e1 < 20).sum()), "est_t1_acima_80": int((e1 > 80).sum()),
            "est_t1_abaixo_50": int((e1 < 50).sum()), "est_t1_acima_50": int((e1 > 50).sum()),
            "est_t2_abaixo_20": int((e2 < 20).sum()), "est_t2_acima_80": int((e2 > 80).sum()),
        }
    tr = x["tr_ntsl"].dropna()
    if not tr.empty:
        out["tr"] = {"tr_p50_pts": round(float(tr.median()), 1),
                     "pct_barras_tr_ge_stop": round(100 * float((tr >= stop_pts).mean()), 1),
                     "pct_barras_tr_ge_2x_stop": round(100 * float((tr >= 2 * stop_pts).mean()), 1)}
    return out


def largura_banda_em_pontos(d: pd.DataFrame, col_sup: str = "bb_sup_ntsl",
                            col_inf: str = "bb_inf_ntsl") -> dict[str, float]:
    """7.5: o 0,38 adimensional esconde o que ele e'. Em pontos e ticks."""
    meia = ((d[col_sup] - d[col_inf]) / 2).dropna()
    if meia.empty:
        return {}
    q = meia.quantile([0.1, 0.5, 0.9])
    return {"meia_largura_p10_pts": round(float(q.iloc[0]), 1),
            "meia_largura_p50_pts": round(float(q.iloc[1]), 1),
            "meia_largura_p90_pts": round(float(q.iloc[2]), 1),
            "meia_largura_p50_ticks": round(float(q.iloc[1]) / TICK_WIN, 2)}


# ---------------------------------------------------------------------
# Rodada completa
# ---------------------------------------------------------------------
def rodar(log_path: Path, saida: Path) -> dict[str, Any]:
    df, meta = carregar_log(log_path)
    d = indicadores(df)
    eq = equivalencia(d)
    x = marcar_sinais(d)
    funil = contar_clausulas(x)
    cobertura = cobertura_por_pregao(x)
    largura = largura_banda_em_pontos(d)
    diag = diagnostico_clausulas(x)
    atr = d["atr_ntsl"].dropna()
    atr_pts = ({"atr21_p50_pts": round(float(atr.median()), 1),
                "atr21_p90_pts": round(float(atr.quantile(0.9)), 1)}
               if not atr.empty else {})

    saida.mkdir(parents=True, exist_ok=True)
    x.to_parquet(saida / "barras_15s.parquet", index=False)
    resumo = {"dump": meta, "equivalencia": eq, "largura_banda": largura,
              "atr": atr_pts, "diagnostico": diag,
              "cobertura": cobertura.to_dict(orient="records", ),
              "funil": funil.to_dict(orient="records")}
    (saida / "resumo.json").write_text(json.dumps(resumo, indent=2, default=str),
                                       encoding="utf-8")
    log.info("bollinger_scalp.rodada", **meta, saida=str(saida))
    return {"meta": meta, "equivalencia": eq, "funil": funil,
            "largura_banda": largura, "atr": atr_pts, "diagnostico": diag,
            "cobertura": cobertura, "barras": x}
