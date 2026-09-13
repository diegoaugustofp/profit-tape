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
# FICHA v1 (2026-09-13, docs/EAS_DE_PRECO.md 3): K = 0,5. O v0 (K = 1)
# dava D mediano de 510 pts com p90 de 805 -- acima do stop catastrofico
# de 500 pts do risco.py; o teste mediria o seguro de cauda, nao o IFR2.
# Com 0,5: D mediano ~255 pts, o mesmo stop mediano da Rota B.
# Incompatibilidade de MECANISMO, decidida antes de congelar; nao e'
# calibracao por resultado (nenhum p1 foi olhado).
K_ATR = 0.5                    # D = K_ATR x ATR14(t), ao tick
# FICHA v1: o regime MME80 SAIU da clausula (7.4: cortava 70% dos sinais,
# 1,09/pregao -> ~980 pregoes para n=1.070). Passa a ESTRATIFICACAO
# reportada -- o primario e' o total; o regime nunca e' escolhido depois.
REGIME_NA_CLAUSULA = False
TICK_WIN = 5.0                 # pontos por tick
HORA_PRIMEIRO_FECHAMENTO = 915     # HHMM, inclusivo: t fecha a partir daqui
HORA_ULTIMO_FECHAMENTO = 1630      # HHMM, inclusivo
MINUTOS_BARRA = 15
CUSTO_PONTOS = 11.0            # ida e volta, por contrato


def arredondar_ao_tick(pts: float, tick: float = TICK_WIN) -> float:
    """Meio-tick vai para CIMA (mesma funcao do bollinger_scalp: `round()`
    do Python arredonda 32,5 para 32 -- pego na conferencia a mao)."""
    if pd.isna(pts):
        return float("nan")
    return float(max(tick, math.floor(pts / tick + 0.5) * tick))


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
    return {"atr14_pts": q(atr), "D_pts": q(dd),
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
