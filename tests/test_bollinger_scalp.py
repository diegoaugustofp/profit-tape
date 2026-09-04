"""
Scalp de Bollinger (15s): parser, indicadores, equivalencia e regra.

Os numeros esperados foram calculados NO PAPEL antes de virarem
asserts (skill disciplina, regra 4) -- ver a sessao de 2026-09-04.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from profittape.research import bollinger_scalp as bs
from profittape.research.bollinger_scalp import (
    CAMPOS,
    carregar_log,
    contar_clausulas,
    equivalencia,
    indicadores,
    marcar_sinais,
)


# ---------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------
def _linha(dia: str = "1260901", hora: int = 900, bar: int = 1,
           o: float = 140000.0, h: float = 140050.0, low: float = 139950.0,
           c: float = 140020.0, extras: str = "|1200|140030,5|139990,5|55,2|38,1|100") -> str:
    return f"BBSBARRA|{dia}|{hora}|{hora}|{bar}|{o}|{h}|{low}|{c}{extras}"


def _ohlc_curto() -> pd.DataFrame:
    o = [100, 102, 101, 104, 103]
    h = [103, 105, 104, 106, 105]
    low = [99, 101, 100, 102, 101]
    c = [102, 101, 104, 103, 105]
    df = pd.DataFrame(dict(open=o, high=h, low=low, close=c), dtype=float)
    df["bloco"] = 1
    return df


@pytest.fixture
def periodos_curtos(monkeypatch: pytest.MonkeyPatch) -> None:
    """Periodos reduzidos para a conta caber no papel. Os asserts sao
    sobre a FORMULA; o periodo e' so' o tamanho da janela."""
    monkeypatch.setattr(bs, "BB_PERIODO", 3)
    monkeypatch.setattr(bs, "EST_PERIODO", 3)
    monkeypatch.setattr(bs, "EST_MEDIA", 2)
    monkeypatch.setattr(bs, "ATR_PERIODO", 2)


# ---------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------
def test_ordem_dos_campos_esta_congelada() -> None:
    assert len(CAMPOS) == 14
    assert CAMPOS[3] == "current_bar"
    assert CAMPOS[-5:] == ["bb_sup_ntsl", "bb_inf_ntsl", "est_ntsl", "atr_ntsl", "tr_ntsl"]


def test_parser_le_ptbr_e_deriva_segundos_de_hhmm(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """`Time` em HHMM: 4 barras no mesmo minuto viram 0/15/30/45 s."""
    arq = tmp_path / "log.txt"
    linhas = [_linha(hora=900 + i // 4, bar=i + 1) for i in range(8)]
    arq.write_text("\n".join(linhas), encoding="utf-8")
    df, meta = carregar_log(arq)
    assert meta["barras"] == 8
    assert meta["time_com_segundos"] is False
    assert meta["blocos"] == 1
    assert df["dia"].iloc[0] == dt.date(2026, 9, 1)
    assert list(df["ts"].dt.second[:4]) == [0, 15, 30, 45]
    assert df["bb_sup_ntsl"].iloc[0] == 140030.5       # virgula decimal
    assert df["vol_total"].iloc[0] == 1200.0


def test_parser_time_com_segundos(tmp_path) -> None:  # type: ignore[no-untyped-def]
    arq = tmp_path / "log.txt"
    arq.write_text("\n".join(_linha(hora=90000 + 15 * i, bar=i + 1) for i in range(3)),
                   encoding="utf-8")
    df, meta = carregar_log(arq)
    assert meta["time_com_segundos"] is True
    assert list(df["ts"].dt.second) == [0, 15, 30]


def test_parser_separa_blocos_quando_current_bar_salta(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Dois dumps nao contiguos nao podem ser vizinhos no rolling."""
    arq = tmp_path / "log.txt"
    linhas = [_linha(hora=900, bar=1), _linha(hora=900, bar=2),
              _linha(hora=1400, bar=900), _linha(hora=1400, bar=901)]
    arq.write_text("\n".join(linhas), encoding="utf-8")
    df, meta = carregar_log(arq)
    assert meta["blocos"] == 2
    assert list(df["bloco"]) == [1, 1, 2, 2]


def test_parser_recusa_duplicata_e_minuto_com_mais_de_4_barras(tmp_path) -> None:  # type: ignore[no-untyped-def]
    arq = tmp_path / "log.txt"
    arq.write_text("\n".join([_linha(bar=1), _linha(bar=1)]), encoding="utf-8")
    with pytest.raises(SystemExit, match="duplicadas"):
        carregar_log(arq)
    arq.write_text("\n".join(_linha(hora=900, bar=i + 1) for i in range(5)),
                   encoding="utf-8")
    with pytest.raises(SystemExit, match="mais de 4 barras"):
        carregar_log(arq)


def test_parser_recusa_formato_de_outro_indicador(tmp_path) -> None:  # type: ignore[no-untyped-def]
    arq = tmp_path / "log.txt"
    arq.write_text("BBSBARRA|1260901|900|900|1|1|2|3", encoding="utf-8")
    with pytest.raises(SystemExit, match="formato incompativel"):
        carregar_log(arq)
    arq.write_text("BBSVIDA|barras=10", encoding="utf-8")
    with pytest.raises(SystemExit, match="nenhuma barra passou"):
        carregar_log(arq)


# ---------------------------------------------------------------------
# indicadores -- valores do papel
# ---------------------------------------------------------------------
def test_bollinger_a_mao_nas_duas_variantes_de_desvio(periodos_curtos: None) -> None:
    """closes 102,101,104: sma=102,333; dp0=1,2472; dp1=1,5275."""
    d = indicadores(_ohlc_curto())
    assert d["bb_sup_ddof0"][2] == pytest.approx(102.333 + 0.38 * 1.2472, abs=1e-3)
    assert d["bb_sup_ddof1"][2] == pytest.approx(102.333 + 0.38 * 1.5275, abs=1e-3)
    assert d["bb_inf_ddof0"][2] == pytest.approx(102.333 - 0.38 * 1.2472, abs=1e-3)


def test_estocastico_a_mao(periodos_curtos: None) -> None:
    """%K rapido idx2 = (104-99)/(105-99) = 83,33; idx3 = 50; idx4 = 83,33.
    %K lento(2) idx3 = idx4 = 66,67; %D idx4 = 66,67."""
    d = indicadores(_ohlc_curto())
    assert list(d["k_rapido"][2:].round(3)) == [83.333, 50.0, 83.333]
    assert d["k_lento"][3] == pytest.approx(66.667, abs=1e-3)
    assert d["d_lento"][4] == pytest.approx(66.667, abs=1e-3)
    assert np.isnan(d["k_lento"][2])


def test_true_range_e_gap(periodos_curtos: None) -> None:
    d = indicadores(_ohlc_curto())
    assert list(d["tr"]) == [4.0] * 5
    assert d["atr_sma"][1] == 4.0
    com_gap = _ohlc_curto()
    com_gap.loc[3, ["open", "high", "low", "close"]] = [111, 112, 110, 111]
    assert indicadores(com_gap)["tr"][3] == 8.0       # |112 - close_ant 104|


def test_bollinger_e_o_mesmo_que_zscore_com_a_barra_atual() -> None:
    """A identidade que justifica tratar a banda como limiar de z."""
    rng = np.random.default_rng(1)
    close = 140000 + 5 * np.cumsum(rng.integers(-3, 4, 500))
    df = pd.DataFrame(dict(open=close, high=close + 5, low=close - 5, close=close),
                      dtype=float)
    df["bloco"] = 1
    d = indicadores(df)
    z = (d["close"] - d["sma"]) / d["dp1"]
    m = z.notna()
    assert ((d.loc[m, "close"] > d.loc[m, "bb_sup_ddof1"]) == (z[m] > bs.BB_DESVIO)).all()


# ---------------------------------------------------------------------
# equivalencia -- e o verificador que precisa REPROVAR (7.3)
# ---------------------------------------------------------------------
def _dump_sintetico(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(3)
    close = 140000 + 5 * np.cumsum(rng.integers(-3, 4, n))
    df = pd.DataFrame(dict(
        open=close + 5 * rng.integers(-1, 2, n),
        high=close + 5 * rng.integers(0, 4, n),
        low=close - 5 * rng.integers(0, 4, n),
        close=close), dtype=float)
    df["bloco"] = 1
    return indicadores(df)


def test_equivalencia_identifica_a_variante_certa() -> None:
    d = _dump_sintetico()
    d["bb_sup_ntsl"] = d["bb_sup_ddof0"]
    d["bb_inf_ntsl"] = d["bb_inf_ddof0"]
    d["est_ntsl"] = d["d_lento"]
    d["atr_ntsl"] = d["atr_wilder"]
    d["tr_ntsl"] = d["tr"]
    eq = equivalencia(d)
    assert eq["bb_sup_ntsl"]["melhor"] == "bb_sup_ddof0" and eq["bb_sup_ntsl"]["bate"]
    assert eq["est_ntsl"]["melhor"] == "d_lento" and eq["est_ntsl"]["bate"]
    assert eq["atr_ntsl"]["melhor"] == "atr_wilder" and eq["atr_ntsl"]["bate"]


def test_equivalencia_REPROVA_formula_diferente() -> None:
    """Um verificador que nao consegue reprovar nao verifica nada."""
    d = _dump_sintetico()
    d["bb_sup_ntsl"] = d["bb_sup_ddof0"]
    d["bb_inf_ntsl"] = d["bb_inf_ddof0"]
    d["est_ntsl"] = d["k_lento"] + 3.0          # desloca 3 pontos: nao e' ruido
    d["atr_ntsl"] = d["atr_sma"]
    d["tr_ntsl"] = d["high"] - d["low"]         # H-L ignora o gap
    eq = equivalencia(d)
    assert eq["est_ntsl"]["bate"] is False
    assert eq["tr_ntsl"]["bate"] is False
    assert eq["bb_sup_ntsl"]["bate"] is True    # o resto continua batendo


# ---------------------------------------------------------------------
# regra de entrada -- sequencia construida e conferida no papel
# ---------------------------------------------------------------------
def _sequencia() -> pd.DataFrame:
    #        t0    t1     t2     t3     t4     t5
    o = [101, 106, 103, 105, 101, 102]
    c = [103, 104, 106, 104, 103, 101]
    h = [104, 107, 107, 106, 104, 103]
    low = [100, 103, 102, 103.5, 100, 100]
    est = [50, 30, 15, 60, 10, 90]
    df = pd.DataFrame(dict(open=o, high=h, low=low, close=c), dtype=float)
    df["bb_sup_ntsl"] = 100.0
    df["bb_inf_ntsl"] = 90.0
    df["est_ntsl"] = est
    df["dia"] = dt.date(2026, 9, 1)
    df["bloco"] = 1
    return df


def test_compra_dispara_na_barra_certa_com_limite_na_maxima_da_correcao() -> None:
    """t1 vermelha acima; t2 branca acima com est=15<20 -> sinal em t3,
    limitada em high(t1)=107; open(t3)=105<=107 -> executa na abertura.
    t5 tambem: t3 vermelha, t4 branca, est(t4)=10."""
    x = marcar_sinais(_sequencia())
    assert list(x["sinal_compra"]) == [False, False, False, True, False, True]
    assert x["preco_limite"][3] == 107.0
    assert x["preco_limite"][5] == 106.0
    assert x["executou"][3] and x["tipo_execucao"][3] == "abertura"
    assert not x["sinal_venda"].any()


def test_estocastico_bloqueia_a_compra() -> None:
    df = _sequencia()
    df.loc[2, "est_ntsl"] = 25.0                 # nao esta' sobrevendido
    x = marcar_sinais(df)
    assert not x["sinal_compra"][3]
    assert x["c_compra_t1"][3] and x["c_compra_t2"][3] and not x["c_compra_est"][3]


def test_venda_e_o_espelho_exato() -> None:
    """Espelhar preco em torno de 95 e o estocastico em torno de 50 tem
    que produzir a venda nas MESMAS barras, com limite na minima."""
    df = _sequencia()
    for col in ("open", "high", "low", "close"):
        df[col] = 190.0 - df[col]
    df["high"], df["low"] = df["low"].copy(), df["high"].copy()
    df["est_ntsl"] = 100.0 - df["est_ntsl"]
    x = marcar_sinais(df)
    assert list(x["sinal_venda"]) == [False, False, False, True, False, True]
    assert x["preco_limite"][3] == 190.0 - 107.0
    assert x["executou"][3] and x["tipo_execucao"][3] == "abertura"
    assert not x["sinal_compra"].any()


def test_execucao_no_recuo_e_nao_tocada() -> None:
    df = _sequencia()
    df.loc[3, ["open", "low"]] = [108.0, 106.5]   # abre acima do limite, recua ate' ele
    x = marcar_sinais(df)
    assert x["executou"][3] and x["tipo_execucao"][3] == "recuo"
    df.loc[3, ["open", "low"]] = [108.0, 107.5]   # nunca chega em 107
    x = marcar_sinais(df)
    assert x["sinal_compra"][3] and not x["executou"][3]


def test_doji_nao_forma_sequencia_e_dia_nao_atravessa() -> None:
    df = _sequencia()
    df.loc[1, "close"] = df.loc[1, "open"]        # t1 vira doji
    assert not marcar_sinais(df)["sinal_compra"][3]
    df = _sequencia()
    df.loc[:1, "dia"] = dt.date(2026, 8, 31)      # t0,t1 em outro pregao
    assert not marcar_sinais(df)["sinal_compra"][3]
    assert marcar_sinais(df)["sinal_compra"][5]


def test_funil_conta_cada_clausula() -> None:
    x = marcar_sinais(_sequencia())
    f = contar_clausulas(x)
    compra = f[f["lado"] == "compra"].set_index("clausula")["n"]
    assert compra["barras"] == 6
    assert compra["+ estocastico(t-1) extremo"] == 2
    assert compra["+ limitada tocada em t"] == 2
    assert compra["   ... executada na abertura"] == 2
    assert compra["   ... executada no recuo"] == 0
