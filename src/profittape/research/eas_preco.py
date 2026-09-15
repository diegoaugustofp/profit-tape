"""
EAs de PRECO (M15) -- equivalencia Python x Profit e funil da ficha IFR2.

O QUE ESTE MODULO E'
--------------------
E' a etapa ANTES de congelar a ficha (skill disciplina, 7.2 a 7.5) para
a linha de EAs de preco decidida em 2026-09-13 (docs/EAS_DE_PRECO.md):

1. `carregar_log`    -- le o dump do `ntsl/preco_m15.ntsl`.
2. `indicadores`     -- recalcula, do mesmo OHLC, TODAS as variantes que
                        o manual do NTSL deixa em aberto (RSI Wilder com
                        semente SMA, RSI exponencial sem semente, RSI de
                        media simples; MME semeada no primeiro close ou
                        na SMA; ATR aritmetica ou Wilder).
3. `equivalencia`    -- MEDE qual variante e' a que o Profit calcula.
                        Recalcular e comparar mede; copiar o logado so'
                        confia (skill engenharia, 3.2).
4. `marcar_ifr2`     -- a regra de sinal da ficha IFR2 v0, os dois lados
                        espelhados, com D e barreiras em pontos.
5. `contar_clausulas` -- quantos sinais cada clausula deixa passar, por
                        pregao (7.4). A ficha pode ser restritiva demais;
                        isso tem que ser visto ANTES de congelar.
6. `ambiguidade`     -- fracao de operacoes cuja barra de resolucao
                        contem alvo E stop (o OHLC nao diz quem bateu
                        primeiro). Diagnostico do ESTIMADOR, nao
                        resultado: este modulo NAO calcula qual barreira
                        bateu, de proposito.

Nada aqui olha RETORNO. Categoria `features`: nao consome trial.

ORB e 123 (fichas 4 e 5 do mesmo documento) usam o MESMO dump; os seus
funis entram quando o IFR2 estiver congelado -- um de cada vez, na ordem
decidida pelo operador.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog

from .absorcao_grafico import _numero

log = structlog.get_logger(__name__)

PREFIXO = "PRCBARRA|"

# Ordem CONGELADA, espelho do ConsoleLog em `ntsl/preco_m15.ntsl`.
# Mudar aqui exige mudar la' na MESMA entrega.
CAMPOS = [
    "data", "hora", "hora_bolsa", "current_bar",
    "open", "high", "low", "close", "vol_total",
    "rsi_ntsl", "mme8_ntsl", "mme80_ntsl", "atr_ntsl", "tr_ntsl",
]

# PARAMETROS DAS FICHAS (docs/EAS_DE_PRECO.md, secao 2) -- declarados,
# nao calibrados. Mudar = ficha nova.
RSI_PERIODO = 2
RSI_SOBREVENDIDO = 10.0
RSI_SOBRECOMPRADO = 90.0
MME_CURTA = 8
MME_LONGA = 80
ATR_PERIODO = 14
# K = 1 (TRIAL 2, 2026-09-14). A v1 usou K = 0,5 justificando pelo stop
# catastrofico do risco.py -- premissa ERRADA: a decisao 4.9 do
# EA_ARQUITETURA diz que risco e' informativo e nunca limita a
# estrategia. O trial 1 (K = 0,5) deu CONTRA e vale para K = 0,5. O
# trial 2 testa a ficha como foi desenhada (K = 1) -- e' o SEGUNDO uso
# da amostra 2023-2025, declarado antes, com criterio mais exigente
# (ver eas_preco_teste.TRIAL). Capital necessario e' CALCULADO e
# reportado (em_pontos), nunca usado para encolher D.
K_ATR = 1.0                    # D = K_ATR x ATR14(t), ao tick
# FICHA v1: o regime MME80 SAIU da clausula (7.4: cortava 70% dos sinais,
# 1,09/pregao -> ~980 pregoes para n=1.070). Passa a ESTRATIFICACAO
# reportada -- o primario e' o total; o regime nunca e' escolhido depois.
REGIME_NA_CLAUSULA = False
TICK_WIN = 5.0                 # pontos por tick
HORA_PRIMEIRO_FECHAMENTO = 915     # HHMM, inclusivo: t fecha a partir daqui
HORA_ULTIMO_FECHAMENTO = 1630      # HHMM, inclusivo
MINUTOS_BARRA = 15
CUSTO_PONTOS = 11.0            # ida e volta, por contrato
# Capital RECOMENDADO por contrato (EA_ARQUITETURA 4.9: risco e'
# informativo, nunca limita a ficha): D x valor do ponto / risco por
# operacao. Reportado em p50 e p90 de D; o operador decide.
VALOR_PONTO_REAIS = 0.20
RISCO_MAX_PCT = 0.02


def capital_recomendado(d_pts: float) -> float:
    return round(d_pts * VALOR_PONTO_REAIS / RISCO_MAX_PCT, 0)

# FICHA ORB v0 (docs/EAS_DE_PRECO.md, 4) -- declarados, nao calibrados.
ORB_BARRAS_RANGE = (900, 915)      # hhmm das barras que formam o range
ORB_PRIMEIRA_ENTRADA = 930         # ordens armadas a partir desta barra
ORB_ULTIMA_ENTRADA = 1145          # ultima barra em que a ordem vale (< 12:00)
ORB_AMPLITUDE_MINIMA = 4 * TICK_WIN   # 20 pts: abaixo, range degenerado
ORB_REGIME_NA_CLAUSULA = False     # v1 (2026-09-14): regime e' ESTRATO; os dois lados armados, OCO


def arredondar_ao_tick(pts: float, tick: float | None = None) -> float:
    """Meio-tick vai para CIMA (mesma funcao do bollinger_scalp: `round()`
    do Python arredonda 32,5 para 32 -- pego na conferencia a mao).
    `tick=None` le o do INSTRUMENTO em vigor (nao capturar TICK_WIN como
    default: default e' avaliado na definicao, antes de `usar_instrumento`)."""
    if pd.isna(pts):
        return float("nan")
    t = TICK_WIN if tick is None else tick
    return float(max(t, math.floor(pts / t + 0.5) * t))


# ---------------------------------------------------------------------
# 1. Parser
# ---------------------------------------------------------------------
def carregar_log(caminho: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Le as linhas PRCBARRA e devolve as barras ordenadas.

    IDENTIDADE DA BARRA: (dia, current_bar). Em M15 (dia, hora) tambem
    identificaria, mas o par com current_bar e' o que o parser irmao
    usa, e a desduplicacao entre dumps sobrepostos e' a mesma.
    """
    if not caminho.exists():
        raise SystemExit(f"nao achei {caminho}")
    bruto = caminho.read_text(encoding="utf-8", errors="replace")
    linhas = [x.strip().replace("\r", "") for x in bruto.splitlines()
              if PREFIXO in x]
    if not linhas:
        pista = ("  Ha' PRCVIDA (o indicador rodou), mas nenhuma barra passou "
                 "na janela.\n  Confira LogDataInicio/Fim (1AnoMesDia)."
                 if "PRCVIDA|" in bruto else
                 "  Nem PRCVIDA aparece: o indicador nao compilou ou nao "
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

    # Formato de Time: HHMM (<= 2359) ou HHMMSS. `hhmm` normalizado e' o
    # que as janelas de horario das fichas usam.
    hhmmss = bool(df["hora_int"].max() > 2359)
    df["hhmm"] = (df["hora_int"] // 100) if hhmmss else df["hora_int"]
    h, m = df["hhmm"] // 100, df["hhmm"] % 100
    df["ts"] = (pd.to_datetime(df["dia"].astype(str))
                + pd.to_timedelta(h * 3600 + m * 60, unit="s"))

    por_hhmm = df.groupby(["dia", "hhmm"]).size()
    if int(por_hhmm.max()) > 1:
        raise SystemExit(
            "um horario tem mais de uma barra no mesmo dia: dumps sobrepostos "
            "ou grafico fora de 15 minutos.")

    # Bloco CONTIGUO: current_bar consecutivo. Rolling so' vale dentro
    # dele. O Profit roda continuo atraves dos dias (indicadores nao
    # reiniciam por pregao -- convencao das fichas), entao o bloco
    # tambem atravessa dias.
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


def rsi_wilder(close: pd.Series, n: int = RSI_PERIODO) -> pd.Series:
    """
    RSI classico de Wilder: semente = media SIMPLES dos n primeiros
    ganhos/perdas; depois media_t = (media_{t-1} x (n-1) + x_t) / n.

    Conferido a mao (regra 4) em [10, 11, 10.5, 11.5, 11.0], n=2:
        variacoes  +1, -0.5, +1, -0.5
        barra 2: g=(1+0)/2=0.5  p=(0+0.5)/2=0.25   RS=2   RSI=66.667
        barra 3: g=(0.5+1)/2=0.75 p=(0.25+0)/2=0.125 RS=6 RSI=85.714
        barra 4: g=(0.75+0)/2=0.375 p=(0.125+0.5)/2=0.3125 RS=1.2 RSI=54.545
    """
    v = close.diff()
    g = v.clip(lower=0.0)
    p = (-v).clip(lower=0.0)
    out = pd.Series(np.nan, index=close.index, dtype=float)
    vals_g, vals_p = g.to_numpy(), p.to_numpy()
    if len(close) <= n:
        return out
    mg = float(np.nanmean(vals_g[1:n + 1]))
    mp = float(np.nanmean(vals_p[1:n + 1]))
    out.iloc[n] = _rsi_de(mg, mp)
    for i in range(n + 1, len(close)):
        mg = (mg * (n - 1) + vals_g[i]) / n
        mp = (mp * (n - 1) + vals_p[i]) / n
        out.iloc[i] = _rsi_de(mg, mp)
    return out


def _rsi_de(mg: float, mp: float) -> float:
    if mp == 0.0:
        return 100.0 if mg > 0.0 else 50.0
    return 100.0 - 100.0 / (1.0 + mg / mp)


def rsi_sma(close: pd.Series, n: int = RSI_PERIODO) -> pd.Series:
    """RSI com media SIMPLES movel dos ultimos n ganhos/perdas (a outra
    leitura possivel de 'RSI(periodo, tipoMedia=0)' no NTSL)."""
    v = close.diff()
    g = v.clip(lower=0.0).rolling(n).mean()
    p = (-v).clip(lower=0.0).rolling(n).mean()
    return pd.Series([_rsi_de(a, b) if not (pd.isna(a) or pd.isna(b)) else np.nan
                      for a, b in zip(g, p, strict=True)], index=close.index)


def rsi_ewm(close: pd.Series, n: int = RSI_PERIODO) -> pd.Series:
    """RSI exponencial SEM semente SMA (ewm alpha=1/n a partir da 1a
    variacao). Converge para o Wilder; difere nas primeiras barras."""
    v = close.diff()
    g = v.clip(lower=0.0).ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    p = (-v).clip(lower=0.0).ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    return pd.Series([_rsi_de(a, b) if not (pd.isna(a) or pd.isna(b)) else np.nan
                      for a, b in zip(g, p, strict=True)], index=close.index)


def mme_semente_close(close: pd.Series, n: int) -> pd.Series:
    """MME semeada no PRIMEIRO close (ewm adjust=False)."""
    return close.ewm(span=n, adjust=False).mean()


def mme_semente_sma(close: pd.Series, n: int) -> pd.Series:
    """MME semeada na SMA das n primeiras barras (a outra convencao)."""
    out = pd.Series(np.nan, index=close.index, dtype=float)
    if len(close) < n:
        return out
    alpha = 2.0 / (n + 1)
    vals = close.to_numpy()
    m = float(np.mean(vals[:n]))
    out.iloc[n - 1] = m
    for i in range(n, len(close)):
        m = alpha * vals[i] + (1 - alpha) * m
        out.iloc[i] = m
    return out


def indicadores(df: pd.DataFrame) -> pd.DataFrame:
    """Recalcula do OHLC, por bloco contiguo. A barra ATUAL entra na
    janela (e' o que o grafico plota na propria barra)."""
    d = df.copy()
    d["rsi_wilder"] = _por_bloco(d, "close", rsi_wilder)
    d["rsi_sma"] = _por_bloco(d, "close", rsi_sma)
    d["rsi_ewm"] = _por_bloco(d, "close", rsi_ewm)
    d["mme8_close"] = _por_bloco(d, "close", lambda s: mme_semente_close(s, MME_CURTA))
    d["mme8_sma"] = _por_bloco(d, "close", lambda s: mme_semente_sma(s, MME_CURTA))
    d["mme80_close"] = _por_bloco(d, "close", lambda s: mme_semente_close(s, MME_LONGA))
    d["mme80_sma"] = _por_bloco(d, "close", lambda s: mme_semente_sma(s, MME_LONGA))

    cp = _por_bloco(d, "close", lambda s: s.shift(1))
    d["tr"] = pd.concat([d["high"] - d["low"], (d["high"] - cp).abs(),
                         (d["low"] - cp).abs()], axis=1).max(axis=1)
    # Primeira barra do bloco: o Profit tem o close anterior, o Python
    # nao. Fica NaN -- honesto, e tira o artefato da comparacao.
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
    "rsi_ntsl": ["rsi_wilder", "rsi_ewm", "rsi_sma"],
    "mme8_ntsl": ["mme8_close", "mme8_sma"],
    "mme80_ntsl": ["mme80_close", "mme80_sma"],
    "atr_ntsl": ["atr_sma", "atr_wilder"],
    "tr_ntsl": ["tr"],
}


# Barras do bloco descartadas ANTES de comparar: a semente diferente decai
# exponencialmente e comparar antes disso mede a semente, nao a formula.
# BUG REAL (2026-09-13, primeiro dump): `startswith("mme8")` casava
# tambem com "mme80" -> MME80 comparada da barra 24 em vez da 240, e o
# RSI sem aquecimento nenhum. O verificador dizia NAO BATE com mediana
# 0,0 -- o proprio sintoma que denunciou. Agora e' chave EXATA.
# Quanto sobra da semente depois de k barras: (1 - alpha)^k, alpha =
# 2/(n+1). Com 3n sobra ~0,26% -- de uma semente 2.000 pts fora (o
# grafico tem historico antes do dump; o Python nao) ainda sao ~5 pts,
# acima da tolerancia de 0,5. Com 5n sobra ~0,005%: 0,1 pt. O teste de
# regressao reproduz exatamente esse caso.
AQUECIMENTO: dict[str, int] = {
    "rsi_ntsl": 10 * RSI_PERIODO,      # alpha 0,5: semente some em ~10 barras
    "mme8_ntsl": 5 * MME_CURTA,
    "mme80_ntsl": 5 * MME_LONGA,
}


def equivalencia(d: pd.DataFrame, tolerancia: float = 0.5,
                 candidatos: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """
    Para cada campo do Profit, qual variante Python bate.

    `tolerancia` em unidades do campo (pontos para MME/ATR/TR; 0-100 para
    o RSI). O veredito por campo e' `bate=True` so' se a MELHOR variante
    fica dentro da tolerancia em TODAS as barras comparaveis -- uma barra
    fora ja' e' formula diferente, nao ruido.

    RSI e MMEs sao comparados so' depois do AQUECIMENTO do bloco (ver
    acima). `dif_max_em` diz ONDE a maior diferenca esta' -- se for na
    borda do aquecimento, e' semente; se for no meio, e' formula.
    """
    cands = candidatos or CANDIDATOS
    saida: dict[str, Any] = {}
    pos = d.groupby("bloco").cumcount()
    for campo, lista in cands.items():
        melhor: dict[str, Any] | None = None
        detalhe: dict[str, Any] = {}
        aquecimento = AQUECIMENTO.get(campo, 0)
        for c in lista:
            m = d[campo].notna() & d[c].notna() & (pos >= aquecimento)
            if int(m.sum()) == 0:
                detalhe[c] = {"comparaveis": 0}
                continue
            dif = (d.loc[m, campo] - d.loc[m, c]).abs()
            i_max = int(dif.idxmax())
            hhmm_max = int(d["hhmm"].to_numpy()[i_max])
            pos_max = int(pos.to_numpy()[i_max])
            r = {"comparaveis": int(m.sum()),
                 "dif_max": round(float(dif.max()), 4),
                 "dif_max_em": f"{d['dia'].iat[i_max]} {hhmm_max:04d} "
                               f"(barra {pos_max} do bloco)",
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
# 4. Regra de sinal da ficha IFR2 v0 (docs/EAS_DE_PRECO.md, 3)
# ---------------------------------------------------------------------
def marcar_ifr2(d: pd.DataFrame, col_rsi: str = "rsi_ntsl",
                col_mme80: str = "mme80_ntsl",
                col_atr: str = "atr_ntsl") -> pd.DataFrame:
    """
    Barra t e' a de SINAL; a entrada e' a mercado na abertura de t+1.

    Clausulas, na ordem do funil (ficha v1):
        extremo     compra: RSI2(t) <= 10        venda: RSI2(t) >= 90
        excursao    primeira barra da excursao (t-1 NAO estava no extremo)
        janela      915 <= hhmm(t) <= 1630
        t+1         existe, no mesmo dia e no mesmo bloco contiguo
    Regime (compra: close(t) > MME80(t); venda: close(t) < MME80(t)) e'
    ESTRATIFICACAO reportada, nao clausula (v1; ver REGIME_NA_CLAUSULA).

    D = K_ATR x ATR14(t) ao tick, congelado. `entrada_ref` = open(t+1).
    Alvo/stop = entrada_ref +- D (espelho na venda).

    `eden` (MME8 > MME80 e ambas subindo) e' calculado SO' como
    informacao do funil -- a ficha v0 usa MME80; escolher a variante
    olhando o funil seria calibracao (7.1).
    """
    x = d.copy()
    x["extremo_compra"] = x[col_rsi] <= RSI_SOBREVENDIDO
    x["extremo_venda"] = x[col_rsi] >= RSI_SOBRECOMPRADO
    prev_c = _por_bloco(x, "extremo_compra", lambda s: s.shift(1, fill_value=False))
    prev_v = _por_bloco(x, "extremo_venda", lambda s: s.shift(1, fill_value=False))
    x["excursao_compra"] = x["extremo_compra"] & ~prev_c.astype(bool)
    x["excursao_venda"] = x["extremo_venda"] & ~prev_v.astype(bool)
    x["regime_compra"] = x["close"] > x[col_mme80]
    x["regime_venda"] = x["close"] < x[col_mme80]
    x["janela"] = ((x["hhmm"] >= HORA_PRIMEIRO_FECHAMENTO)
                   & (x["hhmm"] <= HORA_ULTIMO_FECHAMENTO))

    prox_dia = x["dia"].shift(-1)
    prox_bloco = x["bloco"].shift(-1)
    x["tem_t1"] = (prox_dia == x["dia"]) & (prox_bloco == x["bloco"])
    x["entrada_ref"] = np.where(x["tem_t1"], x["open"].shift(-1), np.nan)

    x["D_pts"] = (K_ATR * x[col_atr]).map(arredondar_ao_tick)
    reg_c = x["regime_compra"] if REGIME_NA_CLAUSULA else True
    reg_v = x["regime_venda"] if REGIME_NA_CLAUSULA else True
    x["sinal_compra"] = (x["excursao_compra"] & reg_c
                         & x["janela"] & x["tem_t1"] & x["D_pts"].notna())
    x["sinal_venda"] = (x["excursao_venda"] & reg_v
                        & x["janela"] & x["tem_t1"] & x["D_pts"].notna())
    x["alvo"] = np.where(x["sinal_compra"], x["entrada_ref"] + x["D_pts"],
                np.where(x["sinal_venda"], x["entrada_ref"] - x["D_pts"], np.nan))
    x["stop"] = np.where(x["sinal_compra"], x["entrada_ref"] - x["D_pts"],
                np.where(x["sinal_venda"], x["entrada_ref"] + x["D_pts"], np.nan))

    # Informacao do funil, NAO clausula da v0.
    m8, m80 = x["mme8_ntsl"], x[col_mme80]
    m8p = _por_bloco(x, "mme8_ntsl", lambda s: s.shift(1))
    m80p = _por_bloco(x, col_mme80, lambda s: s.shift(1))
    x["eden_compra"] = (m8 > m80) & (m8 > m8p) & (m80 > m80p)
    x["eden_venda"] = (m8 < m80) & (m8 < m8p) & (m80 < m80p)
    return x


# ---------------------------------------------------------------------
# 5. Funil por clausula (7.4)
# ---------------------------------------------------------------------
def contar_clausulas(x: pd.DataFrame) -> pd.DataFrame:
    """Quantas barras sobrevivem a cada clausula, por lado, e por pregao.
    A ultima linha de cada lado e' o que a ficha chama de TAXA."""
    pregoes = max(int(x["dia"].nunique()), 1)
    linhas = []
    for lado in ("compra", "venda"):
        etapas = [
            ("extremo", x[f"extremo_{lado}"]),
            ("+excursao (1 sinal por excursao)", x[f"excursao_{lado}"]),
            ("+janela 09:15-16:30", x[f"excursao_{lado}"] & x["janela"]),
            ("+t+1 existe e D ok = SINAL", x[f"sinal_{lado}"]),
            ("(estrato) sinal a favor da MME80", x[f"sinal_{lado}"] & x[f"regime_{lado}"]),
            ("(estrato) sinal contra a MME80", x[f"sinal_{lado}"] & ~x[f"regime_{lado}"]),
            ("(info) sinal e regime Eden", x[f"sinal_{lado}"] & x[f"eden_{lado}"]),
        ]
        for nome, mask in etapas:
            n = int(mask.sum())
            linhas.append({"lado": lado, "clausula": nome, "n": n,
                           "por_pregao": round(n / pregoes, 2)})
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------
# 6. Pontos (7.5) e ambiguidade do estimador
# ---------------------------------------------------------------------
def em_pontos(x: pd.DataFrame, col_atr: str = "atr_ntsl") -> dict[str, Any]:
    atr = x[col_atr].dropna()
    sin = x[x["sinal_compra"] | x["sinal_venda"]]
    dd = sin["D_pts"].dropna()

    def q(s: pd.Series) -> dict[str, float]:
        if s.empty:
            return {}
        return {"p10": round(float(s.quantile(0.1)), 1),
                "p50": round(float(s.median()), 1),
                "p90": round(float(s.quantile(0.9)), 1)}

    # Borda bruta necessaria para pagar 11 pts: D x (2p1 - 1) > custo.
    # Em vez de um p1, a pergunta invertida: com D mediano, qual p1
    # empata o custo? p1_empate = 0,5 + custo / (2 D).
    d50 = float(dd.median()) if not dd.empty else float("nan")
    p1_empate = (0.5 + CUSTO_PONTOS / (2.0 * d50)) if d50 and not math.isnan(d50) else float("nan")
    dq = q(dd)
    return {"atr14_pts": q(atr), "D_pts": dq,
            "capital_recomendado_por_contrato_reais": (
                {"em_D_p50": capital_recomendado(dq["p50"]),
                 "em_D_p90": capital_recomendado(dq["p90"])} if dq else {}),
            "D_minimo_para_pagar_custo_a_p1_056_pts": round(CUSTO_PONTOS / (2 * 0.56 - 1), 1),
            "p1_que_empata_custo_com_D_mediano": (round(p1_empate, 3)
                                                  if not math.isnan(p1_empate) else None)}


def ambiguidade(x: pd.DataFrame, max_barras: int = 400) -> dict[str, Any]:
    """
    Para cada sinal, caminha de t+1 em diante DENTRO DO MESMO DIA ate' a
    primeira barra em que o alvo OU o stop cabem no [low, high]. Classifica:

        ambigua     essa barra contem os dois (alvo e stop): o OHLC nao diz
                    quem bateu primeiro
        resolvida   contem so' um deles
        por_tempo   o dia acabou sem tocar nenhum (zeragem 17:30)

    NAO devolve qual barreira bateu. E' diagnostico do estimador
    binario: se `ambigua` passar de ~10%, o estimador nao serve e a
    ficha volta ao desenho (EAS_DE_PRECO.md, 1). Tambem devolve a
    duracao em barras, para a clausula "posicao aberta ignora sinal".
    """
    highs, lows = x["high"].to_numpy(), x["low"].to_numpy()
    alvos, stops = x["alvo"].to_numpy(dtype=float), x["stop"].to_numpy(dtype=float)
    dias = x["dia"].to_numpy()
    idx_sinais = [int(i) for i in
                  np.flatnonzero((x["sinal_compra"] | x["sinal_venda"]).to_numpy())]
    cont = {"resolvida": 0, "ambigua": 0, "por_tempo": 0}
    duracoes: list[int] = []
    for i in idx_sinais:
        alvo, stop = float(alvos[i]), float(stops[i])
        lo_b, hi_b = min(alvo, stop), max(alvo, stop)
        j, classe = i + 1, "por_tempo"
        while j < len(x) and dias[j] == dias[i] and j - i <= max_barras:
            toca_hi = highs[j] >= hi_b
            toca_lo = lows[j] <= lo_b
            if toca_hi or toca_lo:
                classe = "ambigua" if (toca_hi and toca_lo) else "resolvida"
                break
            j += 1
        cont[classe] += 1
        duracoes.append(j - i)
    n = len(idx_sinais)
    frac = {k: (round(v / n, 3) if n else None) for k, v in cont.items()}
    dur = pd.Series(duracoes, dtype=float)
    return {"n_sinais": n, "contagem": cont, "fracao": frac,
            "duracao_barras": ({"p50": float(dur.median()),
                                "p90": float(dur.quantile(0.9))} if n else {})}


# ---------------------------------------------------------------------
# 7. Orquestracao
# ---------------------------------------------------------------------
def rodar(log_path: Path, saida: Path) -> dict[str, Any]:
    df, meta = carregar_log(log_path)
    d = indicadores(df)
    eq = equivalencia(d)
    x = marcar_ifr2(d)
    funil = contar_clausulas(x)
    pontos = em_pontos(x)
    amb = ambiguidade(x)

    saida.mkdir(parents=True, exist_ok=True)
    x.to_parquet(saida / "barras_m15.parquet", index=False)
    resumo = {"dump": meta, "equivalencia": eq, "pontos": pontos,
              "ambiguidade": amb, "funil_ifr2": funil.to_dict(orient="records")}
    (saida / "resumo.json").write_text(json.dumps(resumo, indent=2, default=str),
                                       encoding="utf-8")
    log.info("eas_preco.rodada", **meta, sinais=amb["n_sinais"], saida=str(saida))
    return {"meta": meta, "equivalencia": eq, "funil": funil,
            "pontos": pontos, "ambiguidade": amb, "barras": x}


# ---------------------------------------------------------------------
# 8. Ficha ORB v0 -- funil por PREGAO (docs/EAS_DE_PRECO.md, 4)
# ---------------------------------------------------------------------
def marcar_orb(d: pd.DataFrame, col_mme80: str = "mme80_ntsl") -> pd.DataFrame:
    """
    Uma linha por PREGAO. Clausulas, na ordem do funil:
        range       as duas barras 09:00 e 09:15 existem no dump
        amplitude   A = R_high - R_low >= 20 pts
        rompimento  primeira barra 09:30..11:45 em que high >= R_high +
                    tick (compra) ou low <= R_low - tick (venda). Os
                    dois lados armados, OCO (v1): o primeiro que rompe
                    e' o SINAL; os dois na MESMA barra = gatilho
                    ambiguo, fora (o OHLC nao ordena).
    Entrada = nivel rompido. D = A ao tick. Alvo = entrada + D, stop =
    entrada - D (espelho na venda). Regime (lado da MME80 no close de
    09:15) e' ESTRATO reportado (v1); com ORB_REGIME_NA_CLAUSULA=True
    (v0) so' o lado da MME80 ficava armado.

    Ambiguidade: a barra de resolucao contem alvo E stop; OU a barra do
    gatilho toca o stop (= R_low + tick na compra, dentro do range) --
    o OHLC nao diz se foi antes ou depois do rompimento. E' o custo de
    entrar por ordem stop sem tape; a fracao e' medida, nao assumida.
    """
    linhas = []
    for dia, g in d.groupby("dia", sort=True):
        g = g.sort_values("current_bar")
        r = g[g["hhmm"].isin(ORB_BARRAS_RANGE)]
        linha: dict[str, Any] = {"dia": dia, "range_ok": len(r) == 2}
        if len(r) != 2:
            linhas.append(linha)
            continue
        r_high, r_low = float(r["high"].max()), float(r["low"].min())
        a = r_high - r_low
        close_915 = float(r.iloc[-1]["close"])
        mme80 = float(r.iloc[-1][col_mme80])
        linha.update({"R_high": r_high, "R_low": r_low, "A_pts": a,
                      "amplitude_ok": a >= ORB_AMPLITUDE_MINIMA,
                      "regime_compra": close_915 > mme80,
                      "regime_venda": close_915 < mme80})
        janela = g[(g["hhmm"] >= ORB_PRIMEIRA_ENTRADA) & (g["hhmm"] <= ORB_ULTIMA_ENTRADA)]
        gat_c = janela[janela["high"] >= r_high + TICK_WIN]
        gat_v = janela[janela["low"] <= r_low - TICK_WIN]
        hh_c = int(gat_c.iloc[0]["hhmm"]) if len(gat_c) else None
        hh_v = int(gat_v.iloc[0]["hhmm"]) if len(gat_v) else None
        linha.update({"rompeu_compra_hhmm": hh_c, "rompeu_venda_hhmm": hh_v,
                      "rompeu_algum": (hh_c is not None) or (hh_v is not None)})

        # lado armado (v0: so' o da MME80; sem regime, o primeiro que romper)
        lado: str | None
        if ORB_REGIME_NA_CLAUSULA:
            lado = ("compra" if linha["regime_compra"] and hh_c is not None else
                    "venda" if linha["regime_venda"] and hh_v is not None else None)
            outro_antes = bool(
                (lado == "compra" and hh_v is not None and hh_c is not None and hh_v < hh_c)
                or (lado == "venda" and hh_c is not None and hh_v is not None and hh_c < hh_v))
        else:
            if hh_c is None and hh_v is None:
                lado = None
            elif hh_v is None or (hh_c is not None and hh_c < hh_v):
                lado = "compra"
            elif hh_c is None or hh_v < hh_c:
                lado = "venda"
            else:
                lado = "gatilho_ambiguo"     # os dois na mesma barra
            outro_antes = False
        linha["outro_lado_rompeu_antes"] = bool(outro_antes)
        linha["sinal"] = bool(lado in ("compra", "venda") and linha["amplitude_ok"])
        linha["lado"] = lado if linha["sinal"] else None
        linha["a_favor_mme80"] = bool(linha["sinal"] and (
            linha["regime_compra"] if lado == "compra" else linha["regime_venda"]))
        if not linha["sinal"]:
            linhas.append(linha)
            continue

        d_pts = arredondar_ao_tick(a)
        if lado == "compra":
            entrada = r_high + TICK_WIN
            alvo, stop, hh_gat = entrada + d_pts, entrada - d_pts, int(hh_c or 0)
        else:
            entrada = r_low - TICK_WIN
            alvo, stop, hh_gat = entrada - d_pts, entrada + d_pts, int(hh_v or 0)
        linha.update({"gatilho_hhmm": hh_gat, "entrada": entrada, "D_pts": d_pts,
                      "alvo": alvo, "stop": stop})
        # resolucao a partir da barra do gatilho (inclusive), ate' o fim do dia
        resto = g[g["hhmm"] >= hh_gat]
        classe, barras = "por_tempo", len(resto)
        for k, (_, b) in enumerate(resto.iterrows()):
            hi, lo = float(b["high"]), float(b["low"])
            if lado == "compra":
                t_alvo, t_stop = hi >= alvo, lo <= stop
            else:
                t_alvo, t_stop = lo <= alvo, hi >= stop
            # Na barra do GATILHO (k == 0) o stop fica dentro do range e o
            # OHLC nao diz se ele foi tocado ANTES ou DEPOIS do rompimento
            # (a barra pode ter ido ao fundo, subido e rompido). Alvo, nao:
            # esta' alem da entrada, so' e' alcancado depois dela. Logo, na
            # barra do gatilho, stop tocado = AMBIGUA sempre.
            if k == 0 and t_stop:
                classe, barras = "ambigua", 1
                break
            if t_alvo or t_stop:
                classe, barras = ("ambigua" if (t_alvo and t_stop) else "resolvida"), k + 1
                break
        linha.update({"classe": classe, "barras_ate_resolver": barras})
        linhas.append(linha)
    return pd.DataFrame(linhas)


def contar_clausulas_orb(o: pd.DataFrame) -> pd.DataFrame:
    n_preg = max(len(o), 1)

    def col(c: str) -> pd.Series:
        if c in o:
            return o[c].fillna(False).astype(bool)
        return pd.Series(False, index=o.index)

    lado = o["lado"] if "lado" in o else pd.Series(None, index=o.index, dtype=object)
    etapas = [
        ("pregoes no dump", pd.Series(True, index=o.index)),
        ("+range 09:00/09:15 presente", col("range_ok")),
        ("+amplitude >= 20 pts", col("range_ok") & col("amplitude_ok")),
        ("+rompeu algum lado ate' 11:45",
         col("range_ok") & col("amplitude_ok") & col("rompeu_algum")),
        ("+primeiro rompimento (um lado so' na barra) = SINAL", col("sinal")),
        ("(info) os dois lados na MESMA barra: gatilho ambiguo, fora",
         col("range_ok") & col("amplitude_ok") & col("rompeu_algum") & ~col("sinal")),
        ("(estrato) sinal de compra", col("sinal") & (lado == "compra")),
        ("(estrato) sinal de venda", col("sinal") & (lado == "venda")),
        ("(estrato) sinal a favor da MME80", col("sinal") & col("a_favor_mme80")),
        ("(estrato) sinal contra a MME80", col("sinal") & ~col("a_favor_mme80")),
    ]
    return pd.DataFrame([{"clausula": nome, "n": int(m.sum()),
                          "por_pregao": round(int(m.sum()) / n_preg, 3)} for nome, m in etapas])


def em_pontos_orb(o: pd.DataFrame) -> dict[str, Any]:
    def q(s: pd.Series) -> dict[str, float]:
        s = s.dropna()
        if s.empty:
            return {}
        return {"p10": round(float(s.quantile(0.1)), 1), "p50": round(float(s.median()), 1),
                "p90": round(float(s.quantile(0.9)), 1)}
    sin = o[o.get("sinal", pd.Series(False, index=o.index)).fillna(False).astype(bool)]
    a_all = o["A_pts"] if "A_pts" in o else pd.Series(dtype=float)
    d50 = float(sin["D_pts"].median()) if len(sin) else float("nan")
    gat = sin["gatilho_hhmm"].dropna() if "gatilho_hhmm" in sin else pd.Series(dtype=float)
    cls = sin["classe"].value_counts().to_dict() if "classe" in sin else {}
    n = len(sin)
    dq = q(sin["D_pts"]) if n else {}
    return {"A_pts_todos_os_pregoes": q(a_all), "D_pts_nos_sinais": dq,
            "capital_recomendado_por_contrato_reais": (
                {"em_D_p50": capital_recomendado(dq["p50"]),
                 "em_D_p90": capital_recomendado(dq["p90"])} if dq else {}),
            "p1_que_empata_custo_com_D_mediano": (round(0.5 + CUSTO_PONTOS / (2 * d50), 3)
                                                  if n and d50 else None),
            "gatilho_hhmm": q(gat) if len(gat) else {},
            "classes": cls,
            "fracao_ambigua": (round(cls.get("ambigua", 0) / n, 3) if n else None),
            "barras_ate_resolver": q(sin["barras_ate_resolver"]) if n else {}}


def rodar_orb(log_path: Path, saida: Path) -> dict[str, Any]:
    df, meta = carregar_log(log_path)
    d = indicadores(df)
    eq = equivalencia(d)
    o = marcar_orb(d)
    funil = contar_clausulas_orb(o)
    pontos = em_pontos_orb(o)
    saida.mkdir(parents=True, exist_ok=True)
    o.to_parquet(saida / "pregoes_orb.parquet", index=False)
    resumo = {"dump": meta, "equivalencia": eq, "pontos": pontos,
              "funil_orb": funil.to_dict(orient="records")}
    (saida / "resumo_orb.json").write_text(json.dumps(resumo, indent=2, default=str),
                                           encoding="utf-8")
    n_sin = int(o["sinal"].sum()) if "sinal" in o else 0
    log.info("eas_preco.rodada_orb", **meta, sinais=n_sin, saida=str(saida))
    return {"meta": meta, "equivalencia": eq, "funil": funil, "pontos": pontos,
            "pregoes": o, "n_sinais": n_sin}


# ---------------------------------------------------------------------
# 9. Ficha 123 v0 -- funil por BARRA (docs/EAS_DE_PRECO.md, 5)
# ---------------------------------------------------------------------
# Declarados, nao calibrados.
P123_REGIME_NA_CLAUSULA = True       # v0: a favor da MME80 (pullback em tendencia)
P123_PRIMEIRO_FECHAMENTO = 930       # t fecha a partir daqui (3 barras formadas)
P123_ULTIMO_FECHAMENTO = 1630
P123_D_MINIMO = 4 * TICK_WIN         # 20 pts


# ---------------------------------------------------------------------
# PERFIS DE INSTRUMENTO (2026-09-15, EAS_DE_PRECO.md 8)
# ---------------------------------------------------------------------
# As fichas sao por instrumento: o MECANISMO e' o mesmo, os NUMEROS que
# elas congelam (tick, custo, sessao, D minimo) sao do instrumento. Os
# modulos de research e o EA leem estes globais em tempo de chamada;
# `usar_instrumento("wdo")` religa todos de uma vez, e loga. O default
# (nunca chamado) e' o WIN, com os valores com que as tres fichas foram
# testadas em 10 anos -- nada muda para quem nao chama.
#
# WDO (mini-dolar): tick 0,5 pt; 1 pt = R$10 por contrato; custo
# ida-e-volta ~R$3 = 0,30 pt (declarado, a conferir na nota de
# corretagem); pregao 09:00-18:00 (ultima barra M15 17:45); zeragem e
# janela iguais ao WIN. A CONFIRMAR NO DUMP: barras/pregao (~36) e o
# rotulo da ultima barra.
@dataclass(frozen=True)
class Instrumento:
    nome: str
    tick: float
    custo_pontos: float
    valor_ponto_reais: float
    hora_primeiro_fechamento: int
    hora_ultimo_fechamento: int
    orb_barras_range: tuple[int, int]
    orb_primeira_entrada: int
    orb_ultima_entrada: int
    fim_sessao_hhmm: int

    @property
    def d_minimo(self) -> float:
        return 4 * self.tick

    def resumo(self) -> dict[str, Any]:
        return {"nome": self.nome, "tick": self.tick, "custo_pontos": self.custo_pontos,
                "valor_ponto_reais": self.valor_ponto_reais,
                "janela": [self.hora_primeiro_fechamento, self.hora_ultimo_fechamento],
                "orb_range": list(self.orb_barras_range),
                "orb_entrada": [self.orb_primeira_entrada, self.orb_ultima_entrada],
                "fim_sessao": self.fim_sessao_hhmm, "d_minimo": self.d_minimo}


PERFIS: dict[str, Instrumento] = {
    "win": Instrumento("win", 5.0, 11.0, 0.20, 915, 1630, (900, 915), 930, 1145, 1830),
    "wdo": Instrumento("wdo", 0.5, 0.30, 10.0, 915, 1630, (900, 915), 930, 1145, 1800),
}
INSTRUMENTO: Instrumento = PERFIS["win"]


def usar_instrumento(nome: str) -> Instrumento:
    """Religa os globais deste modulo para o instrumento. Chamar UMA vez,
    antes de qualquer funil/teste; o hash da ficha inclui o perfil."""
    global TICK_WIN, CUSTO_PONTOS, VALOR_PONTO_REAIS, HORA_PRIMEIRO_FECHAMENTO
    global HORA_ULTIMO_FECHAMENTO, ORB_BARRAS_RANGE, ORB_PRIMEIRA_ENTRADA
    global ORB_ULTIMA_ENTRADA, ORB_AMPLITUDE_MINIMA, P123_PRIMEIRO_FECHAMENTO
    global P123_ULTIMO_FECHAMENTO, P123_D_MINIMO, INSTRUMENTO
    if nome not in PERFIS:
        raise SystemExit(f"instrumento {nome!r} nao tem perfil; use {sorted(PERFIS)}")
    i = PERFIS[nome]
    TICK_WIN, CUSTO_PONTOS, VALOR_PONTO_REAIS = i.tick, i.custo_pontos, i.valor_ponto_reais
    HORA_PRIMEIRO_FECHAMENTO, HORA_ULTIMO_FECHAMENTO = (i.hora_primeiro_fechamento,
                                                       i.hora_ultimo_fechamento)
    ORB_BARRAS_RANGE = i.orb_barras_range
    ORB_PRIMEIRA_ENTRADA, ORB_ULTIMA_ENTRADA = i.orb_primeira_entrada, i.orb_ultima_entrada
    ORB_AMPLITUDE_MINIMA = i.d_minimo
    P123_PRIMEIRO_FECHAMENTO = 930
    P123_ULTIMO_FECHAMENTO = i.hora_ultimo_fechamento
    P123_D_MINIMO = i.d_minimo
    INSTRUMENTO = i
    log.info("eas_preco.instrumento", **i.resumo())
    return i


def avaliar_123(hi2: float, lo2: float, hi1: float, lo1: float,
                hi: float, lo: float, close: float, mme80: float, hhmm: int,
                regime_na_clausula: bool = P123_REGIME_NA_CLAUSULA) -> dict[str, Any] | None:
    """
    A FORMULA da ficha 123 no fechamento de t, escalar -- e' a que o EA
    (`ea/sinal_123.py`) usa ao vivo, e `marcar_123` (vetorizada, usada
    nos 10 anos de teste) e' conferida contra ela por teste de
    equivalencia. Uma formula, dois lados (skill disciplina, 7.3).

    Devolve o candidato ARMADO (sem o gatilho, que e' t+1 / a corretora)
    ou None: {"lado", "entrada", "stop", "alvo", "D_pts", "regime_ok"}.
    """
    padrao_c = lo1 < lo2 and lo1 < lo
    padrao_v = hi1 > hi2 and hi1 > hi
    janela = P123_PRIMEIRO_FECHAMENTO <= hhmm <= P123_ULTIMO_FECHAMENTO
    if not janela:
        return None
    if padrao_c and (not regime_na_clausula or close > mme80):
        entrada, stop = hi + TICK_WIN, lo1 - TICK_WIN
        d_pts = arredondar_ao_tick(entrada - stop)
        if d_pts >= P123_D_MINIMO:
            return {"lado": "compra", "entrada": entrada, "stop": entrada - d_pts,
                    "alvo": entrada + d_pts, "D_pts": d_pts, "regime_ok": close > mme80}
    if padrao_v and (not regime_na_clausula or close < mme80):
        entrada, stop = lo - TICK_WIN, hi1 + TICK_WIN
        d_pts = arredondar_ao_tick(stop - entrada)
        if d_pts >= P123_D_MINIMO:
            return {"lado": "venda", "entrada": entrada, "stop": entrada + d_pts,
                    "alvo": entrada - d_pts, "D_pts": d_pts, "regime_ok": close < mme80}
    return None


def marcar_123(d: pd.DataFrame, col_mme80: str = "mme80_ntsl") -> pd.DataFrame:
    """
    Barra t fecha o padrao (t-2, t-1, t). Clausulas, na ordem do funil:
        padrao     COMPRA: low(t-1) < low(t-2) e low(t-1) < low(t) (a 2a e'
                   a menor minima; empate NAO forma). VENDA: espelho nas
                   maximas.
        regime     COMPRA: close(t) > MME80(t); VENDA: <. (v0: clausula;
                   contado tambem sem regime como informacao)
        janela     930 <= hhmm(t) <= 1630
        D          entrada - stop >= 20 pts
        gatilho    t+1 existe no mesmo dia/bloco e toca a entrada:
                   high(t+1) >= high(t) + tick (compra); espelho na venda
    Entrada = high(t) + tick. Stop = low(t-1) - tick. D = entrada - stop
    ao tick. Alvo = entrada + D. Venda espelho.
    """
    x = d.copy()
    g = x.groupby("bloco", group_keys=False)
    lo1, lo2 = g["low"].shift(1), g["low"].shift(2)
    hi1, hi2 = g["high"].shift(1), g["high"].shift(2)
    x["padrao_compra"] = (lo1 < lo2) & (lo1 < x["low"])
    x["padrao_venda"] = (hi1 > hi2) & (hi1 > x["high"])
    x["regime_compra"] = x["close"] > x[col_mme80]
    x["regime_venda"] = x["close"] < x[col_mme80]
    x["janela"] = (x["hhmm"] >= P123_PRIMEIRO_FECHAMENTO) & (x["hhmm"] <= P123_ULTIMO_FECHAMENTO)
    x["tem_t1"] = (x["dia"].shift(-1) == x["dia"]) & (x["bloco"].shift(-1) == x["bloco"])
    hi_t1, lo_t1 = x["high"].shift(-1), x["low"].shift(-1)

    ent_c, stop_c = x["high"] + TICK_WIN, lo1 - TICK_WIN
    ent_v, stop_v = x["low"] - TICK_WIN, hi1 + TICK_WIN
    x["D_compra"] = (ent_c - stop_c).map(arredondar_ao_tick)
    x["D_venda"] = (stop_v - ent_v).map(arredondar_ao_tick)
    x["gatilho_compra"] = x["tem_t1"] & (hi_t1 >= ent_c)
    x["gatilho_venda"] = x["tem_t1"] & (lo_t1 <= ent_v)
    reg_c = x["regime_compra"] if P123_REGIME_NA_CLAUSULA else True
    reg_v = x["regime_venda"] if P123_REGIME_NA_CLAUSULA else True
    x["sinal_compra"] = (x["padrao_compra"] & reg_c & x["janela"]
                         & (x["D_compra"] >= P123_D_MINIMO) & x["gatilho_compra"])
    x["sinal_venda"] = (x["padrao_venda"] & reg_v & x["janela"]
                        & (x["D_venda"] >= P123_D_MINIMO) & x["gatilho_venda"])
    x["entrada"] = np.where(x["sinal_compra"], ent_c, np.where(x["sinal_venda"], ent_v, np.nan))
    x["D_pts"] = np.where(x["sinal_compra"], x["D_compra"],
                 np.where(x["sinal_venda"], x["D_venda"], np.nan))
    x["stop"] = np.where(x["sinal_compra"], x["entrada"] - x["D_pts"],
                np.where(x["sinal_venda"], x["entrada"] + x["D_pts"], np.nan))
    x["alvo"] = np.where(x["sinal_compra"], x["entrada"] + x["D_pts"],
                np.where(x["sinal_venda"], x["entrada"] - x["D_pts"], np.nan))
    # info: inside bar em t (a pagina do QuantBrasil oferece como filtro; v0 nao usa)
    x["inside_bar"] = (x["high"] <= hi1) & (x["low"] >= lo1)
    return x


def contar_clausulas_123(x: pd.DataFrame) -> pd.DataFrame:
    pregoes = max(int(x["dia"].nunique()), 1)
    linhas = []
    for lado in ("compra", "venda"):
        p, r = x[f"padrao_{lado}"], x[f"regime_{lado}"]
        j, dd, gt = x["janela"], x[f"D_{lado}"] >= P123_D_MINIMO, x[f"gatilho_{lado}"]
        reg = r if P123_REGIME_NA_CLAUSULA else pd.Series(True, index=x.index)
        etapas = [
            ("padrao (3 barras)", p),
            ("+regime MME80" if P123_REGIME_NA_CLAUSULA else "(regime = estrato)", p & reg),
            ("+janela 09:30-16:30", p & reg & j),
            ("+D >= 20 pts", p & reg & j & dd),
            ("+gatilho em t+1 = SINAL", x[f"sinal_{lado}"]),
            ("(info) SINAL sem exigir regime", p & j & dd & gt),
            ("(info) sinal com inside bar em t", x[f"sinal_{lado}"] & x["inside_bar"]),
            ("(estrato) sinal a favor da MME80", x[f"sinal_{lado}"] & r),
            ("(estrato) sinal contra a MME80", x[f"sinal_{lado}"] & ~r),
        ]
        for nome, m in etapas:
            n = int(m.sum())
            linhas.append({"lado": lado, "clausula": nome, "n": n,
                           "por_pregao": round(n / pregoes, 2)})
    return pd.DataFrame(linhas)


def ambiguidade_123(x: pd.DataFrame, max_barras: int = 400) -> dict[str, Any]:
    """Como `ambiguidade`, com a regra da barra do gatilho (t+1): stop
    tocado nela = ambigua (o OHLC nao ordena contra o rompimento); alvo
    nela = resolvida. NAO diz qual barreira bateu."""
    highs, lows = x["high"].to_numpy(dtype=float), x["low"].to_numpy(dtype=float)
    alvos, stops = x["alvo"].to_numpy(dtype=float), x["stop"].to_numpy(dtype=float)
    dias = x["dia"].to_numpy()
    sc, sv = x["sinal_compra"].to_numpy(dtype=bool), x["sinal_venda"].to_numpy(dtype=bool)
    cont = {"resolvida": 0, "ambigua": 0, "por_tempo": 0}
    dur: list[int] = []
    for i in [int(k) for k in np.flatnonzero(sc | sv)]:
        compra = sc[i]
        j, classe = i + 1, "por_tempo"
        while j < len(x) and dias[j] == dias[i] and j - i <= max_barras:
            t_alvo = highs[j] >= alvos[i] if compra else lows[j] <= alvos[i]
            t_stop = lows[j] <= stops[i] if compra else highs[j] >= stops[i]
            if (j == i + 1 and t_stop) or (t_alvo and t_stop):
                classe = "ambigua"
                break
            if t_alvo or t_stop:
                classe = "resolvida"
                break
            j += 1
        cont[classe] += 1
        dur.append(j - i)
    n = len(dur)
    s = pd.Series(dur, dtype=float)
    return {"n_sinais": n, "contagem": cont,
            "fracao": {k: (round(v / n, 3) if n else None) for k, v in cont.items()},
            "duracao_barras": ({"p50": float(s.median()), "p90": float(s.quantile(0.9))}
                               if n else {})}


def em_pontos_123(x: pd.DataFrame) -> dict[str, Any]:
    sin = x[x["sinal_compra"] | x["sinal_venda"]]
    dd = sin["D_pts"].dropna()

    def q(s: pd.Series) -> dict[str, float]:
        return ({"p10": round(float(s.quantile(0.1)), 1), "p50": round(float(s.median()), 1),
                 "p90": round(float(s.quantile(0.9)), 1)} if not s.empty else {})
    dq = q(dd)
    d50 = float(dd.median()) if not dd.empty else float("nan")
    return {"D_pts": dq,
            "capital_recomendado_por_contrato_reais": (
                {"em_D_p50": capital_recomendado(dq["p50"]),
                 "em_D_p90": capital_recomendado(dq["p90"])} if dq else {}),
            "p1_que_empata_custo_com_D_mediano": (round(0.5 + CUSTO_PONTOS / (2 * d50), 3)
                                                  if dq else None)}


def rodar_123(log_path: Path, saida: Path) -> dict[str, Any]:
    df, meta = carregar_log(log_path)
    d = indicadores(df)
    eq = equivalencia(d)
    x = marcar_123(d)
    funil = contar_clausulas_123(x)
    pontos = em_pontos_123(x)
    amb = ambiguidade_123(x)
    saida.mkdir(parents=True, exist_ok=True)
    x.to_parquet(saida / "barras_123.parquet", index=False)
    resumo = {"dump": meta, "equivalencia": eq, "pontos": pontos, "ambiguidade": amb,
              "funil_123": funil.to_dict(orient="records")}
    (saida / "resumo_123.json").write_text(json.dumps(resumo, indent=2, default=str),
                                           encoding="utf-8")
    log.info("eas_preco.rodada_123", **meta, sinais=amb["n_sinais"], saida=str(saida))
    return {"meta": meta, "equivalencia": eq, "funil": funil, "pontos": pontos,
            "ambiguidade": amb, "barras": x}
