"""
Testes do pre-registro de 2026-08-29e: barra de tempo + absorcao direcional.

Os numeros esperados aqui foram conferidos A MAO antes de virarem teste
(regra 4 da skill profit-tape-disciplina) — o cenario e' o mesmo usado na
conferencia manual da sessao.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from profittape.features import bars, flow

S = 1_000_000_000
# 1_000_020 e' divisivel por 60 E por 300: o balde comeca no negocio 0, como
# acontece com timestamp real (a fronteira de minuto vem do epoch).
BASE = 1_000_020 * S


def _cenario() -> pd.DataFrame:
    linhas = [
        (BASE + 0,     100.0, 500, 2),    # balde 0
        (BASE + 10 * S, 110.0, 200, 2),
        (BASE + 20 * S,  95.0, 200, 3),
        (BASE + 30 * S,  97.0, 100, 3),
        (BASE + 40 * S, 999.0, 900, 13),  # RLP: fora do OHLC e de vol_agr
        (BASE + 61 * S, 100.0, 100, 2),   # balde 1
        (BASE + 70 * S, 100.0, 100, 3),
        (BASE + 121 * S, 100.0, 50, 2),   # balde 2 = ultimo do dia
    ]
    df = pd.DataFrame(linhas, columns=["ts_ns", "price", "quantidade", "trade_type"])
    df["agente_comprador"] = 1
    df["agente_vendedor"] = 2
    df["dt"] = pd.Categorical(["2026-08-24"] * len(df))
    return df


def test_ultima_barra_do_dia_e_descartada() -> None:
    barrado, descartadas = bars.atribuir_barras_tempo(_cenario(), 60)
    assert descartadas == 1
    assert sorted(barrado["bar_id"].unique()) == [0, 1]


def test_valores_conferidos_a_mao() -> None:
    barrado, _ = bars.atribuir_barras_tempo(_cenario(), 60)
    b = flow.calcular(barrado, agentes=[], tick=5.0,
                      incluir_absorcao_dir=True).set_index("bar_id")

    # Barra 0: OHLC so' de agressao (o RLP de 999 nao vira high).
    assert b.loc[0, "open"] == 100.0
    assert b.loc[0, "high"] == 110.0
    assert b.loc[0, "low"] == 95.0
    assert b.loc[0, "close"] == 97.0
    assert b.loc[0, "vol_agr"] == 1000      # RLP fora
    assert b.loc[0, "vol_rlp"] == 900
    assert b.loc[0, "imbalance"] == pytest.approx(0.4)          # (700-300)/1000
    assert b.loc[0, "desloc_norm"] == pytest.approx(-0.2)       # (97-100)/15
    assert b.loc[0, "absorcao_dir"] == pytest.approx(0.6)       # 0.4 - (-0.2)


def test_guarda_high_igual_low() -> None:
    """Barra que nao andou: desloc_norm = 0, nunca NaN (0/0 propagaria no z)."""
    barrado, _ = bars.atribuir_barras_tempo(_cenario(), 60)
    b = flow.calcular(barrado, agentes=[], tick=5.0,
                      incluir_absorcao_dir=True).set_index("bar_id")
    assert b.loc[1, "high"] == b.loc[1, "low"]
    assert b.loc[1, "desloc_norm"] == 0.0
    assert not np.isnan(b.loc[1, "absorcao_dir"])


def test_retrocompatibilidade_flow_sem_o_parametro() -> None:
    """
    Comportamento ANTIGO identico sem `incluir_absorcao_dir` (regra 5).

    Nao basta "o default e' False, deve estar tudo bem": ja aconteceu neste
    projeto de um campo novo passar despercebido por horas.
    """
    barrado, _ = bars.atribuir_barras_tempo(_cenario(), 60)
    antigo = flow.calcular(barrado, agentes=[], tick=5.0)
    novo = flow.calcular(barrado, agentes=[], tick=5.0, incluir_absorcao_dir=True)

    assert "desloc_norm" not in antigo.columns
    assert "absorcao_dir" not in antigo.columns
    # Todas as colunas antigas continuam com valores identicos.
    pd.testing.assert_frame_equal(antigo, novo[antigo.columns])


def test_barra_nao_atravessa_o_dia() -> None:
    df = _cenario()
    outro = df.copy()
    outro["ts_ns"] = outro["ts_ns"] + 86_400 * S
    outro["dt"] = "2026-08-25"
    juntos = pd.concat([df, outro], ignore_index=True)
    juntos["dt"] = pd.Categorical(juntos["dt"])

    barrado, descartadas = bars.atribuir_barras_tempo(juntos, 60)
    assert descartadas == 2                       # uma parcial por pregao
    por_dia = barrado.groupby("dt", observed=True)["bar_id"].apply(set)
    assert por_dia["2026-08-24"].isdisjoint(por_dia["2026-08-25"])
    assert barrado["bar_id"].is_monotonic_increasing


def test_periodo_invalido() -> None:
    with pytest.raises(ValueError):
        bars.atribuir_barras_tempo(_cenario(), 0)


def test_tape_de_ruido_nao_tem_informacao_no_lado_agressor() -> None:
    """
    Propriedade que faz do gerador um NULO: o lado agredido nao antecipa o
    passo do preco. Se essa correlacao nao for ~0, o portao nao vale nada.
    """
    from profittape.research.portao_absorcao import gerar_tape_ruido

    tape = gerar_tape_ruido(n_dias=2, semente=7)
    lado = np.where(tape["trade_type"].to_numpy() == 2, 1.0, -1.0)
    # Passo do MID: a variacao de preco entre negocios do mesmo lado isola o
    # passo do bounce; aqui basta o proxy grosseiro do retorno seguinte.
    ret = np.diff(tape["price"].to_numpy(), append=np.nan)
    m = ~np.isnan(ret)
    corr = float(np.corrcoef(lado[m], ret[m])[0, 1])
    # O bounce cria correlacao NEGATIVA forte (comprar no ask e depois voltar
    # ao bid); o que nao pode existir e' correlacao POSITIVA, que seria o
    # lado agressor prevendo o proprio movimento.
    assert corr < 0.05


def test_buracos_sao_preservados_no_bar_id() -> None:
    """
    Balde vazio tem que ficar VISIVEL no bar_id.

    Bug real (2026-08-29): a primeira versao renumerava densamente com
    np.unique(return_inverse=True), o que apagava os baldes vazios; o
    contador de buracos media o resultado ja achatado e devolvia zero por
    construcao, sempre. Isso importa porque com buraco no meio do pregao
    "h barras a frente" deixa de ser "h periodos a frente" — e o horizonte
    do pre-registro e' definido em tempo de relogio.
    """
    from profittape.features.pipeline_tempo import _contar_buracos

    linhas = [
        (BASE + 0, 100.0, 10, 2), (BASE + 30 * S, 101.0, 10, 3),
        (BASE + 300 * S, 102.0, 10, 2), (BASE + 330 * S, 103.0, 10, 3),
        (BASE + 3600 * S, 104.0, 10, 2), (BASE + 3630 * S, 105.0, 10, 3),
        (BASE + 3900 * S, 106.0, 10, 2),          # ultimo balde -> descartado
    ]
    df = pd.DataFrame(linhas, columns=["ts_ns", "price", "quantidade", "trade_type"])
    df["agente_comprador"] = 1
    df["agente_vendedor"] = 2
    df["dt"] = pd.Categorical(["2026-08-24"] * len(df))

    barrado, _ = bars.atribuir_barras_tempo(df, 300)
    b = flow.calcular(barrado, agentes=[], tick=5.0, incluir_absorcao_dir=True)
    # Baldes 0, 1 e 12 (3600s / 300s): dez baldes vazios entre o 1 e o 12.
    assert list(b["bar_id"]) == [0, 1, 12]
    assert _contar_buracos(b) == 10


def test_sem_buraco_continua_dando_zero() -> None:
    """O contador so' vale se nao acusar buraco onde nao ha."""
    from profittape.features.pipeline_tempo import _contar_buracos

    barrado, _ = bars.atribuir_barras_tempo(_cenario(), 60)
    b = flow.calcular(barrado, agentes=[], tick=5.0, incluir_absorcao_dir=True)
    assert _contar_buracos(b) == 0
