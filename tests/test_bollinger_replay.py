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
    assert [o["hora_sinal"] for o in ops] == [910, 915, 925]
    assert ops[1]["motivo_nao_exec"] == "posicao_aberta" and not ops[1]["executou"]
    assert ops[2]["executou"] and ops[2]["pnl_bruto_pts"] == 310.0  # 60 + 100 + 150


def test_circuit_breaker_tres_perdas_liquidas_seguidas() -> None:
    seq = []
    sinais = []
    for k in range(4):
        b = 600 + 300 * k
        seq += [(b, 990.0), (b + 10, 930.0)]  # entra 990, stop cheio
        sinais.append(_sinal(b, 1, 1000.0, 910 + 5 * k))
    seq.append((3000, 990.0))
    ops = br.replay_pregao(pd.DataFrame(sinais), _tape(seq), "2026-09-01")
    assert [o["executou"] for o in ops] == [True, True, True, False]
    assert ops[3]["motivo_nao_exec"] == "circuit_breaker"
    ops = br.replay_pregao(
        pd.DataFrame(sinais), _tape(seq), "2026-09-01", ignorar_circuit_breaker=True
    )
    assert [o["executou"] for o in ops] == [True, True, True, True]


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
                pnl_bruto_pts=150.0,
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
                pnl_bruto_pts=-180.0,
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


def test_comparacao_com_rlp_muda_open_close_mas_nao_high_low() -> None:
    """RLP no meio do spread: primeiro/ultimo negocio mudam, extremos nao."""
    agr = _tape([(1, 100.0), (7, 103.0), (14, 99.0)])
    rlp = _tape([(0, 101.0), (14, 100.0)], tipo=13)  # abre e fecha a barra
    tape = pd.concat([agr, rlp], ignore_index=True)
    so_agr = br.barras_15s_do_tape(tape, "2026-09-01", (2, 3))
    com_rlp = br.barras_15s_do_tape(tape, "2026-09-01", (2, 3, 13))
    assert (so_agr.loc[0, "open"], so_agr.loc[0, "close"]) == (100.0, 99.0)
    assert (com_rlp.loc[0, "open"], com_rlp.loc[0, "close"]) == (101.0, 100.0)
    assert (so_agr.loc[0, "high"], so_agr.loc[0, "low"]) == (
        com_rlp.loc[0, "high"],
        com_rlp.loc[0, "low"],
    )
    c = br.comparar_com_dump(so_agr, com_rlp)
    assert c["open_divergentes"] == 1 and c["close_divergentes"] == 1
    assert c["high_divergentes"] == 0 and c["low_divergentes"] == 0


def test_comparacao_reporta_faixa_do_buraco_do_tape() -> None:
    dump = br.barras_15s_do_tape(
        _tape([(0, 100.0), (15, 101.0), (30, 102.0), (45, 103.0)]), "2026-09-01"
    )
    tape = dump.iloc[[0, 3]].copy()
    c = br.comparar_com_dump(tape, dump)
    assert c["so_dump"] == 2 and c["so_dump_de"] == 900 and c["so_dump_ate"] == 900


def test_resumo_traz_cortes_pre_declarados_e_pernas() -> None:
    ops = pd.DataFrame(
        [
            dict(
                executou=True,
                p1_alvo=True,
                stop_pts=60.0,
                tipo_execucao="abertura",
                pnl_liquido_pts=117.0,
                pnl_bruto_pts=150.0,
                duracao_s=50.0,
                lado=1,
                p1_motivo="alvo",
                p2_motivo="stop",
                p3_motivo="stop",
                p1_pts=60.0,
                p2_pts=45.0,
                p3_pts=45.0,
            ),
            dict(
                executou=True,
                p1_alvo=False,
                stop_pts=60.0,
                tipo_execucao="recuo",
                pnl_liquido_pts=-213.0,
                pnl_bruto_pts=-180.0,
                lado=-1,
                p1_motivo="stop",
                p2_motivo="stop",
                p3_motivo="stop",
                p1_pts=-60.0,
                p2_pts=-60.0,
                p3_pts=-60.0,
            ),
        ]
    )
    r = br.resumo(ops, pregoes=1)
    assert r["p2_pts_medio"] == -7.5 and r["p3_pct_positiva"] == 50.0
    assert r["cortes_pre_declarados"]["abertura"]["p1"] == 1.0
    assert r["cortes_pre_declarados"]["venda"]["n"] == 1


def test_cli_bollinger_replay_aceita_ignorar_circuit_breaker(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A flag existe, chega em rodar() e a saida diz que o CB foi ignorado.
    Na v2.25 a opcao ficou fora do binario porque a edicao da CLI nao
    aconteceu e nenhum teste passava pela CLI."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    from typer.testing import CliRunner

    from profittape.cli import app

    rng = np.random.default_rng(0)
    n = 4000
    ts = (_BASE + np.sort(rng.uniform(0, 3600, n))).astype(np.int64) * NS
    px = 140000 + 5 * np.cumsum(rng.integers(-2, 3, n))
    df = pd.DataFrame(
        {
            "ts_ns": ts,
            "symbol": "WINFUT",
            "exchange": "F",
            "trade_id": np.arange(n),
            "price": px.astype(float),
            "volume_financeiro": 1.0,
            "quantidade": rng.integers(1, 10, n),
            "agente_comprador": 3,
            "agente_vendedor": 85,
            "trade_type": rng.choice([2, 3, 13], n, p=[0.45, 0.45, 0.1]),
            "is_edit": False,
        }
    )
    pasta = tmp_path / "curated" / "trade" / "dt=2026-09-01" / "sym=WINFUT"
    pasta.mkdir(parents=True)
    pq.write_table(pa.table(df), pasta / "part-0000.parquet")
    r = CliRunner().invoke(
        app,
        [
            "bollinger-replay",
            "WINFUT",
            "--curated",
            str(tmp_path / "curated"),
            "--saida",
            str(tmp_path / "s"),
            "--ignorar-circuit-breaker",
            "--log-level",
            "WARNING",
        ],
    )
    assert r.exit_code == 0, r.output
    assert "circuit breaker IGNORADO" in r.output
    assert "circuit_breaker" not in r.output.split("sem execucao")[1].split("\n")[0]


def test_resumo_separa_borda_bruta_de_custo() -> None:
    """Custo e' condicao comercial: a borda bruta e o custo maximo que ela
    suporta saem separados, com IC. Duas operacoes com bruto +150 e -180:
    media -15 por 3 contratos = -5 por contrato."""
    base = dict(
        executou=True,
        stop_pts=60.0,
        tipo_execucao="abertura",
        duracao_s=10.0,
        lado=1,
        p1_motivo="alvo",
        p2_motivo="stop",
        p3_motivo="stop",
        p1_pts=0.0,
        p2_pts=0.0,
        p3_pts=0.0,
    )
    ops = pd.DataFrame(
        [
            dict(base, p1_alvo=True, pnl_bruto_pts=150.0, pnl_liquido_pts=117.0),
            dict(base, p1_alvo=False, pnl_bruto_pts=-180.0, pnl_liquido_pts=-213.0),
        ]
    )
    r = br.resumo(ops, pregoes=1)
    assert r["pnl_bruto_medio_pts"] == -15.0
    assert r["custo_maximo_suportado_pts_por_contrato"] == -5.0
    lo, hi = r["pnl_bruto_ic95"]
    assert lo < -15.0 < hi
