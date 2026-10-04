"""Rolagem, pergunta A: persistencia do fluxo liquido por corretora no instrumento de roll."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from profittape.research import rolagem_persistencia as rp


def _trades(linhas: list[tuple[int, int, int]]) -> pd.DataFrame:
    """(comprador, vendedor, quantidade)."""
    return pd.DataFrame({"ts_ns": range(len(linhas)), "price": 30.0,
                         "quantidade": [q for _, _, q in linhas],
                         "agente_comprador": [c for c, _, _ in linhas],
                         "agente_vendedor": [v for _, v, _ in linhas], "trade_type": 2})


def test_liquido_exclui_cross_da_mesma_corretora() -> None:
    t = _trades([(1, 2, 10), (1, 1, 999), (3, 1, 4)])
    liq = rp.liquido_por_agente(t)
    assert liq.to_dict() == {1: 10 - 4, 2: -10, 3: 4}    # o cross 1x1 de 999 nao entra


def test_s_a_mao_com_exemplo_pequeno() -> None:
    # agente1: min(10,4)=4 mesmo sinal (+4); agente2: min(5,8)=5 oposto (-5);
    # agente3: min(3,3)=3 oposto (-3)
    v = np.array([[10.0, -5.0, 3.0], [4.0, 8.0, -3.0]])
    assert rp.estatistica_s(v) == pytest.approx(4 - 5 - 3)


def test_s_soma_as_transicoes() -> None:
    v = np.array([[5.0], [5.0], [-5.0]])
    assert rp.estatistica_s(v) == pytest.approx(5 - 5)    # (+) depois (-)


def _magnitudes_correlacionadas(n_ag: int, n_dias: int, rng: np.random.Generator) -> np.ndarray:
    escala = np.exp(rng.normal(0, 1.5, n_ag))                  # corretora grande e' grande todo dia
    mags = escala * np.exp(rng.normal(0, 0.3, (n_dias, n_ag)))
    return mags * rng.choice([-1.0, 1.0], size=(n_dias, n_ag))  # sinais INDEPENDENTES


def test_tamanho_do_teste_com_magnitudes_correlacionadas_e_sinais_independentes() -> None:
    """O verificador que faltou na v4.28: sem persistencia, rejeita ~alfa, nao muito mais."""
    rng = np.random.default_rng(1)
    rej = sum(rp.testar(_magnitudes_correlacionadas(30, 3, rng), 500,
                        int(rng.integers(1 << 30)))["p"] < 0.05 for _ in range(300))
    assert rej / 300 < 0.10


def test_persistencia_plantada_e_achada() -> None:
    rng = np.random.default_rng(2)
    base = _magnitudes_correlacionadas(30, 3, rng)
    plantada = rp._plantar(base, 1.0, rng)
    r = rp.testar(plantada, 2000)
    assert r["p"] < 0.01 and r["z"] > 2


def test_poder_cresce_com_a_fracao() -> None:
    rng = np.random.default_rng(3)
    v = _magnitudes_correlacionadas(30, 3, rng)
    p = rp.poder(v, fracoes=(0.0, 1.0), repeticoes=60, n_sorteios=300)
    assert p["0.00"] < 0.15 and p["1.00"] > 0.9


def test_permutacao_entre_corretoras_seria_enviesada() -> None:
    """Documenta POR QUE o nulo e' a inversao de sinal: a permutacao inventa sinal."""
    rng = np.random.default_rng(4)
    escala = np.exp(rng.normal(0, 1.5, 30))
    sg = rng.choice([-1.0, 1.0], size=(2, 30))                 # sem persistencia
    v = escala * np.exp(rng.normal(0, 0.3, (2, 30))) * sg
    obs = []
    nulo_perm = []
    for _ in range(400):
        w = escala * np.exp(rng.normal(0, 0.3, (2, 30))) * rng.choice([-1.0, 1.0], size=(2, 30))
        obs.append(rp.estatistica_s(w))
        nulo_perm.append(rp.estatistica_s(np.vstack([w[0], rng.permutation(w[1])])))
    # a permutacao subestima a dispersao: p enganosamente pequeno
    assert np.std(obs) > np.std(nulo_perm)
    assert v.shape == (2, 30)


def test_descrever_roda_ponta_a_ponta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d1, d2 = dt.date(2026, 9, 28), dt.date(2026, 9, 29)
    tabelas = {d1: _trades([(1, 2, 10), (3, 4, 5), (2, 3, 2)]),
               d2: _trades([(1, 2, 8), (3, 4, 6), (5, 1, 1)])}
    curated = tmp_path / "curated"
    for d in tabelas:
        (curated / "trade" / f"dt={d.isoformat()}" / "sym=WD1V26X26").mkdir(parents=True)
    monkeypatch.setattr(rp, "_carregar_dia",
                        lambda pasta, sym: tabelas[dt.date.fromisoformat(pasta.name[3:])])
    r = rp.descrever(curated, "WD1V26X26", [d1, d2, dt.date(2026, 9, 30)], 500, False,
                     tmp_path / "saida")
    assert r["dias"] == ["2026-09-28", "2026-09-29"]          # 30/09 sem dado: ignorado
    assert len(r["transicoes"]) == 1 and r["transicoes"][0]["S"] > 0
    assert (tmp_path / "saida" / "rolagem_persistencia.json").exists()


def test_dia_unico_nao_gera_transicao(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d1 = dt.date(2026, 9, 28)
    curated = tmp_path / "curated"
    (curated / "trade" / f"dt={d1.isoformat()}" / "sym=WD1V26X26").mkdir(parents=True)
    monkeypatch.setattr(rp, "_carregar_dia", lambda pasta, sym: _trades([(1, 2, 3)]))
    r = rp.descrever(curated, "WD1V26X26", [d1], 100, False, tmp_path / "s")
    assert "transicoes" not in r
