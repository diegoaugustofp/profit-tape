"""
IGNICAO x CONCENTRACAO DA AGRESSAO (fast-track, 2026-09-26).

PERGUNTA
--------
Entre as ignicoes da regra do EA (500 pts / 60 s, barreira +-530 em 60 min),
as empurradas por agressao CONCENTRADA continuam mais do que as outras?
Direcao declarada antes: concentracao ALTA -> p_alvo MAIOR.

FICHA (declarada ANTES de rodar -- HISTORICO 2026-09-26)
---------------------------------------------------------
Janela: os negocios do WIN com ts em (t_det - 60 s, t_det], ate' o negocio
da deteccao inclusive -- o mesmo recorte do saldo agressor de
`research/ignicao.py`. Nada depois da deteccao entra em variavel.
So' negocios de AGRESSAO (trade_type 2 = compra agressora, 3 = venda
agressora): RLP (13), cross (1), leilao etc. ficam fora.
V = volume agressor NA DIRECAO do salto (tipo 2 se alta, 3 se queda).

  C1 concentracao por NEGOCIO:
       volume dos 5 maiores negocios agressores na direcao / V
  C2 concentracao por CORRETORA (saldo liquido):
       cada negocio 2/3 soma +q ao agente comprador e -q ao vendedor,
       nos dois papeis (passivo e agressor). Saldo na direcao = saldo * d.
       C2 = maior saldo na direcao entre as corretoras / V.
       Market maker que agride e devolve passivamente zera o proprio saldo
       e nao conta. Agente <= 0 (nao identificado) fica FORA do maximo e
       entra na fracao `anon` (diagnostico, mostrada na etapa cega).
  Identidade da corretora de maior saldo: SO' registrada (agente_top).

Corte: MEDIANA de cada variavel nos eventos com V > 0. "alta" = acima da
mediana; empate na mediana vai para "baixa". Regra fixa, escolhida sem
ver resultado. p_alvo = alvo / (alvo + stop); 'nenhuma' (tempo) fora.
Empate de custo da ficha do EA: 0,537.

LEITURA (fast-track): ~25 eventos por metade e DUAS variaveis -> a chance
de uma parecer boa por sorte dobra. Resultado aqui e' INDICACAO; quem
decide e' o forward de um EA em paralelo. O EA congelado nao muda.

Limitacoes conhecidas: corretora != cliente (casa grande agrega muitos);
market maker pode zerar estoque em minutos, nao em 60 s (parte do ruido
passa); a ETAPA CEGA mostra a fracao de agente nao identificado antes de
qualquer resultado.
"""

from __future__ import annotations

import csv
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.dataset as ds

from .ignicao import COMPRA_AGRESSORA, VENDA_AGRESSORA, wilson

_NS = 1_000_000_000
TOP_NEGOCIOS = 5
EMPATE_FICHA = 0.537


@dataclass
class TapeAg:
    ts: np.ndarray
    px: np.ndarray
    qtd: np.ndarray
    tipo: np.ndarray
    comprador: np.ndarray
    vendedor: np.ndarray

    def __len__(self) -> int:
        return len(self.ts)


def carregar_tape_agentes(raiz: Path, symbol: str, dia: str) -> TapeAg:
    """Como `ignicao.carregar_tape`, mais os dois agentes. Deduplicado por
    trade_id (fica a edicao), ordenado por ts."""
    pasta = raiz / "trade" / f"dt={dia}" / f"sym={symbol}"
    i64 = np.empty(0, np.int64)
    vazio = TapeAg(i64, np.empty(0), i64, i64, i64, i64)
    if not pasta.exists():
        return vazio
    d = ds.dataset(pasta, format="parquet", exclude_invalid_files=True)
    cols = [c for c in ("ts_ns", "trade_id", "price", "quantidade", "trade_type",
                        "agente_comprador", "agente_vendedor") if c in d.schema.names]
    df = d.to_table(columns=cols).to_pandas()
    df = df[(df["ts_ns"] > 0) & (df["price"] > 0)]
    if "trade_id" in df.columns:
        df = df.drop_duplicates(subset=["trade_id"], keep="last")
    df = df.sort_values("ts_ns", kind="stable")
    if df.empty:
        return vazio
    n = len(df)

    def col(nome: str, padrao: int) -> np.ndarray:
        return (df[nome].to_numpy(np.int64) if nome in df
                else np.full(n, padrao, np.int64))

    return TapeAg(df["ts_ns"].to_numpy(np.int64), df["price"].to_numpy(np.float64),
                  col("quantidade", 1), col("trade_type", 0),
                  col("agente_comprador", 0), col("agente_vendedor", 0))


@dataclass
class Features:
    v_dir: float              # volume agressor na direcao
    c1: float | None          # top-5 negocios / V
    c2: float | None          # maior saldo liquido na direcao / V
    agente_top: int | None    # corretora do maior saldo (so' registro)
    anon: float | None        # fracao do volume 2/3 com agente <= 0
    n_negocios: int           # negocios 2/3 na janela


def features_janela(qtd: np.ndarray, tipo: np.ndarray, comprador: np.ndarray,
                    vendedor: np.ndarray, direcao: int) -> Features:
    """Fatia JA' recortada na janela (ate' a deteccao, inclusive)."""
    agr = (tipo == COMPRA_AGRESSORA) | (tipo == VENDA_AGRESSORA)
    q, tp = qtd[agr].astype(np.float64), tipo[agr]
    comp, vend = comprador[agr], vendedor[agr]
    na_dir = tp == (COMPRA_AGRESSORA if direcao > 0 else VENDA_AGRESSORA)
    v = float(q[na_dir].sum())
    total = float(q.sum())
    anon = (float(q[(comp <= 0) | (vend <= 0)].sum()) / total) if total > 0 else None
    if v <= 0:
        return Features(v, None, None, None, anon, int(agr.sum()))

    top = np.sort(q[na_dir])[::-1][:TOP_NEGOCIOS]
    c1 = float(top.sum()) / v

    saldo: dict[int, float] = {}
    for a, b, x in zip(comp.tolist(), vend.tolist(), q.tolist(), strict=True):
        if a > 0:
            saldo[a] = saldo.get(a, 0.0) + x
        if b > 0:
            saldo[b] = saldo.get(b, 0.0) - x
    c2: float | None = None
    agente_top: int | None = None
    if saldo:
        agente_top, melhor = max(((ag, s * direcao) for ag, s in saldo.items()),
                                 key=lambda t: t[1])
        c2 = max(0.0, melhor) / v
    return Features(v, c1, c2, agente_top, anon, int(agr.sum()))


@dataclass
class EventoAg:
    dia: str
    hora_brt: str
    ts_ns: int
    direcao: int
    barreira: str             # alvo / stop / nenhuma (do CSV do estudo)
    f: Features


def ler_eventos(caminhos: list[Path]) -> list[dict[str, str]]:
    """Linhas dos CSVs do `profit-tape ignicao` (dedup por dia+ts_ns)."""
    vistos: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for p in caminhos:
        with p.open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                k = (r["dia"], r["ts_ns"])
                if k not in vistos:
                    vistos.add(k)
                    out.append(r)
    return sorted(out, key=lambda r: int(r["ts_ns"]))


def indice_deteccao(tape: TapeAg, ts_ns: int, preco: float) -> int | None:
    """Primeiro negocio com o ts da deteccao e o preco de deteccao (no mesmo
    nanossegundo pode haver varios; a deteccao e' o primeiro que cruza)."""
    a = int(np.searchsorted(tape.ts, ts_ns, side="left"))
    b = int(np.searchsorted(tape.ts, ts_ns, side="right"))
    if a == b:
        return None
    hit = np.flatnonzero(np.abs(tape.px[a:b] - preco) < 1e-6)
    return a + int(hit[0]) if len(hit) else b - 1


def calcular(raizes: list[Path], symbol: str, linhas: list[dict[str, str]],
             janela_s: float = 60.0) -> tuple[list[EventoAg], list[str]]:
    """Features de cada evento. Cada dia e' lido da 1a raiz que o tem
    (local e backup). Devolve (eventos, avisos)."""
    jan = int(janela_s * _NS)
    evs: list[EventoAg] = []
    avisos: list[str] = []
    por_dia: dict[str, list[dict[str, str]]] = {}
    for r in linhas:
        por_dia.setdefault(r["dia"], []).append(r)
    for dia, rs in por_dia.items():
        raiz = next((r for r in raizes
                     if (r / "trade" / f"dt={dia}" / f"sym={symbol}").exists()), None)
        tape = (carregar_tape_agentes(raiz, symbol, dia) if raiz is not None
                else carregar_tape_agentes(raizes[0], symbol, dia))
        if len(tape) == 0:
            avisos.append(f"{dia}: sem tape em nenhuma raiz")
            continue
        for r in rs:
            t = int(r["ts_ns"])
            i = indice_deteccao(tape, t, float(r["preco"]))
            if i is None:
                avisos.append(f"{dia} {r['hora_brt']}: deteccao nao achada no tape")
                continue
            j0 = int(np.searchsorted(tape.ts, t - jan, side="right"))
            sl = slice(j0, i + 1)
            f = features_janela(tape.qtd[sl], tape.tipo[sl], tape.comprador[sl],
                                tape.vendedor[sl], int(r["direcao"]))
            evs.append(EventoAg(dia, r["hora_brt"], t, int(r["direcao"]),
                                r["barreira"], f))
    return evs, avisos


def spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3:
        return None
    rx = np.argsort(np.argsort(x)).astype(float)
    ry = np.argsort(np.argsort(y)).astype(float)
    c = np.corrcoef(rx, ry)[0, 1]
    return None if math.isnan(c) else round(float(c), 3)


def etapa_cega(evs: list[EventoAg]) -> dict[str, Any]:
    """TUDO que pode ser visto antes do resultado. Nao le `barreira`."""
    c1 = [e.f.c1 for e in evs if e.f.c1 is not None]
    c2 = [e.f.c2 for e in evs if e.f.c2 is not None]
    par = [(e.f.c1, e.f.c2) for e in evs if e.f.c1 is not None and e.f.c2 is not None]
    anon = [e.f.anon for e in evs if e.f.anon is not None]
    tops: dict[int, int] = {}
    for e in evs:
        if e.f.agente_top is not None:
            tops[e.f.agente_top] = tops.get(e.f.agente_top, 0) + 1

    def dist(v: list[float]) -> dict[str, float] | None:
        if not v:
            return None
        a = np.array(v)
        return {k: round(float(np.percentile(a, p)), 3)
                for k, p in (("p10", 10), ("p25", 25), ("mediana", 50),
                             ("p75", 75), ("p90", 90))}

    return {"eventos": len(evs),
            "sem_volume_na_direcao": sum(e.f.c1 is None for e in evs),
            "c1": dist(c1), "c2": dist(c2),
            "corte_c1": round(float(np.median(c1)), 4) if c1 else None,
            "corte_c2": round(float(np.median(c2)), 4) if c2 else None,
            "spearman_c1_c2": spearman([a for a, _ in par], [b for _, b in par]),
            "anon": dist(anon),
            "agente_top_mais_frequentes": sorted(tops.items(), key=lambda t: -t[1])[:8]}


def _bloco(sub: list[EventoAg]) -> dict[str, Any]:
    dec = [e for e in sub if e.barreira in ("alvo", "stop")]
    k = sum(e.barreira == "alvo" for e in dec)
    return {"n": len(sub), "decididos": len(dec), "alvo": k,
            "p_alvo": round(k / len(dec), 3) if dec else None,
            "ic95": wilson(k, len(dec))}


def medir(evs: list[EventoAg], var: str, corte: float) -> dict[str, Any]:
    """Metades pela regra da ficha: alta = acima do corte; empate -> baixa."""
    val = [(e, getattr(e.f, var)) for e in evs]
    com = [(e, v) for e, v in val if v is not None]
    alta = [e for e, v in com if v > corte]
    baixa = [e for e, v in com if v <= corte]
    ra, rb = _bloco(alta), _bloco(baixa)
    dif = (None if ra["p_alvo"] is None or rb["p_alvo"] is None
           else round(ra["p_alvo"] - rb["p_alvo"], 3))
    lo = ra["ic95"][0] if ra["ic95"] else None
    return {"corte": corte, "alta": ra, "baixa": rb, "diferenca": dif,
            "sem_valor": len(val) - len(com),
            "leitura": ("alta com IC acima do empate" if lo is not None
                        and lo > EMPATE_FICHA else
                        "alta NAO separa do empate")}


def linha_csv(e: EventoAg, com_resultado: bool) -> dict[str, Any]:
    d: dict[str, Any] = {"dia": e.dia, "hora_brt": e.hora_brt, "ts_ns": e.ts_ns,
                         "direcao": e.direcao, **asdict(e.f)}
    if com_resultado:
        d["barreira"] = e.barreira
    return d
