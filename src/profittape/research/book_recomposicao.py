"""
RECOMPOSICAO NO LIVRO — passo 1, v2 (2026-09-19).

A hipotese do iceberg na FONTE CERTA (no tape de negocios ela era DADO
INSUFICIENTE: so' ha' o que executou).

CONTRAPARTE: quem negocia contra profundidade que nao ve. Uma oferta que
SAI do livro (consumida ou cancelada) e cujo lugar e' reposto pelo MESMO
agente, no MESMO preco e com o MESMO tamanho, em segundos, e' alguem
defendendo aquele nivel com capital.

POR QUE A v1 FOI REFEITA (sem nunca ter sido interpretada)
----------------------------------------------------------
A v1 contava "insercoes de mesmo tamanho no mesmo preco". Tres defeitos,
todos de VALIDEZ:

1. **O manual da DLL diz que fora de `atAdd` os campos escalares --
   inclusive `dPrice` -- NAO sao garantidos** (o mesmo motivo pelo qual
   `atFullBook` ja' era descartado na origem). A v1 usava `action in
   (ADD, EDIT)` como se EDIT trouxesse preco valido.
2. Nao exigia que fosse a MESMA ordem nem o mesmo agente: qualquer
   oferta de mesmo tamanho entrava na mesma "corrida". Resultado:
   `tamanho_max` de 63.508 num unico (preco, lado, quantidade) -- isso
   e' o preco mais negociado do dia acumulando lote 1, nao ordem
   defendendo nivel. Mesmo erro que o Times & Trades expos no iceberg
   do tape.
3. Lia o RAW sem deduplicar -- e duplicata e' literalmente "a oferta
   apareceu duas vezes", que infla recarga por construcao.

v2: ESTADO POR `offer_id`
-------------------------
`ADD` registra (offer_id -> preco, quantidade, agente, lado). `DELETE` /
`DELETE_FROM` resolvem o nivel pelo `offer_id` (sem depender dos campos
do proprio evento). RECARGA = uma SAIDA seguida, em ate' `janela_s`, de
uma ENTRADA com mesmo preco, lado, quantidade e AGENTE. A cadeia de
recargas consecutivas no mesmo nivel e' o que se conta.

LIMITES DECLARADOS
------------------
- `offer_id` pode ser reaproveitado no dia; o estado guarda o ultimo ADD.
- `agente` e' CORRETORA, nao cliente final (confirmado no iceberg do
  tape). Reduz o poder, nao invalida: exigir o mesmo agente ja' e' muito
  mais apertado que nao exigir nada.
- O relogio e' `ts_recv_ns` (recepcao): serve para INTERVALO entre
  eventos proximos, nao para datar contra o trade.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import structlog

from ..domain.enums import BookAction

log = structlog.get_logger(__name__)
_NS = 1_000_000_000
JANELA_S = 5.0
N_MINIMO = 3
_ADD = int(BookAction.ADD)
_SAIDAS = (int(BookAction.DELETE), int(BookAction.DELETE_FROM))
_COLS = ["ts_recv_ns", "action", "side", "price", "quantidade", "agente", "offer_id"]


def carregar_book(raiz: Path, symbol: str, dia: dt.date) -> tuple[pd.DataFrame, int]:
    """Le o book do dia e DEDUPLICA (o raw nao passa por cura). Devolve
    (df, duplicatas_removidas)."""
    pasta = raiz / "book_offer" / f"dt={dia.isoformat()}"
    if not pasta.exists():
        return pd.DataFrame(), 0
    dataset = ds.dataset(pasta, format="parquet", partitioning="hive",
                         exclude_invalid_files=True)
    cols = [c for c in _COLS if c in dataset.schema.names]
    t: pd.DataFrame = dataset.to_table(filter=ds.field("sym") == symbol,
                                       columns=cols).to_pandas()
    antes = len(t)
    t = t.drop_duplicates(subset=[c for c in ("ts_recv_ns", "offer_id", "action",
                                              "price", "quantidade") if c in t])
    return t.sort_values("ts_recv_ns").reset_index(drop=True), antes - len(t)


def eventos_de_nivel(df: pd.DataFrame) -> pd.DataFrame:
    """ENTRADAS e SAIDAS com o nivel resolvido.

    Entrada = `ADD` (unica acao em que preco/quantidade sao garantidos).
    Saida = `DELETE`/`DELETE_FROM`, com o nivel vindo do ultimo ADD
    daquele `offer_id` -- nao dos campos do proprio evento.
    """
    add = df[df["action"] == _ADD]
    if add.empty:
        return pd.DataFrame()
    estado = (add[["offer_id", "price", "quantidade", "agente", "side"]]
              .drop_duplicates("offer_id", keep="last"))
    saidas = df[df["action"].isin(_SAIDAS)][["ts_recv_ns", "offer_id"]]
    saidas = saidas.merge(estado, on="offer_id", how="inner")
    entradas = add[["ts_recv_ns", "offer_id", "price", "quantidade", "agente", "side"]]
    ev = pd.concat([entradas.assign(entrada=True), saidas.assign(entrada=False)],
                   ignore_index=True)
    return ev


def _cadeias(ev: pd.DataFrame, janela_ns: int) -> np.ndarray:
    """Tamanho de cada cadeia de RECARGAS: saida seguida de entrada no
    mesmo (preco, lado, quantidade, agente) dentro da janela."""
    if ev.empty:
        return np.array([], dtype=np.int64)
    chave = (ev["price"].to_numpy(dtype=np.float64), ev["side"].to_numpy(dtype=np.int64),
             ev["quantidade"].to_numpy(dtype=np.int64), ev["agente"].to_numpy(dtype=np.int64))
    ts = ev["ts_recv_ns"].to_numpy(dtype=np.int64)
    entrada = ev["entrada"].to_numpy(dtype=bool)
    ordem = np.lexsort((ts, *chave[::-1]))
    p, s_, q, a = (c[ordem] for c in chave)
    t, e = ts[ordem], entrada[ordem]
    mesma = np.empty(len(t), dtype=bool)
    mesma[0] = False
    mesma[1:] = ((p[1:] == p[:-1]) & (s_[1:] == s_[:-1]) & (q[1:] == q[:-1])
                 & (a[1:] == a[:-1]))
    # recarga: entrada logo apos uma SAIDA da mesma chave, dentro da janela
    recarga = np.zeros(len(t), dtype=bool)
    recarga[1:] = mesma[1:] & e[1:] & (~e[:-1]) & ((t[1:] - t[:-1]) <= janela_ns)
    if not recarga.any():
        return np.array([], dtype=np.int64)
    # CADEIA = recargas seguidas no MESMO nivel. Elas nao sao adjacentes no
    # vetor de eventos (entre duas ha' sempre a saida), entao a cadeia se
    # monta sobre as recargas isoladas: quebra quando a chave muda ou
    # quando o intervalo entre duas recargas passa da janela.
    idx = np.flatnonzero(recarga)
    pr, sr, qr, ar, tr = p[idx], s_[idx], q[idx], a[idx], t[idx]
    quebra = np.empty(len(idx), dtype=bool)
    quebra[0] = True
    quebra[1:] = ((pr[1:] != pr[:-1]) | (sr[1:] != sr[:-1]) | (qr[1:] != qr[:-1])
                  | (ar[1:] != ar[:-1]) | ((tr[1:] - tr[:-1]) > janela_ns))
    return np.bincount(np.cumsum(quebra) - 1).astype(np.int64)


def medir_dia(raiz: Path, symbol: str, dia: dt.date, janela_s: float = JANELA_S,
              n_minimo: int = N_MINIMO, semente: int = 1) -> dict[str, Any]:
    t0 = time.monotonic()
    df, dups = carregar_book(raiz, symbol, dia)
    if df.empty:
        return {}
    seg_leitura = round(time.monotonic() - t0, 1)
    ev = eventos_de_nivel(df)
    if ev.empty:
        return {}
    janela_ns = int(janela_s * _NS)
    tam = _cadeias(ev, janela_ns)
    # BASELINE: permuta o par (quantidade, agente) entre os eventos, mantendo
    # preco, lado e instante. Formador repondo rotina gera recarga; isto e'
    # o que separa reposicao automatica de nivel defendido.
    rng = np.random.default_rng(semente)
    perm = rng.permutation(len(ev))
    ev_b = ev.copy()
    ev_b["quantidade"] = ev["quantidade"].to_numpy()[perm]
    ev_b["agente"] = ev["agente"].to_numpy()[perm]
    tam_b = _cadeias(ev_b, janela_ns)

    def curva(v: np.ndarray) -> dict[str, int]:
        return {str(n): int((v >= n).sum()) for n in (3, 5, 10, 20, 50)}

    obs, base = curva(tam), curva(tam_b)
    r = {
        "dia": dia.isoformat(), "deltas": len(df), "duplicatas_removidas": int(dups),
        "entradas": int(ev["entrada"].sum()), "saidas": int((~ev["entrada"]).sum()),
        "recargas": int(tam.sum()),
        "niveis_defendidos": int((tam >= n_minimo).sum()),
        "cadeia_p50": float(np.median(tam)) if len(tam) else None,
        "cadeia_max": int(tam.max()) if len(tam) else 0,
        "por_limiar": obs, "baseline": base,
        "razao_por_limiar": {n: round((obs[n] + 1) / (base[n] + 1), 3) for n in obs},
        "segundos_leitura": seg_leitura,
        "segundos_total": round(time.monotonic() - t0, 1),
    }
    log.info("book_recomposicao.dia", **{k: v for k, v in r.items()
                                         if k not in ("por_limiar", "baseline",
                                                      "razao_por_limiar")})
    return r


def descrever(raiz: Path, symbol: str, dias: list[dt.date], janela_s: float = JANELA_S,
              n_minimo: int = N_MINIMO, saida: Path | None = None) -> dict[str, Any]:
    linhas = [r for d in dias if (r := medir_dia(raiz, symbol, d, janela_s, n_minimo))]
    if not linhas:
        raise SystemExit(f"nenhum dia com book_offer de {symbol} em {raiz}")
    agregado = {
        "dias": len(linhas),
        "deltas_p50": float(np.median([x["deltas"] for x in linhas])),
        "duplicatas_p50": float(np.median([x["duplicatas_removidas"] for x in linhas])),
        "recargas_p50": float(np.median([x["recargas"] for x in linhas])),
        "niveis_defendidos_p50": float(np.median([x["niveis_defendidos"] for x in linhas])),
        "cadeia_max": int(max(x["cadeia_max"] for x in linhas)),
        "por_limiar": {
            n: {"observado_p50": float(np.median([x["por_limiar"][n] for x in linhas])),
                "baseline_p50": float(np.median([x["baseline"][n] for x in linhas])),
                "razao_p50": float(np.median([x["razao_por_limiar"][n] for x in linhas]))}
            for n in linhas[0]["por_limiar"]},
        "segundos_por_dia_p50": float(np.median([x["segundos_total"] for x in linhas])),
    }
    r = {"symbol": symbol, "janela_s": janela_s, "n_minimo": n_minimo, "versao": "v2_offer_id",
         "agregado": agregado, "por_dia": linhas}
    if saida is not None:
        saida.mkdir(parents=True, exist_ok=True)
        (saida / "book_recomposicao.json").write_text(json.dumps(r, indent=2, default=str),
                                                      encoding="utf-8")
    return r
