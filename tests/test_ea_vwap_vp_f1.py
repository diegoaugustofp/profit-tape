"""F1 do EA vwap_vp (2026-09-29): VWAP de sessao com bandas, perfil de
volume POR PRECO (POC, area de valor, HVN/LVN, delta por nivel) e a
conferencia do dia a partir do curated.

Os numeros esperados foram calculados A MAO antes destes testes (regra 4
da disciplina): vwap de (100x10, 110x30) = 4300/40 = 107,5; variancia
ponderada = (10*7,5^2 + 30*2,5^2)/40 = 750/40 = 18,75.
"""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from profittape.ea import cache_barras as cb
from profittape.ea import perfil_preco as pp
from profittape.ea.vwap_sessao import VWAPSessao
from profittape.research import vwapvp_conferir as vc

NS = 1_000_000_000


# ------------------------------------------------------------------ VWAP
def test_vwap_e_desvio_conferidos_a_mao() -> None:
    v = VWAPSessao()
    assert v.vwap is None and v.banda(2) is None
    v.registrar(100, 10)
    v.registrar(110, 30)
    assert v.vwap == pytest.approx(107.5)
    assert v.variancia == pytest.approx(18.75)
    assert v.desvio == pytest.approx(math.sqrt(18.75))
    inf, sup = v.banda(2)  # type: ignore[misc]
    assert inf == pytest.approx(107.5 - 2 * math.sqrt(18.75))
    assert sup == pytest.approx(107.5 + 2 * math.sqrt(18.75))
    assert v.n == 2 and v.volume == 40


def test_vwap_invariante_a_translacao_e_precisao_no_win() -> None:
    """Precos ~140.000 nao podem degradar a variancia (por isso o p0)."""
    a, b = VWAPSessao(), VWAPSessao()
    for p, q in ((100, 10), (110, 30), (105, 7), (103, 1000)):
        a.registrar(p, q)
        b.registrar(p + 140_000, q)
    assert b.vwap == pytest.approx(a.vwap + 140_000)  # type: ignore[operator]
    assert b.variancia == pytest.approx(a.variancia, rel=1e-9)


def test_vwap_ignora_quantidade_nao_positiva_e_reinicia() -> None:
    v = VWAPSessao()
    v.registrar(100, 0)
    assert v.vwap is None
    v.registrar(100, 5)
    v.reiniciar()
    assert v.vwap is None and v.n == 0


def test_vwap_um_unico_preco_tem_desvio_zero() -> None:
    v = VWAPSessao()
    for _ in range(5):
        v.registrar(140_005, 3)
    assert v.desvio == 0.0
    assert v.banda(2) == (140_005, 140_005)


# --------------------------------------------------------------- PERFIL
def _perfil_basico() -> pp.PerfilDePreco:
    p = pp.PerfilDePreco(5)
    for pr in (100, 105, 105, 110, 110, 110, 115):
        p.registrar(pr, 1, 2)
    return p


def test_poc_e_area_de_valor_conferidos_a_mao() -> None:
    """7 contratos; POC=110 (3). Alvo 70% = 4,9. Vizinhos: 115 (1) vs 105
    (2) -> 105 entra, acum 5 >= 4,9. VAL=105, VAH=110+5=115."""
    p = _perfil_basico()
    assert p.poc() == 110
    assert p.area_de_valor(0.70) == (105, 115)
    assert p.volume == 7


def test_bin_e_floor_e_bin_de_25_pts() -> None:
    p = pp.PerfilDePreco(25)
    assert p.bin_de(140_024.9) == 140_000
    assert p.bin_de(140_025) == 140_025
    assert p.bin_de(139_999) == 139_975


def test_poc_empate_pega_o_mais_proximo_do_centro() -> None:
    p = pp.PerfilDePreco(5)
    for pr in (100, 105, 130):          # 100 e 130 sao as pontas; 105 esta' mais no centro
        p.registrar(pr, 1, 2)
    assert p.poc() == 105


def test_area_de_valor_empate_expande_para_cima() -> None:
    p = pp.PerfilDePreco(5)
    for pr, q in ((100, 2), (105, 5), (110, 2)):
        p.registrar(pr, q, 2)
    # alvo 6,3: POC 105 (5); acima 110 (2) == abaixo 100 (2) -> sobe
    assert p.area_de_valor(0.70) == (105, 115)


def test_delta_por_nivel_e_separacao_do_rlp() -> None:
    p = pp.PerfilDePreco(5)
    p.registrar(100, 10, 2)             # agressao compra
    p.registrar(100, 4, 3)              # agressao venda
    p.registrar(100, 30, 13)            # RLP: entra no total, nao no delta
    p.registrar(100, 6, 4)              # leilao: idem
    assert p.volume_no_bin(100) == 50
    assert p.delta_no_bin(100) == 6
    r = p.resumo()
    assert r["volume_rlp"] == 30 and r["volume_leilao"] == 6
    assert r["agr_compra"] == 10 and r["agr_venda"] == 4


def test_incluir_tipos_filtra_o_total_mas_nao_a_agressao() -> None:
    p = pp.PerfilDePreco(5, incluir_tipos=(2, 3))
    p.registrar(100, 10, 2)
    p.registrar(100, 30, 13)
    assert p.volume_no_bin(100) == 10
    assert p.resumo()["volume_rlp"] == 30      # continua contado a parte


def test_nos_lvn_e_hvn() -> None:
    """Perfil em 'M': dois picos (100, 120) e um vale (110) -- o vale e' LVN,
    os picos sao HVN; bin ausente (115) conta como zero e tambem e' LVN."""
    p = pp.PerfilDePreco(5)
    for pr, q in ((100, 100), (105, 60), (110, 5), (120, 90), (125, 40)):
        p.registrar(pr, q, 2)
    nos = p.nos(lvn_frac=0.30, hvn_frac=0.50, vizinhos=1)
    assert 110 in nos["lvn"] and 115 in nos["lvn"]
    assert nos["hvn"] == [100, 120]
    assert 105 not in nos["lvn"]


def test_perfil_vazio_e_range_curto() -> None:
    p = pp.PerfilDePreco(5)
    assert p.vazio and p.poc() is None and p.area_de_valor() is None
    assert p.nos() == {"lvn": [], "hvn": []}
    assert p.resumo()["poc"] is None
    p.registrar(100, 1, 2)
    p.registrar(105, 1, 2)
    assert p.nos() == {"lvn": [], "hvn": []}   # < 3 bins: sem no'


def test_json_ida_e_volta() -> None:
    p = _perfil_basico()
    p.registrar(110, 9, 13)
    q = pp.PerfilDePreco._de_json(json.loads(json.dumps(p._para_json())))
    assert q.bins() == p.bins() and q.volume == p.volume and q.n == p.n
    assert q.poc() == p.poc() and q.area_de_valor() == p.area_de_valor()
    assert q.resumo()["volume_rlp"] == 9


# ------------------------------------------------------------- CURATED
def _dia_no_curated(curated: Path, dia: dt.date, symbol: str = "WINFUT") -> None:
    """Tres bins: 140000 (compra 10 + rlp 30), 140025 (venda 4), 140050 (leilao 6)."""
    pasta = curated / "trade" / f"dt={dia.isoformat()}" / f"sym={symbol}"
    pasta.mkdir(parents=True, exist_ok=True)
    t0 = int(pd.Timestamp(f"{dia} 12:00", tz="UTC").value)   # 09:00 em Sao Paulo
    linhas = [(140_000.0, 10, 2), (140_030.0, 4, 3), (140_010.0, 30, 13), (140_055.0, 6, 4)]
    n = len(linhas)
    tab = pa.table({"ts_ns": [t0 + i * 3600 * NS for i in range(n)],
                    "symbol": [symbol] * n, "trade_id": list(range(n)),
                    "price": [p for p, _, _ in linhas],
                    "quantidade": [q for _, q, _ in linhas],
                    "trade_type": [t for _, _, t in linhas],
                    "agente_comprador": [1] * n, "agente_vendedor": [2] * n,
                    "is_edit": [False] * n, "ts_recv_ns": [t0] * n,
                    "volume_financeiro": [0.0] * n})
    pq.write_table(tab, pasta / "parte-0.parquet")


@pytest.fixture(autouse=True)
def _limpo() -> None:
    cb.limpar_memoria()


def test_perfil_do_dia_constroi_e_cacheia(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dia = dt.date(2026, 9, 28)
    curated = tmp_path / "curated"
    _dia_no_curated(curated, dia)
    p = pp.perfil_do_dia(curated, "WINFUT", dia, 25)
    assert p.bins() == [140_000, 140_025, 140_050]
    assert p.volume == 50 and p.delta_no_bin(140_000) == 10 and p.delta_no_bin(140_025) == -4
    assert p.poc() == 140_000
    arq = list((tmp_path / "cache" / "perfil_preco").glob("*.json"))
    assert len(arq) == 1

    n = {"construiu": 0}
    real = pp.construir_do_dia

    def contando(*a: object, **k: object) -> pp.PerfilDePreco:
        n["construiu"] += 1
        return real(*a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(pp, "construir_do_dia", contando)
    q = pp.perfil_do_dia(curated, "WINFUT", dia, 25)
    assert n["construiu"] == 0 and q.volume == 50 and q.poc() == 140_000

    # o dia mudou no curated (backfill): assinatura muda, refaz
    _dia_no_curated(curated, dia)
    pasta = curated / "trade" / f"dt={dia.isoformat()}" / "sym=WINFUT"
    pq.write_table(pq.read_table(pasta / "parte-0.parquet"), pasta / "parte-1.parquet")
    r = pp.perfil_do_dia(curated, "WINFUT", dia, 25)
    assert n["construiu"] == 1 and r.volume == 100


def test_perfil_do_dia_sem_tape_devolve_vazio_sem_cache(tmp_path: Path) -> None:
    curated = tmp_path / "curated"
    p = pp.perfil_do_dia(curated, "WINFUT", dt.date(2026, 9, 28), 25)
    assert p.vazio
    assert not (tmp_path / "cache").exists()


def test_conferir_dia_vwap_por_conjunto_e_checkpoints(tmp_path: Path) -> None:
    """todos: (140000x10 + 140030x4 + 140010x30 + 140055x6)/50 = 7000750/50 = 140015.
    agressao: (140000x10 + 140030x4)/14 = 140008,571. Checkpoint 10:00
    (SP) ve so' o 1o negocio (09:00); 1200 ve os tres primeiros."""
    dia = dt.date(2026, 9, 28)
    curated = tmp_path / "curated"
    _dia_no_curated(curated, dia)
    r = vc.conferir_dia(curated, "WINFUT", dia, bin_pts=25, checkpoints_hhmm=(1000, 1200, 1600))
    assert "erro" not in r
    assert r["vwap_final"]["todos"]["vwap"] == pytest.approx(140_015.0)
    assert r["vwap_final"]["agressao"]["vwap"] == pytest.approx(140_008.5714, abs=1e-3)
    assert r["vwap_final"]["agressao_rlp"]["volume"] == 44
    assert r["vwap_checkpoints"][1000]["todos"]["n"] == 1
    assert r["vwap_checkpoints"][1200]["todos"]["n"] == 3
    assert r["vwap_checkpoints"][1600]["todos"]["n"] == 4
    assert r["perfil"]["poc"] == 140_000 and r["perfil"]["volume_rlp"] == 30
    assert r["delta_agr_na_area_de_valor"] is not None
    assert list(r["histograma"].columns) == ["bin", "volume", "delta_agr", "rlp"]
    linhas = vc.formatar(r)
    assert any("POC=140000" in ln for ln in linhas)
    assert any("todos" in ln and "140015.0" in ln for ln in linhas)


def test_conferir_dia_sem_tape() -> None:
    r = vc.conferir_dia(Path("/nao/existe"), "WINFUT", dt.date(2026, 9, 28))
    assert "erro" in r and vc.formatar(r)[0].endswith("dia sem tape no curated")


def test_cli_vwapvp_conferir(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from profittape.cli import app

    dia = dt.date(2026, 9, 28)
    curated = tmp_path / "curated"
    _dia_no_curated(curated, dia)
    csv = tmp_path / "hist.csv"
    res = CliRunner().invoke(app, ["vwapvp-conferir", "--dia", dia.isoformat(),
                                   "--curated", str(curated), "--histograma-csv", str(csv)])
    assert res.exit_code == 0, res.output
    assert "POC=140000" in res.output and "[1/1] 2026-09-28" in res.output
    assert (tmp_path / "hist_2026-09-28.csv").exists()
