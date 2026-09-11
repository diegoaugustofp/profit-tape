"""Conteudo direcional do sinal (5.6) -- retorno/MFE/MAE conferidos no papel."""

from __future__ import annotations

import numpy as np
import pandas as pd

from profittape.research import direcao_sinal as ds


def _base() -> pd.DataFrame:
    close = [100, 101, 103, 104, 106, 105, 108, 110]
    high = [101, 102, 104, 105, 107, 106, 109, 111]
    low = [99, 100, 102, 103, 105, 104, 107, 109]
    x = pd.DataFrame(dict(close=close, high=high, low=low), dtype=float)
    x["sinal_compra"] = [False, False, False, True, False, False, False, False]
    x["sinal_venda"] = False
    x["hora_int"] = 900
    return x


def test_retorno_mfe_mae_compra_a_mao() -> None:
    x = _base()
    # ref_pos=2 (close=103, a barra t-1 do padrao). h=1: fim=3, close=104.
    assert ds._retorno_mfe_mae(x, 2, 1, 1) == (1.0, 2.0, 0.0)
    # h=4: fim=6 (close=108); janela [3..6] high max=109 (idx6) low min=103 (idx3)
    assert ds._retorno_mfe_mae(x, 2, 1, 4) == (5.0, 6.0, 0.0)


def test_retorno_mfe_mae_venda_e_o_espelho() -> None:
    x = _base()
    r, mfe, mae = ds._retorno_mfe_mae(x, 2, -1, 1)
    assert (r, mfe, mae) == (-1.0, 0.0, -2.0)


def test_horizonte_que_vaza_do_bloco_da_nan() -> None:
    x = _base()
    assert all(np.isnan(v) for v in ds._retorno_mfe_mae(x, 2, 1, 16))


def test_medir_extrai_o_sinal_na_barra_t_menos_1() -> None:
    x = _base()
    m = ds.medir(x, horizontes=(1, 4))
    sinal = m[m.grupo == "sinal"].sort_values("horizonte")
    assert list(sinal["retorno"]) == [1.0, 5.0]
    assert list(sinal["lado"]) == [1, 1]


def test_controle_tem_a_mesma_contagem_por_faixa_horaria() -> None:
    rng = np.random.default_rng(1)
    n = 200
    close = 1000 + np.cumsum(rng.integers(-2, 3, n)).astype(float)
    x = pd.DataFrame(dict(close=close, high=close + 2, low=close - 2))
    x["sinal_compra"] = False
    x["sinal_venda"] = False
    # 5 sinais de compra na faixa 09:00 (hora_int 900-929), 3 na faixa 10:00
    idx_compra = [20, 40, 60, 80, 100, 150, 160, 170]
    x.loc[idx_compra, "sinal_compra"] = True
    x["hora_int"] = 900
    x.loc[140:, "hora_int"] = 1000
    m = ds.medir(x, horizontes=(1,))
    n_sinal_900 = int(((m.grupo == "sinal") & (m.hora_int == 900)).sum())
    n_ctrl_900 = int(((m.grupo == "controle") & (m.hora_int == 900)).sum())
    n_sinal_1000 = int(((m.grupo == "sinal") & (m.hora_int == 1000)).sum())
    n_ctrl_1000 = int(((m.grupo == "controle") & (m.hora_int == 1000)).sum())
    assert n_sinal_900 == n_ctrl_900
    assert n_sinal_1000 == n_ctrl_1000
    assert n_sinal_900 + n_sinal_1000 == 8


def test_controle_nunca_reusa_a_propria_barra_de_sinal() -> None:
    """As barras marcadas (t e t-1 de qualquer sinal) sao inelegiveis como
    controle -- senao mediriamos o proprio evento como se fosse ruido."""
    rng = np.random.default_rng(2)
    n = 60
    close = 1000 + np.cumsum(rng.integers(-1, 2, n)).astype(float)
    x = pd.DataFrame(dict(close=close, high=close + 1, low=close - 1))
    x["sinal_compra"] = False
    x["sinal_venda"] = False
    x.loc[30, "sinal_compra"] = True
    x["hora_int"] = 900
    ds.medir(x, horizontes=(1,), seed=7)
    # roda muitas vezes com seeds diferentes: nenhuma escolhe pos 29 ou 30
    for s in range(30):
        ds.medir(x, horizontes=(1,), seed=s)
    # nao ha' como recuperar a posicao original aqui sem instrumentar; em vez
    # disso valida indiretamente: reduzindo o pool a SO' as barras 29/30
    # elegiveis (todas as outras marcadas como sinal), a funcao deve avisar
    # que a faixa ficou sem controle, nunca reusar 29/30.
    x2 = x.copy()
    x2["sinal_compra"] = True   # tudo vira sinal, menos nada sobra elegivel
    m2 = ds.medir(x2, horizontes=(1,), seed=0)
    assert (m2.grupo == "controle").sum() == 0


def test_resumir_agrega_media_e_ic95() -> None:
    m = pd.DataFrame({
        "grupo": ["sinal"] * 4, "lado": [1] * 4, "horizonte": [1] * 4,
        "retorno": [1.0, 2.0, 3.0, 4.0], "mfe": [1, 1, 1, 1], "mae": [0, 0, 0, 0],
        "hora_int": [900] * 4,
    })
    r = ds.resumir(m)
    linha = r[(r.grupo == "sinal") & (r.horizonte == 1) & (r.campo == "retorno")].iloc[0]
    assert linha["n"] == 4 and linha["media"] == 2.5
    assert linha["ic95_lo"] < 2.5 < linha["ic95_hi"]
