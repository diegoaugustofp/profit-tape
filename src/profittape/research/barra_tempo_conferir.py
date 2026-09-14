"""
Conferencia no dado REAL: barras M15 construidas pelo EA (trade a trade,
`ConstrutorDeBarraDeTempo`) contra as barras do GRAFICO do Profit (dump do
`preco_m15.ntsl`) para os mesmos dias.

E' o item 2 do checklist do forward ("recalcular e comparar MEDE; copiar o
logado so' CONFIA"): se o EA fecha barras diferentes do grafico, o 123
ao vivo vai discordar da ficha que foi validada em 10 anos de grafico --
e ninguem veria.

O que compara, barra a barra, por dia: open/high/low/close (pontos),
n de barras e a hora de abertura. Diferenca esperada: ZERO em OHLC. O
`n_trades` nao existe no dump; `vol_total` do dump e' o volume TOTAL
(QuantityVol), nao o agredido -- reportado so' como informacao.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from ..ea.barra_tempo import ConstrutorDeBarraDeTempo
from ..features.pipeline import _carregar_dia
from .eas_preco import carregar_log

log = structlog.get_logger(__name__)

_NS = 1_000_000_000


def barras_do_tape(curated: Path, symbol: str, dia: str, periodo_s: int = 900) -> pd.DataFrame:
    pasta = curated / "trade" / f"dt={dia}"
    if not (pasta / f"sym={symbol}").exists():
        raise SystemExit(f"sem tape para {symbol} em {dia}: {pasta}")
    t = _carregar_dia(pasta, symbol)
    c = ConstrutorDeBarraDeTempo(periodo_s)
    linhas: list[dict[str, Any]] = []
    cols = t[["ts_ns", "price", "quantidade", "trade_type"]].itertuples(index=False)
    for ts_ns, price, qtd, tipo in cols:
        b = c.processar_trade(int(ts_ns), float(price), int(qtd), int(tipo))
        if b is not None:
            linhas.append(b.__dict__ | {})
    fim = c.avancar_relogio(int(t["ts_ns"].to_numpy()[-1]) + periodo_s * _NS)
    if fim is not None:
        linhas.append(fim.__dict__ | {})
    df = pd.DataFrame(linhas)
    ts = pd.to_datetime(df["ts_open_ns"], unit="ns", utc=True).dt.tz_convert("America/Sao_Paulo")
    df["hhmm"] = (ts.dt.hour * 100 + ts.dt.minute).astype(int)
    df["dia"] = ts.dt.date
    return df


def conferir(curated: Path, dump: Path, symbol: str, dias: list[str],
             periodo_s: int = 900) -> dict[str, Any]:
    grafico, _ = carregar_log(dump)
    resultado: dict[str, Any] = {"dias": {}}
    for dia in dias:
        ea = barras_do_tape(curated, symbol, dia, periodo_s)
        g = grafico[grafico["dia"].astype(str) == dia]
        if g.empty:
            resultado["dias"][dia] = {"erro": "dia nao esta' no dump"}
            continue
        m = ea.merge(g[["hhmm", "open", "high", "low", "close", "vol_total"]],
                     on="hhmm", how="outer", suffixes=("_ea", "_grafico"), indicator=True)
        so_ea = m[m["_merge"] == "left_only"]["hhmm"].tolist()
        so_grafico = m[m["_merge"] == "right_only"]["hhmm"].tolist()
        ambos = m[m["_merge"] == "both"]
        campos = ("open", "high", "low", "close")
        difs = {c: (ambos[f"{c}_ea"] - ambos[f"{c}_grafico"]).abs() for c in campos}
        piores: dict[str, tuple[float, int | None]] = {}
        for c, d in difs.items():
            if len(d):
                i_max = int(d.to_numpy().argmax())
                piores[c] = (round(float(d.max()), 1), int(ambos["hhmm"].iloc[i_max]))
            else:
                piores[c] = (0.0, None)
        n_iguais = int(sum(all(difs[c].iloc[i] == 0 for c in difs) for i in range(len(ambos))))
        resultado["dias"][dia] = {
            "barras_ea": len(ea), "barras_grafico": len(g),
            "em_comum": len(ambos), "identicas_ohlc": n_iguais,
            "so_no_ea": so_ea, "so_no_grafico": so_grafico,
            "dif_max_por_campo": piores,
            "barras_diferentes": [
                {"hhmm": int(r["hhmm"]),
                 **{c: (float(r[f"{c}_ea"]), float(r[f"{c}_grafico"])) for c in difs
                    if r[f"{c}_ea"] != r[f"{c}_grafico"]}}
                for _, r in ambos.iterrows()
                if any(r[f"{c}_ea"] != r[f"{c}_grafico"] for c in difs)
            ][:20],
        }
        resumo = {k: v for k, v in resultado["dias"][dia].items() if k != "barras_diferentes"}
        log.info("barra_tempo.conferido", dia=dia, **resumo)
    return resultado
