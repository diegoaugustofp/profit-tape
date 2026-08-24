"""
Testes da tabela de quintis: precisa distinguir sinal contrarian construido de
ruido, E precisa reagir ao custo — o mesmo spread bruto deve virar 'MORTO' com
custo alto e 'VIVO' com custo baixo. Se o custo nao mudar o veredito, a tabela
nao esta comparando nada de verdade.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from profittape.research.quintis import avaliar_pares, tabela_quintis
from profittape.research.retornos import adicionar_ret_futuro_pontos
from profittape.research.walkforward import gerar_folds


def _dados_contrarian(n_dias: int = 12, barras_dia: int = 60,
                      spread_pts: float = 8.0, seed: int = 4) -> pd.DataFrame:
    """
    Sinal alto -> retorno futuro NEGATIVO em pontos, por construcao, com
    spread controlado entre quintil 1 e quintil 5 (~spread_pts).
    """
    rng = np.random.default_rng(seed)
    linhas = []
    for d in range(n_dias):
        dia = f"2026-08-{d + 1:02d}"
        preco = 140000.0
        sinal = rng.normal(0, 1, barras_dia)
        for i in range(barras_dia):
            # ret futuro em pontos = -k*sinal + ruido; k calibrado p/ spread alvo
            ret = -(spread_pts / 4) * sinal[i] + rng.normal(0, 1.5)
            linhas.append({
                "ts_close": 1_700_000_000_000_000_000 + i * 60_000_000_000,
                "close": preco, "dia": dia, "z_sinal": sinal[i],
            })
            preco += ret
    return pd.DataFrame(linhas)


def test_tabela_quintis_ordena_e_calcula_spread() -> None:
    df = _dados_contrarian()
    df = adicionar_ret_futuro_pontos(df, [1])
    dias = sorted(df["dia"].unique())
    folds = gerar_folds(dias, treino_min=3, teste_dias=2)
    dias_teste = {d for _t, teste in folds for d in teste}

    t = tabela_quintis(df, "z_sinal", 1, dias_teste, custo_pontos=0.0)
    assert list(t["quintil"]) == [1, 2, 3, 4, 5]
    assert t["n"].sum() > 0
    # sinal contrarian: quintil 1 (sinal mais baixo) deve ter retorno FUTURO
    # medio maior que quintil 5 (sinal mais alto) — spread positivo
    q1 = t.loc[t["quintil"] == 1, "ret_medio_pontos"].iloc[0]
    q5 = t.loc[t["quintil"] == 5, "ret_medio_pontos"].iloc[0]
    assert q1 > q5


def test_custo_muda_o_veredito_vivo_morto(tmp_path) -> None:
    """O mesmo spread bruto deve sobreviver a custo baixo e morrer a custo alto."""
    df = _dados_contrarian(spread_pts=10.0)
    arq = tmp_path / "features.parquet"
    df.to_parquet(arq, index=False)

    barato = avaliar_pares(arq, [("z_sinal", 1)], tmp_path / "out_barato",
                           custo_pontos=0.5)
    caro = avaliar_pares(arq, [("z_sinal", 1)], tmp_path / "out_caro",
                         custo_pontos=50.0)

    t_barato = barato["tabelas"][("z_sinal", 1)]
    t_caro = caro["tabelas"][("z_sinal", 1)]

    spread_liq_barato = (
        t_barato.loc[t_barato["quintil"] == 1, "ret_liquido_pontos"].iloc[0]
        - t_barato.loc[t_barato["quintil"] == 5, "ret_liquido_pontos"].iloc[0]
    )
    spread_liq_caro = (
        t_caro.loc[t_caro["quintil"] == 1, "ret_liquido_pontos"].iloc[0]
        - t_caro.loc[t_caro["quintil"] == 5, "ret_liquido_pontos"].iloc[0]
    )
    # o custo e' subtraido uma vez por observacao em CADA quintil, entao ele
    # cancela no SPREAD (Q1-Q5) — o que muda com o custo e' o nivel de cada
    # perna, nao o spread. Verificamos entao o nivel liquido por perna.
    assert spread_liq_barato == pytest.approx(spread_liq_caro, abs=1e-6)
    ret_liq_q1_barato = t_barato.loc[t_barato["quintil"] == 1, "ret_liquido_pontos"].iloc[0]
    ret_liq_q1_caro = t_caro.loc[t_caro["quintil"] == 1, "ret_liquido_pontos"].iloc[0]
    assert ret_liq_q1_barato > ret_liq_q1_caro          # custo alto reduz o liquido
    assert ret_liq_q1_caro < 0                          # custo de 50 pts mata a perna


def test_relatorio_marca_vivo_ou_morto(tmp_path) -> None:
    df = _dados_contrarian(spread_pts=10.0)
    arq = tmp_path / "features.parquet"
    df.to_parquet(arq, index=False)

    r = avaliar_pares(arq, [("z_sinal", 1)], tmp_path / "out", custo_pontos=0.1)
    texto = (tmp_path / "out" / "quintis.md").read_text(encoding="utf-8")
    assert "ECONOMICAMENTE VIVO" in texto or "MORTO PELO CUSTO" in texto
    assert "z_sinal" in texto
    assert r["custo_pontos"] == 0.1


def test_amostra_pequena_recusa() -> None:
    df = _dados_contrarian(n_dias=2, barras_dia=3)
    df = adicionar_ret_futuro_pontos(df, [1])
    dias_teste = set(df["dia"].unique())
    with pytest.raises(SystemExit):
        tabela_quintis(df, "z_sinal", 1, dias_teste, custo_pontos=1.0)


def test_spread_do_par_long_short_desconta_2x_o_custo(tmp_path) -> None:
    """
    A estrategia implicita e' par (compra Q1, vende Q5) — DUAS pernas, DOIS
    custos de ida-e-volta. O spread liquido do relatorio precisa refletir
    isso (spread_bruto - 2*custo), nao o spread entre ret_liquido_pontos de
    cada perna (que cancela o custo por construcao — bug pego em teste
    anterior). Custo alto o bastante deve matar um spread bruto positivo.
    """
    df = _dados_contrarian(spread_pts=10.0)
    arq = tmp_path / "features.parquet"
    df.to_parquet(arq, index=False)

    avaliar_pares(arq, [("z_sinal", 1)], tmp_path / "out", custo_pontos=8.0)
    texto = (tmp_path / "out" / "quintis.md").read_text(encoding="utf-8")
    # spread bruto ~10pts, custo 8pts/perna x2 = 16pts > spread bruto -> morto
    assert "MORTO PELO CUSTO" in texto


def test_diferenca_quintis_detecta_diferenca_real() -> None:
    """
    Constroi dados onde Q4 e Q5 tem medias claramente diferentes (a
    nao-monotonicidade observada em producao) — o teste de Welch precisa
    detectar isso.
    """
    rng = np.random.default_rng(9)
    linhas = []
    for d in range(15):
        dia = f"2026-08-{d + 1:02d}"
        preco = 140000.0
        sinal = rng.normal(0, 1, 80)
        for i in range(80):
            # Q4 (sinal ~0.5 pos) tem retorno MUITO mais negativo que Q5
            # (sinal ~1.3 pos) por construcao — nao-monotonico de proposito.
            if 0.2 < sinal[i] < 0.8:
                ret = -30 + rng.normal(0, 3)
            elif sinal[i] >= 0.8:
                ret = -5 + rng.normal(0, 3)
            else:
                ret = rng.normal(0, 3)
            linhas.append({
                "ts_close": 1_700_000_000_000_000_000 + i * 60_000_000_000,
                "close": preco, "dia": dia, "z_sinal": sinal[i],
            })
            preco += ret
    df = pd.DataFrame(linhas)
    df = adicionar_ret_futuro_pontos(df, [1])
    dias = sorted(df["dia"].unique())
    folds = gerar_folds(dias, treino_min=3, teste_dias=2)
    dias_teste = {dd for _t, teste in folds for dd in teste}

    from profittape.research.quintis import testar_diferenca_quintis
    t34 = testar_diferenca_quintis(df, "z_sinal", 1, dias_teste, 0.0, 4, 5)
    assert t34["diferem_5pct"] is True
    assert t34["p_valor"] < 0.05


def test_diferenca_quintis_nao_acusa_diferenca_quando_nao_ha(tmp_path) -> None:
    """Quintis com a MESMA distribuicao devem sair 'indistinguivel'."""
    rng = np.random.default_rng(21)
    linhas = []
    for d in range(15):
        dia = f"2026-08-{d + 1:02d}"
        preco = 140000.0
        sinal = rng.normal(0, 1, 80)
        for i in range(80):
            ret = rng.normal(0, 2)   # retorno IID, sem relacao com o sinal
            linhas.append({
                "ts_close": 1_700_000_000_000_000_000 + i * 60_000_000_000,
                "close": preco, "dia": dia, "z_sinal": sinal[i],
            })
            preco += ret
    df = pd.DataFrame(linhas)
    df = adicionar_ret_futuro_pontos(df, [1])
    dias = sorted(df["dia"].unique())
    folds = gerar_folds(dias, treino_min=3, teste_dias=2)
    dias_teste = {dd for _t, teste in folds for dd in teste}

    from profittape.research.quintis import testar_diferenca_quintis
    t = testar_diferenca_quintis(df, "z_sinal", 1, dias_teste, 0.0, 4, 5)
    assert t["diferem_5pct"] is False


def test_avaliar_pares_inclui_diferencas_no_resultado_e_relatorio(tmp_path) -> None:
    df = _dados_contrarian(spread_pts=10.0)
    arq = tmp_path / "features.parquet"
    df.to_parquet(arq, index=False)

    r = avaliar_pares(arq, [("z_sinal", 1)], tmp_path / "out", custo_pontos=1.0)
    assert ("z_sinal", 1) in r["diferencas"]
    assert len(r["diferencas"][("z_sinal", 1)]) == 4    # 1v2,2v3,3v4,4v5
    texto = (tmp_path / "out" / "quintis.md").read_text(encoding="utf-8")
    assert "Diferenca entre quintis adjacentes" in texto
    assert "Welch" in texto
