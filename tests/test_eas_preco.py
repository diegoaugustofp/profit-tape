"""
EAs de preco (M15) -- research/eas_preco.py.

Ordem de conferencia (skill engenharia, secao 2): o RSI foi conferido A
MAO antes destes testes (o exemplo esta no docstring de `rsi_wilder`).
Os testes abaixo fixam esse exemplo e o resto do funil.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from profittape.research import eas_preco as ep


# ---------------------------------------------------------------------
# RSI: conferido a mao (regra 4)
# ---------------------------------------------------------------------
def test_rsi_wilder_bate_com_a_conta_a_mao() -> None:
    close = pd.Series([10.0, 11.0, 10.5, 11.5, 11.0])
    r = ep.rsi_wilder(close, 2)
    assert np.isnan(r.iloc[0]) and np.isnan(r.iloc[1])
    assert r.iloc[2] == pytest.approx(66.6667, abs=1e-3)
    assert r.iloc[3] == pytest.approx(85.7143, abs=1e-3)
    assert r.iloc[4] == pytest.approx(54.5455, abs=1e-3)


def test_rsi_sma_difere_do_wilder_a_partir_da_segunda_barra() -> None:
    close = pd.Series([10.0, 11.0, 10.5, 11.5, 11.0])
    r = ep.rsi_sma(close, 2)
    # barra 2: mesmas medias da semente -> igual ao Wilder
    assert r.iloc[2] == pytest.approx(66.6667, abs=1e-3)
    # barra 3: g=(0+1)/2, p=(0.5+0)/2 -> 66.667 (Wilder da 85.714)
    assert r.iloc[3] == pytest.approx(66.6667, abs=1e-3)


def test_rsi_extremos_sem_perda_e_sem_ganho() -> None:
    assert ep._rsi_de(1.0, 0.0) == 100.0
    assert ep._rsi_de(0.0, 0.0) == 50.0
    assert ep._rsi_de(0.0, 1.0) == 0.0


def test_mme_semente_sma_confere_a_mao() -> None:
    # n=2, alpha=2/3. semente = media(10, 12) = 11 na barra 1.
    # barra 2: 2/3*14 + 1/3*11 = 13.0
    m = ep.mme_semente_sma(pd.Series([10.0, 12.0, 14.0]), 2)
    assert np.isnan(m.iloc[0])
    assert m.iloc[1] == pytest.approx(11.0)
    assert m.iloc[2] == pytest.approx(13.0)


def test_arredondar_ao_tick_meio_tick_sobe() -> None:
    assert ep.arredondar_ao_tick(162.5) == 165.0
    assert ep.arredondar_ao_tick(162.4) == 160.0
    assert ep.arredondar_ao_tick(1.0) == 5.0      # nunca abaixo de 1 tick


# ---------------------------------------------------------------------
# Dump sintetico: escreve no MESMO formato do ntsl e le de volta
# ---------------------------------------------------------------------
def _dump(tmp_path: Path, barras: list[dict], nome: str = "dump.txt") -> Path:
    linhas = ["PRCVIDA|barras=999|primeira_data=1260901"]
    for b in barras:
        campos = [str(b[c]) for c in ep.CAMPOS]
        linhas.append(ep.PREFIXO + "|".join(campos))
    p = tmp_path / nome
    p.write_text("\n".join(linhas), encoding="utf-8")
    return p


def _barra(data: int, hora: int, cb: int, o: float, h: float, lo: float, c: float,
           rsi: float = 50.0, mme8: float = 0.0, mme80: float = 0.0,
           atr: float = 100.0, tr: float = 100.0) -> dict:
    return {"data": data, "hora": hora, "hora_bolsa": hora, "current_bar": cb,
            "open": o, "high": h, "low": lo, "close": c, "vol_total": 1000,
            "rsi_ntsl": rsi, "mme8_ntsl": mme8, "mme80_ntsl": mme80,
            "atr_ntsl": atr, "tr_ntsl": tr}


def _dia(data: int, cb0: int, n: int = 37, base: float = 140000.0) -> list[dict]:
    """Um pregao de n barras M15 a partir de 09:00, precos constantes."""
    out = []
    h, m = 9, 0
    for i in range(n):
        out.append(_barra(data, h * 100 + m, cb0 + i, base, base + 50, base - 50, base))
        m += 15
        if m == 60:
            h, m = h + 1, 0
    return out


def test_parser_le_o_formato_do_ntsl(tmp_path: Path) -> None:
    barras = _dia(1260901, 1) + _dia(1260902, 38)
    df, meta = ep.carregar_log(_dump(tmp_path, barras))
    assert meta["barras"] == 74 and meta["pregoes"] == 2 and meta["blocos"] == 1
    assert meta["time_com_segundos"] is False
    assert list(df["hhmm"].iloc[:3]) == [900, 915, 930]
    assert str(df["dia"].iloc[0]) == "2026-09-01"


def test_parser_recusa_campo_a_menos(tmp_path: Path) -> None:
    linha = ep.PREFIXO + "|".join(["1260901", "900", "900", "1", "1", "1", "1", "1", "1"])
    p = tmp_path / "ruim.txt"
    p.write_text(linha, encoding="utf-8")
    with pytest.raises(SystemExit, match="formato incompativel"):
        ep.carregar_log(p)


def test_parser_recusa_dump_sobreposto(tmp_path: Path) -> None:
    barras = _dia(1260901, 1) + _dia(1260901, 1)
    with pytest.raises(SystemExit, match="duplicadas"):
        ep.carregar_log(_dump(tmp_path, barras))


def test_parser_pt_br_com_virgula(tmp_path: Path) -> None:
    b = _barra(1260901, 900, 1, "140.000,5", "140.100", "139.900", "140.050,5")
    df, _ = ep.carregar_log(_dump(tmp_path, [b]))
    assert df["open"].iloc[0] == 140000.5 and df["close"].iloc[0] == 140050.5


# ---------------------------------------------------------------------
# Funil da ficha IFR2 (clausulas, uma a uma)
# ---------------------------------------------------------------------
def _cenario(tmp_path: Path) -> pd.DataFrame:
    """
    Dia 1 (cb 1..37): RSI 5 nas barras 09:30 e 09:45 (uma excursao, so'
    a primeira conta), close acima da MME80 -> 1 sinal de COMPRA.
    RSI 95 em 16:45 (fora da janela) -> nao conta. RSI 5 em 09:00 (antes
    de 09:15) -> nao conta.
    Dia 2: RSI 95 em 10:00 com close ABAIXO da MME80 -> 1 sinal de VENDA.
    RSI 5 em 10:30 com close abaixo da MME80 -> regime reprova.
    """
    d1 = _dia(1260901, 1)
    for b in d1:
        b["mme80_ntsl"] = 139000.0    # close 140000 acima -> regime compra
        b["mme8_ntsl"] = 139500.0
    d1[0]["rsi_ntsl"] = 5.0        # 09:00, fora da janela
    d1[2]["rsi_ntsl"] = 5.0        # 09:30 -> SINAL
    d1[3]["rsi_ntsl"] = 5.0        # 09:45 -> mesma excursao
    d1[31]["rsi_ntsl"] = 95.0      # 16:45 -> fora da janela (e regime errado)
    d2 = _dia(1260902, 38)
    for b in d2:
        b["mme80_ntsl"] = 141000.0    # close 140000 abaixo -> regime venda
        b["mme8_ntsl"] = 140500.0
    d2[4]["rsi_ntsl"] = 95.0       # 10:00 -> SINAL de venda
    d2[6]["rsi_ntsl"] = 5.0        # 10:30 -> extremo de compra, regime reprova
    df, _ = ep.carregar_log(_dump(tmp_path, d1 + d2))
    return ep.marcar_ifr2(ep.indicadores(df))


def test_funil_ifr2_clausula_a_clausula(tmp_path: Path) -> None:
    x = _cenario(tmp_path)
    f = ep.contar_clausulas(x).set_index(["lado", "clausula"])["n"]
    assert f[("compra", "extremo")] == 4                  # 09:00, 09:30, 09:45, dia2 10:30
    assert f[("compra", "+excursao (1 sinal por excursao)")] == 3   # 09:00, 09:30, dia2 10:30
    assert f[("compra", "+regime MME80")] == 2            # dia2 10:30 cai
    assert f[("compra", "+janela 09:15-16:30")] == 1      # 09:00 cai
    assert f[("compra", "+t+1 existe e D ok = SINAL")] == 1
    assert f[("venda", "extremo")] == 2
    assert f[("venda", "+regime MME80")] == 1
    assert f[("venda", "+t+1 existe e D ok = SINAL")] == 1


def test_sinal_tem_barreiras_simetricas_em_pontos(tmp_path: Path) -> None:
    x = _cenario(tmp_path)
    c = x[x["sinal_compra"]].iloc[0]
    assert c["hhmm"] == 930
    assert c["D_pts"] == 100.0                       # 1.0 x ATR14=100, ao tick
    assert c["entrada_ref"] == 140000.0              # open de t+1
    assert c["alvo"] == 140100.0 and c["stop"] == 139900.0
    v = x[x["sinal_venda"]].iloc[0]
    assert v["alvo"] == 139900.0 and v["stop"] == 140100.0


def test_ultima_barra_do_dia_nao_gera_sinal_sem_t1(tmp_path: Path) -> None:
    d1 = _dia(1260901, 1, n=20)          # termina 13:45, dentro da janela
    for b in d1:
        b["mme80_ntsl"] = 139000.0
    d1[-1]["rsi_ntsl"] = 5.0
    df, _ = ep.carregar_log(_dump(tmp_path, d1))
    x = ep.marcar_ifr2(ep.indicadores(df))
    assert not x["sinal_compra"].any()
    assert not bool(x["tem_t1"].iloc[-1])


# ---------------------------------------------------------------------
# Ambiguidade do estimador: classifica, NUNCA diz quem bateu
# ---------------------------------------------------------------------
def test_ambiguidade_classifica_as_tres_saidas(tmp_path: Path) -> None:
    d1 = _dia(1260901, 1)
    for b in d1:
        b["mme80_ntsl"] = 139000.0
    # sinal em 09:30 (idx 2), entrada open(09:45)=140000, alvo 140100 / stop 139900
    d1[2]["rsi_ntsl"] = 5.0
    # 10:00 (idx 4): barra contem os DOIS -> ambigua
    d1[4]["high"], d1[4]["low"] = 140150.0, 139850.0
    # segundo sinal em 11:00 (idx 8); 11:30 (idx 10) so' toca o alvo -> resolvida
    d1[8]["rsi_ntsl"] = 5.0
    d1[10]["high"] = 140120.0
    # terceiro sinal em 14:00 (idx 20): resto do dia dentro de +-50 -> por_tempo
    d1[20]["rsi_ntsl"] = 5.0
    df, _ = ep.carregar_log(_dump(tmp_path, d1))
    x = ep.marcar_ifr2(ep.indicadores(df))
    a = ep.ambiguidade(x)
    assert a["n_sinais"] == 3
    assert a["contagem"] == {"resolvida": 1, "ambigua": 1, "por_tempo": 1}
    assert "qual" not in a and "acertou" not in a and "p1" not in a


def test_em_pontos_reporta_custo_maximo(tmp_path: Path) -> None:
    x = _cenario(tmp_path)
    pt = ep.em_pontos(x)
    assert pt["D_pts"]["p50"] == 100.0
    assert pt["D_minimo_para_pagar_custo_a_p1_056_pts"] == pytest.approx(91.7, abs=0.1)
    # p1 que empata 11 pts com D=100: 0,5 + 11/200 = 0,555
    assert pt["p1_que_empata_custo_com_D_mediano"] == pytest.approx(0.555, abs=1e-3)


# ---------------------------------------------------------------------
# Equivalencia: reconhece a variante certa e reprova a errada
# ---------------------------------------------------------------------
def test_equivalencia_reconhece_wilder_e_reprova_sma(tmp_path: Path) -> None:
    rng = np.random.default_rng(7)
    closes = 140000.0 + np.cumsum(rng.normal(0, 60, 400))
    barras = []
    cb, h, m, data = 1, 9, 0, 1260901
    for i, c in enumerate(closes):
        if i and i % 37 == 0:
            data += 1
            h, m = 9, 0
        barras.append(_barra(data, h * 100 + m, cb, c, c + 30, c - 30, c))
        cb += 1
        m += 15
        if m == 60:
            h, m = h + 1, 0
    df, _ = ep.carregar_log(_dump(tmp_path, barras))
    # o "Profit" desta simulacao calcula RSI de Wilder
    df["rsi_ntsl"] = ep.rsi_wilder(df["close"], 2).round(2)
    d = ep.indicadores(df)
    eq = ep.equivalencia(d, tolerancia=0.01)
    assert eq["rsi_ntsl"]["melhor"] == "rsi_wilder" and eq["rsi_ntsl"]["bate"]
    assert eq["rsi_ntsl"]["detalhe"]["rsi_sma"]["dif_max"] > 0.01   # reprova a errada


def test_rodar_escreve_saida(tmp_path: Path) -> None:
    x_path = _dump(tmp_path, _dia(1260901, 1) + _dia(1260902, 38))
    r = ep.rodar(x_path, tmp_path / "saida")
    assert (tmp_path / "saida" / "resumo.json").exists()
    assert (tmp_path / "saida" / "barras_m15.parquet").exists()
    assert r["ambiguidade"]["n_sinais"] == 0
