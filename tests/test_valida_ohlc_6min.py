"""
OHLC de 6 min: o do Profit contra a nossa agregacao (lacuna 11.4).

O dump provou que a FORMULA bate, sobre o OHLC do PROFIT. O codigo usa
o OHLC agregado do NOSSO tape -- se divergirem, o estocastico diverge
junto, com a formula certa e o resultado errado.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from profittape.research.valida_ohlc_6min import agregar_15s_para_6min, comparar

_UTC = int(pd.Timestamp("2026-09-01 12:00:00").timestamp()) * 10**9   # 09:00 local


def _barras15(n: int = 48) -> pd.DataFrame:
    v = np.arange(n, dtype=float)
    return pd.DataFrame({
        "ts_ini_ns": _UTC + np.arange(n) * 15 * 10**9,
        # `ts` com offset -3h, como barras_15s_do_tape produz
        "ts": pd.to_datetime([(_UTC + i * 15 * 10**9) // 10**9 - 3 * 3600
                              for i in range(n)], unit="s"),
        "dia": "2026-09-01", "open": v, "high": v + 2, "low": v - 1, "close": v + 1})


def test_agrega_24_barras_e_confere_com_a_conta_a_mao() -> None:
    a = agregar_15s_para_6min(_barras15(48))
    assert list(a["n15"]) == [24, 24]
    assert list(a["open"]) == [0.0, 24.0]
    assert list(a["high"]) == [25.0, 49.0]
    assert list(a["low"]) == [-1.0, 23.0]
    assert list(a["close"]) == [24.0, 48.0]


def test_hora_sai_no_RELOGIO_DA_BOLSA_nao_em_UTC() -> None:
    """O dump usa a hora local. Se a agregacao devolvesse UTC, o merge
    casaria barras de horarios diferentes -- e a comparacao daria
    divergencia onde nao ha' (ou pior, silencio onde ha')."""
    a = agregar_15s_para_6min(_barras15(48))
    assert list(a["hora_int"]) == [900, 906]


def test_ohlc_identico_BATE() -> None:
    p = pd.DataFrame({"dia": ["2026-09-01"] * 2, "hora_int": [900, 906],
                      "open": [100.0, 110.0], "high": [105.0, 115.0],
                      "low": [99.0, 109.0], "close": [104.0, 114.0]})
    n = p.copy()
    n["n15"] = 24
    c = comparar(p, n)
    assert c.bateu and c.barras_casadas == 2
    assert all(v == 0.0 for v in c.dif_max.values())


def test_divergencia_no_HIGH_e_detectada() -> None:
    """High e low sao os mais sensiveis: divergem se QUALQUER negocio a
    mais ou a menos entrar (filtro de tipos diferente, por exemplo)."""
    p = pd.DataFrame({"dia": ["2026-09-01"], "hora_int": [900],
                      "open": [100.0], "high": [105.0], "low": [99.0],
                      "close": [104.0]})
    n = p.copy()
    n["n15"] = 24
    n.loc[0, "high"] = 104.0        # nosso high menor: faltou um negocio
    c = comparar(p, n)
    assert not c.bateu
    assert c.dif_max["high"] == pytest.approx(1.0)
    assert c.dif_qtd["high"] == 1


def test_barra_que_SO_o_profit_tem_e_reportada() -> None:
    """Nao silenciar: uma barra que o Profit tem e nos nao significa que
    o EA operaria com contexto diferente naquele momento."""
    p = pd.DataFrame({"dia": ["2026-09-01"] * 2, "hora_int": [900, 906],
                      "open": [100.0, 110.0], "high": [105.0, 115.0],
                      "low": [99.0, 109.0], "close": [104.0, 114.0]})
    n = p.iloc[:1].copy()
    n["n15"] = 24
    c = comparar(p, n)
    assert c.so_no_profit == 1 and not c.bateu


def test_tolerancia_e_ZERO() -> None:
    """OHLC e' preco de negocio -- nao tem arredondamento. Meio ponto de
    diferenca ja' e' divergencia de verdade."""
    p = pd.DataFrame({"dia": ["2026-09-01"], "hora_int": [900],
                      "open": [100.0], "high": [105.0], "low": [99.0],
                      "close": [104.0]})
    n = p.copy()
    n["n15"] = 24
    n.loc[0, "close"] = 104.5
    assert not comparar(p, n).bateu


def test_sem_barras_nao_quebra() -> None:
    assert agregar_15s_para_6min(pd.DataFrame()).empty
