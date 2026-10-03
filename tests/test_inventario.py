"""Inventario de dados e coletas em curso (v4.22). Arvore sintetica no layout do sink:
<raiz>/<stream>/dt=AAAA-MM-DD/sym=<ATIVO>/part-NNNN.parquet."""

from __future__ import annotations

import datetime as dt
import itertools
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from typer.testing import CliRunner

from profittape import coletas as C
from profittape import inventario as I

NS = 1_000_000_000
TZ = ZoneInfo("America/Sao_Paulo")
RAIZ = Path(__file__).resolve().parents[1]


def _ns(dia: dt.date, h: int = 10, m: int = 0) -> int:
    return int(dt.datetime(dia.year, dia.month, dia.day, h, m, tzinfo=TZ).timestamp()) * NS


def _parte(raiz: Path, stream: str, ativo: str, dia: dt.date, n: int = 100, recv: str = "vivo",
           seq: int = 0, extra_dias: float = 0.0) -> Path:
    """Parquet de n linhas. recv: 'vivo' (chega no dia), 'importado' (so' em dia+14) ou
    'misto' (metade ao vivo, metade 3 dias depois)."""
    pasta = raiz / stream / f"dt={dia.isoformat()}" / f"sym={ativo}"
    pasta.mkdir(parents=True, exist_ok=True)
    ts = [_ns(dia) + i * NS for i in range(n)]
    if recv == "vivo":
        rv = [t + NS // 20 for t in ts]
    elif recv == "importado":
        rv = [_ns(dia + dt.timedelta(days=14)) + i * NS for i in range(n)]
    else:
        rv = [t + NS // 20 if i < n // 2 else t + 3 * 86400 * NS for i, t in enumerate(ts)]
    arq = pasta / f"part-{seq:04d}.parquet"
    pq.write_table(pa.table({"ts_ns": ts, "ts_recv_ns": rv}), arq, row_group_size=max(1, n // 2))
    return arq


def _arvore(tmp: Path) -> dict[str, Path]:
    d = dt.date
    raw, cur, bak = tmp / "raw", tmp / "curated", tmp / "backup"
    for dia in (d(2026, 9, 22), d(2026, 9, 23), d(2026, 9, 25)):          # 24/09 e' LACUNA
        _parte(raw, "trade", "WDOV26", dia, 100)
        _parte(raw, "trade", "WDOX26", dia, 80)
    _parte(raw, "trade", "WDOX26", d(2026, 10, 1), 80)                    # so' o X26, na virada
    for dia in (d(2026, 9, 22), d(2026, 9, 23)):                          # WINFUT: trade + book
        _parte(raw, "trade", "WINFUT", dia, 1000)
        _parte(raw, "book_offer", "WINFUT", dia, 5000)
        _parte(raw, "tiny_book", "WINFUT", dia, 9000)
    _parte(raw, "trade", "PETRJ49", d(2026, 9, 22), 30)                   # opcao: so' trade
    _parte(cur, "trade", "WINFUT", d(2026, 9, 22), 1000)                  # curated = o dia do raw
    _parte(cur, "trade", "WINFUT", d(2026, 9, 1), 700, recv="importado")  # historico importado
    _parte(cur, "trade", "WINFUT", d(2026, 9, 18), 600, recv="misto")
    _parte(bak, "trade", "WINFUT", d(2026, 9, 2), 650, recv="importado")  # so' no backup
    inprogress = raw / "trade" / "dt=2026-09-22" / "sym=WDOV26" / "part-0001.parquet.inprogress"
    inprogress.write_text("x")
    return {"raw": raw, "curated": cur, "backup": bak}


def test_origem_do_dia_ao_vivo_importado_e_misto() -> None:
    dia = dt.date(2026, 9, 1)
    fim = _ns(dia + dt.timedelta(days=1), 0)
    assert I.classificar_origem(dia, _ns(dia, 9), _ns(dia, 18)) == "ao_vivo"
    assert I.classificar_origem(dia, fim - 1, fim + 1800 * NS) == "ao_vivo"      # 30 min de folga
    assert I.classificar_origem(dia, _ns(dia + dt.timedelta(days=14)),
                                _ns(dia + dt.timedelta(days=14), 12)) == "importado"
    assert I.classificar_origem(dia, _ns(dia, 9), fim + 3 * 86400 * NS) == "misto"
    assert I.classificar_origem(dia, None, None) == "desconhecido"


def test_escanear_le_so_o_rodape_e_ignora_arquivo_em_escrita_e_corrompido(tmp_path: Path) -> None:
    raizes = _arvore(tmp_path)
    ruim = _parte(raizes["raw"], "trade", "WDOV26", dt.date(2026, 9, 23), 10, seq=7)
    ruim.write_bytes(b"isto nao e' parquet")                                # footer inexistente
    df = I.escanear(raizes, nivel="completo")
    v26 = df[(df["ativo"] == "WDOV26") & (df["stream"] == "trade")].set_index("dia")
    assert v26.loc[dt.date(2026, 9, 22), "linhas"] == 100                    # .inprogress fora
    assert v26.loc[dt.date(2026, 9, 22), "arquivos"] == 1
    d23 = v26.loc[dt.date(2026, 9, 23)]
    assert d23["linhas"] == 100 and d23["ilegiveis"] == 1
    assert set(df["camada"]) == {"raw", "curated", "backup"}
    assert I.escanear({"raw": tmp_path / "nao_existe"}).empty
    sem = I.escanear(raizes, nivel="listar")
    assert sem["linhas"].isna().all() and (sem["bytes"] > 0).all()


def test_por_ativo_tipo_origem_periodo_lacuna_e_uniao_das_camadas(tmp_path: Path) -> None:
    df = I.escanear(_arvore(tmp_path), nivel="completo")
    a = I.por_ativo(df).set_index("ativo")
    # WINFUT: trade + book; dias do trade = uniao das camadas (22/09 em raw e curated conta 1 vez)
    w = a.loc["WINFUT"]
    assert w["tipo"] == "trade + book de ofertas" and w["book_dias"] == 2
    assert (w["dias_ofertas"], w["dias_preco"], w["dias_topo"]) == (2, 0, 2)
    assert w["trade_dias"] == 5 and str(w["trade_primeiro"]) == "2026-09-01"
    assert str(w["trade_ultimo"]) == "2026-09-23"
    assert (w["ao_vivo"], w["importado"], w["misto"]) == (2, 2, 1)
    assert w["trade_linhas"] == 1000 + 1000 + 700 + 650 + 600     # 22/09 = a maior entre as camadas
    assert w["camadas"] == "backup, curated, raw"
    # WDO: so' trade; a virada: V26 nao negocia em 01/10; lacuna de 24/09 (quarta) no V26
    v26, x26 = a.loc["WDOV26"], a.loc["WDOX26"]
    assert v26["tipo"] == "só trade" and v26["familia"] == "futuro (contrato)"
    assert v26["trade_dias"] == 3 and x26["trade_dias"] == 4
    # V26 negociou 22, 23 e 25/09 (lacuna: 24/09); X26 tambem 01/10 (lacunas: 24, 28, 29, 30/09)
    assert v26["lacunas"] == 1 and x26["lacunas"] == 4
    assert a.loc["PETRJ49", "familia"] == "opcao PETR" and a.loc["PETRJ49", "tipo"] == "só trade"
    assert I.familia("PETR4") == "acao" and I.familia("WINFUT") == "futuro (serie continua)"
    assert I.familia("VALEJ80") == "opcao VALE" and I.familia("ZZZ") == "outro"
    assert I.dias_uteis_sem_dado({dt.date(2026, 9, 25), dt.date(2026, 9, 28)}) == []
    assert I.dias_uteis_sem_dado({dt.date(2026, 9, 25), dt.date(2026, 9, 29)}) == [
        dt.date(2026, 9, 28)]


def test_cruzamento_da_coleta_conta_o_par_de_contratos_e_os_ausentes(tmp_path: Path) -> None:
    df = I.escanear(_arvore(tmp_path), nivel="completo")
    coletas = {c["id"]: c for c in C.carregar_coletas(RAIZ / "docs" / "coletas.yaml")}
    r = I.cruzar_coleta(coletas["rolagem_wdo"], df, dt.date(2026, 10, 3))
    assert r["ativos"]["WDOV26"]["dias"] == 3 and r["ativos"]["WDOX26"]["dias"] == 4
    assert r["dias_em_comum"] == 3                      # o par: so' 22, 23 e 25/09
    assert str(r["comuns_primeiro"]) == "2026-09-22" and str(r["comuns_ultimo"]) == "2026-09-25"
    assert r["ausentes"] == []
    w = I.cruzar_coleta(coletas["rolagem_win"], df, dt.date(2026, 10, 3))
    assert w["ausentes"] == ["WINV26", "WINZ26"] and w["dias_em_comum"] == 0
    o = I.cruzar_coleta(coletas["opcoes_petr4_out"], df, dt.date(2026, 10, 3))
    assert len(o["ausentes"]) == 13 and o["ativos"]["PETRJ49"]["dias"] == 1
    # 22/09 a 03/10: 9 dias uteis (22-25/09, 28/09-02/10) -- 03/10 e' sabado
    assert o["dias_uteis_esperados"] == 9


def test_relatorio_md_traz_coletas_resumo_lacunas_e_o_aviso_de_nao_diario(tmp_path: Path) -> None:
    raizes = _arvore(tmp_path)
    df = I.escanear(raizes, nivel="completo")
    md = I.relatorio_md(df, C.carregar_coletas(RAIZ / "docs" / "coletas.yaml"),
                        dt.date(2026, 10, 3), raizes, "03/10/2026 18:30 (teste)", None,
                        I.plano(I.listar(raizes), "completo"))
    assert "Nível de varredura:** `completo`" in md and "rodapés abertos:" in md
    assert "NÃO é diário" in md and "03/10/2026 18:30 (teste)" in md
    assert "## Coletas em andamento (declaradas x em disco)" in md
    assert "dias com os dois (o par): 3" in md
    assert "`WINV26`: **sem dado**; `WINZ26`: **sem dado**" in md           # WIN: nenhum dos dois
    assert "**sem dado:** " in md and "PETRV480" in md                      # opcoes: 13 ausentes
    assert "| `WDOV26` | futuro (contrato) | só trade |" in md
    assert "| `WINFUT` | futuro (serie continua) | trade + book de ofertas |" in md
    assert "Livro (dias): ofertas / preço / topo" in md and "| 2 / 0 / 2 |" in md
    assert "## Lacunas no trade" in md and "24/09" in md
    assert "Não varrido: passe `--dumps" in md
    assert "faltam 13 dias corridos" in md                                  # opcoes: fim 16/10
    # raiz que nao existe e' dita, nao escondida
    md2 = I.relatorio_md(I.escanear({"raw": tmp_path / "x"}), [], dt.date(2026, 10, 3),
                         {"raw": tmp_path / "x"}, "c", [])
    assert "(NÃO existe)" in md2 and "Nenhum dado encontrado" in md2


def _prc(data: int, hora: int, barra: int, close: float = 105000.0) -> str:
    """Linha PRCBARRA| no formato congelado de `ntsl/preco_m15.ntsl` (14 campos)."""
    campos = [data, hora, hora, barra, close - 50, close + 100, close - 100, close, 1234, 45.0,
              close - 10, close - 90, 120.0, 130.0]
    return "PRCBARRA|" + "|".join(str(c) for c in campos)


def test_dump_e_o_texto_do_console_do_profit_e_nao_um_csv(tmp_path: Path) -> None:
    """Formato real: linhas `PRCBARRA|1AAMMDD|hora|...` copiadas do console, possivelmente com
    texto antes do prefixo. (A v4.22 esperava CSV com data dd/mm/aaaa: nao reconhecia dump.)"""
    from profittape.research.eas_preco import CAMPOS, carregar_log

    linhas = ["[console] indicador aplicado", "PRCVIDA|1150102|ligado"]
    for data in (1150102, 1150105, 1221230):               # 02/01/2015, 05/01/2015, 30/12/2022
        for k, hora in enumerate((900, 915, 930, 945)):
            linhas.append(("[10:23:01] " if k == 0 else "") + _prc(data, hora, k + 1))
    arq = tmp_path / "win_m15_2015_2022.txt"
    arq.write_text("\n".join(linhas), encoding="utf-8")
    d = I.escanear_dumps(arq)
    assert len(d) == 1 and d[0]["prefixo"] == "PRCBARRA" and d[0]["tipo"] == "preco M15 (barras)"
    assert d[0]["linhas"] == 12 and d[0]["dias"] == 3
    assert d[0]["primeira"] == dt.date(2015, 1, 2) and d[0]["ultima"] == dt.date(2022, 12, 30)
    assert d[0]["por_dia_mediana"] == 4 and d[0]["repetidas"] == 0
    assert d[0]["ativo"] == "WIN (pelo nome do arquivo)"
    assert len(_prc(1150102, 900, 1).split("|")) - 1 == len(CAMPOS)
    # prova cruzada: o parser que as fichas usam le o MESMO arquivo e da' o mesmo periodo
    df, _ = carregar_log(arq)
    assert (df["dia"].min(), df["dia"].max(), df["dia"].nunique(), len(df)) == (
        d[0]["primeira"], d[0]["ultima"], d[0]["dias"], d[0]["linhas"])


def test_dump_sobreposto_repetidas_e_ativo_pelo_preco_e_varios_tipos(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    dolar = [_prc(1250102, h, k + 1, close=5400.0) for k, h in enumerate((900, 915))]
    (tmp_path / "sub" / "historico.log").write_text(
        "\n".join(dolar + dolar[:1]), encoding="utf-8")           # barra 09:00 repetida
    (tmp_path / "abs.txt").write_text(
        "ABSBARRA|1260930|905|905|1|2|3|4|5|6\nABSBARRA|1260930|910|910|1|2|3|4|5|6\n"
        "ABSDIR|1260930|905|evento\n", encoding="utf-8")
    (tmp_path / "leia.txt").write_text("nao e' dump nenhum", encoding="utf-8")
    por = {(x["arquivo"].replace("\\", "/"), x["prefixo"]): x for x in I.escanear_dumps(tmp_path)}
    h = por[("sub/historico.log", "PRCBARRA")]
    assert h["linhas"] == 3 and h["repetidas"] == 1 and h["dias"] == 1
    assert h["ativo"] == "WDO (estimado pelo preco)"
    assert por[("abs.txt", "ABSBARRA")]["tipo"] == "absorcao M5 (barras)"
    barra, evento = por[("abs.txt", "ABSBARRA")], por[("abs.txt", "ABSDIR")]
    assert barra["dias"] == 1 and barra["repetidas"] == 0
    assert evento["tipo"] == "absorcao direcional (eventos)"
    assert evento["repetidas"] is None               # eventos: sem identidade de barra: n/d
    assert not any(k[0] == "leia.txt" for k in por)  # sem linha de dump: nao entra
    assert I._data_ntsl("1150102") == dt.date(2015, 1, 2)
    assert I._data_ntsl("990102") == dt.date(1999, 1, 2)
    assert I._data_ntsl("1151302") is None and I._data_ntsl("abc") is None
    assert I._data_ntsl("") is None


def test_relatorio_explica_o_que_e_dump_e_lista_o_periodo_por_arquivo(tmp_path: Path) -> None:
    arq = tmp_path / "wdo_m15.txt"
    arq.write_text("\n".join(_prc(1150102 + 3 * k, 900 + 15 * b, b + 1, close=3000.0)
                             for k in range(5) for b in range(4)), encoding="utf-8")
    md = I.relatorio_md(pd.DataFrame(columns=I.COLUNAS), [], dt.date(2026, 10, 3), {},
                        "c", I.escanear_dumps(arq))
    assert "não é CSV nem parquet" in md and "O NTSL não escreve o ticker na linha" in md
    assert "| `wdo_m15.txt` | preco M15 (barras) | 15 min | 20 | 5 |" in md and "02/01/2015" in md
    assert "WDO (pelo nome do arquivo)" in md and "Repetidas" in md
    assert "passe `--dumps <pasta ou arquivo>`" in I.relatorio_md(
        pd.DataFrame(columns=I.COLUNAS), [], dt.date(2026, 10, 3), {}, "c", None)
    vazio = I.relatorio_md(pd.DataFrame(columns=I.COLUNAS), [], dt.date(2026, 10, 3), {}, "c", [])
    assert "Nenhuma linha de dump" in vazio


def test_cli_inventario_escreve_md_e_csv_e_avisa_raiz_ausente(tmp_path: Path) -> None:
    from profittape.cli import app

    raizes = _arvore(tmp_path)
    saida, csv = tmp_path / "docs" / "INVENTARIO_DADOS.md", tmp_path / "docs" / "inv.csv"
    r = CliRunner().invoke(app, [
        "inventario-dados", "--raw", str(raizes["raw"]), "--curated", str(raizes["curated"]),
        "--backup", str(raizes["backup"]), "--coletas", str(RAIZ / "docs" / "coletas.yaml"),
        "--nivel", "completo", "--log-record", str(tmp_path / "sem_log.jsonl"),
        "--saida", str(saida), "--csv", str(csv)])
    assert r.exit_code == 0, r.output
    assert "ativo(s) ->" in r.output and saida.exists() and csv.exists()
    assert "ETAPA 1 - listando pastas" in r.output and "vai abrir o rodape de" in r.output
    inv = pd.read_csv(csv)
    assert {"camada", "stream", "ativo", "dia", "linhas", "origem"} <= set(inv.columns)
    dump = tmp_path / "meu_dump.txt"
    dump.write_text(_prc(1150102, 900, 1), encoding="utf-8")
    r3 = CliRunner().invoke(app, [
        "inventario-dados", "--raw", str(raizes["raw"]), "--curated", str(raizes["curated"]),
        "--coletas", str(RAIZ / "docs" / "coletas.yaml"), "--dumps", str(dump),
        "--log-record", str(tmp_path / "sem_log.jsonl"),
        "--saida", str(tmp_path / "d.md"), "--csv", str(tmp_path / "d.csv")])
    assert r3.exit_code == 0 and "preco M15 (barras)" in (tmp_path / "d.md").read_text(
        encoding="utf-8")
    r4 = CliRunner().invoke(app, [
        "inventario-dados", "--raw", str(raizes["raw"]), "--curated", str(raizes["curated"]),
        "--dumps", str(tmp_path / "nao_existe_dump"), "--log-record", str(tmp_path / "x.jsonl"),
        "--saida", str(tmp_path / "e.md"),
        "--csv", str(tmp_path / "e.csv")])
    assert r4.exit_code == 0 and "AVISO: --dumps nao existe" in r4.output
    r2 = CliRunner().invoke(app, [
        "inventario-dados", "--raw", str(tmp_path / "nada"), "--curated", str(tmp_path / "nada2"),
        "--log-record", str(tmp_path / "x.jsonl"),
        "--saida", str(tmp_path / "x.md"), "--csv", str(tmp_path / "x.csv")])
    assert r2.exit_code == 0 and "AVISO: raiz 'raw' nao existe" in r2.output
    assert "Nenhum dado encontrado" in (tmp_path / "x.md").read_text(encoding="utf-8")


# ------------------------------------------------------------------ coletas
def test_coletas_do_registro_estao_ancoradas_nos_documentos_de_origem() -> None:
    """Guarda de deriva: cada fato do coletas.yaml tem o trecho literal no documento de origem."""
    cs = C.carregar_coletas(RAIZ / "docs" / "coletas.yaml")
    assert {c["id"] for c in cs} == {"rolagem_wdo", "rolagem_win", "opcoes_petr4_out"}
    for c in cs:
        origem = RAIZ / c["plano"].split(",")[0]
        texto = origem.read_text(encoding="utf-8")
        assert c["trechos"], c["id"]
        for tr in c["trechos"]:
            assert tr in texto, f"{c['id']}: trecho sumiu de {origem.name}: {tr!r}"
        for k in ("titulo", "hipotese", "ativos", "streams", "proximo_passo", "plano"):
            assert c.get(k), f"{c['id']}: falta {k}"
    wdo = next(c for c in cs if c["id"] == "rolagem_wdo")
    assert wdo["ativos"] == ["WDOV26", "WDOX26"] and wdo["streams"] == ["trade", "tiny_book"]
    assert "o PAR existe em 7 pregoes" in wdo["estado"]
    ops = next(c for c in cs if c["id"] == "opcoes_petr4_out")
    assert len(ops["ativos"]) == 14 and str(ops["fim"]) == "2026-10-16"


def test_situacao_por_prazo_antes_durante_e_depois_do_marco() -> None:
    c = {"desde": dt.date(2026, 9, 22), "fim": dt.date(2026, 10, 16),
         "marco": {"data": dt.date(2026, 10, 16), "rotulo": "venc"}}
    s = C.situacao(c, dt.date(2026, 10, 3))
    assert s["fase"] == "durante" and s["dias_ate_fim"] == 13 and s["dias_desde_inicio"] == 11
    assert "faltam 13 dias corridos" in C.frase_de_situacao(s)
    wdo = {"desde": dt.date(2026, 9, 22), "fim": None,
           "marco": {"data": dt.date(2026, 10, 1), "rotulo": "virada"}}
    assert "o marco passou ha' 2 dias" in C.frase_de_situacao(C.situacao(wdo, dt.date(2026, 10, 3)))
    antes = C.situacao(wdo, dt.date(2026, 9, 29))
    assert antes["fase"] == "durante" and antes["dias_ate_marco"] == 2
    assert C.situacao({"desde": None, "marco": {}}, dt.date(2026, 10, 3))["fase"] == "nao_iniciada"
    assert C.situacao({"desde": dt.date(2026, 9, 1)}, dt.date(2026, 10, 3))["fase"] == "sem_prazo"
    assert C.carregar_coletas(Path("/nao/existe.yaml")) == []


def test_indice_do_diario_mostra_as_coletas_com_contagem_regressiva(tmp_path: Path) -> None:
    from profittape import diario_html as H
    from profittape.diario_metas import carregar_metas
    sys_path = tmp_path / "diario"
    sys_path.mkdir()
    pd.DataFrame({"dia": ["2026-10-01"], "operacoes": [0], "pnl_liquido": [0.0], "stops": [0],
                  "stop_real_sobre_programado_mediano": [None], "gap": [0.0], "fill": [0.0],
                  "atraso_p99": [1.0], "atraso_max": [2.0], "incidentes": [0], "buracos": [0],
                  "fila_max": [1]}).to_csv(sys_path / "dias.csv", index=False)
    raiz = RAIZ / "docs" / "eas"
    html = H.renderizar_indice(sys_path, carregar_metas(raiz / "metas.yaml"), raiz, None, RAIZ,
                               hoje=dt.date(2026, 10, 3))
    assert "Coletas em andamento (dado sem EA)" in html
    assert "Rolagem do WDO pelo PAR CASADO" in html and "WDOV26, WDOX26" in html
    assert "Opcoes de PETR4 de outubro" in html and "14 séries" in html
    assert "faltam 13 dias corridos para o fim" in html and "o marco passou ha&#x27; 2 dias" in html
    assert "NÃO confirmado" not in html or "Rolagem do WIN" in html
    assert "INVENTARIO_DADOS.md" in html and "gerado sob demanda" in html
    assert "NULO PESA CONTRA" in html                                   # leitura declarada antes
    sem = H.renderizar_indice(sys_path, carregar_metas(raiz / "metas.yaml"), None)
    assert "Coletas em andamento" not in sem


def test_pytest_garante_que_a_pasta_de_testes_nao_depende_do_cwd() -> None:
    assert (RAIZ / "docs" / "coletas.yaml").exists() and pytest is not None


# ------------------------------------------------ v4.24: o inventario nao pode travar a maquina
def _conta_aberturas(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    abertos: list[Path] = []
    original = I._rodape

    def espiao(arq: Path) -> tuple[int, int | None, int | None]:
        abertos.append(arq)
        return original(arq)
    monkeypatch.setattr(I, "_rodape", espiao)
    return abertos


def _arvore_grande(tmp: Path, partes_book: int = 30) -> dict[str, Path]:
    raw, cur = tmp / "raw", tmp / "curated"
    for d in range(3):
        dia = dt.date(2026, 9, 22) + dt.timedelta(days=d)
        for a in ("WINFUT", "WDOV26"):
            for k in range(3):
                _parte(raw, "trade", a, dia, 10, seq=k)
            for k in range(partes_book):
                _parte(raw, "book_offer", a, dia, 10, seq=k)
                _parte(raw, "tiny_book", a, dia, 10, seq=k)
            _parte(cur, "trade", a, dia, 30)
    return {"raw": raw, "curated": cur}


def test_nivel_padrao_nunca_abre_book_nem_raw_e_listar_nao_abre_nada(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A v4.23 abria TODOS os parquet de todos os streams (o book e' o grosso do raw), 8 ao mesmo
    tempo: travou a maquina do operador. Padrao agora: so' o rodape de curated/trade."""
    raizes = _arvore_grande(tmp_path)
    abertos = _conta_aberturas(monkeypatch)
    df = I.escanear(raizes, nivel="listar")
    assert abertos == [] and df["linhas"].isna().all() and len(df) == 3 * 2 * 4
    df = I.escanear(raizes)                                    # padrao = leve
    assert len(abertos) == 6 and all("curated" in str(a) for a in abertos)
    assert not any("book" in str(a) or "tiny" in str(a) or "raw" in str(a) for a in abertos)
    cur = df[(df["camada"] == "curated")]
    assert (cur["linhas"] == 30).all() and (cur["origem"] == "ao_vivo").all()
    raw = df[df["camada"] == "raw"]
    assert raw["linhas"].isna().all() and (raw["origem"] == "desconhecido").all()
    assert raw["arquivos"].sum() == 3 * 2 * (3 + 30 + 30)      # listado, nao aberto
    abertos.clear()
    I.escanear(raizes, nivel="trade")
    assert len(abertos) == 6 + 3 * 2 * 3 and not any("book" in str(a) for a in abertos)
    abertos.clear()
    I.escanear(raizes, nivel="completo", teto=10**6)
    assert len(abertos) == 6 + 3 * 2 * (3 + 30 + 30)


def test_teto_de_arquivos_recusa_ANTES_de_abrir_e_o_plano_diz_quanto_abriria(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raizes = _arvore_grande(tmp_path)
    abertos = _conta_aberturas(monkeypatch)
    folhas = I.listar(raizes)
    pl = I.plano(folhas, "completo")
    assert pl["pastas"] == 3 * 2 * 4 and pl["a_abrir"] == pl["arquivos"] == 6 + 3 * 2 * 63
    assert I.plano(folhas, "leve")["a_abrir"] == 6 and I.plano(folhas, "listar")["a_abrir"] == 0
    streams = {(x["camada"], x["stream"]): x for x in pl["por_stream"]}
    assert streams[("raw", "tiny_book")]["arquivos"] == 3 * 2 * 30 and streams[
        ("raw", "tiny_book")]["bytes"] > 0
    with pytest.raises(I.LimiteExcedido) as e:
        I.abrir(folhas, "completo", teto=100)
    assert e.value.a_abrir == pl["a_abrir"] and e.value.teto == 100 and abertos == []
    with pytest.raises(ValueError, match="nivel invalido"):
        I.escolher(folhas, "tudo")


def test_progresso_e_pausa_e_poucas_threads_por_padrao(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import inspect
    import threading

    raizes = _arvore_grande(tmp_path, partes_book=2)
    eventos: list[tuple[str, int, int | None]] = []
    I.escanear(raizes, nivel="completo", teto=10**6, progresso=lambda f, a, t: eventos.append(
        (f, a, t)))
    total = sum(f.n_arquivos for f in I.listar(raizes))
    assert eventos[-1] == ("abrindo rodapes", total, total)       # sempre termina em 100%
    assert any(e[0] == "abrindo rodapes" and e[1] % 250 == 0 for e in eventos) or total < 250
    assert inspect.signature(I.escanear).parameters["threads"].default == 2
    pausas: list[float] = []
    monkeypatch.setattr(I.time, "sleep", lambda s: pausas.append(s))
    I.escanear(raizes, nivel="leve", pausa_ms=7)
    assert pausas == [0.007] * 6
    pico, ativos, trava = [0], [0], threading.Lock()
    original = I._rodape

    def conta(arq: Path) -> tuple[int, int | None, int | None]:
        with trava:
            ativos[0] += 1
            pico[0] = max(pico[0], ativos[0])
        try:
            return original(arq)
        finally:
            with trava:
                ativos[0] -= 1
    monkeypatch.setattr(I, "_rodape", conta)
    I.escanear(raizes, nivel="completo", teto=10**6)
    assert pico[0] <= 2


def test_cli_recusa_com_o_record_escrevendo_e_com_o_teto_estourado(tmp_path: Path) -> None:
    import os
    import time

    from profittape.cli import app

    raizes = _arvore_grande(tmp_path)
    log = tmp_path / "record_diario.jsonl"
    log.write_text("{}\n", encoding="utf-8")                      # mtime = agora: record vivo
    base = ["inventario-dados", "--raw", str(raizes["raw"]), "--curated", str(raizes["curated"]),
            "--log-record", str(log), "--coletas", str(RAIZ / "docs" / "coletas.yaml"),
            "--saida", str(tmp_path / "i.md"), "--csv", str(tmp_path / "i.csv")]
    r = CliRunner().invoke(app, base)
    assert r.exit_code == 2 and "RECUSADO: o record parece estar rodando" in r.output
    assert not (tmp_path / "i.md").exists()                        # nem listou
    velho = time.time() - 3600
    os.utime(log, (velho, velho))                                  # parado ha' 1 h
    r2 = CliRunner().invoke(app, base)
    assert r2.exit_code == 0 and (tmp_path / "i.md").exists()
    saida_leve = r2.output
    assert "vai abrir o rodape de 6 arquivos" in saida_leve and "(teto 20.000; 2 thread(s))" in (
        saida_leve)
    assert "24 pastas, 384 arquivos," in saida_leve                # separadores nao viram ponto
    assert saida_leve.index("ETAPA 1") < saida_leve.index("vai abrir") < saida_leve.index(
        "linha(s)")
    os.utime(log, None)                                            # record vivo de novo
    r3 = CliRunner().invoke(app, [*base, "--forcar", "--nivel", "listar"])
    assert r3.exit_code == 0 and "vai abrir o rodape de 0 arquivos" in r3.output
    os.utime(log, (velho, velho))
    r4 = CliRunner().invoke(app, [*base, "--nivel", "completo", "--max-arquivos", "50"])
    assert r4.exit_code == 2 and "RECUSADO, nada foi aberto" in r4.output
    assert "abriria 384 arquivos (teto 50)" in r4.output
    r5 = CliRunner().invoke(app, [*base, "--nivel", "inexistente"])
    assert r5.exit_code != 0


def test_dumps_streaming_tetos_e_podas(tmp_path: Path) -> None:
    (tmp_path / ".git" / "objects").mkdir(parents=True)
    (tmp_path / ".git" / "objects" / "ab12cd").write_text(_prc(1150102, 900, 1), encoding="utf-8")
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "dentro_do_raw.txt").write_text(_prc(1150102, 900, 1), encoding="utf-8")
    (tmp_path / "sem_extensao").write_text(_prc(1150102, 900, 1), encoding="utf-8")
    (tmp_path / "ok.txt").write_text("\n".join(_prc(1150102 + k, 900, 1) for k in range(4)),
                                     encoding="utf-8")
    nomes = [d["arquivo"] for d in I.escanear_dumps(tmp_path)]
    assert nomes == ["ok.txt"]                       # .git, raw/ e arquivo sem extensao: fora
    grande = tmp_path / "enorme.log"
    grande.write_text(_prc(1150102, 900, 1), encoding="utf-8")
    todos = I.escanear_dumps(tmp_path, limite_bytes=10)
    pulados = [d for d in todos if d["arquivo"] == "enorme.log"]
    assert len(pulados) == 1 and pulados[0]["tipo"].startswith("PULADO") and pulados[0][
        "linhas"] is None
    # pasta com arquivos demais: corta e diz
    muitos = tmp_path / "muitos"
    muitos.mkdir()
    for k in range(I.LIMITE_DUMP_ARQUIVOS + 5):
        (muitos / f"d{k:04d}.txt").write_text("x", encoding="utf-8")
    cortado = I.escanear_dumps(muitos)
    assert cortado[0]["tipo"].startswith("CORTADO")
    # uma passada so': arquivo grande de verdade, linhas de 3 tipos misturadas
    misto = tmp_path / "misto.txt"
    misto.write_text("\n".join(_prc(1150102 + (k % 50), 900 + k, k + 1) if k % 2 else
                              f"ABSBARRA|1260930|{900 + k}|{k}|1|2|3|4|5|6" for k in range(20000)),
                     encoding="utf-8")
    por = {d["prefixo"]: d for d in I.escanear_dumps(misto)}
    assert por["PRCBARRA"]["linhas"] == 10000 and por["ABSBARRA"]["linhas"] == 10000


def _bbs(data: int, hora: int) -> str:
    return f"BBSBARRA|{data}|{hora}|{hora}|1|2|3|4|5"


def test_varios_dumps_deduplicam_pasta_dentro_de_pasta_e_avisam_o_que_nao_existe(
        tmp_path: Path) -> None:
    """O operador passou `--dumps data --dumps data\\dumps_15s`: o Typer guardava so' o ultimo, em
    silencio. Agora todos valem, o arquivo alcancado por dois caminhos entra uma vez, e o que nao
    existe e' dito."""
    data = tmp_path / "data"
    (data / "dumps_15s").mkdir(parents=True)
    (data / "dumps_15s" / "bb_15s.txt").write_text(
        "\n".join(_bbs(1260930, 900 + k) for k in range(5)), encoding="utf-8")
    (data / "m15.txt").write_text(_prc(1150102, 900, 1), encoding="utf-8")
    entradas, avisos = I.escanear_dumps_varios(
        [data, data / "dumps_15s", tmp_path / "nao_existe"])
    bb = [e for e in entradas if e["prefixo"] == "BBSBARRA"]
    assert len(bb) == 1 and bb[0]["linhas"] == 5                  # nao contou duas vezes
    assert bb[0]["arquivo"] == "data/dumps_15s/bb_15s.txt"        # nome com a pasta de origem
    assert {e["prefixo"] for e in entradas} == {"BBSBARRA", "PRCBARRA"}
    assert avisos == [f"--dumps nao existe: {tmp_path / 'nao_existe'}"]
    unico, _ = I.escanear_dumps_varios([data / "dumps_15s"])
    assert unico[0]["arquivo"] == "bb_15s.txt"                    # um destino: nome como antes


def test_cli_le_todos_os_dumps_repetidos_e_diz_o_que_encontrou(tmp_path: Path) -> None:
    from profittape.cli import app

    raizes = _arvore_grande(tmp_path, partes_book=1)
    a, b = tmp_path / "dumps_a", tmp_path / "dumps_b"
    a.mkdir()
    b.mkdir()
    (a / "bb.txt").write_text(_bbs(1260930, 900), encoding="utf-8")
    (b / "m15.txt").write_text(_prc(1150102, 900, 1), encoding="utf-8")
    base = ["inventario-dados", "--raw", str(raizes["raw"]), "--curated", str(raizes["curated"]),
            "--log-record", str(tmp_path / "sem.jsonl"), "--coletas",
            str(RAIZ / "docs" / "coletas.yaml"), "--saida", str(tmp_path / "i.md"),
            "--csv", str(tmp_path / "i.csv")]
    r = CliRunner().invoke(app, [*base, "--dumps", str(a), "--dumps", str(b)])
    assert r.exit_code == 0, r.output
    assert ("dumps: 2 tipo(s) de linha em 2 arquivo(s), lidos em 2 caminho(s): "
            "BBSBARRA, PRCBARRA") in r.output
    md = (tmp_path / "i.md").read_text(encoding="utf-8")
    assert "dumps_a/bb.txt" in md and "dumps_b/m15.txt" in md
    vazio = tmp_path / "vazio"
    vazio.mkdir()
    (vazio / "nada.txt").write_text("sem linha de dump", encoding="utf-8")
    r2 = CliRunner().invoke(app, [*base, "--dumps", str(vazio)])
    assert r2.exit_code == 0 and "AVISO: nenhuma linha de dump" in r2.output
    r3 = CliRunner().invoke(app, [*base, "--dumps", str(tmp_path / "x"), "--dumps", str(a)])
    assert "AVISO: --dumps nao existe" in r3.output and "1 tipo(s) de linha" in r3.output
    sem = CliRunner().invoke(app, base)
    assert sem.exit_code == 0 and "dumps:" not in sem.output


# ------------------------------------------- v4.25: erros do primeiro relatorio real do operador
def _arvore_backup_e_curated(tmp: Path) -> dict[str, Path]:
    """O caso real: o MESMO dia existe no backup (rodape nao aberto no nivel leve) e no curated."""
    d = dt.date
    cur, bak = tmp / "curated", tmp / "backup"
    for dia, recv in ((d(2026, 9, 1), "importado"), (d(2026, 9, 18), "misto"),
                      (d(2026, 9, 22), "vivo"), (d(2026, 9, 23), "vivo")):
        for a in ("WINFUT", "PETR4"):
            _parte(cur, "trade", a, dia, 100, recv=recv)
            _parte(bak, "trade", a, dia, 100, recv=recv)
            _parte(bak, "tiny_book", a, dia, 500)
    _parte(bak, "book_offer", "PETR4", d(2026, 9, 22), 800)
    _parte(bak, "book_offer", "PETR4", d(2026, 9, 23), 800)
    return {"curated": cur, "backup": bak}


def test_origem_do_dia_vem_do_curated_mesmo_quando_o_backup_tem_o_mesmo_dia(
        tmp_path: Path) -> None:
    """v4.24 ficava com a linha do backup (rodape fechado => origem desconhecida) e jogava fora a
    do curated: o relatorio real saiu com 'ao vivo / importado / misto = 0 / 0 / 0' no ativo."""
    raizes = _arvore_backup_e_curated(tmp_path)
    df = I.escanear(raizes)                                        # nivel leve
    assert set(df[df["camada"] == "backup"]["origem"]) == {"desconhecido"}
    a = I.por_ativo(df).set_index("ativo")
    w = a.loc["WINFUT"]
    assert (w["ao_vivo"], w["importado"], w["misto"], w["desconhecido"]) == (2, 1, 1, 0)
    assert w["trade_linhas"] == 400 and w["trade_dias"] == 4
    plano = I.plano(I.listar(raizes), "leve")
    md = I.relatorio_md(df, [], dt.date(2026, 10, 3), raizes, "c", None, plano)
    assert "| 2 / 1 / 1 / 0 |" in md                               # a coluna nao mente mais
    # um dia so' no backup (nao compactado) continua contando como desconhecido, nao some
    _parte(raizes["backup"], "trade", "WINFUT", dt.date(2026, 9, 24), 100)
    w2 = I.por_ativo(I.escanear(raizes)).set_index("ativo").loc["WINFUT"]
    assert (w2["ao_vivo"], w2["desconhecido"]) == (2, 1)


def test_tipo_distingue_book_de_ofertas_de_so_topo_e_a_tabela_nao_chama_tudo_de_book(
        tmp_path: Path) -> None:
    raizes = _arvore_backup_e_curated(tmp_path)
    a = I.por_ativo(I.escanear(raizes)).set_index("ativo")
    assert a.loc["PETR4", "tipo"] == "trade + book de ofertas"
    assert (a.loc["PETR4", "dias_ofertas"], a.loc["PETR4", "dias_topo"]) == (2, 4)
    assert a.loc["WINFUT", "tipo"] == "trade + só topo (tiny_book)"  # tiny_book NAO e' profundidade
    assert a.loc["WINFUT", "dias_ofertas"] == 0 and a.loc["WINFUT", "dias_topo"] == 4
    _parte(raizes["backup"], "book_price", "WINFUT", dt.date(2026, 9, 22), 50)
    assert I.por_ativo(I.escanear(raizes)).set_index("ativo").loc["WINFUT", "tipo"] == (
        "trade + book de preço")
    md = I.relatorio_md(I.escanear(raizes), [], dt.date(2026, 10, 3), raizes, "c", None)
    assert "**só topo** = só `tiny_book`" in md


def test_relatorio_nao_mostra_zero_linhas_onde_o_rodape_nao_foi_aberto(tmp_path: Path) -> None:
    raizes = _arvore_backup_e_curated(tmp_path)
    df = I.escanear(raizes)
    md = I.relatorio_md(df, [], dt.date(2026, 10, 3), raizes, "c", None,
                        I.plano(I.listar(raizes), "leve"))
    assert "| backup | trade | 2 | 01/09/2026 a 23/09/2026 | 8 |" in md
    assert "— (rodapé não aberto)" in md                           # backup nao leu: nao e' "0"
    assert "| curated | trade | 2 | 01/09/2026 a 23/09/2026 | 8 |" in md and "| 800 |" in md
    assert "padrão: abre rodapés só de curated/trade (poucos arquivos: um por dia e ativo)" in md
    assert "(0,0 GB)" in md or "GB); rodapés abertos: 8." in md   # GB com virgula; ajuda intacta


def test_dumps_de_15s_nao_acusam_repetidas_falsas_e_batem_com_o_parser_da_ficha(
        tmp_path: Path) -> None:
    """O dump real do operador (dump20260901.txt) tem 2.249 linhas de BBSBARRA no dia: o relatorio
    v4.24 acusou 1.686 'repetidas' porque usava (dia, hora), e em 15 s quatro barras dividem a mesma
    `hora`. A identidade do parser da ficha e' (dia, current_bar)."""
    from profittape.research.bollinger_scalp import CAMPOS, carregar_log

    def bbs(data: int, hora: int, barra: int) -> str:
        campos = [data, hora, hora, barra, 100.0, 101.0, 99.0, 100.5, 1000, 101.0, 99.0, 50.0,
                  1.0, 1.0]
        return "BBSBARRA|" + "|".join(str(c) for c in campos)

    linhas = []
    barra = 0
    for minuto in range(60):                                       # 4 barras de 15 s por minuto
        for _ in range(4):
            barra += 1
            linhas.append(bbs(1260901, 900 + minuto // 60 * 100 + minuto % 60, barra))
    arq = tmp_path / "dump20260901.txt"
    arq.write_text("\n".join(linhas), encoding="utf-8")
    assert len(CAMPOS) == 14
    df, _ = carregar_log(arq)                                      # o parser da ficha aceita
    assert len(df) == 240
    e = I.escanear_dumps(arq)[0]
    assert e["prefixo"] == "BBSBARRA" and e["linhas"] == 240 and e["dias"] == 1
    assert e["repetidas"] == 0                                     # v4.24 dizia 180
    arq.write_text("\n".join([*linhas, linhas[10]]), encoding="utf-8")   # repeticao de verdade
    assert I.escanear_dumps(arq)[0]["repetidas"] == 1
    # VWAPVP: sem parser que desduplique => n/d, nunca um numero chutado
    vw = tmp_path / "vwap.txt"
    vw.write_text("VWAPVP|1260930|905|1|2\nVWAPVP|1260930|905|1|2\n", encoding="utf-8")
    assert I.escanear_dumps(vw)[0]["repetidas"] is None
    md = I.relatorio_md(pd.DataFrame(columns=I.COLUNAS), [],
                        dt.date(2026, 10, 3), {}, "c", I.escanear_dumps(vw))
    assert "| n/d |" in md and "dia + `current_bar` em PRCBARRA e BBSBARRA" in md


# --------------------------- v4.26: o que o segundo inventario real mostrou (sobreposicao e ativo)
def _prc_br(data: int, hora: int, barra: int, close: str) -> str:
    """PRCBARRA com preco no formato pt-BR do Profit (milhar com ponto, decimal com virgula)."""
    campos = [data, hora, hora, barra, "1,0", "1,0", "1,0", close, 1234, "45,0", "1,0", "1,0",
              "1,0", "1,0"]
    return "PRCBARRA|" + "|".join(str(c) for c in campos)


def _dump(caminho: Path, linhas: list[str]) -> Path:
    caminho.write_text("\n".join(linhas), encoding="utf-8")
    return caminho


def _dias_prc(inicio: int, n: int, close: str, barras: int = 3) -> list[str]:
    """n dias a partir de 1AAMMDD `inicio` (dias fictícios de 1 a 28), `barras` barras por dia."""
    out = []
    for d in range(n):
        data = inicio + d
        for b in range(barras):
            out.append(_prc_br(data, 900 + 15 * b, b + 1, close))
    return out


def test_ativo_provavel_le_preco_em_pt_br_como_o_parser_das_fichas(tmp_path: Path) -> None:
    """v4.25 so' trocava a virgula e falhava em "125.450,00": todo `dump_*` (sem o ticker no nome)
    saiu 'nao consta'."""
    from profittape.research.absorcao_grafico import _numero as numero_do_parser

    for txt in ("125.450,00", "5.432,5", "98765", "1.234.567,89", "0,5"):
        assert I._numero(txt) == numero_do_parser(txt)
    assert I._numero("") is None and I._numero("abc") is None
    win = _dump(tmp_path / "dump_15_22.txt", _dias_prc(1150102, 3, "125.450,00"))
    wdo = _dump(tmp_path / "preco_semana.txt", _dias_prc(1150102, 3, "5.432,50"))
    assert I.escanear_dumps(win)[0]["ativo"] == "WIN (estimado pelo preco)"
    assert I.escanear_dumps(wdo)[0]["ativo"] == "WDO (estimado pelo preco)"
    nome = _dump(tmp_path / "wdo_2026.txt", _dias_prc(1260102, 2, "125.450,00"))
    assert I.escanear_dumps(nome)[0]["ativo"] == "WDO (pelo nome do arquivo)"      # o nome vence
    abs_ = _dump(tmp_path / "absorcao_barra_2025.txt", [
        "ABSBARRA|1250102|905|905|130.100,0|130.200,0|130.000,0|130.150,0|10|5|1|1|1|1|1|1"])
    assert I.escanear_dumps(abs_)[0]["ativo"] == "WIN (estimado pelo preco)"       # close = campo 6


def test_dump_grande_que_e_a_concatenacao_de_tres_e_apontado_nao_somado(tmp_path: Path) -> None:
    """O caso real: dump_15_22 tinha EXATAMENTE as linhas e os dias de dump_2015_19 + dump_2020 +
    dump_2021_22, e a coluna 'repetidas' (so' dentro do arquivo) dizia 0."""
    a = _dias_prc(1150101, 6, "125.450,00")                  # "2015-19"
    b = _dias_prc(1200101, 3, "125.450,00")                  # "2020"
    c = _dias_prc(1210101, 4, "125.450,00")                  # "2021-22"
    _dump(tmp_path / "dump_2015_19.txt", a)
    _dump(tmp_path / "dump_2020.txt", b)
    _dump(tmp_path / "dump_2021_22.txt", c)
    _dump(tmp_path / "dump_15_22.txt", a + b + c)
    entradas, _ = I.escanear_dumps_varios([tmp_path])
    assert all(e["repetidas"] == 0 for e in entradas)          # "repetidas" nao ve isso
    res = I.resumo_dumps(entradas)
    u = res["unicos"][0]
    assert (u["arquivos"], u["dias_unicos"], u["soma_dias"], u["repetidos"]) == (4, 13, 26, 13)
    assert u["ativo"] == "WIN"
    grande = [p for p in res["pares"] if "dump_15_22.txt" in (p["a"], p["b"])]
    assert len(grande) == 3                                     # contra cada um dos tres
    assert {p["comuns"] for p in grande} == {6, 3, 4}
    assert all(p["relacao"] in ("A esta' dentro de B", "B esta' dentro de A") for p in grande)
    assert sum(1 for p in res["pares"]) == 3                    # as partes nao se sobrepoem
    md = I.relatorio_md(pd.DataFrame(columns=I.COLUNAS), [], dt.date(2026, 10, 3), {}, "c",
                        entradas)
    assert "### Dias únicos por tipo e ativo" in md and "| 4 | **13** |" in md
    assert "### Sobreposição entre arquivos" in md and "dump_15_22.txt" in md
    assert "Mesmos dias não provam mesmas barras" in md


def test_arquivo_de_2026_que_contem_o_outro_e_arquivo_complementar_sem_sobreposicao(
        tmp_path: Path) -> None:
    """ABSBARRA 2026: jan_a_abril (81 dias) esta' DENTRO de jan_a_abril_jun_jul (119); maio fica em
    outro arquivo, sem sobreposicao. Soma ingenua = 220 dias; unicos = 139."""
    def abs_(dias: list[int]) -> list[str]:
        return [f"ABSBARRA|{d}|{905 + 5 * b}|{905 + 5 * b}|130.100,0|130.200,0|130.000,0|130.150,0"
                f"|10|5|1|1|1|1|1|1" for d in dias for b in range(3)]
    jan_abr, maio, jun_jul = list(range(1260101, 1260109)), [1260201, 1260202], [
        1260301, 1260302, 1260303]
    _dump(tmp_path / "jan_a_abril.txt", abs_(jan_abr))
    _dump(tmp_path / "jan_a_abril_jun_jul.txt", abs_(jan_abr + jun_jul))
    _dump(tmp_path / "maio.txt", abs_(maio))
    res = I.resumo_dumps(I.escanear_dumps_varios([tmp_path])[0])
    assert len(res["pares"]) == 1
    p = res["pares"][0]
    assert p["comuns"] == 8 and p["relacao"] == "A esta' dentro de B"
    assert {p["a"], p["b"]} == {"jan_a_abril.txt", "jan_a_abril_jun_jul.txt"}   # maio: sem par
    u = res["unicos"][0]
    assert (u["soma_dias"], u["dias_unicos"], u["repetidos"]) == (8 + 11 + 2, 8 + 3 + 2, 8)


def test_win_e_wdo_no_mesmo_periodo_nao_sao_acusados_de_duplicata(tmp_path: Path) -> None:
    """dump_15_22 (WIN) e wdo_2015_22 cobrem os mesmos dias, mas sao ativos diferentes."""
    _dump(tmp_path / "dump_15_22.txt", _dias_prc(1150101, 5, "125.450,00"))
    _dump(tmp_path / "wdo_2015_22.txt", _dias_prc(1150101, 5, "3.250,00"))
    res = I.resumo_dumps(I.escanear_dumps_varios([tmp_path])[0])
    assert res["pares"] == []
    assert {(u["ativo"], u["dias_unicos"]) for u in res["unicos"]} == {("WIN", 5), ("WDO", 5)}
    # ativo NAO identificado: compara com todos e avisa que e' ambiguo
    _dump(tmp_path / "mistério.txt", _dias_prc(1150101, 5, "x"))
    pares = I.resumo_dumps(I.escanear_dumps_varios([tmp_path])[0])["pares"]
    assert len(pares) == 2 and all(p["ambiguo"] for p in pares)
    md = I.relatorio_md(pd.DataFrame(columns=I.COLUNAS), [], dt.date(2026, 10, 3), {}, "c",
                        I.escanear_dumps_varios([tmp_path])[0])
    assert "sem ativo identificado: confirme" in md and "não identificado" in md


def test_resolucao_diferente_nos_mesmos_dias_mostra_barras_por_dia(tmp_path: Path) -> None:
    """Mesmos dias nao provam mesmas barras: o relatorio mostra barras/dia lado a lado."""
    def bbs(dias: list[int], por_dia: int) -> list[str]:
        return [f"BBSBARRA|{d}|{900 + k}|{900 + k}|{k + 1}|1,0|1,0|1,0|125.000,0|10|1|1|1|1|1"
                for d in dias for k in range(por_dia)]
    _dump(tmp_path / "dump_15s_dia.txt", bbs([1260901], 40))
    _dump(tmp_path / "dump_6m.txt", bbs([1260901], 4))
    p = I.resumo_dumps(I.escanear_dumps_varios([tmp_path])[0])["pares"][0]
    assert p["comuns"] == 1 and {p["barras_dia_a"], p["barras_dia_b"]} == {40, 4}
    md = I.relatorio_md(pd.DataFrame(columns=I.COLUNAS), [], dt.date(2026, 10, 3), {}, "c",
                        I.escanear_dumps_varios([tmp_path])[0])
    assert "(1; 40)" in md and "(1; 4)" in md


def test_vocabulario_do_relatorio_nao_crava_datas_de_importacao(tmp_path: Path) -> None:
    """A frase 'foram importados em 15/09' estava fixa no gerador e envelheceu (a v4.25 mostrou 28
    dias importados, nao 14)."""
    md = I.relatorio_md(pd.DataFrame(columns=I.COLUNAS), [], dt.date(2026, 10, 3), {}, "c", None)
    assert "15/09" not in md and "por backfill" in md


# ----------------------------- v4.27: resolucao da barra e buracos (2o inventario real)
def _bbs_dia(data: int, horas: list[int], por_hora: int, primeira_barra: int = 1) -> list[str]:
    """BBSBARRA com `por_hora` barras por hora distinta (15 s em HHMM => 4)."""
    out, barra = [], primeira_barra
    for h in horas:
        for _ in range(por_hora):
            out.append(f"BBSBARRA|{data}|{h}|{h}|{barra}|1,0|1,0|1,0|125.000,0|10|1|1|1|1|1")
            barra += 1
    return out


def _minutos(inicio_h: int, fim_h: int, passo_min: int = 1) -> list[int]:
    return [h * 100 + m for h in range(inicio_h, fim_h) for m in range(0, 60, passo_min)]


def test_resolucao_da_barra_e_inferida_do_proprio_arquivo(tmp_path: Path) -> None:
    from profittape.research.bollinger_scalp import CAMPOS, carregar_log

    assert len(CAMPOS) == 14
    cheio = _bbs_dia(1260901, _minutos(9, 18), 4)                       # 15 s, hora em HHMM
    janela = _bbs_dia(1260902, _minutos(9, 14), 4)                      # 15 s, so' 9h as 14h
    seis_min = _bbs_dia(1260903, _minutos(9, 18, 6), 1)                 # barras de 6 min
    com_seg = [f"BBSBARRA|1260904|{h}|{h}|{i + 1}|1,0|1,0|1,0|125.000,0|10|1|1|1|1|1"
               for i, h in enumerate(h * 10000 + m * 100 + s for h in (9, 10) for m in range(60)
                                     for s in (0, 15, 30, 45))]         # 15 s, hora em HHMMSS
    m5 = [f"ABSBARRA|1260905|{h}|{h}|130.100,0|130.200,0|130.000,0|130.150,0|10|5|1|1|1|1|1|1"
          for h in _minutos(9, 18, 5)]
    m15 = _dias_prc(1150102, 2, "125.450,00", barras=1)                 # 1 barra/dia: nao infere
    for nome, linhas, esperado in (("cheio", cheio, "15 s"), ("janela", janela, "15 s"),
                                   ("seis", seis_min, "6 min"), ("seg", com_seg, "15 s"),
                                   ("m5", m5, "5 min"), ("degenerado", m15, "—")):
        e = I.escanear_dumps(_dump(tmp_path / f"{nome}.txt", linhas))[0]
        assert e["resolucao"] == esperado, (nome, e["resolucao"], e["resolucao_s"])
    df, _ = carregar_log(tmp_path / "janela.txt")      # o parser da ficha aceita o mesmo arquivo
    assert len(df) == 5 * 60 * 4
    assert I._rotulo_resolucao(None) == "—" and I._rotulo_resolucao(900.0) == "15 min"
    assert I._rotulo_resolucao(360.0) == "6 min" and I._rotulo_resolucao(15.0) == "15 s"
    assert I._segundos_do_dia(930) == 9 * 3600 + 30 * 60
    assert I._segundos_do_dia(93015) == 9 * 3600 + 30 * 60 + 15


def test_bollinger_15s_e_6min_nao_se_misturam_nem_viram_duplicata(tmp_path: Path) -> None:
    """O caso real: `dump_..._6m.txt` (16 dias, 95 barras/dia) foi somado aos dumps de 15 s: o
    relatorio v4.26 dizia '16 dias unicos de bollinger' e listava 18 'sobreposicoes' falsas."""
    dia15 = _minutos(9, 18)
    for k, dia in enumerate((1260901, 1260902, 1260903, 1260904, 1260908)):
        _dump(tmp_path / f"dump2026090{k}.txt", _bbs_dia(dia, dia15, 4))
    _dump(tmp_path / "dump_dia_completo.txt", _bbs_dia(1260901, dia15, 4))      # copia de um dia
    _dump(tmp_path / "dump_9h_14h.txt", list(itertools.chain.from_iterable(
        _bbs_dia(d, _minutos(9, 14), 4) for d in (1260901, 1260902, 1260903, 1260904))))
    dias_6m = [1260901 + k for k in range(16)]
    _dump(tmp_path / "dump_6m.txt", list(itertools.chain.from_iterable(
        _bbs_dia(d, _minutos(9, 18, 6), 1) for d in dias_6m)))
    entradas, _ = I.escanear_dumps_varios([tmp_path])
    res = I.resumo_dumps(entradas)
    por_res = {u["resolucao"]: u for u in res["unicos"]}
    assert set(por_res) == {"15 s", "6 min"}
    assert por_res["15 s"]["dias_unicos"] == 5 and por_res["15 s"]["arquivos"] == 7
    assert por_res["15 s"]["soma_dias"] == 5 + 1 + 4 and por_res["15 s"]["repetidos"] == 5
    assert por_res["6 min"]["dias_unicos"] == 16 and por_res["6 min"]["arquivos"] == 1
    assert por_res["6 min"]["repetidos"] == 0
    assert res["pares"] and all(p["resolucao"] == "15 s" for p in res["pares"])
    assert not any("dump_6m.txt" in (p["a"], p["b"]) for p in res["pares"])   # 6 min: sem par
    assert any({p["a"], p["b"]} == {"dump_dia_completo.txt", "dump20260900.txt"}
               and p["relacao"] == "mesmos dias" for p in res["pares"])
    md = I.relatorio_md(pd.DataFrame(columns=I.COLUNAS), [], dt.date(2026, 10, 3), {}, "c",
                        entradas)
    assert "| bollinger scalp (barras) | 15 s | WIN | 7 | **5** |" in md
    assert "| bollinger scalp (barras) | 6 min | WIN | 1 | **16** |" in md
    assert "Resolução (estimada)" in md and "arquivos de resoluções diferentes não são dupl" in md


def test_buracos_mostra_o_que_o_periodo_minimo_maximo_esconde(tmp_path: Path) -> None:
    """ABSBARRA do operador: 02/01/2025 a 26/08/2026 parece continuo, mas 24/07 a 21/08/2026 nao
    tem dado (21 dias uteis). Feriado isolado nao pode virar buraco."""
    d = dt.date
    dias = {d(2026, 7, 21), d(2026, 7, 22), d(2026, 7, 23), d(2026, 8, 24), d(2026, 8, 25)}
    assert I.buracos(dias) == [{"de": d(2026, 7, 24), "ate": d(2026, 8, 21), "dias_uteis": 21}]
    feriado = {d(2026, 9, 4), d(2026, 9, 8)}               # 07/09 (segunda): 1 dia util sem dado
    assert I.buracos(feriado) == [] and I.buracos(set()) == []
    carnaval = {d(2026, 2, 13), d(2026, 2, 18)}            # seg e ter: 2 dias uteis
    assert I.buracos(carnaval) == []
    assert I.buracos({d(2026, 3, 2), d(2026, 3, 9)}, minimo=4) == [
        {"de": d(2026, 3, 3), "ate": d(2026, 3, 6), "dias_uteis": 4}]
    assert I.buracos({d(2026, 3, 2), d(2026, 3, 9)}) == []           # 4 < 5: nao e' buraco
    assert I.buracos({d(2026, 3, 6), d(2026, 3, 9)}) == []           # fim de semana nao conta
    def abs_(dia: int) -> list[str]:
        return [f"ABSBARRA|{dia}|{h}|{h}|130.100,0|130.200,0|130.000,0|130.150,0|10|5|1|1|1|1|1|1"
                for h in _minutos(9, 18, 5)]
    arq = _dump(tmp_path / "abs_2026.txt", list(itertools.chain.from_iterable(
        abs_(x) for x in (1260721, 1260722, 1260723, 1260824, 1260825))))
    entradas, _ = I.escanear_dumps_varios([arq])
    u = I.resumo_dumps(entradas)["unicos"][0]
    assert u["dias_unicos"] == 5 and u["buracos"][0]["dias_uteis"] == 21
    md = I.relatorio_md(pd.DataFrame(columns=I.COLUNAS), [], dt.date(2026, 10, 3), {}, "c",
                        entradas)
    assert "24/07/2026 a 21/08/2026 (21 dias)" in md
    assert "Buracos (5+ dias úteis seguidos sem dado)" in md

