"""
Benchmark do pipeline com a DLL falsa.

POR QUE ISTO EXISTE
-------------------
"O writer da conta?" nao e' pergunta para responder por intuicao, e a resposta
depende da MAQUINA: disco, nucleos, versao do Python. Rodar isto antes do
pregao diz quanta folga voce tem, em vez de descobrir na abertura.

O QUE JA SABEMOS DA MEDICAO DE REFERENCIA
------------------------------------------
O caminho de escrita processa ~125 mil linhas/s (transposicao + montagem de
arrays + Parquet zstd-3). Isso e' MUITA folga: mesmo WIN em rajada de abertura
raramente passa de algumas dezenas de milhares de eventos por segundo.

O gargalo real nao e' disco nem Parquet — e' disputa de GIL. Toda thread de
callback e o writer competem pelo mesmo interpretador. E' exatamente por isso
que a regra "callback so empilha e devolve" nao e' preciosismo: cada
microssegundo gasto em Python dentro do callback e' microssegundo roubado do
writer, e a fila cresce nos dois sentidos ao mesmo tempo.
"""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path


def rodar(eventos_por_ativo: int, n_ativos: int, duracao_s: float, intervalo_s: float) -> None:
    import pyarrow.dataset as ds

    from ..config import (
        AtivoConfig,
        Credenciais,
        PipelineConfig,
        RecorderConfig,
        RuntimeConfig,
        StorageConfig,
    )
    from ..recorder.service import RecorderService

    try:
        from tests.fakes.fake_dll import FakeProfitDLL
    except ImportError:  # pragma: no cover
        print("bench exige o pacote de testes no PYTHONPATH (rode da raiz do repo).")
        return

    raiz = Path(tempfile.mkdtemp()) / "raw"
    tickers = [f"SYM{i}" for i in range(n_ativos)]
    cfg = RecorderConfig(
        ativos=[AtivoConfig(ticker=t, trades=True, offer_book=True) for t in tickers],
        storage=StorageConfig(raiz=raiz),
        pipeline=PipelineConfig(fila_maxsize=500_000, batch_max=50_000, poll_timeout_s=0.2),
        runtime=RuntimeConfig(heartbeat_s=1e9),
    )
    cred = Credenciais(activation_key="k", user="u", password="p", dll_path="fake")
    fake = FakeProfitDLL(eventos_por_ativo=eventos_por_ativo, intervalo_s=intervalo_s)
    svc = RecorderService(cfg, cred, dll_injetada=fake)

    t0 = time.perf_counter()
    th = threading.Thread(target=svc.run, daemon=True)
    th.start()
    time.sleep(duracao_s)
    svc._parar.set()
    th.join(timeout=300)
    dt = time.perf_counter() - t0

    st = svc.bus.stats()
    linhas = 0
    tam = 0
    for stream in ("trade", "book_offer"):
        p = raiz / stream
        if p.exists():
            linhas += ds.dataset(p, format="parquet", partitioning="hive").to_table().num_rows
            tam += sum(f.stat().st_size for f in p.rglob("*.parquet"))

    print("=" * 68)
    print("BENCHMARK DO PIPELINE")
    print("=" * 68)
    print(f"  ativos simulados   : {n_ativos} (trades + offer book)")
    print(f"  duracao            : {dt:.1f} s")
    print(f"  eventos recebidos  : {st.total_recebido:,}")
    print(f"  vazao              : {st.total_recebido / dt:,.0f} eventos/s")
    print(f"  descartados        : {st.total_descartado:,} ({st.taxa_descarte:.4%})")
    print(f"  fila pico          : {st.profundidade_maxima:,} de 500.000")
    print(f"  linhas em disco    : {linhas:,}")
    print(f"  PERDA LIQUIDA      : {st.total_recebido - st.total_descartado - linhas}")
    if linhas:
        print(f"  tamanho por evento : {tam / linhas:.1f} bytes")
        print(f"  projecao 50M ev    : {tam / linhas * 50e6 / 1e9:.1f} GB")
    print()
    if st.total_descartado:
        print("  DESCARTE OBSERVADO. Na pratica isso quase sempre significa que o")
        print("  gerador sintetico saturou o GIL, nao que o disco nao da conta —")
        print("  as threads falsas fazem MUITO mais trabalho Python que um callback")
        print("  real. Refaca com --intervalo maior para simular ritmo de mercado.")
    else:
        print("  Sem descarte. A fila pico indica a folga real desta maquina.")
    print("=" * 68)
