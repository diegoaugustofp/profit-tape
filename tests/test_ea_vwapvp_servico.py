"""F3 do EA vwap_vp (docs/eas/vwap_vp.md): config, decisor e servico.
Exemplos do decisor conferidos a mao antes do assert."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from profittape.ea.config_123 import carregar_config_ea
from profittape.ea.config_vwapvp import EAVwapVpConfig
from profittape.ea.decisao import Acao
from profittape.ea.registro import usa_livro
from profittape.ea.service_vwapvp import replay_servico_do_dia
from profittape.ea.sinal import BarraFechada
from profittape.ea.sinal_vwapvp import DecisorVwapVp, hhmm_de
from profittape.research.vwapvp_replay import ParametrosReplay, Regra, simular_regras
from tests.test_ea_vwap_vp_f2 import _curated_dois_dias

NS = 1_000_000_000


def _cfg(**kw: object) -> EAVwapVpConfig:
    base = {"tipo": "vwap_vp", "nome": "t", "symbol": "WINFUT"}
    base.update(kw)
    return EAVwapVpConfig(**base)  # type: ignore[arg-type]


def _ts(hhmm: int, dia: dt.date = dt.date(2026, 9, 28)) -> int:
    h, m = divmod(hhmm, 100)
    return int(pd.Timestamp(f"{dia} {h:02d}:{m:02d}", tz="America/Sao_Paulo").value)


def _barra(hhmm_abre: int, close: float) -> BarraFechada:
    t0 = _ts(hhmm_abre)
    return BarraFechada(bar_id=1, ts_open_ns=t0, ts_close_ns=t0 + 300 * NS, open=close,
                        high=close, low=close, close=close, vol_agr=10, agf={},
                        vol_agr_compra=5, vol_agr_venda=5, n_trades=10, vol_total=10)


def test_config_do_yaml_do_repo_e_registro() -> None:
    raiz = Path(__file__).resolve().parents[1]        # outro teste da suite faz chdir
    cfg = carregar_config_ea(raiz / "config" / "ea_vwapvp_continuacao.yaml")
    assert isinstance(cfg, EAVwapVpConfig) and cfg.dry_run and cfg.janela_inicio_hhmm == 1100
    assert cfg.alvo_sd == 0.5 and cfg.stop_frac_dist == 0.5 and cfg.tempo_max_s == 3600
    assert not usa_livro(cfg)
    with pytest.raises(ValueError):
        _cfg(janela_inicio_hhmm=1700, janela_fim_hhmm=1100)
    with pytest.raises(ValueError):
        _cfg(zeragem_hhmm=1600)
    with pytest.raises(ValueError):
        _cfg(periodo_barra_s=420)
    with pytest.raises(ValueError):
        EAVwapVpConfig(tipo="vwap_vp", campo_inventado=1)  # type: ignore[call-arg]


def test_decisor_sinal_conferido_a_mao() -> None:
    """vwap 100000, sd 400: banda superior 100800. Barra das 11:05 fecha em
    100900 -> z 2,25 -> VENDER? NAO: fechou ACIMA da banda superior ->
    continuacao = COMPRAR (a favor). alvo = 100900 + 0,5x400 = 101100;
    stop = 100900 - 0,5x900 = 100450."""
    d = DecisorVwapVp(_cfg())
    av = d.avaliar_barra(_barra(1105, 100900.0), 100000.0, 400.0)
    assert av.acao == Acao.COMPRAR and av.lado == 1
    assert av.z == pytest.approx(2.25) and av.alvo_px == 101100.0 and av.stop_px == 100450.0
    # pendente: nova barra nao arma de novo
    assert d.avaliar_barra(_barra(1110, 101000.0), 100000.0, 400.0).motivo == "posicionado"
    # fora da janela (manha) e dentro da banda
    d2 = DecisorVwapVp(_cfg())
    assert d2.avaliar_barra(_barra(1030, 100900.0), 100000.0, 400.0).motivo == "fora_da_janela"
    assert d2.avaliar_barra(_barra(1105, 100500.0), 100000.0, 400.0).motivo == "fora_da_banda"
    assert d2.avaliar_barra(_barra(1105, 100900.0), None, None).motivo == "sem_vwap"
    # venda: fecha abaixo de -2 SD
    av2 = d2.avaliar_barra(_barra(1105, 99100.0), 100000.0, 400.0)
    assert av2.acao == Acao.VENDER and av2.lado == -1
    assert av2.alvo_px == 98900.0 and av2.stop_px == pytest.approx(99550.0)


def test_decisor_saidas_e_limites_conferidos_a_mao() -> None:
    cfg = _cfg(max_perdas_seguidas=2, cooldown_s=1800)
    d = DecisorVwapVp(cfg)
    d.avaliar_barra(_barra(1105, 100900.0), 100000.0, 400.0)
    p = d.abrir(100905.0, _ts(1110))
    assert p.hhmm_sinal == 1105
    assert p.alvo_px == 101100.0 and p.stop_px == 100450.0     # niveis do SINAL, nao do fill
    assert d.avaliar_preco(101000.0, _ts(1111)).acao == Acao.NADA
    assert d.avaliar_preco(101100.0, _ts(1112)).motivo == "alvo"
    assert d.avaliar_preco(100450.0, _ts(1112)).motivo == "stop"
    assert d.avaliar_preco(101000.0, _ts(1210)).motivo == "tempo"       # 60 min
    campos = d.fechar(101100.0, _ts(1115), "alvo")
    assert campos["pnl_bruto"] == pytest.approx(195.0) and campos["pnl_liquido"] == 184.0
    # cooldown de 30 min desde o sinal das 11:05 -> 11:20 ainda nao pode
    assert d.avaliar_barra(_barra(1120, 100950.0), 100000.0, 400.0).motivo == "cooldown"
    assert d.avaliar_barra(_barra(1140, 100950.0), 100000.0, 400.0).acao == Acao.COMPRAR
    d.abrir(100950.0, _ts(1145))
    d.fechar(100400.0, _ts(1150), "stop")
    d.avaliar_barra(_barra(1230, 100950.0), 100000.0, 400.0)
    d.abrir(100950.0, _ts(1235))
    d.fechar(100400.0, _ts(1240), "stop")
    assert d.stats.bloqueado == "2 perdas seguidas"
    assert d.avaliar_barra(_barra(1330, 100950.0), 100000.0, 400.0).motivo == "bloqueado"
    r = d.resumo()
    assert r["operacoes"] == 3 and r["saidas"] == {"alvo": 1, "stop": 2}
    # zeragem: posicao recente (menos de 60 min) as 18:01
    d3 = DecisorVwapVp(_cfg(janela_fim_hhmm=1800))
    assert d3.avaliar_barra(_barra(1730, 100900.0), 100000.0, 400.0).acao == Acao.COMPRAR
    d3.abrir(100905.0, _ts(1735))
    assert d3.avaliar_preco(100950.0, _ts(1801)).motivo == "zeragem"


def test_hhmm_de_usa_fuso_de_sao_paulo() -> None:
    assert hhmm_de(_ts(1105)) == 1105


def test_servico_replay_bate_com_o_simulador_no_mesmo_dia(tmp_path: Path) -> None:
    """O servico (codigo do vivo, dry_run) e o simulador de barras devem
    gerar os MESMOS sinais no mesmo dia: mesmo lado e mesma barra. Entrada
    e saida podem diferir (fill no 1o negocio; saida por negocio)."""
    cur = _curated_dois_dias(tmp_path)
    cfg = _cfg(janela_inicio_hhmm=930)       # o sintetico estica as 12:50; janela ampla
    svc = replay_servico_do_dia(cfg, dt.date(2026, 9, 25), cur)
    assert svc.barras >= 110 and svc.trades == 3390
    regra = {"cont": Regra("continuacao", "c_janela", "longe", 0.5, "sd", 0.5, "dist", 3600,
                           11.0, so_tarde=False)}
    sim = simular_regras(cur, "WINFUT", ParametrosReplay(hhmm_inicio=930),
                         cache_dir=tmp_path / "cache", regras=regra)
    t = sim["_trades"]["cont"]
    t = t[t["dia"] == "2026-09-25"]
    assert len(svc.operacoes) == len(t)
    if len(t):
        assert [o["lado"] for o in svc.operacoes] == list(t["lado"])
        assert [o["hhmm_sinal"] for o in svc.operacoes] == list(t["hhmm"])
        # entrada do servico = 1o negocio apos a barra: a <= 1 tick... nao garantido no
        # sintetico (passos de 5); exige so' que esteja a <= 2 passos do close do simulador
        for o, (_, s) in zip(svc.operacoes, t.iterrows(), strict=True):
            assert abs(o["entrada"] - s["entrada"]) <= 10.0


def test_cli_servico_replay(tmp_path: Path) -> None:
    from profittape.cli import app

    cur = _curated_dois_dias(tmp_path)
    yaml = tmp_path / "ea.yaml"
    yaml.write_text("tipo: vwap_vp\nnome: t\njanela_inicio_hhmm: 930\n", encoding="utf-8")
    r = CliRunner().invoke(app, ["ea-vwapvp-servico-replay", "--config", str(yaml),
                                 "--dia", "2026-09-25", "--curated", str(cur)])
    assert r.exit_code == 0, r.output
    assert "replay do servico" in r.output and "pnl liquido do dia" in r.output


def test_registro_inclui_vwap_vp_com_supervisor_e_bridge() -> None:
    """O caminho real do record: incluir() monta o servico pelo tipo, calcula
    a exigencia de capital (ramo default: stop_catastrofico do RiscoConfig)
    e liga no despachante. Sem --ea-livro-ao-vivo (usa_livro = False)."""
    from profittape.ea.despachante import DespachanteDeEAs
    from profittape.ea.registro import RegistroDeEAs
    from profittape.ea.supervisor import SupervisorDeRisco

    d = DespachanteDeEAs()
    reg = RegistroDeEAs(d, supervisor=SupervisorDeRisco(capital_em_conta=8000.0))
    r = reg.incluir(_cfg(nome="ea_vwapvp_continuacao"))
    assert r.nome == "ea_vwapvp_continuacao" and r.symbol == "WINFUT" and len(d) == 1
    assert type(r.bridge.ea_service).__name__ == "EAVwapVpService"
    assert reg.remover("ea_vwapvp_continuacao")
