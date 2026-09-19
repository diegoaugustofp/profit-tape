"""Recomposicao no livro v2: nivel defendido x reposicao rotineira.

A v1 foi refeita SEM nunca ter sido interpretada -- tres defeitos de
validez: usava preco de eventos onde o manual da DLL nao o garante, nao
exigia a mesma ordem nem o mesmo agente (cadeia maxima de 63.508: lote 1
no preco mais negociado), e lia o raw sem deduplicar.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from profittape.research import book_recomposicao as br

NS = 1_000_000_000
ADD, DELETE = 0, 2


def _escrever(raiz: Path, dia: dt.date, df: pd.DataFrame, sym: str = "WINFUT") -> None:
    d = raiz / "book_offer" / f"dt={dia.isoformat()}" / f"sym={sym}"
    d.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), d / "part-0000.parquet")


def _ev(ts: int, acao: int, oid: int, preco: float, qtd: int, agente: int,
        side: int = 0) -> dict:
    # DELETE com preco/qtd ZERADOS de proposito: o manual diz que fora de
    # atAdd os campos escalares nao sao garantidos. Se o detector usar
    # esses campos em vez do estado por offer_id, o teste quebra.
    if acao == DELETE:
        preco, qtd, agente = 0.0, 0, 0
    return {"ts_recv_ns": ts, "action": acao, "side": side, "price": preco,
            "quantidade": qtd, "agente": agente, "offer_id": oid}


def test_saida_resolve_o_nivel_pelo_offer_id_nao_pelos_campos() -> None:
    """DELETE vem com preco 0; o nivel tem que sair do ADD daquele id."""
    df = pd.DataFrame([_ev(0, ADD, 1, 140000.0, 50, 7), _ev(NS, DELETE, 1, 0, 0, 0)])
    ev = br.eventos_de_nivel(df)
    saida = ev[~ev["entrada"]].iloc[0]
    assert saida["price"] == 140000.0 and saida["quantidade"] == 50 and saida["agente"] == 7


def test_recarga_exige_mesmo_agente() -> None:
    base = [_ev(0, ADD, 1, 140000.0, 50, 7), _ev(NS, DELETE, 1, 0, 0, 0)]
    mesmo = pd.DataFrame([*base, _ev(2 * NS, ADD, 2, 140000.0, 50, 7)])
    outro = pd.DataFrame([*base, _ev(2 * NS, ADD, 2, 140000.0, 50, 9)])
    assert br._cadeias(br.eventos_de_nivel(mesmo), 5 * NS).sum() == 1
    assert br._cadeias(br.eventos_de_nivel(outro), 5 * NS).sum() == 0


def test_recarga_respeita_a_janela() -> None:
    dentro = pd.DataFrame([_ev(0, ADD, 1, 140000.0, 50, 7), _ev(NS, DELETE, 1, 0, 0, 0),
                           _ev(2 * NS, ADD, 2, 140000.0, 50, 7)])
    fora = pd.DataFrame([_ev(0, ADD, 1, 140000.0, 50, 7), _ev(NS, DELETE, 1, 0, 0, 0),
                         _ev(60 * NS, ADD, 2, 140000.0, 50, 7)])
    assert br._cadeias(br.eventos_de_nivel(dentro), 5 * NS).sum() == 1
    assert br._cadeias(br.eventos_de_nivel(fora), 5 * NS).sum() == 0


def test_cadeia_conta_recargas_seguidas() -> None:
    linhas = [_ev(0, ADD, 0, 140000.0, 50, 7)]
    for k in range(6):                       # 6 ciclos: sai e volta
        linhas.append(_ev((2 * k + 1) * NS, DELETE, k, 0, 0, 0))
        linhas.append(_ev((2 * k + 2) * NS, ADD, k + 1, 140000.0, 50, 7))
    tam = br._cadeias(br.eventos_de_nivel(pd.DataFrame(linhas)), 5 * NS)
    assert tam.max() >= 5


def test_duplicatas_sao_removidas_na_leitura(tmp_path: Path) -> None:
    dia = dt.date(2026, 9, 10)
    linhas = [_ev(0, ADD, 1, 140000.0, 50, 7)] * 3 + [_ev(NS, DELETE, 1, 0, 0, 0)]
    _escrever(tmp_path, dia, pd.DataFrame(linhas))
    df, dups = br.carregar_book(tmp_path, "WINFUT", dia)
    assert dups == 2 and len(df) == 2


def test_nivel_defendido_aparece_contra_o_baseline(tmp_path: Path) -> None:
    """Fluxo com muita oferta normal (agentes e tamanhos variados) e CINCO
    niveis defendidos pelo mesmo agente com tamanho fixo."""
    dia = dt.date(2026, 9, 11)
    rng = np.random.default_rng(3)
    n = 40_000
    t0 = int(pd.Timestamp(f"{dia} 12:00:00", tz="UTC").value)
    linhas = []
    for i in range(n):
        ts = t0 + i * 10_000_000
        oid = i
        linhas.append(_ev(ts, ADD, oid, 140000.0 + rng.integers(-40, 40) * 5.0,
                          int(rng.choice([1, 2, 5, 10])), int(rng.integers(1, 40))))
        if i % 2 == 0:
            linhas.append(_ev(ts + 5_000_000, DELETE, oid, 0, 0, 0))
    oid = 10_000_000
    for k in range(5):
        nivel = 140000.0 + (k - 2) * 25.0
        base = t0 + (k + 1) * 60 * NS
        linhas.append(_ev(base, ADD, oid, nivel, 137, 7))
        for j in range(30):
            linhas.append(_ev(base + (2 * j + 1) * NS, DELETE, oid, 0, 0, 0))
            oid += 1
            linhas.append(_ev(base + (2 * j + 2) * NS, ADD, oid, nivel, 137, 7))
    _escrever(tmp_path, dia, pd.DataFrame(linhas))
    r = br.medir_dia(tmp_path, "WINFUT", dia)
    assert r["cadeia_max"] >= 25
    assert r["por_limiar"]["20"] >= 5
    assert r["razao_por_limiar"]["20"] > 2.0, r["razao_por_limiar"]


def test_agregado_custo_e_saida(tmp_path: Path) -> None:
    dia = dt.date(2026, 9, 14)
    linhas = [_ev(0, ADD, 1, 140000.0, 50, 7), _ev(NS, DELETE, 1, 0, 0, 0),
              _ev(2 * NS, ADD, 2, 140000.0, 50, 7)]
    _escrever(tmp_path, dia, pd.DataFrame(linhas))
    r = br.descrever(tmp_path, "WINFUT", [dia], saida=tmp_path / "s")
    assert (tmp_path / "s" / "book_recomposicao.json").exists()
    a = r["agregado"]
    assert a["dias"] == 1 and "segundos_por_dia_p50" in a and "duplicatas_p50" in a


def test_sem_book_recusa(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="nenhum dia"):
        br.descrever(tmp_path, "WINFUT", [dt.date(2026, 9, 10)])
