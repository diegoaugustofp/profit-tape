"""
RECOMPOSICAO NO LIVRO — passo 1 (2026-09-17).

A hipotese do iceberg, agora na FONTE CERTA. No tape de negocios ela nao
e' testavel (o tape so' tem o que EXECUTOU, e ordem escondida vive
justamente sem executar) -- ver RESEARCH_PLANO, "COMO CLASSIFICAR UM
FECHAMENTO": aquilo foi DADO INSUFICIENTE, nao hipotese refutada.

CONTRAPARTE: quem negocia contra profundidade que nao ve. Se uma oferta
e' consumida e REAPARECE no mesmo preco, com o mesmo tamanho, em
segundos, ha' alguem defendendo aquele nivel com capital -- e quem
atravessa esta' comprando de quem nao acabou.

O `offer_book` do WINFUT e' ORDER-BY-ORDER: cada delta traz `offer_id`,
`agente`, preco, quantidade, lado, posicao na fila e a ACAO. E' a
materia-prima exata.

O QUE MEDE (features, zero trial, SEM DIRECAO)
----------------------------------------------
1. RECARGAS: por (preco, lado, quantidade), quantas vezes uma oferta
   some e outra do mesmo tamanho aparece em ate' `janela_s`.
2. Distribuicao do TAMANHO da recarga e de QUANTAS vezes o mesmo nivel
   se repoe (a cauda e' o que interessa -- licao do iceberg no tape).
3. BASELINE: as mesmas quantidades PERMUTADAS entre os eventos do dia.
   Formador de mercado repondo rotina tambem gera recarga; o baseline e'
   o que separa "reposicao rotineira" de "nivel defendido".
4. CUSTO da rodada (deltas lidos, MB, segundos) -- reportado junto, nao
   como etapa previa.

LIMITE CONHECIDO, declarado: a maioria dos deltas de book NAO carrega
data propria (`has_date=False`, `ts_ns=0`); nesses casos o unico relogio
e' `ts_recv_ns`, o instante em que NOS recebemos. Com o processo
atrasado, isso desloca tudo junto -- para medir INTERVALOS entre eventos
proximos serve, para datar em relacao ao trade nao serve.
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

log = structlog.get_logger(__name__)
_NS = 1_000_000_000
JANELA_S = 5.0           # a oferta tem que reaparecer em ate' isto
N_MINIMO = 3             # nivel "defendido": 3 recargas no mesmo preco/tamanho
_COLS = ["ts_recv_ns", "action", "side", "price", "quantidade", "agente", "offer_id"]


def carregar_book(curated: Path, symbol: str, dia: dt.date) -> pd.DataFrame:
    pasta = curated / "book_offer" / f"dt={dia.isoformat()}"
    if not pasta.exists():
        return pd.DataFrame()
    dataset = ds.dataset(pasta, format="parquet", partitioning="hive",
                         exclude_invalid_files=True)
    cols = [c for c in _COLS if c in dataset.schema.names]
    t: pd.DataFrame = dataset.to_table(filter=ds.field("sym") == symbol,
                                       columns=cols).to_pandas()
    return t.sort_values("ts_recv_ns").reset_index(drop=True)


def _recargas(ts: np.ndarray, price: np.ndarray, qtd: np.ndarray, side: np.ndarray,
              janela_ns: int) -> np.ndarray:
    """Sequencias de ofertas do MESMO tamanho no MESMO preco e lado, cada
    uma a no maximo `janela_s` da anterior. Tamanho de cada sequencia."""
    if len(ts) == 0:
        return np.array([], dtype=np.int64)
    ordem = np.lexsort((ts, qtd, side, price))
    p, q, s, t = price[ordem], qtd[ordem], side[ordem], ts[ordem]
    nova = np.empty(len(t), dtype=bool)
    nova[0] = True
    nova[1:] = ((p[1:] != p[:-1]) | (q[1:] != q[:-1]) | (s[1:] != s[:-1])
                | ((t[1:] - t[:-1]) > janela_ns))
    return np.bincount(np.cumsum(nova) - 1)


def medir_dia(curated: Path, symbol: str, dia: dt.date, janela_s: float = JANELA_S,
              n_minimo: int = N_MINIMO, semente: int = 1) -> dict[str, Any]:
    t0 = time.monotonic()
    df = carregar_book(curated, symbol, dia)
    if df.empty:
        return {}
    segundos_leitura = round(time.monotonic() - t0, 1)
    # so' INSERCOES de oferta: e' a "recarga". Acao 0/1 = insert/update no
    # padrao da DLL; se a coluna nao existir, usa tudo (e declara).
    ins = df[df["action"].isin([0, 1])] if "action" in df else df
    ts = ins["ts_recv_ns"].to_numpy(dtype=np.int64)
    price = ins["price"].to_numpy(dtype=float)
    qtd = ins["quantidade"].to_numpy(dtype=float)
    side = ins["side"].to_numpy(dtype=np.int64)
    janela_ns = int(janela_s * _NS)
    tam = _recargas(ts, price, qtd, side, janela_ns)
    rng = np.random.default_rng(semente)
    tam_b = _recargas(ts, price, rng.permutation(qtd), side, janela_ns)

    def curva(v: np.ndarray) -> dict[str, int]:
        return {str(n): int((v >= n).sum()) for n in (3, 5, 10, 20, 50)}

    obs, base = curva(tam), curva(tam_b)
    r = {
        "dia": dia.isoformat(), "deltas": len(df), "insercoes": len(ins),
        "niveis_defendidos": int((tam >= n_minimo).sum()),
        "tamanho_p50": float(np.median(tam)) if len(tam) else None,
        "tamanho_max": int(tam.max()) if len(tam) else 0,
        "por_limiar": obs, "baseline": base,
        "razao_por_limiar": {n: round((obs[n] + 1) / (base[n] + 1), 3) for n in obs},
        "quantidade_p50_nas_recargas": (
            float(np.median(qtd)) if len(qtd) else None),
        "segundos_leitura": segundos_leitura,
        "segundos_total": round(time.monotonic() - t0, 1),
    }
    log.info("book_recomposicao.dia", **{k: v for k, v in r.items()
                                         if k not in ("por_limiar", "baseline",
                                                      "razao_por_limiar")})
    return r


def descrever(curated: Path, symbol: str, dias: list[dt.date], janela_s: float = JANELA_S,
              n_minimo: int = N_MINIMO, saida: Path | None = None) -> dict[str, Any]:
    linhas = []
    for d in dias:
        r = medir_dia(curated, symbol, d, janela_s, n_minimo)
        if r:
            linhas.append(r)
    if not linhas:
        raise SystemExit(f"nenhum dia com book_offer de {symbol} em {curated}")
    agregado = {
        "dias": len(linhas),
        "deltas_p50": float(np.median([x["deltas"] for x in linhas])),
        "niveis_defendidos_p50": float(np.median([x["niveis_defendidos"] for x in linhas])),
        "por_limiar": {
            n: {"observado_p50": float(np.median([x["por_limiar"][n] for x in linhas])),
                "baseline_p50": float(np.median([x["baseline"][n] for x in linhas])),
                "razao_p50": float(np.median([x["razao_por_limiar"][n] for x in linhas]))}
            for n in linhas[0]["por_limiar"]},
        "segundos_por_dia_p50": float(np.median([x["segundos_total"] for x in linhas])),
    }
    r = {"symbol": symbol, "janela_s": janela_s, "n_minimo": n_minimo,
         "agregado": agregado, "por_dia": linhas}
    if saida is not None:
        saida.mkdir(parents=True, exist_ok=True)
        (saida / "book_recomposicao.json").write_text(json.dumps(r, indent=2, default=str),
                                                      encoding="utf-8")
    return r
