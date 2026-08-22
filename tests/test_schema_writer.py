"""Schema e writer: o contrato entre evento e disco."""

from __future__ import annotations

from pathlib import Path

import pyarrow.dataset as ds
import pytest

from profittape.domain.enums import Stream
from profittape.domain.events import BookDelta, Trade
from profittape.domain.schema import schema_for
from profittape.storage.parquet_sink import ParquetSink


@pytest.mark.parametrize(
    ("stream", "tipo"),
    [(Stream.TRADE, Trade), (Stream.BOOK_OFFER, BookDelta)],
)
def test_campos_do_evento_batem_com_o_schema(stream: Stream, tipo: type) -> None:
    """
    Divergencia aqui e' bug que so aparece em producao, no primeiro evento.
    Melhor quebrar em CI.
    """
    assert list(tipo._fields) == [f.name for f in schema_for(stream)]


def _colunas(eventos: list[Trade]) -> dict[str, list]:
    """Mesma transposicao que o writer faz. Extraida para nao repetir em cada teste."""
    return dict(zip(Trade._fields, (list(c) for c in zip(*eventos, strict=True)), strict=True))


def _trade(i: int, symbol: str = "PETR4", ts: int = 1_704_193_200_000_000_000) -> Trade:
    return Trade(
        ts_ns=ts + i * 1_000_000, ts_recv_ns=ts + i * 1_000_000 + 500_000,
        symbol=symbol, exchange="B", trade_id=i, price=30.0 + i * 0.01,
        volume_financeiro=3000.0, quantidade=100,
        agente_comprador=3, agente_vendedor=8, trade_type=2, is_edit=False,
    )


def test_grava_e_le_de_volta(tmp_raiz: Path) -> None:
    sink = ParquetSink(tmp_raiz)
    eventos = [_trade(i) for i in range(500)]
    colunas = _colunas(eventos)
    sink.write(Stream.TRADE, "2024-01-02", "PETR4", colunas)
    sink.close()

    tabela = ds.dataset(tmp_raiz / "trade", format="parquet", partitioning="hive").to_table()
    assert tabela.num_rows == 500
    assert tabela["trade_id"].to_pylist()[:3] == [0, 1, 2]


def test_particao_hive_por_dia_e_simbolo(tmp_raiz: Path) -> None:
    sink = ParquetSink(tmp_raiz)
    for dia, sym in (("2024-01-02", "PETR4"), ("2024-01-02", "VALE3"), ("2024-01-03", "PETR4")):
        eventos = [_trade(i, sym) for i in range(10)]
        colunas = _colunas(eventos)
        sink.write(Stream.TRADE, dia, sym, colunas)
    sink.close()

    caminhos = sorted(str(p.relative_to(tmp_raiz)) for p in tmp_raiz.rglob("*.parquet"))
    assert any("dt=2024-01-02" in c and "sym=PETR4" in c for c in caminhos)
    assert any("dt=2024-01-03" in c for c in caminhos)
    assert len(caminhos) == 3


def test_rotaciona_ao_estourar_o_limite(tmp_raiz: Path) -> None:
    sink = ParquetSink(tmp_raiz, max_rows_per_file=100)
    for _ in range(5):
        eventos = [_trade(i) for i in range(60)]
        colunas = _colunas(eventos)
        sink.write(Stream.TRADE, "2024-01-02", "PETR4", colunas)
    sink.close()
    assert len(list(tmp_raiz.rglob("*.parquet"))) > 1


def test_ticker_com_caractere_invalido_nao_quebra_o_caminho(tmp_raiz: Path) -> None:
    sink = ParquetSink(tmp_raiz)
    eventos = [_trade(0, "PETR/A")]
    colunas = _colunas(eventos)
    sink.write(Stream.TRADE, "2024-01-02", "PETR/A", colunas)
    sink.close()
    assert list(tmp_raiz.rglob("*.parquet"))


def test_inspect_sobrevive_a_dicionarios_divergentes(tmp_raiz: Path, capsys) -> None:
    """
    Regressao: `group_by` sobre coluna dictionary levanta
    `ArrowNotImplementedError: Unifying differing dictionaries` quando ha mais
    de um arquivo com dicionarios distintos.

    Falha que NUNCA aparece no teste de um arquivo so, e SEMPRE aparece no dado
    real. Por isso este teste escreve deliberadamente varias particoes.
    """
    from profittape.tools.inspect import resumir

    sink = ParquetSink(tmp_raiz)
    for sym in ("PETR4", "VALE3", "ITUB4"):
        sink.write(Stream.TRADE, "2024-01-02", sym, _colunas([_trade(i, sym) for i in range(20)]))
    sink.close()

    resumir(tmp_raiz, "trade")
    saida = capsys.readouterr().out
    assert "linhas            : 60" in saida
    assert "PETR4" in saida and "VALE3" in saida and "ITUB4" in saida


def test_arquivo_aberto_tem_sufixo_inprogress(tmp_raiz: Path) -> None:
    """
    Regressao do incidente real: processo morto a forca deixou um .parquet sem
    footer indistinguivel de um pronto. Com o sufixo, incompleto se declara.
    """
    sink = ParquetSink(tmp_raiz)
    sink.write(Stream.TRADE, "2024-01-02", "PETR4", _colunas([_trade(0)]))

    assert list(tmp_raiz.rglob("*.parquet")) == []          # nada "pronto" ainda
    assert len(list(tmp_raiz.rglob("*.inprogress"))) == 1

    sink.close()
    assert len(list(tmp_raiz.rglob("*.parquet"))) == 1      # renomeado no close
    assert list(tmp_raiz.rglob("*.inprogress")) == []


def test_inspect_ignora_corrompido_e_lista_o_caminho(tmp_raiz: Path, capsys) -> None:
    from profittape.tools.inspect import resumir

    sink = ParquetSink(tmp_raiz)
    sink.write(Stream.TRADE, "2024-01-02", "PETR4", _colunas([_trade(i) for i in range(30)]))
    sink.close()

    podre = tmp_raiz / "trade" / "dt=2024-01-02" / "sym=VALE3"
    podre.mkdir(parents=True)
    (podre / "part-0000.parquet").write_bytes(b"PAR1\x00\x00truncado-sem-footer")

    resumir(tmp_raiz, "trade")
    out = capsys.readouterr().out
    assert "CORROMPIDO" in out
    assert "sym=VALE3" in out
    assert "linhas            : 30" in out   # o valido foi lido normalmente


def test_curate_recusa_rodar_com_inprogress(tmp_path: Path) -> None:
    """Curar durante uma escrita produziria curated parcial que parece completo."""
    import pytest as _pytest

    from profittape.tools.curate import curar_trades

    raw = tmp_path / "raw"
    sink = ParquetSink(raw)
    sink.write(Stream.TRADE, "2024-01-02", "PETR4", _colunas([_trade(0)]))
    # sem close(): o .inprogress fica no disco, como num recorder ativo

    with _pytest.raises(SystemExit, match="inprogress"):
        curar_trades(raw, tmp_path / "curated")
    sink.close()


def test_segundo_processo_nao_colide_nem_sobrescreve(tmp_raiz: Path) -> None:
    """
    Regressao de bug latente: a numeracao de arquivo comecava em 0 a cada
    processo. Um segundo run na mesma particao colidia no rename (Windows) ou
    sobrescrevia em silencio (antes do rename-on-close). A numeracao agora e'
    descoberta no disco.
    """
    s1 = ParquetSink(tmp_raiz)
    s1.write(Stream.TRADE, "2024-01-02", "PETR4", _colunas([_trade(i) for i in range(10)]))
    s1.close()

    s2 = ParquetSink(tmp_raiz)  # processo novo: memoria zerada
    s2.write(Stream.TRADE, "2024-01-02", "PETR4", _colunas([_trade(i) for i in range(7)]))
    s2.close()

    nomes = sorted(p.name for p in tmp_raiz.rglob("*.parquet"))
    assert nomes == ["part-0000.parquet", "part-0001.parquet"]
    total = ds.dataset(tmp_raiz / "trade", format="parquet", partitioning="hive").to_table()
    assert total.num_rows == 17  # nada sobrescrito


def test_colisao_de_trade_id_entre_simbolos_nao_e_duplicata(tmp_raiz: Path, capsys) -> None:
    """
    Regressao: 621.412 falsos positivos num pregao real porque o inspect
    contava trade_id distintos globalmente, quando a sequencia e' POR SIMBOLO.
    """
    from profittape.tools.inspect import resumir

    sink = ParquetSink(tmp_raiz)
    # Mesmos ids 0..19 em dois simbolos: colisao global, zero duplicata real.
    for sym in ("WINFUT", "WDOFUT"):
        sink.write(Stream.TRADE, "2024-01-02", sym,
                   _colunas([_trade(i, sym) for i in range(20)]))
    sink.close()

    resumir(tmp_raiz, "trade")
    out = capsys.readouterr().out
    assert "sem duplicidade" in out
    assert "ATENCAO" not in out


def test_stream_inexistente_falha_listando_os_disponiveis(tmp_raiz: Path) -> None:
    """Regressao: o fallback silencioso auditou a arvore inteira misturada."""
    import pytest as _pytest

    from profittape.tools.inspect import resumir

    sink = ParquetSink(tmp_raiz)
    sink.write(Stream.TRADE, "2024-01-02", "PETR4", _colunas([_trade(0)]))
    sink.close()

    with _pytest.raises(SystemExit, match=r"book_offer.*trade"):
        resumir(tmp_raiz, "book_offer")


def test_mesmo_trade_id_em_dias_diferentes_nao_e_duplicata(tmp_raiz: Path, capsys) -> None:
    """
    Regressao (camada 2 da cebola): trade_id reinicia por dia; ids de hoje
    dentro da faixa de ontem acusavam 214.349 falsos positivos.
    """
    from profittape.tools.inspect import resumir

    sink = ParquetSink(tmp_raiz)
    for dia in ("2024-01-02", "2024-01-03"):
        sink.write(Stream.TRADE, dia, "WINFUT", _colunas([_trade(i) for i in range(15)]))
    sink.close()

    resumir(tmp_raiz, "trade")
    out = capsys.readouterr().out
    assert "sem duplicidade" in out and "ATENCAO" not in out


def test_timestamp_implausivel_nao_derruba_o_inspect(tmp_raiz: Path, capsys) -> None:
    """
    Regressao real: uma linha com ts_ns de 1990 (pacote atFullBook pre-fix,
    ver client.py) fazia ts_recv - ts_ns estourar o cast seguro int64->float64
    do pyarrow ao calcular latencia, derrubando o comando inteiro.
    """
    from profittape.tools.inspect import resumir

    agora = _trade(0).ts_ns
    implausivel = _trade(1, ts=631152000_000_000_000)   # ~1990
    sink = ParquetSink(tmp_raiz)
    sink.write(Stream.TRADE, "2024-01-02", "PETR4",
              _colunas([_trade(0, ts=agora), implausivel]))
    sink.close()

    resumir(tmp_raiz, "trade")            # nao pode levantar
    out = capsys.readouterr().out
    assert "timestamps implausiveis" in out
    assert "1990" in out


def test_inspect_imprime_progresso(tmp_raiz: Path, capsys) -> None:
    """Pedido direto: nao ficar em silencio durante etapas longas."""
    from profittape.tools.inspect import resumir

    sink = ParquetSink(tmp_raiz)
    sink.write(Stream.TRADE, "2024-01-02", "PETR4", _colunas([_trade(0)]))
    sink.close()

    resumir(tmp_raiz, "trade")
    out = capsys.readouterr().out
    assert "Escaneando" in out
    assert "Carregando" in out
    assert "Calculando estatisticas" in out


def test_inspect_distingue_sem_data_por_design_de_erro(tmp_raiz: Path, capsys) -> None:
    """
    Regressao dupla: (1) has_date=False deve produzir ts_ns=0 SEM alarme —
    e' o comportamento normal de deltas de book; (2) achado ao validar isso:
    o inspect nao carregava a coluna has_date, entao SEMPRE caia no ramo de
    alarme mesmo com o dado correto. As duas camadas ficam cobertas aqui.
    """
    from profittape.tools.inspect import resumir

    base = _trade(0).ts_ns
    linhas = []
    for i in range(20):
        ts = base if i < 2 else 0        # so' 2 com data real
        linhas.append(BookDelta(
            ts_ns=ts, ts_recv_ns=base + i * 1000, symbol="WINFUT", exchange="F",
            action=0, side=0, position=i, offer_id=i, price=100.0, quantidade=10,
            agente=3, has_price=True, has_qtd=True, has_date=(i < 2),
        ))
    cols = dict(zip(BookDelta._fields,
                    (list(c) for c in zip(*linhas, strict=True)), strict=True))
    sink = ParquetSink(tmp_raiz)
    sink.write(Stream.BOOK_OFFER, "2024-01-02", "WINFUT", cols)
    sink.close()

    resumir(tmp_raiz, "book_offer")
    out = capsys.readouterr().out
    assert "sem data por evento : 18" in out
    assert "94" in out or "90.0%" in out
    assert "TIMESTAMP INVALIDO" not in out


def test_inspect_mostra_caminho_absoluto(tmp_raiz: Path, capsys, monkeypatch) -> None:
    """
    Regressao: apos mover storage.raiz para outro volume, `inspect data/raw`
    (caminho relativo, esquecido) continuou lendo o diretorio antigo em
    silencio, devolvendo um relatorio de dado ja corrigido com cara de
    incidente antigo. Caminho absoluto no cabecalho torna o descompasso
    imediatamente visivel.
    """
    from profittape.tools.inspect import resumir

    sink = ParquetSink(tmp_raiz)
    sink.write(Stream.TRADE, "2024-01-02", "PETR4", _colunas([_trade(0)]))
    sink.close()

    monkeypatch.chdir(tmp_raiz.parent)
    resumir(Path(tmp_raiz.name), "trade")
    out = capsys.readouterr().out
    assert str(tmp_raiz.resolve()) in out


def test_sink_conta_aberturas_de_arquivo(tmp_raiz: Path) -> None:
    """
    O writer usa este contador para distinguir lote lento por CRIACAO de
    arquivo (spin-up de HDD USB — esperado, info) de lote lento por VAZAO
    (warning de verdade). Observacao do operador: alarme para comportamento
    esperado ensina a ignorar alarmes.
    """
    sink = ParquetSink(tmp_raiz)
    assert sink.aberturas == 0
    sink.write(Stream.TRADE, "2024-01-02", "PETR4", _colunas([_trade(0)]))
    assert sink.aberturas == 1
    sink.write(Stream.TRADE, "2024-01-02", "PETR4", _colunas([_trade(1)]))
    assert sink.aberturas == 1          # mesma particao: nao abre de novo
    sink.write(Stream.TRADE, "2024-01-03", "PETR4", _colunas([_trade(2)]))
    assert sink.aberturas == 2          # particao nova: abre
    sink.close()


def test_inspect_ignora_inprogress_em_vez_de_travar(tmp_raiz: Path, capsys) -> None:
    """
    Incidente real (2026-08-21): sobras .parquet.inprogress de dias
    interrompidos por Ctrl+C duplo faziam o ds.dataset tentar le-las como
    parquet e MORRER ('magic bytes not found'), travando o inspect inteiro.
    Agora o dataset e' montado so' com os .parquet finalizados.
    """
    from profittape.tools.inspect import resumir

    sink = ParquetSink(tmp_raiz)
    sink.write(Stream.TRADE, "2024-01-02", "PETR4", _colunas([_trade(0)]))
    sink.close()
    # Sobra de escrita interrompida, ao lado de um parquet valido.
    lixo = tmp_raiz / "trade" / "dt=2024-01-03" / "sym=WINFUT"
    lixo.mkdir(parents=True)
    (lixo / "part-0000.parquet.inprogress").write_bytes(b"nao sou parquet")

    resumir(tmp_raiz, "trade")            # nao pode levantar
    out = capsys.readouterr().out
    assert "linhas" in out                 # chegou a produzir o relatorio


def test_inspect_pula_arquivo_corrompido_e_continua(tmp_raiz: Path, capsys) -> None:
    """
    Incidente real (2026-08-21): com 100 arquivos de 19 dias vindos de rodadas
    diferentes, um part corrompido pela interrupcao derrubava o inspect
    inteiro no to_table, com traceback cru sem dizer QUAL arquivo. Agora le
    fragmento a fragmento: reporta o problematico por nome e segue com o resto.
    """
    from profittape.tools.inspect import resumir

    sink = ParquetSink(tmp_raiz)
    sink.write(Stream.TRADE, "2024-01-02", "WINFUT", _colunas([_trade(i) for i in range(20)]))
    sink.close()
    # part corrompido ao lado de um valido
    ruim = tmp_raiz / "trade" / "dt=2024-01-03" / "sym=WINFUT"
    ruim.mkdir(parents=True)
    (ruim / "part-0000.parquet").write_bytes(b"PAR1 isto nao e parquet valido")

    resumir(tmp_raiz, "trade")          # nao pode levantar
    out = capsys.readouterr().out
    assert "linhas" in out               # produziu o relatorio
    assert "CORROMPIDO" in out or "ilegiveis" in out   # avisou do arquivo ruim


def test_fsync_no_close_garante_footer_duravel(tmp_raiz: Path, caplog) -> None:
    """
    Incidente critico (2026-08-21): 96 arquivos ficaram sem footer no G: USB
    porque o footer escrito por writer.close() ficou no cache do SO e o rename
    seguinte "teve sucesso" sobre conteudo nao-duravel. O fsync forca o footer
    ao disco antes do rename — o arquivo final sempre termina com PAR1.

    Bug de follow-up (2026-08-22): a 1a versao abria O_RDONLY para o fsync, o
    que falha no Windows com [Errno 9] Bad file descriptor (FlushFileBuffers
    exige direito de escrita) — mas PASSA no Linux do CI, entao escapou ate'
    producao. A correcao abre 'rb+'. O assert de ausencia de sink.fsync_falhou
    ao menos trava a validade da chamada na plataforma de teste.
    """
    import logging
    caplog.set_level(logging.WARNING)

    sink = ParquetSink(tmp_raiz)
    sink.write(Stream.TRADE, "2026-08-14", "WINFUT",
              _colunas([_trade(i) for i in range(20)]))
    caminhos = sink.close()
    assert caminhos
    for c in caminhos:
        dados = Path(c).read_bytes()
        assert list(dados[-4:]) == [80, 65, 82, 49], f"{c} sem footer PAR1"
        assert list(dados[:4]) == [80, 65, 82, 49]
    assert "sink.fsync_falhou" not in caplog.text


def test_quarentena_acha_fossil_preserva_bom(tmp_raiz: Path, capsys) -> None:
    """
    Ferramenta de limpeza (2026-08-22): a era do fsync quebrado deixou
    part-0000 sem footer, e a recaptura criou part-0001 novos AO LADO (a
    numeracao incrementa para nao colidir). A quarentena acha os fosseis sem
    tocar nos bons, e avisa quais dias ficam sem dado.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    from profittape.tools.quarentena import varrer

    # dia com bom + fossil
    d = tmp_raiz / "trade" / "dt=2026-08-14" / "sym=WINFUT"
    d.mkdir(parents=True)
    pq.write_table(pa.table({"a": [1, 2, 3]}), d / "part-0001.parquet")
    (d / "part-0000.parquet").write_bytes(b"PAR1" + b"\x00" * 500)

    varrer(tmp_raiz, remover=False)
    out = capsys.readouterr().out
    assert "1 arquivo(s) SEM footer" in out
    assert "part-0000.parquet" in out
    assert "dry-run" in out
    # o bom continua la'
    assert (d / "part-0001.parquet").exists()

    varrer(tmp_raiz, remover=True)
    assert not (d / "part-0000.parquet").exists()   # fossil apagado
    assert (d / "part-0001.parquet").exists()        # bom preservado


def test_verificacao_de_footer_bloqueia_promocao(tmp_raiz: Path, monkeypatch) -> None:
    """
    INVARIANTE DA REVISAO (2026-08-22): '.parquet' so' existe se o footer foi
    verificado RELENDO o disco. Se a releitura falha, o arquivo permanece
    .inprogress (estruturalmente nao-confiavel) e a falha e' contada — no
    disco que apodrecia footers, isso gritaria no PRIMEIRO arquivo, nao 96
    arquivos depois.
    """
    sink = ParquetSink(tmp_raiz)
    sink.write(Stream.TRADE, "2026-08-14", "WINFUT", _colunas([_trade(0)]))
    monkeypatch.setattr(ParquetSink, "_footer_ok", staticmethod(lambda _p: False))
    caminhos = sink.close()

    assert caminhos == [] or all(".inprogress" in str(c) for c in caminhos)
    assert sink.arquivos_verificados == 0
    assert len(sink.falhas_verificacao) == 1
    sobras = list(tmp_raiz.rglob("*.inprogress"))
    assert len(sobras) == 1                      # ficou marcado, nao promovido
    assert not list(tmp_raiz.rglob("*.parquet")) or all(
        p.name.endswith(".inprogress") for p in tmp_raiz.rglob("*")
        if p.is_file()
    )


def test_verificacao_ok_promove_e_conta(tmp_raiz: Path) -> None:
    """Caminho feliz: footer confere, arquivo promovido, verificado contado."""
    sink = ParquetSink(tmp_raiz)
    sink.write(Stream.TRADE, "2026-08-14", "WINFUT", _colunas([_trade(0)]))
    sink.close()
    assert sink.arquivos_verificados == 1
    assert sink.falhas_verificacao == []
    assert len(list(tmp_raiz.rglob("*.parquet"))) == 1
    assert not list(tmp_raiz.rglob("*.inprogress"))
