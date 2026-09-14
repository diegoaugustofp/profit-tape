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
}

# CRITERIO da ficha (ponto estimado; IC sempre reportado).
P1_FAVORAVEL = 0.56
P1_CONTRA = 0.50
# TRIAL: quantas vezes a amostra 2023-2025 foi usada por esta familia.
# Trial 1 = K 0,5 (CONTRA, 2026-09-14). Trial 2 = K 1,0. O IC e' de
# (1 - 0,05/TRIAL): Bonferroni sobre os trials da familia -- o preco
# honesto de usar a mesma amostra duas vezes. FAVORAVEL exige, alem de
# p1 >= 0,56, que o limite inferior do IC fique acima de 0,50.
TRIAL = 2
Z95 = 1.959963984540054
Z_IC = 2.2414027276049473 if TRIAL == 2 else Z95   # 97,5% bicaudal

PARAMETROS_FICHA: dict[str, Any] = {
    "RSI_PERIODO": ep.RSI_PERIODO,
    "RSI_SOBREVENDIDO": ep.RSI_SOBREVENDIDO,
    "RSI_SOBRECOMPRADO": ep.RSI_SOBRECOMPRADO,
    "MME_LONGA": ep.MME_LONGA,
    "ATR_PERIODO": ep.ATR_PERIODO,
    "K_ATR": ep.K_ATR,
    "REGIME_NA_CLAUSULA": ep.REGIME_NA_CLAUSULA,
    "HORA_PRIMEIRO_FECHAMENTO": ep.HORA_PRIMEIRO_FECHAMENTO,
    "HORA_ULTIMO_FECHAMENTO": ep.HORA_ULTIMO_FECHAMENTO,
    "TICK_WIN": ep.TICK_WIN,
    "CUSTO_PONTOS": ep.CUSTO_PONTOS,
    "P1_FAVORAVEL": P1_FAVORAVEL,
    "P1_CONTRA": P1_CONTRA,
    "TRIAL": TRIAL,
}


def hash_ficha() -> str:
    return hashlib.sha256(json.dumps(PARAMETROS_FICHA, sort_keys=True).encode()).hexdigest()[:12]


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


def _placar(r: pd.DataFrame) -> dict[str, Any]:
    res = r[r["classe"] == "resolvida"]
    n = len(res)
    k = int((res["resultado"] > 0).sum())
    p1 = (k / n) if n else float("nan")
    lo, hi = wilson(k, n, Z_IC)
    pnl = res["pnl_bruto_pts"]
    if n > 1:
        meia = Z_IC * float(pnl.std(ddof=1)) / math.sqrt(n)
        pnl_ic: list[float] | None = [round(float(pnl.mean()) - meia, 1),
                                      round(float(pnl.mean()) + meia, 1)]
    else:
        pnl_ic = None
    n_amb = int((r["classe"] == "ambigua").sum())
    return {
        "n_sinais": len(r), "n_resolvidas": n, "n_ambiguas": n_amb,
        "n_por_tempo": int((r["classe"] == "por_tempo").sum()),
        "fracao_ambigua": (round(n_amb / len(r), 4) if len(r) else None),
        "p1": (round(p1, 4) if n else None),
        "ic95": ([round(lo, 4), round(hi, 4)] if n else None),   # nivel = ic_confianca
        "pnl_bruto_pts_medio": (round(float(pnl.mean()), 1) if n else None),
        "pnl_bruto_pts_ic95": pnl_ic,
        "pnl_liquido_pts_medio": (round(float(pnl.mean()) - ep.CUSTO_PONTOS, 1) if n else None),
    }


def placar(r: pd.DataFrame) -> dict[str, Any]:
    """Primario = total. Estratos so' REPORTADOS (a favor/contra a MME80,
    compra/venda): nao tem veredito proprio, de proposito."""
    total = _placar(r)
    total["veredito"] = veredito(total["p1"] if total["p1"] is not None else float("nan"),
                                 total["ic95"][0] if total["ic95"] else None)
    total["ic_confianca"] = round(1 - 0.05 / TRIAL, 4)
    estratos = {
        "a_favor_mme80": _placar(r[r["a_favor_mme80"]]),
        "contra_mme80": _placar(r[~r["a_favor_mme80"]]),
        "compra": _placar(r[r["lado"] == "compra"]),
        "venda": _placar(r[r["lado"] == "venda"]),
    }
    # Tendencia das ambiguas: SO' a lista para conferir no tape. Sem
    # resultado aqui, porque o OHLC nao o tem.
    amb = r[r["classe"] == "ambigua"]
    return {"primario": total, "estratos_reportados": estratos,
            "ambiguas_para_conferir_no_tape": len(amb)}


# ---------------------------------------------------------------------
# 4. Orquestracao, com o lock de UMA rodada
# ---------------------------------------------------------------------
def rodar(dump: Path, saida: Path, amostra: str,
          forcar_motivo: str | None = None) -> dict[str, Any]:
    df, meta = ep.carregar_log(dump)
    x = ep.marcar_ifr2(ep.indicadores(df))
    x = recortar_amostra(x, amostra)

    arquivo = saida / f"resultado_{amostra}.json"
    if amostra == "teste" and arquivo.exists():
        if not forcar_motivo:
            raise SystemExit(
                f"{arquivo} ja' existe: a rodada de TESTE e' UMA. Rodar de novo "
                "e' a segunda olhada que a ficha proibe.\n  Se ha' um motivo "
                "legitimo (bug no codigo que muda o que a ficha ja' dizia), passe "
                "--forcar \"motivo\" e ele fica gravado na saida.")
        log.warning("eas_preco_teste.forcado", motivo=forcar_motivo, arquivo=str(arquivo))

    r = resolver_sinais(x)
    pl = placar(r)
    carimbo = {"codigo": _carimbo(), "hash_ficha": hash_ficha(),
               "parametros": PARAMETROS_FICHA,
               "rodado_em": dt.datetime.now().isoformat(timespec="seconds"),
               "forcado_motivo": forcar_motivo}
    saida.mkdir(parents=True, exist_ok=True)
    r.to_csv(saida / f"sinais_{amostra}.csv", index=False)
    resumo = {"amostra": amostra, "janela": [str(d) for d in AMOSTRAS[amostra]],
              "dump": meta, "carimbo": carimbo, **pl}
    arquivo.write_text(json.dumps(resumo, indent=2, default=str), encoding="utf-8")
    log.info("eas_preco_teste.rodada", amostra=amostra, pregoes=meta["pregoes"],
             n_resolvidas=pl["primario"]["n_resolvidas"], p1=pl["primario"]["p1"],
             veredito=pl["primario"]["veredito"], codigo=carimbo["codigo"],
             hash_ficha=carimbo["hash_ficha"])
    return {"meta": meta, "placar": pl, "carimbo": carimbo, "sinais": r, "arquivo": arquivo}
