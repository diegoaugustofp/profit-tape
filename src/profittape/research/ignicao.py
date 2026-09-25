"""
IGNICOES: grandes movimentos do WIN -- detectar e acompanhar, nao prever
(fast-track, 2026-09-25).

MOTIVACAO
---------
Microprice e lead-lag deram sinais REAIS de +1 a +2 pts que morrem em
segundos (sonda h30 = ruido; lideranca WIN->WDO some a partir de 250 ms).
Nao preveem um candle de 1.000 pts: isso e' choque de informacao que
atinge os dois mercados juntos. A troca de pergunta e': dado que o
movimento COMECOU e foi detectado, ele CONTINUA o bastante para pagar a
entrada tardia? Nessa escala o custo de ~9 pts (taker) vira detalhe.

DESENHO (declarado ANTES de ver numero -- HISTORICO 2026-09-25)
---------------------------------------------------------------
Ignicao:     WIN anda >= `limiar_pts` em <= `janela_s` (preco do negocio
             agora vs ha' janela), detectada NO PRIMEIRO negocio que cruza.
             Horario [inicio, fim) BRT. Refratario `refratario_s` (default
             = maior horizonte: eventos nao se sobrepoem).
Confirmacao: WDO na MESMA janela. `confirma` = andou >= `conf_pts` no
             sentido OPOSTO (choque macro); `contra` = >= conf_pts no
             MESMO sentido; `neutro` = o resto.
Agressao:    saldo (compra - venda agressora)/(total agressor) do WIN na
             janela, na direcao do movimento. So' registrado (CSV); nao
             entra no resumo -- a pergunta declarada e' a do WDO.
Resultado:   a partir do preco de DETECCAO, na direcao do movimento:
             ret em cada horizonte; MFE/MAE ate' o maior horizonte;
             BARREIRA: qual de +alvo/-stop o tape toca primeiro (ordem
             resolvida pelo proprio tape, sem empate intrabarra). Com
             barreiras simetricas e custo C, empate em p = (stop + C) /
             (alvo + stop). Variancia limitada p(1-p) (skill forward 1.1).

A pergunta que decide: p_alvo(confirma) > p_alvo(neutro/contra) e acima
do empate. ANTES dela: a TAXA de eventos por pregao.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.dataset as ds

from .leadlag import janela_do_dia, preco_em

_NS = 1_000_000_000
_BRT = dt.timezone(dt.timedelta(hours=-3))
COMPRA_AGRESSORA, VENDA_AGRESSORA = 2, 3


@dataclass
class Tape:
    ts: np.ndarray
    px: np.ndarray
    qtd: np.ndarray
    tipo: np.ndarray

    def __len__(self) -> int:
        return len(self.ts)


def carregar_tape(raiz: Path, symbol: str, dia: str) -> Tape:
    """Raw deduplicado por trade_id (fica a edicao), ordenado."""
    pasta = raiz / "trade" / f"dt={dia}" / f"sym={symbol}"
    vazio = Tape(np.empty(0, np.int64), np.empty(0), np.empty(0, np.int64),
                 np.empty(0, np.int64))
    if not pasta.exists():
        return vazio
    d = ds.dataset(pasta, format="parquet", exclude_invalid_files=True)
    cols = [c for c in ("ts_ns", "trade_id", "price", "quantidade", "trade_type")
            if c in d.schema.names]
    df = d.to_table(columns=cols).to_pandas()
    df = df[(df["ts_ns"] > 0) & (df["price"] > 0)]
    if "trade_id" in df.columns:
        df = df.drop_duplicates(subset=["trade_id"], keep="last")
    df = df.sort_values("ts_ns", kind="stable")
    if df.empty:
        return vazio
    n = len(df)
    qtd = df["quantidade"].to_numpy(np.int64) if "quantidade" in df else np.ones(n, np.int64)
    tipo = df["trade_type"].to_numpy(np.int64) if "trade_type" in df else np.zeros(n, np.int64)
    return Tape(df["ts_ns"].to_numpy(np.int64), df["price"].to_numpy(np.float64), qtd, tipo)


@dataclass
class Ignicao:
    dia: str
    hora_brt: str
    ts_ns: int
    direcao: int              # +1 alta, -1 queda
    mov_pts: float            # WIN na janela (com sinal)
    preco: float              # preco de deteccao
    wdo_mov_pts: float | None
    classe: str               # confirma / neutro / contra / sem_wdo
    agressao: float | None    # saldo agressor na direcao, [-1, 1]
    ret: dict[int, float]     # horizonte_s -> pts na direcao
    mfe: float
    mae: float
    barreira: str             # alvo / stop / nenhuma


def _hora(ts: int) -> str:
    return dt.datetime.fromtimestamp(ts / _NS, _BRT).strftime("%H:%M:%S")


def detectar(win: Tape, wdo: Tape, dia: str, *, limiar_pts: float, janela_s: float,
             refratario_s: float, conf_pts: float, horizontes_s: list[int],
             alvo_pts: float, stop_pts: float, inicio_hhmm: int, fim_hhmm: int
             ) -> list[Ignicao]:
    if len(win) == 0:
        return []
    t0, t1 = janela_do_dia(dia, inicio_hhmm, fim_hhmm)
    jan = int(janela_s * _NS)
    antes = preco_em(win.ts, win.px, win.ts - jan)
    mov = win.px - antes
    cand = np.flatnonzero(np.isfinite(mov) & (np.abs(mov) >= limiar_pts - 1e-9)
                          & (win.ts >= t0 + jan) & (win.ts < t1))
    hmax = max(horizontes_s) * _NS
    out: list[Ignicao] = []
    livre_desde = -1
    for i in cand:
        t = int(win.ts[i])
        if t < livre_desde:
            continue
        livre_desde = t + int(refratario_s * _NS)
        d = 1 if mov[i] > 0 else -1
        p0 = float(win.px[i])

        # --- confirmacao pelo WDO na mesma janela
        wdo_mov: float | None = None
        classe = "sem_wdo"
        if len(wdo):
            a, b = preco_em(wdo.ts, wdo.px, np.array([t - jan, t], dtype=np.int64))
            if np.isfinite(a) and np.isfinite(b):
                wdo_mov = float(b - a)
                if wdo_mov * -d >= conf_pts - 1e-9:
                    classe = "confirma"
                elif wdo_mov * d >= conf_pts - 1e-9:
                    classe = "contra"
                else:
                    classe = "neutro"

        # --- saldo agressor do WIN na janela, na direcao do movimento
        j0 = int(np.searchsorted(win.ts, t - jan, side="right"))
        tp, q = win.tipo[j0:i + 1], win.qtd[j0:i + 1]
        c, v = float(q[tp == COMPRA_AGRESSORA].sum()), float(q[tp == VENDA_AGRESSORA].sum())
        agressao = (c - v) / (c + v) * d if c + v > 0 else None

        # --- resultado depois da deteccao
        ret: dict[int, float] = {}
        pts = preco_em(win.ts, win.px,
                       np.array([t + h * _NS for h in horizontes_s], dtype=np.int64))
        ultimo_ts = int(win.ts[-1])
        for h, p in zip(horizontes_s, pts, strict=True):
            if t + h * _NS <= ultimo_ts and np.isfinite(p):
                ret[h] = float((p - p0) * d)
        k1 = int(np.searchsorted(win.ts, t + hmax, side="right"))
        cam = (win.px[i + 1:k1] - p0) * d
        # o ponto de partida conta: MFE >= 0 e MAE <= 0 por definicao
        mfe = max(0.0, float(cam.max())) if len(cam) else 0.0
        mae = min(0.0, float(cam.min())) if len(cam) else 0.0
        barreira = "nenhuma"
        hit_a = np.flatnonzero(cam >= alvo_pts - 1e-9)
        hit_s = np.flatnonzero(cam <= -stop_pts + 1e-9)
        if len(hit_a) or len(hit_s):
            ia = hit_a[0] if len(hit_a) else math.inf
            is_ = hit_s[0] if len(hit_s) else math.inf
            barreira = "alvo" if ia < is_ else "stop"
        out.append(Ignicao(dia, _hora(t), t, d, float(mov[i]), p0, wdo_mov, classe,
                           None if agressao is None else round(agressao, 3),
                           ret, mfe, mae, barreira))
    return out


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n == 0:
        return None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return round(c - m, 3), round(c + m, 3)


def resumir(evs: list[Ignicao], horizontes_s: list[int], n_dias: int) -> dict[str, Any]:
    def bloco(sub: list[Ignicao]) -> dict[str, Any]:
        r: dict[str, Any] = {"n": len(sub),
                             "por_dia": round(len(sub) / n_dias, 2) if n_dias else None}
        if not sub:
            return r
        for h in horizontes_s:
            v = np.array([e.ret[h] for e in sub if h in e.ret])
            if len(v):
                r[f"ret_{h // 60}min"] = {"media": round(float(v.mean()), 1),
                                          "mediana": round(float(np.median(v)), 1),
                                          "pct_pos": round(100 * float((v > 0).mean()), 1)}
        r["mfe_mediana"] = round(float(np.median([e.mfe for e in sub])), 1)
        r["mae_mediana"] = round(float(np.median([e.mae for e in sub])), 1)
        dec = [e for e in sub if e.barreira != "nenhuma"]
        k = sum(e.barreira == "alvo" for e in dec)
        r["barreira"] = {"decididos": len(dec), "alvo": k,
                         "p_alvo": round(k / len(dec), 3) if dec else None,
                         "ic95": wilson(k, len(dec)),
                         "sem_decisao": len(sub) - len(dec)}
        return r

    classes = ["confirma", "neutro", "contra", "sem_wdo"]
    return {"todos": bloco(evs),
            **{c: bloco([e for e in evs if e.classe == c]) for c in classes
               if any(e.classe == c for e in evs)}}


def linha_csv(e: Ignicao) -> dict[str, Any]:
    d = asdict(e)
    ret = d.pop("ret")
    for h, v in ret.items():
        d[f"ret_{h}s"] = v
    return d
