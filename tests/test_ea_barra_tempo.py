"""ea/barra_tempo.py -- barra de tempo para o EA de preco (passo 1 do F5 do 123)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from profittape.ea.barra_tempo import ConstrutorDeBarraDeTempo, TradeForaDeOrdem

NS = 1_000_000_000
# 2026-09-14 09:00:00 America/Sao_Paulo (-03:00) = 12:00:00 UTC
T0900 = int(pd.Timestamp("2026-09-14 12:00:00", tz="UTC").value)
P15 = 900 * NS


def _t(seg: float) -> int:
    return T0900 + int(seg * NS)


def test_periodo_precisa_dividir_uma_hora() -> None:
    ConstrutorDeBarraDeTempo(900)
    ConstrutorDeBarraDeTempo(300)
    with pytest.raises(ValueError, match="dividir uma hora"):
        ConstrutorDeBarraDeTempo(420)
    with pytest.raises(ValueError):
        ConstrutorDeBarraDeTempo(0)


def test_alinhamento_na_grade_da_bolsa_e_fechamento_pelo_trade() -> None:
    c = ConstrutorDeBarraDeTempo(900)
    assert c.processar_trade(_t(7), 140000.0, 1, 2) is None        # 09:00:07
    assert c.processar_trade(_t(400), 140050.0, 2, 3) is None      # 09:06:40
    assert c.processar_trade(_t(899.9), 139980.0, 1, 2) is None    # 09:14:59.9
    b = c.processar_trade(_t(900), 140010.0, 1, 2)                 # 09:15:00 -> fecha a de 09:00
    assert b is not None
    assert b.ts_open_ns == T0900 and b.ts_close_ns == T0900 + P15
    assert b.bar_id == T0900 // P15
    assert (b.open, b.high, b.low, b.close) == (140000.0, 140050.0, 139980.0, 139980.0)
    assert b.n_trades == 3
    # o trade de 09:15:00 abriu a barra seguinte
    acc = c.em_formacao
    assert acc is not None and acc.ts_open_ns == T0900 + P15 and acc.open == 140010.0
    assert c.barras_fechadas == 1


def test_volume_agredido_por_lado_e_rlp_fora() -> None:
    c = ConstrutorDeBarraDeTempo(900)
    c.processar_trade(_t(1), 140000.0, 5, 2)     # comprador agressor
    c.processar_trade(_t(2), 140000.0, 3, 3)     # vendedor agressor
    c.processar_trade(_t(3), 140000.0, 7, 13)    # RLP: nao e' agressao
    c.processar_trade(_t(4), 140000.0, 9, 32)    # desconhecido
    b = c.avancar_relogio(_t(900))
    assert b is not None
    assert b.vol_agr == 8 and b.vol_agr_compra == 5 and b.vol_agr_venda == 3
    assert b.n_trades == 4 and b.agf == {}


def test_fechamento_pelo_relogio_sem_abrir_barra_nova() -> None:
    c = ConstrutorDeBarraDeTempo(900)
    c.processar_trade(_t(10), 140000.0, 1, 2)
    assert c.avancar_relogio(_t(899)) is None            # ainda dentro da barra
    b = c.avancar_relogio(_t(900))                       # fronteira: fecha
    assert b is not None and b.close == 140000.0
    assert c.em_formacao is None
    assert c.avancar_relogio(_t(2000)) is None           # nada em formacao: nada
    # o proximo trade abre a barra da SUA fronteira, nao uma vazia no meio
    c.processar_trade(_t(2000), 140100.0, 1, 2)          # 09:33:20 -> barra 09:30
    acc = c.em_formacao
    assert acc is not None and acc.ts_open_ns == T0900 + 2 * P15


def test_buraco_nao_inventa_barra_vazia() -> None:
    c = ConstrutorDeBarraDeTempo(900)
    c.processar_trade(_t(1), 140000.0, 1, 2)             # 09:00
    b = c.processar_trade(_t(2701), 140200.0, 1, 2)      # 09:45:01 -> fecha a de 09:00
    assert b is not None and b.bar_id == T0900 // P15
    acc = c.em_formacao
    assert acc is not None and acc.ts_open_ns == T0900 + 3 * P15
    assert c.barras_fechadas == 1                        # nenhuma barra 09:15 / 09:30


def test_trade_fora_de_ordem_levanta() -> None:
    c = ConstrutorDeBarraDeTempo(900)
    c.processar_trade(_t(1000), 140000.0, 1, 2)          # barra 09:15
    with pytest.raises(TradeForaDeOrdem):
        c.processar_trade(_t(100), 140000.0, 1, 2)       # 09:01: barra anterior


def test_equivalencia_com_resample_do_pandas() -> None:
    """Recalcular e comparar MEDE: o construtor trade a trade tem que dar
    exatamente o resample('15min') do mesmo fluxo (OHLC, n, volume por lado)."""
    rng = np.random.default_rng(11)
    n = 5000
    ts = np.sort(rng.integers(T0900, T0900 + 3600 * 3 * NS, size=n))    # 3 h de trades
    ts[0] = T0900
    price = 140000.0 + np.cumsum(rng.choice([-5.0, 0.0, 5.0], size=n))
    qtd = rng.integers(1, 20, size=n)
    tipo = rng.choice([2, 3, 13], size=n, p=[0.4, 0.4, 0.2])

    c = ConstrutorDeBarraDeTempo(900)
    barras = []
    for i in range(n):
        b = c.processar_trade(int(ts[i]), float(price[i]), int(qtd[i]), int(tipo[i]))
        if b is not None:
            barras.append(b)
    ultima = c.avancar_relogio(int(ts[-1]) + P15)
    assert ultima is not None
    barras.append(ultima)

    df = pd.DataFrame({"ts": pd.to_datetime(ts, unit="ns", utc=True), "price": price,
                       "qtd": qtd, "tipo": tipo}).set_index("ts")
    ref = df["price"].resample("15min").ohlc().dropna()
    n_ref = df["price"].resample("15min").count()
    n_ref = n_ref[n_ref > 0]
    assert len(barras) == len(ref)
    for b, (t_open, row), n_esp in zip(barras, ref.iterrows(), n_ref, strict=True):
        assert b.ts_open_ns == int(t_open.value)
        assert (b.open, b.high, b.low, b.close) == (
            row["open"], row["high"], row["low"], row["close"])
        assert b.n_trades == int(n_esp)
        janela = df[(df.index >= t_open) & (df.index < t_open + pd.Timedelta(minutes=15))]
        assert b.vol_agr_compra == int(janela.loc[janela["tipo"] == 2, "qtd"].sum())
        assert b.vol_agr_venda == int(janela.loc[janela["tipo"] == 3, "qtd"].sum())


def test_conferir_tape_x_grafico_bate_e_acusa_diferenca(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """`barra-tempo-conferir`: mesmo fluxo -> dump identico -> tudo BATE;
    um high adulterado no dump -> a barra aparece como diferente."""
    from profittape.research import barra_tempo_conferir as btc
    from tests.test_eas_preco import _barra, _dump

    rng = np.random.default_rng(3)
    n = 3000
    ts = np.sort(rng.integers(T0900, T0900 + 3600 * 2 * NS, size=n))
    ts[0] = T0900
    price = 140000.0 + np.cumsum(rng.choice([-5.0, 0.0, 5.0], size=n))
    trades = pd.DataFrame({"ts_ns": ts, "price": price,
                           "quantidade": rng.integers(1, 10, size=n),
                           "trade_type": rng.choice([2, 3], size=n)})
    monkeypatch.setattr(btc, "_carregar_dia", lambda pasta, sym: trades)
    (tmp_path / "curated" / "trade" / "dt=2026-09-14" / "sym=WINFUT").mkdir(parents=True)

    # dump do "grafico" = resample do mesmo fluxo, no formato PRCBARRA
    df = pd.DataFrame({"ts": pd.to_datetime(ts, unit="ns", utc=True),
                       "price": price}).set_index("ts")
    ohlc = df["price"].resample("15min").ohlc().dropna()
    barras = []
    for i, (t_open, r) in enumerate(ohlc.iterrows()):
        local = t_open.tz_convert("America/Sao_Paulo")
        hhmm = local.hour * 100 + local.minute
        barras.append(_barra(1260914, hhmm, i + 1, r["open"], r["high"], r["low"], r["close"]))
    barras[3]["high"] += 25.0            # adultera a 4a barra (09:45)
    dump = _dump(tmp_path, barras)

    r = btc.conferir(tmp_path / "curated", dump, "WINFUT", ["2026-09-14"])
    d = r["dias"]["2026-09-14"]
    assert d["barras_grafico"] == len(ohlc) == d["barras_ea"]
    # o 1o trade esta' em 09:00:00 exato: a barra 09:00 e' completa, nao parcial
    assert d["parciais_excluidas"] == [] and d["so_no_grafico"] == []
    assert d["em_comum"] == len(ohlc) and d["identicas_ohlc"] == len(ohlc) - 1
    assert d["so_no_ea"] == []
    assert d["dif_max_por_campo"]["high"] == (25.0, 945)
    assert d["barras_diferentes"][0]["hhmm"] == 945


def test_fim_de_sessao_dobra_na_ultima_barra_como_o_grafico() -> None:
    """Medido em 28/08: o grafico nao abre barra 18:30 -- dobra os negocios
    do fechamento na 18:15, que fica com o ultimo preco como close."""
    t1815 = int(pd.Timestamp("2026-08-28 21:15:00", tz="UTC").value)   # 18:15 BRT
    c = ConstrutorDeBarraDeTempo(900)
    c.processar_trade(t1815 + 5 * NS, 177700.0, 1, 2)
    c.processar_trade(t1815 + 600 * NS, 177680.0, 1, 3)                  # 18:25
    assert c.processar_trade(t1815 + 905 * NS, 177650.0, 1, 2) is None  # 18:30:05 -> dobra
    assert c.processar_trade(t1815 + 1200 * NS, 177640.0, 1, 3) is None # 18:35
    b = c.avancar_relogio(t1815 + 2000 * NS)
    assert b is not None
    assert b.ts_open_ns == t1815 and (b.low, b.close) == (177640.0, 177640.0)
    assert b.n_trades == 4 and c.barras_fechadas == 1
    # dia seguinte: nao dobra (data local diferente)
    t0900 = int(pd.Timestamp("2026-08-31 12:00:00", tz="UTC").value)
    c.processar_trade(t0900 + NS, 178000.0, 1, 2)
    acc = c.em_formacao
    assert acc is not None and acc.ts_open_ns == t0900


def test_sem_fim_de_sessao_abre_barra_normalmente() -> None:
    t1815 = int(pd.Timestamp("2026-08-28 21:15:00", tz="UTC").value)
    c = ConstrutorDeBarraDeTempo(900, fim_sessao_hhmm=None)
    c.processar_trade(t1815 + NS, 1.0, 1, 2)
    assert c.processar_trade(t1815 + 905 * NS, 1.0, 1, 2) is not None


def test_primeira_barra_e_parcial_so_se_o_primeiro_trade_veio_tarde() -> None:
    """Medido em 11/09: record ligado as ~09:50, a 09:45 saiu com open/low
    errados. Marcada. Mas 09:00 com o 1o trade em 09:00:07 e' completa."""
    c = ConstrutorDeBarraDeTempo(900)
    c.processar_trade(_t(3000), 140000.0, 1, 2)          # 09:50 -> barra 09:45, parcial
    b1 = c.processar_trade(_t(3600), 140010.0, 1, 2)     # 10:00 fecha a 09:45
    b2 = c.processar_trade(_t(4500), 140020.0, 1, 2)     # 10:15 fecha a 10:00
    assert b1 is not None and b1.parcial and b1.ts_primeiro_ns == _t(3000)
    assert b2 is not None and not b2.parcial
    c2 = ConstrutorDeBarraDeTempo(900)
    c2.processar_trade(_t(7), 140000.0, 1, 2)            # 09:00:07
    b = c2.processar_trade(_t(900), 140000.0, 1, 2)
    assert b is not None and not b.parcial
