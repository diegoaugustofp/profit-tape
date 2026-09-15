"""
IFR2 (M15) -- o TESTE da ficha CONGELADA (docs/EAS_DE_PRECO.md, 3.2).

O QUE ESTE MODULO E'
--------------------
Calcula p1 (a barreira favoravel bate antes da desfavoravel) sobre UMA
das tres amostras que a ficha congelou, e so' nela:

    teste        2023-01-01 .. 2025-12-31   primario, UMA rodada
    replicacao   2026-01-01 .. 2026-08-13   reportada depois, sem veto
    depuracao    2026-08-14 ..              barras olhadas uma a uma;
                                            NAO produz p1 interpretavel

Recusa dias fora da amostra pedida (misturar amostras e' o que a ficha
proibe), recusa rodar `teste` duas vezes na mesma pasta (a rodada e'
UMA -- `--forcar` exige motivo, e o motivo fica gravado), e carimba a
saida com a tag do codigo e o hash dos parametros da ficha.

O que NAO faz: nao ajusta nada, nao escolhe estrato, nao roda variante.
Os numeros da regra vem de `eas_preco` (RSI_SOBREVENDIDO, K_ATR, ...) e
sao os da ficha. Mudar qualquer um la' muda o hash aqui, e a saida deixa
de ser comparavel -- e' o carimbo de versao da disciplina forward.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog

from . import eas_preco as ep
from .fase2 import _carimbo

log = structlog.get_logger(__name__)

# AMOSTRAS CONGELADAS (2026-09-13). Datas, nao contagens: "os 20 pregoes
# mais recentes" mudaria com o proximo dump; 2026-08-14 nao muda.
AMOSTRAS: dict[str, tuple[dt.date, dt.date]] = {
    "teste": (dt.date(2023, 1, 1), dt.date(2025, 12, 31)),
    "replicacao": (dt.date(2026, 1, 1), dt.date(2026, 8, 13)),
    "depuracao": (dt.date(2026, 8, 14), dt.date(2099, 12, 31)),
    # Declarada 2026-09-14 (ORB inconclusivo em teste + replicacao): TODO
    # o historico que o teste nao tocou, como UMA amostra. Veredito final
    # sobre o combinado (`combinar`); por-ano so' reportado.
    "historico_2015_22": (dt.date(2015, 1, 1), dt.date(2022, 12, 31)),
}
# Amostras que entram no veredito COMBINADO (depuracao nunca entra).
AMOSTRAS_COMBINAVEIS = ("teste", "replicacao", "historico_2015_22")

# CRITERIO das fichas (ponto estimado; IC sempre reportado).
P1_FAVORAVEL = 0.56
P1_CONTRA = 0.50
Z95 = 1.959963984540054


def z_ic(trial: int) -> float:
    """IC de (1 - 0,05/trial): Bonferroni sobre os trials da FAMILIA na
    mesma amostra -- o preco honesto de usar 2023-2025 mais de uma vez.
    trial 1 -> 1,960 (95%); trial 2 -> 2,241 (97,5%)."""
    from statistics import NormalDist
    return float(NormalDist().inv_cdf(1 - 0.05 / (2 * trial)))


# TRIAL: quantas vezes a amostra 2023-2025 foi usada pela familia.
#   ifr2: trial 1 = K 0,5 (CONTRA); trial 2 = K 1,0 (CONTRA). FECHADA.
#   orb : trial 1 (v1: regime estrato, D = A).
_COMUM: dict[str, Any] = {
    "MME_LONGA": ep.MME_LONGA, "TICK_WIN": ep.TICK_WIN, "CUSTO_PONTOS": ep.CUSTO_PONTOS,
    "P1_FAVORAVEL": P1_FAVORAVEL, "P1_CONTRA": P1_CONTRA,
}
FICHAS: dict[str, dict[str, Any]] = {
    "ifr2": {**_COMUM, "TRIAL": 2,
             "RSI_PERIODO": ep.RSI_PERIODO, "RSI_SOBREVENDIDO": ep.RSI_SOBREVENDIDO,
             "RSI_SOBRECOMPRADO": ep.RSI_SOBRECOMPRADO, "ATR_PERIODO": ep.ATR_PERIODO,
             "K_ATR": ep.K_ATR, "REGIME_NA_CLAUSULA": ep.REGIME_NA_CLAUSULA,
             "HORA_PRIMEIRO_FECHAMENTO": ep.HORA_PRIMEIRO_FECHAMENTO,
             "HORA_ULTIMO_FECHAMENTO": ep.HORA_ULTIMO_FECHAMENTO},
    "orb": {**_COMUM, "TRIAL": 1,
            "ORB_BARRAS_RANGE": list(ep.ORB_BARRAS_RANGE),
            "ORB_PRIMEIRA_ENTRADA": ep.ORB_PRIMEIRA_ENTRADA,
            "ORB_ULTIMA_ENTRADA": ep.ORB_ULTIMA_ENTRADA,
            "ORB_AMPLITUDE_MINIMA": ep.ORB_AMPLITUDE_MINIMA,
            "ORB_REGIME_NA_CLAUSULA": ep.ORB_REGIME_NA_CLAUSULA},
    "123": {**_COMUM, "TRIAL": 1,
            "P123_REGIME_NA_CLAUSULA": ep.P123_REGIME_NA_CLAUSULA,
            "P123_PRIMEIRO_FECHAMENTO": ep.P123_PRIMEIRO_FECHAMENTO,
            "P123_ULTIMO_FECHAMENTO": ep.P123_ULTIMO_FECHAMENTO,
            "P123_D_MINIMO": ep.P123_D_MINIMO},
}
# Compatibilidade com quem importa os nomes antigos (IFR2).
PARAMETROS_FICHA = FICHAS["ifr2"]
TRIAL = FICHAS["ifr2"]["TRIAL"]
Z_IC = z_ic(TRIAL)


def parametros_da_ficha(ficha: str) -> dict[str, Any]:
    """Parametros CONGELADOS + o perfil do instrumento em vigor. Os valores
    dependentes de instrumento sao lidos AGORA (apos `usar_instrumento`),
    nao na importacao."""
    base = dict(FICHAS[ficha])
    base.update({"TICK_WIN": ep.TICK_WIN, "CUSTO_PONTOS": ep.CUSTO_PONTOS,
                 "INSTRUMENTO": ep.INSTRUMENTO.resumo()})
    if ficha == "ifr2":
        base.update({"HORA_PRIMEIRO_FECHAMENTO": ep.HORA_PRIMEIRO_FECHAMENTO,
                     "HORA_ULTIMO_FECHAMENTO": ep.HORA_ULTIMO_FECHAMENTO})
    elif ficha == "orb":
        base.update({"ORB_BARRAS_RANGE": list(ep.ORB_BARRAS_RANGE),
                     "ORB_PRIMEIRA_ENTRADA": ep.ORB_PRIMEIRA_ENTRADA,
                     "ORB_ULTIMA_ENTRADA": ep.ORB_ULTIMA_ENTRADA,
                     "ORB_AMPLITUDE_MINIMA": ep.ORB_AMPLITUDE_MINIMA})
    elif ficha == "123":
        base.update({"P123_ULTIMO_FECHAMENTO": ep.P123_ULTIMO_FECHAMENTO,
                     "P123_D_MINIMO": ep.P123_D_MINIMO})
    return base


def hash_ficha(ficha: str = "ifr2") -> str:
    return hashlib.sha256(json.dumps(parametros_da_ficha(ficha), sort_keys=True,
                                     default=str).encode()).hexdigest()[:12]


# ---------------------------------------------------------------------
# 1. Portao de amostra
# ---------------------------------------------------------------------
def recortar_amostra(x: pd.DataFrame, amostra: str) -> pd.DataFrame:
    """Devolve so' os dias da amostra pedida. Se o dump contem dias FORA
    dela, recusa: o operador tem que fatiar o dump (ou passar o dump
    certo), nao este codigo escolher silenciosamente."""
    if amostra not in AMOSTRAS:
        raise SystemExit(f"amostra '{amostra}' nao existe; use {sorted(AMOSTRAS)}")
    ini, fim = AMOSTRAS[amostra]
    dias = pd.to_datetime(x["dia"].astype(str)).dt.date
    fora = x[(dias < ini) | (dias > fim)]
    if len(fora):
        raise SystemExit(
            f"o dump tem {int(fora['dia'].nunique())} pregao(oes) FORA da amostra "
            f"'{amostra}' ({ini}..{fim}): {fora['dia'].min()} .. {fora['dia'].max()}.\n"
            "  A ficha proibe misturar amostras. Passe um dump so' com os dias "
            "desta amostra (janelas de data no .ntsl) ou fatie o .txt.")
    return x


# ---------------------------------------------------------------------
# 2. Resultado binario por sinal
# ---------------------------------------------------------------------
def resolver_sinais(x: pd.DataFrame, max_barras: int = 400) -> pd.DataFrame:
    """
    Para cada sinal (marcado por `eas_preco.marcar_ifr2`), caminha de t+1
    em diante DENTRO DO MESMO DIA ate' a primeira barra em que o alvo ou o
    stop cabem no [low, high].

        resultado   +1 favoravel bateu, -1 desfavoravel bateu,
                     0 ambigua (os dois na mesma barra), NaN por tempo
    """
    highs, lows = x["high"].to_numpy(dtype=float), x["low"].to_numpy(dtype=float)
    alvos, stops = x["alvo"].to_numpy(dtype=float), x["stop"].to_numpy(dtype=float)
    dias = x["dia"].to_numpy()
    sc = x["sinal_compra"].to_numpy(dtype=bool)
    sv = x["sinal_venda"].to_numpy(dtype=bool)
    d_all = x["D_pts"].to_numpy(dtype=float)
    hhmm = x["hhmm"].to_numpy(dtype=int)
    cbar = x["current_bar"].to_numpy(dtype=int)
    entr = x["entrada_ref"].to_numpy(dtype=float)
    reg_c = x["regime_compra"].to_numpy(dtype=bool)
    reg_v = x["regime_venda"].to_numpy(dtype=bool)
    idx = [int(i) for i in np.flatnonzero(sc | sv)]
    linhas = []
    for i in idx:
        alvo, stop = alvos[i], stops[i]
        lado = "compra" if sc[i] else "venda"
        j, classe, res = i + 1, "por_tempo", float("nan")
        while j < len(x) and dias[j] == dias[i] and j - i <= max_barras:
            toca_alvo = (highs[j] >= alvo) if lado == "compra" else (lows[j] <= alvo)
            toca_stop = (lows[j] <= stop) if lado == "compra" else (highs[j] >= stop)
            if toca_alvo and toca_stop:
                classe, res = "ambigua", 0.0
                break
            if toca_alvo:
                classe, res = "resolvida", 1.0
                break
            if toca_stop:
                classe, res = "resolvida", -1.0
                break
            j += 1
        d_pts = float(d_all[i])
        linhas.append({
            "dia": dias[i], "hhmm": int(hhmm[i]), "current_bar": int(cbar[i]), "lado": lado,
            "a_favor_mme80": bool(reg_c[i] if lado == "compra" else reg_v[i]),
            "entrada": float(entr[i]), "alvo": alvo, "stop": stop,
            "D_pts": d_pts, "classe": classe, "resultado": res,
            "barras": j - i,
            "pnl_bruto_pts": (res * d_pts) if classe == "resolvida" else float("nan"),
            "barra_resolucao_hhmm": (int(hhmm[j]) if j < len(x) and classe != "por_tempo"
                                     else None),
        })
    return pd.DataFrame(linhas)


def resolver_orb(d: pd.DataFrame) -> pd.DataFrame:
    """
    Resultado por PREGAO da ficha ORB v1 (docs/EAS_DE_PRECO.md 4.1). A
    classificacao (gatilho, classe) vem de `eas_preco.marcar_orb`; o
    RESULTADO (+1/-1) e' calculado aqui, de proposito fora do funil.

    Alem das classes do IFR2, o ORB reporta o P&L de ZERAGEM das
    operacoes por tempo (close da ultima barra do dia - entrada): elas
    sao 12-24% dos pregoes e excluir sem dizer o que valeram nao e'
    neutro. Fica fora do p1 (que e' binario) e entra so' no P&L
    reportado.
    """
    o = ep.marcar_orb(d)
    o = o[o["sinal"].fillna(False).astype(bool)].copy()
    linhas = []
    for _, ln in o.iterrows():
        g = d[d["dia"] == ln["dia"]].sort_values("current_bar")
        lado = ln["lado"]
        alvo, stop, entrada = float(ln["alvo"]), float(ln["stop"]), float(ln["entrada"])
        resto = g[g["hhmm"] >= int(ln["gatilho_hhmm"])]
        classe, res, k_res = "por_tempo", float("nan"), len(resto)
        for k, (_, b) in enumerate(resto.iterrows()):
            hi, lo = float(b["high"]), float(b["low"])
            t_alvo = (hi >= alvo) if lado == "compra" else (lo <= alvo)
            t_stop = (lo <= stop) if lado == "compra" else (hi >= stop)
            if k == 0 and t_stop:
                classe, res, k_res = "ambigua", 0.0, 1
                break
            if t_alvo and t_stop:
                classe, res, k_res = "ambigua", 0.0, k + 1
                break
            if t_alvo:
                classe, res, k_res = "resolvida", 1.0, k + 1
                break
            if t_stop:
                classe, res, k_res = "resolvida", -1.0, k + 1
                break
        d_pts = float(ln["D_pts"])
        close_final = float(g.iloc[-1]["close"])
        sinal_lado = 1.0 if lado == "compra" else -1.0
        pnl_zeragem = ((close_final - entrada) * sinal_lado if classe == "por_tempo"
                       else float("nan"))
        linhas.append({
            "dia": ln["dia"], "hhmm": int(ln["gatilho_hhmm"]),
            "current_bar": int(g.iloc[0]["current_bar"]),
            "lado": lado, "a_favor_mme80": bool(ln["a_favor_mme80"]),
            "entrada": entrada, "alvo": alvo, "stop": stop, "D_pts": d_pts,
            "classe": classe, "resultado": res, "barras": k_res,
            "pnl_bruto_pts": (res * d_pts) if classe == "resolvida" else float("nan"),
            "pnl_zeragem_pts": pnl_zeragem,
            "barra_resolucao_hhmm": None,
        })
    return pd.DataFrame(linhas)


def resolver_123(d: pd.DataFrame) -> pd.DataFrame:
    """
    Resultado por sinal da ficha 123 (docs/EAS_DE_PRECO.md 5), SEQUENCIAL
    dentro do dia: "posicao aberta ignora sinal" -- um sinal cujo t+1 cai
    dentro de uma operacao ainda aberta e' PULADO (classe=ignorado_posicao,
    contado, fora do p1). Barra do gatilho (t+1): stop tocado = ambigua;
    alvo tocado = favoravel. Por tempo: P&L na zeragem 17:30 reportado.
    """
    x = ep.marcar_123(d).reset_index(drop=True)
    highs, lows = x["high"].to_numpy(dtype=float), x["low"].to_numpy(dtype=float)
    closes = x["close"].to_numpy(dtype=float)
    alvos, stops = x["alvo"].to_numpy(dtype=float), x["stop"].to_numpy(dtype=float)
    entr, d_all = x["entrada"].to_numpy(dtype=float), x["D_pts"].to_numpy(dtype=float)
    dias, hhmm = x["dia"].to_numpy(), x["hhmm"].to_numpy(dtype=int)
    cbar = x["current_bar"].to_numpy(dtype=int)
    sc, sv = x["sinal_compra"].to_numpy(dtype=bool), x["sinal_venda"].to_numpy(dtype=bool)
    reg_c, reg_v = x["regime_compra"].to_numpy(dtype=bool), x["regime_venda"].to_numpy(dtype=bool)
    linhas = []
    livre_a_partir = -1          # indice da barra em que a posicao anterior fechou
    for i in [int(k) for k in np.flatnonzero(sc | sv)]:
        compra = bool(sc[i])
        lado = "compra" if compra else "venda"
        base = {"dia": dias[i], "hhmm": int(hhmm[i]), "current_bar": int(cbar[i]), "lado": lado,
                "a_favor_mme80": bool(reg_c[i] if compra else reg_v[i]),
                "entrada": float(entr[i]), "alvo": float(alvos[i]), "stop": float(stops[i]),
                "D_pts": float(d_all[i])}
        if i + 1 <= livre_a_partir and dias[i] == dias[livre_a_partir]:
            linhas.append({**base, "classe": "ignorado_posicao", "resultado": float("nan"),
                           "barras": 0, "pnl_bruto_pts": float("nan"),
                           "pnl_zeragem_pts": float("nan"), "barra_resolucao_hhmm": None})
            continue
        j, classe, res = i + 1, "por_tempo", float("nan")
        while j < len(x) and dias[j] == dias[i]:
            t_alvo = highs[j] >= alvos[i] if compra else lows[j] <= alvos[i]
            t_stop = lows[j] <= stops[i] if compra else highs[j] >= stops[i]
            if (j == i + 1 and t_stop) or (t_alvo and t_stop):
                classe, res = "ambigua", 0.0
                break
            if t_alvo:
                classe, res = "resolvida", 1.0
                break
            if t_stop:
                classe, res = "resolvida", -1.0
                break
            j += 1
        fim = min(j, len(x) - 1)
        livre_a_partir = fim
        pnl_z = float("nan")
        if classe == "por_tempo":
            k = fim if dias[fim] == dias[i] else fim - 1
            pnl_z = (closes[k] - entr[i]) * (1.0 if compra else -1.0)
        linhas.append({**base, "classe": classe, "resultado": res, "barras": fim - i,
                       "pnl_bruto_pts": (res * d_all[i]) if classe == "resolvida" else float("nan"),
                       "pnl_zeragem_pts": pnl_z,
                       "barra_resolucao_hhmm": (int(hhmm[fim]) if classe != "por_tempo" else None)})
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------
# 3. p1, IC de Wilson, veredito
# ---------------------------------------------------------------------
def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """
    IC de Wilson. Conferido a mao (regra 4) com k=7, n=10:
        centro = (0,7 + z^2/20) / (1 + z^2/10) = 0,6445
        meia   = z x sqrt(0,021 + z^2/400) / (1 + z^2/10) = 0,2477
        -> (0,3968, 0,8922)
    """
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    meia = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (centro - meia, centro + meia)


def veredito(p1: float, ic_inferior: float | None = None) -> str:
    if math.isnan(p1):
        return "sem amostra"
    if p1 >= P1_FAVORAVEL and (ic_inferior is None or ic_inferior > P1_CONTRA):
        return "FAVORAVEL"
    if p1 <= P1_CONTRA:
        return "CONTRA"
    return "INCONCLUSIVO"


_COLUNAS = ["dia", "hhmm", "current_bar", "lado", "a_favor_mme80", "entrada", "alvo", "stop",
            "D_pts", "classe", "resultado", "barras", "pnl_bruto_pts", "barra_resolucao_hhmm"]


def _placar(r: pd.DataFrame, z: float = Z95) -> dict[str, Any]:
    if r.empty:
        r = pd.DataFrame(columns=_COLUNAS)
    res = r[r["classe"] == "resolvida"]
    n = len(res)
    k = int((res["resultado"] > 0).sum())
    p1 = (k / n) if n else float("nan")
    lo, hi = wilson(k, n, z)
    pnl = res["pnl_bruto_pts"]
    if n > 1:
        meia = z * float(pnl.std(ddof=1)) / math.sqrt(n)
        pnl_ic: list[float] | None = [round(float(pnl.mean()) - meia, 1),
                                      round(float(pnl.mean()) + meia, 1)]
    else:
        pnl_ic = None
    n_amb = int((r["classe"] == "ambigua").sum())
    return {
        "n_sinais": len(r), "n_resolvidas": n, "n_ambiguas": n_amb,
        "n_por_tempo": int((r["classe"] == "por_tempo").sum()),
        "n_ignorados_posicao": int((r["classe"] == "ignorado_posicao").sum()),
        "fracao_ambigua": (round(n_amb / len(r), 4) if len(r) else None),
        "p1": (round(p1, 4) if n else None),
        "ic95": ([round(lo, 4), round(hi, 4)] if n else None),   # nivel = ic_confianca
        "pnl_bruto_pts_medio": (round(float(pnl.mean()), 1) if n else None),
        "pnl_bruto_pts_ic95": pnl_ic,
        "pnl_liquido_pts_medio": (round(float(pnl.mean()) - ep.CUSTO_PONTOS, 1) if n else None),
        "pnl_zeragem_por_tempo_pts_medio": (
            round(float(r["pnl_zeragem_pts"].dropna().mean()), 1)
            if "pnl_zeragem_pts" in r and r["pnl_zeragem_pts"].notna().any() else None),
    }


def placar(r: pd.DataFrame, ficha: str = "ifr2") -> dict[str, Any]:
    """Primario = total. Estratos so' REPORTADOS (a favor/contra a MME80,
    compra/venda): nao tem veredito proprio, de proposito."""
    trial = int(FICHAS[ficha]["TRIAL"])
    z = z_ic(trial)
    if r.empty:
        r = pd.DataFrame(columns=_COLUNAS)
    total = _placar(r, z)
    total["veredito"] = veredito(total["p1"] if total["p1"] is not None else float("nan"),
                                 total["ic95"][0] if total["ic95"] else None)
    total["ic_confianca"] = round(1 - 0.05 / trial, 4)
    estratos = {
        "a_favor_mme80": _placar(r[r["a_favor_mme80"]], z),
        "contra_mme80": _placar(r[~r["a_favor_mme80"]], z),
        "compra": _placar(r[r["lado"] == "compra"], z),
        "venda": _placar(r[r["lado"] == "venda"], z),
    }
    # Tendencia das ambiguas: SO' a lista para conferir no tape. Sem
    # resultado aqui, porque o OHLC nao o tem.
    amb = r[r["classe"] == "ambigua"]
    return {"primario": total, "estratos_reportados": estratos,
            "ambiguas_para_conferir_no_tape": len(amb)}


def por_ano(r: pd.DataFrame, z: float) -> dict[str, Any]:
    """Estrato por ano: reportado, sem veredito. E' onde um ano atipico
    (2020) aparece sem que ninguem escolha tira-lo."""
    if r.empty:
        return {}
    anos = pd.to_datetime(r["dia"].astype(str)).dt.year
    return {str(a): _placar(r[anos == a], z) for a in sorted(anos.unique())}


def combinar(saida: Path, ficha: str) -> dict[str, Any]:
    """
    Le `sinais_<ficha>_<amostra>.csv` de todas as amostras combinaveis
    presentes em `saida` e devolve o placar do CONJUNTO, com o por-ano.
    Recusa se um arquivo tiver hash de ficha diferente (resultados com
    hash diferente nunca se somam) -- o hash vem do resultado_*.json ao
    lado do CSV.
    """
    partes, hashes, presentes = [], set(), []
    for amostra in AMOSTRAS_COMBINAVEIS:
        csv = saida / f"sinais_{ficha}_{amostra}.csv"
        js = saida / f"resultado_{ficha}_{amostra}.json"
        if not csv.exists():
            continue
        if js.exists():
            hashes.add(json.loads(js.read_text(encoding="utf-8"))["carimbo"]["hash_ficha"])
        df = pd.read_csv(csv)
        df["amostra"] = amostra
        partes.append(df)
        presentes.append(amostra)
    if not partes:
        raise SystemExit(f"nenhum sinais_{ficha}_<amostra>.csv em {saida}")
    if len(hashes) > 1:
        raise SystemExit(f"hashes de ficha diferentes em {saida}: {sorted(hashes)} -- "
                         "resultados de fichas diferentes nunca se somam.")
    r = pd.concat(partes, ignore_index=True)
    pl = placar(r, ficha)
    pl["por_ano_reportado"] = por_ano(r, z_ic(int(FICHAS[ficha]["TRIAL"])))
    pl["amostras"] = presentes
    pl["hash_ficha"] = next(iter(hashes)) if hashes else None
    (saida / f"resultado_{ficha}_COMBINADO.json").write_text(
        json.dumps(pl, indent=2, default=str), encoding="utf-8")
    return pl


# ---------------------------------------------------------------------
# 4. Orquestracao, com o lock de UMA rodada
# ---------------------------------------------------------------------
def rodar(dump: Path, saida: Path, amostra: str,
          forcar_motivo: str | None = None, ficha: str = "ifr2") -> dict[str, Any]:
    if ficha not in FICHAS:
        raise SystemExit(f"ficha '{ficha}' nao existe; use {sorted(FICHAS)}")
    df, meta = ep.carregar_log(dump)
    d = ep.indicadores(df)
    d = recortar_amostra(d, amostra)

    arquivo = saida / f"resultado_{ficha}_{amostra}.json"
    if amostra == "teste" and arquivo.exists():
        if not forcar_motivo:
            raise SystemExit(
                f"{arquivo} ja' existe: a rodada de TESTE e' UMA. Rodar de novo "
                "e' a segunda olhada que a ficha proibe.\n  Se ha' um motivo "
                "legitimo (bug no codigo que muda o que a ficha ja' dizia), passe "
                "--forcar \"motivo\" e ele fica gravado na saida.")
        log.warning("eas_preco_teste.forcado", motivo=forcar_motivo, arquivo=str(arquivo))

    r = {"ifr2": lambda: resolver_sinais(ep.marcar_ifr2(d)),
         "orb": lambda: resolver_orb(d),
         "123": lambda: resolver_123(d)}[ficha]()
    pl = placar(r, ficha)
    carimbo = {"codigo": _carimbo(), "hash_ficha": hash_ficha(ficha), "ficha": ficha,
               "parametros": parametros_da_ficha(ficha),
               "rodado_em": dt.datetime.now().isoformat(timespec="seconds"),
               "forcado_motivo": forcar_motivo}
    saida.mkdir(parents=True, exist_ok=True)
    r.to_csv(saida / f"sinais_{ficha}_{amostra}.csv", index=False)
    resumo = {"ficha": ficha, "amostra": amostra,
              "janela": [str(x) for x in AMOSTRAS[amostra]],
              "dump": meta, "carimbo": carimbo, **pl}
    arquivo.write_text(json.dumps(resumo, indent=2, default=str), encoding="utf-8")
    log.info("eas_preco_teste.rodada", ficha=ficha, amostra=amostra, pregoes=meta["pregoes"],
             n_resolvidas=pl["primario"]["n_resolvidas"], p1=pl["primario"]["p1"],
             veredito=pl["primario"]["veredito"], codigo=carimbo["codigo"],
             hash_ficha=carimbo["hash_ficha"])
    return {"meta": meta, "placar": pl, "carimbo": carimbo, "sinais": r, "arquivo": arquivo}
