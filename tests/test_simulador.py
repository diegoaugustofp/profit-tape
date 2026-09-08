"""Simulador de replay (Fase 1 DeepScalper) -- numeros conferidos no papel."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import pytest
import structlog

from profittape.ea.config import SinalConfig
from profittape.research.simulador import (
    COLUNAS_FUTURAS,
    Obs,
    Ordem,
    Regras,
    Simulador,
    conferir_com_replay,
    politica_ea,
    preparar,
    verificar_lookahead,
)

_NS = 10**9
_T0 = int(pd.Timestamp("2026-09-01 12:00:00", tz="UTC").timestamp()) * _NS


@pytest.fixture(autouse=True)
def _silencia_structlog() -> None:
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.ERROR))


def _dia(closes: list[float], sinal: list[int] | None = None, dia_offset: int = 0,
         bar0: int = 0) -> pd.DataFrame:
    n = len(closes)
    base = _T0 + dia_offset * 86400 * _NS
    return pd.DataFrame({
        "bar_id": range(bar0, bar0 + n),
        "ts_open": [base + i * 60 * _NS for i in range(n)],
        "ts_close": [base + i * 60 * _NS + 30 * _NS for i in range(n)],
        "close": closes,
        "sinal": sinal if sinal is not None else [0] * n,
    })


def _pol_sinal(o: Obs) -> Ordem | None:
    """+1 no sinal 1 (horizonte 2), -1 no sinal -1 (horizonte 5)."""
    s = int(o.barra["sinal"])
    if o.pos == 0 and s == 1:
        return Ordem(+1, 2)
    if o.pos == 0 and s == -1:
        return Ordem(-1, 5)
    return None


def test_pnl_de_cinco_barras_a_mao() -> None:
    """closes 100000/100020/99990/100050/100030, custo 11:
    compra em 0 a 100000, saida por tempo em 2 a 99990 -> -10 - 11 = -21;
    venda em 3 a 100050, encerramento em 4 a 100030 -> +20 - 11 = +9.
    Total -12."""
    b = preparar(_dia([100000., 100020., 99990., 100050., 100030.], [1, 0, 0, -1, 0]))
    r = Simulador(b, Regras(custo_pontos=11.0)).rodar(_pol_sinal)
    ops = r["operacoes"]
    assert list(ops["pnl_liquido"]) == [-21.0, 9.0]
    assert list(ops["idx_entrada"]) == [0, 3] and list(ops["idx_saida"]) == [2, 4]
    assert list(ops["preco_entrada"]) == [100000.0, 100050.0]
    assert ops["motivo"].iloc[0].startswith("saida por tempo: 2")
    assert ops["motivo"].iloc[1] == "encerramento do dia"
    assert r["pnl_total"] == -12.0
    assert r["por_dia"].iloc[0]["pnl_dia"] == -12.0


def test_stop_catastrofico_no_close() -> None:
    """compra a 100000; proxima barra fecha 99400 -> 600 contra >= 500."""
    b = preparar(_dia([100000., 99400., 99990., 100050., 100030.], [1, 0, 0, 0, 0]))
    ops = Simulador(b, Regras()).rodar(_pol_sinal)["operacoes"]
    assert len(ops) == 1
    assert ops.iloc[0]["pnl_liquido"] == -611.0
    assert ops.iloc[0]["motivo"].startswith("STOP CATASTROFICO")


def test_circuit_breaker_tres_perdas() -> None:
    """closes caindo 50 por barra, compra com horizonte 1 sempre que zerado:
    -61, -61, e a terceira abre na ultima barra e encerra a -11 -> bloqueado."""
    b = preparar(_dia([100100., 100050., 100000., 99950., 99900.]))
    sempre = lambda o: Ordem(+1, 1) if o.pos == 0 else None  # noqa: E731
    r = Simulador(b, Regras(circuit_breaker=True)).rodar(sempre)
    assert list(r["operacoes"]["pnl_liquido"]) == [-61.0, -61.0, -11.0]
    assert bool(r["por_dia"].iloc[0]["bloqueado"]) is True
    # sem breaker o resultado e' o mesmo aqui (nao ha' barra depois da 3a
    # perda), mas o flag continua sendo calculado
    r2 = Simulador(b, Regras(circuit_breaker=False)).rodar(sempre)
    assert len(r2["operacoes"]) == 3


def test_sinal_contrario_zera_e_nao_inverte() -> None:
    """Com posicao comprada, ordem -1 = ZERAR (igual a decidir()); so' abre
    venda na barra seguinte."""
    b = preparar(_dia([100000., 100010., 100020., 100030.], [1, -1, -1, 0]))
    pol = lambda o: Ordem(-1, 9) if int(o.barra["sinal"]) == -1 else (  # noqa: E731
        Ordem(+1, 9) if (o.pos == 0 and int(o.barra["sinal"]) == 1) else None)
    ops = Simulador(b, Regras()).rodar(pol)["operacoes"]
    assert list(ops["lado"]) == [1, -1]
    assert ops.iloc[0]["motivo"] == "sinal virou contra a posicao"
    assert list(ops["idx_entrada"]) == [0, 2]   # a venda so' abre na barra 2


def test_dias_sao_independentes_e_posicao_nao_atravessa() -> None:
    d1 = _dia([100000., 100010., 100020.], [0, 0, 1])
    d2 = _dia([100100., 100200., 100300.], [0, 0, 0], dia_offset=1, bar0=3)
    b = preparar(pd.concat([d1, d2], ignore_index=True))
    ops = Simulador(b, Regras()).rodar(_pol_sinal)["operacoes"]
    assert len(ops) == 1 and ops.iloc[0]["motivo"] == "encerramento do dia"
    assert ops.iloc[0]["pnl_liquido"] == -11.0      # abriu e fechou na mesma barra
    assert list(b["dia"].unique()) == ["2026-09-01", "2026-09-02"]


def test_colunas_futuras_nao_chegam_na_politica() -> None:
    b = _dia([1., 2., 3.])
    for c in COLUNAS_FUTURAS:
        b[c] = 1
    vistas: set[str] = set()

    def espiona(o: Obs) -> None:
        vistas.update(o.barra.index)

    Simulador(preparar(b), Regras()).rodar(espiona)
    assert not (vistas & set(COLUNAS_FUTURAS))
    assert {"close", "sinal", "bar_id"} <= vistas


def test_politica_ea_reproduz_decidir() -> None:
    s = SinalConfig(feature="z_agf_3", horizonte=3, agent_id=3,
                    threshold_entrada=1.4, direcao="contrarian", lado_permitido="ambos")
    b = _dia([100000., 100010., 100020., 100030., 100040., 100050.])
    b["z_agf_3"] = [np.nan, 1.5, 0.0, 0.0, 0.0, -2.0]   # NaN aquece; 1.5 vende; -2 compra
    ops = Simulador(preparar(b), Regras()).rodar(politica_ea([s]))["operacoes"]
    # vende em 1 a 100010, sai por tempo em 4 a 100040: -30 - 11 = -41
    # compra em 5 a 100050, encerra na mesma barra: -11
    assert list(ops["lado"]) == [-1, 1]
    assert list(ops["pnl_liquido"]) == [-41.0, -11.0]
    assert list(ops["idx_entrada"]) == [1, 5]


def test_z_por_dia_zera_a_janela_a_cada_dia() -> None:
    """Com z continuo o segundo dia herda a janela; com z por dia as
    primeiras barras do dia 2 voltam a ser NaN (min_periods = janela//2)."""
    rng = np.random.default_rng(0)
    d1 = _dia(list(100000. + np.arange(30)))
    d2 = _dia(list(100000. + np.arange(30)), dia_offset=1, bar0=30)
    b = pd.concat([d1, d2], ignore_index=True)
    b["agf_3"] = rng.normal(size=60)
    from profittape.features import normalize
    b["z_agf_3"] = normalize.zscore_rolante(b["agf_3"], 10)
    cont = preparar(b)
    por_dia = preparar(b, z_por_dia=["agf_3"], janela_z=10)
    assert not np.isnan(cont.loc[31, "z_agf_3"])          # continuo: dia 2 ja' tem z
    assert np.isnan(por_dia.loc[31, "z_agf_3"])           # por dia: aquecendo de novo
    assert por_dia.loc[:29, "z_agf_3"].equals(cont.loc[:29, "z_agf_3"])  # dia 1 igual


def _passeio(n: int, seed: int = 3) -> pd.DataFrame:
    closes = 100000. + np.cumsum(np.random.default_rng(seed).choice([-10., 10.], n))
    b = _dia(list(closes))
    b["label"] = np.random.default_rng(1).choice([-1, 0, 1], n)
    return preparar(b)


def test_verificador_aprova_politica_causal() -> None:
    honesta = lambda df: (lambda o: Ordem(+1, 1) if (o.pos == 0 and o.idx % 3 == 0)  # noqa: E731
                          else None)
    r = verificar_lookahead(_passeio(60), honesta)
    assert r["ok"] and r["decisoes_no_inteiro"] > 0


def test_verificador_reprova_quem_le_a_proxima_barra() -> None:
    """O caso que DEVE reprovar (disciplina 7.3)."""
    def trapaceira(df: pd.DataFrame):  # type: ignore[no-untyped-def]
        def p(o: Obs) -> Ordem | None:
            if o.pos != 0 or o.idx + 1 >= len(df):
                return None
            return Ordem(+1, 1) if df.iloc[o.idx + 1]["close"] > o.close else Ordem(-1, 1)
        return p
    r = verificar_lookahead(_passeio(60), trapaceira)
    assert not r["ok"] and r["divergencias"]


def test_verificador_nao_deixa_ler_label() -> None:
    le_label = lambda df: (lambda o: Ordem(int(o.barra["label"]), 1))  # noqa: E731
    with pytest.raises(KeyError):
        verificar_lookahead(_passeio(30), le_label)


def test_conferencia_casa_por_dia_barra_lado() -> None:
    sim = pd.DataFrame({"dia": ["d1", "d1", "d2"], "seq_no_dia": [1, 2, 1],
                        "lado": [1, -1, 1], "preco_entrada": [1., 1., 1.],
                        "preco_saida": [1., 1., 1.], "idx_entrada": [3, 10, 5],
                        "idx_saida": [6, 13, 8], "pnl_liquido": [9.0, -21.0, 4.0],
                        "motivo": ["t", "t", "t"]})
    ea = pd.DataFrame({"dia": ["d1", "d1", "d2"], "seq_no_dia": [1, 2, 1],
                       "lado": [1, -1, -1], "preco_entrada": [1., 1., 1.],
                       "preco_saida": [1., 1., 1.], "bar_id_entrada": [3, 10, 5],
                       "bar_id_saida": [6, 13, 8], "pnl_liquido": [9.0, -20.0, 4.0],
                       "motivo": ["t", "t", "t"]})
    c = conferir_com_replay(sim, ea)
    assert c["casadas"] == 2 and c["so_sim"] == 1 and c["so_ea"] == 1
    assert c["casadas_fora_da_tolerancia"] == 1 and c["max_dif_pnl_casadas"] == 1.0
    assert c["pnl_sim"] == -8.0 and c["pnl_ea"] == -7.0


def test_balde_pulado_conta_como_barra_na_saida_por_tempo() -> None:
    """bar_id 0,1,3,4 (balde 2 pulado por trade gigante): compra no 0 com
    horizonte 3 sai no balde 3 -- que e' a 3a LINHA, nao a 4a. Igual ao EA,
    cujo relogio e' cum_total // volume_barra."""
    b = _dia([100000., 100010., 100020., 100030.], [1, 0, 0, 0])
    b["bar_id"] = [0, 1, 3, 4]
    pol = lambda o: Ordem(+1, 3) if (o.pos == 0 and int(o.barra["sinal"]) == 1) else None  # noqa: E731
    ops = Simulador(preparar(b), Regras()).rodar(pol)["operacoes"]
    assert list(ops["idx_saida"]) == [3] and ops.iloc[0]["preco_saida"] == 100020.0
    assert ops.iloc[0]["pnl_liquido"] == 20.0 - 11.0
