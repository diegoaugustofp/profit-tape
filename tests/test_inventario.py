"""Inventario de dados e coletas em curso (v4.22). Arvore sintetica no layout do sink:
<raiz>/<stream>/dt=AAAA-MM-DD/sym=<ATIVO>/part-NNNN.parquet."""

from __future__ import annotations

import datetime as dt
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
    assert w["tipo"] == "trade + book" and w["book_dias"] == 2
    assert w["trade_dias"] == 5 and str(w["trade_primeiro"]) == "2026-09-01"
    assert str(w["trade_ultimo"]) == "2026-09-23"
    assert (w["ao_vivo"], w["importado"], w["misto"]) == (2, 2, 1)
    assert w["trade_linhas"] == 1000 + 1000 + 700 + 650 + 600     # 22/09 = a maior entre as camadas
    assert w["camadas"] == "backup, curated, raw"
    # WDO: so' trade; a virada: V26 nao negocia em 01/10; lacuna de 24/09 (quarta) no V26
    v26, x26 = a.loc["WDOV26"], a.loc["WDOX26"]
    assert v26["tipo"] == "so' trade" and v26["familia"] == "futuro (contrato)"
    assert v26["trade_dias"] == 3 and x26["trade_dias"] == 4
    # V26 negociou 22, 23 e 25/09 (lacuna: 24/09); X26 tambem 01/10 (lacunas: 24, 28, 29, 30/09)
    assert v26["lacunas"] == 1 and x26["lacunas"] == 4
    assert a.loc["PETRJ49", "familia"] == "opcao PETR" and a.loc["PETRJ49", "tipo"] == "so' trade"
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
    assert "| `WDOV26` | futuro (contrato) | so' trade |" in md
    assert "| `WINFUT` | futuro (serie continua) | trade + book |" in md
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
    assert evento["repetidas"] == 0                  # eventos: nao ha' identidade de barra
    assert not any(k[0] == "leia.txt" for k in por)  # sem linha de dump: nao entra
    assert I._data_ntsl("1150102") == dt.date(2015, 1, 2)
    assert I._data_ntsl("990102") == dt.date(1999, 1, 2)
    assert I._data_ntsl("1151302") is None and I._data_ntsl("abc") is None
    assert I._data_ntsl("") is None


def test_relatorio_explica_o_que_e_dump_e_lista_o_periodo_por_arquivo(tmp_path: Path) -> None:
    arq = tmp_path / "wdo_m15.txt"
    arq.write_text("\n".join(_prc(1150102 + 3 * k, 900, 1, close=3000.0) for k in range(5)),
                   encoding="utf-8")
    md = I.relatorio_md(pd.DataFrame(columns=I.COLUNAS), [], dt.date(2026, 10, 3), {},
                        "c", I.escanear_dumps(arq))
    assert "não é CSV nem parquet" in md and "O NTSL não escreve o ticker na linha" in md
    assert "| `wdo_m15.txt` | preco M15 (barras) | 5 | 5 |" in md and "02/01/2015" in md
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
    assert wdo["ativos"] == ["WDOV26", "WDOX26"] and wdo["streams"] == ["trade"]
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

