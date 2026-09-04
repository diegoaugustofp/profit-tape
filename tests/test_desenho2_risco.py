"""
Testes da simulacao de gestao do DESENHO 2.

Os valores esperados foram conferidos A MAO antes de virarem teste
(regra 4). O simulador tem varias condicoes que interagem -- stop, alvo,
piso, teto, horario -- e um erro em qualquer uma produz numero plausivel.
"""

from __future__ import annotations

import pandas as pd
import pytest

from profittape.research import desenho2_risco as d2

DIA = pd.Timestamp("2026-08-24").date()


def _barras(specs: list[tuple[int, float, float, float, float]],
            lado: int = -1) -> pd.DataFrame:
    """Primeira barra e' o sinal; as demais formam o caminho."""
    return pd.DataFrame([
        {"dia": DIA, "hora": h, "open": o, "high": hi, "low": lo, "close": c,
         "evento": k == 0, "contexto_ok": k == 0, "lado": lado}
        for k, (h, o, hi, lo, c) in enumerate(specs)
    ])


# venda a 100.000 com extremo em 100.200 -> stop 100.220, risco 220
_SINAL = (1000, 100000.0, 100200.0, 99900.0, 100000.0)


def test_saida_por_ALVO() -> None:
    r = d2.simular(_barras([_SINAL,
                            (1005, 100000, 100050, 99500, 99600),
                            (1010, 99600, 99650, 98900, 99000)]))
    assert r["saida"].iloc[0] == "alvo"
    assert r["resultado"].iloc[0] == pytest.approx(d2.ALVO)


def test_saida_por_STOP() -> None:
    r = d2.simular(_barras([_SINAL, (1005, 100000, 100400, 99950, 100350)]))
    assert r["saida"].iloc[0] == "stop"
    assert r["resultado"].iloc[0] == pytest.approx(-220.0)


def test_ambiguidade_intrabarra_assume_STOP_primeiro() -> None:
    """
    Quando a MESMA barra toca stop e alvo, o OHLC nao diz qual veio
    antes. LIMITE PESSIMISTA: stop.

    E' raro por construcao -- stop e alvo distam 1.500 pts e barras com
    essa amplitude sao 1 em 2.260 na depuracao (0,04%). Foi essa raridade
    que tornou o desenho mensuravel no grafico, ao contrario da Rota B.
    """
    r = d2.simular(_barras([_SINAL, (1005, 100000, 100400, 98900, 99000)]))
    assert r["saida"].iloc[0] == "stop", "ambiguidade tem que ser pessimista"


def test_stop_acima_do_teto_NAO_OPERA() -> None:
    """O operador decidiu nao operar em vez de truncar: truncar tiraria
    o stop do extremo, que e' o oposto do proposito."""
    r = d2.simular(_barras([(1000, 100000, 100600, 99900, 100000),
                            (1005, 100000, 100050, 99500, 99600)]))
    assert r["saida"].iloc[0] == "nao_operou"
    assert r["risco"].iloc[0] > d2.STOP_MAXIMO


def test_stop_abaixo_do_piso_OPERA_COM_O_PISO() -> None:
    r = d2.simular(_barras([(1000, 100000, 100030, 99900, 100000),
                            (1005, 100000, 100050, 99500, 99600)]))
    assert r["risco"].iloc[0] == pytest.approx(d2.STOP_MINIMO)


def test_nao_abre_depois_do_horario_limite() -> None:
    r = d2.simular(_barras([(1705, 100000, 100200, 99900, 100000),
                            (1710, 100000, 100050, 99500, 99600)]))
    assert len(r) == 0


def test_fecha_no_horario_de_saida() -> None:
    """17:30 fecha a posicao: evita o leilao e impede virar swing."""
    r = d2.simular(_barras([(1655, 100000, 100200, 99900, 100000),
                            (1700, 100000, 100050, 99950, 100000),
                            (1730, 100000, 100050, 99950, 99980)]))
    assert r["saida"].iloc[0] == "tempo"


def test_extremo_pode_ser_a_PROPRIA_barra_de_sinal() -> None:
    """
    Medido na depuracao: em 70% dos eventos o extremo E' a barra de
    sinal -- esperado, porque o evento exige `z_amplitude` alto.
    """
    janela = pd.DataFrame({"high": [100100.0, 100500.0], "low": [99000.0, 98500.0]})
    assert d2._nivel_de_stop(janela, -1) == pytest.approx(100520.0)
    assert d2._nivel_de_stop(janela, +1) == pytest.approx(98480.0)


def test_emd_usa_variancia_e_NAO_a_media() -> None:
    """
    O que separa "abandonar desenho impossivel" de "abandonar desenho
    que deu resultado ruim". Deslocar TODOS os resultados por uma
    constante muda a media e NAO pode mudar o EMD.
    """
    base = pd.DataFrame({"lado": [-1] * 40, "saida": ["stop"] * 40,
                         "resultado": [(-1) ** i * 200.0 for i in range(40)]})
    deslocado = base.assign(resultado=base["resultado"] + 500.0)
    a = d2.medir_emd(base)["por_lado"][0]["emd"]
    b = d2.medir_emd(deslocado)["por_lado"][0]["emd"]
    assert a == pytest.approx(b)


def test_diagnostico_reporta_o_custo_do_alvo_e_a_MFE() -> None:
    """
    As duas metricas que cobrem os defeitos que o operador ACEITOU:
    encerrar cedo em dia direcional, e stopar depois de ter tido R:R
    alto. Sao DIAGNOSTICO -- mudar o alvo por causa da MFE observada
    seria calibrar depois de ver o dado.
    """
    r = d2.simular(_barras([_SINAL,
                            (1005, 100000, 100050, 99500, 99600),
                            (1010, 99600, 99650, 98900, 99000)]))
    dg = d2.diagnostico(r)
    assert "custo_do_alvo_medio" in dg
    assert "mfe_em_risco_p50" in dg


def test_diagnostico_por_lado_separa_os_dois() -> None:
    ops = pd.DataFrame({
        "dia": [DIA] * 6,
        "lado": [-1, -1, -1, 1, 1, 1],
        "saida": ["stop", "alvo", "nao_operou", "stop", "stop", "tempo"],
        "risco": [200.0, 250.0, 700.0, 300.0, 350.0, 400.0],
        "resultado": [-200.0, 1000.0, float("nan"), -300.0, -350.0, 120.0],
        "mfe_em_risco": [0.5, 4.0, float("nan"), 0.3, 0.8, 1.2],
        "sem_alvo": [-200.0, 1400.0, float("nan"), -300.0, -350.0, 120.0],
    })
    t = d2.diagnostico_por_lado(ops)
    assert list(t["lado"]) == ["BAIXA (aqua)", "ALTA (fucsia)"]
    baixa = t[t["lado"] == "BAIXA (aqua)"].iloc[0]
    assert baixa["n"] == 2, "a descartada nao entra na contagem de operadas"
    assert baixa["descartados"] == 1
    assert baixa["alvo"] == 1


def test_por_lado_ignora_as_descartadas_nas_metricas() -> None:
    """
    `nao_operou` tem `resultado` NaN. Se entrasse nas metricas, o risco
    p50 incluiria stops que nunca foram tomados -- justamente os grandes,
    que foram descartados por passar de 500.
    """
    ops = pd.DataFrame({
        "dia": [DIA] * 3, "lado": [-1, -1, -1],
        "saida": ["stop", "nao_operou", "nao_operou"],
        "risco": [200.0, 900.0, 800.0],
        "resultado": [-200.0, float("nan"), float("nan")],
        "mfe_em_risco": [0.5, float("nan"), float("nan")],
        "sem_alvo": [-200.0, float("nan"), float("nan")],
    })
    t = d2.diagnostico_por_lado(ops)
    linha = t.iloc[0]
    assert linha["n"] == 1
    assert linha["risco_p50"] == pytest.approx(200.0), (
        "o risco das descartadas nao pode entrar")


def test_lado_sem_operacao_nao_estoura() -> None:
    ops = pd.DataFrame({
        "dia": [DIA], "lado": [-1], "saida": ["stop"], "risco": [200.0],
        "resultado": [-200.0], "mfe_em_risco": [0.5], "sem_alvo": [-200.0],
    })
    t = d2.diagnostico_por_lado(ops)
    assert int(t[t["lado"] == "ALTA (fucsia)"]["n"].iloc[0]) == 0
