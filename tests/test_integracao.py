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
