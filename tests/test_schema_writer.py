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
