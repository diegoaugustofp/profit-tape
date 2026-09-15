"""
Semente da MME80 para o EA de preco (passo 2 do F5 do 123, EAS_DE_PRECO.md 5.4).

POR QUE EXISTE
--------------
A MME80 da ficha e' CONTINUA entre pregoes e leva 5 x 80 = 400 barras
(~11 pregoes) para esquecer a semente (medido: com 3 x 80 sobrava 0,26%,
5 pts de uma semente 2.000 pts fora; com 5 x 80, 0,1 pt). Um EA que
liga as 09:00 e comeca a MME do primeiro close vai discordar do grafico
por duas semanas -- e o regime (close vs MME80) e' clausula da ficha.

DE ONDE VEM
-----------
Duas fontes, nesta ordem, as duas em disco ANTES do primeiro trade:

1. PARQUET do grafico (`barras_123.parquet`, saida do `eas-preco --ficha
   123`): traz `mme80_ntsl`, o valor que o PROPRIO Profit calculou. E' a
   historia profunda -- 10 anos se quiser. O valor da ultima barra e' a
   semente exata, sem aquecimento nenhum.
2. PONTE pelo TAPE (`curated`): se o parquet termina no dia D-k, os dias
   D-k+1 .. D-1 sao reconstruidos com o `ConstrutorDeBarraDeTempo` (o
   mesmo do EA, conferido 69/69 contra o grafico) e a recursao continua
   barra a barra: mme = alpha*close + (1-alpha)*mme.

REGRAS DE VALIDADE (sem semente valida o EA NAO arma e loga)
-----------------------------------------------------------
- Todo dia UTIL entre o fim do parquet e D-1 precisa ter tape, ou estar
  na lista de feriados. Um dia de barras pulado desloca a MME pelo
  movimento daquele dia (centenas de pontos), e o erro leva 11 pregoes
  para sumir. Dia faltando = semente INVALIDA, com o dia no motivo.
- A primeira barra do tape num dia de ponte e' `parcial` -- mas a MME
  usa so' o CLOSE, que a barra parcial tem certo (o ultimo negocio foi
  visto). Entra normalmente. O que a parcial invalida e' geometria
  (open/high/low), nao o indicador.
- Dentro de um dia, as barras do tape tem que cobrir >= 30 barras
  (um pregao inteiro tem ~37). Menos que isso e' tape com buraco
  (queda de conexao) -> invalida, com o dia no motivo.

AO VIVO
-------
`IndicadorMME.atualizar(close)` a cada barra fechada (parcial ou nao). O
EA loga a semente no arranque (valor, origem, ultima barra) e a MME a
cada barra; o `semente-conferir` mede, no dado real, a diferenca entre
esta recursao e o `mme80_ntsl` do grafico ao longo de um dia inteiro.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from ..features.pipeline import _carregar_dia
from .barra_tempo import ConstrutorDeBarraDeTempo

log = structlog.get_logger(__name__)

_NS = 1_000_000_000
MME_PERIODO = 80
BARRAS_MINIMAS_POR_DIA = 30


class IndicadorMME:
    """Media movel exponencial, semeada num valor dado (nao no primeiro
    close). alpha = 2/(n+1) -- a variante que bateu com o Profit
    (`mme80_close`, 0,03 pt em 28.000 barras)."""

    def __init__(self, periodo: int, valor_inicial: float) -> None:
        self.periodo = periodo
        self.alpha = 2.0 / (periodo + 1)
        self.valor = float(valor_inicial)
        self.n = 0

    def atualizar(self, close: float) -> float:
        self.valor = self.alpha * close + (1.0 - self.alpha) * self.valor
        self.n += 1
        return self.valor


@dataclass
class Semente:
    valida: bool
    valor: float | None
    ultima_barra: str                      # "YYYY-MM-DD HHMM"
    parquet_ate: str | None
    ponte_dias: list[str] = field(default_factory=list)
    motivo: str = ""
    barras_por_dia_ponte: dict[str, int] = field(default_factory=dict)

    def resumo(self) -> dict[str, Any]:
        return {"valida": self.valida, "valor": (round(self.valor, 2) if self.valor else None),
                "ultima_barra": self.ultima_barra, "parquet_ate": self.parquet_ate,
                "ponte_dias": self.ponte_dias, "motivo": self.motivo,
                "barras_por_dia_ponte": self.barras_por_dia_ponte}


def _dias_uteis(a: dt.date, b: dt.date) -> list[dt.date]:
    """Dias de segunda a sexta em (a, b], exclusivo em a."""
    out, d = [], a + dt.timedelta(days=1)
    while d <= b:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def _barras_do_tape(curated: Path, symbol: str, dia: dt.date,
                    periodo_s: int) -> list[tuple[int, float]]:
    """[(ts_open_ns, close)] das barras do dia, pelo construtor do EA."""
    pasta = curated / "trade" / f"dt={dia.isoformat()}"
    if not (pasta / f"sym={symbol}").exists():
        return []
    t = _carregar_dia(pasta, symbol)
    if t.empty:
        return []
    c = ConstrutorDeBarraDeTempo(periodo_s)
    out: list[tuple[int, float]] = []
    for ts_ns, price, qtd, tipo in t[["ts_ns", "price", "quantidade", "trade_type"]].itertuples(
            index=False):
        b = c.processar_trade(int(ts_ns), float(price), int(qtd), int(tipo))
        if b is not None:
            out.append((b.ts_open_ns, b.close))
    fim = c.avancar_relogio(int(t["ts_ns"].to_numpy()[-1]) + periodo_s * _NS)
    if fim is not None:
        out.append((fim.ts_open_ns, fim.close))
    return out


def construir_semente(parquet: Path, dia_alvo: dt.date, curated: Path | None = None,
                      symbol: str = "WINFUT", periodo_s: int = 900,
                      feriados: tuple[dt.date, ...] = (),
                      col_mme: str = "mme80_ntsl") -> Semente:
    """Semente da MME80 para operar em `dia_alvo`, com tudo que existe ANTES dele."""
    if not parquet.exists():
        return Semente(False, None, "", None, motivo=f"parquet nao existe: {parquet}")
    hist = pd.read_parquet(parquet, columns=["dia", "hhmm", "close", col_mme])
    hist["dia"] = pd.to_datetime(hist["dia"].astype(str)).dt.date
    hist = hist[hist["dia"] < dia_alvo].sort_values(["dia", "hhmm"])
    hist = hist[hist[col_mme].notna()]
    if hist.empty:
        return Semente(False, None, "", None,
                       motivo=f"parquet nao tem barra com {col_mme} antes de {dia_alvo}")
    ult = hist.iloc[-1]
    parquet_ate: dt.date = ult["dia"]
    mme = IndicadorMME(MME_PERIODO, float(ult[col_mme]))
    ultima = f"{parquet_ate} {int(ult['hhmm']):04d}"

    # ponte: dias uteis entre o fim do parquet e a vespera do alvo
    pendentes = [d for d in _dias_uteis(parquet_ate, dia_alvo - dt.timedelta(days=1))
                 if d not in feriados]
    ponte: list[str] = []
    contagens: dict[str, int] = {}
    for d in pendentes:
        barras = _barras_do_tape(curated, symbol, d, periodo_s) if curated else []
        contagens[d.isoformat()] = len(barras)
        if len(barras) < BARRAS_MINIMAS_POR_DIA:
            return Semente(False, None, ultima, parquet_ate.isoformat(), ponte,
                           motivo=(f"dia util {d} sem tape suficiente na ponte "
                                   f"({len(barras)} barras; minimo {BARRAS_MINIMAS_POR_DIA}). "
                                   "Backfill + cura, ou refazer o dump do grafico, ou declarar "
                                   "feriado."),
                           barras_por_dia_ponte=contagens)
        for _ts_open, close in barras:
            mme.atualizar(close)
        ponte.append(d.isoformat())
        t = pd.Timestamp(barras[-1][0], unit="ns", tz="UTC").tz_convert("America/Sao_Paulo")
        ultima = f"{d} {t.hour * 100 + t.minute:04d}"
    s = Semente(True, mme.valor, ultima, parquet_ate.isoformat(), ponte,
                barras_por_dia_ponte=contagens)
    log.info("ea.semente_mme80", **s.resumo(), dia_alvo=dia_alvo.isoformat())
    return s


def conferir_no_dia(parquet: Path, dia: dt.date, curated: Path, symbol: str = "WINFUT",
                    periodo_s: int = 900, feriados: tuple[dt.date, ...] = ()) -> dict[str, Any]:
    """
    Semente construida com tudo ANTES de `dia`, recursao pelas barras do
    TAPE de `dia`, comparada barra a barra com o mme80_ntsl do grafico no
    mesmo dia (que esta' no parquet). E' a equivalencia ao vivo, no dado
    real, do que o EA vai fazer.
    """
    s = construir_semente(parquet, dia, curated, symbol, periodo_s, feriados)
    if not s.valida or s.valor is None:
        return {"semente": s.resumo(), "erro": s.motivo}
    graf = pd.read_parquet(parquet, columns=["dia", "hhmm", "close", "mme80_ntsl"])
    graf["dia"] = pd.to_datetime(graf["dia"].astype(str)).dt.date
    graf = graf[graf["dia"] == dia].set_index("hhmm")
    barras = _barras_do_tape(curated, symbol, dia, periodo_s)
    mme = IndicadorMME(MME_PERIODO, s.valor)
    linhas = []
    for ts_open, close in barras:
        v = mme.atualizar(close)
        t = pd.Timestamp(ts_open, unit="ns", tz="UTC").tz_convert("America/Sao_Paulo")
        hhmm = t.hour * 100 + t.minute
        ref = float(graf["mme80_ntsl"].get(hhmm, float("nan")))
        linhas.append({"hhmm": hhmm, "close_tape": close,
                       "close_grafico": float(graf["close"].get(hhmm, float("nan"))),
                       "mme_ea": round(v, 2), "mme_grafico": round(ref, 2),
                       "dif": round(v - ref, 2) if ref == ref else None})
    df = pd.DataFrame(linhas)
    comp = df[df["dif"].notna()]
    return {"semente": s.resumo(), "barras": len(df), "comparaveis": len(comp),
            "dif_max": (round(float(comp["dif"].abs().max()), 2) if len(comp) else None),
            "dif_primeira": (comp["dif"].iloc[0] if len(comp) else None),
            "dif_ultima": (comp["dif"].iloc[-1] if len(comp) else None),
            "detalhe": df.to_dict(orient="records")}
