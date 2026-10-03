"""Metricas puras sobre a serie de operacoes de UM EA (pontos; R$ so' na conversao)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def ordenar(ops: pd.DataFrame) -> pd.DataFrame:
    out: pd.DataFrame = ops.sort_values(["dia", "hora_saida"]).reset_index(drop=True)
    return out


def drawdown(pnl: list[float] | np.ndarray) -> dict[str, Any]:
    """Drawdown maximo pico-a-vale da curva ACUMULADA de operacoes FECHADAS, com ponto inicial
    zero (posicao k = depois de k operacoes). So' fechadas: o que a operacao sofreu ENTRE a
    entrada e a saida (MAE) nao entra -- o drawdown real e' >= este.
    `recuperado` = a curva voltou ao pico depois do vale."""
    p = np.asarray(pnl, dtype=float)
    cheio = np.concatenate([[0.0], np.cumsum(p)])
    pico = np.maximum.accumulate(cheio)
    dd = pico - cheio
    k_vale = int(dd.argmax())
    out: dict[str, Any] = {"n": int(p.size), "max_pts": float(dd[k_vale]), "k_vale": k_vale,
                           "k_pico": int(cheio[:k_vale + 1].argmax()), "k_rec": None,
                           "atual_pts": float(dd[-1]), "final_pts": float(cheio[-1]),
                           "pico_pts": float(pico[-1])}
    if out["max_pts"] == 0.0:
        out.update(k_pico=0, k_vale=0, recuperado=True)
        return out
    voltou = np.nonzero(cheio[k_vale + 1:] >= cheio[out["k_pico"]])[0]
    out["recuperado"] = bool(voltou.size)
    if voltou.size:
        out["k_rec"] = k_vale + 1 + int(voltou[0])
    out["ops_pico_ao_vale"] = k_vale - out["k_pico"]
    return out


def resumo(ops: pd.DataFrame) -> dict[str, Any]:
    """Ganhos, perdas, payoff, fator de lucro, expectativa. `ops` ja' filtrado para o EA."""
    p = ops["pnl_liquido"].astype(float)
    g, per = p[p > 0], p[p < 0]
    perda_media = float(per.mean()) if len(per) else None
    out: dict[str, Any] = {
        "n": len(p), "ganhos": len(g), "perdas": len(per),
        "pct_ganho": 100.0 * len(g) / len(p) if len(p) else None,
        "pnl_pts": float(p.sum()), "media_pts": float(p.mean()) if len(p) else None,
        "melhor_pts": float(p.max()) if len(p) else None,
        "pior_pts": float(p.min()) if len(p) else None,
        "ganho_medio_pts": float(g.mean()) if len(g) else None, "perda_media_pts": perda_media,
        "payoff": (float(g.mean()) / abs(perda_media)
                   if len(g) and perda_media else None),
        "fator_de_lucro": (float(g.sum()) / abs(float(per.sum())) if len(per) else None)}
    return out


def por_dia(ops: pd.DataFrame) -> pd.DataFrame:
    g = ops.groupby("dia")["pnl_liquido"].agg(["size", "sum"])
    g.columns = ["ops", "pnl_pts"]
    out: pd.DataFrame = g.reset_index().sort_values("dia")
    return out


def capital(*, mdd_pts: float, pior_perda_pts: float, pior_stop_pts: float | None,
            valor_ponto: float, contratos: int, risco_max_pct: float,
            margem_por_contrato: float | None, recomendado_projeto: float | None,
            capital_inicial: float) -> dict[str, Any]:
    """Tres leituras de capital, todas DECLARADAS (nao ha' formula unica):
      regra_dos_2pct : capital em que o PIOR STOP PROGRAMADO cabe em `risco_max_pct`
                       (e' a regra do supervisor do projeto: stop x ponto / risco_max_pct);
      sobreviver     : margem + drawdown observado + 1 pior perda (piso: o observado e' amostra);
      com_folga      : margem + 2 x drawdown observado + 1 pior perda."""
    def brl(pts: float) -> float:
        return pts * valor_ponto * contratos
    pior = max(pior_perda_pts, pior_stop_pts or 0.0)
    margem = (margem_por_contrato or 0.0) * contratos
    out: dict[str, Any] = {
        "mdd_brl": brl(mdd_pts), "pior_perda_brl": brl(pior_perda_pts),
        "pior_stop_brl": None if pior_stop_pts is None else brl(pior_stop_pts),
        "regra_2pct": (brl(pior_stop_pts) / risco_max_pct if pior_stop_pts else None),
        "sobreviver": margem + brl(mdd_pts) + brl(pior),
        "com_folga": margem + 2 * brl(mdd_pts) + brl(pior),
        "margem_informada": margem_por_contrato is not None,
        "recomendado_projeto": recomendado_projeto, "capital_inicial": capital_inicial}
    base = out["regra_2pct"]
    out["projeto_subestima"] = bool(
        recomendado_projeto and base and recomendado_projeto < 0.9 * base)
    return out


def curva_de_capital(pnl: list[float] | np.ndarray, capital_inicial: float, valor_ponto: float,
                     contratos: int) -> np.ndarray:
    """Capital apos cada operacao (comeca em `capital_inicial`)."""
    return capital_inicial + np.concatenate([[0.0], np.cumsum(np.asarray(pnl, float))]) \
        * valor_ponto * contratos
