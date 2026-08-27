from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest
import structlog

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture
def tmp_raiz(tmp_path: Path) -> Path:
    d = tmp_path / "raw"
    d.mkdir()
    return d


@pytest.fixture(autouse=True)
def _isolar_estado_global_de_logging():
    """
    Rede de seguranca GLOBAL (2026-08-27): qualquer teste que chame
    logging_setup.configurar() (direto, ou indireto via CliRunner
    invocando um comando do CLI) muda o estado GLOBAL do structlog —
    structlog.configure() nao e' por teste, e' por PROCESSO inteiro.
    Sem reset, um teste que deixa isso configurado polui QUALQUER teste
    que rode depois no mesmo processo de pytest e espere o comportamento
    padrao nao-configurado do structlog (ex.: capturar log via capsys).

    Achado na pratica (2026-08-27): um teste pre-existente
    (test_schema_writer.py::test_quarentena_loga_progresso_...) ja
    chamava configurar() sem limpeza havia dias -- so' nao tinha sido
    pego porque a ordem de colecao do pytest nunca tinha exposto o
    problema antes. Em vez de remendar teste por teste (facil de
    esquecer em testes futuros), fechado aqui de uma vez: TODO teste
    ganha reset automatico, precisa ou nao de configurar() diretamente.
    """
    handlers_antes = list(logging.getLogger().handlers)
    nivel_antes = logging.getLogger().level
    yield
    structlog.reset_defaults()
    logging.getLogger().handlers[:] = handlers_antes
    logging.getLogger().setLevel(nivel_antes)
