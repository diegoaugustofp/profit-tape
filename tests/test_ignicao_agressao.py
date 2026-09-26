"""Concentracao da agressao nas ignicoes (research/ignicao_agressao.py)."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd

from profittape.research.ignicao_agressao import (
    EventoAg,
    Features,
    calcular,
    etapa_cega,
    features_janela,
    ler_eventos,
    medir,
)

C, V, RLP = 2, 3, 13


def test_conta_a_mao_alta() -> None:
    """O exemplo conferido a mao antes do teste (skill disciplina, regra 4).
    V = 10+20+30+40 = 100; top-5 = tudo -> C1 = 1,0.
    saldos: ag7 +30; ag9 -10+5-30 = -35; ag8 -20-5+30+40 = +45 -> C2 = 0,45.
    RLP fica fora; anon = 40 / 105."""
    q = np.array([10, 20, 5, 30, 3, 40])
    tp = np.array([C, C, V, C, RLP, C])
    comp = np.array([7, 7, 9, 8, 7, 8])
    vend = np.array([9, 8, 8, 9, 8, 0])
    f = features_janela(q, tp, comp, vend, +1)
    assert f.v_dir == 100 and f.c1 == 1.0
    assert f.c2 == 0.45 and f.agente_top == 8
    assert abs(f.anon - 40 / 105) < 1e-12
    assert f.n_negocios == 5


def test_queda_e_top5_de_muitos_negocios() -> None:
    """Queda: V = venda agressora. 10 negocios de 1..10 -> top-5 = 40/55."""
    q = np.arange(1, 11)
    tp = np.full(10, V)
    comp = np.full(10, 1)          # ag1 compra passivo tudo
    vend = np.full(10, 2)          # ag2 vende agredindo tudo
    f = features_janela(q, tp, comp, vend, -1)
    assert f.v_dir == 55
    assert abs(f.c1 - 40 / 55) < 1e-12
    assert f.agente_top == 2 and f.c2 == 1.0     # vendeu 55 na direcao da queda


def test_market_maker_que_devolve_nao_conta() -> None:
    """Salto de alta. ag5 AGRIDE comprando 50 (de ag6) e depois VENDE 50
    passivo (para ag4, que agride). ag5 foi o maior agressor, mas saldo 0.
    ag4 +50, ag3 +30, ag6 -80  ->  top = ag4, C2 = 50/130."""
    q = np.array([50, 50, 30])
    tp = np.array([C, C, C])
    comp = np.array([5, 4, 3])
    vend = np.array([6, 5, 6])
    f = features_janela(q, tp, comp, vend, +1)
    assert f.agente_top == 4
    assert abs(f.c2 - 50 / 130) < 1e-12


def test_sem_agressao_na_direcao() -> None:
    f = features_janela(np.array([5]), np.array([V]), np.array([1]), np.array([2]), +1)
    assert f.v_dir == 0 and f.c1 is None and f.c2 is None


def _escrever_dia(raiz: Path, dia: str,
                  linhas: list[tuple[int, float, int, int, int, int]]) -> None:
    pasta = raiz / "trade" / f"dt={dia}" / "sym=WINFUT"
    pasta.mkdir(parents=True)
    df = pd.DataFrame(linhas, columns=["ts_ns", "price", "quantidade", "trade_type",
                                       "agente_comprador", "agente_vendedor"])
    df["trade_id"] = np.arange(len(df))
    df.to_parquet(pasta / "part-0.parquet", index=False)


def test_ponta_a_ponta_recorte_da_janela_e_backup(tmp_path: Path) -> None:
    """Janela = (t-60 s, t]. O negocio de 61 s antes e o posterior ficam fora.
    O dia so' existe na 2a raiz (backup)."""
    s = 1_000_000_000
    t = 1_000 * s
    _escrever_dia(tmp_path / "bk", "2026-08-03", [
        (t - 61 * s, 100.0, 999, C, 1, 2),     # fora (antes da janela)
        (t - 30 * s, 300.0, 10, C, 1, 2),
        (t, 600.0, 30, C, 3, 2),               # a deteccao
        (t + 1 * s, 700.0, 999, C, 1, 2),      # fora (depois)
    ])
    arq = tmp_path / "ev.csv"
    with arq.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["dia", "hora_brt", "ts_ns", "direcao", "preco", "barreira"])
        w.writerow(["2026-08-03", "10:00:00", t, 1, 600.0, "alvo"])
        w.writerow(["2026-08-03", "10:00:00", t, 1, 600.0, "alvo"])   # duplicado
    linhas = ler_eventos([arq, arq])
    assert len(linhas) == 1
    evs, avisos = calcular([tmp_path / "local", tmp_path / "bk"], "WINFUT", linhas)
    assert avisos == [] and len(evs) == 1
    f = evs[0].f
    assert f.v_dir == 40 and f.c1 == 1.0
    assert f.agente_top == 3 and abs(f.c2 - 30 / 40) < 1e-12


def _ev(c1: float, barreira: str) -> EventoAg:
    return EventoAg("2026-08-03", "10:00:00", 0, 1, barreira,
                    Features(100.0, c1, c1, 1, 0.0, 10))


def test_etapa_cega_nao_le_resultado() -> None:
    """Mesmos eventos com resultados diferentes -> etapa cega identica."""
    a = [_ev(i / 10, "alvo") for i in range(10)]
    b = [_ev(i / 10, "xxxx") for i in range(10)]
    assert etapa_cega(a) == etapa_cega(b)


def test_medir_controles_positivo_e_negativo() -> None:
    rng = np.random.default_rng(7)
    c1 = rng.random(60)
    # positivo: alvo sse concentracao alta
    pos = [_ev(v, "alvo" if v > np.median(c1) else "stop") for v in c1]
    r = medir(pos, "c1", float(np.median(c1)))
    assert r["alta"]["p_alvo"] == 1.0 and r["baixa"]["p_alvo"] == 0.0
    # negativo: resultado sem relacao com a variavel -> diferenca pequena
    res = rng.random(60) < 0.6
    neg = [_ev(v, "alvo" if a else "stop") for v, a in zip(c1, res, strict=True)]
    r = medir(neg, "c1", float(np.median(c1)))
    assert abs(r["diferenca"]) < 0.3
    assert r["alta"]["n"] + r["baixa"]["n"] == 60
