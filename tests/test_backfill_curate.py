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


def _dia_util_recente(dias_atras_min: int = 3) -> str:
    """
    Um dia UTIL (nao sabado/domingo) dentro da janela de 30 dias, pelo menos
    dias_atras_min dias no passado. hoje-3 fixo e' fragil -- cai em fim de
    semana dependendo do dia da semana em que os testes rodam (bug real
    pego 2026-08-25: falhava toda terca/quarta porque hoje-3 caia no
    sabado anterior). Anda para tras ate achar um dia util.
    """
    d = datetime.now() - timedelta(days=dias_atras_min)
    while d.weekday() >= 5:   # 5=sabado, 6=domingo
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")

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
    # subconjunto, nao igualdade exata: segundos_leitura/segundos_total
    # (2026-09-09, diagnostico de performance) sao FLOAT e variam por
    # execucao -- nao pertencem a uma comparacao de CONTAGENS exatas.
    assert {k: t[k] for k in ("lidas", "duplicatas", "ts_invalido",
                              "gravadas", "particoes")} == {
        "lidas": 5, "duplicatas": 1, "ts_invalido": 1, "gravadas": 3, "particoes": 1}

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
    # 3, nao 2: o priming (2026-09-11) tambem chama GetHistoryTrades e usa
    # o mesmo contador da fake -- 1a recusada, 2a e' o priming bem
    # sucedido; a chamada REAL vem depois e ja' encontra o servidor
    # pronto. O que importa esta' abaixo: os 80 eventos chegaram inteiros.
    assert fake._hist_chamadas["FLAKYHIST_PETR4"] == 3

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
        # 3, nao 2: o priming (2026-09-11) faz sua PROPRIA chamada de
        # quiesce (via _aguardar_entrega) antes do laco de dias comecar.
        # Contagem: 1=priming, 2=dia 1 (08-17), 3=dia 2 (08-18) -- e' esta
        # que precisa interromper, como o teste sempre pretendeu.
        if chamadas["n"] == 3:
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

    dia_alvo = _dia_util_recente()   # dentro dos 30, sempre dia util

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
    assert "curate.arquivo_pulado" in out


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


def test_raiz_relativa_e_sempre_recusada(tmp_path, monkeypatch) -> None:
    """
    REVISAO (2026-08-25): a defesa original so' recusava o caso drive-
    relativo ('\\data\\raw') e RECOMENDAVA relativo puro ('data/raw') como
    alternativa segura. Provado errado na pratica: o mesmo yaml, lancado de
    um diretorio de trabalho diferente (como o schtasks pode fazer sem
    aviso), resolveu 'data\\raw' para C:\\data\\raw — fora do projeto
    inteiro. Relativo puro NUNCA e' seguro para um processo cujo CWD de
    lancamento nao esta sob nosso controle. Agora e' recusa incondicional.
    """
    from profittape.config import StorageConfig

    monkeypatch.chdir(tmp_path)
    with pytest.raises(Exception, match=r"nao e. absoluto"):
        StorageConfig(raiz=Path("data/raw"))


def test_raiz_absoluta_e_imutavel_ao_cwd(tmp_path, monkeypatch) -> None:
    """Caminho absoluto passa direto e nunca muda, mesmo se o CWD mudar depois."""
    import os

    from profittape.config import StorageConfig

    alvo = tmp_path / "data" / "raw"
    cfg = StorageConfig(raiz=alvo)
    assert cfg.raiz.is_absolute()
    assert str(cfg.raiz) == str(alvo.resolve())
    os.chdir(tmp_path.anchor)                       # muda o CWD depois do load
    assert str(cfg.raiz) == str(alvo.resolve())      # destino nao se move


def test_raiz_drive_relativa_e_recusada_no_windows(monkeypatch) -> None:
    """
    REVISAO (2026-08-22, endurecida em 2026-08-25): '\\data\\raw' (drive-
    relativo) mandou uma recaptura para G:\\ e outra para C:\\data\\raw, em
    silencio. Agora a regra e' unica e mais simples: qualquer coisa que nao
    seja absoluto e' recusada — drive-relativo incluso, sem caso especial.
    """
    import os

    import pytest as _pt

    from profittape import config as cfg_mod

    monkeypatch.setattr(os, "name", "nt")
    with _pt.raises(Exception, match=r"nao e. absoluto"):
        cfg_mod.StorageConfig(raiz=Path("\\data\\raw"))


def test_dia_com_um_simbolo_falta_outro_fica_pendente(tmp_raiz: Path) -> None:
    """
    Bug real (2026-08-23): o operador baixou WINFUT, depois ampliou o yaml
    para WDOFUT+acoes e rodou de novo — o backfill disse 'ja capturado' sem
    NUNCA pedir WDOFUT/acoes, porque a checagem antiga era 'existe QUALQUER
    .parquet nesse dt=', nao 'existe .parquet de CADA ticker configurado'.
    """
    from profittape.recorder.backfill import _dia_ja_capturado

    dia = "2026-08-14"
    pasta_win = tmp_raiz / "trade" / f"dt={dia}" / "sym=WINFUT"
    pasta_win.mkdir(parents=True)
    (pasta_win / "part-0000.parquet").write_bytes(b"PAR1" + b"\x00" * 100 + b"PAR1")

    # Com so' WINFUT configurado: dia esta completo.
    assert _dia_ja_capturado(tmp_raiz, dia, ["WINFUT"]) is True
    # Ampliando para WINFUT+WDOFUT: falta WDOFUT, dia NAO pode estar completo.
    assert _dia_ja_capturado(tmp_raiz, dia, ["WINFUT", "WDOFUT"]) is False

    # Depois de capturar WDOFUT tambem, aí sim completo.
    pasta_wdo = tmp_raiz / "trade" / f"dt={dia}" / "sym=WDOFUT"
    pasta_wdo.mkdir(parents=True)
    (pasta_wdo / "part-0000.parquet").write_bytes(b"PAR1" + b"\x00" * 100 + b"PAR1")
    assert _dia_ja_capturado(tmp_raiz, dia, ["WINFUT", "WDOFUT"]) is True


def test_backfill_pede_so_o_ticker_faltante_no_dia(tmp_raiz: Path, capsys) -> None:
    """
    Alem de nao pular o dia, o backfill deve pedir SO' o ticker que falta —
    nao re-baixar um simbolo ja presente so' porque outro do mesmo dia
    esta faltando (desperdicio de tempo e de janela de historico).
    """
    cfg = RecorderConfig(
        ativos=[AtivoConfig(ticker="WINFUT"), AtivoConfig(ticker="WDOFUT")],
        storage=StorageConfig(raiz=tmp_raiz),
        pipeline=PipelineConfig(poll_timeout_s=0.1),
        runtime=RuntimeConfig(),
    )
    cred = Credenciais(activation_key="k", user="u", password="p", dll_path="fake")

    dia_alvo = _dia_util_recente()

    # Pre-existe SO' o WINFUT para esse dia (simulando a rodada anterior).
    pasta_win = tmp_raiz / "trade" / f"dt={dia_alvo}" / "sym=WINFUT"
    pasta_win.mkdir(parents=True)
    (pasta_win / "part-0000.parquet").write_bytes(b"PAR1" + b"\x00" * 100 + b"PAR1")

    from profittape.recorder import backfill as bf

    fake = FakeProfitDLL(eventos_por_ativo=30)
    rc = bf.executar_por_dia(
        cfg, cred, dia_alvo, dia_alvo,
        quiesce_s=0.3, timeout_dia_s=10, settle_s=0.0,
        dll_injetada=fake,
    )
    assert rc == 0

    # O log estruturado de 'solicitando' registra os ativos efetivamente
    # pedidos — evidencia direta, sem depender de instrumentar o cliente DLL.
    saida = capsys.readouterr().out
    assert "'WDOFUT'" in saida            # o que faltava foi pedido
    assert "'WINFUT'" not in saida        # o que ja existia NAO foi re-pedido


def test_curate_loga_progresso_por_dia_nao_so_resumo_final(tmp_raiz: Path, capsys) -> None:
    """
    Pedido real do operador (2026-08-24): com 20+ dias e 9 simbolos, o curate
    ficava mudo por minutos ate' o resumo final — indistinguivel de travado.
    Agora loga curate.destino no inicio e curate.particao_ok POR (DIA,
    SIMBOLO) processado (evento renomeado de dia_ok em 2026-09-10c quando a
    granularidade de leitura passou de dia inteiro para dia+simbolo).
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    from profittape.tools.curate import curar_trades

    cols = dict(ts_ns=[1000], ts_recv_ns=[1], symbol=["WINFUT"], exchange=["F"],
                trade_id=[1], price=[1.0], volume_financeiro=[1.0],
                quantidade=[1], agente_comprador=[3], agente_vendedor=[85],
                trade_type=[2], is_edit=[False])
    for dia in ("2026-08-11", "2026-08-12", "2026-08-13"):
        d = tmp_raiz / "trade" / f"dt={dia}" / "sym=WINFUT"
        d.mkdir(parents=True)
        pq.write_table(pa.table(cols), d / "part-0000.parquet")

    curar_trades(tmp_raiz, tmp_raiz.parent / "curated")
    out = capsys.readouterr().out
    assert "curate.destino" in out
    assert out.count("curate.particao_ok") == 3   # um log por dia (1 simbolo cada)
    for dia in ("2026-08-11", "2026-08-12", "2026-08-13"):
        assert dia in out


def _escrever_dia_trade(raiz: Path, dia: str, symbol: str,
                        n_arquivos: int, linhas_por_arquivo: int = 2) -> None:
    """Gera N arquivos .parquet saudaveis de trade para um (dia, symbol) --
    o cenario comum (sem corrupcao) que o caminho rapido do curate precisa
    cobrir. IDs de trade sequenciais e unicos entre arquivos para nao
    disparar dedup incidental."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    d = raiz / "trade" / f"dt={dia}" / f"sym={symbol}"
    d.mkdir(parents=True, exist_ok=True)
    prox_id = 1
    for i in range(n_arquivos):
        base = prox_id
        ids = list(range(base, base + linhas_por_arquivo))
        prox_id += linhas_por_arquivo
        n = linhas_por_arquivo
        cols = dict(
            ts_ns=[1000 + k for k in ids], ts_recv_ns=[k for k in ids],
            symbol=[symbol] * n, exchange=["F"] * n, trade_id=ids,
            price=[float(k) for k in ids], volume_financeiro=[1.0] * n,
            quantidade=[1] * n, agente_comprador=[3] * n,
            agente_vendedor=[85] * n, trade_type=[2] * n, is_edit=[False] * n,
        )
        pq.write_table(pa.table(cols), d / f"part-{i:04d}.parquet")


def test_curate_caminho_rapido_nao_abre_fragmento_a_fragmento(
    tmp_raiz: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    PERFORMANCE (2026-09-09): com a rotacao por IDADE (todo arquivo fecha aos
    900s, ativo ou nao -- close_idle em parquet_sink.py), um dia comum ja'
    produz centenas de arquivos de trade; um dia com reinicio passa de 800.
    Um dia de 5,4M linhas / 280 arquivos levou 55 minutos no loop antigo
    (fragment.to_table() um de cada vez, em Python).

    Nao basta o resultado bater -- e' facil o caminho rapido silenciosamente
    cair pro lento sem ninguem notar. Este teste prova que o atalho e'
    REALMENTE tomado: `pa.concat_tables` so' e' chamado no FALLBACK (o
    caminho rapido usa `dataset.to_table()` direto, sem concat manual) --
    se ele for chamado, o teste falha, mesmo que o total de linhas esteja
    certo.
    """
    curated = tmp_raiz.parent / "curated"
    _escrever_dia_trade(tmp_raiz, "2026-08-14", "WINFUT", n_arquivos=50)

    import pyarrow as pa_mod

    chamado = {"n": 0}
    original = pa_mod.concat_tables

    def _espiao(*a: object, **k: object) -> object:
        chamado["n"] += 1
        return original(*a, **k)

    monkeypatch.setattr(pa_mod, "concat_tables", _espiao)

    totais = curar_trades(tmp_raiz, curated)

    assert chamado["n"] == 0, (
        "pa.concat_tables foi chamado -- o curate caiu no fallback lento "
        "sem nenhum arquivo corrompido para justificar")
    assert totais["gravadas"] == 100          # 50 arquivos x 2 linhas
    assert totais["duplicatas"] == 0
    assert totais["ts_invalido"] == 0


def test_curate_caminho_lento_ainda_e_correto_com_muitos_arquivos(
    tmp_raiz: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """O fallback fragmento-a-fragmento precisa continuar correto quando
    disparado num dia com VARIOS arquivos saudaveis e um so' podre -- nao so'
    no caso minimo de 2 arquivos que o teste original de 22/08 cobre."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    curated = tmp_raiz.parent / "curated"
    _escrever_dia_trade(tmp_raiz, "2026-08-14", "WINFUT",
                       n_arquivos=20, linhas_por_arquivo=3)

    ruim = tmp_raiz / "trade" / "dt=2026-08-14" / "sym=WINFUT" / "part-9999.parquet"
    cols = dict(ts_ns=[999000], ts_recv_ns=[999], symbol=["WINFUT"],
                exchange=["F"], trade_id=[999], price=[9.0],
                volume_financeiro=[1.0], quantidade=[1],
                agente_comprador=[3], agente_vendedor=[85],
                trade_type=[2], is_edit=[False])
    pq.write_table(pa.table(cols), ruim)
    b = bytearray(ruim.read_bytes())
    for i in range(50, min(80, len(b) - 8)):
        b[i] = 0xFF
    ruim.write_bytes(bytes(b))

    totais = curar_trades(tmp_raiz, curated)

    assert totais["gravadas"] == 60            # 20 arquivos bons x 3, o podre fora
    out = capsys.readouterr().out
    assert "curate.leitura_em_lote_falhou" in out
    assert "curate.arquivo_pulado" in out


def test_curate_loga_quebra_leitura_x_processamento(
    tmp_raiz: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """A instrumentacao que deveria existir antes de eu adivinhar a causa da
    lentidao de 09/09: proxima vez, o log diz onde o tempo foi, sem
    reproduzir nada. segundos = leitura + processamento, sempre."""
    curated = tmp_raiz.parent / "curated"
    _escrever_dia_trade(tmp_raiz, "2026-08-14", "WINFUT", n_arquivos=10)

    curar_trades(tmp_raiz, curated)
    out = capsys.readouterr().out

    assert "segundos_leitura=" in out
    assert "segundos_processamento=" in out

    import re
    m = re.search(
        r"segundos=([\d.]+).*segundos_leitura=([\d.]+).*"
        r"segundos_processamento=([\d.]+)", out)
    assert m, f"campos nao encontrados na linha de log:\n{out}"
    total, leitura, proc = (float(x) for x in m.groups())
    assert proc >= 0.0             # nunca "processamento negativo" (-0.0)
    assert total >= leitura - 0.15  # folga por arredondamento


def test_modo_leitura_invalido_e_rejeitado(tmp_raiz: Path) -> None:
    curated = tmp_raiz.parent / "curated"
    _escrever_dia_trade(tmp_raiz, "2026-08-14", "WINFUT", n_arquivos=2)
    with pytest.raises(ValueError, match="modo_leitura invalido"):
        curar_trades(tmp_raiz, curated, modo_leitura="turbo")


class _DatasetEspiao:
    """Envolve um pyarrow.dataset real para espionar to_table() -- Dataset e'
    tipo de extensao IMUTAVEL (mesma limitacao de Fragment), entao o unico
    ponto patcheavel e' a FABRICA `ds.dataset()`, que e' funcao Python comum."""
    def __init__(self, real: object, chamadas: list[dict[str, object]]) -> None:
        self._real = real
        self._chamadas = chamadas

    def to_table(self, *a: object, **k: object) -> object:
        self._chamadas.append(dict(k))
        return self._real.to_table(*a, **k)  # type: ignore[attr-defined]

    def get_fragments(self, *a: object, **k: object) -> object:
        return self._real.get_fragments(*a, **k)  # type: ignore[attr-defined]


def test_modo_fragmento_nunca_chama_dataset_to_table(
    tmp_raiz: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    O modo de ultimo recurso (2026-09-10, curadoria travada em producao com
    'lote' mesmo apos exclusao do antivirus -- causa ainda desconhecida).
    'fragmento' precisa pular O TO_TABLE EM LOTE INTEIRAMENTE, nao so' cair
    nele e falhar -- se a suspeita for que dataset.to_table() TRAVA (nao so'
    e' lento), CHAMA-LO e deixar ele levantar excecao nao ajuda; ele pode
    nunca retornar. Prova via proxy em ds.dataset(): zero chamadas a
    to_table() no modo fragmento, mesmo com dado saudavel.
    """
    curated = tmp_raiz.parent / "curated"
    _escrever_dia_trade(tmp_raiz, "2026-08-14", "WINFUT", n_arquivos=15)

    import profittape.tools.curate as curate_mod

    chamadas: list[dict[str, object]] = []
    original_fabrica = curate_mod.ds.dataset

    def _fabrica_espia(*a: object, **k: object) -> object:
        return _DatasetEspiao(original_fabrica(*a, **k), chamadas)

    monkeypatch.setattr(curate_mod.ds, "dataset", _fabrica_espia)

    totais = curar_trades(tmp_raiz, curated, modo_leitura="fragmento")

    assert chamadas == [], (
        "dataset.to_table() foi chamado no modo 'fragmento' -- exatamente "
        "o que este modo existe para NUNCA fazer")
    assert totais["gravadas"] == 30   # 15 arquivos x 2 linhas


def test_modo_sequencial_le_sem_threads(
    tmp_raiz: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """'sequencial' precisa chamar to_table com use_threads=False -- unica
    forma de verificar isso e' espionar o kwarg recebido de verdade."""
    curated = tmp_raiz.parent / "curated"
    _escrever_dia_trade(tmp_raiz, "2026-08-14", "WINFUT", n_arquivos=5)

    import profittape.tools.curate as curate_mod

    chamadas: list[dict[str, object]] = []
    original_fabrica = curate_mod.ds.dataset

    def _fabrica_espia(*a: object, **k: object) -> object:
        return _DatasetEspiao(original_fabrica(*a, **k), chamadas)

    monkeypatch.setattr(curate_mod.ds, "dataset", _fabrica_espia)

    curar_trades(tmp_raiz, curated, modo_leitura="sequencial")
    assert len(chamadas) == 1
    assert chamadas[0].get("use_threads") is False


def test_todos_os_tres_modos_dao_o_mesmo_resultado(tmp_raiz: Path) -> None:
    """Independente de como o dia e' lido, o dado curado final tem que ser
    IDENTICO -- os modos sao so' estrategia de leitura, nunca de logica."""
    resultados = []
    for modo in ("lote", "sequencial", "fragmento"):
        raiz = tmp_raiz.parent / f"raw_{modo}"
        curated = tmp_raiz.parent / f"curated_{modo}"
        _escrever_dia_trade(raiz, "2026-08-14", "WINFUT", n_arquivos=12)
        t = curar_trades(raiz, curated, modo_leitura=modo)
        resultados.append((t["gravadas"], t["duplicatas"], t["ts_invalido"]))
    assert resultados[0] == resultados[1] == resultados[2]


def test_checkpoints_de_leitura_pandas_dedup_sao_sempre_emitidos(
    tmp_raiz: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """
    Pedido do operador apos 2 dias sem sinal de onde o tempo ia (2026-09-10):
    o log padrao so' saia ao FIM do dia inteiro -- inutil quando um dia leva
    horas. Estes tres SEMPRE aparecem, com ou sem --diagnostico, e SEMPRE
    nesta ordem: leitura -> pandas -> dedup.
    """
    curated = tmp_raiz.parent / "curated"
    _escrever_dia_trade(tmp_raiz, "2026-08-14", "WINFUT", n_arquivos=8)

    curar_trades(tmp_raiz, curated)
    out = capsys.readouterr().out

    assert "curate.leitura_ok" in out
    assert "curate.conversao_pandas_ok" in out
    assert "curate.dedup_ok" in out
    pos_leitura = out.index("curate.leitura_ok")
    pos_pandas = out.index("curate.conversao_pandas_ok")
    pos_dedup = out.index("curate.dedup_ok")
    assert pos_leitura < pos_pandas < pos_dedup, (
        "checkpoints fora de ordem -- leitura precisa vir antes de pandas, "
        "que precisa vir antes de dedup")


def test_leitura_ok_reporta_arquivos_e_linhas_corretos(
    tmp_raiz: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    curated = tmp_raiz.parent / "curated"
    _escrever_dia_trade(tmp_raiz, "2026-08-14", "WINFUT",
                       n_arquivos=7, linhas_por_arquivo=4)

    curar_trades(tmp_raiz, curated)
    out = capsys.readouterr().out

    import re
    m = re.search(r"curate\.leitura_ok\s+.*?arquivos=(\d+).*?linhas=(\d+)", out)
    assert m, f"campos nao encontrados:\n{out}"
    assert int(m.group(1)) == 7
    assert int(m.group(2)) == 28   # 7 arquivos x 4 linhas


def test_diagnostico_forca_fragmento_e_loga_progresso(
    tmp_raiz: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """--diagnostico precisa: (1) forcar o loop fragmento-a-fragmento mesmo
    com modo_leitura='lote' (o default), (2) logar progresso a cada 25
    arquivos, (3) logar o resto final mesmo quando o total nao e' multiplo
    de 25."""
    curated = tmp_raiz.parent / "curated"
    _escrever_dia_trade(tmp_raiz, "2026-08-14", "WINFUT", n_arquivos=60)

    totais = curar_trades(tmp_raiz, curated, modo_leitura="lote", diagnostico=True)
    out = capsys.readouterr().out

    assert "curate.leitura_progresso" in out
    import re
    marcas = re.findall(r"arquivos_lidos=(\d+)", out)
    assert marcas == ["25", "50", "60"], (
        f"esperava progresso em 25, 50 e o resto (60) -- veio {marcas}")
    assert totais["gravadas"] == 120   # 60 arquivos x 2 linhas


def test_diagnostico_forca_fragmento_mesmo_sem_pedir_modo_fragmento(
    tmp_raiz: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """diagnostico=True com modo_leitura='lote' (o default) NAO pode chamar
    dataset.to_table() em lote -- senao o progresso por fragmento nunca
    apareceria no cenario real que motivou o pedido."""
    curated = tmp_raiz.parent / "curated"
    _escrever_dia_trade(tmp_raiz, "2026-08-14", "WINFUT", n_arquivos=10)

    import profittape.tools.curate as curate_mod

    chamadas: list[dict[str, object]] = []
    original_fabrica = curate_mod.ds.dataset

    def _fabrica_espia(*a: object, **k: object) -> object:
        return _DatasetEspiao(original_fabrica(*a, **k), chamadas)

    monkeypatch.setattr(curate_mod.ds, "dataset", _fabrica_espia)

    curar_trades(tmp_raiz, curated, modo_leitura="lote", diagnostico=True)

    assert chamadas == [], (
        "dataset.to_table() foi chamado com diagnostico=True -- deveria "
        "ter forcado o loop fragmento-a-fragmento")


def test_progresso_conta_arquivos_pulados_tambem(
    tmp_raiz: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Um arquivo corrompido no meio nao pode fazer a contagem de progresso
    perder o passo -- 'arquivos_lidos' conta TENTATIVAS (i do enumerate),
    nao so' sucessos, senao o total no ultimo log nao bateria com
    arquivos_total."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    curated = tmp_raiz.parent / "curated"
    _escrever_dia_trade(tmp_raiz, "2026-08-14", "WINFUT",
                       n_arquivos=30, linhas_por_arquivo=2)

    ruim = tmp_raiz / "trade" / "dt=2026-08-14" / "sym=WINFUT" / "part-9999.parquet"
    cols = dict(ts_ns=[999000], ts_recv_ns=[999], symbol=["WINFUT"],
                exchange=["F"], trade_id=[999], price=[9.0],
                volume_financeiro=[1.0], quantidade=[1],
                agente_comprador=[3], agente_vendedor=[85],
                trade_type=[2], is_edit=[False])
    pq.write_table(pa.table(cols), ruim)
    b = bytearray(ruim.read_bytes())
    for i in range(50, min(80, len(b) - 8)):
        b[i] = 0xFF
    ruim.write_bytes(bytes(b))

    curar_trades(tmp_raiz, curated, diagnostico=True)
    out = capsys.readouterr().out

    import re
    marcas = re.findall(r"arquivos_lidos=(\d+)", out)
    assert marcas[-1] == "31"          # 30 boas + 1 podre = 31 tentativas
    assert "curate.arquivo_pulado" in out


def test_curate_le_por_simbolo_nao_o_dia_inteiro_junto(
    tmp_raiz: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A mudanca central de 2026-09-10c: dois runs identicos de --diagnostico
    travaram na MESMA posicao da lista combinada (~200-225 de 318), o
    segundo MAIS LENTO -- descarta cache e contencao pontual, aponta pra
    arquivos especificos que rglob() sempre encontra naquela posicao (um
    SIMBOLO, dado que as pastas sym=* sao percorridas em ordem). Ler por
    (dia, simbolo) faz esse simbolo aparecer nomeado.

    Prova pelo dataset PASSADO a cada chamada de ds.dataset(): cada chamada
    precisa conter arquivos de UM SO' simbolo -- nunca os dois misturados.
    """
    _escrever_dia_trade(tmp_raiz, "2026-08-14", "WINFUT", n_arquivos=5)
    _escrever_dia_trade(tmp_raiz, "2026-08-14", "PETR4", n_arquivos=3)
    curated = tmp_raiz.parent / "curated"

    import profittape.tools.curate as curate_mod

    listas_de_arquivos: list[list[str]] = []
    original_fabrica = curate_mod.ds.dataset

    def _fabrica_espia(arquivos: list[str], *a: object, **k: object) -> object:
        listas_de_arquivos.append(list(arquivos))
        return original_fabrica(arquivos, *a, **k)

    monkeypatch.setattr(curate_mod.ds, "dataset", _fabrica_espia)

    totais = curar_trades(tmp_raiz, curated)

    assert len(listas_de_arquivos) == 2, (
        "esperava exatamente 2 chamadas a ds.dataset() -- uma por simbolo, "
        f"nao o dia inteiro de uma vez; veio {len(listas_de_arquivos)}")
    for lista in listas_de_arquivos:
        simbolos_na_lista = {"WINFUT" if "sym=WINFUT" in p else "PETR4"
                             for p in lista}
        assert len(simbolos_na_lista) == 1, (
            f"uma chamada misturou simbolos: {lista}")
    assert totais["particoes"] == 2       # (dia, WINFUT) + (dia, PETR4)
    assert totais["gravadas"] == 5 * 2 + 3 * 2   # 2 linhas/arquivo cada


def test_simbolo_corrompido_nao_contamina_outro_simbolo_saudavel(
    tmp_raiz: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Antes da v2.10c, um arquivo podre em QUALQUER simbolo derrubava a
    leitura em lote do DIA INTEIRO (todos os simbolos misturados), caindo
    no fallback lento para o dia todo. Agora o fallback e' escopado ao
    simbolo podre -- o simbolo saudavel nem passa pelo caminho lento."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    curated = tmp_raiz.parent / "curated"
    _escrever_dia_trade(tmp_raiz, "2026-08-14", "WINFUT", n_arquivos=10)
    _escrever_dia_trade(tmp_raiz, "2026-08-14", "PETR4", n_arquivos=5)

    ruim = tmp_raiz / "trade" / "dt=2026-08-14" / "sym=PETR4" / "part-9999.parquet"
    cols = dict(ts_ns=[999000], ts_recv_ns=[999], symbol=["PETR4"],
                exchange=["F"], trade_id=[999], price=[9.0],
                volume_financeiro=[1.0], quantidade=[1],
                agente_comprador=[3], agente_vendedor=[85],
                trade_type=[2], is_edit=[False])
    pq.write_table(pa.table(cols), ruim)
    b = bytearray(ruim.read_bytes())
    for i in range(50, min(80, len(b) - 8)):
        b[i] = 0xFF
    ruim.write_bytes(bytes(b))

    totais = curar_trades(tmp_raiz, curated)
    out = capsys.readouterr().out

    assert totais["gravadas"] == 20 + 10   # WINFUT 10x2 + PETR4 5x2 (podre fora)
    # o aviso de fallback e o arquivo pulado tem que citar PETR4, nunca WINFUT
    assert "symbol=PETR4" in out
    assert "curate.arquivo_pulado" in out
    # WINFUT (saudavel) nunca deveria precisar do fallback lento
    linhas_winfut = [linha for linha in out.splitlines() if "symbol=WINFUT" in linha]
    assert not any("leitura_em_lote_falhou" in linha for linha in linhas_winfut)


def test_filtro_por_simbolo_processa_so_o_pedido(tmp_raiz: Path) -> None:
    """Pedido direto do operador (2026-09-10): isolar UM simbolo suspeito
    sem esperar o dia inteiro (WINFUT/WDOFUT com 10x mais volume que os
    outros -- o teste que decide se e' so' volume ou trava de verdade)."""
    curated = tmp_raiz.parent / "curated"
    _escrever_dia_trade(tmp_raiz, "2026-08-14", "WINFUT", n_arquivos=5)
    _escrever_dia_trade(tmp_raiz, "2026-08-14", "PETR4", n_arquivos=3)

    totais = curar_trades(tmp_raiz, curated, simbolo_filtro="WINFUT")

    assert totais["particoes"] == 1
    assert totais["gravadas"] == 10          # so' WINFUT: 5 arquivos x 2
    assert not (curated / "trade" / "dt=2026-08-14" / "sym=PETR4").exists()
    assert (curated / "trade" / "dt=2026-08-14" / "sym=WINFUT").exists()


def test_filtro_por_dia_processa_so_o_pedido(tmp_raiz: Path) -> None:
    curated = tmp_raiz.parent / "curated"
    _escrever_dia_trade(tmp_raiz, "2026-08-14", "WINFUT", n_arquivos=3)
    _escrever_dia_trade(tmp_raiz, "2026-08-15", "WINFUT", n_arquivos=4)

    totais = curar_trades(tmp_raiz, curated, dia_filtro="2026-08-14")

    assert totais["particoes"] == 1
    assert totais["gravadas"] == 6           # so' 08-14: 3 arquivos x 2
    assert not (curated / "trade" / "dt=2026-08-15").exists()


def test_filtros_dia_e_simbolo_sao_combinaveis(tmp_raiz: Path) -> None:
    curated = tmp_raiz.parent / "curated"
    _escrever_dia_trade(tmp_raiz, "2026-08-14", "WINFUT", n_arquivos=3)
    _escrever_dia_trade(tmp_raiz, "2026-08-14", "PETR4", n_arquivos=2)
    _escrever_dia_trade(tmp_raiz, "2026-08-15", "WINFUT", n_arquivos=5)

    totais = curar_trades(tmp_raiz, curated,
                          dia_filtro="2026-08-14", simbolo_filtro="WINFUT")

    assert totais["particoes"] == 1
    assert totais["gravadas"] == 6           # so' (08-14, WINFUT): 3x2
    assert not (curated / "trade" / "dt=2026-08-14" / "sym=PETR4").exists()
    assert not (curated / "trade" / "dt=2026-08-15").exists()


def test_sem_filtro_continua_processando_tudo(tmp_raiz: Path) -> None:
    """None (default) nos dois filtros precisa continuar identico ao
    comportamento de antes -- ninguem que nao usa a flag pode ser afetado."""
    curated = tmp_raiz.parent / "curated"
    _escrever_dia_trade(tmp_raiz, "2026-08-14", "WINFUT", n_arquivos=3)
    _escrever_dia_trade(tmp_raiz, "2026-08-14", "PETR4", n_arquivos=2)
    _escrever_dia_trade(tmp_raiz, "2026-08-15", "WINFUT", n_arquivos=4)

    totais = curar_trades(tmp_raiz, curated)

    assert totais["particoes"] == 3          # (14,WINFUT) (14,PETR4) (15,WINFUT)
    assert totais["gravadas"] == 6 + 4 + 8


def test_dia_filtro_inexistente_da_erro_claro(tmp_raiz: Path) -> None:
    curated = tmp_raiz.parent / "curated"
    _escrever_dia_trade(tmp_raiz, "2026-08-14", "WINFUT", n_arquivos=2)
    with pytest.raises(SystemExit, match="2026-01-01"):
        curar_trades(tmp_raiz, curated, dia_filtro="2026-01-01")


def test_simbolo_filtro_inexistente_da_erro_claro(tmp_raiz: Path) -> None:
    curated = tmp_raiz.parent / "curated"
    _escrever_dia_trade(tmp_raiz, "2026-08-14", "WINFUT", n_arquivos=2)
    with pytest.raises(SystemExit, match="XPTO99"):
        curar_trades(tmp_raiz, curated, simbolo_filtro="XPTO99")


def test_cli_curate_aceita_dia_e_simbolo(tmp_raiz: Path) -> None:
    """Fecha a ponta CLI -- garante que --dia/--simbolo chegam de verdade
    em curar_trades, nao so' existem em curar_trades sozinho."""
    from typer.testing import CliRunner

    from profittape.cli import app
    _escrever_dia_trade(tmp_raiz, "2026-08-14", "WINFUT", n_arquivos=2)
    _escrever_dia_trade(tmp_raiz, "2026-08-14", "PETR4", n_arquivos=2)
    curated = tmp_raiz.parent / "curated"

    r = CliRunner().invoke(app, ["curate", "--raw", str(tmp_raiz),
                                "--curated", str(curated),
                                "--simbolo", "WINFUT"])
    assert r.exit_code == 0, r.output
    assert (curated / "trade" / "dt=2026-08-14" / "sym=WINFUT").exists()
    assert not (curated / "trade" / "dt=2026-08-14" / "sym=PETR4").exists()
