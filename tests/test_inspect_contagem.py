"""
Testes da correcao do inspect (2026-08-31): contagem por metadados,
guarda de tamanho e filtro --dia. Incidente real: 8h mudo concatenando 25
pregoes em memoria quando a resposta cabia num footer.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from profittape.tools import inspect as insp


def _arvore(tmp_path: Path, dias: dict[str, int]) -> Path:
    raiz = tmp_path / "raw" / "trade"
    for dt, n in dias.items():
        pasta = raiz / f"dt={dt}" / "sym=WINFUT"
        pasta.mkdir(parents=True)
        df = pd.DataFrame({"ts_ns": range(1, n + 1), "ts_recv_ns": range(1, n + 1),
                           "symbol": ["WINFUT"] * n, "trade_id": range(n),
                           "price": [100.0] * n})
        df.to_parquet(pasta / "part-0000.parquet", index=False)
        (pasta / "sobra.parquet.inprogress").write_bytes(b"PAR1lixo")
    return tmp_path / "raw"


def test_contagem_por_dia_le_so_metadados(tmp_path: Path) -> None:
    raiz = _arvore(tmp_path, {"2026-08-10": 7, "2026-08-11": 12})
    linhas = insp.contar_por_dia(raiz / "trade")
    assert [r["dt"] for r in linhas] == ["2026-08-10", "2026-08-11"]
    assert [r["linhas"] for r in linhas] == [7, 12]
    assert all(r["arquivos"] == 1 for r in linhas)   # .inprogress ignorado


def test_contagem_marca_arquivo_sem_footer(tmp_path: Path) -> None:
    raiz = _arvore(tmp_path, {"2026-08-10": 3})
    podre = raiz / "trade" / "dt=2026-08-10" / "sym=WINFUT" / "part-0001.parquet"
    podre.write_bytes(b"PAR1" + b"\0" * 40)
    r = insp.contar_por_dia(raiz / "trade")[0]
    assert r["arquivos"] == 2 and r["ilegiveis"] == 1 and r["linhas"] == 3


def test_so_contagem_nao_carrega_dado(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    raiz = _arvore(tmp_path, {"2026-08-10": 5})
    insp.resumir(raiz, "trade", so_contagem=True)
    out = capsys.readouterr().out
    assert "CONTAGEM POR DIA" in out
    assert "AUDITORIA" not in out


def test_guarda_de_tamanho_para_sem_carregar(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    raiz = _arvore(tmp_path, {"2026-08-10": 50, "2026-08-11": 50})
    monkeypatch.setattr(insp, "LIMITE_LINHAS_SEM_CONFIRMACAO", 60)
    insp.resumir(raiz, "trade")
    out = capsys.readouterr().out
    assert "auditoria completa carrega TUDO" in out
    assert "AUDITORIA" not in out           # parou antes de carregar
    insp.resumir(raiz, "trade", completo=True)
    assert "AUDITORIA" in capsys.readouterr().out


def test_dia_filtra_e_auditoria_completa_roda(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    raiz = _arvore(tmp_path, {"2026-08-10": 5, "2026-08-11": 9})
    insp.resumir(raiz, "trade", dia="2026-08-11")
    out = capsys.readouterr().out
    assert "linhas            : 9" in out
    assert "[1/1]" in out                    # progresso no loop que era mudo


def test_dia_inexistente_falha_claro(tmp_path: Path) -> None:
    raiz = _arvore(tmp_path, {"2026-08-10": 5})
    with pytest.raises(SystemExit, match="dt=2026-01-01"):
        insp.resumir(raiz, "trade", dia="2026-01-01")
