"""
E2b dentro do record (2026-09-14): OrdemDeTesteB -- stop / limitada /
cancelamento / OCO na simulacao.

O que precisa REPROVAR e' testado com a mesma seriedade: trava -> zero
Send*; OCO sem execucao -> cancela as duas E zera; cancelamento nao
confirmado -> zera e avisa.
"""

from __future__ import annotations

import time

import pytest

from profittape.ea.config import RoteamentoConfig
from profittape.ea.ordem_teste_b import OrdemDeTesteB, _ao_tick
from profittape.pipeline.bus import EventBus
from profittape.profitdll.client import ProfitClient
from profittape.testing.fake_dll import FakeProfitDLL


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROTEAMENTO_ID_CORRETORA_DEMO", "32006")
    monkeypatch.setenv("ROTEAMENTO_ID_ACCOUNT_DEMO", "DEMO-1")
    monkeypatch.setenv("ROTEAMENTO_SENHA_ROTEAMENTO", "s")


def _client(fake: FakeProfitDLL) -> ProfitClient:
    c = ProfitClient(dll_path="x", activation_key="k", user="u", password="p",
                     bus=EventBus(), dll=fake, login_completo=True)  # type: ignore[arg-type]
    c.connect(timeout_s=5)
    return c


def _rodar(ot: OrdemDeTesteB, max_s: float = 8.0) -> None:
    fim = time.monotonic() + max_s
    while not ot.concluida and time.monotonic() < fim:
        ot.tick()
        time.sleep(0.01)


def _nomes(fake: FakeProfitDLL) -> list[str]:
    return [n for n, _ in fake.ordens_enviadas]


def test_ao_tick() -> None:
    assert _ao_tick(140002.0) == 140000.0 and _ao_tick(140003.0) == 140005.0


def test_evento_ordem_carrega_cl_ord_id_tipo_e_stop() -> None:
    fake = FakeProfitDLL(eventos_por_ativo=0, preco_fill=141000.0)
    c = _client(fake)
    try:
        fake.SendStopBuyOrder("DEMO-1", "32006", "s", "WINV26", "F", 141350.0, 141300.0, 1)
        time.sleep(0.1)
        evs = list(c.ordens_eventos)
        assert evs and evs[-1].cl_ord_id.startswith("CL")
        assert evs[-1].tipo == "Stop" and evs[-1].stop_preco == 141300.0
    finally:
        c.disconnect()


def test_ciclo_completo_stop_cancel_oco(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeProfitDLL(eventos_por_ativo=0, preco_fill=141000.0)
    fake.fill_pendente_apos_s = 0.05          # a primeira perna de venda executa sozinha
    c = _client(fake)
    try:
        ot = OrdemDeTesteB(c, RoteamentoConfig(), horario_hhmm="00:00", ticker="WINV26",
                           longe_pts=300.0, distancia_pts=15.0, timeout_oco_s=3.0)
        _rodar(ot)
        r = ot.rel.resumo()
        assert r["resultado"] == "ok", r
        assert _nomes(fake) == [
            "SendMarketBuyOrder",
            "SendStopBuyOrder", "SendCancelOrder",
            "SendStopSellOrder", "SendSellOrder", "SendCancelOrder",
        ]
        assert r["preco_ref"] == 141000.0
        pl = r["pernas"]
        assert pl["stop_longe"]["stop"] == 141300.0 and pl["stop_longe"]["preco"] == 141350.0
        assert pl["stop_longe"]["status"][-1] == "Cancelled"
        assert pl["stop_longe"]["latencia_cancel_ms"] is not None
        assert pl["stop_venda"]["stop"] == 140985.0 and pl["limite_venda"]["preco"] == 141015.0
        assert r["perna_oco_executada"] == "stop_venda"          # a 1a venda enviada
        assert pl["limite_venda"]["status"][-1] == "Cancelled"
        # cancelamento pelo ClOrdID, senha em 4o
        cancel_args = [a for n, a in fake.ordens_enviadas if n == "SendCancelOrder"]
        assert cancel_args[0][2] == pl["stop_longe"]["cl_ord_id"] and cancel_args[0][3] == "s"
        assert "SendZeroPositionAtMarket" not in _nomes(fake)     # posicao zerou pela perna
    finally:
        c.disconnect()


def test_oco_sem_execucao_cancela_as_duas_e_zera() -> None:
    fake = FakeProfitDLL(eventos_por_ativo=0, preco_fill=141000.0)   # nenhuma pendente executa
    c = _client(fake)
    try:
        ot = OrdemDeTesteB(c, RoteamentoConfig(), horario_hhmm="00:00", ticker="WINV26",
                           timeout_oco_s=0.3)
        _rodar(ot)
        r = ot.rel.resumo()
        assert r["resultado"] == "timeout_oco", r
        nomes = _nomes(fake)
        assert nomes[-3:] == ["SendCancelOrder", "SendCancelOrder", "SendZeroPositionAtMarket"]
        assert r["pernas"]["stop_venda"]["status"][-1] == "Cancelled"
        assert r["pernas"]["limite_venda"]["status"][-1] == "Cancelled"
        assert r["pernas"]["zeragem"]["preco_medio"] == 141000.0
    finally:
        c.disconnect()


def test_trava_conta_real_zero_envios(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROTEAMENTO_ID_CORRETORA_DEMO", "1003")
    monkeypatch.setenv("ROTEAMENTO_ID_ACCOUNT_DEMO", "REAL-9")
    fake = FakeProfitDLL(eventos_por_ativo=0,
                         contas=((32006, "Simulador", "DEMO-1"), (1003, "XP", "REAL-9")))
    c = _client(fake)
    try:
        ot = OrdemDeTesteB(c, RoteamentoConfig(), horario_hhmm="00:00", ticker="WINV26")
        _rodar(ot)
        assert ot.rel.resultado == "trava" and fake.ordens_enviadas == []
    finally:
        c.disconnect()


def test_ticker_agregador_e_distancias_recusados() -> None:
    fake = FakeProfitDLL(eventos_por_ativo=0)
    c = _client(fake)
    try:
        from profittape.ea.ordem_teste import TickerAgregadorInvalido
        with pytest.raises(TickerAgregadorInvalido):
            OrdemDeTesteB(c, RoteamentoConfig(), horario_hhmm="00:00", ticker="WINFUT")
        with pytest.raises(ValueError, match="seguro"):
            OrdemDeTesteB(c, RoteamentoConfig(), horario_hhmm="00:00", ticker="WINV26",
                          longe_pts=50.0)
    finally:
        c.disconnect()


def test_stop_longe_sem_callback_zera() -> None:
    """A fake nao tem SendStopBuyOrder com callback? Simula DLL que aceita
    (id > 0) mas nunca chama o callback: o E2b nao pode ficar refem -- zera."""
    fake = FakeProfitDLL(eventos_por_ativo=0, preco_fill=141000.0)
    fake._cb_ordem_original = None

    def _stop_mudo(*args: object) -> int:
        fake.ordens_enviadas.append(("SendStopBuyOrder", args))
        return 7777
    fake.SendStopBuyOrder = _stop_mudo  # type: ignore[method-assign]
    c = _client(fake)
    try:
        ot = OrdemDeTesteB(c, RoteamentoConfig(), horario_hhmm="00:00", ticker="WINV26",
                           timeout_s=0.3)
        _rodar(ot)
        r = ot.rel.resumo()
        assert r["resultado"] == "stop_sem_callback", r
        assert _nomes(fake)[-1] == "SendZeroPositionAtMarket"
    finally:
        c.disconnect()
