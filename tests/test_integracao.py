"""
Integracao ponta a ponta com a DLL falsa.

E' o teste que realmente importa: prova que callback -> fila -> writer ->
Parquet funciona, que nada se perde no encerramento e que os arquivos ficam
legiveis. Roda no Linux, em segundos, sem mercado aberto.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pyarrow.dataset as ds

from profittape.config import (
    AtivoConfig,
    Credenciais,
    PipelineConfig,
    RecorderConfig,
    RuntimeConfig,
    StorageConfig,
)
from profittape.recorder.service import RecorderService
from tests.fakes.fake_dll import FakeProfitDLL


def _config(raiz: Path) -> RecorderConfig:
    return RecorderConfig(
        ativos=[
            AtivoConfig(ticker="PETR4", bolsa="B", trades=True, offer_book=True),
            AtivoConfig(ticker="VALE3", bolsa="B", trades=True),
        ],
        storage=StorageConfig(raiz=raiz, max_rows_per_file=1_000_000),
        pipeline=PipelineConfig(fila_maxsize=200_000, batch_max=5_000, poll_timeout_s=0.1),
        runtime=RuntimeConfig(heartbeat_s=1.0, encerrar_em=None),
    )


def _cred() -> Credenciais:
    return Credenciais(activation_key="k", user="u", password="p", dll_path="fake")


def test_ponta_a_ponta_sem_perda(tmp_raiz: Path) -> None:
    n = 400
    fake = FakeProfitDLL(eventos_por_ativo=n, intervalo_s=0.0)
    svc = RecorderService(_config(tmp_raiz), _cred(), dll_injetada=fake)

    t = threading.Thread(target=svc.run, daemon=True)
    t.start()
    time.sleep(3.0)
    svc._parar.set()
    t.join(timeout=60)

    st = svc.bus.stats()
    assert st.total_descartado == 0, "houve descarte silencioso"
    assert st.total_recebido > 0

    trades = ds.dataset(tmp_raiz / "trade", format="parquet", partitioning="hive").to_table()
    assert trades.num_rows > 0
    assert set(trades["symbol"].to_pylist()) == {"PETR4", "VALE3"}

    livro = ds.dataset(tmp_raiz / "book_offer", format="parquet", partitioning="hive").to_table()
    assert livro.num_rows > 0
    assert set(livro["symbol"].to_pylist()) == {"PETR4"}


def test_encerramento_drena_a_fila(tmp_raiz: Path) -> None:
    """
    O contrato de encerramento: tudo que entrou na fila chega ao disco.
    Se este teste ficar vermelho, a gravacao perde a cauda de todo pregao.
    """
    fake = FakeProfitDLL(eventos_por_ativo=800, intervalo_s=0.0)
    svc = RecorderService(_config(tmp_raiz), _cred(), dll_injetada=fake)

    t = threading.Thread(target=svc.run, daemon=True)
    t.start()
    time.sleep(2.5)
    svc._parar.set()
    t.join(timeout=60)

    recebidos = svc.bus.stats().total_recebido
    descartados = svc.bus.stats().total_descartado

    total_em_disco = 0
    for stream in ("trade", "book_offer", "book_price", "tiny_book"):
        pasta = tmp_raiz / stream
        if pasta.exists():
            total_em_disco += ds.dataset(
                pasta, format="parquet", partitioning="hive"
            ).to_table().num_rows

    assert total_em_disco == recebidos - descartados, (
        f"disco={total_em_disco} fila={recebidos - descartados} — perda no encerramento"
    )


def test_tipos_de_negocio_preservados_ate_o_disco(tmp_raiz: Path) -> None:
    """
    Leilao e RLP precisam sobreviver ate o Parquet para poderem ser excluidos
    do calculo de OFI depois. Se o pipeline normalizasse isso, o dado ficaria
    irrecuperavel.
    """
    fake = FakeProfitDLL(eventos_por_ativo=600, intervalo_s=0.0)
    svc = RecorderService(_config(tmp_raiz), _cred(), dll_injetada=fake)

    t = threading.Thread(target=svc.run, daemon=True)
    t.start()
    time.sleep(2.5)
    svc._parar.set()
    t.join(timeout=60)

    tabela = ds.dataset(tmp_raiz / "trade", format="parquet", partitioning="hive").to_table()
    tipos = set(tabela["trade_type"].to_pylist())
    assert {2, 3} <= tipos, "agressao continua ausente"
    assert 13 in tipos, "RLP foi perdido pelo caminho"


def test_dll_e_finalizada(tmp_raiz: Path) -> None:
    fake = FakeProfitDLL(eventos_por_ativo=50)
    svc = RecorderService(_config(tmp_raiz), _cred(), dll_injetada=fake)
    t = threading.Thread(target=svc.run, daemon=True)
    t.start()
    time.sleep(1.5)
    svc._parar.set()
    t.join(timeout=30)
    assert fake.finalizado


def test_metricas_por_stream_e_feed_vivo(tmp_raiz: Path) -> None:
    """
    Regressao do monitor mentiroso: sessao real com 769k eventos mostrou
    sem_evento_ha_s=844 (feed vivissimo) e por_stream vazio, porque o contador
    por evento nunca era alimentado. Agora o writer alimenta por lote.
    """
    fake = FakeProfitDLL(eventos_por_ativo=200)
    svc = RecorderService(_config(tmp_raiz), _cred(), dll_injetada=fake)
    t = threading.Thread(target=svc.run, daemon=True)
    t.start()
    time.sleep(2.5)

    st = svc.bus.stats()
    snap = svc.metrics.snapshot(st.profundidade_atual, st.profundidade_maxima,
                                st.total_descartado, st.total_recebido)
    assert snap.eventos_por_stream.get("trade", 0) > 0
    assert snap.eventos_por_stream.get("book_offer", 0) > 0
    assert snap.ultimo_evento_ha_s < 5.0        # feed vivo = contador recente

    svc._parar.set()
    t.join(timeout=60)
    snap2 = svc.metrics.snapshot(0, 0, 0, 1)
    assert sum(snap2.eventos_por_stream.values()) == svc.bus.stats().total_recebido


def test_offer_book_exige_registro_v2(tmp_raiz: Path) -> None:
    """
    Regressao do incidente 2026-08-21: 14 min de pregao com subscribe aceito e
    ZERO eventos de offer book — o slot V1 do init nao e' alimentado; so o
    callback registrado via SetOfferBookCallbackV2 recebe. O fake reproduz
    esse comportamento com fidelidade, entao este teste so passa se o cliente
    fizer o registro.
    """
    fake = FakeProfitDLL(eventos_por_ativo=150)
    svc = RecorderService(_config(tmp_raiz), _cred(), dll_injetada=fake)
    t = threading.Thread(target=svc.run, daemon=True)
    t.start()
    time.sleep(2.5)
    svc._parar.set()
    t.join(timeout=60)

    assert svc.client.offer_book_v2 is True
    livro = ds.dataset(tmp_raiz / "book_offer", format="parquet",
                       partitioning="hive").to_table()
    assert livro.num_rows > 0


def test_dll_sem_v2_nao_quebra_e_avisa(tmp_raiz: Path) -> None:
    """DLL antiga sem o setter: sem crash, offer_book ausente, flag False."""
    fake = FakeProfitDLL(eventos_por_ativo=100, com_offer_v2=False)
    fake.SetOfferBookCallbackV2 = None          # export ausente
    svc = RecorderService(_config(tmp_raiz), _cred(), dll_injetada=fake)
    t = threading.Thread(target=svc.run, daemon=True)
    t.start()
    time.sleep(2.0)
    svc._parar.set()
    t.join(timeout=60)

    assert svc.client.offer_book_v2 is False
    assert not (tmp_raiz / "book_offer").exists()      # silencio, como em producao
    trades = ds.dataset(tmp_raiz / "trade", format="parquet",
                        partitioning="hive").to_table()
    assert trades.num_rows > 0                          # o resto segue vivo


def test_fullbook_scalar_nao_e_publicado_como_delta(tmp_raiz: Path) -> None:
    """
    Regressao: pacote atFullBook (action=4) escapava para o disco com campos
    escalares invalidos (a manual so garante os arrays em atFullBook) — em
    producao produziu uma linha com timestamp '1990-01-01', memoria obsoleta
    lida como data. Confirma que o cliente descarta e conta.
    """
    from profittape.pipeline.bus import EventBus
    from profittape.profitdll.client import ProfitClient
    from profittape.profitdll.types import TAssetIDRec

    bus = EventBus()
    fake = FakeProfitDLL(eventos_por_ativo=1)
    c = ProfitClient(dll_path="x", activation_key="k", user="u", password="p",
                     bus=bus, dll=fake)
    c.connect(timeout_s=5)
    try:
        ativo = TAssetIDRec("WINFUT", "F", 0)
        # action=4 (atFullBook) com data LIXO: se publicado, contaminaria com
        # um timestamp implausivel — exatamente o incidente real.
        c._cb["offer_book"](ativo, 4, 0, 0, 999, 1, 1, 999.0,
                            b"\x01", b"\x01", b"\x01", b"\x01", b"\x01",
                            "01/01/1990 00:00:00.000", None, None)
        c._cb["offer_book_v2"](ativo, 4, 0, 0, 999, 1, 1, 999.0,
                               b"\x01", b"\x01", b"\x01", b"\x01", b"\x01",
                               "01/01/1990 00:00:00.000", None, None)
        assert bus.stats().total_recebido == 0
        assert c.full_book_descartados["offer"] == 2
    finally:
        c.disconnect()


def test_has_date_false_nao_confia_no_ponteiro_de_data(tmp_raiz: Path) -> None:
    """
    Regressao do achado real (SESSAO 2, 2026-08-21): 97% dos deltas de
    book_offer saiam com timestamp '1990-01-01' — memoria obsoleta de um
    pwcDate nao preenchido pela DLL para aquele evento, lida como se fosse
    data valida, porque has_date era ignorado. O manual documenta bHasDate
    exatamente para isto. Chama o callback diretamente com has_date=False e
    uma string de data PLAUSIVEL (simulando o buffer obsoleto) para provar
    que o cliente a ignora e grava ts_ns=0, has_date=False.
    """
    from profittape.pipeline.bus import EventBus
    from profittape.profitdll.client import ProfitClient
    from profittape.profitdll.types import TAssetIDRec

    bus = EventBus()
    fake = FakeProfitDLL(eventos_por_ativo=1)
    c = ProfitClient(dll_path="x", activation_key="k", user="u", password="p",
                     bus=bus, dll=fake)
    c.connect(timeout_s=5)
    try:
        ativo = TAssetIDRec("WINFUT", "F", 0)
        c._cb["offer_book_v2"](
            ativo, 0, 0, 0, 100, 3, 55, 5000.0,
            b"\x01", b"\x01", b"\x00",           # has_date=False
            b"\x01", b"\x01",
            "01/01/1990 00:00:00.000",           # data-lixo plausivel
            None, None,
        )
        lote = bus.drain(timeout=2.0, max_batch=10)
        assert len(lote) == 1
        evento = lote[0].event
        assert evento.has_date is False
        assert evento.ts_ns == 0
    finally:
        c.disconnect()


def test_has_date_true_confia_na_data(tmp_raiz: Path) -> None:
    """Contraprova: quando a flag confirma, a data e' parseada normalmente."""
    from profittape.pipeline.bus import EventBus
    from profittape.profitdll.client import ProfitClient
    from profittape.profitdll.types import TAssetIDRec

    bus = EventBus()
    fake = FakeProfitDLL(eventos_por_ativo=1)
    c = ProfitClient(dll_path="x", activation_key="k", user="u", password="p",
                     bus=bus, dll=fake)
    c.connect(timeout_s=5)
    try:
        ativo = TAssetIDRec("WINFUT", "F", 0)
        c._cb["offer_book_v2"](
            ativo, 0, 0, 0, 100, 3, 55, 5000.0,
            b"\x01", b"\x01", b"\x01",           # has_date=True
            b"\x01", b"\x01",
            "21/08/2026 13:00:00.000",
            None, None,
        )
        lote = bus.drain(timeout=2.0, max_batch=10)
        evento = lote[0].event
        assert evento.has_date is True
        assert evento.ts_ns > 0
    finally:
        c.disconnect()


def test_segundo_sinal_durante_encerramento_avisa_e_nao_quebra(tmp_raiz: Path) -> None:
    """
    Diagnostico do proprio usuario: o resumo sumia porque o SEGUNDO Ctrl+C
    interrompia a limpeza — e ele apertava de novo porque nada confirmava que
    o primeiro registrou. O handler do record agora responde ao segundo sinal
    com aviso em vez de silencio.
    """
    svc = RecorderService(_config(tmp_raiz), _cred(),
                          dll_injetada=FakeProfitDLL(eventos_por_ativo=10))
    # chama o handler direto, sem sinal de verdade (portavel em qualquer SO)
    import signal as _s
    svc._instalar_sinais()
    handler = _s.getsignal(_s.SIGINT)
    handler(_s.SIGINT, None)              # 1o: inicia encerramento
    assert svc._parar.is_set()
    handler(_s.SIGINT, None)              # 2o: so avisa, nao levanta
    assert svc._parar.is_set()
