"""
Testes da leitura de `F` a partir do tape (Rota B).

Os valores esperados foram conferidos A MAO antes de virarem teste
(regra 4). O cenario e' o mesmo da conferencia manual.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from profittape.research.preenchimento import (
    localizar_preenchimentos,
    localizar_toque,
    preparar_tape,
)

S = 1_000_000_000


def _tape() -> pd.DataFrame:
    #  ts   preco  tipo
    #   0    100     2  agressao  <- negocio de ENTRADA
    #  10    105     2  agressao
    #  20    112    13  RLP       <- cruza 110, mas RLP nao dispara
    #  30    108     3  agressao
    #  40    114     2  agressao  <- primeira AGRESSAO que cruza 110
    #  50    130     2  agressao
    linhas = [(0, 100.0, 2), (10 * S, 105.0, 2), (20 * S, 112.0, 13),
              (30 * S, 108.0, 3), (40 * S, 114.0, 2), (50 * S, 130.0, 2)]
    return pd.DataFrame(linhas, columns=["ts_ns", "price", "trade_type"])


def test_primeiro_negocio_de_agressao_que_cruza() -> None:
    r = localizar_toque(preparar_tape(_tape()), 0, 60 * S, 110.0, -1)
    assert r == (40 * S, 114.0)


def test_preco_vem_da_linha_certa() -> None:
    """
    Bug real, pego na conferencia a mao: o indice do preco era deslocado
    duas vezes (fatiava a janela e indexava com o indice absoluto). O
    TIMESTAMP saia certo e o PRECO vinha de outra linha — num agregado,
    `F` ficaria levemente torto sem nada parecer quebrado.
    """
    ts, preco = localizar_toque(preparar_tape(_tape()), 0, 60 * S, 110.0, -1)  # type: ignore[misc]
    tape = preparar_tape(_tape())
    esperado = float(tape.loc[tape["ts_ns"] == ts, "price"].iloc[0])
    assert preco == esperado


def test_rlp_nao_dispara_por_default_mas_dispara_se_pedido() -> None:
    assert localizar_toque(preparar_tape(_tape(), so_agressao=True),
                           0, 60 * S, 110.0, -1) == (40 * S, 114.0)
    assert localizar_toque(preparar_tape(_tape(), so_agressao=False),
                           0, 60 * S, 110.0, -1) == (20 * S, 112.0)


def test_o_proprio_negocio_de_entrada_nao_dispara() -> None:
    """Intervalo aberto no inicio: a entrada nao aciona o proprio stop."""
    assert localizar_toque(preparar_tape(_tape()),
                           40 * S, 60 * S, 110.0, -1) == (50 * S, 130.0)


def test_janela_fechada_no_fim_e_sem_toque() -> None:
    assert localizar_toque(preparar_tape(_tape()), 0, 30 * S, 110.0, -1) is None
    assert localizar_toque(preparar_tape(_tape()), 0, 60 * S, 102.0, +1) is None
    assert localizar_toque(preparar_tape(_tape()), 0, 60 * S, 106.0, +1) == (
        10 * S, 105.0)


def test_F_e_o_preco_negociado_nao_o_nivel() -> None:
    """
    O overshoot do cruzamento e' real e e' o que um stop paga. Usar o
    nivel seria o limite 'otimista' do pre-registro anulado em
    2026-08-29c.
    """
    _, f = localizar_toque(preparar_tape(_tape()), 0, 60 * S, 110.0, -1)  # type: ignore[misc]
    assert f == 114.0 and f > 110.0


def test_tape_fora_de_ordem_e_ordenado() -> None:
    """
    'Primeiro negocio que cruza' so' faz sentido em sequencia ordenada.
    Sem a ordenacao, o resultado seria um `F` posterior, sem erro visivel.
    """
    embaralhado = _tape().sample(frac=1.0, random_state=3)
    assert localizar_toque(preparar_tape(embaralhado),
                           0, 60 * S, 110.0, -1) == (40 * S, 114.0)


def test_lote_de_entradas() -> None:
    entradas = pd.DataFrame({
        "ts_entrada": [0, 0, 40 * S],
        "ts_limite": [60 * S, 30 * S, 60 * S],
        "nivel": [110.0, 110.0, 110.0],
        "lado": [-1, -1, -1],
    })
    r = localizar_preenchimentos(preparar_tape(_tape()), entradas)
    assert list(r["tocou"]) == [True, False, True]
    assert r["F"].tolist()[0] == 114.0
    assert np.isnan(r["F"].tolist()[1])


def test_entradas_sem_colunas_obrigatorias() -> None:
    with pytest.raises(ValueError, match="nivel"):
        localizar_preenchimentos(preparar_tape(_tape()),
                                 pd.DataFrame({"ts_entrada": [0]}))


def test_sob_martingal_o_remanescente_medio_e_zero() -> None:
    """
    A PROPRIEDADE QUE TORNA O ESTIMADOR VALIDO.

    `F` e' o preco do primeiro negocio a cruzar o nivel — um tempo de
    parada legitimo na filtracao dos negocios. Pelo teorema da parada
    opcional, sob martingal E[preco_final - F] = 0.

    E' isto que os dois estimadores anteriores NAO tinham: o extremo de
    uma barra so' e' conhecido no fechamento dela, usa informacao do
    futuro dentro da barra, e nao e' tempo de parada. Sobre ruido puro
    um devolveu t ~ -25 e o outro +30 pontos com t ~ 13.

    Aqui o teste e' direto: passeio aleatorio simetrico, stop a -X, e o
    remanescente medio a partir de F tem que ser estatisticamente zero.
    """
    rng = np.random.default_rng(20260830)
    n_caminhos, n_passos, nivel_rel = 4000, 400, 20.0
    remanescentes = []
    for _ in range(n_caminhos):
        passos = rng.choice([-5.0, 5.0], size=n_passos)
        precos = 100_000.0 + np.cumsum(passos)
        tape = pd.DataFrame({
            "ts_ns": np.arange(1, n_passos + 1, dtype=np.int64) * S,
            "price": precos,
            "trade_type": 2,
        })
        r = localizar_toque(preparar_tape(tape), 0, n_passos * S,
                            100_000.0 + nivel_rel, -1)
        if r is None:
            continue
        # vendido: ganha se o preco CAI a partir de F
        remanescentes.append(F := r[1])
        remanescentes[-1] = F - precos[-1]

    rem = np.array(remanescentes)
    assert len(rem) > 1000, "poucos caminhos tocaram o nivel"
    t = rem.mean() / (rem.std(ddof=1) / np.sqrt(len(rem)))
    assert abs(t) < 3.0, f"vies detectado: media={rem.mean():.2f} t={t:.2f}"
