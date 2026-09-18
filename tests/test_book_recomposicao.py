"""Recomposicao no livro, passo 1: nivel defendido x reposicao rotineira."""

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


def _escrever(curated: Path, dia: dt.date, df: pd.DataFrame, sym: str = "WINFUT") -> None:
    d = curated / "book_offer" / f"dt={dia.isoformat()}" / f"sym={sym}"
    d.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), d / "part-0000.parquet")


def _livro(n: int, seed: int, com_defesa: bool, dia: dt.date) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    t0 = int(pd.Timestamp(f"{dia} 12:00:00", tz="UTC").value)
    ts = np.sort(rng.integers(t0, t0 + 6 * 3600 * NS, n))
    price = 140000.0 + rng.integers(-40, 40, n) * 5.0
    qtd = rng.choice([1, 2, 3, 5, 10, 20], n).astype(float)
    df = pd.DataFrame({"ts_recv_ns": ts, "action": 0, "side": rng.integers(0, 2, n),
                       "price": price, "quantidade": qtd,
                       "agente": rng.integers(1, 40, n), "offer_id": np.arange(n)})
    if com_defesa:
        extras = []
        for k in range(5):                       # 5 niveis defendidos
            nivel = 140000.0 + (k - 2) * 25.0
            base = t0 + (k + 1) * 600 * NS
            for j in range(40):                  # 40 recargas de 137 lotes
                extras.append({"ts_recv_ns": base + j * 2 * NS, "action": 0, "side": 0,
                               "price": nivel, "quantidade": 137.0, "agente": 7,
                               "offer_id": 10_000_000 + k * 100 + j})
        df = pd.concat([df, pd.DataFrame(extras)], ignore_index=True)
    return df.sort_values("ts_recv_ns").reset_index(drop=True)


def test_sem_defesa_a_curva_fica_perto_do_acaso(tmp_path: Path) -> None:
    dia = dt.date(2026, 9, 10)
    _escrever(tmp_path, dia, _livro(60_000, 1, False, dia))
    r = br.medir_dia(tmp_path, "WINFUT", dia)
    for n, razao in r["razao_por_limiar"].items():
        assert 0.3 < razao < 3.0, (n, razao)


def test_nivel_defendido_aparece_na_cauda(tmp_path: Path) -> None:
    dia = dt.date(2026, 9, 11)
    _escrever(tmp_path, dia, _livro(60_000, 2, True, dia))
    r = br.medir_dia(tmp_path, "WINFUT", dia)
    assert r["por_limiar"]["20"] >= 5
    assert r["razao_por_limiar"]["20"] > 2.0, r["razao_por_limiar"]
    assert r["tamanho_max"] >= 40


def test_recargas_respeitam_janela_preco_e_lado() -> None:
    ts = np.array([0, 2 * NS, 100 * NS], dtype=np.int64)
    price = np.array([100.0, 100.0, 100.0])
    qtd = np.array([5.0, 5.0, 5.0])
    side = np.array([0, 0, 0], dtype=np.int64)
    assert br._recargas(ts, price, qtd, side, 5 * NS).tolist() == [2, 1]
    # lado diferente nao e' a mesma fila
    assert br._recargas(ts[:2], price[:2], qtd[:2], np.array([0, 1]), 5 * NS).tolist() == [1, 1]


def test_agregado_custo_e_saida(tmp_path: Path) -> None:
    dia = dt.date(2026, 9, 14)
    _escrever(tmp_path, dia, _livro(20_000, 3, True, dia))
    r = br.descrever(tmp_path, "WINFUT", [dia], saida=tmp_path / "s")
    assert (tmp_path / "s" / "book_recomposicao.json").exists()
    a = r["agregado"]
    assert a["dias"] == 1 and a["deltas_p50"] > 0
    assert "segundos_por_dia_p50" in a           # custo reportado JUNTO
    assert a["por_limiar"]["20"]["observado_p50"] >= 5


def test_sem_book_recusa(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="nenhum dia"):
        br.descrever(tmp_path, "WINFUT", [dt.date(2026, 9, 10)])
