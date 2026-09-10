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


def test_drain_acumula_chegada_gradual_nao_devolve_lote_de_1(monkeypatch) -> None:
    """
    O BUG REAL (2026-08-21 a 2026-09-10): a versao antiga usava get_nowait()
    apos o primeiro item -- espera ZERO. Contra um produtor que entrega um
    item de cada vez em cadencia REGULAR (nao em rajada instantanea, o
    padrao real de um ativo de alta frequencia como WINFUT), o consumidor
    quase sempre "vencia a corrida": acordava no primeiro item, checava
    get_nowait(), achava vazio porque o proximo ainda nao tinha chegado, e
    devolvia lote de 1. Descoberto em producao via row groups por arquivo:
    WINFUT em 08/09 tinha ~15 linhas por row group (34.525 row groups pra
    519.764 linhas) -- 4h48min pra ler o que devia levar segundos.

    Este teste simula EXATAMENTE essa cadencia: uma thread produtora publica
    um item a cada 2 ms (mais rapido que qualquer timeout real de producao,
    mas alto o bastante pra nunca virar rajada por acidente de agendamento
    do SO). Contra a versao antiga, este teste falha (lote pequeno). Contra
    a corrigida, drain() espera o ORCAMENTO INTEIRO de timeout, acumulando
    dezenas de itens em vez de 1.
    """
    import threading
    import time as time_mod

    bus = EventBus(maxsize=10_000)
    parar = threading.Event()

    def produzir() -> None:
        i = 0
        while not parar.is_set():
            bus.publish(Stream.TRADE, i)
            i += 1
            time_mod.sleep(0.002)   # 2 ms entre itens -- cadencia, nao rajada

    t = threading.Thread(target=produzir, daemon=True)
    t.start()
    try:
        lote = bus.drain(timeout=0.5, max_batch=10_000)
    finally:
        parar.set()
        t.join(timeout=2)

    # em 0.5s a 2ms/item, esperam-se ~250 itens. Exige so' >= 20 pra nao ser
    # fragil a variacao de agendamento do SO, mas 20 ja' e' 20x o que a
    # versao antiga (que sempre devolvia 1) conseguiria.
    assert len(lote) >= 20, (
        f"lote={len(lote)} -- drain() devolveu quase nada mesmo com o "
        "produtor rodando durante toda a janela de timeout. Isto e' "
        "exatamente o bug antigo: get_nowait() apos o primeiro item nao da' "
        "ao produtor NENHUMA chance de empilhar mais.")


def test_drain_ainda_respeita_max_batch_com_producao_continua() -> None:
    """A correcao nao pode remover o teto de max_batch -- so' deixa de
    devolver cedo demais, nunca deixa acumular alem do limite."""
    import threading
    import time as time_mod

    bus = EventBus(maxsize=10_000)
    parar = threading.Event()

    def produzir() -> None:
        i = 0
        while not parar.is_set():
            bus.publish(Stream.TRADE, i)
            i += 1
            time_mod.sleep(0.001)

    t = threading.Thread(target=produzir, daemon=True)
    t.start()
    try:
        lote = bus.drain(timeout=0.5, max_batch=15)
    finally:
        parar.set()
        t.join(timeout=2)

    assert len(lote) == 15


def test_drain_fila_quieta_nao_espera_alem_do_timeout() -> None:
    """A correcao nao pode transformar drain() numa espera fixa e' cega --
    se so' 1 item chega e mais NADA vem depois, o retorno tem que sair
    perto do timeout, nao muito alem dele (sem hang, sem lentidao extra)."""
    import time as time_mod

    bus = EventBus(maxsize=100)
    bus.publish(Stream.TRADE, 1)   # um so' item, fila fica quieta depois

    t0 = time_mod.monotonic()
    lote = bus.drain(timeout=0.3, max_batch=100)
    decorrido = time_mod.monotonic() - t0

    assert len(lote) == 1
    assert decorrido < 0.5, (
        f"drain() levou {decorrido:.2f}s para uma fila quieta com timeout "
        "de 0.3s -- deveria estourar o timeout e devolver, nao esperar bem "
        "mais que isso")
