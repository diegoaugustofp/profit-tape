
"""research/eas_preco_teste.py -- o teste da ficha IFR2 congelada."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from profittape.research import eas_preco as ep
from profittape.research import eas_preco_teste as et
from tests.test_eas_preco import _barra, _dia, _dump


def test_wilson_conferido_a_mao() -> None:
    lo, hi = et.wilson(7, 10)
    assert lo == pytest.approx(0.3968, abs=1e-4)
    assert hi == pytest.approx(0.8922, abs=1e-4)
    import math
    assert all(math.isnan(v) for v in et.wilson(0, 0))


def test_veredito_segue_o_criterio_da_ficha() -> None:
    assert et.veredito(0.56) == "FAVORAVEL"
    assert et.veredito(0.56, ic_inferior=0.49) == "INCONCLUSIVO"   # IC tem que excluir 0,50
    assert et.veredito(0.56, ic_inferior=0.51) == "FAVORAVEL"
    assert et.veredito(0.50) == "CONTRA"
    assert et.veredito(0.53) == "INCONCLUSIVO"
    assert et.veredito(float("nan")) == "sem amostra"


def test_hash_da_ficha_muda_se_um_parametro_mudar(monkeypatch: pytest.MonkeyPatch) -> None:
    h0 = et.hash_ficha()
    monkeypatch.setitem(et.PARAMETROS_FICHA, "K_ATR", 0.75)
    assert et.hash_ficha() != h0


def _cenario_teste(tmp_path: Path, data: int = 1250901) -> Path:
    """Um pregao de 2025 com 3 sinais de compra: um vence, um perde, um
    ambiguo. Barras a +-50, abaixo das barreiras a +-100 (K = 1)."""
    d1 = _dia(data, 1)
    for b in d1:
        b["mme80_ntsl"] = 139000.0
    d1[2]["rsi_ntsl"] = 5.0          # sinal 09:30 -> entrada 140000, alvo 140100, stop 139900
    d1[4]["high"] = 140120.0         # 10:00 toca so' o alvo -> +1
    d1[8]["rsi_ntsl"] = 5.0          # sinal 11:00
    d1[10]["low"] = 139880.0         # 11:30 toca so' o stop -> -1
    d1[14]["rsi_ntsl"] = 5.0         # sinal 12:30
    d1[16]["high"], d1[16]["low"] = 140150.0, 139850.0   # 13:00 os dois -> ambigua
    return _dump(tmp_path, d1)


def test_resolver_sinais_classifica_e_da_o_resultado(tmp_path: Path) -> None:
    df, _ = ep.carregar_log(_cenario_teste(tmp_path))
    x = ep.marcar_ifr2(ep.indicadores(df))
    r = et.resolver_sinais(x)
    assert list(r["classe"]) == ["resolvida", "resolvida", "ambigua"]
    assert list(r["resultado"]) == [1.0, -1.0, 0.0]
    assert list(r["pnl_bruto_pts"].iloc[:2]) == [100.0, -100.0]
    assert list(r["barras"]) == [2, 2, 2]


def test_venda_espelha_o_favoravel(tmp_path: Path) -> None:
    d1 = _dia(1250901, 1)
    for b in d1:
        b["mme80_ntsl"] = 141000.0
    d1[2]["rsi_ntsl"] = 95.0         # venda: alvo 139900, stop 140100
    d1[4]["low"] = 139880.0          # toca o alvo da venda -> +1
    df, _ = ep.carregar_log(_dump(tmp_path, d1))
    r = et.resolver_sinais(ep.marcar_ifr2(ep.indicadores(df)))
    assert r["lado"].iloc[0] == "venda" and r["resultado"].iloc[0] == 1.0
    assert bool(r["a_favor_mme80"].iloc[0]) is True


def test_placar_primario_e_estratos_reportados(tmp_path: Path) -> None:
    df, _ = ep.carregar_log(_cenario_teste(tmp_path))
    r = et.resolver_sinais(ep.marcar_ifr2(ep.indicadores(df)))
    pl = et.placar(r)
    pr = pl["primario"]
    assert pr["n_sinais"] == 3 and pr["n_resolvidas"] == 2 and pr["n_ambiguas"] == 1
    assert pr["p1"] == 0.5 and pr["veredito"] == "CONTRA"
    assert pr["pnl_bruto_pts_medio"] == 0.0 and pr["pnl_liquido_pts_medio"] == -11.0
    assert "veredito" not in pl["estratos_reportados"]["a_favor_mme80"]
    assert pl["estratos_reportados"]["contra_mme80"]["n_resolvidas"] == 0
    assert pl["ambiguas_para_conferir_no_tape"] == 1


def test_recusa_dia_fora_da_amostra(tmp_path: Path) -> None:
    dump = _cenario_teste(tmp_path, data=1260901)      # 2026 num pedido de `teste`
    with pytest.raises(SystemExit, match="FORA da amostra 'teste'"):
        et.rodar(dump, tmp_path / "s", "teste")
    with pytest.raises(SystemExit, match="FORA da amostra 'replicacao'"):
        et.rodar(dump, tmp_path / "s", "replicacao")   # 01/09/2026 e' depuracao


def test_amostra_desconhecida(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="nao existe"):
        et.rodar(_cenario_teste(tmp_path), tmp_path / "s", "tudo")


def test_teste_e_uma_rodada_so(tmp_path: Path) -> None:
    dump = _cenario_teste(tmp_path)
    r = et.rodar(dump, tmp_path / "s", "teste")
    assert r["arquivo"].exists() and (tmp_path / "s" / "sinais_ifr2_teste.csv").exists()
    with pytest.raises(SystemExit, match="UMA"):
        et.rodar(dump, tmp_path / "s", "teste")
    r2 = et.rodar(dump, tmp_path / "s", "teste", forcar_motivo="bug X corrigido")
    assert r2["carimbo"]["forcado_motivo"] == "bug X corrigido"
    assert r2["carimbo"]["hash_ficha"] == et.hash_ficha()


def test_depuracao_e_replicacao_podem_repetir(tmp_path: Path) -> None:
    dump = _cenario_teste(tmp_path, data=1260901)
    et.rodar(dump, tmp_path / "s", "depuracao")
    et.rodar(dump, tmp_path / "s", "depuracao")          # sem lock: nao e' o teste


def test_barra_fixture_continua_igual() -> None:
    # protege o compartilhamento das fixtures com test_eas_preco
    b = _barra(1250901, 900, 1, 1.0, 2.0, 0.5, 1.5)
    assert set(b) == set(ep.CAMPOS)


def test_trial_por_ficha_e_z_deflacionado() -> None:
    assert et.FICHAS["ifr2"]["TRIAL"] == 2 and et.FICHAS["orb"]["TRIAL"] == 1
    assert et.z_ic(1) == pytest.approx(et.Z95, abs=1e-6)
    assert et.z_ic(2) == pytest.approx(2.2414, abs=1e-4)
    assert et.hash_ficha("ifr2") != et.hash_ficha("orb")


def test_orb_resolve_e_reporta_zeragem(tmp_path: Path) -> None:
    from tests.test_eas_preco import _dia_orb
    # dia 1: compra rompe 10:00 (entrada 140105, D=200), alvo 140305 em 10:30 -> +1
    d1 = _dia_orb(1250901, 1, 139000.0, **{"4": {"high": 140110.0}, "6": {"high": 140310.0}})
    # dia 2: venda rompe 10:00 (entrada 139895), nada mais -> por tempo;
    # close final 139990 -> zeragem = (139990 - 139895) * -1 = -95
    d2 = _dia_orb(1250902, 38, 141000.0, **{"4": {"low": 139890.0}})
    for b in d2[5:]:
        b["close"] = 139990.0
    df, _ = ep.carregar_log(_dump(tmp_path, d1 + d2))
    r = et.resolver_orb(ep.indicadores(df))
    assert list(r["classe"]) == ["resolvida", "por_tempo"]
    assert r["resultado"].iloc[0] == 1.0 and r["pnl_bruto_pts"].iloc[0] == 200.0
    assert r["pnl_zeragem_pts"].iloc[1] == pytest.approx(-95.0)
    pl = et.placar(r, "orb")
    assert pl["primario"]["n_resolvidas"] == 1 and pl["primario"]["n_por_tempo"] == 1
    assert pl["primario"]["pnl_zeragem_por_tempo_pts_medio"] == -95.0
    assert pl["primario"]["ic_confianca"] == 0.95


def test_rodar_orb_usa_arquivo_por_ficha(tmp_path: Path) -> None:
    from tests.test_eas_preco import _dia_orb
    d1 = _dia_orb(1250901, 1, 139000.0, **{"4": {"high": 140110.0}})
    dump = _dump(tmp_path, d1)
    r = et.rodar(dump, tmp_path / "s", "teste", ficha="orb")
    assert r["arquivo"].name == "resultado_orb_teste.json"
    assert r["carimbo"]["parametros"]["TRIAL"] == 1
    with pytest.raises(SystemExit, match="UMA"):
        et.rodar(dump, tmp_path / "s", "teste", ficha="orb")
    et.rodar(dump, tmp_path / "s", "teste", ficha="ifr2")      # outra ficha, outro arquivo


def test_historico_2015_22_e_amostra_valida_e_combinar_soma(tmp_path: Path) -> None:
    from tests.test_eas_preco import _dia_orb
    # 2021: compra resolve a favor; 2025 (teste): compra resolve contra
    d21 = _dia_orb(1210301, 1, 139000.0, **{"4": {"high": 140110.0}, "6": {"high": 140310.0}})
    d25 = _dia_orb(1250901, 38, 139000.0, **{"4": {"high": 140110.0}, "6": {"low": 139900.0}})
    s = tmp_path / "s"
    et.rodar(_dump(tmp_path, d21, "h.txt"), s, "historico_2015_22", ficha="orb")
    et.rodar(_dump(tmp_path, d25, "t.txt"), s, "teste", ficha="orb")
    with pytest.raises(SystemExit, match="FORA da amostra 'historico_2015_22'"):
        et.rodar(_dump(tmp_path, d25, "x.txt"), s, "historico_2015_22", ficha="orb")
    pl = et.combinar(s, "orb")
    assert pl["amostras"] == ["teste", "historico_2015_22"]
    assert pl["primario"]["n_resolvidas"] == 2 and pl["primario"]["p1"] == 0.5
    assert set(pl["por_ano_reportado"]) == {"2021", "2025"}
    assert pl["por_ano_reportado"]["2021"]["p1"] == 1.0
    assert (s / "resultado_orb_COMBINADO.json").exists()


def test_combinar_recusa_hash_diferente(tmp_path: Path) -> None:
    import json

    from tests.test_eas_preco import _dia_orb
    d = _dia_orb(1250901, 1, 139000.0, **{"4": {"high": 140110.0}})
    s = tmp_path / "s"
    et.rodar(_dump(tmp_path, d, "t.txt"), s, "teste", ficha="orb")
    # forja uma replicacao com outro hash
    (s / "sinais_orb_replicacao.csv").write_text(
        (s / "sinais_orb_teste.csv").read_text(encoding="utf-8"), encoding="utf-8")
    (s / "resultado_orb_replicacao.json").write_text(
        json.dumps({"carimbo": {"hash_ficha": "outro"}}), encoding="utf-8")
    with pytest.raises(SystemExit, match="hashes de ficha diferentes"):
        et.combinar(s, "orb")


def test_123_resolve_sequencial_e_ignora_sinal_com_posicao_aberta(tmp_path: Path) -> None:
    from tests.test_eas_preco import _dia_123
    d = _dia_123(1250901, 1)
    # sinal A em t=idx4: padrao idx2-4, gatilho idx5; alvo 140315 -> resolve em idx 8
    d[2]["low"], d[3]["low"] = 139900.0, 139800.0
    d[4].update({"low": 139900.0, "high": 140050.0})
    d[5]["high"] = 140060.0
    # sinal B em t=idx6 (padrao idx4-6: low4=139900 > low5? montar low5=139850, low6=139900)
    d[5]["low"], d[6]["low"] = 139850.0, 139900.0
    d[6]["high"] = 140050.0
    d[7]["high"] = 140060.0          # gatilho de B em idx7, com A ainda aberta -> ignorado
    d[8]["high"] = 140320.0          # A resolve a favor em idx8
    df, _ = ep.carregar_log(_dump(tmp_path, d))
    r = et.resolver_123(ep.indicadores(df))
    assert list(r["classe"]) == ["resolvida", "ignorado_posicao"]
    assert r["resultado"].iloc[0] == 1.0 and r["barras"].iloc[0] == 4
    pl = et.placar(r, "123")
    assert pl["primario"]["n_resolvidas"] == 1 and pl["primario"]["n_ignorados_posicao"] == 1
    assert pl["primario"]["ic_confianca"] == 0.95


def test_rodar_123_por_ficha(tmp_path: Path) -> None:
    from tests.test_eas_preco import _dia_123
    d = _dia_123(1250901, 1)
    r = et.rodar(_dump(tmp_path, d), tmp_path / "s", "teste", ficha="123")
    assert r["arquivo"].name == "resultado_123_teste.json"
    assert r["carimbo"]["parametros"]["TRIAL"] == 1


def test_trial_e_por_ficha_e_instrumento() -> None:
    import importlib

    from profittape.research import eas_preco as ep
    assert et.trial_de("ifr2") == 2 and et.trial_de("orb") == 1
    try:
        ep.usar_instrumento("wdo")
        assert et.trial_de("ifr2") == 1                      # WDO: trial 1
        assert et.parametros_da_ficha("ifr2")["TRIAL"] == 1
    finally:
        ep.usar_instrumento("win")
        importlib.reload(ep)


def test_ficha_123gate_tem_trial_1_hash_proprio_e_complemento(tmp_path: Path) -> None:
    from tests.test_eas_preco import _dia, _dump
    assert et.trial_de("123gate") == 1 and et.hash_ficha("123gate") != et.hash_ficha("123")
    d = _dia(1250901, 1)
    for b in d:
        b["vol_total"] = 100
    r = et.rodar(_dump(tmp_path, d), tmp_path / "s", "teste", ficha="123gate")
    assert r["arquivo"].name == "resultado_123gate_teste.json"
    assert "complemento_reportado" in r["placar"]
    assert (tmp_path / "s" / "sinais_123gate_teste_complemento.csv").exists()


def test_por_quartil_de_d_separa_gate_e_complemento() -> None:
    import numpy as np
    rng = np.random.default_rng(1)
    def _r(n: int, base_d: float) -> pd.DataFrame:
        return pd.DataFrame({"classe": "resolvida", "D_pts": base_d + rng.integers(0, 400, n) * 5.0,
                             "resultado": rng.choice([1.0, -1.0], n), "pnl_bruto_pts": 0.0,
                             "lado": "compra", "a_favor_mme80": True})
    pq = et.por_quartil_de_d(_r(200, 500.0), _r(200, 100.0), et.Z95)
    assert set(pq) == {"cortes_D_pts", "Q1", "Q2", "Q3", "Q4"} and len(pq["cortes_D_pts"]) == 3
    total = sum(pq[q]["gate"]["n_resolvidas"] + pq[q]["complemento"]["n_resolvidas"]
                for q in ("Q1", "Q2", "Q3", "Q4"))
    assert total == 400
    # D pequeno = complemento
    assert pq["Q1"]["complemento"]["n_resolvidas"] > pq["Q1"]["gate"]["n_resolvidas"]


def test_ficha_123gate_baixo_recusa_win_e_roda_no_wdo(tmp_path: Path) -> None:
    import importlib

    from tests.test_eas_preco import _dia, _dump
    d = _dia(1250901, 1)
    for b in d:
        b["vol_total"] = 100
    dump = _dump(tmp_path, d)
    with pytest.raises(SystemExit, match="queimado"):
        et.rodar(dump, tmp_path / "s", "teste", ficha="123gate_baixo")
    try:
        ep.usar_instrumento("wdo")
        r = et.rodar(dump, tmp_path / "s", "teste", ficha="123gate_baixo")
        assert r["arquivo"].name == "resultado_123gate_baixo_teste.json"
        assert r["carimbo"]["parametros"]["TRIAL"] == 1 and "complemento_reportado" in r["placar"]
    finally:
        ep.usar_instrumento("win")
        importlib.reload(ep)
