"""
Features Tier 1: cada teste verifica um numero calculavel a mao.

Feature errada e' pior que feature ausente — parece funcionar e envenena tudo
que vem depois. Por isso nada aqui usa dado aleatorio: cada cenario e'
construido para ter UMA resposta certa, conferivel no papel.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from profittape.features import bars, flow, labels, normalize

BUY, SELL, RLP = 2, 3, 13


def _df(trades: list[tuple]) -> pd.DataFrame:
    """(tipo, qtd, preco, comprador, vendedor) -> DataFrame minimo de curated."""
    base = 1_704_193_200_000_000_000
    linhas = []
    for i, (tipo, qtd, preco, comp, vend) in enumerate(trades):
        linhas.append({
            "ts_ns": base + i * 1_000_000_000, "symbol": "TESTE", "trade_id": i,
            "price": float(preco), "quantidade": int(qtd),
            "agente_comprador": comp, "agente_vendedor": vend,
            "trade_type": tipo, "dt": "2024-01-02",
        })
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------- barras
def test_rlp_nao_avanca_o_relogio() -> None:
    """3000 de RLP no meio nao podem fechar barra de threshold 100."""
    df = _df([
        (BUY, 60, 10.0, 1, 2),
        (RLP, 3000, 10.0, 1, 2),      # ignorado pelo relogio
        (SELL, 40, 10.1, 3, 4),       # cum agressao = 100: fecha a barra 0
        (BUY, 100, 10.2, 1, 2),       # barra 1 completa
    ])
    com_barras, parciais = bars.atribuir_barras(df, 100)
    assert parciais == 0
    assert com_barras.groupby("bar_id").size().to_dict() == {0: 3, 1: 1}
    assert com_barras.loc[com_barras["trade_type"] == RLP, "bar_id"].iloc[0] == 0


def test_negocio_que_cruza_pertence_a_barra_que_completa() -> None:
    df = _df([(BUY, 95, 10.0, 1, 2), (BUY, 10, 10.0, 1, 2), (BUY, 100, 10.0, 1, 2)])
    com_barras, _ = bars.atribuir_barras(df, 100)
    assert list(com_barras["bar_id"]) == [0, 0, 1]


def test_parcial_do_fim_do_dia_e_descartada() -> None:
    df = _df([(BUY, 100, 10.0, 1, 2), (SELL, 30, 10.0, 3, 4)])   # 30 sobra
    com_barras, parciais = bars.atribuir_barras(df, 100)
    assert parciais == 1
    assert len(com_barras) == 1


def test_barra_nao_atravessa_dias() -> None:
    # Por dia: 60+60 fecham a barra (o 2o cruza e pertence a ela); o 3o de 30
    # inicia uma parcial que deve ser descartada. Dois dias = 2 parciais.
    df = _df([(BUY, 60, 10.0, 1, 2), (BUY, 60, 10.0, 1, 2), (BUY, 30, 10.0, 1, 2)] * 2)
    df.loc[3:, "dt"] = "2024-01-03"
    com_barras, parciais = bars.atribuir_barras(df, 100)
    assert parciais == 2
    assert sorted(com_barras["bar_id"].unique()) == [0, 1]
    assert com_barras.groupby("bar_id").size().to_dict() == {0: 2, 1: 2}


def test_sugestao_de_threshold_usa_mediana() -> None:
    df = pd.concat([
        _df([(BUY, 1000, 10.0, 1, 2)]).assign(dt="2024-01-02"),
        _df([(BUY, 1000, 10.0, 1, 2)]).assign(dt="2024-01-03"),
        _df([(BUY, 100_000, 10.0, 1, 2)]).assign(dt="2024-01-04"),  # outlier
    ], ignore_index=True)
    # mediana=1000, alvo 10 barras/dia -> 100; a media (34k) daria ~3400.
    assert bars.sugerir_volume_barra(df, barras_por_dia=10) == 100


# ---------------------------------------------------------------- flow
def _barras_simples() -> pd.DataFrame:
    df = _df([
        (BUY, 70, 10.00, 1, 9),
        (SELL, 30, 10.05, 9, 1),      # fecha barra 0: buy 70, sell 30
        (RLP, 50, 10.05, 7, 8),
        (SELL, 100, 10.10, 9, 1),     # fecha barra 1: buy 0, sell 100
    ])
    com_barras, _ = bars.atribuir_barras(df, 100)
    return flow.calcular(com_barras, agentes=[1, 9], tick=0.05)


def test_imbalance_e_fluxo_por_agente_calculados_a_mao() -> None:
    b = _barras_simples()
    assert b.loc[0, "imbalance"] == pytest.approx((70 - 30) / 100)
    assert b.loc[1, "imbalance"] == pytest.approx(-1.0)
    # agente 1: comprou 70 e vendeu 30 na barra 0 -> +0.4; barra 1 vendeu 100 -> -1
    assert b.loc[0, "agf_1"] == pytest.approx(0.4)
    assert b.loc[1, "agf_1"] == pytest.approx(-1.0)
    assert b.loc[0, "agf_9"] == pytest.approx(-0.4)   # espelho


def test_rlp_frac_e_absorcao() -> None:
    b = _barras_simples()
    assert b.loc[1, "rlp_frac"] == pytest.approx(50 / 150)
    # barra 0: range 0.05 = 1 tick; vol 100 -> absorcao 100
    assert b.loc[0, "absorcao"] == pytest.approx(100.0)


def test_ohlc_ignora_rlp() -> None:
    df = _df([
        (BUY, 100, 10.00, 1, 2),
        (RLP, 10, 99.99, 7, 8),       # preco absurdo NAO pode entrar no high
        (BUY, 100, 10.10, 1, 2),
    ])
    com_barras, _ = bars.atribuir_barras(df, 100)
    b = flow.calcular(com_barras, agentes=[], tick=0.05)
    assert b["high"].max() == pytest.approx(10.10)


# ---------------------------------------------------------------- normalize
def test_zscore_nao_ve_o_presente() -> None:
    """
    Serie constante e depois um degrau: o z do degrau deve ser calculado com a
    estatistica ANTERIOR (desvio 0 -> NaN), nunca com uma que ja inclui o
    degrau. Se este teste quebrar, ha lookahead na normalizacao.
    """
    s = pd.Series([1.0] * 10 + [5.0])
    z = normalize.zscore_rolante(s, janela=5)
    assert np.isnan(z.iloc[10])           # desvio do passado estrito era 0
    s2 = pd.Series([1.0, 2.0, 1.0, 2.0, 1.0, 2.0, 10.0])
    z2 = normalize.zscore_rolante(s2, janela=4)
    media_passada = np.mean([1.0, 2.0, 1.0, 2.0])
    desvio_passado = np.std([1.0, 2.0, 1.0, 2.0], ddof=1)
    assert z2.iloc[6] == pytest.approx((10.0 - media_passada) / desvio_passado)


# ---------------------------------------------------------------- labels
def _barras_para_label(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({
        "close": closes,
        "high": [c * 1.001 for c in closes],
        "low": [c * 0.999 for c in closes],
    })


def test_triple_barrier_toque_superior() -> None:
    # 30 barras estaveis p/ sigma, depois alta forte: label +1
    closes = [100.0 + 0.1 * ((-1) ** i) for i in range(30)] + [103.0, 103.0]
    b = labels.triple_barrier(_barras_para_label(closes), k=2.0, h=5, janela_vol=20)
    idx = 29                              # ultima barra antes da alta
    assert b.loc[idx, "label_valida"]
    assert b.loc[idx, "label"] == 1
    assert b.loc[idx, "t_evento"] == 30


def test_triple_barrier_vertical_da_zero() -> None:
    closes = [100.0 + 0.1 * ((-1) ** i) for i in range(40)]
    b = labels.triple_barrier(_barras_para_label(closes), k=50.0, h=3, janela_vol=20)
    validas = b[b["label_valida"]]
    assert (validas["label"] == 0).all()
    assert (validas["t_evento"] - validas.index == 3)[:-3].all()


def test_toque_ambiguo_vira_zero_marcado() -> None:
    closes = [100.0 + 0.1 * ((-1) ** i) for i in range(30)]
    barras_df = _barras_para_label([*closes, 100.0])
    # barra futura com range gigante: cruza as duas barreiras ao mesmo tempo
    barras_df.loc[30, "high"] = 110.0
    barras_df.loc[30, "low"] = 90.0
    b = labels.triple_barrier(barras_df, k=2.0, h=5, janela_vol=20)
    assert b.loc[29, "label"] == 0
    assert bool(b.loc[29, "label_ambigua"])


def test_streaming_equivale_ao_monolitico(tmp_path) -> None:
    """
    REFATORO DE MEMORIA (2026-08-23): o pipeline passou a processar dia a dia
    (21 pregoes estouraram >20GB no monolitico). Este teste trava a promessa
    de ZERO mudanca semantica: o resultado do streaming deve ser IDENTICO ao
    que o caminho monolitico (carregar tudo, barrar tudo) produziria.
    """
    import numpy as np
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq

    from profittape.features import bars, flow, labels, normalize
    from profittape.features.pipeline import COLUNAS_Z, gerar

    rng = np.random.default_rng(11)
    curated = tmp_path / "curated"
    linhas_todas = []
    ts = 1_700_000_000_000_000_000
    for dia in ("2026-08-11", "2026-08-12", "2026-08-13"):
        n = 4000
        df_dia = pd.DataFrame({
            "ts_ns": ts + np.arange(n) * 10**8,
            "symbol": "WINFUT", "exchange": "F",
            "trade_id": np.arange(n),
            "price": 140000 + np.cumsum(rng.choice([-5, 0, 5], n)).astype(float),
            "volume_financeiro": 1.0,
            "quantidade": rng.integers(1, 30, n),
            "agente_comprador": rng.choice([3, 85, 1618, 120], n),
            "agente_vendedor": rng.choice([3, 85, 1618, 120], n),
            "trade_type": rng.choice([2, 3, 13], n, p=[0.4, 0.4, 0.2]),
            "is_edit": False,
            "dt": dia,
        })
        d = curated / "trade" / f"dt={dia}" / "sym=WINFUT"
        d.mkdir(parents=True)
        # Fiel a producao: o curate NAO grava dt como coluna fisica — vive
        # so' no caminho. Foi exatamente essa diferenca que escondeu o bug
        # do FieldRef.Name(dt) do teste original.
        pq.write_table(pa.table(df_dia.drop(columns=["dt"])),
                       d / "part-0000.parquet")
        linhas_todas.append(df_dia)
        ts += n * 10**8 + 10**12

    # STREAMING (o pipeline real)
    r = gerar(curated, tmp_path / "features", "WINFUT",
              barras_por_dia=40, top_n_agentes=3, janela_z=20)
    streaming = pd.read_parquet(r["arquivo"])

    # MONOLITICO (referencia inline, o caminho antigo)
    df = pd.concat(linhas_todas, ignore_index=True)
    df["dt"] = pd.Categorical(df["dt"])
    vb = bars.sugerir_volume_barra(df, 40)
    tick = bars.inferir_tick(df)
    dfb, _ = bars.atribuir_barras(df, vb)
    ag = flow.top_agentes(dfb, 3)
    ref = flow.calcular(dfb, ag, tick)
    ref = normalize.aplicar(ref, COLUNAS_Z + [f"agf_{a}" for a in ag], 20)
    ref = labels.triple_barrier(ref, k=2.0, h=10)

    assert r["volume_barra"] == vb
    assert r["tick_inferido"] == tick
    assert r["agentes_top"] == ag
    assert len(streaming) == len(ref)
    pd.testing.assert_frame_equal(
        streaming.reset_index(drop=True), ref.reset_index(drop=True),
        check_dtype=False, check_categorical=False,
    )
