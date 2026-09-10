"""Versao do arquivo da DLL: fora do Windows devolve None, sem excecao."""

from __future__ import annotations

from profittape.profitdll.versao import versao_arquivo


def test_fora_do_windows_devolve_none_sem_levantar(tmp_path) -> None:  # type: ignore[no-untyped-def]
    arq = tmp_path / "ProfitDLL64.dll"
    arq.write_bytes(b"nao e uma dll")
    assert versao_arquivo(arq) is None
    assert versao_arquivo(tmp_path / "inexistente.dll") is None


def test_doctor_mostra_a_linha_de_versao(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from typer.testing import CliRunner

    from profittape.cli import app

    r = CliRunner().invoke(app, ["doctor"])
    assert "dll_versao" in r.output
