"""
Testes de ea/bridge.py -- a ponte entre captura e EA, rodando dentro do
mesmo processo do record (2026-08-27, decisao de arquitetura de longo
prazo). As tres garantias que mais importam: filtra por simbolo, nunca
bloqueia/derruba por fila cheia, nunca derruba por erro de processamento.
"""

from __future__ import annotations

import time

from profittape.domain.events import Trade
from profittape.ea.bridge import EABridge
from profittape.ea.config import EAConfig, RiscoConfig, SinalConfig
from profittape.ea.service import EAService

_SINAL = SinalConfig(feature="z_agf_3", horizonte=3, agent_id=3,
                     threshold_entrada=1.0, direcao="contrarian")


def _svc(symbol: str = "WINFUT") -> EAService:
    cfg = EAConfig(symbol=symbol, volume_barra=50, janela_z=6,
                   sinais=[_SINAL], tamanho_posicao=1, dry_run=True,
                   risco=RiscoConfig())
    return EAService(cfg)


def _trade(symbol: str, i: int, comp: int = 3, vend: int = 85) -> Trade:
    return Trade(ts_ns=i * 10**8, ts_recv_ns=i * 10**8, symbol=symbol,
                exchange="F", trade_id=i, price=140000.0 + i,
                volume_financeiro=0.0, quantidade=5,
                agente_comprador=comp, agente_vendedor=vend,
                trade_type=2, is_edit=False)


def test_filtra_trades_de_outro_simbolo() -> None:
    svc = _svc("WINFUT")
    bridge = EABridge(svc)
    bridge.publicar(_trade("WDOFUT", 1))   # outro simbolo -- filtrado
    bridge.publicar(_trade("WDOFUT", 2))
    assert bridge._fila.qsize() == 0
    assert bridge._filtrados_outro_simbolo == 2

    bridge.publicar(_trade("WINFUT", 3))   # simbolo certo -- entra
    assert bridge._fila.qsize() == 1


def test_descarta_com_contagem_quando_fila_cheia_nunca_bloqueia() -> None:
    svc = _svc("WINFUT")
    bridge = EABridge(svc, maxsize=2)
    for i in range(5):
        bridge.publicar(_trade("WINFUT", i))   # nunca deve lancar/bloquear
    assert bridge._fila.qsize() == 2   # so' os 2 que couberam
    assert bridge._descartados == 3    # os outros 3, contabilizados


def test_consumidor_processa_e_alimenta_o_ea_service() -> None:
    svc = _svc("WINFUT")
    bridge = EABridge(svc)
    bridge.iniciar()
    try:
        for i in range(3000):
            bridge.publicar(_trade("WINFUT", i))
        time.sleep(1.0)   # da' tempo da thread consumidora processar
        assert svc.stats.trades == 3000
        assert svc.stats.barras > 0
    finally:
        bridge.parar()


def test_erro_no_processamento_nao_derruba_a_thread(monkeypatch) -> None:
    """Um bug processando UM trade nao pode impedir o resto de continuar
    sendo processado."""
    svc = _svc("WINFUT")
    bridge = EABridge(svc)

    chamadas = {"n": 0}
    original = svc.processar_trade_bruto

    def _quebra_na_primeira(t):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise RuntimeError("bug proposital")
        return original(t)

    svc.processar_trade_bruto = _quebra_na_primeira
    bridge.iniciar()
    try:
        bridge.publicar(_trade("WINFUT", 1))   # este vai "quebrar"
        bridge.publicar(_trade("WINFUT", 2))   # este tem que continuar normal
        time.sleep(0.5)
        assert chamadas["n"] == 2   # os DOIS foram tentados, nao so' o 1o
    finally:
        bridge.parar()


def test_parar_encerra_o_dia_no_ea_service() -> None:
    """parar() chama encerrar_dia() -- posicao aberta (se houver) e' zerada."""
    svc = _svc("WINFUT")
    svc.stats.posicao_simulada = 2   # simula posicao aberta
    bridge = EABridge(svc)
    bridge.iniciar()
    bridge.parar()
    assert svc.stats.posicao_simulada == 0
