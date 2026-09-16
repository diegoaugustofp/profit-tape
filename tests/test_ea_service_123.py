"""Passo 7: EA123Config, loader por tipo, EA123Service na esteira (dry_run)."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd
import pytest

from profittape.ea.config_123 import EA123Config, carregar_config_ea
from profittape.ea.despachante import DespachanteDeEAs
from profittape.ea.registro import RegistroDeEAs
from profittape.ea.service_123 import EA123Service, _TradeBruto
from tests.test_ea_semente import _parquet

NS = 1_000_000_000


def _yaml(tmp_path: Path, **extra: object) -> Path:
    base = {"tipo": "123", "nome": "ea_123", "symbol": "WINFUT", "dry_run": True,
            "semente_parquet": str(tmp_path / "barras_123.parquet"),
            "curated": str(tmp_path / "curated"), "registro_dir": str(tmp_path / "forward")}
    base.update(extra)
    p = tmp_path / "ea_123.yaml"
    import yaml
    p.write_text(yaml.safe_dump(base), encoding="utf-8")
    return p


def test_loader_escolhe_pelo_tipo(tmp_path: Path) -> None:
    cfg = carregar_config_ea(_yaml(tmp_path))
    assert isinstance(cfg, EA123Config) and cfg.filtro_fluxo is None
    assert cfg.capital_recomendado_informativo() == 6000.0
    assert len(cfg.sha256()) == 12


def test_config_recusa_campo_desconhecido_e_gate_com_conteudo(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="extra"):
        EA123Config.from_yaml(_yaml(tmp_path, k_atr=0.5))
    from profittape.ea.gate_fluxo import construir_gate
    with pytest.raises(ValueError, match="ficha"):
        construir_gate({"absorcao_min": 1.0})


def test_yaml_do_repositorio_carrega() -> None:
    raiz = Path(__file__).resolve().parents[1]
    cfg = carregar_config_ea(raiz / "config" / "ea_123.yaml")
    assert isinstance(cfg, EA123Config) and cfg.dry_run and cfg.filtro_fluxo is None


def test_servico_sem_semente_nao_arma_mas_sobe(tmp_path: Path) -> None:
    cfg = EA123Config.from_yaml(_yaml(tmp_path))          # parquet nao existe
    s = EA123Service(cfg, dia=dt.date(2026, 9, 11))
    assert not s.semente.valida and s._hb()["semente_valida"] is False
    t0 = int(pd.Timestamp("2026-09-11 12:00:00", tz="UTC").value)
    for i in range(40):
        s.processar_trade_bruto(_TradeBruto(t0 + i * 900 * NS + NS, 140000.0, 1, 2))
    assert s.barras >= 36 and s.ciclo.sinal.candidatos_armados == 0   # 18:30+ dobra na 18:15
    assert s.sinal.mme.n == s.barras                       # MME atualizada mesmo assim


def test_servico_dry_run_opera_e_grava_registro(tmp_path: Path) -> None:
    # semente valida: parquet ate' 10/09
    _parquet(tmp_path, [dt.date(2026, 9, 9), dt.date(2026, 9, 10)])
    cfg = EA123Config.from_yaml(_yaml(tmp_path))
    s = EA123Service(cfg, dia=dt.date(2026, 9, 11))
    assert s.semente.valida
    s.sinal.mme.valor = 139000.0                            # regime de compra garantido
    t0 = int(pd.Timestamp("2026-09-11 12:00:00", tz="UTC").value)

    def trade(seg: float, px: float) -> None:
        s.processar_trade_bruto(_TradeBruto(t0 + int(seg * NS), px, 1, 2))

    # 09:00: 140000-140100/139900 ; 09:15: low 139800 ; 09:30: high 140050 -> compra 140055
    for seg, px in [(1, 140000.0), (100, 140100.0), (200, 139900.0), (800, 140050.0),
                    (901, 140050.0), (1000, 139800.0), (1700, 140000.0),
                    (1801, 140000.0), (1900, 140050.0), (2000, 139900.0), (2600, 140020.0)]:
        trade(seg, px)
    trade(2701, 140020.0)                                   # fecha 09:30 -> arma
    assert s.ciclo.estado == "entrada_pendente"
    trade(2750, 140060.0)                                   # cruza -> posicionado
    assert s.ciclo.estado == "posicionado"
    trade(2800, 140320.0)                                   # alvo -> livre
    assert s.ciclo.estado == "livre" and len(s.ciclo.operacoes) == 1
    arq = list((tmp_path / "forward").glob("sinais_123_*.jsonl"))
    assert len(arq) == 1
    linha = json.loads(arq[0].read_text(encoding="utf-8").strip().splitlines()[-1])
    assert linha["desfecho"] == "alvo" and linha["carimbo"]["yaml_sha256"] == cfg.sha256()
    assert linha["ordens"]["entrada"]["slippage_pts"] == 5.0
    assert linha["barra_gatilho"] is None or "vol_agr_compra" in linha["barra_gatilho"]


def test_registro_de_eas_monta_o_123_pelo_yaml(tmp_path: Path) -> None:
    _parquet(tmp_path, [dt.date(2026, 9, 10)])
    cfg = carregar_config_ea(_yaml(tmp_path))
    reg = RegistroDeEAs(DespachanteDeEAs(), modo_ticker="exclusivo")
    r = reg.incluir(cfg, origem=tmp_path / "ea_123.yaml")
    assert r.nome == "ea_123" and r.symbol == "WINFUT"
    assert type(r.bridge.ea_service).__name__ == "EA123Service"
    assert reg.remover("ea_123")


def test_caminho_relativo_resolve_pela_pasta_do_yaml(tmp_path: Path) -> None:
    """Bug real (2026-09-16): record rodado de outra pasta -> semente e perfil
    vazios, EA sobe inerte. Relativo passa a ser resolvido pelo yaml."""
    import os

    import yaml
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "x.parquet").write_text("", encoding="utf-8")
    p = tmp_path / "ea.yaml"
    p.write_text(yaml.safe_dump({"tipo": "123", "semente_parquet": "data/x.parquet",
                                 "curated": "data", "registro_dir": "fw"}), encoding="utf-8")
    cwd = os.getcwd()
    try:
        os.chdir("/")                       # de qualquer lugar
        cfg = carregar_config_ea(p)
    finally:
        os.chdir(cwd)
    assert cfg.semente_parquet == str((tmp_path / "data" / "x.parquet").resolve())
    assert cfg.registro_dir == str((tmp_path / "fw").resolve())


def test_servico_recusa_gate_com_perfil_vazio(tmp_path: Path) -> None:
    import yaml
    p = tmp_path / "ea.yaml"
    p.write_text(yaml.safe_dump({
        "tipo": "123", "nome": "vb", "semente_parquet": str(tmp_path / "nao.parquet"),
        "curated": str(tmp_path / "nao"), "registro_dir": str(tmp_path / "fw"),
        "filtro_fluxo": {"tipo": "volume_baixo"}}), encoding="utf-8")
    cfg = EA123Config.from_yaml(p)
    with pytest.raises(SystemExit, match="perfil esta' VAZIO"):
        EA123Service(cfg, dia=dt.date(2026, 9, 16))
