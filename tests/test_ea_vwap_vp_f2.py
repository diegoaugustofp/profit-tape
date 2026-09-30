"""F2 do EA vwap_vp (docs/eas/vwap_vp.md): replay do Setup B.

Os exemplos numericos foram conferidos a mao ANTES de virar assert
(disciplina, regra 4): estimador de absorcao, z rolante, area de valor
por pares, plato do POC, sonda de excursao.
"""

from __future__ import annotations

import datetime as dt
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from typer.testing import CliRunner

from profittape.ea import perfil_preco as pp
from profittape.ea.sinal import BarraFechada
from profittape.research import vwapvp_replay as vr

NS = 1_000_000_000


def _barra(o: float, h: float, lo: float, c: float, compra: int, venda: int) -> BarraFechada:
    return BarraFechada(bar_id=1, ts_open_ns=0, ts_close_ns=300 * NS, open=o, high=h, low=lo,
                        close=c, vol_agr=compra + venda, agf={}, vol_agr_compra=compra,
                        vol_agr_venda=venda, n_trades=10, vol_total=compra + venda)


# --------------------------------------------------------------- estimador
def test_absorcao_dir_conferida_a_mao() -> None:
    """compra 30 / venda 10 -> imbalance 0,5; open 100 close 102 em range 10
    -> desloc 0,2; absorcao_dir = 0,3. Coluna historica, nao clausula."""
    assert vr.absorcao_dir(_barra(100, 110, 100, 102, 30, 10)) == pytest.approx(0.3)
    assert vr.absorcao_dir(_barra(100, 100, 100, 100, 30, 10)) is None      # range 0
    assert vr.absorcao_dir(_barra(100, 110, 100, 105, 0, 0)) is None        # sem agressao


def test_absorcao_do_lado_exausto_conferida_a_mao() -> None:
    """v3.90. compra 30 / venda 10 (imb 0,5), sobe 20% do range (des 0,2):
    comp = 0,5 x 0,8 = 0,40; vend = 0 (nao sao vendedores agredindo).
    Mesma agressao, preco cai ate' a minima (open 110 close 100, des -1):
    comp = 0,5 x 2 = 1,0. Barra de 27/07 18:10 (compra 8870 / venda 15249,
    open 176845 close 176775 high 176870 low 176745): comp = 0 e vend =
    0,2645 x 0,44 = 0,116 -- o absorcao_dir dava +0,30 e disparava."""
    b = _barra(100, 110, 100, 102, 30, 10)
    assert vr.absorcao_comp(b) == pytest.approx(0.40)
    assert vr.absorcao_vend(b) == 0.0
    assert vr.absorcao_comp(_barra(110, 110, 100, 100, 30, 10)) == pytest.approx(1.0)
    b27 = _barra(176845, 176870, 176745, 176775, 8870, 15249)
    assert vr.absorcao_comp(b27) == 0.0
    assert vr.absorcao_vend(b27) == pytest.approx(0.2645 * 0.44, abs=1e-3)
    assert vr.absorcao_dir(b27) == pytest.approx(0.2955, abs=1e-3)
    assert vr.absorcao_comp(_barra(100, 100, 100, 100, 30, 10)) is None


def test_z_rolante_usa_so_as_anteriores() -> None:
    """historico [1,2,3]: media 2, var populacional 2/3; x=4 -> z = 2/sqrt(2/3)."""
    z = vr.ZRolante(3)
    for x in (1.0, 2.0, 3.0):
        assert z.z(x) is None          # janela ainda nao fechou
        z.empurrar(x)
    assert z.z(4.0) == pytest.approx(2 / math.sqrt(2 / 3))
    z2 = vr.ZRolante(2)
    z2.empurrar(5.0)
    z2.empurrar(5.0)
    assert z2.z(7.0) is None           # variancia zero


# --------------------------------------------------------- area de valor v2
def test_area_de_valor_por_pares_e_plato_conferidos_a_mao() -> None:
    """bins 99975:1, 100000:15, 100025:20, 100050:4 (total 40, alvo 28).
    bin a bin: abaixo 15 > acima 4 -> (100000, 100050).
    pares: abaixo 15+1=16 > acima 4 -> desce 2 -> (99975, 100050).
    plato 90%: so' o bin de 20 -> (100025, 100050)."""
    q = pp.PerfilDePreco(25)
    for b, v in ((99975, 1), (100000, 15), (100025, 20), (100050, 4)):
        q.registrar(b, v, 2)
    assert q.area_de_valor(0.7) == (100000, 100050)
    assert q.area_de_valor(0.7, "pares") == (99975, 100050)
    assert q.poc_faixa(0.9) == (100025, 100050)
    assert q.poc_faixa(0.7) == (100000, 100050)     # 15 >= 14 entra
    with pytest.raises(ValueError):
        q.area_de_valor(0.7, "tpo")


# ------------------------------------------------------- clausulas/episodios
def _df(rows: list[dict[str, object]]) -> pd.DataFrame:
    base = {"ts_close_ns": 0, "hhmm": 1000, "close": 100.0, "vwap": 100.0, "sd": 10.0,
            "z_vwap": 0.0, "z_absorcao": 0.0, "dist_vah": 0.0, "dist_val": 0.0, "dia": "d"}
    return pd.DataFrame([{**base, **r} for r in rows])


def test_marcar_clausulas_lado_nivel_e_estimador() -> None:
    p = vr.ParametrosReplay(tolerancia_pts=25, hhmm_inicio=930, hhmm_fim=1700)
    d = vr._marcar_clausulas(_df([
        {"z_vwap": 2.5, "dist_vah": 10.0, "z_absorcao": 1.0, "hhmm": 1100},   # venda completa
        {"z_vwap": 2.5, "dist_vah": 60.0, "z_absorcao": 1.0},                 # longe do VAH
        {"z_vwap": -2.5, "dist_val": -20.0, "z_absorcao": -1.0, "hhmm": 1730},  # compra fora janela
        {"z_vwap": 1.0},                                                       # sem banda
        {"z_vwap": 2.5, "dist_vah": 0.0, "z_absorcao": -1.0, "hhmm": 1100},   # absorcao lado errado
    ]), p, p80=0.5, p90=0.9)
    assert list(d["lado"]) == [-1, -1, 1, 0, -1]
    assert list(d["c_banda"]) == [True, True, True, False, True]
    assert list(d["c_nivel"]) == [True, False, True, False, True]
    # estimador = z_absorcao * sinal(z_vwap): compra com z_abs -1 vira +1
    assert d["estimador"].iloc[2] == pytest.approx(1.0)
    assert list(d["c_absorcao_p80"]) == [True, False, True, False, False]
    assert list(d["c_janela"]) == [True, False, False, False, False]
    assert list(d["c_absorcao_p90"]) == [True, False, True, False, False]


def test_episodios_colapsam_com_cooldown() -> None:
    d = _df([{"ts_close_ns": t * NS, "c": c} for t, c in
             ((0, True), (300, True), (600, False), (1800, True), (2100, True), (3700, True))])
    e = vr._episodios(d, "c", cooldown_s=1800)
    assert list(e["ts_close_ns"] // NS) == [0, 1800, 3700]
    assert vr._episodios(d.assign(c=False), "c", 1800).empty


def test_sonda_mfe_mae_e_toque_conferidos_a_mao() -> None:
    """Venda em 110 com VWAP 100: precos 112, 108, 101, 99. A favor = queda:
    MFE = 110-99 = 11, MAE = 112-110 = 2; toca a VWAP (<= 100) no 99, aos 40 s."""
    ts = np.array([10, 20, 30, 40], dtype=np.int64) * NS
    px = np.array([112.0, 108.0, 101.0, 99.0])
    ep = pd.Series({"ts_close_ns": 0, "lado": -1, "close": 110.0, "vwap": 100.0})
    s = vr._sonda(ep, ts, px, (25, 60))
    assert s["dist_vwap_pts"] == 10
    assert s["mfe_25"] == 2 and s["mae_25"] == 2 and s["tocou_vwap_25"] is False
    assert s["mfe_60"] == 11 and s["mae_60"] == 2 and s["tocou_vwap_60"] is True
    assert s["s_ate_vwap_60"] == 40
    ep_c = pd.Series({"ts_close_ns": 0, "lado": 1, "close": 90.0, "vwap": 100.0})
    s2 = vr._sonda(ep_c, ts, px, (60,))
    assert s2["mfe_60"] == 22 and s2["tocou_vwap_60"] is True and s2["s_ate_vwap_60"] == 10


# ------------------------------------------------------------- dias/curated
def _dia_sintetico(curated: Path, dia: dt.date, precos: list[float], symbol: str = "WINFUT",
                   passo_s: int = 10) -> None:
    pasta = curated / "trade" / f"dt={dia.isoformat()}" / f"sym={symbol}"
    pasta.mkdir(parents=True, exist_ok=True)
    t0 = int(pd.Timestamp(f"{dia} 09:00", tz="America/Sao_Paulo").value)
    n = len(precos)
    # agressor variando por barra (senao absorcao_vend e' 0 constante e o z nao existe)
    tipos = [int(x) for x in np.random.default_rng(len(precos) + dia.day).choice([2, 3], size=n)]
    tab = pa.table({"ts_ns": [t0 + i * passo_s * NS for i in range(n)],
                    "symbol": [symbol] * n, "trade_id": list(range(n)),
                    "price": precos, "quantidade": [5] * n, "trade_type": tipos,
                    "agente_comprador": [1] * n, "agente_vendedor": [2] * n,
                    "is_edit": [False] * n, "ts_recv_ns": [t0 + i * passo_s * NS for i in range(n)],
                    "volume_financeiro": [0.0] * n})
    pq.write_table(tab, pasta / "parte-0.parquet")


def _curated_dois_dias(tmp_path: Path) -> Path:
    cur = tmp_path / "curated"
    rng = np.random.default_rng(7)
    # dia 1: passeio de 8 h (2.880 negocios a 10 s) em torno de 100.000 -> perfil de referencia
    p1 = 100_000 + np.cumsum(rng.choice([-5.0, 0.0, 5.0], size=2880))
    _dia_sintetico(cur, dt.date(2026, 9, 24), list(p1))
    # dia 2: mesmo passeio, com um esticao para cima no meio do dia
    p2 = 100_000 + np.cumsum(rng.choice([-5.0, 0.0, 5.0], size=2880))
    p2[1400:1500] += np.linspace(0, 600, 100)
    p2[1500:1700] += 600
    _dia_sintetico(cur, dt.date(2026, 9, 25), list(p2))
    return cur


def test_dias_disponiveis_e_referencia(tmp_path: Path) -> None:
    cur = _curated_dois_dias(tmp_path)
    (cur / "trade" / "dt=lixo").mkdir()
    dias = pp.dias_disponiveis(cur, "WINFUT")
    assert dias == [dt.date(2026, 9, 24), dt.date(2026, 9, 25)]
    assert pp.dia_de_referencia(cur, "WINFUT", dt.date(2026, 9, 25)) == dt.date(2026, 9, 24)
    assert pp.dia_de_referencia(cur, "WINFUT", dt.date(2026, 9, 24)) is None
    assert pp.dias_disponiveis(cur, "WDOFUT") == []


def test_rodar_replay_ponta_a_ponta_com_cache(tmp_path: Path,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    cur = _curated_dois_dias(tmp_path)
    cache = tmp_path / "cache"
    r = vr.rodar(cur, "WINFUT", None, vr.ParametrosReplay(), cache_dir=cache)
    assert "erro" not in r
    assert r["dias"] == 2 and r["dias_com_referencia"] == 1
    assert r["barras"] > 100 and r["barras_com_z"] > 0
    perc = r["estimador_percentis"]
    assert perc[50] <= perc[80] <= perc[90] <= perc[95]
    assert r["limiar_p80_congelado"] == perc[80]
    # z continuo: o dia 2 tem z desde a primeira barra (a janela fechou no dia 1)
    b = r["_barras"]
    d2 = b[b["dia"] == "2026-09-25"]
    assert d2["z_absorcao_comp"].notna().iloc[0] and d2["z_absorcao_vend"].notna().iloc[0]
    # estimador = z da serie do lado exausto; comp e vend nunca positivos juntos
    assert ((b["absorcao_comp"] > 0) & (b["absorcao_vend"] > 0)).sum() == 0
    acima = b[b["z_vwap"].astype(float) > 0]
    assert (acima["estimador"].fillna(-9) == acima["z_absorcao_comp"].fillna(-9)).all()
    assert (b["hhmm_abertura"] < b["hhmm"]).all() or (b["hhmm_abertura"] <= b["hhmm"]).all()
    # 4 variantes declaradas, clausulas acumulativas em cada uma
    assert len(r["variantes"]) == 4
    for v in r["variantes"]:
        e = v["episodios_por_clausula"]
        assert e["c_banda"] >= e["c_nivel"] >= e["c_absorcao_p80"] >= e["c_janela"]
        assert e["c_absorcao_p80"] >= e["c_absorcao_p90"]
    # afrouxar so' pode aumentar a taxa
    taxas = [v["episodios_por_dia"]["c_banda"] for v in r["variantes"]]
    assert taxas[2] >= taxas[0] and taxas[3] >= taxas[1]
    assert len(r["area_de_valor_dois_algoritmos"]) == 1
    assert any(k.startswith("c_banda") for k in r["sonda"])
    # sonda cacheada por barra: toda barra com |z| >= 1,5 tem dist_vwap_pts
    com_z = b[b["z_vwap"].abs() >= 1.5]
    if len(com_z):
        assert com_z["dist_vwap_pts"].notna().all()
    linhas = vr.formatar(r)
    assert any("CONGELADO" in x for x in linhas) and any("regra:" in x for x in linhas)
    # segunda rodada vem do cache: dois arquivos, e o caminho caro nao e' chamado
    assert len(list((cache).glob("WINFUT_*_300_*.json"))) == 2

    def _nao_construir(*a: object, **k: object) -> pd.DataFrame:
        raise AssertionError("construiu barras com cache valido")
    monkeypatch.setattr(vr, "_construir_barras", _nao_construir)
    r2 = vr.rodar(cur, "WINFUT", None, vr.ParametrosReplay(), cache_dir=cache)
    assert r2["barras"] == r["barras"] and r2["estimador_percentis"] == perc
    monkeypatch.undo()
    # dia sem tape e sem referencia nao quebram
    r3 = vr.rodar(cur, "WINFUT", ["2026-09-24", "2026-09-30"], cache_dir=cache)
    assert r3["dias"] == 1 and r3["dias_com_referencia"] == 0
    r4 = vr.rodar(cur, "WDOFUT")            # simbolo sem pasta: erro com lista vazia
    assert "erro" in r4 and r4["dias_disponiveis"] == []


def test_escolher_variante_por_taxa() -> None:
    def v(z: float, tol: float, nivel: float, janela: float) -> dict[str, object]:
        return {"z_banda": z, "tolerancia_pts": tol,
                "episodios_por_dia": {"c_nivel": nivel, "c_janela": janela}}
    vs = [v(2.0, 25, 0.2, 0.0), v(2.0, 50, 0.5, 0.4), v(1.5, 25, 0.9, 1.1), v(1.5, 50, 1.8, 1.6)]
    assert vr.escolher_variante(vs, 1.0) == 2          # a mais restritiva que chega a 1/dia
    assert vr.escolher_variante(vs, 2.0) is None       # nenhuma: abandono por taxa
    empate = [v(2.0, 50, 1.0, 1.2), v(1.5, 25, 1.0, 1.3)]
    assert vr.escolher_variante(empate, 1.0) == 0      # empate em c_nivel -> maior z_banda


def test_cli_replay_e_conferir_sem_dia(tmp_path: Path) -> None:
    from profittape.cli import app

    cur = _curated_dois_dias(tmp_path)
    runner = CliRunner()
    r = runner.invoke(app, ["ea-vwapvp-replay", "--curated", str(cur),
                            "--saida", str(tmp_path / "out")])
    assert r.exit_code == 0, r.output
    assert "CONGELADO" in r.output
    assert (tmp_path / "out" / "vwapvp_replay.json").exists()
    assert (tmp_path / "out" / "barras.csv").exists()
    assert "regra:" in r.output

    r = runner.invoke(app, ["vwapvp-conferir", "--curated", str(cur)])
    assert r.exit_code == 0, r.output
    assert "2026-09-24, 2026-09-25" in r.output and "plato" in r.output
    r = runner.invoke(app, ["vwapvp-conferir", "--curated", str(cur), "--dia", "2026-09-26"])
    assert r.exit_code == 1 and "recusado" in r.output and "2026-09-25" in r.output
