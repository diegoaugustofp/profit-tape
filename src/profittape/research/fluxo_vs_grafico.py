"""
O GRAFICO SUBSTITUI O TAPE? (2026-09-16, exploracao declarada)

Pergunta, em duas metades com respostas provavelmente opostas:

  (a) NAO-DIRECIONAL. `absorcao = vol_agr / range_em_ticks` (flow.py) usa
      vol_agr = volume AGREDIDO (trade_type 2 e 3). O grafico so' da'
      `vol_total` (QuantityVol, tudo). Se a razao vol_agr/vol_total for
      estavel, `vol_total / range` e' um proxy da absorcao -- e a
      absorcao passaria a existir em DEZ ANOS de grafico, nao em dois
      meses de tape.
  (b) DIRECIONAL. `imbalance = (compra - venda) / vol_agr` nao esta' no
      grafico por construcao. O unico proxy possivel e' a geometria da
      barra (`desloc_norm = (close - open) / range`). Se a geometria
      explicar o imbalance, o tape e' dispensavel tambem aqui; se nao
      explicar -- e o RESIDUO e' exatamente onde a absorcao direcional
      vive -- fica PROVADO que o tape e' insubstituivel, o que tambem e'
      resposta (decisao de dezembro sobre estrutura: DLL x NTSL).

O QUE DECIDE NAO E' CORRELACAO. Feature vira LIMIAR (gate), nao
regressao: o que importa e' se o proxy escolhe as MESMAS BARRAS no decil
extremo. Por isso a medida principal e' a CONCORDANCIA NO DECIL (quantas
das 10% maiores pelo tape estao entre as 10% maiores pelo proxy; acaso =
10%), com Spearman como apoio.

CATEGORIA `features`: relacao entre variaveis, nenhum retorno olhado,
nenhum trial consumido. Barras M15 (as do EA de preco), so' as
`volume_confiavel` -- barra com buraco de feed subconta volume e
contaminaria a razao.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog

from ..ea.barra_tempo import ConstrutorDeBarraDeTempo
from ..features.pipeline import _carregar_dia

log = structlog.get_logger(__name__)
_NS = 1_000_000_000


def barras_do_tape(curated: Path, symbol: str, dia: dt.date,
                   periodo_s: int = 900, tick: float = 5.0) -> pd.DataFrame:
    pasta = curated / "trade" / f"dt={dia.isoformat()}"
    if not (pasta / f"sym={symbol}").exists():
        return pd.DataFrame()
    t = _carregar_dia(pasta, symbol)
    if t.empty:
        return pd.DataFrame()
    c = ConstrutorDeBarraDeTempo(periodo_s)
    linhas = []

    def _add(b: Any) -> None:
        rng_ticks = max((b.high - b.low) / tick, 1.0)
        vol_agr = b.vol_agr_compra + b.vol_agr_venda
        linhas.append({
            "dia": dia, "ts_open_ns": b.ts_open_ns, "confiavel": b.volume_confiavel,
            "open": b.open, "high": b.high, "low": b.low, "close": b.close,
            "vol_total": b.vol_total, "vol_agr": vol_agr,
            "vol_agr_compra": b.vol_agr_compra, "vol_agr_venda": b.vol_agr_venda,
            "n_trades": b.n_trades, "range_ticks": rng_ticks,
            # tape (a verdade)
            "absorcao_tape": vol_agr / rng_ticks,
            "imbalance_tape": ((b.vol_agr_compra - b.vol_agr_venda) / vol_agr) if vol_agr else 0.0,
            # grafico (o proxy)
            "absorcao_proxy": b.vol_total / rng_ticks,
            "desloc_norm": ((b.close - b.open) / (b.high - b.low)) if b.high > b.low else 0.0,
            "razao_agr": (vol_agr / b.vol_total) if b.vol_total else float("nan"),
        })

    for ts_ns, price, qtd, tipo in t[["ts_ns", "price", "quantidade", "trade_type"]].itertuples(
            index=False):
        b = c.processar_trade(int(ts_ns), float(price), int(qtd), int(tipo))
        if b is not None:
            _add(b)
    fim = c.avancar_relogio(int(t["ts_ns"].to_numpy()[-1]) + periodo_s * _NS)
    if fim is not None:
        _add(fim)
    return pd.DataFrame(linhas)


def _concordancia_decil(verdade: pd.Series, proxy: pd.Series, q: float = 0.9) -> dict[str, Any]:
    """Das barras no decil SUPERIOR pela verdade, quantas estao no decil
    superior pelo proxy. Acaso = 10%. E' a medida que importa, porque
    feature vira limiar."""
    n = len(verdade)
    if n < 50:
        return {"n": n, "insuficiente": True}
    top_v = verdade >= verdade.quantile(q)
    top_p = proxy >= proxy.quantile(q)
    acerto = int((top_v & top_p).sum())
    return {"n": n, "no_decil_pela_verdade": int(top_v.sum()),
            "tambem_no_decil_pelo_proxy": acerto,
            "taxa": round(acerto / max(int(top_v.sum()), 1), 3), "acaso": round(1 - q, 3)}


def medir(curated: Path, symbol: str, dias: list[dt.date], periodo_s: int = 900,
          tick: float = 5.0) -> dict[str, Any]:
    partes = [barras_do_tape(curated, symbol, d, periodo_s, tick) for d in dias]
    partes = [p for p in partes if not p.empty]
    if not partes:
        raise SystemExit(f"nenhum dia com tape em {curated} para {symbol}")
    df = pd.concat(partes, ignore_index=True)
    total = len(df)
    df = df[df["confiavel"] & (df["vol_total"] > 0) & (df["vol_agr"] > 0)]

    def q(s: pd.Series) -> dict[str, float]:
        return {"p10": round(float(s.quantile(0.1)), 4), "p50": round(float(s.median()), 4),
                "p90": round(float(s.quantile(0.9)), 4)}

    razao = df["razao_agr"]
    razao_resumo = ({**q(razao), "media": round(float(razao.mean()), 4),
                     "desvio": round(float(razao.std()), 4),
                     "cv": round(float(razao.std() / razao.mean()), 4)} if len(df) else {})
    # (a) nao-direcional
    sp_abs = float(df["absorcao_tape"].corr(df["absorcao_proxy"], method="spearman"))
    conc_abs = _concordancia_decil(df["absorcao_tape"], df["absorcao_proxy"])
    # (b) direcional: a geometria explica o imbalance?
    sp_imb = float(df["imbalance_tape"].corr(df["desloc_norm"], method="spearman"))
    mesmo_sinal = float((np.sign(df["imbalance_tape"]) == np.sign(df["desloc_norm"])).mean())
    # residuo: imbalance que a geometria NAO explica (regressao linear simples)
    x, y = df["desloc_norm"].to_numpy(), df["imbalance_tape"].to_numpy()
    a, b = np.polyfit(x, y, 1) if len(x) > 2 else (0.0, 0.0)
    resid = y - (a * x + b)
    r2 = float(1 - resid.var() / y.var()) if y.var() > 0 else float("nan")
    conc_imb = _concordancia_decil(df["imbalance_tape"].abs(), df["desloc_norm"].abs())
    saida = {
        "barras": int(total), "barras_usadas": len(df),
        "dias": [d.isoformat() for d in dias if any(p["dia"].iloc[0] == d for p in partes)],
        "razao_vol_agr_sobre_vol_total": razao_resumo,
        "nao_direcional_absorcao": {
            "spearman_proxy_x_tape": round(sp_abs, 4),
            "concordancia_decil": conc_abs,
        },
        "direcional_imbalance": {
            "spearman_desloc_x_imbalance": round(sp_imb, 4),
            "fracao_mesmo_sinal": round(mesmo_sinal, 4),
            "r2_da_geometria": round(r2, 4),
            "residuo_desvio": round(float(resid.std()), 4),
            "imbalance_desvio": round(float(y.std()), 4),
            "concordancia_decil_em_modulo": conc_imb,
        },
    }
    log.info("fluxo_vs_grafico.medido", barras=len(df),
             razao_cv=razao_resumo.get("cv"),
             absorcao_decil=conc_abs.get("taxa"), imbalance_r2=round(r2, 3))
    return saida


def rodar(curated: Path, symbol: str, dias: list[dt.date], saida: Path,
          periodo_s: int = 900, tick: float = 5.0) -> dict[str, Any]:
    r = medir(curated, symbol, dias, periodo_s, tick)
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "fluxo_vs_grafico.json").write_text(json.dumps(r, indent=2, default=str),
                                                 encoding="utf-8")
    return r
