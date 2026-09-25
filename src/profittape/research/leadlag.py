"""
LEAD-LAG WDO x WIN em MILISSEGUNDOS — medicao (fast-track, 2026-09-25).

POR QUE NAO O `defasagem.py`
----------------------------
`defasagem` (WIN x cesta, 17/09) usa barra >= 1 s, `dropna`+`shift(-1)`
(pula segundos sem negocio: "barra seguinte" pode ser 3 s depois) e
resume por `papel_antecipa > win_antecipa` -- que so' faz sentido para
ativos que andam JUNTOS. WDO e WIN andam em sentido OPOSTO: o lado que
lidera tem a correlacao defasada MAIS NEGATIVA, e aquela fracao sairia
invertida. O achado de la' (em 15 s o WIN chega ANTES das acoes) diz que
o futuro de indice ja' e' o lider rapido; a pergunta aqui e' se o DOLAR
chega antes dele em escala sub-segundo.

O QUE MEDE
----------
1. CORRELACAO CRUZADA em grade fixa (`passo_ms`, preco com ffill), por
   defasagem k em ms:  c(k) = corr(r_lider(t), r_seguidor(t+k)).
   k > 0: o lider se move ANTES. Leitura com sinal esperado s (-1 para
   WDO x WIN):  assimetria(k) = s * (c(k) - c(-k)) > 0  =>  lider na frente.
   Estatisticas SOMADAS entre dias (n, somas), nunca media de correlacoes.

2. ESTUDO DE EVENTOS (o que um EA usaria): evento = lider andou >=
   `limiar_ticks` em `janela_ms` (preco do negocio agora vs ha' janela).
   Direcao esperada do seguidor = s * sinal(movimento). Para cada evento:
     pre   = quanto o seguidor JA' andou na direcao esperada na janela
     pos_h = quanto anda depois, em h ms, na direcao esperada
   Em PONTOS do seguidor. Subconjunto `seguidor_parado` (|pre| < 1 tick):
   e' o gatilho acionavel -- "o dolar andou e o indice ainda nao".
   Refratario: evento do mesmo lado dentro de `refratario_ms` nao conta.

LIMITES CONHECIDOS
------------------
- Preco = ultimo NEGOCIO, nao mid: pos_h carrega o ruido do bid-ask bounce
  (+-2,5 pts no WIN). A media nao e' enviesada por ele; a dispersao e'.
- ts_ns = relogio da BOLSA, resolucao de ms. Defasagem < 1 ms e' invisivel.
- Mede estrutura, nao resultado: nao simula fill nem custo. O numero a
  comparar e' pos_h do subconjunto parado contra ~9 pts (spread 5 +
  custo 4, taker nos dois lados).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.dataset as ds
import structlog

log = structlog.get_logger(__name__)
_MS = 1_000_000
_BRT = dt.timezone(dt.timedelta(hours=-3))


# ---------------------------------------------------------------- carga
def carregar_precos(raiz: Path, symbol: str, dia: str) -> tuple[np.ndarray, np.ndarray]:
    """(ts_ns, preco) do tape bruto, deduplicado por trade_id (fica o
    ultimo: edicao sobrescreve), ordenado. Vazio se o dia nao existe."""
    pasta = raiz / "trade" / f"dt={dia}" / f"sym={symbol}"
    vazio = (np.empty(0, np.int64), np.empty(0, np.float64))
    if not pasta.exists():
        return vazio
    d = ds.dataset(pasta, format="parquet", exclude_invalid_files=True)
    cols = [c for c in ("ts_ns", "trade_id", "price") if c in d.schema.names]
    df = d.to_table(columns=cols).to_pandas()
    df = df[(df["ts_ns"] > 0) & (df["price"] > 0)]
    if "trade_id" in df.columns:
        df = df.drop_duplicates(subset=["trade_id"], keep="last")
    df = df.sort_values("ts_ns", kind="stable")
    if df.empty:
        return vazio
    return (df["ts_ns"].to_numpy(np.int64), df["price"].to_numpy(np.float64))


def janela_do_dia(dia: str, ini_hhmm: int, fim_hhmm: int) -> tuple[int, int]:
    d = dt.date.fromisoformat(dia)

    def ns(hhmm: int) -> int:
        t = dt.datetime(d.year, d.month, d.day, hhmm // 100, hhmm % 100, tzinfo=_BRT)
        return int(t.timestamp()) * 1_000_000_000

    return ns(ini_hhmm), ns(fim_hhmm)


def preco_em(ts: np.ndarray, px: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Ultimo preco negociado ate' cada instante de `t` (NaN se nenhum)."""
    i = np.searchsorted(ts, t, side="right") - 1
    out = np.full(len(t), np.nan)
    ok = i >= 0
    out[ok] = px[i[ok]]
    return out


# ------------------------------------------------- correlacao cruzada
@dataclass
class AcumCorr:
    lags_ms: list[int]
    n: dict[int, float] = field(default_factory=dict)
    sx: dict[int, float] = field(default_factory=dict)
    sy: dict[int, float] = field(default_factory=dict)
    sxx: dict[int, float] = field(default_factory=dict)
    syy: dict[int, float] = field(default_factory=dict)
    sxy: dict[int, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for d in (self.n, self.sx, self.sy, self.sxx, self.syy, self.sxy):
            for k in self.lags_ms:
                d[k] = 0.0

    def somar(self, r_lider: np.ndarray, r_seg: np.ndarray, passo_ms: int) -> None:
        for k in self.lags_ms:
            s = k // passo_ms
            if s >= 0:
                x, y = r_lider[: len(r_lider) - s], r_seg[s:]
            else:
                x, y = r_lider[-s:], r_seg[: len(r_seg) + s]
            ok = np.isfinite(x) & np.isfinite(y)
            x, y = x[ok], y[ok]
            self.n[k] += len(x)
            self.sx[k] += float(x.sum())
            self.sy[k] += float(y.sum())
            self.sxx[k] += float((x * x).sum())
            self.syy[k] += float((y * y).sum())
            self.sxy[k] += float((x * y).sum())

    def corr(self) -> dict[int, float | None]:
        out: dict[int, float | None] = {}
        for k in self.lags_ms:
            n = self.n[k]
            if n < 2:
                out[k] = None
                continue
            cov = self.sxy[k] - self.sx[k] * self.sy[k] / n
            vx = self.sxx[k] - self.sx[k] ** 2 / n
            vy = self.syy[k] - self.sy[k] ** 2 / n
            out[k] = cov / np.sqrt(vx * vy) if vx > 0 and vy > 0 else None
        return out


def retornos_na_grade(ts: np.ndarray, px: np.ndarray, tick: float,
                      t0: int, t1: int, passo_ms: int) -> np.ndarray:
    grade = np.arange(t0, t1, passo_ms * _MS, dtype=np.int64)
    p = preco_em(ts, px, grade) / tick
    return np.diff(p)


def assimetria(c: dict[int, float | None], sentido: int) -> dict[int, float | None]:
    """s*(c(k) - c(-k)) para k > 0: positivo = lider chega primeiro."""
    out: dict[int, float | None] = {}
    for k, v in c.items():
        if k <= 0:
            continue
        w = c.get(-k)
        out[k] = None if v is None or w is None else sentido * (v - w)
    return out


# ------------------------------------------------------ estudo de eventos
@dataclass
class Evento:
    ts_ns: int
    direcao_lider: int         # +1 lider subiu, -1 caiu
    pre_pts: float             # seguidor na janela ANTERIOR, na direcao esperada
    pos_pts: dict[int, float]  # h_ms -> movimento do seguidor, direcao esperada


def eventos(ts_l: np.ndarray, px_l: np.ndarray, ts_s: np.ndarray, px_s: np.ndarray,
            *, tick_lider: float, limiar_ticks: int, janela_ms: int,
            horizontes_ms: list[int], refratario_ms: int, sentido: int,
            t0: int, t1: int) -> list[Evento]:
    if len(ts_l) == 0 or len(ts_s) == 0:
        return []
    jan = janela_ms * _MS
    antes = preco_em(ts_l, px_l, ts_l - jan)
    mov = px_l - antes
    cand = np.flatnonzero(np.isfinite(mov) & (np.abs(mov) >= limiar_ticks * tick_lider - 1e-9)
                          & (ts_l >= t0 + jan) & (ts_l < t1))
    out: list[Evento] = []
    ultimo: dict[int, int] = {}
    for i in cand:
        t = int(ts_l[i])
        d = 1 if mov[i] > 0 else -1
        u = ultimo.get(d)
        if u is not None and t - u < refratario_ms * _MS:
            continue
        ultimo[d] = t
        esp = sentido * d
        pontos = np.array([t - jan, t] + [t + h * _MS for h in horizontes_ms], dtype=np.int64)
        p = preco_em(ts_s, px_s, pontos)
        if not np.isfinite(p[0]) or not np.isfinite(p[1]):
            continue
        pos = {h: float((p[2 + j] - p[1]) * esp) for j, h in enumerate(horizontes_ms)
               if np.isfinite(p[2 + j])}
        out.append(Evento(t, d, float((p[1] - p[0]) * esp), pos))
    return out


def resumir_eventos(evs: list[Evento], horizontes_ms: list[int],
                    tick_seg: float) -> dict[str, Any]:
    def bloco(sub: list[Evento]) -> dict[str, Any]:
        r: dict[str, Any] = {"n": len(sub)}
        if not sub:
            return r
        pre = np.array([e.pre_pts for e in sub])
        r["pre_media_pts"] = round(float(pre.mean()), 2)
        for h in horizontes_ms:
            v = np.array([e.pos_pts[h] for e in sub if h in e.pos_pts])
            if len(v):
                r[f"h{h}ms"] = {"media_pts": round(float(v.mean()), 2),
                                "pct_a_favor": round(100 * float((v > 0).mean()), 1),
                                "pct_contra": round(100 * float((v < 0).mean()), 1)}
        return r

    parado = [e for e in evs if abs(e.pre_pts) < tick_seg - 1e-9]
    return {"todos": bloco(evs), "seguidor_parado": bloco(parado)}
