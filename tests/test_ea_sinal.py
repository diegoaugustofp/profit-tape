"""
Testes de sinal.py — a peca central do EA. O teste que mais importa aqui e'
EQUIVALENCIA com o research: streaming trade-a-trade tem que produzir o
MESMO z-score que bars.atribuir_barras + flow.calcular + normalize.aplicar
em batch, para a mesma sequencia de trades. Qualquer divergencia e' o tipo
de bug que so' aparece com dinheiro real em jogo (ver docstring do modulo).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from profittape.ea.sinal import ConstrutorDeSinalAoVivo


def _trades_sinteticos(n: int, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "ts_ns": np.arange(n, dtype=np.int64) * 10**8,
        "symbol": "WINFUT", "trade_id": np.arange(n),
        "price": 140000.0 + np.cumsum(rng.choice([-5.0, 0.0, 5.0], n)),
        "quantidade": rng.integers(1, 10, n),
        "agente_comprador": rng.choice([3, 85, 1618], n),
        "agente_vendedor": rng.choice([3, 85, 1618], n),
        "trade_type": rng.choice([2, 3], n),   # so' agressao, sem RLP no teste
        "dt": "2026-08-26",
    })


def test_processar_trade_fecha_barra_no_volume_certo() -> None:
    c = ConstrutorDeSinalAoVivo(volume_barra=100, janela_z=10, agentes_rastreados=[3])
    fechada = None
    acumulado = 0
    df = _trades_sinteticos(500)
    for _, t in df.iterrows():
        r = c.processar_trade(t.ts_ns, t.price, t.quantidade, t.trade_type,
                              t.agente_comprador, t.agente_vendedor)
        acumulado += t.quantidade
        if r is not None:
            fechada = r
            break
    assert fechada is not None
    assert fechada.vol_agr >= 100          # pode passar um pouco (documentado)
    assert fechada.bar_id == 0


def test_primeiras_barras_saem_nan_ate_min_periods() -> None:
    """Espelha normalize.py: barras antes de janela_z//2 saem NaN, nao um
    numero de amostra minuscula fingindo precisao."""
    c = ConstrutorDeSinalAoVivo(volume_barra=50, janela_z=10, agentes_rastreados=[3])
    df = _trades_sinteticos(2000)
    primeira_nao_nan = None
    n_barras = 0
    for _, t in df.iterrows():
        r = c.processar_trade(t.ts_ns, t.price, t.quantidade, t.trade_type,
                              t.agente_comprador, t.agente_vendedor)
        if r is not None:
            n_barras += 1
            if primeira_nao_nan is None and not pd.isna(r.agf[3]):
                primeira_nao_nan = n_barras
    assert primeira_nao_nan is not None
    assert primeira_nao_nan >= 5   # min_periods = max(2, 10//2) = 5


def test_equivalencia_streaming_vs_batch_do_research() -> None:
    """
    O teste que mais importa: mesma sequencia de trades, mesmo volume_barra,
    mesma janela_z -- o z-score da N-esima barra em streaming tem que bater
    com o z-score da N-esima barra calculada em BATCH pelo pipeline real de
    features (bars.py + flow.py + normalize.py), dentro de tolerancia de
    ponto flutuante.
    """
    from profittape.features import bars, flow, normalize

    df = _trades_sinteticos(3000)
    volume_barra, janela_z, agente = 80, 12, 3

    # --- BATCH (o caminho que o research/pipeline.py realmente usa) ---
    df_barrado, _ = bars.atribuir_barras(df.assign(dt=pd.Categorical(df["dt"])),
                                         volume_barra)
    tick = 5.0
    barras_batch = flow.calcular(df_barrado, [agente], tick)
    barras_batch = normalize.aplicar(barras_batch, [f"agf_{agente}"], janela_z)

    # --- STREAMING (sinal.py) ---
    c = ConstrutorDeSinalAoVivo(volume_barra, janela_z, [agente])
    barras_stream = []
    for _, t in df.iterrows():
        r = c.processar_trade(t.ts_ns, t.price, t.quantidade, t.trade_type,
                              t.agente_comprador, t.agente_vendedor)
        if r is not None:
            barras_stream.append(r)

    n_comparar = min(len(barras_batch), len(barras_stream)) - 1  # ultima pode
    # divergir por causa do excesso de volume documentado no fechamento
    assert n_comparar >= 10, "poucas barras geradas para comparar com confianca"

    for i in range(n_comparar):
        z_batch = barras_batch.iloc[i][f"z_agf_{agente}"]
        z_stream = barras_stream[i].agf[agente]
        if pd.isna(z_batch):
            assert pd.isna(z_stream) or np.isnan(z_stream), (
                f"barra {i}: batch=NaN mas streaming={z_stream}"
            )
        else:
            assert z_stream == pytest.approx(z_batch, abs=1e-6), (
                f"barra {i}: batch={z_batch} streaming={z_stream}"
            )


def test_volume_barra_invalido_recusa() -> None:
    with pytest.raises(ValueError, match="positivo"):
        ConstrutorDeSinalAoVivo(volume_barra=0, janela_z=10, agentes_rastreados=[3])
    with pytest.raises(ValueError, match="positivo"):
        ConstrutorDeSinalAoVivo(volume_barra=-5, janela_z=10, agentes_rastreados=[3])
