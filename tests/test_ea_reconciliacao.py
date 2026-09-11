"""
E3 dentro do record (2026-09-11): ReconciliadorPosicao.

GetPositionV2 (client.consultar_posicao) NAO E' VERIFICADO contra a DLL
real -- ver profitdll/types.py. Os testes aqui provam a LOGICA de
reconciliacao (bate, diverge-e-zera, implausivel-nao-age, trava) contra
a fake, que usa a MESMA struct ctypes -- ou seja, provam auto-
consistencia, nao correspondencia com a DLL real. Isso fica registrado
no doc, nao escondido aqui.
"""

from __future__ import annotations

import time

import pytest

from profittape.ea.config import RoteamentoConfig
from profittape.ea.ordem_teste import TickerAgregadorInvalido
from profittape.ea.reconciliacao import ReconciliadorPosicao
from profittape.pipeline.bus import EventBus
from profittape.profitdll.client import ProfitClient
from profittape.testing.fake_dll import FakeProfitDLL


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROTEAMENTO_ID_CORRETORA_DEMO", "32006")
    monkeypatch.setenv("ROTEAMENTO_ID_ACCOUNT_DEMO", "DEMO-1")
    monkeypatch.setenv("ROTEAMENTO_SENHA_ROTEAMENTO", "s")


def _client(fake: FakeProfitDLL) -> ProfitClient:
    c = ProfitClient(
        dll_path="x", activation_key="k", user="u", password="p",
        bus=EventBus(), dll=fake, login_completo=True,
    )  # type: ignore[arg-type]
    c.connect(timeout_s=5)
    return c


def _rodar(r: ReconciliadorPosicao, max_s: float = 5.0) -> None:
    fim = time.monotonic() + max_s
    while not r.concluida and time.monotonic() < fim:
        r.tick()
        time.sleep(0.01)


def test_posicao_zerada_bate_com_esperado_zero() -> None:
    fake = FakeProfitDLL(eventos_por_ativo=0)
    c = _client(fake)
    try:
        r = ReconciliadorPosicao(c, RoteamentoConfig(), horario_hhmm="00:00", ticker="WINV26")
        _rodar(r)
        assert r.rel.resultado == "bate"
        assert r.rel.encontrado == 0 and r.rel.plausivel is True
        assert fake.ordens_enviadas == []          # nao zerou nada -- ja' estava zerado
    finally:
        c.disconnect()


def test_divergencia_aciona_zeragem_automatica() -> None:
    fake = FakeProfitDLL(eventos_por_ativo=0)
    fake.posicoes[(32006, "DEMO-1", "WINV26")] = (3, 2, 189370.0)  # 3 vendida
    c = _client(fake)
    try:
        r = ReconciliadorPosicao(c, RoteamentoConfig(), horario_hhmm="00:00",
                                 ticker="WINV26", esperado=0)
        _rodar(r)
        assert r.rel.resultado == "divergiu_zerado"
        assert r.rel.encontrado == -3          # vendida vira negativa
        assert [n for n, _ in fake.ordens_enviadas] == ["SendZeroPositionAtMarket"]
        assert r.rel.zeragem_status == ["ClientCreated", "ClientCreated", "HadesCreated", "Filled"]
        assert r.rel.t_zeragem_fill is not None
    finally:
        c.disconnect()


def test_encontrado_bate_com_esperado_nao_zero_e_nao_zera() -> None:
    """esperado=5 (comprada) e a corretora tambem diz 5 comprada -> bate,
    sem zerar. O E3 reconcilia contra o esperado, nao contra "sempre zero"."""
    fake = FakeProfitDLL(eventos_por_ativo=0)
    fake.posicoes[(32006, "DEMO-1", "WINV26")] = (5, 1, 189000.0)  # 5 comprada
    c = _client(fake)
    try:
        r = ReconciliadorPosicao(c, RoteamentoConfig(), horario_hhmm="00:00",
                                 ticker="WINV26", esperado=5)
        _rodar(r)
        assert r.rel.resultado == "bate" and r.rel.encontrado == 5
        assert fake.ordens_enviadas == []
    finally:
        c.disconnect()


def test_resultado_implausivel_nao_aciona_zeragem() -> None:
    """Layout de bytes suspeito (lado fora de 0/1/2) -- NUNCA agir sobre
    isto, so' alarmar e pedir conferencia manual."""
    fake = FakeProfitDLL(eventos_por_ativo=0)
    c = _client(fake)
    original = fake.GetPositionV2

    def espiao(ptr: object) -> int:
        ret = original(ptr)
        ptr.contents.open_side = 9  # type: ignore[attr-defined]
        ptr.contents.open_quantity = 10**9  # type: ignore[attr-defined]
        return ret

    fake.GetPositionV2 = espiao  # type: ignore[method-assign]
    try:
        r = ReconciliadorPosicao(c, RoteamentoConfig(), horario_hhmm="00:00", ticker="WINV26")
        _rodar(r)
        assert r.rel.resultado == "implausivel"
        assert "CONFIRA A POSICAO NO PROFIT" in r.rel.erro
        assert fake.ordens_enviadas == []
    finally:
        c.disconnect()


def test_trava_REPROVA_conta_real(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROTEAMENTO_ID_CORRETORA_DEMO", "1003")
    monkeypatch.setenv("ROTEAMENTO_ID_ACCOUNT_DEMO", "REAL-9")
    fake = FakeProfitDLL(eventos_por_ativo=0,
                         contas=((32006, "Simulador", "DEMO-1"),
                                 (1003, "XP Investimentos CCTVM S/A", "REAL-9")))
    fake.posicoes[(1003, "REAL-9", "WINV26")] = (1, 1, 189000.0)
    c = _client(fake)
    try:
        r = ReconciliadorPosicao(c, RoteamentoConfig(), horario_hhmm="00:00", ticker="WINV26")
        _rodar(r)
        assert r.rel.resultado == "trava"
        assert fake.ordens_enviadas == []
        assert fake.get_position_chamadas == []    # nem a CONSULTA acontece
    finally:
        c.disconnect()


def test_espera_o_horario() -> None:
    fake = FakeProfitDLL(eventos_por_ativo=0)
    c = _client(fake)
    try:
        relogio = {"h": "09:59"}
        r = ReconciliadorPosicao(c, RoteamentoConfig(), horario_hhmm="10:00",
                                 ticker="WINV26", relogio=lambda: relogio["h"])
        r.tick()
        r.tick()
        assert r.estado == "aguardando_horario" and fake.get_position_chamadas == []
        relogio["h"] = "10:00"
        _rodar(r)
        assert r.rel.resultado == "bate"
    finally:
        c.disconnect()


def test_ticker_agregador_bloqueia_na_construcao() -> None:
    fake = FakeProfitDLL(eventos_por_ativo=0)
    c = _client(fake)
    try:
        with pytest.raises(TickerAgregadorInvalido):
            ReconciliadorPosicao(c, RoteamentoConfig(), horario_hhmm="00:00", ticker="WINFUT")
    finally:
        c.disconnect()


def test_zeragem_recusada_nao_confirma_fill() -> None:
    fake = FakeProfitDLL(eventos_por_ativo=0, preenche_ordens=False)
    fake.posicoes[(32006, "DEMO-1", "WINV26")] = (1, 1, 189000.0)
    c = _client(fake)
    try:
        r = ReconciliadorPosicao(c, RoteamentoConfig(), horario_hhmm="00:00",
                                 ticker="WINV26", timeout_zeragem_s=0.2)
        _rodar(r)
        assert r.rel.resultado == "divergiu_zeragem_falhou"
        assert "CONFIRA A POSICAO NO PROFIT" in r.rel.erro
    finally:
        c.disconnect()


def test_record_com_reconciliacao_ponta_a_ponta(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import threading

    from profittape.config import (
        AtivoConfig,
        Credenciais,
        PipelineConfig,
        RecorderConfig,
        RuntimeConfig,
        StorageConfig,
    )
    from profittape.recorder.service import RecorderService

    cfg = RecorderConfig(
        ativos=[AtivoConfig(ticker="WINFUT", bolsa="F", trades=True)],
        storage=StorageConfig(raiz=tmp_path / "raw", max_rows_per_file=1_000_000),
        pipeline=PipelineConfig(fila_maxsize=200_000, batch_max=5_000, poll_timeout_s=0.1),
        runtime=RuntimeConfig(heartbeat_s=1.0, encerrar_em=None, login_completo=True),
    )
    cred = Credenciais(activation_key="k", user="u", password="p", dll_path="fake")
    fake = FakeProfitDLL(eventos_por_ativo=200, intervalo_s=0.0)
    fake.posicoes[(32006, "DEMO-1", "WINV26")] = (2, 2, 189000.0)
    svc = RecorderService(cfg, cred, dll_injetada=fake, reconciliar_em="00:00",
                          reconciliar_ticker="WINV26")
    t = threading.Thread(target=svc.run, daemon=True)
    t.start()
    fim = time.monotonic() + 8
    while time.monotonic() < fim and not (svc.reconciliador and svc.reconciliador.concluida):
        time.sleep(0.1)
    svc._parar.set()
    t.join(timeout=60)
    assert svc.reconciliador is not None
    assert svc.reconciliador.rel.resultado == "divergiu_zerado"
    assert svc.bus.stats().total_descartado == 0


def test_record_bloqueia_reconciliar_ticker_agregador(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from profittape.config import Credenciais, RecorderConfig
    from profittape.recorder.service import RecorderService

    yaml = tmp_path / "r.yaml"
    yaml.write_text(
        f"storage:\n  raiz: {tmp_path / 'raw'}\nativos:\n  - ticker: WINFUT\n    bolsa: F\n"
        "    trades: true\nruntime:\n  login_completo: true\n", encoding="utf-8")
    cfg = RecorderConfig.from_yaml(yaml)
    cred = Credenciais(dll_path="fake", activation_key="k", user="u", password="p")
    fake = FakeProfitDLL(eventos_por_ativo=0)
    with pytest.raises(SystemExit, match="agregador"):
        RecorderService(cfg, cred, dll_injetada=fake, reconciliar_em="10:00")


def test_record_reconciliar_exige_login_completo(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from profittape.config import Credenciais, RecorderConfig
    from profittape.recorder.service import RecorderService

    yaml = tmp_path / "r.yaml"
    yaml.write_text(
        f"storage:\n  raiz: {tmp_path / 'raw'}\nativos:\n  - ticker: WINFUT\n    bolsa: F\n"
        "    trades: true\n", encoding="utf-8")
    cfg = RecorderConfig.from_yaml(yaml)
    cred = Credenciais(dll_path="fake", activation_key="k", user="u", password="p")
    with pytest.raises(SystemExit, match="login completo"):
        RecorderService(cfg, cred, dll_injetada=FakeProfitDLL(eventos_por_ativo=0),
                        reconciliar_em="10:00", reconciliar_ticker="WINV26")
