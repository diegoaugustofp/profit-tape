"""
OPCAO SOBRE ACAO — passo 1: o hedge deixa marca no PAPEL? (2026-09-22)

CONTRAPARTE: quem vendeu opcao e esta' com delta e' OBRIGADO a hedgear, e
o hedge fica mais violento quanto mais perto do strike no vencimento --
compra quando o papel sobe, vende quando cai. Fluxo que nao escolhe preco,
concentrado em DATA e em NIVEL DE PRECO.

ESTE MODULO NAO E' UMA FICHA. Categoria `features`, zero trial, SEM
DIRECAO (nao olha retorno com sinal).

AS DUAS PERGUNTAS, e por que a segunda e' a que importa
-------------------------------------------------------
1. A semana do vencimento e' diferente das outras em MAGNITUDE (volume,
   amplitude, |retorno| do papel)? Sozinha, isso e' so' sazonalidade.
2. O volume do papel se CONCENTRA perto dos strikes com OI relevante? E'
   o que separa "semana agitada" de "o preco e' atraido pelos strikes" --
   a unica das duas com mecanismo.

O PLACEBO (o que decide a pergunta 2): a mesma conta com strikes FALSOS,
deslocados de `placebo_desloc` (default 1,7% -- meio intervalo tipico
entre strikes de PETR4). Se a concentracao nos strikes de verdade for
igual a` dos falsos, e' so' onde o preco andou -- nao ha' atracao.

LIMITE DECLARADO: o OI vem do Trade Hunter e e' de FECHAMENTO (EOD), nao
intradiario; e e' posicao em aberto, nao fluxo. Os strikes entram como
parametro -- este modulo nao busca dado externo.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog

from ..features.pipeline import _carregar_dia

log = structlog.get_logger(__name__)
_NS = 1_000_000_000
TOL_PCT = 0.004          # "perto do strike" = +-0,4% (PETR4 ~ +-0,19 em 48,50)
PLACEBO_DESLOC_PCT = 0.017


def carregar_papel(curated: Path, papel: str, dia: dt.date) -> pd.DataFrame:
    pasta = curated / "trade" / f"dt={dia.isoformat()}"
    if not (pasta / f"sym={papel}").exists():
        return pd.DataFrame()
    t = _carregar_dia(pasta, papel)
    return t.sort_values("ts_ns") if not t.empty else pd.DataFrame()


def concentracao(precos: np.ndarray, qtds: np.ndarray, strikes: list[float],
                 tol_pct: float = TOL_PCT) -> dict[str, Any]:
    """Fracao do volume negociada a menos de `tol_pct` de ALGUM strike."""
    if not len(precos) or not strikes:
        return {}
    perto = np.zeros(len(precos), dtype=bool)
    for s in strikes:
        perto |= np.abs(precos - s) <= s * tol_pct
    total = float(qtds.sum())
    return {"fracao_do_volume_perto": round(float(qtds[perto].sum() / total), 4) if total else None,
            "negocios_perto": int(perto.sum()),
            "faixa_coberta_pct": round(100 * len(strikes) * 2 * tol_pct, 2)}


def medir_dia(curated: Path, papel: str, dia: dt.date, strikes: list[float],
              vencimento: dt.date, series: list[str] | None = None,
              tol_pct: float = TOL_PCT,
              placebo_desloc: float = PLACEBO_DESLOC_PCT) -> dict[str, Any]:
    t = carregar_papel(curated, papel, dia)
    if t.empty:
        return {}
    p = t["price"].to_numpy(dtype=float)
    q = t["quantidade"].to_numpy(dtype=float)
    falsos = [s * (1 + placebo_desloc) for s in strikes]
    r: dict[str, Any] = {
        "dia": dia.isoformat(),
        "pregoes_ate_o_vencimento": int(np.busday_count(dia, vencimento)),
        "negocios": len(t), "volume": int(q.sum()),
        "amplitude_pct": round(float((p.max() - p.min()) / p[0] * 100), 3),
        "retorno_abs_pct": round(float(abs(p[-1] - p[0]) / p[0] * 100), 3),
        "strikes": concentracao(p, q, strikes, tol_pct),
        "strikes_PLACEBO": concentracao(p, q, falsos, tol_pct),
    }
    a, b = (r["strikes"].get("fracao_do_volume_perto"),
            r["strikes_PLACEBO"].get("fracao_do_volume_perto"))
    r["razao_strike_vs_placebo"] = (round((a + 1e-9) / (b + 1e-9), 3)
                                    if a is not None and b is not None else None)
    if series:
        ativ = {}
        for s in series:
            ts = carregar_papel(curated, s, dia)
            if not ts.empty:
                ativ[s] = {"negocios": len(ts),
                           "volume": int(ts["quantidade"].sum())}
        r["series"] = ativ
        r["negocios_nas_series"] = int(sum(x["negocios"] for x in ativ.values()))
    log.info("opcoes_vencimento.dia", dia=r["dia"],
             pregoes_ate_o_vencimento=r["pregoes_ate_o_vencimento"],
             volume=r["volume"], razao=r["razao_strike_vs_placebo"],
             negocios_nas_series=r.get("negocios_nas_series"))
    return r


def descrever(curated: Path, papel: str, dias: list[dt.date], strikes: list[float],
              vencimento: dt.date, series: list[str] | None = None,
              tol_pct: float = TOL_PCT, placebo_desloc: float = PLACEBO_DESLOC_PCT,
              saida: Path | None = None) -> dict[str, Any]:
    linhas = [x for d in dias
              if (x := medir_dia(curated, papel, d, strikes, vencimento, series,
                                 tol_pct, placebo_desloc))]
    if not linhas:
        raise SystemExit(f"nenhum dia com tape de {papel} em {curated}")
    df = pd.DataFrame([{k: v for k, v in x.items() if not isinstance(v, dict)} for x in linhas])
    semana = df[df["pregoes_ate_o_vencimento"] <= 5]
    resto = df[df["pregoes_ate_o_vencimento"] > 5]

    def resumo(d: pd.DataFrame) -> dict[str, Any]:
        if d.empty:
            return {}
        return {"pregoes": len(d),
                "volume_p50": float(d["volume"].median()),
                "amplitude_pct_p50": float(d["amplitude_pct"].median()),
                "retorno_abs_pct_p50": float(d["retorno_abs_pct"].median()),
                "razao_strike_vs_placebo_p50": (float(d["razao_strike_vs_placebo"].median())
                                                if d["razao_strike_vs_placebo"].notna().any()
                                                else None)}

    r = {"papel": papel, "vencimento": vencimento.isoformat(), "strikes": strikes,
         "tol_pct": tol_pct, "placebo_desloc": placebo_desloc,
         "semana_do_vencimento": resumo(semana), "demais_pregoes": resumo(resto),
         "por_dia": linhas}
    if saida is not None:
        saida.mkdir(parents=True, exist_ok=True)
        (saida / "opcoes_vencimento.json").write_text(json.dumps(r, indent=2, default=str),
                                                      encoding="utf-8")
    return r
