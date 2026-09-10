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
    c = ProfitClient(dll_path="x", activation_key="k", user="u", password="p", bus=bus, dll=fake)  # type: ignore[arg-type]
    c.connect(timeout_s=5)
    try:
        c.request_history("WINFUT", "31/08/2026", "31/08/2026", "F")
        assert chamadas == [
            ("WINFUT", "F", f"31/08/2026 {HORA_INICIO_PREGAO}", f"31/08/2026 {HORA_FIM_PREGAO}")
        ]
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
    c = ProfitClient(dll_path="x", activation_key="k", user="u", password="p", bus=bus, dll=fake)  # type: ignore[arg-type]
    c.connect(timeout_s=5)
    try:
        c.historico_100.clear()
        assert fake.GetHistoryTrades("WINFUT", "F", "31/08/2026", "31/08/2026") == 0
        assert c.historico_100.wait(2)
        time.sleep(0.2)
        assert bus.stats().total_recebido == 0  # aceito, vazio
    finally:
        c.disconnect()


def test_backfill_assina_o_ticker_antes_de_pedir_historico(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Medido 2026-09-10: sem SubscribeTicker antes, a DLL 4.0.0.4x devolve
    progresso 100 imediato e zero negocios para o mesmo pedido que, com o
    ticker assinado, entrega 6,1 M negocios."""
    from profittape.config import (
        AtivoConfig,
        Credenciais,
        PipelineConfig,
        RecorderConfig,
        RuntimeConfig,
        StorageConfig,
    )
    from profittape.recorder import backfill as bf

    fake = FakeProfitDLL(eventos_por_ativo=20, com_login_completo=False)
    ordem: list[str] = []
    sub, hist = fake.SubscribeTicker, fake.GetHistoryTrades

    def espiao_sub(ticker: str, bolsa: str) -> int:
        ordem.append(f"sub:{ticker}")
        return sub(ticker, bolsa)

    def espiao_hist(ticker: str, bolsa: str, ini: str, fim: str) -> int:
        ordem.append(f"hist:{ticker}:{ini}")
        return hist(ticker, bolsa, ini, fim)

    fake.SubscribeTicker = espiao_sub  # type: ignore[method-assign]
    fake.GetHistoryTrades = espiao_hist  # type: ignore[method-assign]
    cfg = RecorderConfig(
        ativos=[AtivoConfig(ticker="WINFUT", bolsa="F", trades=True)],
        storage=StorageConfig(raiz=tmp_path / "raw", max_rows_per_file=1_000_000),
        pipeline=PipelineConfig(fila_maxsize=100_000, batch_max=1_000, poll_timeout_s=0.1),
        runtime=RuntimeConfig(),
    )
    cred = Credenciais(activation_key="k", user="u", password="p", dll_path="fake")
    rc = bf.executar_por_dia(
        cfg,
        cred,
        "2026-09-02",
        "2026-09-02",
        quiesce_s=0.3,
        timeout_dia_s=10,
        settle_s=0.0,
        dll_injetada=fake,
    )
    assert rc == 0
    assert ordem[0] == "sub:WINFUT"
    assert ordem[1] == "hist:WINFUT:02/09/2026 09:00:00"


def test_backfill_nao_grava_tempo_real_mesmo_assinado(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A assinatura liga o tempo real; num backfill dentro do pregao isso
    viraria uma particao parcial de HOJE que pareceria capturada. O client
    em modo backfill descarta o tempo real antes de montar o evento."""
    from profittape.config import (
        AtivoConfig,
        Credenciais,
        PipelineConfig,
        RecorderConfig,
        RuntimeConfig,
        StorageConfig,
    )
    from profittape.recorder import backfill as bf

    fake = FakeProfitDLL(
        eventos_por_ativo=20, com_login_completo=False
    )  # emite tempo real ao assinar
    cfg = RecorderConfig(
        ativos=[AtivoConfig(ticker="WINFUT", bolsa="F", trades=True)],
        storage=StorageConfig(raiz=tmp_path / "raw", max_rows_per_file=1_000_000),
        pipeline=PipelineConfig(fila_maxsize=100_000, batch_max=1_000, poll_timeout_s=0.1),
        runtime=RuntimeConfig(),
    )
    cred = Credenciais(activation_key="k", user="u", password="p", dll_path="fake")
    rc = bf.executar_por_dia(
        cfg,
        cred,
        "2026-09-02",
        "2026-09-02",
        quiesce_s=0.3,
        timeout_dia_s=10,
        settle_s=0.0,
        dll_injetada=fake,
    )
    assert rc == 0
    particoes = sorted(p.name for p in (tmp_path / "raw" / "trade").glob("dt=*"))
    assert particoes == ["dt=2026-09-02"]  # nada de "hoje"
