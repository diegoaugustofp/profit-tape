"""
Compactacao de raw (tools/compact.py) -- incidente 2026-09-10: backfill em
micro-lotes de ~15 linhas deixou part-0000 do WINFUT com 519.764 linhas em
34.525 row groups. Cada teste aqui reproduz esse formato com write_batch
repetido, que e' EXATAMENTE como o sink gravava.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from profittape.tools.compact import (
    MANIFESTO,
    SUFIXO_TEMP,
    compactar_raw,
)

HOJE = date(2026, 9, 10)
DIA = "2026-08-14"


def _schema() -> pa.Schema:
    return pa.schema([
        ("ts_ns", pa.int64()), ("ts_recv_ns", pa.int64()), ("symbol", pa.string()),
        ("exchange", pa.string()), ("trade_id", pa.int64()), ("price", pa.float64()),
        ("volume_financeiro", pa.float64()), ("quantidade", pa.int64()),
        ("agente_comprador", pa.int32()), ("agente_vendedor", pa.int32()),
        ("trade_type", pa.int32()), ("is_edit", pa.bool_()),
    ])


def _batch(ids: list[int], symbol: str) -> pa.RecordBatch:
    n = len(ids)
    s = _schema()
    cols = [
        [1000 + k for k in ids], list(ids), [symbol] * n, ["F"] * n, list(ids),
        [float(k) for k in ids], [1.0] * n, [1] * n, [3] * n, [85] * n, [2] * n,
        [False] * n,
    ]
    return pa.record_batch([pa.array(c, type=f.type) for c, f in zip(cols, s, strict=True)],
                           schema=s)


def _escrever_fragmentado(raiz: Path, dia: str, symbol: str, n_arquivos: int,
                          lotes_por_arquivo: int, linhas_por_lote: int = 15,
                          stream: str = "trade") -> Path:
    """Reproduz o formato do incidente: um row group por write_batch."""
    d = raiz / stream / f"dt={dia}" / f"sym={symbol}"
    d.mkdir(parents=True, exist_ok=True)
    prox = 1
    for i in range(n_arquivos):
        w = pq.ParquetWriter(d / f"part-{i:04d}.parquet", _schema(),
                             compression="zstd", write_statistics=True)
        for _ in range(lotes_por_arquivo):
            ids = list(range(prox, prox + linhas_por_lote))
            prox += linhas_por_lote
            w.write_batch(_batch(ids, symbol))
        w.close()
    return d


def _row_groups(pasta: Path) -> dict[str, int]:
    return {p.name: pq.ParquetFile(p).metadata.num_row_groups
            for p in sorted(pasta.glob("*.parquet"))}


def _ler_ordenado(pasta: Path) -> pa.Table:
    import pyarrow.dataset as ds
    t = ds.dataset([str(p) for p in sorted(pasta.glob("*.parquet"))],
                   format="parquet").to_table()
    return t.sort_by("trade_id")


def test_compactacao_reduz_row_groups_preservando_todas_as_linhas(tmp_raiz: Path) -> None:
    """O caso do incidente em miniatura: 4 arquivos x 60 row groups de 15
    linhas = 240 row groups / 3.600 linhas -> deve virar 1 arquivo, 1 row
    group, mesmas 3.600 linhas, mesmo conteudo."""
    d = _escrever_fragmentado(tmp_raiz, DIA, "WINFUT", n_arquivos=4, lotes_por_arquivo=60)
    antes = _ler_ordenado(d)
    assert sum(_row_groups(d).values()) == 240

    totais = compactar_raw(tmp_raiz, hoje=HOJE)

    rg = _row_groups(d)
    assert rg == {"part-0004.parquet": 1}, rg     # indice novo, nunca colide
    assert totais["particoes"] == 1
    assert totais["row_groups_antes"] == 240
    assert totais["row_groups_depois"] == 1
    assert totais["arquivos_antes"] == 4
    assert totais["arquivos_depois"] == 1
    assert totais["linhas"] == 3600
    depois = _ler_ordenado(d)
    assert depois.equals(antes), "conteudo mudou -- compact NAO pode alterar dado"
    assert depois.schema.equals(antes.schema)
    # estatistica por coluna preservada (pulo de row group por ts_ns na leitura)
    meta = pq.ParquetFile(d / "part-0004.parquet").metadata
    assert meta.row_group(0).column(0).statistics is not None
    assert meta.row_group(0).column(0).compression == "ZSTD"
    assert not list(d.glob(f"*{SUFIXO_TEMP}"))
    assert not (d / MANIFESTO).exists()


def test_row_group_size_explicito_e_respeitado_e_max_rows_per_file_tambem(tmp_raiz: Path) -> None:
    """row_group_size controla o row group DENTRO do arquivo; max_rows_per_file
    controla o arquivo. 3.600 linhas, arquivo de 2.000, row group de 500 ->
    2 arquivos (2000 + 1600) com 4 + 4 row groups."""
    d = _escrever_fragmentado(tmp_raiz, DIA, "WINFUT", n_arquivos=4, lotes_por_arquivo=60)
    totais = compactar_raw(tmp_raiz, hoje=HOJE, row_group_size=500, max_rows_per_file=2000)
    rg = _row_groups(d)
    assert rg == {"part-0004.parquet": 4, "part-0005.parquet": 4}, rg
    assert totais["linhas"] == 3600
    assert pq.ParquetFile(d / "part-0004.parquet").metadata.num_rows == 2000
    assert pq.ParquetFile(d / "part-0005.parquet").metadata.num_rows == 1600


def test_recusa_row_group_maior_que_arquivo() -> None:
    with pytest.raises(ValueError, match="nao pode exceder"):
        compactar_raw(Path("/nao/importa"), row_group_size=10, max_rows_per_file=5)


def test_particao_com_inprogress_e_pulada_sem_abortar_as_outras(tmp_raiz: Path) -> None:
    """Regra do curate, mas por PARTICAO: .inprogress = escrita em andamento
    (ou sobra nao triada). A particao suja fica intocada; a saudavel do
    mesmo dia e' compactada normalmente."""
    suja = _escrever_fragmentado(tmp_raiz, DIA, "WINFUT", n_arquivos=2, lotes_por_arquivo=10)
    (suja / "part-0002.parquet.inprogress").write_bytes(b"PAR1 parcial")
    sadia = _escrever_fragmentado(tmp_raiz, DIA, "PETR4", n_arquivos=2, lotes_por_arquivo=10)
    rg_suja_antes = _row_groups(suja)

    totais = compactar_raw(tmp_raiz, hoje=HOJE)

    assert totais["puladas_inprogress"] == 1
    assert totais["particoes"] == 1
    assert _row_groups(suja) == rg_suja_antes          # nada tocado
    assert (suja / "part-0002.parquet.inprogress").exists()
    assert _row_groups(sadia) == {"part-0002.parquet": 1}


def test_dia_corrente_nunca_e_compactado(tmp_raiz: Path) -> None:
    """Mesmo sem .inprogress no disco AGORA, o recorder pode abrir um arquivo
    novo no dia de hoje a qualquer segundo."""
    hoje_str = HOJE.isoformat()
    d_hoje = _escrever_fragmentado(tmp_raiz, hoje_str, "WINFUT", 2, 10)
    d_ontem = _escrever_fragmentado(tmp_raiz, "2026-09-09", "WINFUT", 2, 10)
    antes = _row_groups(d_hoje)
    totais = compactar_raw(tmp_raiz, hoje=HOJE)
    assert totais["puladas_dia_corrente"] == 1
    assert _row_groups(d_hoje) == antes
    assert _row_groups(d_ontem) == {"part-0002.parquet": 1}


def test_pula_arquivo_com_zstd_corrompido_sem_perder_a_particao(
    tmp_raiz: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Espelho de test_curate_pula_arquivo_com_zstd_corrompido: footer valido,
    row group podre por dentro. O arquivo ruim FICA no disco (evidencia; e'
    a quarentena que trata), os sadios sao compactados."""
    d = _escrever_fragmentado(tmp_raiz, DIA, "WINFUT", n_arquivos=3, lotes_por_arquivo=10)
    ruim = d / "part-0001.parquet"
    b = bytearray(ruim.read_bytes())
    for i in range(50, min(80, len(b) - 8)):
        b[i] = 0xFF
    ruim.write_bytes(bytes(b))
    bytes_ruim = ruim.read_bytes()

    totais = compactar_raw(tmp_raiz, hoje=HOJE)

    assert totais["particoes"] == 1
    assert totais["arquivos_pulados"] == 1
    assert totais["linhas"] == 300                      # 2 arquivos x 150
    assert ruim.exists() and ruim.read_bytes() == bytes_ruim
    assert not (d / "part-0000.parquet").exists()
    assert not (d / "part-0002.parquet").exists()
    assert pq.ParquetFile(d / "part-0003.parquet").metadata.num_row_groups == 1
    assert "compact.arquivo_pulado" in capsys.readouterr().out


def test_arquivo_sem_footer_fica_no_disco_e_nao_derruba_a_particao(tmp_raiz: Path) -> None:
    d = _escrever_fragmentado(tmp_raiz, DIA, "WINFUT", n_arquivos=2, lotes_por_arquivo=10)
    (d / "part-0002.parquet").write_bytes(b"lixo sem footer")
    totais = compactar_raw(tmp_raiz, hoje=HOJE)
    assert totais["arquivos_pulados"] == 1
    assert totais["linhas"] == 300
    assert (d / "part-0002.parquet").read_bytes() == b"lixo sem footer"
    assert pq.ParquetFile(d / "part-0003.parquet").metadata.num_row_groups == 1


def test_originais_so_sao_removidos_depois_dos_novos_gravados_e_verificados(
    tmp_raiz: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Atomicidade, lado 'antes do commit': se a escrita do novo falha, os
    originais nao foram tocados e nao sobra temporario."""
    import profittape.tools.compact as mod

    d = _escrever_fragmentado(tmp_raiz, DIA, "WINFUT", n_arquivos=3, lotes_por_arquivo=10)
    antes = _row_groups(d)
    conteudo_antes = _ler_ordenado(d)

    original = mod.pq.write_table

    def _explode(*a: object, **k: object) -> None:
        original(*a, **k)               # grava o temporario de verdade...
        raise OSError("disco cheio")    # ...e falha antes de terminar

    monkeypatch.setattr(mod.pq, "write_table", _explode)
    with pytest.raises(OSError, match="disco cheio"):
        compactar_raw(tmp_raiz, hoje=HOJE)

    assert _row_groups(d) == antes, "originais foram tocados apesar da falha"
    assert not list(d.glob(f"*{SUFIXO_TEMP}")), "temporario ficou para tras"
    assert not (d / MANIFESTO).exists()
    assert _ler_ordenado(d).equals(conteudo_antes)


def test_verificacao_pos_escrita_recusa_novo_com_row_groups_demais(
    tmp_raiz: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O objetivo do comando e' reduzir row groups. Se a escrita produzir
    tantos quanto antes (row_group_size ignorado, ou reencaminhamento em
    micro-lotes), o resultado NAO pode substituir o original."""
    import profittape.tools.compact as mod

    d = _escrever_fragmentado(tmp_raiz, DIA, "WINFUT", n_arquivos=2, lotes_por_arquivo=20)
    antes = _row_groups(d)

    def _write_batch_a_batch(table: pa.Table, where: Path, **k: object) -> None:
        # simula a regressao: micro-lotes de 15 linhas
        w = pq.ParquetWriter(where, table.schema, compression="zstd")
        for b in table.to_batches(max_chunksize=15):
            w.write_batch(b)
        w.close()

    monkeypatch.setattr(mod.pq, "write_table", _write_batch_a_batch)
    with pytest.raises(RuntimeError, match="row groups"):
        compactar_raw(tmp_raiz, hoje=HOJE)
    assert _row_groups(d) == antes
    assert not list(d.glob(f"*{SUFIXO_TEMP}"))


def test_interrupcao_durante_o_commit_e_retomada_na_rodada_seguinte(
    tmp_raiz: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """Atomicidade, lado 'durante o commit': manifesto gravado, um original
    ja' removido, processo morre. A proxima rodada termina o commit ANTES de
    fazer qualquer outra coisa -- sem linha perdida, sem duplicata."""
    import profittape.tools.compact as mod

    d = _escrever_fragmentado(tmp_raiz, DIA, "WINFUT", n_arquivos=3, lotes_por_arquivo=10)
    conteudo_antes = _ler_ordenado(d)

    def _morre_no_meio(pasta: Path, conteudo: dict[str, object]) -> None:
        originais = conteudo["originais"]
        assert isinstance(originais, list)
        (pasta / originais[0]).unlink()          # removeu UM original e caiu
        raise KeyboardInterrupt

    monkeypatch.setattr(mod, "_commit", _morre_no_meio)
    with pytest.raises(KeyboardInterrupt):
        compactar_raw(tmp_raiz, hoje=HOJE)
    monkeypatch.undo()

    # estado intermediario: manifesto + temporario + 2 originais
    assert (d / MANIFESTO).exists()
    assert len(list(d.glob(f"*{SUFIXO_TEMP}"))) == 1
    assert len(list(d.glob("*.parquet"))) == 2
    # nenhum leitor ve duplicata neste estado: so' *.parquet conta, e o
    # compactado ainda esta' invisivel
    parcial = _ler_ordenado(d)
    assert parcial.num_rows == 300

    totais = compactar_raw(tmp_raiz, hoje=HOJE)
    out = capsys.readouterr().out
    assert "compact.retomando_commit" in out
    assert _row_groups(d) == {"part-0003.parquet": 1}
    assert _ler_ordenado(d).equals(conteudo_antes)
    assert not (d / MANIFESTO).exists()
    # a retomada nao conta como reescrita nova, e a particao agora esta'
    # compacta -- reconhecida e pulada
    assert totais["particoes"] == 0
    assert totais["ja_compactas"] == 1


def test_temporario_orfao_sem_manifesto_e_descartado(tmp_raiz: Path) -> None:
    """Crash ANTES do manifesto: originais intactos, sobra .compacting e'
    lixo e nao pode virar .parquet (poderia estar pela metade)."""
    d = _escrever_fragmentado(tmp_raiz, DIA, "WINFUT", n_arquivos=2, lotes_por_arquivo=10)
    (d / f"part-0002.parquet{SUFIXO_TEMP}").write_bytes(b"pela metade")
    compactar_raw(tmp_raiz, hoje=HOJE)
    assert not (d / f"part-0002.parquet{SUFIXO_TEMP}").exists()
    # o orfao sai ANTES da numeracao, entao o indice 0002 e' reutilizado
    assert _row_groups(d) == {"part-0002.parquet": 1}


def test_reexecucao_e_idempotente_reconhece_particao_ja_compacta(tmp_raiz: Path) -> None:
    d = _escrever_fragmentado(tmp_raiz, DIA, "WINFUT", n_arquivos=2, lotes_por_arquivo=10)
    compactar_raw(tmp_raiz, hoje=HOJE)
    estado = {p.name: p.stat().st_mtime_ns for p in d.glob("*.parquet")}
    totais = compactar_raw(tmp_raiz, hoje=HOJE)
    assert totais["particoes"] == 0
    assert totais["ja_compactas"] == 1
    assert {p.name: p.stat().st_mtime_ns for p in d.glob("*.parquet")} == estado


def test_compacta_todos_os_streams_nao_so_trade(tmp_raiz: Path) -> None:
    dt = _escrever_fragmentado(tmp_raiz, DIA, "WINFUT", 2, 10, stream="trade")
    db = _escrever_fragmentado(tmp_raiz, DIA, "WINFUT", 2, 10, stream="book_offer")
    totais = compactar_raw(tmp_raiz, hoje=HOJE)
    assert totais["particoes"] == 2
    assert _row_groups(dt) == {"part-0002.parquet": 1}
    assert _row_groups(db) == {"part-0002.parquet": 1}


def test_filtros_dia_e_simbolo(tmp_raiz: Path) -> None:
    a = _escrever_fragmentado(tmp_raiz, DIA, "WINFUT", 2, 10)
    b = _escrever_fragmentado(tmp_raiz, DIA, "PETR4", 2, 10)
    c = _escrever_fragmentado(tmp_raiz, "2026-08-15", "WINFUT", 2, 10)
    totais = compactar_raw(tmp_raiz, hoje=HOJE, dia_filtro=DIA, simbolo_filtro="WINFUT")
    assert totais["particoes"] == 1
    assert _row_groups(a) == {"part-0002.parquet": 1}
    assert len(_row_groups(b)) == 2 and len(_row_groups(c)) == 2
    with pytest.raises(SystemExit, match="--dia"):
        compactar_raw(tmp_raiz, hoje=HOJE, dia_filtro="1999-01-01")
    with pytest.raises(SystemExit, match="--simbolo"):
        compactar_raw(tmp_raiz, hoje=HOJE, simbolo_filtro="NAOEXISTE")


def test_manifesto_e_legivel_e_lista_originais_e_novos(tmp_raiz: Path,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    """O manifesto e' o que um operador le num crash -- precisa dizer o que
    estava sendo trocado por o que."""
    import profittape.tools.compact as mod

    d = _escrever_fragmentado(tmp_raiz, DIA, "WINFUT", n_arquivos=2, lotes_por_arquivo=10)
    capturado: dict[str, object] = {}

    def _espiao(pasta: Path, conteudo: dict[str, object]) -> None:
        capturado.update(conteudo)
        raise SystemExit("parei")

    monkeypatch.setattr(mod, "_commit", _espiao)
    with pytest.raises(SystemExit):
        compactar_raw(tmp_raiz, hoje=HOJE)
    em_disco = json.loads((d / MANIFESTO).read_text())
    assert em_disco == capturado
    assert em_disco["originais"] == ["part-0000.parquet", "part-0001.parquet"]
    assert em_disco["finais"] == ["part-0002.parquet"]
    assert em_disco["linhas"] == 300


def test_cli_compact_chega_em_compactar_raw(tmp_raiz: Path) -> None:
    from typer.testing import CliRunner

    from profittape.cli import app

    d = _escrever_fragmentado(tmp_raiz, "2020-01-02", "WINFUT", 2, 10)
    r = CliRunner().invoke(app, ["compact", "--raw", str(tmp_raiz), "--row-group-size", "100"])
    assert r.exit_code == 0, r.output
    assert _row_groups(d) == {"part-0002.parquet": 3}     # 300 linhas / 100
    assert "COMPACTACAO" in r.output
    r2 = CliRunner().invoke(app, ["compact", "--raw", str(tmp_raiz),
                                  "--row-group-size", "10", "--max-rows-per-file", "5"])
    assert r2.exit_code != 0
