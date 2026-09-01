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


def test_para_barras_entrega_o_que_preparar_espera() -> None:
    from profittape.research.absorcao_barra import preparar

    df = pd.DataFrame({
        "dia": [pd.Timestamp("2026-06-01").date()] * 60,
        "open": 140000.0, "high": 140200.0, "low": 139900.0,
        "close": 140050.0, "vol_agr": 180000.0,
        "desloc_norm_ntsl": 0.5,
    })
    d = preparar(para_barras(df))
    assert {"z_amplitude", "z_vol_agr", "mov_contexto"} <= set(d.columns)


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
