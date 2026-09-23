"""
Estocastico de CONTEXTO (6 min) como filtro do scalp de Bollinger.

O que estes testes protegem, acima de tudo, e' a AUSENCIA DE
LOOK-AHEAD: uma barra de 6 minutos so' existe depois de fechar, e usar
o valor da barra que contem o sinal seria decidir com informacao que,
no instante do sinal, ainda nao aconteceu.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from profittape.research.bollinger_contexto import (
    SEGUNDOS_CONTEXTO,
    alinhar_contexto,
    barras_de_contexto,
    estocastico_de_contexto,
    medir_funil,
)

_BASE = (1_700_000_000 // SEGUNDOS_CONTEXTO) * SEGUNDOS_CONTEXTO * 10**9


def _barras15(n: int = 48, dia: str = "2026-09-01") -> pd.DataFrame:
    ts = _BASE + np.arange(n) * 15 * 10**9
    v = np.arange(n, dtype=float)
    return pd.DataFrame({"ts": ts, "dia": dia, "open": v, "high": v + 2,
                         "low": v - 1, "close": v + 1})


def test_agrega_24_barras_de_15s_por_barra_de_6min() -> None:
    ctx = barras_de_contexto(_barras15(48))
    assert len(ctx) == 2
    assert list(ctx["barras15"]) == [24, 24]
    # conferido a mao: b0 = barras 0..23, b1 = barras 24..47
    assert list(ctx["open"]) == [0.0, 24.0]
    assert list(ctx["high"]) == [25.0, 49.0]
    assert list(ctx["low"]) == [-1.0, 23.0]
    assert list(ctx["close"]) == [24.0, 48.0]


def test_SEM_LOOK_AHEAD_usa_a_ultima_barra_FECHADA() -> None:
    """O teste central. Uma barra de 15s dentro da 1a barra de 6 min nao
    pode enxergar o estocastico DELA -- essa barra ainda nao fechou."""
    x = _barras15(48)
    ctx = barras_de_contexto(x)
    ctx["est_ctx"] = [11.0, 77.0]
    v = alinhar_contexto(x, ctx, permitir_look_ahead=False)
    assert np.isnan(v[0]) and np.isnan(v[23]), (
        "dentro da 1a barra de contexto nao ha' barra fechada antes -- NaN")
    assert v[24] == 11.0 and v[47] == 11.0, (
        "na 2a barra, o valor disponivel e' o da 1a (que fechou), nao o da 2a")


def test_look_ahead_VAZA_o_futuro_e_e_por_isso_que_existe_a_trava() -> None:
    """Rodado contra o caso que a trava DEVE pegar (disciplina 7.3): com
    look-ahead, a barra 0 ja' enxerga o estocastico da barra de 6 min que
    so' vai fechar 6 minutos depois."""
    x = _barras15(48)
    ctx = barras_de_contexto(x)
    ctx["est_ctx"] = [11.0, 77.0]
    v = alinhar_contexto(x, ctx, permitir_look_ahead=True)
    assert v.iloc[0] == 11.0, "com look-ahead a barra 0 ve o futuro"
    assert v.iloc[24] == 77.0
    sem = alinhar_contexto(x, ctx, permitir_look_ahead=False)
    assert np.isnan(sem[0]) and v.iloc[0] == 11.0, (
        "os dois modos PRECISAM divergir -- se nao divergissem, a trava "
        "nao estaria travando nada")


def test_estocastico_de_contexto_usa_a_janela_das_barras_MAIORES() -> None:
    """A correcao de 2026-10-01: a janela de 8 periodos passa a ser de 8
    barras de 6 min (48 min), nao de 8 barras de 15s (2 min)."""
    x = _barras15(24 * 12)              # 12 barras de 6 min
    ctx = estocastico_de_contexto(barras_de_contexto(x))
    assert len(ctx) == 12
    # periodo 8 + media 3 => primeiro valor definido na 10a barra (indice 9)
    assert ctx["est_ctx"].iloc[:9].isna().all()
    assert ctx["est_ctx"].iloc[9:].notna().all()


def test_estocastico_reinicia_por_pregao() -> None:
    a, b = _barras15(24 * 10, "2026-09-01"), _barras15(24 * 10, "2026-09-02")
    b["ts"] = b["ts"] + 86_400 * 10**9
    ctx = estocastico_de_contexto(barras_de_contexto(pd.concat([a, b])))
    for dia in ("2026-09-01", "2026-09-02"):
        d = ctx[ctx["dia"] == dia]
        assert d["est_ctx"].iloc[:9].isna().all(), f"{dia} tem que reiniciar"


def test_funil_conta_os_dois_limiares() -> None:
    x = _barras15(24 * 12)
    x["sinal_compra"] = False
    x["sinal_venda"] = False
    x.loc[240:, "sinal_compra"] = True          # barras com contexto ja' definido
    linhas, comctx = medir_funil(x)
    compra = next(x for x in linhas if x.lado == "compra")
    assert compra.candidatos > 0
    assert compra.passa_direcao >= compra.passa_extremo, (
        "o limiar de direcao (<50) e' mais frouxo que o extremo (<20) -- "
        "tem que deixar passar pelo menos tanto quanto")
    assert "est_ctx" in comctx.columns


def test_sem_barras_nao_quebra() -> None:
    vazio = pd.DataFrame(columns=["ts", "dia", "open", "high", "low", "close"])
    assert barras_de_contexto(vazio).empty
    assert estocastico_de_contexto(pd.DataFrame()).empty
