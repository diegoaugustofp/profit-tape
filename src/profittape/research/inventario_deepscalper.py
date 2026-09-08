"""
Inventario da Fase 0 do pre-registro DeepScalper (docs/RESEARCH_PLANO.md,
2026-09-07). Quatro contagens em dado QUEIMADO. Categoria `features`:
zero trial, nada aqui olha resultado.

O QUE MEDE, POR PREGAO
----------------------
1. `barras`            : barras de volume COMPLETAS com `volume_barra`
                         (mesma convencao de features/bars.py: RLP e leilao
                         nao avancam o relogio; a parcial do fim e'
                         descartada). E' a TAXA da ficha forward: uma
                         decisao por barra.
2. `barras_por_hora`   : barras / horas entre o primeiro e o ultimo
                         negocio de agressao. `h_120min` = quantas barras
                         cobrem 120 min = round(2 * barras_por_hora). O `h`
                         do hindsight bonus e' a MEDIANA disso entre
                         pregoes -- medido, nao chutado.
3. `spread_*`          : spread do melhor bid/ask em TICKS, a partir do
                         stream `tiny_book` (raw, nao curado). Cada update
                         de tiny_book e' uma observacao (ponderacao por
                         evento, nao por tempo -- declarado). Spread <= 0
                         (travado/cruzado ou lado vazio) conta como
                         invalido e sai da mediana. Tick inferido do
                         proprio dia (menor variacao positiva na agressao).
4. `book_integro`      : dia >= `data_book_confiavel` (v0.55, correcao do
                         bug de ts_ns=0 em docs/INTEGRIDADE_DOS_DADOS.md)
                         E book_offer presente E book_price presente. Antes
                         dessa data o book_offer e' NAO-CONFIAVEL por
                         construcao, mesmo que exista.

O agregado entre pregoes e' a MEDIANA. O resumo diz quantos pregoes
faltam para o portao de 160 da Fase 3.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import structlog

from ..features.pipeline import _carregar_dia, _dias_do_symbol

log = structlog.get_logger(__name__)

_AGRESSAO = (2, 3)
_NS_POR_H = 3_600_000_000_000
_BID, _ASK = 0, 1
PORTAO_FASE_3 = 160
DATA_BOOK_CONFIAVEL = "2026-08-26"
_STREAMS_BOOK = ("book_offer", "book_price", "tiny_book")


def barras_de_um_dia(trades: pd.DataFrame, volume_barra: int) -> dict[str, float]:
    """`trades` = negocios de UM pregao (ts_ns, price, quantidade, trade_type)."""
    if volume_barra <= 0:
        raise ValueError("volume_barra deve ser positivo")
    agr = trades[trades["trade_type"].isin(_AGRESSAO)]
    if agr.empty:
        return {"vol_agr": 0.0, "negocios_agr": 0.0, "barras": 0.0,
                "horas": 0.0, "barras_por_hora": float("nan"),
                "h_120min": float("nan"), "tick": float("nan")}
    vol = float(agr["quantidade"].sum())
    barras = float(int(vol // volume_barra))
    horas = float(int(agr["ts_ns"].max()) - int(agr["ts_ns"].min())) / _NS_POR_H
    bph = barras / horas if horas > 0 else float("nan")
    difs = agr["price"].diff().abs()
    pos = difs[difs > 0]
    tick = float(pos.min()) if len(pos) else float("nan")
    return {"vol_agr": vol, "negocios_agr": float(len(agr)), "barras": barras,
            "horas": horas, "barras_por_hora": bph,
            "h_120min": float(round(2 * bph)) if np.isfinite(bph) else float("nan"),
            "tick": tick}


def spread_de_um_dia(tiny: pd.DataFrame, tick: float) -> dict[str, float]:
    """`tiny` = updates de tiny_book de UM pregao (ts_recv_ns, side, price)."""
    vazio = {"spread_mediana_ticks": float("nan"), "spread_p90_ticks": float("nan"),
             "spread_frac_1tick": float("nan"), "spread_n": 0.0,
             "spread_invalidos": 0.0}
    if tiny.empty or not np.isfinite(tick) or tick <= 0:
        return vazio
    t = tiny.sort_values("ts_recv_ns", kind="stable")
    # price == 0 e' "lado vazio": o update VALE (apaga a cotacao anterior),
    # entao o ffill vem antes de descartar o zero -- se descartasse antes,
    # a cotacao velha seria arrastada por cima do vazio.
    bid = t["price"].where(t["side"] == _BID).ffill()
    ask = t["price"].where(t["side"] == _ASK).ffill()
    bid = bid.where(bid > 0)
    ask = ask.where(ask > 0)
    spread = (ask - bid).dropna()
    validos = spread[spread > 0] / tick
    invalidos = float((spread <= 0).sum())
    if validos.empty:
        return {**vazio, "spread_invalidos": invalidos}
    return {"spread_mediana_ticks": float(validos.median()),
            "spread_p90_ticks": float(validos.quantile(0.9)),
            "spread_frac_1tick": float((validos <= 1.0 + 1e-9).mean()),
            "spread_n": float(len(validos)), "spread_invalidos": invalidos}


def _pasta_stream(raw: Path, stream: str, dia: str, symbol: str) -> Path:
    return raw / stream / f"dt={dia}" / f"sym={symbol}"


def _contar(pasta: Path) -> int:
    if not pasta.exists():
        return 0
    return int(ds.dataset(pasta, format="parquet",
                          exclude_invalid_files=True).count_rows())


def book_de_um_dia(raw: Path, symbol: str, dia: str,
                   data_book_confiavel: str = DATA_BOOK_CONFIAVEL) -> dict[str, Any]:
    n = {s: _contar(_pasta_stream(raw, s, dia, symbol)) for s in _STREAMS_BOOK}
    integro = (dia >= data_book_confiavel and n["book_offer"] > 0
               and n["book_price"] > 0)
    return {"n_book_offer": float(n["book_offer"]),
            "n_book_price": float(n["book_price"]),
            "n_tiny_book": float(n["tiny_book"]),
            "book_confiavel_por_data": dia >= data_book_confiavel,
            "book_integro": bool(integro)}


def _carregar_tiny(raw: Path, symbol: str, dia: str) -> pd.DataFrame:
    pasta = _pasta_stream(raw, "tiny_book", dia, symbol)
    if not pasta.exists():
        return pd.DataFrame(columns=["ts_recv_ns", "side", "price"])
    tabela = ds.dataset(pasta, format="parquet", exclude_invalid_files=True)
    return cast(pd.DataFrame,
                tabela.to_table(columns=["ts_recv_ns", "side", "price"]).to_pandas())


def inventario(curated: Path, raw: Path, symbol: str, volume_barra: int,
               data_book_confiavel: str = DATA_BOOK_CONFIAVEL) -> dict[str, Any]:
    origem = curated / "trade"
    dias = _dias_do_symbol(origem, symbol)
    if not dias:
        raise SystemExit(f"nenhum pregao de {symbol} em {origem}")
    linhas: list[dict[str, Any]] = []
    for i, pasta in enumerate(dias, 1):
        dia = pasta.name.split("=", 1)[1]
        log.info("inventario_deepscalper.pregao", i=i, n=len(dias), dia=dia)
        trades = _carregar_dia(pasta, symbol)
        b = barras_de_um_dia(trades, volume_barra)
        s = spread_de_um_dia(_carregar_tiny(raw, symbol, dia), b["tick"])
        k = book_de_um_dia(raw, symbol, dia, data_book_confiavel)
        linhas.append({"dia": dia, **b, **s, **k})
    por_dia = pd.DataFrame(linhas)

    def med(col: str) -> float:
        v = por_dia[col].dropna()
        return float(v.median()) if len(v) else float("nan")

    integros = int(por_dia["book_integro"].sum())
    bph = med("barras_por_hora")
    resumo: dict[str, Any] = {
        "symbol": symbol, "volume_barra": volume_barra,
        "pregoes_trade": len(por_dia),
        "pregoes_book_integro": integros,
        "faltam_para_portao_fase3": max(0, PORTAO_FASE_3 - integros),
        "data_book_confiavel": data_book_confiavel,
        "barras_por_pregao_mediana": med("barras"),
        "horas_por_pregao_mediana": med("horas"),
        "barras_por_hora_mediana": bph,
        "h_120min": round(2 * bph) if np.isfinite(bph) else None,
        "tick_mediana": med("tick"),
        "spread_mediana_ticks": med("spread_mediana_ticks"),
        "spread_p90_ticks": med("spread_p90_ticks"),
        "spread_frac_1tick": med("spread_frac_1tick"),
        "pregoes_com_tiny_book": int((por_dia["spread_n"] > 0).sum()),
    }
    return {"por_dia": por_dia, "resumo": resumo}


def gravar(r: dict[str, Any], saida: Path) -> None:
    saida.mkdir(parents=True, exist_ok=True)
    r["por_dia"].to_parquet(saida / "por_dia.parquet", index=False)
    r["por_dia"].to_csv(saida / "por_dia.csv", index=False)
    with open(saida / "resumo.json", "w", encoding="utf-8") as f:
        json.dump(r["resumo"], f, ensure_ascii=False, indent=2)
