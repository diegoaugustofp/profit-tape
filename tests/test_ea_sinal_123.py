"""ea/sinal_123.py -- o 123 ao vivo (passo 3 do F5). Uma formula, dois lados."""

from __future__ import annotations

import numpy as np
import pandas as pd

from profittape.ea.semente import IndicadorMME
from profittape.ea.sinal import BarraFechada
from profittape.ea.sinal_123 import SinalPreco123
from profittape.research import eas_preco as ep

NS = 1_000_000_000
P15 = 900 * NS


def _barra(ts_open: int, o: float, h: float, lo: float, c: float, parcial: bool = False,
           vc: int = 0, vv: int = 0) -> BarraFechada:
    return BarraFechada(bar_id=ts_open // P15, ts_open_ns=ts_open, ts_close_ns=ts_open + P15,
                        open=o, high=h, low=lo, close=c, vol_agr=vc + vv, agf={},
                        vol_agr_compra=vc, vol_agr_venda=vv, n_trades=vc + vv, parcial=parcial)


def _dia_utc(dia: str) -> int:
    return int(pd.Timestamp(f"{dia} 12:00:00", tz="UTC").value)      # 09:00 BRT


def _barras_aleatorias(dias: list[str], seed: int) -> list[BarraFechada]:
    rng = np.random.default_rng(seed)
    out = []
    p = 140000.0
    for d in dias:
        t0 = _dia_utc(d)
        for i in range(38):                                             # 09:00 .. 18:15
            o = p
            h = o + float(rng.integers(0, 60)) * 5
            lo = o - float(rng.integers(0, 60)) * 5
            c = float(rng.uniform(lo, h) // 5 * 5)
            out.append(_barra(t0 + i * P15, o, h, lo, c, vc=int(rng.integers(1, 50)),
                              vv=int(rng.integers(1, 50))))
            p = c
    return out


def test_equivalencia_com_marcar_123_do_research() -> None:
    """O EA (avaliar_123 barra a barra + MME propria) tem que ARMAR os mesmos
    candidatos, com os mesmos niveis, que marcar_123 marca nos 10 anos --
    fora o gatilho, que ao vivo e' a corretora."""
    barras = _barras_aleatorias(["2026-09-08", "2026-09-09", "2026-09-10"], seed=5)
    # research: frame continuo com mme80 calculada como o Profit (ewm no close)
    df = pd.DataFrame([{"dia": pd.Timestamp(b.ts_open_ns, unit="ns", tz="UTC")
                         .tz_convert("America/Sao_Paulo").date(),
                        "hhmm": (lambda t: t.hour * 100 + t.minute)(
                            pd.Timestamp(b.ts_open_ns, unit="ns", tz="UTC")
                            .tz_convert("America/Sao_Paulo")),
                        "current_bar": i + 1, "bloco": 1,
                        "open": b.open, "high": b.high, "low": b.low, "close": b.close}
                       for i, b in enumerate(barras)])
    semente = 140000.0
    df["mme80_ntsl"] = df["close"].ewm(span=80, adjust=False).mean()
    # ewm semeia no 1o close; o EA semeia em `semente` -> use a mesma semente:
    alpha = 2 / 81
    v, col = semente, []
    for c in df["close"]:
        v = alpha * c + (1 - alpha) * v
        col.append(v)
    df["mme80_ntsl"] = col
    x = ep.marcar_123(df)
    armados_research = x[(x["padrao_compra"] & x["regime_compra"] & x["janela"]
                          & (x["D_compra"] >= ep.P123_D_MINIMO))
                         | (x["padrao_venda"] & x["regime_venda"] & x["janela"]
                            & (x["D_venda"] >= ep.P123_D_MINIMO))]

    ea = SinalPreco123(IndicadorMME(80, semente))
    armados_ea = []
    for b in barras:
        c = ea.barra_fechada(b)
        if c is not None:
            armados_ea.append(c)

    assert len(armados_ea) == len(armados_research) > 0
    for c, (_, r) in zip(armados_ea, armados_research.iterrows(), strict=True):
        assert c.hhmm_sinal == int(r["hhmm"])
        lado = "compra" if r["padrao_compra"] and r["regime_compra"] else "venda"
        assert c.lado == lado
        entrada = r["high"] + 5 if lado == "compra" else r["low"] - 5
        assert c.entrada == entrada and c.D_pts == r[f"D_{lado}"]
        assert abs(c.mme80 - r["mme80_ntsl"]) < 1e-6


def test_dia_incompleto_nao_arma_mas_atualiza_mme() -> None:
    t0 = _dia_utc("2026-09-11")
    ea = SinalPreco123(IndicadorMME(80, 140000.0))
    # primeira barra do dia e' a 09:45 (record ligado tarde) -> dia incompleto
    seq = [_barra(t0 + 3 * P15, 140000.0, 140100.0, 139900.0, 140050.0, parcial=True)]
    for i in range(4, 12):
        seq.append(_barra(t0 + i * P15, 140000.0, 140200.0, 139800.0, 140100.0))
    # monta um 123 valido no meio (lo1 menor que vizinhas)
    seq[6] = _barra(t0 + 6 * P15, 140000.0, 140100.0, 139700.0, 140050.0)
    for b in seq:
        assert ea.barra_fechada(b) is None
    assert not ea.dia_completo and ea.mme.n == len(seq)      # a MME viu todas


def test_parcial_reinicia_a_janela_e_alimenta_a_mme() -> None:
    t0 = _dia_utc("2026-09-11")
    ea = SinalPreco123(IndicadorMME(80, 139000.0))          # close acima -> regime compra
    b0 = _barra(t0, 140000.0, 140100.0, 139900.0, 140050.0)                 # 09:00 completa
    b1 = _barra(t0 + P15, 140050.0, 140100.0, 139800.0, 140000.0, parcial=True)  # 09:15 parcial
    b2 = _barra(t0 + 2 * P15, 140000.0, 140100.0, 139900.0, 140050.0)
    b3 = _barra(t0 + 3 * P15, 140050.0, 140120.0, 139950.0, 140100.0)       # 09:45
    assert ea.barra_fechada(b0) is None
    assert ea.barra_fechada(b1) is None
    assert ea.barra_fechada(b2) is None
    # b1 (parcial) seria o "t-1" mais baixo de um 123 fechado em b2/b3; a
    # janela recomecou em b2, entao NAO arma em b3
    assert ea.barra_fechada(b3) is None
    assert ea.mme.n == 4 and ea.dia_completo


def test_candidato_tem_niveis_validade_e_fluxo() -> None:
    t0 = _dia_utc("2026-09-11")
    ea = SinalPreco123(IndicadorMME(80, 139000.0))
    ea.barra_fechada(_barra(t0, 140000.0, 140100.0, 139900.0, 140050.0))            # 09:00
    ea.barra_fechada(_barra(t0 + P15, 140050.0, 140080.0, 139800.0, 140000.0))      # 09:15 (menor)
    c = ea.barra_fechada(_barra(t0 + 2 * P15, 140000.0, 140050.0, 139900.0, 140020.0,
                                vc=30, vv=10))                                       # 09:30 = t
    assert c is not None and c.lado == "compra" and c.hhmm_sinal == 930
    assert c.entrada == 140055.0 and c.stop == 139795.0 and c.D_pts == 260.0
    assert c.alvo == 140315.0
    assert c.valido_ate_ns == t0 + 4 * P15          # fim da barra 09:45 (t+1)
    assert (c.vol_agr_compra_t, c.vol_agr_venda_t, c.n_trades_t) == (30, 10, 40)
    assert ea.candidatos_armados == 1
