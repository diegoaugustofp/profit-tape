"""Cache das barras derivadas do tape (2026-09-28).

Em 28/09 o EA real subiu 09:21 -- 21 min depois da abertura -- porque
semente e perfil reconstruiam 10 pregoes do tape a CADA arranque, o
perfil lia cada dia DUAS vezes, e havia tres EAs no ar. O primeiro sinal
saiu 10 min atrasado e a ordem stop virou ordem a mercado: 455 pts.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from profittape.ea import cache_barras as cb

NS = 1_000_000_000


def _dia_no_curated(curated: Path, dia: dt.date, n: int = 30, symbol: str = "WINFUT") -> None:
    pasta = curated / "trade" / f"dt={dia.isoformat()}" / f"sym={symbol}"
    pasta.mkdir(parents=True, exist_ok=True)
    t0 = int(pd.Timestamp(f"{dia} 12:00", tz="UTC").value)
    tab = pa.table({"ts_ns": [t0 + i * 60 * NS for i in range(n)],
                    "symbol": [symbol] * n, "trade_id": list(range(n)),
                    "price": [140000.0 + i * 5 for i in range(n)],
                    "quantidade": [10] * n, "trade_type": [2] * n,
                    "agente_comprador": [1] * n, "agente_vendedor": [2] * n,
                    "is_edit": [False] * n, "ts_recv_ns": [t0 + i * 60 * NS for i in range(n)],
                    "volume_financeiro": [0.0] * n})
    pq.write_table(tab, pasta / "parte-0.parquet")


@pytest.fixture(autouse=True)
def _limpo() -> None:
    cb.limpar_memoria()


def test_segunda_chamada_nao_reconstroi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dia = dt.date(2026, 9, 25)
    curated = tmp_path / "curated"
    _dia_no_curated(curated, dia)
    n = {"construiu": 0}
    real = cb._construir

    def contando(*a: object, **k: object) -> list:
        n["construiu"] += 1
        return real(*a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(cb, "_construir", contando)
    a = cb.barras_do_dia(curated, "WINFUT", dia, 900)
    cb.limpar_memoria()                       # forca passar pelo cache em DISCO
    b = cb.barras_do_dia(curated, "WINFUT", dia, 900)
    assert a == b and a != []
    assert n["construiu"] == 1                # a segunda veio do cache


def test_dia_RECURADO_invalida_o_cache(tmp_path: Path) -> None:
    """O caso real de 18/09: o backfill acrescentou 212 mil negocios ao dia
    depois de ele ja' ter sido lido."""
    dia = dt.date(2026, 9, 18)
    curated = tmp_path / "curated"
    _dia_no_curated(curated, dia, n=10)
    antes = cb.barras_do_dia(curated, "WINFUT", dia, 900)
    cb.limpar_memoria()
    _dia_no_curated(curated, dia, n=40)       # backfill: o dia mudou
    depois = cb.barras_do_dia(curated, "WINFUT", dia, 900)
    assert depois != antes
    assert cb.assinatura(curated, "WINFUT", dia) == (1, 40)


def test_dia_sem_tape_devolve_vazio_sem_criar_cache(tmp_path: Path) -> None:
    curated = tmp_path / "curated"
    assert cb.barras_do_dia(curated, "WINFUT", dt.date(2026, 9, 25), 900) == []
    assert not (tmp_path / "cache").exists()


def test_cache_que_nao_grava_nao_quebra_o_EA(tmp_path: Path,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    dia = dt.date(2026, 9, 25)
    curated = tmp_path / "curated"
    _dia_no_curated(curated, dia)

    def recusa(*a: object, **k: object) -> None:
        raise OSError("disco cheio")

    monkeypatch.setattr(Path, "write_text", recusa)
    assert cb.barras_do_dia(curated, "WINFUT", dia, 900) != []


def test_semente_e_perfil_compartilham_a_MESMA_reconstrucao(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Antes, cada um reconstruia o dia por conta propria."""
    from profittape.ea import perfil_volume as pv
    from profittape.ea import semente as sm

    dia = dt.date(2026, 9, 25)
    curated = tmp_path / "curated"
    _dia_no_curated(curated, dia)
    n = {"construiu": 0}
    real = cb._construir

    def contando(*a: object, **k: object) -> list:
        n["construiu"] += 1
        return real(*a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(cb, "_construir", contando)
    sm._barras_do_tape(curated, "WINFUT", dia, 900)
    pv.barras_do_dia(curated, "WINFUT", dia, 900)
    assert n["construiu"] == 1
