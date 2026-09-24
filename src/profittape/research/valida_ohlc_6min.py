"""
OHLC de 6 minutos: o do PROFIT contra a NOSSA agregação.

A LACUNA QUE ISTO FECHA (11.4, aberta em 2026-09-23)
-----------------------------------------------------
O dump do gráfico de 6 min provou que a FÓRMULA do estocástico bate com
o Profit (dif_max = 0,00000000 em 1.509 barras). Mas provou isso sobre
o OHLC **do Profit**.

O código não usa esse OHLC: ele agrega as nossas barras de 15s do tape.
São dois caminhos diferentes para a mesma barra de 6 minutos, e se eles
divergirem, o estocástico diverge junto — com a fórmula certa e o
resultado errado.

Dois motivos concretos para desconfiar:
- as barras de 15s são montadas com TIPOS_OHLC_GRAFICO (um filtro de
  tipos de negócio). Se o Profit incluir tipos diferentes no gráfico de
  6 min, o high/low muda;
- 2,2% das barras de contexto têm menos de 24 barras de 15s (balde sem
  negócio não existe no dado). Nessas, a agregação vê menos preço.

O QUE É DIVERGÊNCIA E O QUE NÃO É
----------------------------------
`open` e `close` são o primeiro e o último negócio do balde: divergem se
os filtros de tipo diferirem. `high` e `low` são extremos: divergem se
QUALQUER negócio a mais ou a menos entrar. Por isso high/low são os
mais sensíveis, e é neles que uma diferença de filtro aparece primeiro.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import structlog

log = structlog.get_logger(__name__)


@dataclass
class ComparacaoOHLC:
    barras_profit: int
    barras_nossas: int
    barras_casadas: int
    so_no_profit: int
    so_nossas: int
    dif_max: dict[str, float]
    dif_qtd: dict[str, int]          # quantas barras divergem em cada campo

    @property
    def bateu(self) -> bool:
        """Tolerância zero: OHLC é preço de negócio, não conta com
        arredondamento. Qualquer diferença é divergência de verdade."""
        return all(v == 0.0 for v in self.dif_max.values()) and self.so_no_profit == 0

    def resumo(self) -> dict[str, object]:
        return {
            "barras_profit": self.barras_profit,
            "barras_nossas": self.barras_nossas,
            "casadas": self.barras_casadas,
            "so_no_profit": self.so_no_profit,
            "so_nossas": self.so_nossas,
            "dif_max": {k: round(v, 6) for k, v in self.dif_max.items()},
            "barras_divergentes": self.dif_qtd,
            "bateu": self.bateu,
        }


def agregar_15s_para_6min(barras15: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega as barras de 15s em 6 min, no formato do dump: uma linha por
    (dia, hora HHMM).

    Usa `ts_ini_ns` (epoch puro) e não `ts` (que carrega o offset de
    fuso) — mesmo cuidado de `bollinger_contexto._balde_das_barras`, e
    pela mesma razão: misturar os dois relógios dá 3 horas de erro.
    """
    if barras15.empty:
        return pd.DataFrame()
    x = barras15.copy()
    passo = 360 * 10**9
    x["balde6"] = (x["ts_ini_ns"].astype("int64") // passo) * passo
    g = x.groupby(["dia", "balde6"], sort=True)
    out = pd.DataFrame({
        "open": g["open"].first(),
        "high": g["high"].max(),
        "low": g["low"].min(),
        "close": g["close"].last(),
        "n15": g["close"].size(),
    }).reset_index()
    # hora local (o dump usa o relogio da bolsa): o `ts` das barras ja'
    # tem o offset aplicado, entao a hora sai dele.
    h = pd.to_datetime(out["balde6"] // 10**9, unit="s")
    offset = int((barras15["ts"].iloc[0] - pd.to_datetime(
        barras15["ts_ini_ns"].iloc[0] // 10**9, unit="s")).total_seconds())
    h = h + pd.Timedelta(seconds=offset)
    out["hora_int"] = h.dt.hour * 100 + h.dt.minute
    return out


def comparar(dump6: pd.DataFrame, nossas6: pd.DataFrame) -> ComparacaoOHLC:
    """
    `dump6`  = saida de `carregar_log` sobre o dump do grafico de 6 min.
    `nossas6` = saida de `agregar_15s_para_6min`.

    Casa por (dia, hora). Barras que existem so' de um lado sao
    reportadas separadamente -- NAO silenciadas: uma barra que o Profit
    tem e nos nao significa que o EA operaria com contexto diferente.
    """
    p = dump6[["dia", "hora_int", "open", "high", "low", "close"]].copy()
    n = nossas6[["dia", "hora_int", "open", "high", "low", "close", "n15"]].copy()
    p["dia"] = p["dia"].astype(str)
    n["dia"] = n["dia"].astype(str)
    j = p.merge(n, on=["dia", "hora_int"], how="outer",
                suffixes=("_profit", "_nosso"), indicator=True)
    casadas = j[j["_merge"] == "both"]
    dif_max, dif_qtd = {}, {}
    for campo in ("open", "high", "low", "close"):
        d = (casadas[f"{campo}_profit"] - casadas[f"{campo}_nosso"]).abs()
        dif_max[campo] = float(d.max()) if len(d) else 0.0
        dif_qtd[campo] = int((d > 0).sum()) if len(d) else 0
    return ComparacaoOHLC(
        barras_profit=len(p), barras_nossas=len(n), barras_casadas=len(casadas),
        so_no_profit=int((j["_merge"] == "left_only").sum()),
        so_nossas=int((j["_merge"] == "right_only").sum()),
        dif_max=dif_max, dif_qtd=dif_qtd,
    )
