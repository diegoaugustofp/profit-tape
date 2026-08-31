"""
Testes da verificacao de recuperacao por GetHistoryTrades.

O modulo existe para responder "da' para recuperar tape perdido?", e o
primeiro uso NAO e' preencher buraco: e' pedir um dia que ja' temos e
comparar. "Esta documentado" e "funciona" sao coisas diferentes.
"""

from __future__ import annotations

import pandas as pd

from profittape.recorder.recuperacao import (
    comparar,
    normalizar_historico,
)

S = 1_000_000_000


def _negocios(n: int = 100, trade_type: int = 2) -> pd.DataFrame:
    return pd.DataFrame({
        "trade_number": range(1, n + 1),
        "price": [100_000.0 + i * 5 for i in range(n)],
        "quantidade": [1 + (i % 3) for i in range(n)],
        "trade_type": trade_type,
        "agente_comprador": 1,
        "agente_vendedor": 2,
    })


def test_identicos_conferem() -> None:
    d = _negocios()
    c = comparar(d, d.copy(), "2026-08-25")
    assert c.confere
    assert c.em_ambos == 100 and c.so_no_curated == 0


def test_historico_incompleto_e_detectado() -> None:
    cur = _negocios(100)
    his = _negocios(100).iloc[:70]
    c = comparar(cur, his, "2026-08-25")
    assert not c.confere
    assert c.so_no_curated == 30


def test_mesma_contagem_com_conteudo_DIFERENTE_e_detectado() -> None:
    """
    O caso que motiva a segunda etapa: contar linhas nao basta. Dois
    conjuntos podem ter o mesmo tamanho e conteudo diferente.
    """
    cur = _negocios(100, trade_type=2)
    his = _negocios(100, trade_type=2)
    his.loc[his.index[:40], "trade_type"] = 3      # agressao trocada
    c = comparar(cur, his, "2026-08-25")
    assert c.n_curated == c.n_historico == 100
    assert c.em_ambos == 100
    assert not c.confere, "contagem igual nao pode passar por 'confere'"
    assert c.divergencias[0]["campo"] == "trade_type"
    assert c.divergencias[0]["linhas_diferentes"] == 40


def test_agressao_zerada_no_historico_e_detectada() -> None:
    """
    A falha mais provavel, dado o historico deste projeto: em
    2026-08-31, `AgressionVolBuy/Sell` devolveu ZERO em 2.001 barras sem
    erro nenhum. Se o `GetHistoryTrades` vier sem `trade_type`, a
    verificacao TEM que acusar — e' pior recuperar dado silenciosamente
    diferente do que nao recuperar.
    """
    cur = _negocios(50, trade_type=2)
    his = _negocios(50, trade_type=0)              # tipo ausente/zerado
    c = comparar(cur, his, "2026-08-25")
    assert not c.confere
    assert any(d["campo"] == "trade_type" and d["pct"] == 100.0
               for d in c.divergencias)


def test_conjunto_vazio_nao_passa_por_confere() -> None:
    """Comparar com o vazio nao mede nada, e nao pode ser lido como sucesso."""
    c = comparar(_negocios(10), pd.DataFrame(), "2026-08-25")
    assert not c.confere
    assert c.so_no_curated == 10


def test_normaliza_data_do_callback() -> None:
    """
    `pwcDate` vem como DD/MM/YYYY HH:mm:SS.ZZZ. Converter errado daria
    "nenhum negocio em comum", que pareceria falha da API.
    """
    df = normalizar_historico([
        {"data": "25/08/2026 10:30:15.250", "trade_number": 7,
         "price": 140_000.0, "quantidade": 2, "trade_type": 2},
    ])
    esperado = pd.Timestamp("2026-08-25 10:30:15.250").value
    assert df["ts_ns"].iloc[0] == esperado


def test_normaliza_lista_vazia_sem_estourar() -> None:
    df = normalizar_historico([])
    assert df.empty and "trade_type" in df.columns


def test_resumo_tem_o_veredito() -> None:
    c = comparar(_negocios(5), _negocios(5), "2026-08-25")
    r = c.resumo()
    assert r["confere"] is True and r["dia"] == "2026-08-25"
