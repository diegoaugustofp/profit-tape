"""
Ordem STOP x LIMITADA no replay do scalp de Bollinger.

O DEFEITO QUE ISTO CORRIGE (2026-10-01, achado pelo operador)
--------------------------------------------------------------
A variante "rompimento" usava ordem LIMITADA no gatilho `high(t-1)`.
Mas uma limitada de COMPRA colocada ACIMA do preco corrente executa
IMEDIATAMENTE -- ela nunca espera o rompimento. Resultado: as 320
execucoes medidas vieram 100% como "abertura" e ZERO como "recuo", e o
que foi testado nao era rompimento nenhum: era entrada a mercado na
abertura da barra seguinte ao padrao.

O operador percebeu pelo grafico ("a abertura do candle fica na maioria
das vezes no fechamento do anterior"), que e' incompativel com o
comportamento que a explicacao previa.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from profittape.research import bollinger_replay as br

_BASE = int(pd.Timestamp("2026-09-01 10:00:00").timestamp())


def _tape(precos: list[float]) -> pd.DataFrame:
    ts = (np.array([_BASE + i for i in range(len(precos))], dtype="int64") * 10**9)
    return pd.DataFrame({"ts_ns": ts, "price": precos, "quantidade": 1,
                         "trade_type": 3, "symbol": "WINFUT"})


def _sinal(limite: float, compra: bool = True) -> pd.DataFrame:
    return pd.DataFrame({
        "ts_ini_ns": [_BASE * 10**9], "hora_int": [1000],
        "sinal_compra": [compra], "sinal_venda": [not compra],
        "preco_limite": [limite], "stop_pts": [50.0],
        "alvo1_pts": [50.0], "alvo2_pts": [81.0], "alvo3_pts": [125.0],
        "trailing_ativa_pts": [31.0], "trailing_puxa_pts": [12.5],
        "trailing_passo_pts": [6.0],
    })


def test_STOP_espera_o_gatilho_LIMITADA_nao() -> None:
    """O teste que prova o defeito. Mesmo tape, mesmo gatilho (107),
    abertura em 105: a limitada entra JA' a 105; a stop espera o preco
    subir ate' 107."""
    trades, sin = _tape([105.0, 106.0, 107.0, 108.0]), _sinal(107.0)
    lim = br.replay_pregao(sin, trades, "2026-09-01", tipo_ordem="limitada")[0]
    stop = br.replay_pregao(sin, trades, "2026-09-01", tipo_ordem="stop")[0]
    assert lim["tipo_execucao"] == "abertura" and lim["preco_entrada"] == 105.0
    assert stop["tipo_execucao"] == "rompimento" and stop["preco_entrada"] == 107.0


def test_STOP_entra_PIOR_no_gap() -> None:
    """Se a barra ja' abre alem do gatilho, a stop dispara na abertura e
    entra PIOR que o gatilho -- e' o custo real da ordem stop, e a
    limitada nunca teria esse custo (ela entraria melhor)."""
    trades, sin = _tape([108.5, 109.0]), _sinal(107.0)
    stop = br.replay_pregao(sin, trades, "2026-09-01", tipo_ordem="stop")[0]
    assert stop["tipo_execucao"] == "gap"
    assert stop["preco_entrada"] == 108.5, "entra na abertura, pior que os 107"


def test_STOP_nao_dispara_se_o_preco_nunca_alcanca_o_gatilho() -> None:
    trades, sin = _tape([105.0, 105.5, 106.0]), _sinal(107.0)
    stop = br.replay_pregao(sin, trades, "2026-09-01", tipo_ordem="stop")[0]
    assert not stop.get("executou", stop.get("preco_entrada") is not None)
    assert stop["motivo_nao_exec"] == "nao_atravessou"


def test_STOP_na_venda_e_o_espelho() -> None:
    """Venda: gatilho na perda da minima. Dispara quando o preco CAI ate'
    ele."""
    trades, sin = _tape([105.0, 104.0, 103.0, 102.0]), _sinal(103.0, compra=False)
    stop = br.replay_pregao(sin, trades, "2026-09-01", tipo_ordem="stop")[0]
    assert stop["tipo_execucao"] == "rompimento" and stop["preco_entrada"] == 103.0


def test_default_continua_LIMITADA() -> None:
    """Retrocompatibilidade (disciplina 5): sem `tipo_ordem`, o
    comportamento antigo tem que ser identico."""
    trades, sin = _tape([105.0, 106.0, 107.0]), _sinal(107.0)
    sem = br.replay_pregao(sin, trades, "2026-09-01")[0]
    explicito = br.replay_pregao(sin, trades, "2026-09-01", tipo_ordem="limitada")[0]
    assert sem["tipo_execucao"] == explicito["tipo_execucao"] == "abertura"
    assert sem["preco_entrada"] == explicito["preco_entrada"] == 105.0
