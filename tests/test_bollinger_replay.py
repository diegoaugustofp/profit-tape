"""Replay do scalp de Bollinger pelo tape -- casos conferidos no papel."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from profittape.research import bollinger_replay as br

NS = 10**9
_BASE = int(pd.Timestamp("2026-09-01 12:00:00", tz="UTC").timestamp())  # 09:00 local


def _t(seg: int) -> int:
    return (_BASE + seg) * NS


def _tape(seq: list[tuple[int, float]], tipo: int = 2) -> pd.DataFrame:
    return pd.DataFrame(
        [dict(ts_ns=_t(s), price=float(p), quantidade=1, trade_type=tipo) for s, p in seq]
    )


def _sinal(seg: int, lado: int, limite: float, hora: int = 910) -> dict:  # type: ignore[type-arg]
    return dict(
        ts_ini_ns=_t(seg),
        hora_int=hora,
        sinal_compra=(lado == 1),
        sinal_venda=(lado == -1),
        preco_limite=limite,
        stop_pts=60.0,
        alvo1_pts=60.0,
        alvo2_pts=100.0,
        alvo3_pts=150.0,
        trailing_ativa_pts=40.0,
        trailing_puxa_pts=15.0,
        trailing_passo_pts=10.0,
    )


def test_compra_recuo_alvo1_e_trailing_a_mao() -> None:
    """Limite 1000. Barra t abre 1010, toca 1000 (nao executa), 995
    atravessa -> entra a 1000. 1045: fav 45 >= 40 -> stop das pernas 2/3
    = 1030. 1060: perna 1 alvo (+60); fav 60 (+15 >= passo 10) -> stop
    1045. 1035 <= 1045 -> pernas 2/3 stop a +45. Bruto 150, custo 33."""
    seq = [
        (600, 1010),
        (603, 1000),
        (605, 995),
        (620, 1030),
        (625, 1045),
        (630, 1060),
        (640, 1035),
        (650, 1050),
    ]
    o = br.replay_pregao(pd.DataFrame([_sinal(600, 1, 1000.0)]), _tape(seq), "2026-09-01")[0]
    assert o["tipo_execucao"] == "recuo" and o["preco_entrada"] == 1000.0
    assert (o["p1_pts"], o["p1_motivo"]) == (60.0, "alvo")
    assert (o["p2_pts"], o["p2_motivo"]) == (45.0, "stop")
    assert (o["p3_pts"], o["p3_motivo"]) == (45.0, "stop")
    assert o["pnl_liquido_pts"] == 117.0 and o["p1_alvo"] is True
    assert o["max_fav_pts"] == 60.0


def test_venda_e_o_espelho_exato() -> None:
    seq = [
        (600, 990),
        (603, 1000),
        (605, 1005),
        (620, 970),
        (625, 955),
        (630, 940),
        (640, 965),
        (650, 950),
    ]
    o = br.replay_pregao(pd.DataFrame([_sinal(600, -1, 1000.0)]), _tape(seq), "2026-09-01")[0]
    assert o["tipo_execucao"] == "recuo" and o["preco_entrada"] == 1000.0
    assert (o["p1_pts"], o["p2_pts"], o["p3_pts"]) == (60.0, 45.0, 45.0)
    assert o["pnl_liquido_pts"] == 117.0


def test_abertura_a_favor_executa_no_primeiro_negocio_e_stop_cheio() -> None:
    seq = [(600, 990), (605, 960), (610, 930), (620, 1100)]
    o = br.replay_pregao(pd.DataFrame([_sinal(600, 1, 1000.0)]), _tape(seq), "2026-09-01")[0]
    assert o["tipo_execucao"] == "abertura" and o["preco_entrada"] == 990.0
    assert (o["p1_pts"], o["p2_pts"], o["p3_pts"]) == (-60.0, -60.0, -60.0)
    assert o["pnl_liquido_pts"] == -213.0 and o["p1_alvo"] is False


def test_toque_sem_atravessar_nao_executa_e_cancela_no_fim_da_barra() -> None:
    seq = [(600, 1010), (605, 1000), (614, 1000), (620, 900)]  # 900 ja' e' a barra seguinte
    o = br.replay_pregao(pd.DataFrame([_sinal(600, 1, 1000.0)]), _tape(seq), "2026-09-01")[0]
    assert o["executou"] is False and o["motivo_nao_exec"] == "nao_atravessou"


def test_sinal_com_posicao_aberta_e_ignorado() -> None:
    """Primeira operacao vive de 09:10 ate' o stop as 09:20:10. O sinal
    de 09:15 cai dentro dela -> ignorado. O de 09:25 entra."""
    seq = [(600, 990), (700, 1000), (900, 1000), (1210, 930), (1500, 990), (1600, 1200)]
    sinais = pd.DataFrame(
        [_sinal(600, 1, 1000.0), _sinal(900, 1, 1000.0, 915), _sinal(1500, 1, 1000.0, 925)]
    )
    ops = br.replay_pregao(sinais, _tape(seq), "2026-09-01")
    assert [o["hora_sinal"] for o in ops] == [910, 925]
    assert ops[1]["executou"] and ops[1]["pnl_bruto_pts"] == 310.0  # 60 + 100 + 150


def test_circuit_breaker_tres_perdas_liquidas_seguidas() -> None:
    seq = []
    sinais = []
    for k in range(4):
        b = 600 + 300 * k
        seq += [(b, 990.0), (b + 10, 930.0)]  # entra 990, stop cheio
        sinais.append(_sinal(b, 1, 1000.0, 910 + 5 * k))
    seq.append((3000, 990.0))
    ops = br.replay_pregao(pd.DataFrame(sinais), _tape(seq), "2026-09-01")
    assert len(ops) == 3  # o 4o sinal nem aparece


def test_zeragem_as_17h30_fecha_as_pernas_abertas() -> None:
    ini = 8 * 3600 + 25 * 60  # 17:25 local
    seq = [(ini, 990.0), (ini + 60, 1000.0), (ini + 6 * 60, 1010.0), (ini + 7 * 60, 1200.0)]
    o = br.replay_pregao(pd.DataFrame([_sinal(ini, 1, 1000.0, 1725)]), _tape(seq), "2026-09-01")[0]
    assert o["p1_motivo"] == "zeragem" and o["p1_pts"] == 20.0  # 1010 - 990
    assert o["p3_motivo"] == "zeragem"


def test_barras_15s_do_tape_alinham_no_relogio_e_ignoram_rlp() -> None:
    seq = [(0, 100.0), (7, 103.0), (14, 99.0), (15, 101.0), (29, 104.0)]
    tape = _tape(seq)
    tape = pd.concat([tape, _tape([(3, 500.0)], tipo=13)], ignore_index=True)  # RLP fora
    b = br.barras_15s_do_tape(tape, "2026-09-01")
    assert list(b["hora_int"]) == [900, 900]
    assert list(b["ts"].dt.second) == [0, 15]
    assert (b.loc[0, "open"], b.loc[0, "high"], b.loc[0, "low"], b.loc[0, "close"]) == (
        100,
        103,
        99,
        99,
    )
    assert (b.loc[1, "open"], b.loc[1, "close"]) == (101, 104)
    assert b["dia"].iloc[0] == dt.date(2026, 9, 1)


def test_comparar_com_dump_conta_divergencias() -> None:
    tape = br.barras_15s_do_tape(
        _tape([(0, 100.0), (14, 99.0), (15, 101.0), (29, 104.0)]), "2026-09-01"
    )
    tape["sinal_compra"] = [False, True]
    tape["sinal_venda"] = False
    dump = tape.copy()
    dump.loc[1, "close"] = 200.0
    dump["sinal_compra"] = [True, True]
    c = br.comparar_com_dump(tape, dump)
    assert c["comuns"] == 2 and c["close_divergentes"] == 1 and c["open_divergentes"] == 0
    assert c["sinal_compra_so_dump"] == 1 and c["sinal_compra_so_tape"] == 0


def test_resumo_p1_e_intervalo() -> None:
    ops = pd.DataFrame(
        [
            dict(
                executou=True,
                p1_alvo=True,
                stop_pts=60.0,
                tipo_execucao="abertura",
                pnl_liquido_pts=117.0,
                duracao_s=50.0,
                lado=1,
                p1_motivo="alvo",
                p2_motivo="stop",
                p3_motivo="stop",
            ),
            dict(
                executou=True,
                p1_alvo=False,
                stop_pts=60.0,
                tipo_execucao="recuo",
                pnl_liquido_pts=-213.0,
                duracao_s=10.0,
                lado=-1,
                p1_motivo="stop",
                p2_motivo="stop",
                p3_motivo="stop",
            ),
            dict(executou=False),
        ]
    )
    r = br.resumo(ops, pregoes=1)
    assert r["operacoes"] == 2 and r["sinais_sem_execucao"] == 1
    assert r["p1"] == 0.5 and r["p1_nula_lucro"] == pytest.approx((60 + 11) / 120, abs=1e-3)
    assert r["p1_ic95"][0] < 0.5 < r["p1_ic95"][1]
    assert np.isfinite(r["pnl_liquido_medio_pts"])
