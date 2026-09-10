"""
GetHistoryTrades exige data COM hora (DLL 4.0.0.41, medido 2026-09-10).

So' data -> a DLL aceita (retorno 0), progresso 0 -> 100 na hora, ZERO
negocios. Foi o "backfill quebrado" de setembro. A fake reproduz isso;
os testes garantem que o client sempre manda hora e que o backfill
espera o progresso 100 antes de decidir que nada veio.
"""

from __future__ import annotations

import time

from profittape.pipeline.bus import EventBus
from profittape.profitdll.client import (
    HORA_FIM_PREGAO,
    HORA_INICIO_PREGAO,
    ProfitClient,
    _com_hora,
)
from profittape.testing.fake_dll import FakeProfitDLL


def test_com_hora_acrescenta_so_quando_falta() -> None:
    assert _com_hora("31/08/2026", "09:00:00") == "31/08/2026 09:00:00"
    assert _com_hora("31/08/2026 10:15:00", "09:00:00") == "31/08/2026 10:15:00"
    assert _com_hora(" 31/08/2026 ", "18:35:00") == "31/08/2026 18:35:00"


def test_request_history_manda_hora_e_recebe_progresso_100() -> None:
    fake = FakeProfitDLL(eventos_por_ativo=30, com_login_completo=False)
    chamadas: list[tuple[str, str, str, str]] = []
    original = fake.GetHistoryTrades

    def espiao(ticker: str, bolsa: str, ini: str, fim: str) -> int:
        chamadas.append((ticker, bolsa, ini, fim))
        return original(ticker, bolsa, ini, fim)

    fake.GetHistoryTrades = espiao  # type: ignore[method-assign]
    bus = EventBus()
    c = ProfitClient(dll_path="x", activation_key="k", user="u", password="p",
                     bus=bus, dll=fake)  # type: ignore[arg-type]
    c.connect(timeout_s=5)
    try:
        c.request_history("WINFUT", "31/08/2026", "31/08/2026", "F")
        assert chamadas == [("WINFUT", "F", f"31/08/2026 {HORA_INICIO_PREGAO}",
                             f"31/08/2026 {HORA_FIM_PREGAO}")]
        assert c.historico_100.wait(5), "progresso 100 nao chegou"
        assert c.progresso_historico["WINFUT"] == 100
        time.sleep(0.2)
        assert bus.stats().total_recebido == 30
    finally:
        c.disconnect()


def test_fake_reproduz_so_data_como_janela_vazia() -> None:
    """A fake precisa falhar do jeito que a DLL falha, senao o teste do
    backfill nao prova nada."""
    fake = FakeProfitDLL(eventos_por_ativo=30, com_login_completo=False)
    bus = EventBus()
    c = ProfitClient(dll_path="x", activation_key="k", user="u", password="p",
                     bus=bus, dll=fake)  # type: ignore[arg-type]
    c.connect(timeout_s=5)
    try:
        c.historico_100.clear()
        assert fake.GetHistoryTrades("WINFUT", "F", "31/08/2026", "31/08/2026") == 0
        assert c.historico_100.wait(2)
        time.sleep(0.2)
        assert bus.stats().total_recebido == 0          # aceito, vazio
    finally:
        c.disconnect()
