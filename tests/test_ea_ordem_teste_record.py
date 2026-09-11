"""
E2 dentro do record (2026-09-11): OrdemDeTeste + trava "so' Simulador".

O que precisa REPROVAR e' testado com a mesma seriedade do que precisa
passar: conta da XP, conta nao anunciada, corretora nao pronta -- em
todos, a fake registra ZERO Send*.
"""

from __future__ import annotations

import time

import pytest

from profittape.ea.config import RoteamentoConfig
from profittape.ea.ordem_teste import OrdemDeTeste, TravaSimulacao, exigir_simulador
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
        dll_path="x",
        activation_key="k",
        user="u",
        password="p",
        bus=EventBus(),
        dll=fake,
        login_completo=True,
    )  # type: ignore[arg-type]
    c.connect(timeout_s=5)
    return c


def _rodar(ot: OrdemDeTeste, max_s: float = 5.0) -> None:
    fim = time.monotonic() + max_s
    while not ot.concluida and time.monotonic() < fim:
        ot.tick()
        time.sleep(0.01)


# ---------------------------------------------------------------------
# trava
# ---------------------------------------------------------------------
def test_trava_aceita_simulador_anunciado_pela_dll() -> None:
    fake = FakeProfitDLL(eventos_por_ativo=0, contas=((32006, "Simulador", "DEMO-1"),))
    c = _client(fake)
    try:
        exigir_simulador(c, "32006", "DEMO-1")  # nao levanta
    finally:
        c.disconnect()


def test_trava_REPROVA_conta_real_mesmo_configurada_como_demo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O .env aponta a XP como 'demo'. A DLL diz que 1003 e' 'XP Investimentos'.
    A DLL manda: nao envia."""
    monkeypatch.setenv("ROTEAMENTO_ID_CORRETORA_DEMO", "1003")
    monkeypatch.setenv("ROTEAMENTO_ID_ACCOUNT_DEMO", "REAL-9")
    fake = FakeProfitDLL(
        eventos_por_ativo=0,
        contas=((32006, "Simulador", "DEMO-1"), (1003, "XP Investimentos CCTVM S/A", "REAL-9")),
    )
    c = _client(fake)
    try:
        with pytest.raises(TravaSimulacao, match="nao e' o Simulador"):
            exigir_simulador(c, "1003", "REAL-9")
        ot = OrdemDeTeste(c, RoteamentoConfig(), horario_hhmm="00:00")
        _rodar(ot)
        assert ot.rel.resultado == "trava"
        assert fake.ordens_enviadas == []  # ZERO chamadas de ordem
    finally:
        c.disconnect()


def test_trava_REPROVA_conta_nao_anunciada() -> None:
    fake = FakeProfitDLL(eventos_por_ativo=0, contas=((32006, "Simulador", "OUTRA"),))
    c = _client(fake)
    try:
        with pytest.raises(TravaSimulacao, match="nao foi anunciada"):
            exigir_simulador(c, "32006", "DEMO-1")
    finally:
        c.disconnect()


# ---------------------------------------------------------------------
# fluxo
# ---------------------------------------------------------------------
def test_fluxo_completo_compra_fill_zeragem_fill() -> None:
    fake = FakeProfitDLL(eventos_por_ativo=0, preco_fill=141000.0)
    c = _client(fake)
    try:
        ot = OrdemDeTeste(c, RoteamentoConfig(), horario_hhmm="00:00")
        _rodar(ot)
        r = ot.rel.resumo()
        assert r["resultado"] == "ok", r
        assert [n for n, _ in fake.ordens_enviadas] == [
            "SendMarketBuyOrder",
            "SendZeroPositionAtMarket",
        ]
        assert r["status_compra"] == ["Accepted", "Filled"]
        assert r["status_zeragem"] == ["Accepted", "Filled"]
        assert r["preco_medio_compra"] == 141000.0
        assert r["latencia_primeiro_callback_ms"] is not None
        assert r["latencia_fill_compra_ms"] >= r["latencia_primeiro_callback_ms"]
        # argumentos: conta, corretora, senha, ticker, bolsa, qtd (compra)
        assert fake.ordens_enviadas[0][1] == ("DEMO-1", "32006", "s", "WINFUT", "F", 1)
        # zeragem: senha em 5o lugar
        assert fake.ordens_enviadas[1][1] == ("DEMO-1", "32006", "WINFUT", "F", "s")
    finally:
        c.disconnect()


def test_espera_o_horario() -> None:
    fake = FakeProfitDLL(eventos_por_ativo=0)
    c = _client(fake)
    try:
        relogio = {"h": "09:59"}
        ot = OrdemDeTeste(c, RoteamentoConfig(), horario_hhmm="10:00", relogio=lambda: relogio["h"])
        ot.tick()
        ot.tick()
        assert ot.estado == "aguardando_horario" and fake.ordens_enviadas == []
        relogio["h"] = "10:00"
        _rodar(ot)
        assert ot.rel.resultado == "ok"
    finally:
        c.disconnect()


def test_fill_nao_confirmado_zera_mesmo_assim_e_marca_timeout() -> None:
    fake = FakeProfitDLL(eventos_por_ativo=0, preenche_ordens=False)
    c = _client(fake)
    try:
        ot = OrdemDeTeste(c, RoteamentoConfig(), horario_hhmm="00:00", timeout_fill_s=0.1)
        _rodar(ot)
        assert ot.rel.resultado == "timeout_fill"
        assert [n for n, _ in fake.ordens_enviadas] == [
            "SendMarketBuyOrder",
            "SendZeroPositionAtMarket",
        ]
        assert "CONFIRA A POSICAO" in ot.rel.erro
    finally:
        c.disconnect()


def test_corretora_nao_pronta_no_instante_nao_envia() -> None:
    fake = FakeProfitDLL(eventos_por_ativo=0)
    c = _client(fake)
    try:
        ot = OrdemDeTeste(c, RoteamentoConfig(), horario_hhmm="00:00")
        c.roteamento_estado = 2  # caiu (evento real de 09/09)
        _rodar(ot)
        assert ot.rel.resultado == "trava" and "pronta" in ot.rel.erro
        assert fake.ordens_enviadas == []
    finally:
        c.disconnect()


def test_e2_e_um_contrato() -> None:
    fake = FakeProfitDLL(eventos_por_ativo=0)
    c = _client(fake)
    try:
        with pytest.raises(ValueError, match="UM contrato"):
            OrdemDeTeste(c, RoteamentoConfig(), horario_hhmm="00:00", quantidade=3)
    finally:
        c.disconnect()


def test_record_exige_login_completo_para_ordem_teste(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from profittape.config import Credenciais, RecorderConfig
    from profittape.recorder.service import RecorderService

    yaml = tmp_path / "r.yaml"
    yaml.write_text(
        f"storage:\n  raiz: {tmp_path / 'raw'}\nativos:\n  - ticker: WINFUT\n    bolsa: F\n"
        "    trades: true\n",
        encoding="utf-8",
    )
    cfg = RecorderConfig.from_yaml(yaml)
    cred = Credenciais(dll_path="x", activation_key="k", user="u", password="p")
    with pytest.raises(SystemExit, match="login completo"):
        RecorderService(
            cfg, cred, dll_injetada=FakeProfitDLL(eventos_por_ativo=0), ordem_teste_em="10:00"
        )


def test_record_com_ordem_teste_envia_na_conexao_de_captura(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Ponta a ponta: o record sobe com login completo, a captura corre, e
    no laco de monitoramento (thread principal) a ordem de teste vai e
    volta -- sem parar a captura. E' o E2 como vai rodar no pregao."""
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
    svc = RecorderService(cfg, cred, dll_injetada=fake, ordem_teste_em="00:00")
    t = threading.Thread(target=svc.run, daemon=True)
    t.start()
    fim = time.monotonic() + 8
    while time.monotonic() < fim and not (svc.ordem_teste and svc.ordem_teste.concluida):
        time.sleep(0.1)
    svc._parar.set()
    t.join(timeout=60)
    assert svc.ordem_teste is not None and svc.ordem_teste.rel.resultado == "ok"
    assert [n for n, _ in fake.ordens_enviadas] == [
        "SendMarketBuyOrder",
        "SendZeroPositionAtMarket",
    ]
    assert svc.bus.stats().total_descartado == 0  # a captura nao sofreu


def test_record_avisa_quando_ordem_teste_usa_ticker_generico(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """WINFUT resolve dado mas nao e' negociavel -- o record precisa avisar
    isso na hora de agendar, nao so' deixar a ordem falhar (2026-09-11:
    'Ordem invalida' porque o E2 usava WINFUT por default)."""
    import structlog

    from profittape.config import Credenciais, RecorderConfig
    from profittape.recorder.service import RecorderService

    yaml = tmp_path / "r.yaml"
    yaml.write_text(
        f"storage:\n  raiz: {tmp_path / 'raw'}\nativos:\n  - ticker: WINFUT\n    bolsa: F\n"
        "    trades: true\nruntime:\n  login_completo: true\n",
        encoding="utf-8",
    )
    cfg = RecorderConfig.from_yaml(yaml)
    cred = Credenciais(dll_path="fake", activation_key="k", user="u", password="p")
    fake = FakeProfitDLL(eventos_por_ativo=0)

    with structlog.testing.capture_logs() as eventos:
        svc = RecorderService(
            cfg, cred, dll_injetada=fake, ordem_teste_em="10:00", ordem_teste_ticker="WINFUT"
        )
    assert svc.ordem_teste is not None and svc.ordem_teste._ticker == "WINFUT"
    assert any(e.get("event") == "recorder.ordem_teste_ticker_generico" for e in eventos)


def test_ordem_teste_aceita_ticker_especifico() -> None:
    fake = FakeProfitDLL(eventos_por_ativo=0)
    c = _client(fake)
    try:
        ot = OrdemDeTeste(c, RoteamentoConfig(), horario_hhmm="00:00", ticker="WINV26")
        assert ot._ticker == "WINV26"
    finally:
        c.disconnect()
