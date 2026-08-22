"""Backfill (quiesce) e curadoria (dedup, exclusao de ts invalido)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pyarrow.dataset as ds
import pytest

from profittape.config import (
    AtivoConfig,
    Credenciais,
    PipelineConfig,
    RecorderConfig,
    RuntimeConfig,
    StorageConfig,
)
from profittape.domain.enums import Stream
from profittape.domain.events import Trade
from profittape.recorder.backfill import _iso_para_dll, executar
from profittape.storage.parquet_sink import ParquetSink
from profittape.testing import FakeProfitDLL
from profittape.tools.curate import curar_trades


def test_conversao_de_data() -> None:
    assert _iso_para_dll("2026-08-20") == "20/08/2026"
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        _iso_para_dll("20/08/2026")


def test_backfill_ponta_a_ponta(tmp_raiz: Path) -> None:
    cfg = RecorderConfig(
        ativos=[AtivoConfig(ticker="PETR4"), AtivoConfig(ticker="VALE3")],
        storage=StorageConfig(raiz=tmp_raiz),
        pipeline=PipelineConfig(poll_timeout_s=0.1),
        runtime=RuntimeConfig(),
    )
    cred = Credenciais(activation_key="k", user="u", password="p", dll_path="fake")
    fake = FakeProfitDLL(eventos_por_ativo=300)

    rc = executar(cfg, cred, "2026-08-18", "2026-08-19",
                  quiesce_s=1.5, timeout_s=20, settle_s=0.0, dll_injetada=fake)
    assert not fake.erros, f"thread emissora do fake morreu: {fake.erros[0]!r}"
    assert rc == 0

    tabela = ds.dataset(tmp_raiz / "trade", format="parquet", partitioning="hive").to_table()
    assert tabela.num_rows == 600
    assert set(tabela["symbol"].to_pylist()) == {"PETR4", "VALE3"}
    # O quiesce nao pode cortar cedo: os 300 de cada ativo tem que estar la.
    assert max(tabela["trade_id"].to_pylist()) == 300


def _trade(i: int, trade_id: int, ts: int, recv: int, sym: str = "PETR4") -> Trade:
    return Trade(ts_ns=ts, ts_recv_ns=recv, symbol=sym, exchange="B",
                 trade_id=trade_id, price=30.0 + i * 0.01, volume_financeiro=3000.0,
                 quantidade=100, agente_comprador=3, agente_vendedor=8,
                 trade_type=2, is_edit=i % 2 == 1)


def test_curadoria_deduplica_e_exclui_ts_invalido(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    curated = tmp_path / "curated"
    base = 1_704_193_200_000_000_000
    sink = ParquetSink(raw)

    eventos = [
        _trade(0, trade_id=1, ts=base, recv=base + 100),
        _trade(1, trade_id=1, ts=base, recv=base + 900),      # edicao: vence (preco 30.01)
        _trade(2, trade_id=2, ts=base + 5_000, recv=base + 5_100),
        _trade(3, trade_id=3, ts=0, recv=base + 6_000),        # parse falhou: excluir
        _trade(4, trade_id=4, ts=base + 1_000, recv=base + 1_100),
    ]
    cols = dict(zip(Trade._fields, (list(c) for c in zip(*eventos, strict=True)), strict=True))
    sink.write(Stream.TRADE, "2024-01-02", "PETR4", cols)
    sink.close()

    t = curar_trades(raw, curated)
    assert t == {"lidas": 5, "duplicatas": 1, "ts_invalido": 1, "gravadas": 3, "particoes": 1}

    tabela = ds.dataset(curated / "trade", format="parquet", partitioning="hive").to_table()
    ids = tabela["trade_id"].to_pylist()
    assert ids == [1, 4, 2]                       # ordenado por ts_ns
    assert 0 not in tabela["ts_ns"].to_pylist()
    linha_1 = tabela.to_pylist()[0]
    assert linha_1["price"] == pytest.approx(30.01)  # a EDICAO venceu, nao a original


def test_ticker_recusado_nao_aborta_os_demais(tmp_raiz: Path) -> None:
    """
    Regressao do incidente real: GetHistoryTrades devolveu NL desconhecido para
    WINFUT e o backfill abortou sem tentar PETR4/VALE3 — jogando fora justamente
    o padrao diferencial que diagnostica a causa.
    """
    cfg = RecorderConfig(
        ativos=[
            AtivoConfig(ticker="FAILHIST_WINFUT", bolsa="F"),
            AtivoConfig(ticker="PETR4"),
        ],
        storage=StorageConfig(raiz=tmp_raiz),
        pipeline=PipelineConfig(poll_timeout_s=0.1),
        runtime=RuntimeConfig(),
    )
    cred = Credenciais(activation_key="k", user="u", password="p", dll_path="fake")
    fake = FakeProfitDLL(eventos_por_ativo=100)

    rc = executar(cfg, cred, "2026-08-18", "2026-08-19",
                  quiesce_s=1.5, timeout_s=20, settle_s=0.0,
                  tentativas=1, dll_injetada=fake)
    assert rc == 0

    tabela = ds.dataset(tmp_raiz / "trade", format="parquet", partitioning="hive").to_table()
    assert set(tabela["symbol"].to_pylist()) == {"PETR4"}
    assert tabela.num_rows == 100


def test_todos_recusados_devolve_2(tmp_raiz: Path) -> None:
    cfg = RecorderConfig(
        ativos=[AtivoConfig(ticker="FAILHIST_A"), AtivoConfig(ticker="FAILHIST_B")],
        storage=StorageConfig(raiz=tmp_raiz),
        pipeline=PipelineConfig(poll_timeout_s=0.1),
        runtime=RuntimeConfig(),
    )
    cred = Credenciais(activation_key="k", user="u", password="p", dll_path="fake")
    rc = executar(cfg, cred, "2026-08-18", "2026-08-19",
                  quiesce_s=1.0, timeout_s=10,
                  settle_s=0.0, tentativas=2, intervalo_retry_s=0.1,
                  dll_injetada=FakeProfitDLL(eventos_por_ativo=10))
    assert rc == 2


def test_describe_codigo_agora_nomeado_nao_mais_desconhecido() -> None:
    """
    Superado: -2147483602 era 'codigo desconhecido' ate ser identificado no
    manual como NL_HISTORY_PERIOD_LIMIT (base+46, GetHistoryTrades so' aceita
    'data inicial' dentro dos ultimos 30 dias corridos). Trava o estado atual.
    """
    from profittape.profitdll.errors import describe

    msg = describe(-2147483602)
    assert "30 dias" in msg
    assert "desconhecido" not in msg


def test_retry_recupera_servidor_nao_pronto(tmp_raiz: Path) -> None:
    """
    Padrao observado em producao: recusa NL logo apos conectar, que some numa
    segunda tentativa. O retry precisa recuperar o ticker sem intervencao.
    """
    cfg = RecorderConfig(
        ativos=[AtivoConfig(ticker="FLAKYHIST_PETR4")],
        storage=StorageConfig(raiz=tmp_raiz),
        pipeline=PipelineConfig(poll_timeout_s=0.1),
        runtime=RuntimeConfig(),
    )
    cred = Credenciais(activation_key="k", user="u", password="p", dll_path="fake")
    fake = FakeProfitDLL(eventos_por_ativo=80)

    rc = executar(cfg, cred, "2026-08-18", "2026-08-19",
                  quiesce_s=1.0, timeout_s=20,
                  settle_s=0.0, tentativas=3, intervalo_retry_s=0.2,
                  dll_injetada=fake)
    assert rc == 0
    assert fake._hist_chamadas["FLAKYHIST_PETR4"] == 2  # recusou, retry aceitou

    tabela = ds.dataset(tmp_raiz / "trade", format="parquet", partitioning="hive").to_table()
    assert tabela.num_rows == 80


def test_tabela_de_tipos_validada_contra_a_dll_em_uso() -> None:
    """Trava os fatos confirmados pelo manual em 2026-08-21."""
    from profittape.domain.enums import TradeType

    assert TradeType.RLP == 13
    assert TradeType.UNKNOWN == 32
    assert TradeType(13).is_agressao_continua is False   # RLP fora do OFI
    assert TradeType(2).signo == 1 and TradeType(3).signo == -1
    assert TradeType(34).name == "MID"


def test_agent_name_via_fake() -> None:
    from profittape.pipeline.bus import EventBus
    from profittape.profitdll.client import ProfitClient

    fake = FakeProfitDLL(eventos_por_ativo=1)
    c = ProfitClient(dll_path="x", activation_key="k", user="u", password="p",
                     bus=EventBus(maxsize=16), dll=fake)
    c.connect(timeout_s=5)
    try:
        assert c.agent_name(3) == "CORRETORA 3"
        assert c.agent_name(999) is None       # DLL nao conhece -> None
    finally:
        c.disconnect()


def test_curated_nao_duplica_colunas_de_particao(tmp_path: Path) -> None:
    """
    Regressao: dt gravado dentro do arquivo sob dt=... quebra a leitura do
    dataset quando o tipo em-arquivo (large_string, dependendo da versao do
    pandas) difere do inferido da particao (string).
    """
    import pyarrow.parquet as pq_

    from profittape.tools.curate import curar_trades

    raw = tmp_path / "raw"
    base = 1_704_193_200_000_000_000
    eventos = [_trade(0, trade_id=1, ts=base, recv=base + 1)]
    cols = dict(zip(Trade._fields, (list(c) for c in zip(*eventos, strict=True)), strict=True))
    sink = ParquetSink(raw)
    sink.write(Stream.TRADE, "2024-01-02", "PETR4", cols)
    sink.close()

    curar_trades(raw, tmp_path / "curated")
    arquivos = list((tmp_path / "curated").rglob("*.parquet"))
    schema = pq_.read_schema(arquivos[0])
    assert "dt" not in schema.names
    assert "sym" not in schema.names

    tabela = ds.dataset(tmp_path / "curated" / "trade", format="parquet",
                        partitioning="hive").to_table()
    assert set(tabela.column_names) >= {"dt", "sym", "trade_id"}   # vindos da particao


def test_por_dia_captura_e_e_retomavel(tmp_raiz: Path) -> None:
    """
    O contrato do modo longo: (1) uma particao dt= por dia util pedido;
    (2) re-rodar NAO re-baixa o que ja existe — queda no meio da noite custa
    um comando, nao a noite.
    """
    from profittape.recorder.backfill import executar_por_dia

    cfg = RecorderConfig(
        ativos=[AtivoConfig(ticker="PETR4")],
        storage=StorageConfig(raiz=tmp_raiz),
        pipeline=PipelineConfig(poll_timeout_s=0.1),
        runtime=RuntimeConfig(),
    )
    cred = Credenciais(activation_key="k", user="u", password="p", dll_path="fake")

    # 2026-08-14 (sex) a 2026-08-18 (ter): 3 dias uteis, fim de semana pulado
    fake = FakeProfitDLL(eventos_por_ativo=50)
    rc = executar_por_dia(cfg, cred, "2026-08-14", "2026-08-18",
                          quiesce_s=1.0, timeout_dia_s=20, settle_s=0.0,
                          dll_injetada=fake)
    assert rc == 0
    dias = sorted(p.name for p in (tmp_raiz / "trade").glob("dt=*"))
    assert dias == ["dt=2026-08-14", "dt=2026-08-17", "dt=2026-08-18"]

    # Retomada: nada pendente -> nenhuma chamada de historico nova
    fake2 = FakeProfitDLL(eventos_por_ativo=50)
    rc2 = executar_por_dia(cfg, cred, "2026-08-14", "2026-08-18",
                           quiesce_s=1.0, timeout_dia_s=20, settle_s=0.0,
                           dll_injetada=fake2)
    assert rc2 == 0
    assert fake2._hist_chamadas == {} and not fake2._subscritos


def test_backfill_avisa_dias_fora_da_janela_de_30_dias(tmp_raiz: Path) -> None:
    """
    Achado real 2026-08-21: GetHistoryTrades so' aceita 'data inicial' dentro
    dos ultimos 30 dias corridos. O aviso upfront deve nomear quantos dias do
    pedido estao fora dessa janela, sem abortar a tentativa.
    """
    from profittape.recorder.backfill import executar_por_dia

    cfg = RecorderConfig(
        ativos=[AtivoConfig(ticker="PETR4")],
        storage=StorageConfig(raiz=tmp_raiz),
        pipeline=PipelineConfig(poll_timeout_s=0.1),
        runtime=RuntimeConfig(),
    )
    cred = Credenciais(activation_key="k", user="u", password="p", dll_path="fake")
    ha_60_dias = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
    ha_58_dias = (datetime.now() - timedelta(days=58)).strftime("%Y-%m-%d")

    executar_por_dia(cfg, cred, ha_60_dias, ha_58_dias,
                     quiesce_s=1.0, timeout_dia_s=10, settle_s=0.0,
                     dll_injetada=FakeProfitDLL(eventos_por_ativo=10))
    # Nao afirma sobre o log (capturado so' por caplog se configurado); o
    # teste de valor aqui e' que a funcao NAO LEVANTA e completa mesmo com
    # o intervalo inteiro fora da janela.


def test_por_dia_interrompido_ainda_reporta_resumo_e_e_retomavel(tmp_raiz: Path) -> None:
    """
    Achado real: Ctrl+C no meio de --por-dia pulava o log de resumo (Keyboard
    Interrupt e' BaseException, escapa do 'except Exception'), deixando o
    usuario sem saber quanto ja tinha. Corrigido: resumo sempre imprime;
    codigo de saida vira 130 (convencao SIGINT); dias ja gravados permanecem
    e o proximo run pula exatamente esses.
    """
    from profittape.recorder import backfill as bf

    cfg = RecorderConfig(
        ativos=[AtivoConfig(ticker="PETR4")],
        storage=StorageConfig(raiz=tmp_raiz),
        pipeline=PipelineConfig(poll_timeout_s=0.1),
        runtime=RuntimeConfig(),
    )
    cred = Credenciais(activation_key="k", user="u", password="p", dll_path="fake")

    original = bf._aguardar_quiesce
    chamadas = {"n": 0}

    def _quiesce_que_interrompe(bus, base, quiesce_s, timeout_s):
        chamadas["n"] += 1
        if chamadas["n"] == 2:          # interrompe no 2o dia
            raise KeyboardInterrupt
        return original(bus, base, quiesce_s, timeout_s)

    sinais_configurados = []
    monkey = bf._aguardar_quiesce
    monkey_signal = bf.signal.signal
    bf.signal.signal = lambda sig, disp: sinais_configurados.append((sig, disp))
    bf._aguardar_quiesce = _quiesce_que_interrompe
    try:
        rc = bf.executar_por_dia(
            cfg, cred, "2026-08-17", "2026-08-19",   # 3 dias uteis (seg-qua)
            quiesce_s=1.0, timeout_dia_s=10, settle_s=0.0,
            dll_injetada=FakeProfitDLL(eventos_por_ativo=50),
        )
    finally:
        bf._aguardar_quiesce = monkey
        bf.signal.signal = monkey_signal

    assert rc == 130
    # Blindagem: apos o 1o Ctrl+C, SIGINT passa a ser ignorado para o
    # fechamento dos arquivos nao poder ser interrompido por um 2o aperto.
    assert (bf.signal.SIGINT, bf.signal.SIG_IGN) in sinais_configurados
    capturados = sorted(p.name for p in (tmp_raiz / "trade").glob("dt=*"))
    assert capturados == ["dt=2026-08-17"]        # 1o dia completo, 2o interrompido

    # Retomada: so' pede o que falta.
    rc2 = bf.executar_por_dia(cfg, cred, "2026-08-17", "2026-08-19",
                              quiesce_s=1.0, timeout_dia_s=10, settle_s=0.0,
                              dll_injetada=FakeProfitDLL(eventos_por_ativo=50))
    assert rc2 == 0
    capturados2 = sorted(p.name for p in (tmp_raiz / "trade").glob("dt=*"))
    assert capturados2 == ["dt=2026-08-17", "dt=2026-08-18", "dt=2026-08-19"]


def test_por_dia_repete_dia_vazio_dentro_da_janela(tmp_raiz: Path) -> None:
    """
    Padrao real (2026-08-21): dia pedido logo apos um dia pesado voltava vazio
    (servidor ocupado), com timing exato de quiesce. Dentro da janela de 30
    dias, um vazio deve ser repetido — este teste faz o fake devolver vazio na
    1a tentativa e dados na 2a, e exige que o dia seja capturado.
    """
    from profittape.recorder import backfill as bf

    hoje = datetime.now()
    dia_alvo = (hoje - timedelta(days=3)).strftime("%Y-%m-%d")   # dentro dos 30

    cfg = RecorderConfig(
        ativos=[AtivoConfig(ticker="PETR4")],
        storage=StorageConfig(raiz=tmp_raiz),
        pipeline=PipelineConfig(poll_timeout_s=0.1),
        runtime=RuntimeConfig(),
    )
    cred = Credenciais(activation_key="k", user="u", password="p", dll_path="fake")

    fake = FakeProfitDLL(eventos_por_ativo=40)

    # O fake padrao entrega sempre; simulamos "vazio na 1a" monkeypatchando o
    # quiesce para reportar 0 na primeira chamada e o valor real depois.
    real_quiesce = bf._aguardar_quiesce
    chamadas = {"n": 0}

    def quiesce_vazio_primeiro(bus, base, quiesce_s, timeout_s):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            return 0, True          # vazio, sem timeout
        return real_quiesce(bus, base, quiesce_s, timeout_s)

    bf._aguardar_quiesce = quiesce_vazio_primeiro
    try:
        rc = bf.executar_por_dia(
            cfg, cred, dia_alvo, dia_alvo,
            quiesce_s=0.5, timeout_dia_s=10, settle_s=0.0,
            tentativas_vazio=3, pausa_retry_vazio=0.1,
            dll_injetada=fake,
        )
    finally:
        bf._aguardar_quiesce = real_quiesce

    assert rc == 0
    assert chamadas["n"] == 2                       # repetiu uma vez
    dias = [p.name for p in (tmp_raiz / "trade").glob("dt=*")]
    assert dias == [f"dt={dia_alvo}"]               # capturado na 2a tentativa


def test_diagnostico_duplicatas_distingue_edicao_de_reentrega(tmp_raiz: Path, capsys) -> None:
    """
    Ferramenta de decisao (2026-08-22): 50% de trade_id repetido num unico dia.
    Precisa distinguir edicao de negocio (campos diferem -> exige callback V2)
    de reentrega benigna (identico -> curate deduplica a vontade).
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    from profittape.tools.duplicatas import diagnosticar

    d = tmp_raiz / "trade" / "dt=2026-08-14" / "sym=WINFUT"
    d.mkdir(parents=True)
    rows = [
        # edicao: preco difere
        dict(ts_ns=1, ts_recv_ns=1, symbol="WINFUT", exchange="F", trade_id=1,
             price=100.0, volume_financeiro=500.0, quantidade=5,
             agente_comprador=3, agente_vendedor=85, trade_type=2, is_edit=False),
        dict(ts_ns=1, ts_recv_ns=2, symbol="WINFUT", exchange="F", trade_id=1,
             price=101.0, volume_financeiro=505.0, quantidade=5,
             agente_comprador=3, agente_vendedor=85, trade_type=2, is_edit=False),
        # reentrega: identico exceto ts_recv
        dict(ts_ns=1, ts_recv_ns=1, symbol="WINFUT", exchange="F", trade_id=2,
             price=300.0, volume_financeiro=2100.0, quantidade=7,
             agente_comprador=120, agente_vendedor=39, trade_type=2, is_edit=False),
        dict(ts_ns=1, ts_recv_ns=2, symbol="WINFUT", exchange="F", trade_id=2,
             price=300.0, volume_financeiro=2100.0, quantidade=7,
             agente_comprador=120, agente_vendedor=39, trade_type=2, is_edit=False),
    ]
    cols = {k: [r[k] for r in rows] for k in rows[0]}
    pq.write_table(pa.table(cols), d / "part-0000.parquet")

    diagnosticar(tmp_raiz, "WINFUT", "2026-08-14", amostras=5)
    out = capsys.readouterr().out
    assert "DIFERE" in out          # pegou a edicao
    assert "IDENTICO" in out        # pegou a reentrega
    assert "MISTO" in out or "EDICAO" in out


def test_curate_pula_arquivo_com_zstd_corrompido(tmp_raiz: Path, capsys) -> None:
    """
    Incidente (2026-08-22): 'ZSTD decompression failed' derrubava o curate
    inteiro. Diferente de sem-footer: o arquivo TEM footer valido (passa pelo
    exclude_invalid_files) mas um row group esta corrompido por dentro. So'
    lendo fragmento a fragmento da' pra isolar o podre e salvar os sadios.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    from profittape.tools.curate import curar_trades

    curated = tmp_raiz.parent / "curated"
    d = tmp_raiz / "trade" / "dt=2026-08-14" / "sym=WINFUT"
    d.mkdir(parents=True)
    cols = dict(ts_ns=[1000, 2000], ts_recv_ns=[1, 2], symbol=["WINFUT"] * 2,
                exchange=["F"] * 2, trade_id=[1, 2], price=[1.0, 2.0],
                volume_financeiro=[1.0, 2.0], quantidade=[1, 1],
                agente_comprador=[3, 3], agente_vendedor=[85, 85],
                trade_type=[2, 2], is_edit=[False] * 2)
    pq.write_table(pa.table(cols), d / "part-0001.parquet")   # bom

    # corrompido: footer valido, row group estragado
    ruim = d / "part-0000.parquet"
    pq.write_table(pa.table(cols), ruim)
    b = bytearray(ruim.read_bytes())
    for i in range(50, min(80, len(b) - 8)):
        b[i] = 0xFF
    ruim.write_bytes(bytes(b))

    totais = curar_trades(tmp_raiz, curated)   # nao pode crashar
    assert totais["gravadas"] == 2             # curou o arquivo bom
    out = capsys.readouterr().out
    assert "PULADO" in out


def test_quarentena_profundo_pega_corrupcao_interna(tmp_raiz: Path, capsys) -> None:
    """--profundo descomprime e pega o que o footer intacto esconde."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    from profittape.tools.quarentena import varrer

    d = tmp_raiz / "trade" / "dt=2026-08-14" / "sym=WINFUT"
    d.mkdir(parents=True)
    ruim = d / "part-0000.parquet"
    pq.write_table(pa.table({"a": list(range(100))}), ruim)
    b = bytearray(ruim.read_bytes())
    for i in range(50, min(90, len(b) - 8)):
        b[i] = 0xFF
    ruim.write_bytes(bytes(b))

    varrer(tmp_raiz, remover=False, profundo=True)
    out = capsys.readouterr().out
    assert "SEM footer" in out or "part-0000" in out
