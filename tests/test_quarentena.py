"""
Testes de tools/quarentena.py — o filtro de data (--desde/--ate/--dia) e a
retrocompatibilidade (sem filtro = varre tudo, comportamento de sempre).
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from profittape.tools.quarentena import _dt_de, varrer


def _criar_parquet_valido(caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tabela = pa.table({"x": [1, 2, 3]})
    pq.write_table(tabela, caminho)


def _arvore_de_3_dias(tmp_path: Path) -> Path:
    raiz = tmp_path / "raw"
    for dia in ["2026-08-24", "2026-08-25", "2026-08-26"]:
        _criar_parquet_valido(raiz / "trade" / f"dt={dia}" / "sym=WINFUT" / "part-0000.parquet")
    return raiz


def test_dt_de_extrai_a_data_do_caminho() -> None:
    p = Path("data/raw/trade/dt=2026-08-26/sym=WINFUT/part-0000.parquet")
    assert _dt_de(p) == "2026-08-26"


def test_dt_de_sem_componente_dt_devolve_none() -> None:
    p = Path("data/raw/qualquer/coisa.parquet")
    assert _dt_de(p) is None


def test_sem_filtro_varre_todos_os_dias_comportamento_de_sempre(tmp_path, capsys) -> None:
    """Retrocompatibilidade: omitir desde/ate tem que continuar varrendo
    TUDO, igual sempre foi -- nenhum uso existente muda."""
    raiz = _arvore_de_3_dias(tmp_path)
    varrer(raiz)
    saida = capsys.readouterr().out
    assert "Varrendo 3 de 3 arquivo(s)" in saida


def test_filtro_dia_unico_restringe_a_um_dia(tmp_path, capsys) -> None:
    raiz = _arvore_de_3_dias(tmp_path)
    varrer(raiz, desde="2026-08-25", ate="2026-08-25")
    saida = capsys.readouterr().out
    assert "Varrendo 1 de 3 arquivo(s)" in saida


def test_filtro_intervalo_desde_ate(tmp_path, capsys) -> None:
    raiz = _arvore_de_3_dias(tmp_path)
    varrer(raiz, desde="2026-08-25", ate="2026-08-26")
    saida = capsys.readouterr().out
    assert "Varrendo 2 de 3 arquivo(s)" in saida


def test_filtro_so_desde_aberto_no_fim(tmp_path, capsys) -> None:
    raiz = _arvore_de_3_dias(tmp_path)
    varrer(raiz, desde="2026-08-25")
    saida = capsys.readouterr().out
    assert "Varrendo 2 de 3 arquivo(s)" in saida   # 25 e 26, nao 24


def test_arquivo_sem_dt_sempre_incluido_mesmo_com_filtro_ativo(tmp_path, capsys) -> None:
    raiz = _arvore_de_3_dias(tmp_path)
    _criar_parquet_valido(raiz / "solto_sem_particao.parquet")   # sem dt=
    varrer(raiz, desde="2026-08-26", ate="2026-08-26")
    saida = capsys.readouterr().out
    # 1 do dia filtrado + 1 sem dt= (sempre incluido) = 2, de um total de 4
    assert "Varrendo 2 de 4 arquivo(s)" in saida
