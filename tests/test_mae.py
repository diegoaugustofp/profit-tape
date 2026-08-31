"""
Testes de research/mae.py -- o calculo de MAE precisa ser exato, ele decide
se o stop catastrofico e' seguro de cauda ou ja esta mordendo de verdade.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from profittape.research.mae import (
    LIMITE_NAO_INFERIORIDADE_PTS,
    _sinal_de_entrada,
    analisar_mae,
)


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


def test_quebra_por_lado_inclui_mfe_mediana(tmp_path: Path) -> None:
    """
    Lacuna real achada (2026-08-27): o MFE agregado (compra+venda
    misturados) nao serve para congelar o par da Rota B -- precisa do
    MFE ESPECIFICO do lado com edge (venda), senao o lado sem edge
    (compra) dilui a mediana usada para escolher o alvo.
    """
    df = pd.DataFrame({
        "dia": ["2026-01-01"] * 10,
        "ts_close": np.arange(10) * 10**11,
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

    # compra (barras 0 e 6): MFE de cada uma -- calculado a mao no teste
    # ja existente (test_quebra_por_lado_separa_compra_e_venda) confirma
    # n=2 compra, n=1 venda; aqui so' confere que a chave existe e e' um
    # numero real, nao NaN nem ausente.
    assert not pd.isna(r["stats_compra"]["mfe_close_mediana"])
    assert not pd.isna(r["stats_venda"]["mfe_close_mediana"])

    conteudo = Path(r["relatorio"]).read_text(encoding="utf-8")
    assert "MFE_close mediana" in conteudo


# ---------------------------------------------------------------------------
# TRES REGIMES DE SAIDA (2026-08-31, pre-voo do stop continuo).
# Cenario CONFERIDO A MAO antes destes testes (regra 4 da disciplina):
# duas vendas, entrada 100, h=3, stop=50.
#
#   Op A (idx1): closes 130,120,90 | highs 155,140,125
#     exc_close    = 30, 20, -10 -> MAE_close    = 30  (NAO cruza)
#     exc_intrabar = 55, 40,  25 -> MAE_intrabar = 55  (CRUZA)
#     -> MARGINAL, pnl_final = (90-100)*-1 = +10 (POSITIVA)
#   Op B (idx5): closes 165,150,140 | highs 170,155,145
#     exc_close    = 65, 50, 40 -> primeiro cruzamento em 65 (excesso 15)
#     -> pnl_final = -40, stop close = -65, stop continuo = -50
#
#   agregados: sem stop -15.0 | stop close -27.5 | stop continuo -50.0
# ---------------------------------------------------------------------------

def _df_tres_regimes() -> pd.DataFrame:
    return pd.DataFrame({
        "dia": ["2026-01-01"] * 10,
        "ts_close": np.arange(10) * 10**11,
        "close": [50, 100, 130, 120, 90, 100, 165, 150, 140, 60],
        "high":  [51, 101, 155, 140, 125, 101, 170, 155, 145, 61],
        "low":   [49,  99, 125, 115,  85,  99, 160, 145, 135, 59],
        "z_agf_3": [0, 1.5, 0, 0, 0, 1.5, 0, 0, 0, 0],   # vende em 1 e 5
    })


def _rodar_tres_regimes(tmp_path: Path) -> dict:
    arq = tmp_path / "features.parquet"
    _df_tres_regimes().to_parquet(arq, index=False)
    return analisar_mae(arq, "z_agf_3", horizonte=3, threshold_entrada=1.4,
                        direcao="contrarian", stop_catastrofico_pontos=50,
                        saida=tmp_path / "out", treino_min=0)


def test_stop_continuo_dispara_onde_o_close_nao_dispara(tmp_path: Path) -> None:
    """A pergunta que decide o desenho: o continuo morde mais que o close?
    Op A cruza 50 no high (55) mas nunca no close (30) -- e' exatamente a
    classe de operacao que o stop continuo mata a mais."""
    r = _rodar_tres_regimes(tmp_path)
    assert r["n_teria_batido_stop"] == 1            # so' a Op B
    assert r["n_teria_batido_stop_intrabar"] == 2   # A e B
    t = r["tabela"]
    assert not t["teria_batido_stop"].iloc[0]
    assert t["teria_batido_stop_intrabar"].iloc[0]


def test_marginais_sao_as_que_so_o_continuo_mata(tmp_path: Path) -> None:
    """O conjunto do veredito: se as marginais terminam POSITIVAS, o stop
    continuo esta cortando a cauda que paga a conta."""
    r = _rodar_tres_regimes(tmp_path)
    assert r["n_marginais"] == 1
    assert r["n_marginais_positivas"] == 1
    assert r["pct_marginais_positivas"] == 1.0
    assert r["pnl_marginais_medio"] == 10.0   # Op A deixada correr: +10
    t = r["tabela"]
    assert t["marginal_so_intrabar"].iloc[0]       # Op A e' marginal
    assert not t["marginal_so_intrabar"].iloc[1]   # Op B bate nos dois


def test_stop_no_close_sai_no_preco_real_nao_no_limite(tmp_path: Path) -> None:
    """O bug que esta versao existe para consertar: o stop do close NAO sai
    em -50, sai em -65 (o close da barra que cruzou). E' o analogo das
    perdas reais de -615/-590/-565 contra um limite de 500."""
    r = _rodar_tres_regimes(tmp_path)
    t = r["tabela"]
    assert t["pnl_stop_close"].iloc[1] == -65.0      # preco REAL do close
    assert t["pnl_stop_continuo"].iloc[1] == -50.0   # ~ no limite
    assert t["excesso_close"].iloc[1] == 15.0        # 65 - 50
    assert r["excesso_close_medio"] == 15.0
    assert r["excesso_close_max"] == 15.0


def test_operacao_que_nao_bate_stop_nenhum_mantem_pnl_do_horizonte(tmp_path: Path) -> None:
    """Retrocompatibilidade do calculo: sem cruzamento, os tres regimes
    coincidem com a saida por tempo -- o stop nao inventa saida."""
    arq = tmp_path / "features.parquet"
    _df_basico().to_parquet(arq, index=False)   # compra, MAE_intrabar=10
    r = analisar_mae(arq, "z_agf_3", horizonte=3, threshold_entrada=1.4,
                     direcao="contrarian", stop_catastrofico_pontos=500,
                     saida=tmp_path / "out", treino_min=0)
    t = r["tabela"]
    assert not t["teria_batido_stop"].iloc[0]
    assert not t["teria_batido_stop_intrabar"].iloc[0]
    assert not t["marginal_so_intrabar"].iloc[0]
    assert pd.isna(t["excesso_close"].iloc[0])
    assert t["pnl_stop_close"].iloc[0] == t["pnl_final_h"].iloc[0]
    assert t["pnl_stop_continuo"].iloc[0] == t["pnl_final_h"].iloc[0]
    assert r["n_marginais"] == 0
    assert pd.isna(r["pct_marginais_positivas"])


def test_media_dos_tres_regimes(tmp_path: Path) -> None:
    """Conferido a mao: (10-40)/2, (10-65)/2, (-50-50)/2."""
    r = _rodar_tres_regimes(tmp_path)
    assert r["pnl_medio_sem_stop"] == -15.0
    assert r["pnl_medio_stop_close"] == -27.5
    assert r["pnl_medio_stop_continuo"] == -50.0


def test_contagem_por_lado_separa_close_de_continuo(tmp_path: Path) -> None:
    """O EA roda venda-apenas: a contagem que decide o pre-registro e' a do
    lado, nao a agregada."""
    r = _rodar_tres_regimes(tmp_path)
    v = r["stats_venda"]
    assert v["n"] == 2
    assert v["n_batido_stop"] == 1
    assert v["n_batido_stop_intrabar"] == 2
    assert v["n_marginais"] == 1
    assert v["n_marginais_positivas"] == 1
    # lado sem nenhuma operacao devolve o esqueleto completo, sem KeyError
    c = r["stats_compra"]
    assert c["n"] == 0
    assert c["n_batido_stop_intrabar"] == 0
    assert c["n_marginais"] == 0


def test_relatorio_traz_os_tres_regimes_e_a_errata(tmp_path: Path) -> None:
    r = _rodar_tres_regimes(tmp_path)
    conteudo = Path(r["relatorio"]).read_text(encoding="utf-8")
    assert "FREQUENCIA" in conteudo
    assert "CONFORMIDADE" in conteudo
    assert "TRES REGIMES" in conteudo
    assert "MARGINAIS" in conteudo
    assert "ERRATA" in conteudo
    assert "VENDA-APENAS" in conteudo
    # a chave enganosa nao volta por acidente
    assert "pnl_medio_com_stop_hipotetico" not in r


# ---------------------------------------------------------------------------
# DIFERENCA PAREADA + VEREDITO DO CRITERIO CONGELADO (2026-08-31b).
# Cenarios CONFERIDOS A MAO antes destes testes (regra 4).
#
#   Cenario 1 (_df_tres_regimes, o stop continuo CUSTA):
#     Op A: close=+10, continuo=-50 -> d=-60 | Op B: close=-65, cont=-50 -> d=+15
#     media = -22.5. UM dia -> bootstrap por bloco colapsa em [-22.5;-22.5].
#     -22.5 < -3.0 -> CONTRA
#
#   Cenario 2 (_df_pareado_favoravel, o stop continuo AJUDA):
#     Op X: closes 180,150,140 highs 185,155,145 -> close=-80, cont=-50, d=+30
#     Op Y: nao cruza em nenhum regime -> d=0
#     media = +15 -> IC [15;15] -> +15 > -3.0 -> FAVORAVEL, afetadas=1
# ---------------------------------------------------------------------------

def _df_pareado_favoravel() -> pd.DataFrame:
    return pd.DataFrame({
        "dia": ["2026-01-01"] * 10,
        "ts_close": np.arange(10) * 10**11,
        "close": [50, 100, 180, 150, 140, 100, 90, 95, 85, 60],
        "high":  [51, 101, 185, 155, 145, 101, 105, 110, 108, 61],
        "low":   [49,  99, 175, 145, 135,  99,  85,  90,  80, 59],
        "z_agf_3": [0, 1.5, 0, 0, 0, 1.5, 0, 0, 0, 0],
    })


def test_limite_de_nao_inferioridade_esta_congelado_no_modulo() -> None:
    """O criterio nao e' opcao de CLI de proposito (mesmo padrao de
    reversao.py): mudar exige editar o codigo e um pre-registro novo."""
    assert LIMITE_NAO_INFERIORIDADE_PTS == -3.0


def test_diferenca_pareada_e_zero_em_operacao_nao_afetada(tmp_path: Path) -> None:
    """O pareamento so' tem variancia nas operacoes que algum stop toca --
    e' isso que o torna melhor que comparar duas medias soltas."""
    arq = tmp_path / "features.parquet"
    _df_pareado_favoravel().to_parquet(arq, index=False)
    r = analisar_mae(arq, "z_agf_3", horizonte=3, threshold_entrada=1.4,
                     direcao="contrarian", stop_catastrofico_pontos=50,
                     saida=tmp_path / "out", treino_min=0)
    t = r["tabela"]
    assert t["dif_pareada"].iloc[0] == 30.0   # Op X: -50 - (-80)
    assert t["dif_pareada"].iloc[1] == 0.0    # Op Y: nenhum regime toca
    assert r["stats_venda"]["n_afetadas"] == 1


def test_veredito_contra_quando_o_continuo_custa(tmp_path: Path) -> None:
    arq = tmp_path / "features.parquet"
    _df_tres_regimes().to_parquet(arq, index=False)
    r = analisar_mae(arq, "z_agf_3", horizonte=3, threshold_entrada=1.4,
                     direcao="contrarian", stop_catastrofico_pontos=50,
                     saida=tmp_path / "out", treino_min=0)
    v = r["stats_venda"]
    assert v["dif_pareada_media"] == -22.5
    assert v["ic95_baixo"] == -22.5   # um so' dia -> IC deterministico
    assert v["ic95_alto"] == -22.5
    assert r["veredito"].startswith("CONTRA")


def test_veredito_favoravel_quando_o_continuo_ajuda(tmp_path: Path) -> None:
    arq = tmp_path / "features.parquet"
    _df_pareado_favoravel().to_parquet(arq, index=False)
    r = analisar_mae(arq, "z_agf_3", horizonte=3, threshold_entrada=1.4,
                     direcao="contrarian", stop_catastrofico_pontos=50,
                     saida=tmp_path / "out", treino_min=0)
    v = r["stats_venda"]
    assert v["dif_pareada_media"] == 15.0
    assert v["ic95_baixo"] == 15.0
    assert r["veredito"].startswith("FAVORAVEL")


def test_veredito_avalia_a_venda_e_ignora_a_compra(tmp_path: Path) -> None:
    """O EA roda venda-apenas: um lado de compra desastroso nao pode
    derrubar o veredito, e um lado de venda ausente nao pode aprova-lo."""
    arq = tmp_path / "features.parquet"
    _df_basico().to_parquet(arq, index=False)   # so' compra, nenhuma venda
    r = analisar_mae(arq, "z_agf_3", horizonte=3, threshold_entrada=1.4,
                     direcao="contrarian", stop_catastrofico_pontos=500,
                     saida=tmp_path / "out", treino_min=0)
    assert r["stats_venda"]["n"] == 0
    assert r["veredito"].startswith("INCONCLUSIVO")


def test_tres_regimes_saem_quebrados_por_lado(tmp_path: Path) -> None:
    """A lacuna da v1.48: os tres regimes so' existiam agregados, e o
    agregado mistura um lado que o EA nem opera."""
    arq = tmp_path / "features.parquet"
    _df_tres_regimes().to_parquet(arq, index=False)
    r = analisar_mae(arq, "z_agf_3", horizonte=3, threshold_entrada=1.4,
                     direcao="contrarian", stop_catastrofico_pontos=50,
                     saida=tmp_path / "out", treino_min=0)
    v = r["stats_venda"]
    assert v["pnl_medio_sem_stop"] == -15.0
    assert v["pnl_medio_stop_close"] == -27.5
    assert v["pnl_medio_stop_continuo"] == -50.0
    # lado vazio devolve o esqueleto completo, sem KeyError
    c = r["stats_compra"]
    assert pd.isna(c["pnl_medio_stop_continuo"])
    assert pd.isna(c["ic95_baixo"])
    assert c["n_afetadas"] == 0


def test_relatorio_traz_o_pre_registro_e_o_veredito(tmp_path: Path) -> None:
    arq = tmp_path / "features.parquet"
    _df_tres_regimes().to_parquet(arq, index=False)
    r = analisar_mae(arq, "z_agf_3", horizonte=3, threshold_entrada=1.4,
                     direcao="contrarian", stop_catastrofico_pontos=50,
                     saida=tmp_path / "out", treino_min=0)
    conteudo = Path(r["relatorio"]).read_text(encoding="utf-8")
    assert "PRE-REGISTRO" in conteudo
    assert "VEREDITO" in conteudo
    assert "-3.0 pts/op" in conteudo
    assert "Os tres regimes POR LADO" in conteudo


def test_semente_fixa_torna_o_bootstrap_reprodutivel(tmp_path: Path) -> None:
    """Duas rodadas identicas precisam dar o MESMO IC -- senao o veredito
    dependeria da sorte da rodada, nao do dado."""
    arq = tmp_path / "features.parquet"
    _df_pareado_favoravel().to_parquet(arq, index=False)
    kwargs = dict(horizonte=3, threshold_entrada=1.4, direcao="contrarian",
                  stop_catastrofico_pontos=50, treino_min=0)
    a = analisar_mae(arq, "z_agf_3", saida=tmp_path / "a", **kwargs)
    b = analisar_mae(arq, "z_agf_3", saida=tmp_path / "b", **kwargs)
    assert a["stats_venda"]["ic95_baixo"] == b["stats_venda"]["ic95_baixo"]
    assert a["veredito"] == b["veredito"]
