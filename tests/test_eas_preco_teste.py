"""research/eas_preco_teste.py -- o teste da ficha IFR2 congelada."""

from __future__ import annotations

from pathlib import Path

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
    assert et.veredito(0.50) == "CONTRA"
    assert et.veredito(0.53) == "INCONCLUSIVO"
    assert et.veredito(float("nan")) == "sem amostra"


def test_hash_da_ficha_muda_se_um_parametro_mudar(monkeypatch: pytest.MonkeyPatch) -> None:
    h0 = et.hash_ficha()
    monkeypatch.setitem(et.PARAMETROS_FICHA, "K_ATR", 0.75)
    assert et.hash_ficha() != h0


def _cenario_teste(tmp_path: Path, data: int = 1250901) -> Path:
    """Um pregao de 2025 com 3 sinais de compra: um vence, um perde, um
    ambiguo. Barras a +-20 para nao tocar barreiras a +-50."""
    d1 = _dia(data, 1)
    for b in d1:
        b["high"], b["low"], b["mme80_ntsl"] = 140020.0, 139980.0, 139000.0
    d1[2]["rsi_ntsl"] = 5.0          # sinal 09:30 -> entrada 140000, alvo 140050, stop 139950
    d1[4]["high"] = 140060.0         # 10:00 toca so' o alvo -> +1
    d1[8]["rsi_ntsl"] = 5.0          # sinal 11:00
    d1[10]["low"] = 139940.0         # 11:30 toca so' o stop -> -1
    d1[14]["rsi_ntsl"] = 5.0         # sinal 12:30
    d1[16]["high"], d1[16]["low"] = 140080.0, 139920.0   # 13:00 os dois -> ambigua
    return _dump(tmp_path, d1)


def test_resolver_sinais_classifica_e_da_o_resultado(tmp_path: Path) -> None:
    df, _ = ep.carregar_log(_cenario_teste(tmp_path))
    x = ep.marcar_ifr2(ep.indicadores(df))
    r = et.resolver_sinais(x)
    assert list(r["classe"]) == ["resolvida", "resolvida", "ambigua"]
    assert list(r["resultado"]) == [1.0, -1.0, 0.0]
    assert list(r["pnl_bruto_pts"].iloc[:2]) == [50.0, -50.0]
    assert list(r["barras"]) == [2, 2, 2]


def test_venda_espelha_o_favoravel(tmp_path: Path) -> None:
    d1 = _dia(1250901, 1)
    for b in d1:
        b["high"], b["low"], b["mme80_ntsl"] = 140020.0, 139980.0, 141000.0
    d1[2]["rsi_ntsl"] = 95.0         # venda: alvo 139950, stop 140050
    d1[4]["low"] = 139940.0          # toca o alvo da venda -> +1
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
    assert r["arquivo"].exists() and (tmp_path / "s" / "sinais_teste.csv").exists()
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
