"""
Testes de research/mae.py -- o calculo de MAE precisa ser exato, ele decide
se o stop catastrofico e' seguro de cauda ou ja esta mordendo de verdade.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from profittape.research.mae import _sinal_de_entrada, analisar_mae


def test_sinal_de_entrada_contrarian() -> None:
    z = pd.Series([-2.0, -0.5, 0.0, 0.5, 2.0])
    lado = _sinal_de_entrada(z, threshold=1.4, direcao="contrarian")
    assert list(lado) == [1, 0, 0, 0, -1]   # extremo baixo compra, alto vende


def test_sinal_de_entrada_momentum() -> None:
    z = pd.Series([-2.0, 0.0, 2.0])
    lado = _sinal_de_entrada(z, threshold=1.4, direcao="momentum")
    assert list(lado) == [-1, 0, 1]   # invertido do contrarian


def _df_basico() -> pd.DataFrame:
    """Cenario calculado a mao: compra na barra 2 (close=100), h=3.
    MAE_close esperado=5 (barra 3), MAE_intrabar esperado=10 (barra 3),
    pnl_final_h esperado=+10 (barra 5, close=110)."""
    return pd.DataFrame({
        "dia": ["2026-01-01"] * 10,
        "ts_close": np.arange(10) * 10**11,
        "close":  [50, 60, 100, 95, 98, 110, 70, 71, 72, 73],
        "high":   [51, 61, 101, 96, 99, 111, 71, 72, 73, 74],
        "low":    [49, 59, 99,  90, 97, 105, 69, 70, 71, 72],
        "z_agf_3": [0, 0, -1.5, 0, 0, 0, 0, 0, 0, 0],
    })


def test_mae_calculado_corretamente_compra(tmp_path: Path) -> None:
    arq = tmp_path / "features.parquet"
    _df_basico().to_parquet(arq, index=False)
    r = analisar_mae(arq, "z_agf_3", horizonte=3, threshold_entrada=1.4,
                     direcao="contrarian", stop_catastrofico_pontos=500,
                     saida=tmp_path / "out", treino_min=0)
    tabela = r["tabela"]
    assert len(tabela) == 1
    assert tabela["lado"].iloc[0] == 1
    assert tabela["mae_close"].iloc[0] == 5
    assert tabela["mae_intrabar"].iloc[0] == 10
    assert tabela["pnl_final_h"].iloc[0] == 10
    assert not tabela["teria_batido_stop"].iloc[0]


def test_mae_calculado_corretamente_venda(tmp_path: Path) -> None:
    """Espelha o cenario de compra: venda na barra 2 (close=100), preco
    SOBE (contra a posicao vendida) na barra 3 -> excursao positiva."""
    df = pd.DataFrame({
        "dia": ["2026-01-01"] * 10,
        "ts_close": np.arange(10) * 10**11,
        "close":  [50, 60, 100, 108, 102, 90, 70, 71, 72, 73],
        "high":   [51, 61, 101, 112, 103, 91, 71, 72, 73, 74],
        "low":    [49, 59, 99,  105, 101, 89, 69, 70, 71, 72],
        "z_agf_3": [0, 0, 1.5, 0, 0, 0, 0, 0, 0, 0],   # extremo alto -> vende
    })
    arq = tmp_path / "features.parquet"
    df.to_parquet(arq, index=False)
    r = analisar_mae(arq, "z_agf_3", horizonte=3, threshold_entrada=1.4,
                     direcao="contrarian", stop_catastrofico_pontos=500,
                     saida=tmp_path / "out", treino_min=0)
    tabela = r["tabela"]
    assert tabela["lado"].iloc[0] == -1
    # excursao contra vendido = (entrada - preco) * -1 = preco - entrada
    assert tabela["mae_close"].iloc[0] == 8     # barra3: 108-100
    assert tabela["mae_intrabar"].iloc[0] == 12  # barra3 high=112: 112-100
    assert tabela["pnl_final_h"].iloc[0] == 10   # (90-100)*-1 = 10


def test_trigger_no_fim_do_dia_sem_janela_completa_e_descartado(tmp_path: Path) -> None:
    """Trigger na PENULTIMA barra do dia (h=3) nao tem 3 barras de futuro
    dentro do mesmo dia -- purge estrutural, mesma regra de retornos.py."""
    df = pd.DataFrame({
        "dia": ["2026-01-01"] * 5,
        "ts_close": np.arange(5) * 10**11,
        "close": [50, 60, 70, 80, 90],
        "high": [51, 61, 71, 81, 91],
        "low": [49, 59, 69, 79, 89],
        "z_agf_3": [0, 0, 0, -1.5, 0],   # trigger na barra 3, so' 1 barra depois
    })
    arq = tmp_path / "features.parquet"
    df.to_parquet(arq, index=False)
    with pytest.raises(SystemExit, match="insuficiente"):
        analisar_mae(arq, "z_agf_3", horizonte=3, threshold_entrada=1.4,
                    direcao="contrarian", stop_catastrofico_pontos=500,
                    saida=tmp_path / "out", treino_min=0)


def test_trigger_nao_atravessa_para_o_dia_seguinte(tmp_path: Path) -> None:
    """Trigger no fim do dia 1 nao pode usar barras do dia 2 como futuro,
    mesmo que existam logo em seguida no dataframe."""
    df = pd.DataFrame({
        "dia": ["2026-01-01"] * 4 + ["2026-01-02"] * 4,
        "ts_close": np.arange(8) * 10**11,
        "close": [50, 60, 70, 80,   200, 201, 202, 203],
        "high":  [51, 61, 71, 81,   201, 202, 203, 204],
        "low":   [49, 59, 69, 79,   199, 200, 201, 202],
        "z_agf_3": [0, 0, 0, -1.5,   0, 0, 0, 0],   # trigger na ultima barra do dia 1
    })
    arq = tmp_path / "features.parquet"
    df.to_parquet(arq, index=False)
    with pytest.raises(SystemExit, match="insuficiente"):
        analisar_mae(arq, "z_agf_3", horizonte=3, threshold_entrada=1.4,
                    direcao="contrarian", stop_catastrofico_pontos=500,
                    saida=tmp_path / "out", treino_min=0)


def test_nenhum_trigger_falha_com_mensagem_clara(tmp_path: Path) -> None:
    df = pd.DataFrame({
        "dia": ["2026-01-01"] * 5,
        "ts_close": np.arange(5) * 10**11,
        "close": [50, 60, 70, 80, 90],
        "high": [51, 61, 71, 81, 91],
        "low": [49, 59, 69, 79, 89],
        "z_agf_3": [0.1, 0.2, -0.3, 0.1, 0.0],   # nunca cruza o threshold
    })
    arq = tmp_path / "features.parquet"
    df.to_parquet(arq, index=False)
    with pytest.raises(SystemExit, match="nenhum trigger"):
        analisar_mae(arq, "z_agf_3", horizonte=3, threshold_entrada=1.4,
                    direcao="contrarian", stop_catastrofico_pontos=500,
                    saida=tmp_path / "out", treino_min=0)


def test_relatorio_markdown_e_gerado(tmp_path: Path) -> None:
    arq = tmp_path / "features.parquet"
    _df_basico().to_parquet(arq, index=False)
    r = analisar_mae(arq, "z_agf_3", horizonte=3, threshold_entrada=1.4,
                     direcao="contrarian", stop_catastrofico_pontos=500,
                     saida=tmp_path / "out", treino_min=0)
    conteudo = Path(r["relatorio"]).read_text(encoding="utf-8")
    assert "MAE_close" in conteudo
    assert "MAE_intrabar" in conteudo
    assert "stop catastrofico" in conteudo


def test_quebra_por_lado_separa_compra_e_venda(tmp_path: Path) -> None:
    """
    Achado real (2026-08-27): threshold simetrico pode esconder assimetria
    de edge entre compra e venda -- um lado carrega o sinal, o outro dilui.
    A quebra por lado precisa separar corretamente os dois grupos.
    """
    df = pd.DataFrame({
        "dia": ["2026-01-01"] * 10,
        "ts_close": np.arange(10) * 10**11,
        # Duas compras (lucrativas) e duas vendas (uma lucrativa, uma nao)
        "close":  [100, 100, 110,  90, 100, 95, 105, 130, 131, 132],
        "high":   [101, 101, 111,  91, 101, 96, 106, 131, 132, 133],
        "low":    [99,  99,  109,  89, 99,  94, 104, 129, 130, 131],
        "z_agf_3": [-1.5, 0, 0, 1.5, 0, 0, -1.5, 0, 0, 0],
    })
    arq = tmp_path / "features.parquet"
    df.to_parquet(arq, index=False)
    r = analisar_mae(arq, "z_agf_3", horizonte=3, threshold_entrada=1.4,
                     direcao="contrarian", stop_catastrofico_pontos=500,
                     saida=tmp_path / "out", treino_min=0)

    assert r["stats_compra"]["n"] == 2   # barras 0 e 6
    assert r["stats_venda"]["n"] == 1    # barra 3
    conteudo = Path(r["relatorio"]).read_text(encoding="utf-8")
    assert "Quebra por lado" in conteudo
    assert "compra" in conteudo and "venda" in conteudo


def test_restringe_a_dias_out_of_sample_como_quintis(tmp_path: Path) -> None:
    """
    BUG REAL corrigido (2026-08-27, achado comparando com quintis.py): a
    primeira versao rodava sobre a amostra INTEIRA, misturando dias de
    TREINO do walk-forward com dias de TESTE -- diferente da disciplina
    que quintis.py ja seguia. Aqui, com treino_min=3, teste_dias=1, os
    primeiros 3 dias sao SEMPRE treino (nunca aparecem na analise) --
    um trigger so' no dia 1 (treino) tem que ser IGNORADO.
    """
    dias_todos = [f"2026-01-0{i}" for i in range(1, 6)]   # 5 dias
    linhas = []
    for d_idx, dia in enumerate(dias_todos):
        for b in range(5):
            z = -1.5 if (d_idx == 0 and b == 2) else 0.0   # trigger SO no dia 1 (treino)
            linhas.append({"dia": dia, "close": 100.0 + b, "high": 101.0 + b,
                           "low": 99.0 + b, "z_agf_3": z})
    df = pd.DataFrame(linhas)
    df["ts_close"] = np.arange(len(df)) * 10**11
    arq = tmp_path / "features.parquet"
    df.to_parquet(arq, index=False)

    with pytest.raises(SystemExit, match="nenhum trigger"):
        # com treino_min=3, teste_dias=1: dias 1-3 sao treino (o unico
        # trigger existente esta no dia 1) -- filtrado fora, sobra ZERO
        # triggers no pool out-of-sample.
        analisar_mae(arq, "z_agf_3", horizonte=1, threshold_entrada=1.4,
                    direcao="contrarian", stop_catastrofico_pontos=500,
                    saida=tmp_path / "out", treino_min=3, teste_dias=1)


def test_purge_de_dia_sobrevive_a_reindexacao_apos_filtro_oos(tmp_path: Path) -> None:
    """
    Depois de filtrar para so' dias de teste e reindexar, linhas de dias de
    teste NAO ADJACENTES no calendario (com um dia de treino saltado no
    meio) ficam fisicamente vizinhas no dataframe filtrado. O purge (nunca
    atravessar o dia) tem que continuar funcionando MESMO ASSIM -- ele
    compara a coluna 'dia', nao a posicao fisica da linha.
    """
    # dias 1,2,3 = treino (teste_dias=1, treino_min=3); dia 4 e' teste;
    # dia 2 (NO MEIO do treino) nao aparece na analise -- mas o ponto do
    # teste e' o trigger no FIM do dia 4 nao vazar para o "dia 5" seguinte
    # (que tambem seria teste) usando dado de um dia diferente.
    linhas = []
    for d_idx in range(1, 6):
        dia = f"2026-01-0{d_idx}"
        for b in range(3):
            z = -1.5 if (d_idx == 4 and b == 2) else 0.0   # trigger na ULTIMA barra do dia 4
            linhas.append({"dia": dia, "close": 100.0 + d_idx * 10 + b,
                           "high": 101.0 + d_idx * 10 + b,
                           "low": 99.0 + d_idx * 10 + b, "z_agf_3": z})
    df = pd.DataFrame(linhas)
    df["ts_close"] = np.arange(len(df)) * 10**11
    arq = tmp_path / "features.parquet"
    df.to_parquet(arq, index=False)

    # dias de teste com treino_min=3, teste_dias=1: dia4, dia5 sao teste.
    # O trigger esta na ULTIMA barra do dia4 -- sem barra seguinte NO
    # MESMO dia, precisa ser descartado (nao pode usar barra do dia5).
    with pytest.raises(SystemExit, match="insuficiente"):
        analisar_mae(arq, "z_agf_3", horizonte=1, threshold_entrada=1.4,
                    direcao="contrarian", stop_catastrofico_pontos=500,
                    saida=tmp_path / "out", treino_min=3, teste_dias=1)


def test_mfe_e_complemento_simetrico_do_mae(tmp_path: Path) -> None:
    """
    Preparacao para Rota B (2026-08-27): MFE = complemento simetrico do
    MAE, excursao A FAVOR em vez de contra. Mesmo cenario ja conferido a
    mao do MAE (compra, entrada=100, janela close=[95,98,110]):
    excursao_close=[5,2,-10] -> MAE=5 (ja testado), MFE=10 (o -10 vira
    +10, a melhor excursao a favor).
    """
    arq = tmp_path / "features.parquet"
    _df_basico().to_parquet(arq, index=False)
    r = analisar_mae(arq, "z_agf_3", horizonte=3, threshold_entrada=1.4,
                     direcao="contrarian", stop_catastrofico_pontos=500,
                     saida=tmp_path / "out", treino_min=0)
    assert r["tabela"]["mfe_close"].iloc[0] == 10


def test_mfe_venda_espelha_o_sinal_corretamente(tmp_path: Path) -> None:
    """Mesmo cenario ja conferido a mao da venda: entrada=100, janela
    close=[108,102,90]. excursao_close (venda, L=-1) = [8,2,-10] ->
    MAE=8 (ja testado), MFE=10 (o -10 vira +10)."""
    df = pd.DataFrame({
        "dia": ["2026-01-01"] * 10,
        "ts_close": np.arange(10) * 10**11,
        "close":  [50, 60, 100, 108, 102, 90, 70, 71, 72, 73],
        "high":   [51, 61, 101, 112, 103, 91, 71, 72, 73, 74],
        "low":    [49, 59, 99,  105, 101, 89, 69, 70, 71, 72],
        "z_agf_3": [0, 0, 1.5, 0, 0, 0, 0, 0, 0, 0],
    })
    arq = tmp_path / "features.parquet"
    df.to_parquet(arq, index=False)
    r = analisar_mae(arq, "z_agf_3", horizonte=3, threshold_entrada=1.4,
                     direcao="contrarian", stop_catastrofico_pontos=500,
                     saida=tmp_path / "out", treino_min=0)
    assert r["tabela"]["mfe_close"].iloc[0] == 10


def test_relatorio_inclui_secao_mfe(tmp_path: Path) -> None:
    arq = tmp_path / "features.parquet"
    _df_basico().to_parquet(arq, index=False)
    r = analisar_mae(arq, "z_agf_3", horizonte=3, threshold_entrada=1.4,
                     direcao="contrarian", stop_catastrofico_pontos=500,
                     saida=tmp_path / "out", treino_min=0)
    conteudo = Path(r["relatorio"]).read_text(encoding="utf-8")
    assert "MFE_close" in conteudo
    assert "Rota B" in conteudo
