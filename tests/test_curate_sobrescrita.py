"""Protecao contra sobrescrita destrutiva no curate (incidente de 17/09).

O record gravou no raw um RESIDUO de 1 linha do dia anterior ao subir; a
cura rodou sem `--dia`, processou o residuo e substituiu a particao de
16/09 -- 5.971.245 linhas viraram 1, em NOVE simbolos. So' houve
recuperacao porque existia backup do raw.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from profittape.tools.curate import _pode_sobrescrever


def _particao(tmp_path: Path, linhas: int, nome: str = "sym=WINFUT") -> Path:
    d = tmp_path / nome
    d.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.Table.from_pandas(pd.DataFrame({"ts_ns": range(linhas)}), preserve_index=False),
        d / "part-0000.parquet")
    return d


def test_residuo_de_uma_linha_e_recusado(tmp_path: Path) -> None:
    d = _particao(tmp_path, 100_000)
    totais: dict[str, int | float] = {}
    assert _pode_sobrescrever(d, 1, None, "2026-09-16", "WINFUT", totais) is False
    assert totais["particoes_recusadas"] == 1


def test_forcar_com_motivo_libera(tmp_path: Path) -> None:
    d = _particao(tmp_path, 1000)
    assert _pode_sobrescrever(d, 1, "recapturei so' a tarde", "2026-09-16", "WINFUT", {}) is True


def test_particao_nova_passa(tmp_path: Path) -> None:
    assert _pode_sobrescrever(tmp_path / "sym=NOVO", 10, None, "2026-09-16", "NOVO", {}) is True


def test_recura_normal_passa(tmp_path: Path) -> None:
    """Recurar o mesmo dia nao pode ser bloqueado -- a cura E' idempotente
    por desenho. So' cai abaixo de METADE."""
    d = _particao(tmp_path, 1000)
    assert _pode_sobrescrever(d, 1000, None, "2026-09-16", "WINFUT", {}) is True
    assert _pode_sobrescrever(d, 980, None, "2026-09-16", "WINFUT", {}) is True
    assert _pode_sobrescrever(d, 500, None, "2026-09-16", "WINFUT", {}) is True
    assert _pode_sobrescrever(d, 499, None, "2026-09-16", "WINFUT", {}) is False
