"""Testes do comando `alertas-testar` via CliRunner (typer/click)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from profittape.cli import app

runner = CliRunner()


def test_alertas_testar_sem_config_falha_com_mensagem_clara(tmp_path: Path) -> None:
    resultado = runner.invoke(app, ["alertas-testar", "--alertas",
                                    str(tmp_path / "nao_existe.yaml")])
    assert resultado.exit_code == 1
    assert "SEM CONFIG" in resultado.stdout


def test_alertas_testar_com_config_chama_enviar(tmp_path: Path) -> None:
    """Com config valida, o comando tenta enviar — mockado para nao bater
    na rede de verdade num teste automatizado."""
    p = tmp_path / "alertas.yaml"
    p.write_text('telegram:\n  bot_token: "123:ABC"\n  chat_id: "999"\n',
                encoding="utf-8")

    with patch("profittape.alertas.enviar", return_value=True) as mock_enviar:
        resultado = runner.invoke(app, ["alertas-testar", "--alertas", str(p)])
    assert resultado.exit_code == 0
    assert "Enviado" in resultado.stdout
    assert mock_enviar.called


def test_alertas_testar_envio_falho_reporta_erro(tmp_path: Path) -> None:
    p = tmp_path / "alertas.yaml"
    p.write_text('telegram:\n  bot_token: "123:ABC"\n  chat_id: "999"\n',
                encoding="utf-8")

    with patch("profittape.alertas.enviar", return_value=False):
        resultado = runner.invoke(app, ["alertas-testar", "--alertas", str(p)])
    assert resultado.exit_code == 1
    assert "FALHOU" in resultado.stdout
