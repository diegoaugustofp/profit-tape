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


def test_caminho_relativo_resolve_pela_raiz_do_projeto(tmp_path: Path) -> None:
    """Dois bugs reais: 16/09 record de outra pasta; 17/09 yaml em config/ ->
    `config/data/curated`. Relativo passa a ser resolvido pela RAIZ (a pasta
    com pyproject.toml), com o yaml podendo morar em qualquer subpasta."""
    import os

    import yaml
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "x.parquet").write_text("", encoding="utf-8")
    (tmp_path / "config").mkdir()
    p = tmp_path / "config" / "ea.yaml"                  # yaml NAO esta' na raiz
    p.write_text(yaml.safe_dump({"tipo": "123", "semente_parquet": "data/x.parquet",
                                 "curated": "data", "registro_dir": "data/fw"}),
                 encoding="utf-8")
    cwd = os.getcwd()
    try:
        os.chdir("/")
        cfg = carregar_config_ea(p)
    finally:
        os.chdir(cwd)
    assert cfg.semente_parquet == str((tmp_path / "data" / "x.parquet").resolve())
    assert cfg.curated == str((tmp_path / "data").resolve())
    assert cfg.registro_dir == str((tmp_path / "data" / "fw").resolve())


def test_servico_recusa_subir_com_semente_invalida_e_gate_pedido(tmp_path: Path) -> None:
    """17/09: com semente invalida o EA subia INERTE e o dia se perdia. Se o
    yaml pede o gate, agora recusa."""
    import yaml
    p = tmp_path / "ea.yaml"
    p.write_text(yaml.safe_dump({
        "tipo": "123", "nome": "vb", "semente_parquet": str(tmp_path / "nao.parquet"),
        "curated": str(tmp_path / "nao"), "registro_dir": str(tmp_path / "fw"),
        "filtro_fluxo": {"tipo": "volume_baixo"}}), encoding="utf-8")
    cfg = EA123Config.from_yaml(p)
    with pytest.raises(SystemExit, match="semente da MME80 INVALIDA"):
        EA123Service(cfg, dia=dt.date(2026, 9, 16))


def test_replay_do_dia_roda_o_caminho_inteiro(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Replay sobre um dia curado: semente, perfil, gate, sinal, ciclo e
    diario, com dry_run FORCADO."""
    import numpy as np

    from profittape.ea import service_123 as sv
    from profittape.ea.config_123 import EA123Config
    from tests.test_ea_perfil_volume import _parquet_vol

    p, df = _parquet_vol(tmp_path, 25)
    df["mme80_ntsl"] = 139000.0
    df.to_parquet(p, index=False)
    alvo = sorted(df["dia"].unique())[-1]

    # tape do dia: um trade a cada 2 s, preco em passeio com passos de 5 pts
    rng = np.random.default_rng(7)
    t0 = int(pd.Timestamp(f"{alvo} 12:00:00", tz="UTC").value)
    n = 9000
    precos = 140000.0 + np.cumsum(rng.choice([-5.0, 0.0, 5.0], n))
    trades = pd.DataFrame({"ts_ns": [t0 + i * 2 * NS for i in range(n)], "price": precos,
                           "quantidade": 1, "trade_type": 2,
                           "agente_comprador": 0, "agente_vendedor": 0})
    (tmp_path / "curated" / "trade" / f"dt={alvo.isoformat()}" / "sym=WINFUT").mkdir(parents=True)
    monkeypatch.setattr(sv, "_carregar_dia", lambda pasta, sym: trades, raising=False)
    import profittape.features.pipeline as pipe
    monkeypatch.setattr(pipe, "_carregar_dia", lambda pasta, sym: trades)

    import yaml
    cfg_path = tmp_path / "ea.yaml"
    cfg_path.write_text(yaml.safe_dump({
        "tipo": "123", "nome": "ea_rep", "dry_run": False,        # sera' FORCADO para True
        "semente_parquet": str(p), "curated": str(tmp_path / "curated"),
        "registro_dir": str(tmp_path / "fw"),
        "filtro_fluxo": {"tipo": "volume_baixo"}}), encoding="utf-8")
    s = sv.replay_do_dia(EA123Config.from_yaml(cfg_path), alvo)
    assert s.ciclo.dry_run is True                                # forcado
    assert s.semente.valida and s.perfil is not None
    hb = s._hb()
    assert hb["trades"] == n and hb["barras"] >= 9
    assert hb["candidatos"] >= 0 and s.ciclo.estado == "livre"     # encerrar_dia zerou


def test_replay_fecha_exatamente_as_barras_do_dia(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TESTE ESCRITO ANTES DA CORRECAO (17/09, segunda tentativa no mesmo
    defeito): o replay de 16/09 fechou 3.022 barras num pregao de 38 porque
    o `tick` chamava `avancar_relogio` com um relogio que ja' estava alem da
    fronteira da barra em formacao. Em replay quem fecha barra e' o fluxo de
    TRADES; `avancar_relogio` so' existe para o ao vivo, onde o tempo passa
    sem negocio. Aqui: 6 h de trades a cada 2 s = 24 barras M15, e o teste
    exige 24 -- com o tick sendo chamado o tempo todo."""
    import numpy as np

    from profittape.ea import service_123 as sv
    from profittape.ea.config_123 import EA123Config
    from tests.test_ea_perfil_volume import _parquet_vol

    p, df = _parquet_vol(tmp_path, 25)
    df["mme80_ntsl"] = 139000.0
    df.to_parquet(p, index=False)
    alvo = sorted(df["dia"].unique())[-1]

    rng = np.random.default_rng(11)
    t0 = int(pd.Timestamp(f"{alvo} 12:00:00", tz="UTC").value)      # 09:00 BRT
    n = 6 * 3600 // 2                                               # 6 h, 1 trade a cada 2 s
    precos = 140000.0 + np.cumsum(rng.choice([-5.0, 0.0, 5.0], n))
    trades = pd.DataFrame({"ts_ns": [t0 + i * 2 * NS for i in range(n)], "price": precos,
                           "quantidade": 1, "trade_type": 2,
                           "agente_comprador": 0, "agente_vendedor": 0})
    (tmp_path / "curated" / "trade" / f"dt={alvo.isoformat()}" / "sym=WINFUT").mkdir(parents=True)
    import profittape.features.pipeline as pipe
    monkeypatch.setattr(pipe, "_carregar_dia", lambda pasta, sym: trades)

    import yaml
    cfg_path = tmp_path / "ea.yaml"
    cfg_path.write_text(yaml.safe_dump({
        "tipo": "123", "nome": "ea_bar", "dry_run": True,
        "semente_parquet": str(p), "curated": str(tmp_path / "curated"),
        "registro_dir": str(tmp_path / "fw")}), encoding="utf-8")
    # tick a CADA trade: o caso mais agressivo possivel
    s = sv.replay_do_dia(EA123Config.from_yaml(cfg_path), alvo, tick_a_cada=1)
    # 6 h = 24 barras; a ultima fica em formacao (o ultimo trade e' 2 s antes
    # do fim), entao 23 fechadas -- e nao 10.800, que era o que o tick fazia.
    assert s.barras == 23, f"esperava 23 barras fechadas em 6 h, veio {s.barras}"
    assert s.sinal.dia_completo is True


def test_replay_do_proprio_dia_nao_e_tratado_como_ao_vivo(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bug de 17/09 (terceira aparicao): o replay rodado a noite, sobre o
    pregao do MESMO dia, era lido como ao vivo -- o relogio de parede
    fechava uma barra por tick (3.022 num pregao de 37) e marcava a 1a
    barra parcial. `replay_do_dia` FORCA ao_vivo=False."""
    import numpy as np

    from profittape.ea import service_123 as sv
    from profittape.ea.config_123 import EA123Config
    from tests.test_ea_perfil_volume import _parquet_vol

    p, df = _parquet_vol(tmp_path, 25)
    df["mme80_ntsl"] = 139000.0
    df.to_parquet(p, index=False)
    alvo = sorted(df["dia"].unique())[-1]
    rng = np.random.default_rng(13)
    t0 = int(pd.Timestamp(f"{alvo} 12:00:00", tz="UTC").value)
    n = 6 * 3600 // 2
    precos = 140000.0 + np.cumsum(rng.choice([-5.0, 0.0, 5.0], n))
    trades = pd.DataFrame({"ts_ns": [t0 + i * 2 * NS for i in range(n)], "price": precos,
                           "quantidade": 1, "trade_type": 2,
                           "agente_comprador": 0, "agente_vendedor": 0})
    (tmp_path / "curated" / "trade" / f"dt={alvo.isoformat()}" / "sym=WINFUT").mkdir(parents=True)
    import profittape.features.pipeline as pipe
    monkeypatch.setattr(pipe, "_carregar_dia", lambda pasta, sym: trades)

    # o relogio do sistema diz que HOJE e' o dia do replay (o caso que quebrou)
    class _FakeDT(dt.datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[no-untyped-def]
            return dt.datetime.combine(alvo, dt.time(23, 33), tzinfo=tz)

    monkeypatch.setattr(sv.dt, "datetime", _FakeDT)
    import yaml
    cfg_path = tmp_path / "ea.yaml"
    cfg_path.write_text(yaml.safe_dump({
        "tipo": "123", "nome": "ea_noite", "dry_run": True,
        "semente_parquet": str(p), "curated": str(tmp_path / "curated"),
        "registro_dir": str(tmp_path / "fw")}), encoding="utf-8")
    s = sv.replay_do_dia(EA123Config.from_yaml(cfg_path), alvo, tick_a_cada=1)
    assert s.ao_vivo is False
    assert s.barras == 23, f"esperava 23 barras, veio {s.barras}"
    assert s.sinal.dia_completo is True


def test_ao_vivo_com_ea_atrasado_nao_fragmenta_a_barra(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """REPRODUZ o defeito de producao (17/09): AO VIVO, com o EA atras da
    fila, o relogio de parede esta' minutos a` frente da barra em formacao
    e `avancar_relogio` fechava a barra a cada tick -- `vol_total_t=329`
    numa barra M15 que teve 670.878 contratos. Aqui: 6 h de trades com
    timestamp 30 MIN atras do relogio, tick a cada trade, ao_vivo=True.
    Tem que fechar 23 barras (a ultima fica em formacao), nao milhares."""
    import numpy as np

    from profittape.ea import service_123 as sv
    from profittape.ea.config_123 import EA123Config
    from tests.test_ea_perfil_volume import _parquet_vol

    p, df = _parquet_vol(tmp_path, 25)
    df["mme80_ntsl"] = 139000.0
    df.to_parquet(p, index=False)
    alvo = sorted(df["dia"].unique())[-1]
    import yaml
    cfg_path = tmp_path / "ea.yaml"
    cfg_path.write_text(yaml.safe_dump({
        "tipo": "123", "nome": "ea_vivo", "dry_run": True,
        "semente_parquet": str(p), "curated": str(tmp_path / "curated"),
        "registro_dir": str(tmp_path / "fw")}), encoding="utf-8")
    (tmp_path / "curated").mkdir(exist_ok=True)

    # relogio de parede 30 min A FRENTE do ultimo trade (o EA atrasado)
    t0 = int(pd.Timestamp(f"{alvo} 12:00:00", tz="UTC").value)
    agora = [t0 / NS + 1800.0]
    monkeypatch.setattr(sv.time, "time", lambda: agora[0])
    s = sv.EA123Service(EA123Config.from_yaml(cfg_path), dia=alvo, ao_vivo=True)
    assert s.ao_vivo is True

    rng = np.random.default_rng(17)
    n = 6 * 3600 // 2
    precos = 140000.0 + np.cumsum(rng.choice([-5.0, 0.0, 5.0], n))
    for i in range(n):
        ts = t0 + i * 2 * NS
        agora[0] = ts / NS + 1800.0          # o relogio segue 30 min a frente
        s.processar_trade_bruto(sv._TradeBruto(ts, float(precos[i]), 1, 2))
        s._ultimo_tick = 0.0                 # forca o tick a cada trade
        s.tick()
    assert s.barras == 23, f"esperava 23 barras, veio {s.barras}"


def test_limpeza_na_subida_roda_uma_vez_quando_a_corretora_fica_pronta(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from profittape.ea import service_123 as sv

    class _Ciclo:
        def __init__(self) -> None:
            self.limpezas = 0
            self.reconc = 0

        def limpeza_na_subida(self) -> dict:
            self.limpezas += 1
            return {}

        def reconciliar_apos_reconexao(self) -> dict:
            self.reconc += 1
            return {}

        def tick(self) -> None:
            pass

    class _Cfg:
        dry_run = False

    class _Client:
        corretora_pronta = False

    s = sv.EA123Service.__new__(sv.EA123Service)
    s.config, s.client, s.ciclo = _Cfg(), _Client(), _Ciclo()
    s.ao_vivo, s._ultimo_ts_ns, s._ultimo_tick = False, 0, 0.0
    s._limpeza_feita, s._corretora_pronta_antes = False, None
    s.tick()
    assert s.ciclo.limpezas == 0                      # corretora ainda nao pronta
    s.client.corretora_pronta = True
    for _ in range(3):
        s._ultimo_tick = 0.0
        s.tick()
    assert s.ciclo.limpezas == 1                      # uma vez so'
    assert s.ciclo.reconc == 1                        # e a transicao False->True reconcilia
