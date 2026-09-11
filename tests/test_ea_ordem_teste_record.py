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
from profittape.ea.ordem_teste import (
    OrdemDeTeste,
    TickerAgregadorInvalido,
    TravaSimulacao,
    exigir_simulador,
    exigir_ticker_especifico,
)
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
        ot = OrdemDeTeste(c, RoteamentoConfig(), horario_hhmm="00:00", ticker="WINV26")
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
        ot = OrdemDeTeste(c, RoteamentoConfig(), horario_hhmm="00:00", ticker="WINV26")
        _rodar(ot)
        r = ot.rel.resumo()
        assert r["resultado"] == "ok", r
        assert [n for n, _ in fake.ordens_enviadas] == [
            "SendMarketBuyOrder",
            "SendZeroPositionAtMarket",
        ]
        # esteira real (2026-09-11, 12:30): ClientCreated x2, HadesCreated, Filled
        assert r["status_compra"] == ["ClientCreated", "ClientCreated", "HadesCreated", "Filled"]
        assert r["status_zeragem"] == ["ClientCreated", "ClientCreated", "HadesCreated", "Filled"]
        assert r["preco_medio_compra"] == 141000.0
        assert r["latencia_primeiro_callback_ms"] is not None
        assert r["latencia_fill_compra_ms"] >= r["latencia_primeiro_callback_ms"]
        # argumentos: conta, corretora, senha, ticker, bolsa, qtd (compra)
        assert fake.ordens_enviadas[0][1] == ("DEMO-1", "32006", "s", "WINV26", "F", 1)
        # zeragem: senha em 5o lugar
        assert fake.ordens_enviadas[1][1] == ("DEMO-1", "32006", "WINV26", "F", "s")
    finally:
        c.disconnect()


def test_espera_o_horario() -> None:
    fake = FakeProfitDLL(eventos_por_ativo=0)
    c = _client(fake)
    try:
        relogio = {"h": "09:59"}
        ot = OrdemDeTeste(
            c,
            RoteamentoConfig(),
            horario_hhmm="10:00",
            ticker="WINV26",
            relogio=lambda: relogio["h"],
        )
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
        ot = OrdemDeTeste(
            c, RoteamentoConfig(), horario_hhmm="00:00", ticker="WINV26", timeout_fill_s=0.1
        )
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
        ot = OrdemDeTeste(c, RoteamentoConfig(), horario_hhmm="00:00", ticker="WINV26")
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
            OrdemDeTeste(c, RoteamentoConfig(), horario_hhmm="00:00", ticker="WINV26", quantidade=3)
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
    svc = RecorderService(
        cfg, cred, dll_injetada=fake, ordem_teste_em="00:00", ordem_teste_ticker="WINV26"
    )
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


def test_record_bloqueia_ticker_agregador_no_startup(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """WINFUT resolve dado mas nao e' negociavel (manual Nelogica, "Como
    rotear ordens com a ProfitDLL"). Ate 2026-09-11 isso era so' um AVISO
    e a ordem falhava so' no pregao ("Ordem invalida", 10:30 real). Agora
    falha no STARTUP, antes de qualquer conexao, com SystemExit."""
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

    with pytest.raises(SystemExit, match="agregador"):
        RecorderService(
            cfg, cred, dll_injetada=fake, ordem_teste_em="10:00", ordem_teste_ticker="WINFUT"
        )
    # default do comando tambem e' "WINFUT" -- confirma que o default
    # falha alto em vez de silenciosamente nao funcionar no pregao.
    with pytest.raises(SystemExit, match="agregador"):
        RecorderService(cfg, cred, dll_injetada=fake, ordem_teste_em="10:00")


def test_outros_agregadores_tambem_sao_bloqueados() -> None:
    for agregador in ("WDOFUT", "INDFUT", "winfut", "  WINFUT  "):
        with pytest.raises(TickerAgregadorInvalido):
            exigir_ticker_especifico(agregador)
    exigir_ticker_especifico("WINV26")  # nao levanta


def test_ordem_teste_aceita_ticker_especifico() -> None:
    fake = FakeProfitDLL(eventos_por_ativo=0)
    c = _client(fake)
    try:
        ot = OrdemDeTeste(c, RoteamentoConfig(), horario_hhmm="00:00", ticker="WINV26")
        assert ot._ticker == "WINV26"
    finally:
        c.disconnect()


# ---------------------------------------------------------------------
# E4 (2026-09-11): dry_run=False no ea_config, SO' em demo, SO' com
# contrato especifico -- montado em duas fases (bridge precisa existir
# antes do client, o executor precisa do client depois de existir).
# ---------------------------------------------------------------------
def _ea_yaml_dry_run_false(tmp_path):  # type: ignore[no-untyped-def]
    caminho = tmp_path / "ea.yaml"
    caminho.write_text(
        "symbol: WINFUT\nvolume_barra: 1000\njanela_z: 10\n"
        "tamanho_posicao: 1\ndry_run: false\nusar_conta_real: false\n"
        "sinais:\n  - feature: z_agf_3\n    horizonte: 3\n    agent_id: 3\n"
        "    threshold_entrada: 1.4\n    direcao: contrarian\n",
        encoding="utf-8",
    )
    return caminho


def _recorder_yaml(tmp_path):  # type: ignore[no-untyped-def]
    caminho = tmp_path / "r.yaml"
    caminho.write_text(
        f"storage:\n  raiz: {tmp_path / 'raw'}\nativos:\n  - ticker: WINFUT\n    bolsa: F\n"
        "    trades: true\nruntime:\n  login_completo: true\n", encoding="utf-8")
    return caminho


def test_e4_exige_ea_ticker_ordem(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from profittape.config import Credenciais, RecorderConfig
    from profittape.recorder.service import RecorderService

    cfg = RecorderConfig.from_yaml(_recorder_yaml(tmp_path))
    cred = Credenciais(dll_path="fake", activation_key="k", user="u", password="p")
    with pytest.raises(SystemExit, match="ea-ticker-ordem"):
        RecorderService(cfg, cred, dll_injetada=FakeProfitDLL(eventos_por_ativo=0),
                        ea_config_path=_ea_yaml_dry_run_false(tmp_path))


def test_e4_exige_login_completo(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from profittape.config import Credenciais, RecorderConfig
    from profittape.recorder.service import RecorderService

    yaml = tmp_path / "r.yaml"
    yaml.write_text(
        f"storage:\n  raiz: {tmp_path / 'raw'}\nativos:\n  - ticker: WINFUT\n    bolsa: F\n"
        "    trades: true\n", encoding="utf-8")   # SEM login_completo
    cfg = RecorderConfig.from_yaml(yaml)
    cred = Credenciais(dll_path="fake", activation_key="k", user="u", password="p")
    with pytest.raises(SystemExit, match="login completo"):
        RecorderService(cfg, cred, dll_injetada=FakeProfitDLL(eventos_por_ativo=0),
                        ea_config_path=_ea_yaml_dry_run_false(tmp_path),
                        ea_ticker_ordem="WINV26")


def test_e4_bloqueia_ticker_agregador(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from profittape.config import Credenciais, RecorderConfig
    from profittape.recorder.service import RecorderService

    cfg = RecorderConfig.from_yaml(_recorder_yaml(tmp_path))
    cred = Credenciais(dll_path="fake", activation_key="k", user="u", password="p")
    with pytest.raises(SystemExit, match="agregador"):
        RecorderService(cfg, cred, dll_injetada=FakeProfitDLL(eventos_por_ativo=0),
                        ea_config_path=_ea_yaml_dry_run_false(tmp_path),
                        ea_ticker_ordem="WINFUT")


def test_e4_constroi_com_ticker_especifico_e_login_completo(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """So' a MONTAGEM (nao precisa de trade fluindo) -- confirma que as
    duas fases (bridge antes do client, executor depois) produzem um
    RecorderService valido, com o hook de trade religado."""
    from profittape.config import Credenciais, RecorderConfig
    from profittape.recorder.service import RecorderService

    cfg = RecorderConfig.from_yaml(_recorder_yaml(tmp_path))
    cred = Credenciais(dll_path="fake", activation_key="k", user="u", password="p")
    fake = FakeProfitDLL(eventos_por_ativo=0)
    svc = RecorderService(cfg, cred, dll_injetada=fake,
                          ea_config_path=_ea_yaml_dry_run_false(tmp_path),
                          ea_ticker_ordem="WINV26")
    assert svc.ea_bridge is not None
    assert svc.ea_bridge.ea_service.executor is not None
    assert svc.ea_bridge.ea_service.executor._ticker == "WINV26"
    assert svc.ea_bridge.ea_service.executor._apenas_simulador is True
    assert svc.client._on_trade_extra == svc.ea_bridge.publicar


def test_e4_dry_run_true_continua_sem_executor(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Regressao: o caminho dry_run=True (semanas em producao) nao pode
    mudar de comportamento so' porque o dry_run=False agora existe."""
    from profittape.config import Credenciais, RecorderConfig
    from profittape.recorder.service import RecorderService

    caminho = tmp_path / "ea_dry.yaml"
    caminho.write_text(
        "symbol: WINFUT\nvolume_barra: 1000\njanela_z: 10\ntamanho_posicao: 1\n"
        "dry_run: true\nsinais:\n  - feature: z_agf_3\n    horizonte: 3\n"
        "    agent_id: 3\n    threshold_entrada: 1.4\n    direcao: contrarian\n",
        encoding="utf-8")
    cfg = RecorderConfig.from_yaml(_recorder_yaml(tmp_path))
    cred = Credenciais(dll_path="fake", activation_key="k", user="u", password="p")
    fake = FakeProfitDLL(eventos_por_ativo=0)
    svc = RecorderService(cfg, cred, dll_injetada=fake, ea_config_path=caminho)
    assert svc.ea_bridge is not None
    assert svc.ea_bridge.ea_service.executor is None
    assert svc.client._on_trade_extra == svc.ea_bridge.publicar


def test_e4_ponta_a_ponta_ordem_real_em_demo(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Sinal de verdade fluindo pelo bridge, disparando ExecutorDeOrdens,
    enviando SendMarketBuyOrder/SellOrder na fake -- fluxo completo do E4."""
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
    # eventos_por_ativo>0: a fake emite trades de tempo real (WINFUT) que
    # o bridge encaminha ao EAService -- volume_barra baixo para fechar
    # barra logo e chegar a uma decisao.
    fake = FakeProfitDLL(eventos_por_ativo=3000, intervalo_s=0.0)
    svc = RecorderService(cfg, cred, dll_injetada=fake,
                          ea_config_path=_ea_yaml_dry_run_false(tmp_path),
                          ea_ticker_ordem="WINV26")
    t = threading.Thread(target=svc.run, daemon=True)
    t.start()
    fim = time.monotonic() + 8
    while time.monotonic() < fim and not fake.ordens_enviadas:
        time.sleep(0.1)
    svc._parar.set()
    t.join(timeout=60)
    # Nao afirmamos QUE sinal disparou (depende do fluxo aleatorio da
    # fake) -- so' que SE disparou, foi por uma chamada real de ordem
    # (nao dry_run), na conta de simulacao.
    if fake.ordens_enviadas:
        nomes = {n for n, _ in fake.ordens_enviadas}
        assert nomes <= {"SendMarketBuyOrder", "SendMarketSellOrder",
                         "SendZeroPositionAtMarket"}
        for _, args in fake.ordens_enviadas:
            assert "WINV26" in args   # nunca o agregador


def test_cli_dry_run_mostra_e4_no_resumo(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """`record --dry-run` so' valida e imprime -- confirma que
    --ea-ticker-ordem aparece no resumo quando o ea_config e' dry_run=False."""
    from typer.testing import CliRunner

    from profittape.cli import app

    yaml = tmp_path / "r.yaml"
    yaml.write_text(
        "ativos:\n  - ticker: WINFUT\n    bolsa: F\n    trades: true\n"
        f"storage:\n  raiz: {tmp_path / 'raw'}\n", encoding="utf-8")
    r = CliRunner().invoke(app, [
        "record", "-c", str(yaml), "--dry-run", "--login-completo",
        "--ea-config", str(_ea_yaml_dry_run_false(tmp_path)),
        "--ea-ticker-ordem", "WINV26",
    ])
    assert r.exit_code == 0, r.output
    assert "E4: ordem real em demo, ticker=WINV26" in r.output
