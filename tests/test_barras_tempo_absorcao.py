"""
Testes do pre-registro de 2026-08-29e: barra de tempo + absorcao direcional.

Os numeros esperados aqui foram conferidos A MAO antes de virarem teste
(regra 4 da skill profit-tape-disciplina) — o cenario e' o mesmo usado na
conferencia manual da sessao.
"""

from __future__ import annotations

from pathlib import Path

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


def _features_sinteticas(n_dias: int = 12, por_dia: int = 40) -> pd.DataFrame:
    """Arquivo de features minimo para exercitar `rodar` sem tocar em tape."""
    rng = np.random.default_rng(3)
    linhas = []
    bar = 0
    for d in range(n_dias):
        t0 = pd.Timestamp("2026-03-02", tz="UTC").value + d * 86_400 * S
        for j in range(por_dia):
            linhas.append({
                "bar_id": bar, "ts_close": t0 + j * 300 * S,
                "close": 100.0 + rng.normal(),
                "z_absorcao_dir": rng.normal(),
            })
            bar += 1
    return pd.DataFrame(linhas)


def test_trials_previstos_so_endurece(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """
    Deflacionar contra um total MAIOR (hipotese resolvida em duas
    invocacoes) sobe a barra; um total menor que o real e ignorado. A
    contabilidade em disco nao muda nos dois casos.
    """
    from profittape.research.pipeline import rodar

    arq = tmp_path / "features.parquet"
    _features_sinteticas().to_parquet(arq, index=False)

    baixo = rodar(arq, tmp_path / "a", horizontes=[1], trials_previstos=None)
    alto = rodar(arq, tmp_path / "b", horizontes=[1], trials_previstos=5000)
    ignorado = rodar(arq, tmp_path / "c", horizontes=[1], trials_previstos=1)

    assert alto["limiar_deflacionado"] > baixo["limiar_deflacionado"]
    # Total menor que o real nao afrouxa nada.
    assert ignorado["limiar_deflacionado"] == baixo["limiar_deflacionado"]
    # E a cobranca em disco e' identica nos tres casos.
    assert baixo["trials_rodada"] == alto["trials_rodada"] == 1


# --- PRE-REGISTRO 3: promocao por falta de poder (congelado 2026-08-29i) ---

def _celula(ic: float, t: float, consist: float,
            n_obs: int = 2000, folds: int = 11) -> pd.Series:
    return pd.Series({"folds_validos": folds, "t_stat": t, "n_obs_teste": n_obs,
                      "ic_medio": ic, "consistencia_sinal": consist})


# 11 folds e limiar 3,055 dao t_critico 4,03; piso de magnitude com
# n_obs=2000 e' 2/sqrt(2000) = 0,0447. Conferido a mao antes destes testes.
_LIM = 3.055


def test_promove_quando_falha_so_estabilidade() -> None:
    from profittape.research.pipeline import _veredito

    celula = _celula(ic=-0.08, t=-3.0, consist=0.91)
    assert _veredito(celula, _LIM) == "descarta"
    assert _veredito(celula, _LIM, promover_por_poder=True) == "inconclusivo"


def test_nao_promove_com_consistencia_abaixo_de_085() -> None:
    """
    A porta dos fundos que o limiar de 0,85 existe para fechar: |t| baixo
    tambem vem de desvio ALTO entre folds, que e' instabilidade real. A
    barra de 0,70 de `segue` nao separa os dois casos.
    """
    from profittape.research.pipeline import _veredito

    celula = _celula(ic=-0.08, t=-3.0, consist=0.82)
    assert _veredito(celula, _LIM, promover_por_poder=True) == "descarta"


def test_nao_promove_se_magnitude_tambem_falha() -> None:
    from profittape.research.pipeline import _veredito

    celula = _celula(ic=-0.02, t=-3.0, consist=0.95)   # 0,02 < piso 0,0447
    assert _veredito(celula, _LIM, promover_por_poder=True) == "descarta"


def test_promocao_nunca_cria_um_segue() -> None:
    """A regra so' move `descarta` -> `inconclusivo`. `segue` e' identico."""
    from profittape.research.pipeline import _veredito

    rng = np.random.default_rng(11)
    for _ in range(500):
        celula = _celula(ic=float(rng.normal(0, 0.06)),
                         t=float(rng.normal(0, 4)),
                         consist=float(rng.uniform(0.3, 1.0)),
                         n_obs=int(rng.integers(500, 5000)),
                         folds=int(rng.integers(4, 24)))
        classico = _veredito(celula, _LIM)
        com_poder = _veredito(celula, _LIM, promover_por_poder=True)
        if classico == "segue":
            assert com_poder == "segue"
        assert com_poder in {classico, "inconclusivo"}
        if com_poder != classico:
            assert classico == "descarta"


def test_retrocompatibilidade_veredito_sem_a_flag(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """
    Sem a flag, o veredito e' IDENTICO ao classico celula a celula.

    Nao basta "o default e' False": mudar `_veredito` para todos
    reclassificaria retroativamente o historico de barra de volume (492
    trials, incluindo os dois `segue` de 2026-08-23) sem ninguem ter
    rerodado nada.
    """
    from profittape.research.pipeline import _veredito, rodar

    rng = np.random.default_rng(5)
    for _ in range(500):
        celula = _celula(ic=float(rng.normal(0, 0.06)),
                         t=float(rng.normal(0, 4)),
                         consist=float(rng.uniform(0.3, 1.0)),
                         n_obs=int(rng.integers(500, 5000)),
                         folds=int(rng.integers(4, 24)))
        assert _veredito(celula, _LIM) == _veredito(
            celula, _LIM, promover_por_poder=False)

    arq = tmp_path / "features.parquet"
    _features_sinteticas().to_parquet(arq, index=False)
    antigo = rodar(arq, tmp_path / "x", horizontes=[1])
    novo = rodar(arq, tmp_path / "y", horizontes=[1], promover_por_poder=False)
    pd.testing.assert_frame_equal(antigo["tabela"], novo["tabela"])


def test_relatorio_registra_qual_regra_foi_usada(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """
    Um `inconclusivo` de origem "faltou fold" e um de origem "promovido por
    poder" significam coisas diferentes; um relatorio antigo tem que dizer
    qual regra o produziu.
    """
    from profittape.research.pipeline import rodar

    arq = tmp_path / "features.parquet"
    _features_sinteticas().to_parquet(arq, index=False)

    classico = rodar(arq, tmp_path / "c", horizontes=[1])
    com_poder = rodar(arq, tmp_path / "p", horizontes=[1],
                      promover_por_poder=True)
    assert "sem promocao" in Path(classico["relatorio"]).read_text(encoding="utf-8")
    assert "promocao por poder ATIVA" in Path(
        com_poder["relatorio"]).read_text(encoding="utf-8")
