"""A fila e' onde o dado se perde. Estes testes existem para provar que a perda
e' contabilizada, nunca silenciosa."""

from __future__ import annotations

import threading

from profittape.domain.enums import Stream
from profittape.pipeline.bus import EventBus, _Shutdown


def test_conta_descarte_quando_enche() -> None:
    bus = EventBus(maxsize=10)
    aceitos = sum(bus.publish(Stream.TRADE, i) for i in range(25))

    st = bus.stats()
    assert aceitos == 10
    assert st.total_recebido == 25
    assert st.total_descartado == 15
    assert st.taxa_descarte == 15 / 25


def test_publish_nunca_levanta() -> None:
    """Excecao atravessando a fronteira ctypes derruba o processo."""
    bus = EventBus(maxsize=1)
    for _ in range(100):
        assert bus.publish(Stream.TRADE, object()) in (True, False)


def test_drain_devolve_lote() -> None:
    bus = EventBus(maxsize=100)
    for i in range(30):
        bus.publish(Stream.TRADE, i)
    lote = bus.drain(timeout=1.0, max_batch=50)
    assert len(lote) == 30
    assert lote[0].stream is Stream.TRADE


def test_drain_respeita_max_batch() -> None:
    bus = EventBus(maxsize=100)
    for i in range(80):
        bus.publish(Stream.TRADE, i)
    assert len(bus.drain(timeout=1.0, max_batch=25)) == 25


def test_sentinela_preserva_lote_parcial() -> None:
    """Encerrar nao pode descartar o que ja estava na fila."""
    bus = EventBus(maxsize=100)
    for i in range(5):
        bus.publish(Stream.TRADE, i)
    bus.close()
    try:
        bus.drain(timeout=1.0, max_batch=100)
        raise AssertionError("deveria ter sinalizado shutdown")
    except _Shutdown as fim:
        assert len(fim.lote_parcial) == 5


def test_concorrencia_de_multiplos_produtores() -> None:
    bus = EventBus(maxsize=50_000)

    def produzir() -> None:
        for i in range(2_000):
            bus.publish(Stream.TRADE, i)

    threads = [threading.Thread(target=produzir) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    st = bus.stats()
    assert st.total_recebido == 16_000
    assert st.total_descartado == 0


def test_nivel_ocupacao_limiares() -> None:
    """Criterio unico de alerta pre-descarte, usado por record e backfill."""
    from profittape.pipeline.bus import nivel_ocupacao

    assert nivel_ocupacao(0, 500_000) is None
    assert nivel_ocupacao(49_999, 500_000) is None
    assert nivel_ocupacao(50_000, 500_000) == "atencao"
    assert nivel_ocupacao(249_999, 500_000) == "atencao"
    assert nivel_ocupacao(250_000, 500_000) == "critico"
    assert nivel_ocupacao(500_000, 500_000) == "critico"
    assert nivel_ocupacao(10, 0) is None            # maxsize invalido nao explode
