"""
Testes do parser do log ABSBARRA e da rodada sobre dados do grafico.

A amostra do grafico so' vale como INDEPENDENTE. Os testes protegem
justamente essa propriedade.
"""

from __future__ import annotations

import pandas as pd
import pytest

from profittape.research.absorcao_grafico import (
    CAMPOS,
    carregar_log,
    checar_sobreposicao,
    conferir_contra_o_ntsl,
    para_barras,
)


def _linha(dia: str = "1260601", hora: int = 900, o: float = 140000.0,
           h: float = 140200.0, low: float = 139900.0, c: float = 140050.0,
           extras: str = "|250000|180000|0.5|1.0|1.0|3.5|-1") -> str:
    return f"ABSBARRA|{dia}|{hora}|{hora}|{o}|{h}|{low}|{c}{extras}"


def test_carrega_e_converte_a_data_do_easylanguage(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """`Date` vem em 1AnoMesDia, com o ano deslocado de 1900."""
    arq = tmp_path / "log.txt"
    arq.write_text("\n".join(_linha(hora=900 + i) for i in range(5)),
                   encoding="utf-8")
    df, diag = carregar_log(arq)
    assert diag["barras"] == 5
    assert df["dia"].iloc[0] == pd.Timestamp("2026-06-01").date()


def test_recusa_log_do_indicador_ERRADO(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """
    `absorcao_dir.ntsl` loga 'ABSDIR|'. Colar o indicador errado no
    grafico e' erro plausivel, e a mensagem tem que dizer qual e' o certo.
    """
    arq = tmp_path / "log.txt"
    arq.write_text("ABSDIR|1260601|900|900|1|2|3|4\n", encoding="utf-8")
    with pytest.raises(SystemExit, match=r"absorcao_barra\.ntsl"):
        carregar_log(arq)


def test_formato_incompativel_NOMEIA_o_campo_ausente(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """
    Contar e' ambiguo: a LINHA tem um token a mais que os campos, porque
    o proprio prefixo entra na separacao. Em 2026-08-31 isso custou uma
    ida e volta.
    """
    arq = tmp_path / "log.txt"
    curta = _linha(extras="|250000|180000|0.5|1.0|1.0|3.5")   # falta `lado`
    arq.write_text(f"{curta}\n{curta}\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        carregar_log(arq)
    assert "lado_ntsl" in str(e.value)
    assert "DEPOIS do prefixo" in str(e.value)


def test_recusa_sobreposicao_com_o_periodo_JA_capturado() -> None:
    """
    A independencia e' a UNICA razao de usar esta fonte. Sobrepor
    transformaria "duas amostras que concordam" em "a mesma amostra
    contada duas vezes", e o segundo resultado pareceria confirmacao.
    """
    df = pd.DataFrame({"dia": [pd.Timestamp("2026-08-01").date(),
                              pd.Timestamp("2026-08-05").date()]})
    with pytest.raises(SystemExit, match="JA' ESTA no parquet"):
        checar_sobreposicao(df)


def test_periodo_anterior_ao_curated_e_aceito() -> None:
    df = pd.DataFrame({"dia": [pd.Timestamp("2026-06-01").date(),
                              pd.Timestamp("2026-07-23").date()]})
    checar_sobreposicao(df)          # nao levanta


def test_recusa_barras_duplicadas(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Dumps sobrepostos inflam o n sem acrescentar informacao."""
    arq = tmp_path / "log.txt"
    arq.write_text(f"{_linha(hora=900)}\n{_linha(hora=900)}\n",
                   encoding="utf-8")
    with pytest.raises(SystemExit, match="duplicadas"):
        carregar_log(arq)


def test_numero_no_formato_pt_BR(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """
    Milhar com ponto, decimal com virgula. Devolver NaN em silencio seria
    pior que falhar: o campo sumiria das estatisticas em vez de acusar.
    """
    arq = tmp_path / "log.txt"
    arq.write_text(
        "ABSBARRA|1260601|900|900|140.000,00|140.200,00|139.900,00"
        "|140.050,00|250.000,00|180.000,00|0,50|1,00|1,00|3,50|-1\n"
        "ABSBARRA|1260601|905|905|140.000,00|140.200,00|139.900,00"
        "|140.050,00|250.000,00|180.000,00|0,50|1,00|1,00|3,50|-1\n",
        encoding="utf-8")
    df, _ = carregar_log(arq)
    assert df["open"].iloc[0] == 140000.0
    assert df["desloc_norm_ntsl"].iloc[0] == 0.5


def test_conferencia_acusa_divergencia_entre_python_e_ntsl() -> None:
    """
    Divergencia aqui nao e' detalhe: significa que o indicador que se
    OLHA e o estimador que DECIDE nao sao a mesma coisa.
    """
    d = pd.DataFrame({"desloc_norm": [0.1, 0.2], "z_amplitude": [1.0, 1.0],
                      "z_vol_agr": [1.0, 1.0], "mov_contexto": [3.0, 3.0]})
    df = pd.DataFrame({"desloc_norm_ntsl": [0.1, 0.9],
                       "z_amplitude_ntsl": [1.0, 1.0],
                       "z_vol_agr_ntsl": [1.0, 1.0],
                       "mov_contexto_ntsl": [3.0, 3.0]})
    r = conferir_contra_o_ntsl(d, df)
    assert r["desloc_norm"]["dif_max"] == pytest.approx(0.7)
    assert r["z_amplitude"]["dif_max"] == 0.0


def test_para_barras_DERIVA_o_desloc_norm() -> None:
    """
    Bug real (2026-09-01): `preparar` assume `desloc_norm` pronto — no
    parquet ele vem do `pipeline_tempo`, mas o dump do grafico so' traz
    OHLC, e a rodada morria com KeyError.

    Meu teste anterior nao pegou porque a fixture passava a coluna. Aqui
    ela NAO e' passada, que e' o caso real.
    """
    from profittape.research.absorcao_barra import marcar_eventos, preparar

    df = pd.DataFrame({
        "dia": [pd.Timestamp("2026-06-01").date()] * 60,
        "open": 140000.0, "high": 140200.0, "low": 139900.0,
        "close": 140050.0, "vol_agr": 180000.0,
    })
    b = para_barras(df)
    assert "desloc_norm" in b.columns
    # (140050-140000)/(140200-139900) = 50/300
    assert b["desloc_norm"].iloc[0] == pytest.approx(50 / 300)
    d = marcar_eventos(preparar(b))
    assert {"z_amplitude", "z_vol_agr", "mov_contexto", "evento"} <= set(d.columns)


def test_desloc_norm_e_DERIVADO_e_nao_copiado_do_log() -> None:
    """
    Copiar o valor logado seria confiar que os dois lados concordam;
    derivar do OHLC e comparar MEDE se concordam. Se o `.ntsl` estiver
    errado, copiar esconderia o erro.
    """
    df = pd.DataFrame({
        "dia": [pd.Timestamp("2026-06-01").date()],
        "open": [100.0], "high": [110.0], "low": [90.0], "close": [105.0],
        "vol_agr": [1000.0],
        "desloc_norm_ntsl": [0.999],        # valor ABSURDO de proposito
    })
    b = para_barras(df)
    assert b["desloc_norm"].iloc[0] == pytest.approx(0.25)


def test_ordem_dos_campos_bate_com_o_ntsl() -> None:
    """
    Dois lados da mesma ordem congelada. Foi essa lacuna que, em
    2026-08-31, deixou o parser exigir um campo que o indicador nunca
    emitiu -- com a suite inteira verde.
    """
    from pathlib import Path as _P

    t = (_P(__file__).resolve().parents[1] / "ntsl"
         / "absorcao_barra.ntsl").read_text(encoding="utf-8")
    inicio = t.index('ConsoleLog("ABSBARRA|')
    chamada = t[inicio:t.index(");", inicio)]
    assert chamada.count('"|"') + 1 == len(CAMPOS), (
        f"o .ntsl emite {chamada.count('|') } campos e o parser espera "
        f"{len(CAMPOS)}"
    )


def _declara(tmp_path, periodos):  # type: ignore[no-untyped-def]
    import json
    arq = tmp_path / "PERIODOS.json"
    arq.write_text(json.dumps({"periodos": periodos}), encoding="utf-8")
    return arq


def _df_dias(inicio: str, fim: str) -> pd.DataFrame:
    return pd.DataFrame({"dia": [pd.Timestamp(inicio).date(),
                                 pd.Timestamp(fim).date()]})


def test_periodo_declarado_antes_e_aceito(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from profittape.research.absorcao_grafico import checar_periodo_declarado

    arq = _declara(tmp_path, [{"inicio": "2026-05-01", "fim": "2026-05-31",
                               "motivo": "mes completo anterior ao curated"}])
    p = checar_periodo_declarado(_df_dias("2026-05-04", "2026-05-29"), arq)
    assert "mes completo" in p["motivo"]


def test_periodo_NAO_declarado_e_recusado(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """
    A protecao central. Recusar sobreposicao com o capturado nao basta:
    nada impediria dumpar maio, ver o resultado, e depois dumpar marco.
    Cada dump seria "um tiro", mas o CONJUNTO seria uma busca -- e o
    ultimo resultado pareceria confirmacao.
    """
    from profittape.research.absorcao_grafico import checar_periodo_declarado

    arq = _declara(tmp_path, [{"inicio": "2026-05-01", "fim": "2026-05-31",
                               "motivo": "x"}])
    with pytest.raises(SystemExit, match="NAO esta declarado"):
        checar_periodo_declarado(_df_dias("2026-03-02", "2026-03-20"), arq)


def test_dump_que_EXTRAPOLA_o_declarado_e_recusado(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """
    Declarar maio e dumpar maio+junho seria ampliar depois do fato.
    """
    from profittape.research.absorcao_grafico import checar_periodo_declarado

    arq = _declara(tmp_path, [{"inicio": "2026-05-01", "fim": "2026-05-31",
                               "motivo": "x"}])
    with pytest.raises(SystemExit, match="NAO esta declarado"):
        checar_periodo_declarado(_df_dias("2026-05-04", "2026-06-15"), arq)


def test_lista_vazia_exige_declaracao_com_motivo(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """O motivo e' cobravel: se nao puder ser dito ANTES de ver o dado,
    nao e' criterio."""
    from profittape.research.absorcao_grafico import checar_periodo_declarado

    arq = _declara(tmp_path, [])
    with pytest.raises(SystemExit, match="motivo"):
        checar_periodo_declarado(_df_dias("2026-05-04", "2026-05-29"), arq)


def test_arquivo_de_periodos_do_repositorio_e_valido() -> None:
    """O arquivo commitado tem que ser JSON legivel e ter a chave certa."""
    import json
    from pathlib import Path as _P

    arq = _P(__file__).resolve().parents[1] / "docs" / "PERIODOS_DECLARADOS.json"
    dados = json.loads(arq.read_text(encoding="utf-8"))
    assert "periodos" in dados and isinstance(dados["periodos"], list)
    for p in dados["periodos"]:
        assert {"inicio", "fim", "motivo"} <= set(p), (
            "todo periodo precisa de inicio, fim e MOTIVO")


def test_json_malformado_explica_o_erro_real(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """
    Caso real (2026-09-01): a entrada foi acrescentada DEPOIS do `}`
    final e o arquivo virou dois objetos JSON colados.

    Falha de desenho minha antes de ser erro de digitacao: o arquivo
    tinha 30 linhas de instrucao ANTES da lista, o que empurrava
    `periodos` para o fim e tornava facil errar o lugar. A mensagem crua
    de JSONDecodeError nao diria nada sobre isso.
    """
    from profittape.research.absorcao_grafico import checar_periodo_declarado

    arq = tmp_path / "P.json"
    arq.write_text('{"periodos": []}\n{"inicio": "2026-05-01"}\n',
                   encoding="utf-8")
    with pytest.raises(SystemExit, match="DENTRO da lista"):
        checar_periodo_declarado(_df_dias("2026-05-04", "2026-05-29"), arq)


def test_periodo_sem_motivo_e_recusado(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from profittape.research.absorcao_grafico import checar_periodo_declarado

    arq = _declara(tmp_path, [{"inicio": "2026-05-01", "fim": "2026-05-31"}])
    with pytest.raises(SystemExit, match="motivo"):
        checar_periodo_declarado(_df_dias("2026-05-04", "2026-05-29"), arq)


@pytest.mark.parametrize(("conteudo", "esperado"), [
    ("ABSVIDA|x\nABSDIAG|1|100|1260504|900|1|1|0.1|1|1|2\n", "LogDiagnostico"),
    ("ABSDIR|1260504|900|900|1|2|3|4\n", "absorcao_dir"),
    ("ABSVIDA|barras=100|primeira_data=1260504\n", "janela de data"),
    ("qualquer coisa\n", "nao compilou"),
])
def test_log_sem_ABSBARRA_aponta_a_causa_CERTA(tmp_path, conteudo, esperado) -> None:  # type: ignore[no-untyped-def]
    """
    Quatro causas produzem o mesmo sintoma (nenhuma linha ABSBARRA), e
    cada uma pede acao diferente. A mensagem antiga sugeria SEMPRE
    "confira o indicador" -- enganoso quando a causa era o
    `LogDiagnostico` ligado, modo em que o indicador (corretamente) nao
    emite ABSBARRA.
    """
    arq = tmp_path / "log.txt"
    arq.write_text(conteudo, encoding="utf-8")
    with pytest.raises(SystemExit, match=esperado):
        carregar_log(arq)


def test_linhas_ABSDIAG_e_ABSVIDA_nao_atrapalham_o_parse(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Os tres formatos convivem: o parser filtra pelo prefixo."""
    arq = tmp_path / "log.txt"
    linhas = ["ABSVIDA|barras=3|primeira_data=1260504"]
    for i in range(3):
        linhas.append(f"ABSDIAG|{i}|3|1260504|{900 + i}|1000|50|0.1|1|1|2")
        linhas.append(_linha(hora=900 + i))
    arq.write_text("\n".join(linhas), encoding="utf-8")
    _, diag = carregar_log(arq)
    assert diag["barras"] == 3
