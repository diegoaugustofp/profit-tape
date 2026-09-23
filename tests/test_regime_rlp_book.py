"""
Funil de RLP e topo do livro como filtro de regime.

Categoria `features`: mede TAXA, nao desempenho. O que estes testes
protegem e' o calculo -- a DECISAO de direcao tem que vir de mecanismo
declarado, nunca da taxa (ver docstring do modulo).
"""

from __future__ import annotations

import pandas as pd
import pytest

from profittape.research.regime_rlp_book import (
    combinado,
    medir,
    rlp_por_barra,
    topo_do_livro_por_barra,
)

_BASE = int(pd.Timestamp("2026-09-01 10:00:00").timestamp()) * 10**9
_PASSO = 15 * 10**9


def test_rlp_confere_com_a_conta_a_mao() -> None:
    """2 RLP (10+20=30) e 2 de agressao (5+15=20) -> 30/50 = 0,60."""
    tr = pd.DataFrame({
        "ts_ns": [_BASE, _BASE + 10**9, _BASE + 2 * 10**9, _BASE + 3 * 10**9],
        "trade_type": [13, 13, 2, 3], "quantidade": [10, 20, 5, 15]})
    assert float(rlp_por_barra(tr, None).iloc[0]) == pytest.approx(0.60)


def test_rlp_ignora_tipos_que_nao_sao_agressao_nem_RLP() -> None:
    """Leilao (4) e demais tipos nao entram no denominador -- misturar
    leilao com agressao mediria dois fenomenos diferentes."""
    tr = pd.DataFrame({
        "ts_ns": [_BASE] * 3, "trade_type": [13, 2, 4],
        "quantidade": [10, 10, 1000]})
    assert float(rlp_por_barra(tr, None).iloc[0]) == pytest.approx(0.50)


def test_barra_sem_volume_da_NaN_e_nao_zero() -> None:
    """Sem negocio de agressao nem RLP nao existe fracao -- zero seria
    inventar 'nenhum RLP', que e' afirmacao diferente de 'nao sei'."""
    tr = pd.DataFrame({"ts_ns": [_BASE], "trade_type": [4], "quantidade": [100]})
    assert pd.isna(rlp_por_barra(tr, None).iloc[0])


def test_topo_do_livro_usa_o_ULTIMO_estado_do_balde() -> None:
    """O que importa para o sinal e' o livro como estava quando a barra
    fechou -- e' ele que a ordem vai encontrar. Media misturaria estados
    que ja' nao existem."""
    tb = pd.DataFrame({
        "ts_ns": [_BASE, _BASE + 10**9, _BASE + 2 * 10**9, _BASE + 3 * 10**9],
        "side": [0, 1, 0, 1], "price": [100, 101, 100, 101],
        "quantidade": [50, 10, 80, 20]})
    L = topo_do_livro_por_barra(tb)
    assert int(L["qtd_bid"][0]) == 80 and int(L["qtd_ask"][0]) == 20
    assert float(L["desequilibrio"][0]) == pytest.approx(0.60)


def test_desequilibrio_vai_de_menos_um_a_mais_um() -> None:
    """+1 = so' tem bid (livro de venda vazio): rompimento para cima sem
    resistencia. -1 = o oposto."""
    tb = pd.DataFrame({"ts_ns": [_BASE, _BASE + 10**9], "side": [0, 1],
                       "price": [100, 101], "quantidade": [100, 0]})
    assert float(topo_do_livro_por_barra(tb)["desequilibrio"][0]) == pytest.approx(1.0)
    tb2 = pd.DataFrame({"ts_ns": [_BASE, _BASE + 10**9], "side": [0, 1],
                        "price": [100, 101], "quantidade": [0, 100]})
    assert float(topo_do_livro_por_barra(tb2)["desequilibrio"][0]) == pytest.approx(-1.0)


def test_baldes_diferentes_nao_se_misturam() -> None:
    tb = pd.DataFrame({
        "ts_ns": [_BASE, _BASE, _BASE + _PASSO, _BASE + _PASSO],
        "side": [0, 1, 0, 1], "price": [100, 101, 100, 101],
        "quantidade": [10, 10, 90, 10]})
    L = topo_do_livro_por_barra(tb).sort_values("balde")
    assert float(L["desequilibrio"].iloc[0]) == pytest.approx(0.0)
    assert float(L["desequilibrio"].iloc[1]) == pytest.approx(0.8)


def _cenario(n_baldes: int = 20) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    baldes = [_BASE + i * _PASSO for i in range(n_baldes)]
    barras = pd.DataFrame({
        "ts": pd.to_datetime([b // 10**9 for b in baldes], unit="s"),
        "sinal_compra": [i % 2 == 0 for i in range(n_baldes)],
        "sinal_venda": [i % 2 == 1 for i in range(n_baldes)]})
    trades = pd.DataFrame({
        "ts_ns": [b for b in baldes for _ in range(2)],
        "trade_type": [13, 2] * n_baldes,
        "quantidade": [i for i in range(n_baldes) for _ in range(2)]})
    tiny = pd.DataFrame({
        "ts_ns": [b for b in baldes for _ in range(2)],
        "side": [0, 1] * n_baldes, "price": [100.0, 101.0] * n_baldes,
        "quantidade": [q for i in range(n_baldes) for q in (i + 1, n_baldes - i)]})
    return barras, trades, tiny


def test_funil_mede_os_DOIS_lados_de_cada_eixo() -> None:
    """Os dois lados sao medidos de proposito: taxa responde 'da' para
    medir?', nao 'qual lado esta' certo?'."""
    barras, trades, tiny = _cenario()
    linhas = medir(barras, trades, tiny)
    eixos = {x.eixo for x in linhas}
    assert eixos == {"rlp", "book"}
    for eixo in eixos:
        for lado in ("compra", "venda"):
            cortes = [x for x in linhas if x.eixo == eixo and x.lado == lado]
            assert len(cortes) == 2, f"{eixo}/{lado} precisa dos DOIS lados"
            # mediana: os dois lados somados dao o total com dado
            assert sum(c.passa for c in cortes) == cortes[0].com_dado


def test_combinado_mostra_o_custo_de_somar_clausulas() -> None:
    """Somar clausula multiplica restricao -- ja' matou um desenho neste
    projeto (326 eventos -> 62). As 4 combinacoes tem que somar o total."""
    barras, trades, tiny = _cenario()
    c = combinado(barras, trades, tiny)
    quatro = [c[f"{r}+{b}"] for r in ("rlp_alto", "rlp_baixo")
              for b in ("book_alto", "book_baixo")]
    assert sum(quatro) == c["com_os_dois_dados"]
    assert c["com_os_dois_dados"] <= c["candidatos"]
