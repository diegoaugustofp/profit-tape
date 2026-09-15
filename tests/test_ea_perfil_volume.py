"""Perfil de volume por horario (EA) x perfil_volume_horario (research): a
mesma mediana, ou o gate ao vivo nao e' o gate testado."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from profittape.ea import perfil_volume as pv
from profittape.ea.config_123 import EA123Config
from profittape.ea.gate_fluxo import GateVolumeBaixo, construir_gate
from profittape.ea.service_123 import EA123Service, _TradeBruto
from profittape.ea.sinal import BarraFechada
from profittape.research import eas_preco as ep
from tests.test_ea_semente import _tape_fake

NS = 1_000_000_000


def _parquet_vol(tmp_path: Path, n_dias: int = 25, seed: int = 2) -> tuple[Path, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    linhas = []
    d = dt.date(2026, 7, 1)
    cb = 1
    for _ in range(n_dias):
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        h, m = 9, 0
        for _ in range(37):
            linhas.append({"dia": d, "hhmm": h * 100 + m, "current_bar": cb, "bloco": 1,
                           "close": 140000.0, "vol_total": float(rng.integers(1000, 9000))})
            cb += 1
            m += 15
            if m == 60:
                h, m = h + 1, 0
        d += dt.timedelta(days=1)
    df = pd.DataFrame(linhas)
    p = tmp_path / "barras_123.parquet"
    df.to_parquet(p, index=False)
    return p, df


def test_perfil_do_ea_e_igual_ao_do_research(tmp_path: Path) -> None:
    p, df = _parquet_vol(tmp_path, 26)
    dias = sorted(df["dia"].unique())
    alvo = dias[-1]                                     # opera no ultimo dia do parquet
    perfil = pv.construir_perfil(p, alvo)               # usa dias < alvo
    ref = df.copy()
    ref["med"] = ep.perfil_volume_horario(ref, 20)      # research: 20 dias anteriores
    ref_alvo = ref[ref["dia"] == alvo].set_index("hhmm")["med"]
    for hhmm, med in ref_alvo.items():
        assert perfil.mediana(int(hhmm), alvo) == pytest.approx(float(med))


def test_perfil_indefinido_sem_20_dias_e_dia_corrente_nao_entra(tmp_path: Path) -> None:
    p, df = _parquet_vol(tmp_path, 15)
    alvo = sorted(df["dia"].unique())[-1] + dt.timedelta(days=1)
    perfil = pv.construir_perfil(p, alvo)
    assert perfil.mediana(1000, alvo) is None           # so' 15 dias
    perfil2 = pv.PerfilVolumeHorario(2)
    perfil2.registrar(dt.date(2026, 9, 1), 1000, 10.0)
    perfil2.registrar(dt.date(2026, 9, 2), 1000, 30.0)
    perfil2.registrar(dt.date(2026, 9, 3), 1000, 1000.0)          # o proprio dia
    assert perfil2.mediana(1000, dt.date(2026, 9, 3)) == 20.0     # so' 01 e 02
    perfil2.registrar(dt.date(2026, 9, 4), 1000, 5.0, confiavel=False)
    assert perfil2.mediana(1000, dt.date(2026, 9, 5)) == pytest.approx(515.0)  # 30 e 1000


def test_ponte_pelo_tape_entra_no_perfil(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p, df = _parquet_vol(tmp_path, 22)
    ultimo = sorted(df["dia"].unique())[-1]
    prox = ultimo + dt.timedelta(days=1)
    while prox.weekday() >= 5:
        prox += dt.timedelta(days=1)
    curated = _tape_fake(monkeypatch, tmp_path, {prox: [140000.0] * 37})
    from profittape.ea import semente as sm
    monkeypatch.setattr(pv, "_carregar_dia", sm._carregar_dia)     # o fake instalado em semente
    alvo = prox + dt.timedelta(days=1)
    perfil = pv.construir_perfil(p, alvo, curated)
    assert prox.isoformat() in perfil.dias_carregados
    # o dia da ponte entrou: a fila do 09:00 tem `prox` como ultimo
    assert perfil._fila[900][-1][0] == prox


def _barra(ts_open: int, vol: int, confiavel: bool = True) -> BarraFechada:
    return BarraFechada(bar_id=ts_open // (900 * NS), ts_open_ns=ts_open,
                        ts_close_ns=ts_open + 900 * NS, open=1.0, high=2.0, low=0.5, close=1.5,
                        vol_agr=vol, agf={}, vol_total=vol, volume_confiavel=confiavel)


def test_gate_volume_baixo_decide_e_conta_indefinidos() -> None:
    from profittape.ea.sinal_123 import Candidato123
    perfil = pv.PerfilVolumeHorario(2)
    perfil.registrar(dt.date(2026, 9, 1), 1000, 100.0)
    perfil.registrar(dt.date(2026, 9, 2), 1000, 200.0)             # mediana 150
    g = GateVolumeBaixo(perfil, lambda: dt.date(2026, 9, 3))
    t0 = int(pd.Timestamp("2026-09-03 13:00:00", tz="UTC").value)   # 10:00 BRT
    cand = Candidato123("compra", 1.0, 0.5, 1.5, 0.5, 1, 1000, t0 + 2 * 900 * NS, 1.0, True,
                        0, 0, 0)
    assert g.permite(cand, _barra(t0, 120)) is True                  # 120 < 150
    assert g.permite(cand, _barra(t0, 180)) is False
    assert g.permite(cand, _barra(t0, 120, confiavel=False)) is False and g.indefinidos == 1
    t1 = int(pd.Timestamp("2026-09-03 15:00:00", tz="UTC").value)   # 12:00: sem perfil
    assert g.permite(cand, _barra(t1, 1)) is False and g.indefinidos == 2
    assert g.ultimo["mediana"] is None
    assert isinstance(construir_gate({"tipo": "volume_baixo"}, perfil, None), GateVolumeBaixo)
    with pytest.raises(ValueError, match="exige"):
        construir_gate({"tipo": "volume_baixo"})


def test_servico_com_gate_volume_baixo_grava_infra(tmp_path: Path) -> None:
    import yaml
    p, df = _parquet_vol(tmp_path, 25)
    # semente da MME80: o parquet precisa de mme80_ntsl
    df["mme80_ntsl"] = 139000.0
    df.to_parquet(p, index=False)
    alvo = sorted(df["dia"].unique())[-1]
    cfg_path = tmp_path / "ea.yaml"
    cfg_path.write_text(yaml.safe_dump({
        "tipo": "123", "nome": "ea_123g", "dry_run": True,
        "semente_parquet": str(p), "curated": str(tmp_path / "nao"),
        "registro_dir": str(tmp_path / "fw"),
        "filtro_fluxo": {"tipo": "volume_baixo", "janela_pregoes": 20}}), encoding="utf-8")
    cfg = EA123Config.from_yaml(cfg_path)
    s = EA123Service(cfg, dia=alvo)
    assert s.perfil is not None and s.perfil.resumo()["horarios_com_perfil"] >= 30
    assert type(s.ciclo.gate).__name__ == "GateVolumeBaixo"
    assert s.sinal.mme.valor == 139000.0
    t0 = int(pd.Timestamp(f"{alvo} 12:00:00", tz="UTC").value)

    def trade(seg: float, px: float, qtd: int = 1) -> None:
        s.processar_trade_bruto(_TradeBruto(t0 + int(seg * NS), px, qtd, 2))

    # 3 barras com negocio a cada 2 s (confiaveis), volume minusculo (< mediana)
    def barra(ini: float, o: float, h: float, lo: float, c: float) -> None:
        trade(ini, o)
        trade(ini + 2, h)
        trade(ini + 4, lo)
        for k in range(6, 898, 2):
            trade(ini + k, c)
    barra(0, 140000.0, 140100.0, 139900.0, 140050.0)
    barra(900, 140050.0, 140080.0, 139800.0, 140000.0)
    barra(1800, 140000.0, 140050.0, 139900.0, 140020.0)
    trade(2700, 140020.0)                                  # fecha 09:30 -> arma (volume baixo)
    assert s.ciclo.estado == "entrada_pendente"
    trade(2750, 140060.0)
    trade(2800, 140320.0)                                  # fill e alvo
    arq = list((tmp_path / "fw").glob("*.jsonl"))
    linha = json.loads(arq[0].read_text(encoding="utf-8").strip().splitlines()[-1])
    assert linha["infra"]["gate"]["confiavel"] is True and linha["infra"]["gate"]["mediana"] > 0
    assert linha["infra"]["semente_valida"] is True and linha["infra"]["dia_completo"] is True
    assert linha["candidato"]["volume_confiavel_t"] is True
    # fill e alvo cairam na mesma barra: a barra do gatilho ainda nao tinha fechado
    assert linha["barra_gatilho"] is None
