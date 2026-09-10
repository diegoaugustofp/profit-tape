"""E2: comando ea-ordem-teste. Contra FakeProfitDLL -- sem DLL real."""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from profittape.cli import app
from profittape.testing.fake_dll import FakeProfitDLL

runner = CliRunner()


@pytest.fixture(autouse=True)
def _env_roteamento(monkeypatch):
    monkeypatch.setenv("ROTEAMENTO_SENHA_ROTEAMENTO", "s3nh4")
    monkeypatch.setenv("ROTEAMENTO_ID_ACCOUNT_DEMO", "DEMO123")
    monkeypatch.setenv("ROTEAMENTO_ID_CORRETORA_DEMO", "32006")


def _config(caminho) -> None:
    caminho.write_text("""
ativos:
  - ticker: WINFUT
    bolsa: F
    trades: true
storage:
  raiz: /tmp/raw_teste
runtime:
  tz_offset_horas: -3
""")


def test_envia_compra_e_zera_em_demo(tmp_path, monkeypatch):
    cfg = tmp_path / "r.yaml"
    _config(cfg)
    fake = FakeProfitDLL(eventos_por_ativo=0, atraso_login_s=0.05,
                         contas=((32006, "SIMULADOR", "DEMO123"),))

    import profittape.cli as cli_mod
    monkeypatch.setattr(cli_mod, "Credenciais",
                        lambda: type("C", (), {"dll_path": "x", "activation_key": "k",
                                                "user": "u", "password": "p"})())

    from profittape.profitdll.client import ProfitClient as _Original

    def _client_fake(*a, **k):
        k["dll"] = fake
        return _Original(*a, **k)

    monkeypatch.setattr("profittape.profitdll.client.ProfitClient", _client_fake)

    r = runner.invoke(app, ["ea-ordem-teste", "-c", str(cfg), "--timeout", "3"])
    assert r.exit_code == 0, r.output
    assert "enviada=True" in r.output
    assert r.output.count("enviada=True") == 2   # compra + zeragem


def test_recusa_conta_real_sem_confirmacao(tmp_path, monkeypatch):
    cfg = tmp_path / "r.yaml"
    _config(cfg)
    r = runner.invoke(app, ["ea-ordem-teste", "-c", str(cfg), "--usar-conta-real"],
                      input="n\n")
    assert r.exit_code == 1
    assert "Conectando" not in r.output   # nunca chegou a tentar conectar
