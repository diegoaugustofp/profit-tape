"""
Testes do pre-registro de absorcao de barra (congelado 2026-08-31).

Os valores congelados sao verificados como CONSTANTES: se alguem mudar
um corte sem pre-registro novo, o teste falha e diz por que.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from profittape.research import absorcao_barra as ab


def _barras(n: int = 300, semente: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(semente)
    preco = 140_000.0
    linhas = []
    for _ in range(n):
        amp = rng.gamma(4.0, 40.0)
        o = preco
        c = o + rng.normal(0, amp / 3)
        h = max(o, c) + rng.gamma(2.0, amp / 6)
        low = min(o, c) - rng.gamma(2.0, amp / 6)
        linhas.append({"dia": pd.Timestamp("2026-08-24").date(),
                       "open": o, "high": h, "low": low, "close": c,
                       "vol_agr": (h - low) * rng.gamma(20.0, 5.0)})
        preco = c
    b = pd.DataFrame(linhas)
    a = b["high"] - b["low"]
    b["desloc_norm"] = ((b["close"] - b["open"]) / a).where(a > 0, 0.0)
    return b


def test_parametros_congelados_nao_mudam_sem_pre_registro() -> None:
    """
    Guarda os numeros do pre-registro. Mudar qualquer um exige
    pre-registro NOVO, nao edicao do modulo -- e um teste que falha e'
    mais barato que descobrir a mudanca tres rodadas depois.
    """
    assert ab.MAX_DESLOC_NORM == 0.25
    assert ab.MIN_Z_AMPLITUDE == 0.50
    assert ab.MIN_Z_VOL_AGR == 0.50
    assert ab.JANELA_CONTEXTO == 6      # ~30 min, do relato do operador
    assert ab.K_CONTEXTO == 3.0         # reduzido de 5 por amostra
    assert ab.HORIZONTE == 2
    assert ab.N_MINIMO == 30


def test_o_evento_e_conjuncao_das_TRES_condicoes() -> None:
    """
    Nenhuma condicao sozinha basta. Combinar as tres num numero unico
    repetiria o erro do `absorcao_dir`, em que a subtracao escondia dois
    casos OPOSTOS sob o mesmo valor extremo.
    """
    d = ab.marcar_eventos(ab.preparar(_barras()))
    v = d.dropna(subset=["z_amplitude", "z_vol_agr"])
    assert (v.loc[v["evento"], "desloc_norm"].abs() <= ab.MAX_DESLOC_NORM).all()
    assert (v.loc[v["evento"], "z_amplitude"] >= ab.MIN_Z_AMPLITUDE).all()
    assert (v.loc[v["evento"], "z_vol_agr"] >= ab.MIN_Z_VOL_AGR).all()
    # e cada condicao isolada aceita mais barras que a conjuncao
    so_desloc = (v["desloc_norm"].abs() <= ab.MAX_DESLOC_NORM).sum()
    assert so_desloc > v["evento"].sum()


def test_lado_e_CONTRARIO_ao_movimento() -> None:
    """Subiu muito e travou -> viés de BAIXA. E' a hipotese de reversao."""
    d = pd.DataFrame({"mov_contexto": [5.0, -5.0, 0.0]})
    d["desloc_norm"] = 0.0
    d["z_amplitude"] = 1.0
    d["z_vol_agr"] = 1.0
    r = ab.marcar_eventos(d)
    assert list(r["lado"]) == [-1, 1, 0]


def test_janela_nao_atravessa_o_pregao() -> None:
    """
    Purga estrutural: retorno que cruza a virada mede o gap noturno, nao
    o efeito da barra.
    """
    d = pd.DataFrame({
        "dia": [pd.Timestamp("2026-08-24").date()] * 2
               + [pd.Timestamp("2026-08-25").date()] * 2,
        "close": [100.0, 110.0, 120.0, 130.0],
        "lado": [1, 1, 1, 1],
        "mov_contexto": [5.0] * 4,
    })
    r = ab.retornos(d, pd.Series([True, True, False, False]))
    assert len(r) == 0, "nenhuma janela de 2 barras cabe dentro do dia 24"


def test_sem_lookahead_no_contexto() -> None:
    """
    `mov_contexto` usa shift(1) para tras: a propria barra nao entra no
    contexto que a habilita. Sem isso, o teste mediria a barra de entrada.
    """
    d = ab.preparar(_barras(n=120))
    i = 100
    esperado = ((d["close"].iloc[i - 1] - d["close"].iloc[i - 1 - ab.JANELA_CONTEXTO])
                / d["range_medio"].iloc[i])
    assert d["mov_contexto"].iloc[i] == pytest.approx(esperado)


def test_range_medio_nao_inclui_a_propria_barra() -> None:
    d = ab.preparar(_barras(n=120))
    i = 100
    esperado = (d["amplitude_pts"].iloc[i - ab.JANELA_Z:i]).mean()
    assert d["range_medio"].iloc[i] == pytest.approx(esperado)


def test_decidir_contra_quando_nada_e_significativo() -> None:
    pontos = [{"grupo": "evento+contexto BAIXA", "n": 50, "n_suficiente": True,
               "media": 1.0, "sig": False},
              {"grupo": "evento+contexto ALTA", "n": 50, "n_suficiente": True,
               "media": 1.0, "sig": False}]
    v, _ = ab.decidir(pontos)
    assert v == "CONTRA"


def test_controles_nao_entram_no_veredito() -> None:
    """Sao diagnostico: respondem 'a conjuncao acrescenta algo?'."""
    pontos = [
        {"grupo": "evento+contexto BAIXA", "n": 50, "n_suficiente": True,
         "media": 1.0, "sig": False},
        {"grupo": "evento+contexto ALTA", "n": 50, "n_suficiente": True,
         "media": 1.0, "sig": False},
        {"grupo": "CONTROLE contexto sem evento", "n": 900,
         "n_suficiente": True, "media": 50.0, "sig": True},
    ]
    v, _ = ab.decidir(pontos)
    assert v == "CONTRA", "controle significativo nao pode virar FAVORAVEL"


def test_decidir_invertido() -> None:
    pontos = [{"grupo": "evento+contexto BAIXA", "n": 50, "n_suficiente": True,
               "media": -20.0, "sig": True},
              {"grupo": "evento+contexto ALTA", "n": 50, "n_suficiente": True,
               "media": 1.0, "sig": False}]
    v, m = ab.decidir(pontos)
    assert v == "INVERTIDO" and "ao contrario" in m


def test_ruido_tem_amplitude_e_volume_CORRELACIONADOS() -> None:
    """
    Defeito real do primeiro gerador: volume sorteado INDEPENDENTE do
    caminho do preco dava corr +0,012 contra +0,892 do real. Como o
    evento exige amplitude E volume altos ao mesmo tempo, o ruido
    produzia 25x menos eventos -- e testava outra geometria.
    """
    d = ab.preparar(ab.gerar_ruido(n_dias=30)).dropna(
        subset=["amplitude_pts", "vol_agr"])
    r = float(np.corrcoef(d["amplitude_pts"], d["vol_agr"])[0, 1])
    assert r > 0.4, f"amplitude e volume precisam andar juntos, deu {r:.3f}"
