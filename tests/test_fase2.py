"""fase2-preparar -- numeros conferidos no papel."""

from __future__ import annotations

import logging
import pickle

import numpy as np
import pandas as pd
import pytest
import structlog

from profittape.research.fase2 import (
    Alvo,
    escolher_k,
    eventos_nao_sobrepostos,
    preparar_fase2,
    rotular_por_dia,
    triagem_redundancia,
)
from profittape.research.simulador import preparar

_NS = 10**9
_T0 = int(pd.Timestamp("2026-09-01 12:00:00", tz="UTC").timestamp()) * _NS


@pytest.fixture(autouse=True)
def _silencia() -> None:
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.ERROR))


def _barras(close: np.ndarray, dia_offset: int = 0, bar0: int = 0) -> pd.DataFrame:
    n = len(close)
    base = _T0 + dia_offset * 86400 * _NS
    return pd.DataFrame({
        "bar_id": range(bar0, bar0 + n),
        "ts_open": [base + i * 60 * _NS for i in range(n)],
        "ts_close": [base + i * 60 * _NS + 59 * _NS for i in range(n)],
        "open": close, "high": close + 5, "low": close - 5, "close": close,
    })


def _zigzag(n: int = 60) -> np.ndarray:
    c = np.empty(n)
    c[0] = 100000.0
    for i in range(1, n):
        c[i] = c[i - 1] + (10 if i % 2 else -10)
    return c


def test_label_por_dia_janela_e_barreira_a_mao() -> None:
    """closes alternando +-10: sigma ~1e-4 -> barreira k=1 ~10 pts; high/low
    +-5 cruzam a barreira na barra seguinte: label = sinal do proximo passo.
    Validas so' com sigma aquecido (>=26) e i+h <= n-1 (<=56)."""
    r = rotular_por_dia(preparar(_barras(_zigzag())), Alvo(h=3, k=1.0, custo_pontos=11))
    v = r[r["label_valida"]]
    assert v.index.min() == 26 and v.index.max() == 56
    assert 9.5 < v["barreira_pts"].median() < 10.5
    assert r.loc[49, "label"] == -1 and r.loc[49, "t_evento"] == 50   # 100010 -> 100000
    assert r.loc[50, "label"] == 1 and r.loc[50, "t_evento"] == 51    # 100000 -> 100010
    assert r.loc[57, "label_valida"] == np.False_                     # h nao cabe


def test_label_nao_atravessa_o_dia() -> None:
    d1 = _barras(_zigzag(40))
    d2 = _barras(_zigzag(40) + 500, dia_offset=1, bar0=40)
    r = rotular_por_dia(preparar(pd.concat([d1, d2], ignore_index=True)),
                        Alvo(3, 1.0, 11))
    # ultimas 3 barras do dia 1 invalidas; dia 2 aquece de novo
    assert not r.loc[37:39, "label_valida"].any()
    assert not r.loc[40:65, "label_valida"].any()
    assert r.loc[66, "label_valida"]


def test_empate_resolvido_pelo_tape() -> None:
    b = preparar(_barras(_zigzag()))
    b.loc[30, "high"] = b.loc[29, "close"] + 500
    b.loc[30, "low"] = b.loc[29, "close"] - 500
    sem = rotular_por_dia(b, Alvo(3, 1.0, 11))
    assert sem.loc[29, "label"] == 0 and sem.loc[29, "label_ambigua"]
    t0 = int(b.loc[30, "ts_open"])
    tape = pd.DataFrame({"ts_ns": [t0 + 1, t0 + 2],
                         "price": [b.loc[29, "close"] - 400, b.loc[29, "close"] + 400],
                         "trade_type": [3, 2]})
    com = rotular_por_dia(b, Alvo(3, 1.0, 11), trades_por_dia={"2026-09-01": tape})
    assert com.loc[29, "label"] == -1 and com.loc[29, "label_desempatada_tape"]
    assert not com.loc[29, "label_ambigua"]
    # RLP (13) nao decide: se o unico negocio que cruza for RLP, continua ambiguo
    tape_rlp = tape.assign(trade_type=[13, 13])
    r = rotular_por_dia(b, Alvo(3, 1.0, 11), trades_por_dia={"2026-09-01": tape_rlp})
    assert r.loc[29, "label"] == 0 and r.loc[29, "label_ambigua"]


def test_triagem_remove_a_segunda_do_par() -> None:
    rng = np.random.default_rng(0)
    a = rng.normal(size=500)
    df = pd.DataFrame({"z_a": a, "z_b": a * 0.99 + rng.normal(size=500) * 0.01,
                       "z_c": rng.normal(size=500)})
    t = triagem_redundancia(df, ["z_a", "z_b", "z_c"])
    assert t["mantidas"] == ["z_a", "z_c"]
    assert t["removidas"][0][:2] == ("z_b", "z_a")


def test_escolher_k_regra_fixa() -> None:
    """zigzag +-10: barreira k pts ~ 10,1k. custo 2 -> 2x custo = 4 pts.
    k=0.25 (2,5 pts) falha na barreira; k=0.5 e 1.0 resolvem 100%; k=1.5 da'
    15,15 pts e o high (close+5, i.e. +15 do close anterior) NAO alcanca ->
    resolucao 0 -> escolhe 1.0. (Primeira versao deste teste esperava 1.5:
    conta de papel errada por 0,15 pt na borda -- o codigo estava certo.)"""
    b = preparar(_barras(_zigzag(120)))
    e = escolher_k(b, h=3, custo=2.0, grade=(0.25, 0.5, 1.0, 1.5, 3.0))
    tab = e["tabela"].set_index("k")
    assert tab.loc[0.25, "barreira_pts_mediana"] < 4.0
    assert tab.loc[1.5, "frac_resolvidas"] < 0.6
    assert e["k"] == 1.0 and e["motivo"].startswith("maior k")
    # nenhum passa -> menor da grade, registrado
    e2 = escolher_k(b, h=3, custo=50.0, grade=(0.25, 0.5))
    assert e2["k"] == 0.25 and "NENHUM" in e2["motivo"]


def test_eventos_nao_sobrepostos_a_mao() -> None:
    d = pd.DataFrame({"dia": ["d"] * 6, "bar_id": [0, 1, 2, 3, 4, 5],
                      "label": [1, 1, -1, 0, 1, 1], "barreira_pts": [20.0] * 6,
                      "ret_h_pts": [5.0, 5.0, 5.0, -8.0, 5.0, 5.0]})
    conf = np.array([0.9, 0.9, 0.9, 0.9, 0.5, 0.9])
    lado = np.array([1, 1, 1, 1, 1, -1])
    ev = eventos_nao_sobrepostos(d, conf, lado, p_star=0.8, h=3, custo=11.0)
    # t=0 evento (acerto, +20-11=9); bloqueia 1,2,3; t=4 conf baixa; t=5 evento
    # lado -1 com label +1 -> barreira oposta: -20-11 = -31
    assert list(ev["bar_id"]) == [0, 5]
    assert list(ev["acerto"]) == [1, 0]
    assert list(ev["pnl_liquido_proxy"]) == [9.0, -31.0]
    # vertical: label 0 -> ret_h_pts * lado - custo
    ev2 = eventos_nao_sobrepostos(d.iloc[[3]], np.array([0.9]), np.array([1]), 0.8, 3, 11.0)
    assert list(ev2["pnl_liquido_proxy"]) == [-19.0]


def _sintetico(dias: int, forca: float, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    bar = 0
    for d in range(dias):
        c = 100000.0
        for i in range(80):
            imb = rng.normal()
            rows.append({"bar_id": bar, "ts_open": _T0 + d * 86400 * _NS + i * 60 * _NS,
                         "ts_close": _T0 + d * 86400 * _NS + i * 60 * _NS + 59 * _NS,
                         "open": c, "high": c + abs(rng.normal()) * 15,
                         "low": c - abs(rng.normal()) * 15, "close": c,
                         "imbalance": imb, "tick_imbalance": rng.normal(),
                         "absorcao": rng.normal(), "rlp_frac": rng.normal(),
                         "agf_3": rng.normal()})
            bar += 1
            c += rng.normal() * 10 + forca * imb
    return pd.DataFrame(rows)


def test_preparar_ponta_a_ponta_detecta_sinal_plantado(tmp_path) -> None:  # type: ignore[no-untyped-def]
    f = tmp_path / "f.parquet"
    _sintetico(12, forca=40.0).to_parquet(f, index=False)
    r = preparar_fase2(f, tmp_path / "out", "WINFUT", h=3, custo=11.0)
    fi = r["ficha"]
    assert fi["DEPURACAO_acerto_validacao"] > fi["MEDIDO_nula"] + 0.3
    assert fi["MEDIDO_taxa_eventos_por_pregao"] > 0
    assert (tmp_path / "out" / "ficha_fase2.json").exists()
    with open(fi["modelo_arquivo"], "rb") as fh:
        m = pickle.load(fh)
    assert m["features"] == fi["features"] and m["p_star"] == fi["MEDIDO_p_star"]
    assert "label" not in fi["features"] and all(c.startswith("z_") for c in fi["features"])


def test_preparar_amostra_pequena_falha_alto(tmp_path) -> None:  # type: ignore[no-untyped-def]
    f = tmp_path / "f.parquet"
    _sintetico(3, forca=0.0).to_parquet(f, index=False)
    with pytest.raises(SystemExit, match="amostra insuficiente"):
        preparar_fase2(f, tmp_path / "out", "WINFUT")


def test_carregar_trades_usa_a_pasta_dt(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Layout hive real: curated/trade/dt=D/sym=S/part.parquet. A primeira
    versao passava dt=/sym= para _carregar_dia e quebrava em producao."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    from profittape.research.fase2 import carregar_trades_dos_dias

    pasta = tmp_path / "trade" / "dt=2026-09-01" / "sym=WINFUT"
    pasta.mkdir(parents=True)
    n = 3
    pq.write_table(pa.table({
        "ts_ns": [3, 1, 2], "symbol": ["WINFUT"] * n, "exchange": ["F"] * n,
        "trade_id": [1, 2, 3], "price": [1.0, 2.0, 3.0], "volume_financeiro": [1.0] * n,
        "quantidade": [1] * n, "agente_comprador": [3] * n, "agente_vendedor": [85] * n,
        "trade_type": [2, 3, 13], "is_edit": [False] * n,
    }), pasta / "part-0000.parquet")
    out = carregar_trades_dos_dias(tmp_path, "WINFUT", ["2026-09-01", "2026-09-02"])
    assert list(out) == ["2026-09-01"]
    assert list(out["2026-09-01"].columns) == ["ts_ns", "price", "trade_type"]
    assert list(out["2026-09-01"]["ts_ns"]) == [1, 2, 3]      # ordenado


def test_score_e_livro_forward(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """preparar em 12 dias; escorar os 2 dias seguintes (forward); re-escorar
    nao duplica; carimbo presente; dia queimado e' recusado pelo CLI (testado
    na funcao de placar/registro aqui, o CLI so' orquestra)."""
    import json

    from profittape.research.fase2 import (
        carregar_modelo,
        colunas_tier1,
        escorar,
        placar,
        politica_modelo,
        registrar_forward,
    )
    from profittape.research.simulador import preparar, verificar_lookahead

    todo = _sintetico(14, forca=40.0)
    dias = sorted(pd.to_datetime(todo["ts_open"], unit="ns", utc=True)
                  .dt.strftime("%Y-%m-%d").unique())
    f = tmp_path / "f.parquet"
    todo[todo["ts_open"] < todo["ts_open"].quantile(12 / 14)].to_parquet(f, index=False)
    preparar_fase2(f, tmp_path / "out", "WINFUT")
    with open(tmp_path / "out" / "ficha_fase2.json", encoding="utf-8") as fh:
        ficha = json.load(fh)
    m = carregar_modelo(tmp_path / "out" / "modelo_fase2.pkl")
    assert m["sha256"] == ficha["modelo_sha256"]
    assert ficha["DEPURACAO_n_eventos_treino_in_sample"] > 0

    b = preparar(todo, z_por_dia=colunas_tier1(todo), janela_z=50)
    forward = [d for d in dias if d > ficha["dias_validacao"][1]]
    assert len(forward) == 2
    ev = escorar(b, m, forward)
    assert len(ev) > 0 and set(ev["dia"]) <= set(forward)
    assert (ev["modelo_sha256"] == m["sha256"]).all() and ev["carimbo"].notna().all()
    assert ev["acerto"].mean() > ficha["MEDIDO_nula"]      # sinal plantado forte

    livro = tmp_path / "out" / "forward_eventos.csv"
    t1 = registrar_forward(ev, livro)
    t2 = registrar_forward(ev, livro)                       # de novo: nao duplica
    assert len(t1) == len(t2) == len(ev)
    p = placar(t2, ficha)
    assert p["n"] == len(ev) and p["alvo_favoravel"] == pytest.approx(ficha["MEDIDO_nula"] + 0.08)

    # coluna do modelo faltando -> falha alta
    with pytest.raises(SystemExit, match="sem colunas do modelo"):
        escorar(b.drop(columns=[m["features"][0]]), m, forward)

    # a politica do modelo e' causal (verificador da Fase 1)
    assert verificar_lookahead(b[b["dia"].isin(forward)].reset_index(drop=True),
                               politica_modelo(tmp_path / "out" / "modelo_fase2.pkl"),
                               n_cortes=4)["ok"]
