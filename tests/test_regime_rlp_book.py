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
        # `ts_ini_ns` e' epoch PURO; `ts` carrega o offset de fuso (-3h),
        # como `barras_15s_do_tape` produz. O alinhamento usa ts_ini_ns
        # justamente para nao errar o relogio (bug real de 2026-09-23:
        # 3 horas de diferenca faziam o join nao casar NADA, sem erro).
        "ts_ini_ns": baldes,
        "ts": pd.to_datetime([b // 10**9 - 3 * 3600 for b in baldes], unit="s"),
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


def test_balde_usa_ts_ini_ns_e_nao_o_ts_com_FUSO() -> None:
    """ARMADILHA REAL (2026-09-23): a coluna `ts` das barras tem o offset
    de fuso somado; `ts_ns` de trades e livro e' epoch puro. Converter
    `ts` de volta dava 3 HORAS de diferenca e o join nao casava NENHUMA
    linha -- o funil dizia '0 com dado' sem erro nenhum."""
    from profittape.research.regime_rlp_book import _balde_das_barras

    passo = 15 * 10**9
    barras = pd.DataFrame({
        "ts_ini_ns": [_BASE, _BASE + passo],
        # `ts` DE PROPOSITO com 3h a mais, como o replay produz
        "ts": pd.to_datetime([(_BASE // 10**9) - 3 * 3600,
                              (_BASE // 10**9) + 15 - 3 * 3600], unit="s")})
    b = _balde_das_barras(barras)
    assert list(b) == [_BASE, _BASE + passo], (
        "o balde tem que sair de ts_ini_ns (epoch puro), nao de ts (com fuso)")


def test_barras_sem_ts_ini_ns_falham_alto() -> None:
    """Melhor falhar do que adivinhar o relogio: adivinhar errado produz
    '0 eventos' silencioso, que parece resultado."""
    from profittape.research.regime_rlp_book import _balde_das_barras

    with pytest.raises(KeyError, match="ts_ini_ns"):
        _balde_das_barras(pd.DataFrame({"ts": [1, 2]}))


def test_alinhamento_usa_ts_ini_ns_e_NAO_o_ts_com_fuso() -> None:
    """Bug real (2026-09-23): `ts` das barras tem o offset de fuso (-3h)
    somado; `ts_ns` dos trades e do livro e' epoch puro. Converter `ts`
    de volta dava 3 HORAS de diferenca e o join nao casava NENHUMA
    linha -- o funil dizia "0 com dado" sem erro nenhum."""
    barras, trades, tiny = _cenario()
    c = combinado(barras, trades, tiny)
    # 19 de 20: o primeiro balde do cenario tem volume zero e o RLP fica
    # indefinido (correto). O que este teste protege e' que NAO seja 0 --
    # zero era o sintoma do relogio divergindo.
    assert c["com_os_dois_dados"] >= c["candidatos"] - 1, (
        f"so' {c['com_os_dois_dados']} de {c['candidatos']} casaram -- "
        "o relogio voltou a divergir (ts com fuso x ts_ns epoch puro)")
    assert c["com_os_dois_dados"] > 0


def test_barras_SEM_ts_ini_ns_falham_alto() -> None:
    """Sem o campo de epoch puro nao da' para alinhar com seguranca --
    melhor falhar que casar errado em silencio."""
    barras, trades, tiny = _cenario()
    with pytest.raises(KeyError, match="ts_ini_ns"):
        combinado(barras.drop(columns=["ts_ini_ns"]), trades, tiny)


def test_aceita_o_SCHEMA_REAL_do_tiny_book() -> None:
    """Erro real (2026-09-23): o codigo pedia `ts_ns` ao parquet, mas
    TINY_BOOK_SCHEMA so' grava `ts_recv_ns`. Sao RELOGIOS DIFERENTES -- o
    trade traz o carimbo da B3, o livro o instante em que NOS recebemos.
    O comando quebrou com ArrowInvalid na maquina do operador porque os
    testes usavam um fixture inventado em vez do schema do projeto."""
    from profittape.domain.schema import TINY_BOOK_SCHEMA

    nomes = [f.name for f in TINY_BOOK_SCHEMA]
    assert "ts_recv_ns" in nomes and "ts_ns" not in nomes, (
        "se o schema do tiny_book mudar, este teste falha junto -- e' o "
        "ponto: o fixture tem que seguir o schema, nao a memoria")

    tb = pd.DataFrame({
        "ts_recv_ns": [_BASE, _BASE + 10**9],      # o nome REAL, sem ts_ns
        "symbol": "WINFUT", "exchange": "F",
        "side": [0, 1], "price": [100.0, 101.0], "quantidade": [80, 20]})
    L = topo_do_livro_por_barra(tb)
    assert float(L["desequilibrio"][0]) == pytest.approx(0.60)
