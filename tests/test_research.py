"""
Testes do research/: o metodo precisa provar que distingue sinal de ruido
ANTES de rodar sobre dado real — senao o veredito nao vale nada.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from profittape.research.ic import ic_spearman
from profittape.research.pipeline import rodar
from profittape.research.retornos import adicionar_ret_futuro
from profittape.research.trials import RegistroTrials, limiar_deflacionado
from profittape.research.walkforward import gerar_folds


def _barras_sinteticas(n_dias: int = 12, barras_dia: int = 80,
                       seed: int = 7) -> pd.DataFrame:
    """
    Barras com uma feature PREDITIVA por construcao (correlacionada com o
    retorno futuro de 1 barra) e uma de ruido puro. O teste de honestidade do
    metodo: ele precisa separar as duas.
    """
    rng = np.random.default_rng(seed)
    linhas = []
    ts = 1_700_000_000_000_000_000
    for d in range(n_dias):
        dia = f"2026-08-{d+1:02d}"
        ret_fut = rng.normal(0, 0.001, barras_dia)          # retornos da barra t->t+1
        preco = 100 * np.cumprod(1 + np.concatenate([[0], ret_fut[:-1]]))
        for i in range(barras_dia):
            linhas.append({
                "ts_close": ts, "close": preco[i], "dia": dia,
                # sinal_bom conhece 60% do retorno futuro + ruido
                "z_sinal_bom": 0.6 * (ret_fut[i] / 0.001) + rng.normal(0, 0.8),
                "z_ruido": rng.normal(),
            })
            ts += 60_000_000_000
    return pd.DataFrame(linhas)


def test_ic_spearman_basico() -> None:
    x = pd.Series(range(100), dtype=float)
    assert ic_spearman(x, x) == pytest.approx(1.0)
    assert ic_spearman(x, -x) == pytest.approx(-1.0)
    assert np.isnan(ic_spearman(x.head(5), x.head(5)))     # amostra < 10 -> NaN


def test_retorno_futuro_nao_cruza_dia() -> None:
    df = _barras_sinteticas(n_dias=2, barras_dia=20)
    df = adicionar_ret_futuro(df, [5])
    ultimas = df.groupby("dia", observed=True).tail(5)
    assert ultimas["ret_fut_5"].isna().all()               # sem futuro intra-dia
    primeiras = df.groupby("dia", observed=True).head(15)
    assert primeiras["ret_fut_5"].notna().all()


def test_walkforward_expande_e_nunca_vaza_dia() -> None:
    dias = [f"d{i}" for i in range(10)]
    folds = gerar_folds(dias, treino_min=3, teste_dias=2)
    assert folds[0] == (["d0", "d1", "d2"], ["d3", "d4"])
    for treino, teste in folds:
        assert not set(treino) & set(teste)                # disjuntos
        assert max(treino) < min(teste)                    # teste sempre no futuro


def test_metodo_separa_sinal_de_ruido(tmp_path) -> None:
    """O teste central: preditiva por construcao -> segue; ruido -> nao-segue."""
    df = _barras_sinteticas()
    arq = tmp_path / "features.parquet"
    df.to_parquet(arq, index=False)

    r = rodar(arq, tmp_path / "research", horizontes=[1], treino_min=3, teste_dias=2)
    tab = r["tabela"].set_index("feature")

    assert tab.loc["z_sinal_bom", "veredito"] == "segue"
    assert tab.loc["z_ruido", "veredito"] in ("descarta", "inconclusivo")
    assert tab.loc["z_sinal_bom", "ic_medio"] > 0.3
    assert abs(tab.loc["z_ruido", "ic_medio"]) < 0.15


def test_trials_persistem_entre_rodadas(tmp_path) -> None:
    df = _barras_sinteticas()
    arq = tmp_path / "features.parquet"
    df.to_parquet(arq, index=False)
    saida = tmp_path / "research"

    r1 = rodar(arq, saida, horizontes=[1])
    r2 = rodar(arq, saida, horizontes=[1])
    assert r2["trials_acumulados"] == r1["trials_acumulados"] * 2
    # limiar SOBE com mais trials — repetir o teste custa evidencia
    assert r2["limiar_deflacionado"] >= r1["limiar_deflacionado"]


def test_limiar_deflacionado_cresce_com_trials() -> None:
    assert limiar_deflacionado(1) == pytest.approx(1.96)
    l10, l100, l1000 = (limiar_deflacionado(n) for n in (10, 100, 1000))
    assert l10 < l100 < l1000
    assert 1.5 < l10 < 2.5
    assert 3.0 < l1000 < 4.0


def test_registro_trials_sobrevive_reload(tmp_path) -> None:
    caminho = tmp_path / "trials.json"
    r1 = RegistroTrials(caminho)
    r1.registrar_rodada(15, {"nota": "rodada 1"})
    r2 = RegistroTrials(caminho)                            # reabre do disco
    assert r2.total == 15
    r2.registrar_rodada(15, {"nota": "rodada 2"})
    assert RegistroTrials(caminho).total == 30


def test_relatorio_escrito_com_vereditos(tmp_path) -> None:
    df = _barras_sinteticas()
    arq = tmp_path / "features.parquet"
    df.to_parquet(arq, index=False)
    rodar(arq, tmp_path / "research", horizontes=[1])
    texto = (tmp_path / "research").glob("relatorio_*.md")
    conteudo = next(texto).read_text(encoding="utf-8")
    assert "z_sinal_bom" in conteudo
    assert "segue" in conteudo
    assert "limiar deflacionado" in conteudo
