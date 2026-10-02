"""Metas de avaliacao por EA no indice do diario (v4.15): quantas operacoes a ficha
pede para a proxima avaliacao, quantas ja' houve e quantas faltam.

Os numeros vem de `docs/eas/metas.yaml` (cada um com o trecho literal da ficha, guardado
por teste). O diario so' CONTA: se a ficha proibe olhar resultado antes da meta
(`veredito_parcial: false`) o indice mostra a contagem e nao compoe nenhum veredito."""

from __future__ import annotations

import datetime as dt
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


def carregar_metas(caminho: Path) -> list[dict[str, Any]]:
    if not caminho.exists():
        return []
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    return list(dados.get("eas") or [])


def status_da_ficha(raiz_fichas: Path, ficha: str, max_chars: int = 260) -> str:
    """Primeira linha `> **Status:** ...` da ficha, sem markdown, truncada."""
    f = raiz_fichas / ficha
    if not f.exists():
        return f"ficha {ficha} nao encontrada"
    for linha in f.read_text(encoding="utf-8").splitlines():
        if linha.startswith("> **Status"):
            t = re.sub(r"[*`]", "", linha.lstrip("> ").strip())      # nao tocar em "_" (nomes)
            t = re.sub(r"^Status:\s*", "", t)
            return t if len(t) <= max_chars else t[:max_chars].rsplit(" ", 1)[0] + "…"
    return "sem linha de status"


def _dias_uteis_apos(d: dt.date, n: int) -> dt.date:
    while n > 0:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def _drawdown(pnl: pd.Series) -> float:
    acum = pnl.cumsum()
    pico = acum.cummax().clip(lower=0)
    return float((pico - acum).max()) if len(acum) else 0.0


def contar(ent: dict[str, Any], ops: pd.DataFrame) -> pd.DataFrame:
    """Operacoes que contam para a meta daquele EA (desde o inicio do forward)."""
    x = ops[(ops["ea"] == ent["ea"]) & (~ops["descartado"].fillna(False).astype(bool))].copy()
    if ent.get("desde"):
        x = x[x["dia"].astype(str) >= str(ent["desde"])]
    c = ent.get("contar") or {}
    if c.get("motivos"):
        x = x[x["motivo"].isin(c["motivos"])]
    if c.get("com_slippage"):
        x = x[x["slippage_ordens_pts"].notna()]
    ordenado: pd.DataFrame = x.sort_values(["dia", "hora_saida"])
    return ordenado


def progresso(ent: dict[str, Any], ops: pd.DataFrame, dias: pd.DataFrame) -> dict[str, Any]:
    """Estado da meta: contado, proximo marco, faltam, ritmo observado x da ficha, previsao."""
    x = contar(ent, ops)
    n = len(x)
    out: dict[str, Any] = {"ea": ent["ea"], "n": n, "metas": ent.get("metas") or []}
    desde = str(ent.get("desde") or "")
    d = dias[dias["dia"].astype(str) >= desde] if desde else dias
    pregoes = len(d)
    ultimo = dt.date.fromisoformat(str(d["dia"].max())) if pregoes else None
    out["pregoes"] = pregoes
    out["ritmo_obs"] = (n / pregoes) if pregoes else None
    out["ritmo_ficha"] = ent.get("ritmo_ficha")
    proximo = next((m for m in out["metas"] if m["n"] > n), None)
    out["proximo"] = proximo
    out["faltam"] = (proximo["n"] - n) if proximo else None
    out["atingidas"] = [m for m in out["metas"] if m["n"] <= n]
    if proximo and out["ritmo_obs"] and ultimo:
        falta_pregoes = math.ceil(out["faltam"] / out["ritmo_obs"])
        out["previsao"] = _dias_uteis_apos(ultimo, falta_pregoes)
        out["faltam_pregoes"] = falta_pregoes
    else:
        out["previsao"] = None
    if ent.get("prazo_ate"):
        prazo = dt.date.fromisoformat(str(ent["prazo_ate"]))
        out["prazo"] = prazo
    mostrar = ent.get("mostrar") or []
    if "slippage_medio" in mostrar and n:
        out["slippage_medio"] = float(x["slippage_ordens_pts"].mean())
    if "dd_media" in mostrar and n:
        pnl = x["pnl_liquido"].fillna(0.0)
        out["media"] = float(pnl.mean())
        out["drawdown"] = _drawdown(pnl)
        out["morte"] = ent.get("morte")
    if n:
        out["primeiro_dia"] = str(x["dia"].min())
    return out
