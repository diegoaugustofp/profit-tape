"""
E5.4 — DespachanteDeEAs: um alvo fixo para o callback, N bridges dentro.

O que estes testes protegem: o record NUNCA para para mexer em EA
(decisao do operador, 2026-09-11 -- reiniciar perde captura, o unico
ativo que nao da' para refazer).
"""

from __future__ import annotations

import threading
import time

from profittape.domain.events import Trade
from profittape.ea.despachante import DespachanteDeEAs


class _BridgeFalso:
    def __init__(self, simbolo: str = "WINV26", explode: bool = False) -> None:
        self._simbolo = simbolo
        self.recebidos: list[Trade] = []
        self.iniciado = False
        self.parado = False
        self._explode = explode

    def publicar(self, trade: Trade) -> None:
        if self._explode:
            raise RuntimeError("bug proposital neste EA")
        self.recebidos.append(trade)

    def iniciar(self) -> None:
        self.iniciado = True

    def parar(self, timeout_s: float = 5.0) -> None:
        self.parado = True


def _trade(symbol: str = "WINV26") -> Trade:
    return Trade(ts_ns=1, ts_recv_ns=1, symbol=symbol, exchange="F", trade_id=1,
                 price=100.0, volume_financeiro=1.0, quantidade=1,
                 agente_comprador=3, agente_vendedor=85, trade_type=2, is_edit=False)


def test_despachante_vazio_nao_quebra() -> None:
    """Caso de partida: record sobe sem EA nenhum. `publicar` tem que ser
    praticamente gratuito e nunca levantar."""
    d = DespachanteDeEAs()
    d.publicar(_trade())
    assert len(d) == 0


def test_fan_out_entrega_para_todos() -> None:
    d = DespachanteDeEAs()
    a, b = _BridgeFalso("WINV26"), _BridgeFalso("WDOV26")
    d.incluir(a)  # type: ignore[arg-type]
    d.incluir(b)  # type: ignore[arg-type]
    assert a.iniciado and b.iniciado, "incluir tem que INICIAR o bridge"
    t = _trade()
    d.publicar(t)
    assert a.recebidos == [t] and b.recebidos == [t]


def test_ea_com_bug_nao_impede_os_outros_nem_levanta() -> None:
    """Regra herdada do on_trade_extra: excecao de EA e' contida. Um EA
    quebrado nao pode derrubar o callback da DLL (mataria a captura) nem
    roubar o trade dos outros."""
    d = DespachanteDeEAs()
    ruim, bom = _BridgeFalso("WINV26", explode=True), _BridgeFalso("WINV26")
    d.incluir(ruim)  # type: ignore[arg-type]
    d.incluir(bom)  # type: ignore[arg-type]
    d.publicar(_trade())          # nao levanta
    assert len(bom.recebidos) == 1, "o EA bom tem que receber mesmo assim"
    assert d.resumo()["erros"] == 1


def test_remover_para_de_entregar_e_para_o_bridge() -> None:
    d = DespachanteDeEAs()
    a = _BridgeFalso("WINV26")
    d.incluir(a)  # type: ignore[arg-type]
    d.publicar(_trade())
    assert d.remover(a) is True  # type: ignore[arg-type]
    assert a.parado, "remover tem que parar o bridge (encerra_dia zera posicao)"
    d.publicar(_trade())
    assert len(a.recebidos) == 1, "nao pode receber trade depois de removido"
    assert len(d) == 0


def test_remover_bridge_que_nao_esta_na_lista() -> None:
    d = DespachanteDeEAs()
    assert d.remover(_BridgeFalso()) is False  # type: ignore[arg-type]


def test_parar_todos_esvazia_e_para_cada_um() -> None:
    d = DespachanteDeEAs()
    a, b = _BridgeFalso("WINV26"), _BridgeFalso("WDOV26")
    d.incluir(a)  # type: ignore[arg-type]
    d.incluir(b)  # type: ignore[arg-type]
    d.parar_todos()
    assert a.parado and b.parado and len(d) == 0


def test_bridge_que_falha_ao_parar_nao_impede_os_outros() -> None:
    class _NaoPara(_BridgeFalso):
        def parar(self, timeout_s: float = 5.0) -> None:
            raise RuntimeError("falhou ao encerrar")

    d = DespachanteDeEAs()
    ruim, bom = _NaoPara("WINV26"), _BridgeFalso("WDOV26")
    d.incluir(ruim)  # type: ignore[arg-type]
    d.incluir(bom)  # type: ignore[arg-type]
    d.parar_todos()               # nao levanta
    assert bom.parado, "o outro tem que encerrar mesmo assim"


def test_inclusao_concorrente_com_publicacao_nao_perde_bridge() -> None:
    """`publicar` roda no hot path sem lock (le uma tupla imutavel). Este
    teste exercita inclusao enquanto trades chegam: nenhum bridge pode
    sumir da lista final."""
    d = DespachanteDeEAs()
    parar = threading.Event()

    def publicando() -> None:
        while not parar.is_set():
            d.publicar(_trade())

    t = threading.Thread(target=publicando, daemon=True)
    t.start()
    bridges = [_BridgeFalso(f"TICK{i}") for i in range(50)]
    for b in bridges:
        d.incluir(b)  # type: ignore[arg-type]
        time.sleep(0.001)
    parar.set()
    t.join(timeout=5)
    assert len(d) == 50
    assert all(b.iniciado for b in bridges)
