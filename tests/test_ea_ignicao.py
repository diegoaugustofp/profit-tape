"""EA de ignicao: nucleo conferido a mao, bordas (janela, tempo, refratario,
fora de ordem, horario), fill pelo livro, servico, registro e -- o central --
EQUIVALENCIA com o estudo (`research/ignicao.py`) no mesmo tape."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from profittape.ea.config_123 import carregar_config_ea
from profittape.ea.config_ignicao import EAIgnicaoConfig
from profittape.ea.livro_ao_vivo import TopoDoLivro
from profittape.ea.service_ignicao import EAIgnicaoService, replay_trades
from profittape.ea.sinal_ignicao import DecisorIgnicao, Entrada, Saida, ancora_de
from profittape.research.ignicao import Tape, detectar
from profittape.research.leadlag import janela_do_dia

S = 1_000_000_000
DIA = "2026-09-24"
T0, _ = janela_do_dia(DIA, 915, 1700)
B = T0 + 600 * S                          # 09:25:00 BRT
RAIZ = Path(__file__).resolve().parents[1]


def _t(dt_s: float) -> int:
    return B + int(dt_s * S)


def _decisor(**kw: Any) -> DecisorIgnicao:
    return DecisorIgnicao(EAIgnicaoConfig(**kw))


def test_nucleo_conferido_a_mao() -> None:
    d = _decisor()
    assert d.novo_trade(_t(0), 188000) == []
    assert d.novo_trade(_t(59.9), 188400) == []               # sem janela ainda
    a = d.novo_trade(_t(60), 188500)                          # ref = negocio de 0 s
    assert len(a) == 1 and isinstance(a[0], Entrada)
    ign = a[0].ignicao
    assert (ign.direcao, ign.mov_pts, ign.referencia, ign.preco) == (1, 500, 188000, 188500)
    d.abrir(ign, 188505, _t(60))
    assert d.novo_trade(_t(100), 188600) == []                # sem barreira
    s = d.novo_trade(_t(1000), 189030)                        # +530 do preco de DETECCAO
    assert s == [Saida("alvo", 189030, _t(1000))]
    c = d.fechar(189025, _t(1000), "alvo", 189030)
    assert (c["pnl_bruto"], c["pnl_liquido"], c["desliz_entrada"], c["desliz_saida"]) == (
        520, 516.0, 5, 5)
    assert d.novo_trade(_t(1100), 189600) == []               # refratario ate' 60+1800


def test_referencia_e_o_ultimo_negocio_ate_t_menos_janela() -> None:
    d = _decisor()
    d.novo_trade(_t(0), 188000)
    d.novo_trade(_t(0), 188100)            # mesmo ts: vale o ULTIMO (como no estudo)
    d.novo_trade(_t(30), 187000)           # dentro da janela: nao e' referencia
    a = d.novo_trade(_t(60), 188600)
    assert a and isinstance(a[0], Entrada) and a[0].ignicao.referencia == 188100


def test_tempo_estrito_barreira_vale_no_instante_exato() -> None:
    for dt_s, esperado in [(3600.0, "alvo"), (3600.001, "tempo")]:
        d = _decisor()
        d.novo_trade(_t(0), 188000)
        ign = d.novo_trade(_t(60), 188500)[0].ignicao        # type: ignore[union-attr]
        d.abrir(ign, 188500, _t(60))
        s = d.novo_trade(_t(60 + dt_s), 189100)
        assert isinstance(s[0], Saida) and s[0].motivo == esperado


def test_stop_e_queda_simetrica() -> None:
    d = _decisor()
    d.novo_trade(_t(0), 188000)
    ign = d.novo_trade(_t(60), 187480)[0].ignicao             # type: ignore[union-attr]
    assert ign.direcao == -1
    d.abrir(ign, 187475, _t(60))
    assert d.novo_trade(_t(200), 188000) == []                # +520 contra: ainda nao
    s = d.novo_trade(_t(300), 188010)                         # +530 contra
    assert s == [Saida("stop", 188010, _t(300))]


def test_ignicao_com_posicao_aberta_e_limite_do_dia() -> None:
    d2 = _decisor(refratario_s=60, alvo_pts=5000, stop_pts=5000)
    d2.novo_trade(_t(0), 188000)
    ign2 = d2.novo_trade(_t(60), 188500)[0].ignicao           # type: ignore[union-attr]
    d2.abrir(ign2, 188500, _t(60))
    d2.novo_trade(_t(125), 188500)
    assert d2.novo_trade(_t(190), 189100) == []               # nova ignicao, posicionado
    assert d2.stats.ignoradas["posicionado"] == 1
    d3 = _decisor(refratario_s=60, max_operacoes_dia=1)
    d3.novo_trade(_t(0), 188000)
    ign3 = d3.novo_trade(_t(60), 188500)[0].ignicao           # type: ignore[union-attr]
    d3.abrir(ign3, 188500, _t(60))
    d3.novo_trade(_t(100), 189100)                            # alvo
    d3.fechar(189100, _t(100), "alvo", 189100)
    # 125 s TAMBEM e' ignicao: +600 contra o negocio de 60 s, refratario vencido
    assert d3.novo_trade(_t(125), 189100) == []
    assert d3.novo_trade(_t(190), 189700) == []
    assert d3.stats.ignoradas["limite_dia"] == 2 and d3.stats.detectadas == 3


def test_negocio_fora_de_ordem_e_descartado() -> None:
    d = _decisor()
    d.novo_trade(_t(0), 188000)
    d.novo_trade(_t(50), 188100)
    assert d.novo_trade(_t(10), 190000) == []                 # edicao com ts antigo
    assert d.stats.fora_de_ordem == 1
    assert d.novo_trade(_t(60), 188400) == []                 # ref segue 188000


def test_horario_de_deteccao() -> None:
    cedo = T0 - 300 * S                                       # 09:10
    d = _decisor()
    d.novo_trade(cedo, 188000)
    assert d.novo_trade(T0 + 59 * S, 188600) == []            # 09:15:59 < 09:16
    d = _decisor()
    d.novo_trade(cedo, 188000)
    assert d.novo_trade(T0 + 60 * S, 188600) != []            # 09:16:00 exato
    fim = janela_do_dia(DIA, 1700, 1700)[0]
    d = _decisor()
    d.novo_trade(fim - 120 * S, 188000)
    assert d.novo_trade(fim, 188600) == []                    # 17:00 exclusivo


def test_ancora() -> None:
    t1030 = janela_do_dia(DIA, 1030, 1030)[0]
    assert ancora_de(t1030 + 299 * S, [930, 1000, 1030, 1500], 5) == "10:30"
    assert ancora_de(t1030 + 300 * S, [930, 1000, 1030, 1500], 5) is None


# ------------------------------------------------ EQUIVALENCIA com o estudo
def _tape_com_ignicoes(seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Passeio aleatorio de 7 h com saltos ocasionais de 600 pts em 30 s."""
    rng = np.random.default_rng(seed)
    n = 7 * 3600 * 2                                          # negocio a cada 500 ms
    ts = T0 + np.arange(n, dtype=np.int64) * (S // 2)
    passos = rng.choice([-5.0, 0.0, 5.0], size=n, p=[0.3, 0.4, 0.3])
    for ini in rng.choice(np.arange(200, n - 200), size=25, replace=False):
        passos[ini:ini + 60] += rng.choice([-10.0, 10.0])     # +-600 em 30 s
    return ts, 188000 + np.cumsum(passos)


def _estudo(ts: np.ndarray, px: np.ndarray, cfg: EAIgnicaoConfig) -> list[Any]:
    vazio = Tape(np.empty(0, np.int64), np.empty(0), np.empty(0, np.int64),
                 np.empty(0, np.int64))
    tape = Tape(ts, px, np.ones(len(ts), np.int64), np.zeros(len(ts), np.int64))
    return detectar(tape, vazio, DIA, limiar_pts=cfg.limiar_pts, janela_s=cfg.janela_s,
                    refratario_s=cfg.refratario_s, conf_pts=1.0,
                    horizontes_s=[int(cfg.tempo_max_s)], alvo_pts=cfg.alvo_pts,
                    stop_pts=cfg.stop_pts, inicio_hhmm=cfg.inicio_hhmm,
                    fim_hhmm=cfg.fim_hhmm, barreira_s=cfg.tempo_max_s)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_equivalencia_com_o_estudo_sem_sobreposicao(seed: int) -> None:
    """Refratario >= tempo maximo: nenhuma ignicao cai com posicao aberta, e
    os DOIS LADOS tem de dar os mesmos eventos e as mesmas barreiras."""
    cfg = EAIgnicaoConfig(refratario_s=3600, max_operacoes_dia=99, zerar_ate_hhmm=2359)
    ts, px = _tape_com_ignicoes(seed)
    est = _estudo(ts, px, cfg)
    svc = replay_trades(cfg, zip(ts.tolist(), px.tolist(), strict=True))
    ops = svc.operacoes
    assert len(est) >= 5
    assert [o["ts_deteccao"] for o in ops] == [e.ts_ns for e in est]
    traduz = {"alvo": "alvo", "stop": "stop", "tempo": "nenhuma", "encerramento": "nenhuma"}
    assert [traduz[o["motivo"]] for o in ops] == [e.barreira for e in est]
    assert svc.decisor.stats.ignoradas == {}


def test_equivalencia_com_sobreposicao_ea_contido_no_estudo() -> None:
    """Config padrao (refratario 30 min < barreira 60): o EA ignora ignicao
    com posicao aberta, entao os eventos dele sao SUBCONJUNTO dos do estudo,
    e cada diferenca e' uma `ignorada_posicionado`."""
    cfg = EAIgnicaoConfig(max_operacoes_dia=99, zerar_ate_hhmm=2359)
    ts, px = _tape_com_ignicoes(4)
    est = _estudo(ts, px, cfg)
    svc = replay_trades(cfg, zip(ts.tolist(), px.tolist(), strict=True))
    ea = [o["ts_deteccao"] for o in svc.operacoes]
    assert set(ea) <= {e.ts_ns for e in est}
    assert len(est) - len(ea) == svc.decisor.stats.ignoradas.get("posicionado", 0)


def test_sobreposicao_construida_o_estudo_conta_e_o_ea_ignora() -> None:
    """Reforco: a semente 4 acima NAO teve sobreposicao (a propriedade passava
    com 0 == 0). Aqui ha' exatamente uma: 2a ignicao 1.850 s depois da 1a,
    com a posicao ainda aberta (preco parado, nenhuma barreira)."""
    cfg = EAIgnicaoConfig(max_operacoes_dia=99, zerar_ate_hhmm=2359)
    ts_l, px_l = [], []
    t, p = T0, 188000.0
    def andar(segundos: float, passo: float) -> None:
        nonlocal t, p
        for _ in range(int(segundos * 2)):
            t += S // 2
            p += passo
            ts_l.append(t)
            px_l.append(p)
    andar(300, 0.0)                    # 09:15-09:20 parado
    andar(30, 500 / 60)                # +500 em 30 s -> 1a ignicao
    andar(1850, 0.0)                   # parado: sem barreira, refratario vence
    andar(30, 500 / 60)                # +500 -> 2a ignicao, posicao aberta
    andar(600, 0.0)
    ts, px = np.array(ts_l, dtype=np.int64), np.round(np.array(px_l) / 5) * 5
    est = _estudo(ts, px, cfg)
    svc = replay_trades(cfg, zip(ts.tolist(), px.tolist(), strict=True))
    assert len(est) == 2 and len(svc.operacoes) == 1
    assert svc.decisor.stats.ignoradas == {"posicionado": 1}
    assert svc.operacoes[0]["ts_deteccao"] == est[0].ts_ns


def test_controle_negativo_verificador_reprova_regra_diferente() -> None:
    """O verificador de equivalencia DEVE reprovar se a regra divergir: com
    limiar diferente de um lado, as listas nao batem."""
    cfg = EAIgnicaoConfig(refratario_s=3600, max_operacoes_dia=99, zerar_ate_hhmm=2359)
    ts, px = _tape_com_ignicoes(1)
    est = _estudo(ts, px, cfg.model_copy(update={"limiar_pts": 450}))
    svc = replay_trades(cfg, zip(ts.tolist(), px.tolist(), strict=True))
    assert [o["ts_deteccao"] for o in svc.operacoes] != [e.ts_ns for e in est]


# --------------------------------------------------------------- servico
class _Livro:
    def __init__(self, topo: TopoDoLivro | None) -> None:
        self.topo = topo

    def ler(self, symbol: str) -> TopoDoLivro | None:
        return self.topo


class _Tr:
    def __init__(self, ts: int, px: float) -> None:
        self.ts_ns, self.price = ts, px


def _svc(topo: TopoDoLivro | None, agora: list[int]) -> EAIgnicaoService:
    return EAIgnicaoService(EAIgnicaoConfig(), livro=_Livro(topo),  # type: ignore[arg-type]
                            relogio=lambda: agora[0], carimbo="t")


@pytest.mark.parametrize("topo_kw,fill,origem", [
    ({"preco_bid": 188520.0, "preco_ask": 188525.0, "atraso": 0}, 188525.0, "livro"),
    ({"preco_bid": 188520.0, "preco_ask": 188525.0, "atraso": 3}, 188500.0, "tape"),
    ({"preco_bid": 188525.0, "preco_ask": 188525.0, "atraso": 0}, 188500.0, "tape"),
])
def test_fill_de_entrada_pelo_topo_ao_vivo(topo_kw: dict[str, Any], fill: float,
                                           origem: str) -> None:
    agora = [_t(62)]                         # processado 2 s depois (fila do bridge)
    topo = TopoDoLivro("WINFUT", topo_kw["preco_bid"], 10, topo_kw["preco_ask"], 10,
                       agora[0] - topo_kw["atraso"] * S)
    svc = _svc(topo, agora)
    svc.processar_trade_bruto(_Tr(_t(0), 188000))
    svc.processar_trade_bruto(_Tr(_t(60), 188500))
    p = svc.decisor.posicao
    assert p is not None and p.preco_fill == fill
    assert svc.fills[origem] == 1 and svc.atraso_max_s == pytest.approx(2.0)


def test_saida_vendendo_no_bid_e_encerramento() -> None:
    agora = [_t(62)]
    topo = TopoDoLivro("WINFUT", 188495.0, 10, 188500.0, 10, agora[0])
    svc = _svc(topo, agora)
    svc.processar_trade_bruto(_Tr(_t(0), 188000))
    svc.processar_trade_bruto(_Tr(_t(60), 188500))            # compra no ask 188500
    agora[0] = _t(700)
    svc.livro.topo = TopoDoLivro("WINFUT", 189020.0, 10, 189025.0, 10,  # type: ignore[union-attr]
                                 agora[0])
    svc.processar_trade_bruto(_Tr(_t(699), 189030))           # alvo pelo tape
    op = svc.operacoes[-1]
    assert (op["motivo"], op["saida"], op["pnl_bruto"], op["desliz_saida"]) == (
        "alvo", 189020.0, 520.0, 10.0)
    svc.processar_trade_bruto(_Tr(_t(2000), 189030))
    svc.processar_trade_bruto(_Tr(_t(2060), 189600))          # nova ignicao
    svc.encerrar_dia()
    assert svc.operacoes[-1]["motivo"] == "encerramento"
    assert svc.decisor.posicao is None


def test_tick_fecha_por_tempo_sem_negocio() -> None:
    agora = [_t(60)]
    svc = _svc(None, agora)
    svc.processar_trade_bruto(_Tr(_t(0), 188000))
    svc.processar_trade_bruto(_Tr(_t(60), 188500))
    agora[0] = _t(60 + 3601)
    svc.tick()
    assert svc.operacoes[-1]["motivo"] == "tempo"
    assert svc.fills == {"livro": 0, "tape": 2, "executor": 0}


def test_dry_run_false_sem_executor_recusa() -> None:
    with pytest.raises(SystemExit):
        EAIgnicaoService(EAIgnicaoConfig(dry_run=False), carimbo="t")


def test_config_valida_horarios() -> None:
    with pytest.raises(ValueError, match="fim_hhmm"):
        EAIgnicaoConfig(inicio_hhmm=1700, fim_hhmm=915)
    with pytest.raises(ValueError, match="zerar_ate_hhmm"):
        EAIgnicaoConfig(zerar_ate_hhmm=1600)
    with pytest.raises(ValueError):
        EAIgnicaoConfig(limiar_pts=500, alvo_extra=1)          # type: ignore[call-arg]


def test_yaml_do_repositorio_carrega_com_os_numeros_do_estudo() -> None:
    cfg = carregar_config_ea(RAIZ / "config" / "ea_ignicao.yaml")
    assert isinstance(cfg, EAIgnicaoConfig) and cfg.dry_run
    assert (cfg.limiar_pts, cfg.janela_s, cfg.alvo_pts, cfg.stop_pts, cfg.tempo_max_s,
            cfg.refratario_s) == (500, 60, 530, 530, 3600, 1800)


def test_registro_monta_o_servico_ignicao() -> None:
    from profittape.ea.despachante import DespachanteDeEAs
    from profittape.ea.livro_ao_vivo import EstadoDoLivro
    from profittape.ea.registro import RegistroDeEAs
    from profittape.ea.supervisor import SupervisorDeRisco

    livro = EstadoDoLivro()
    reg = RegistroDeEAs(DespachanteDeEAs(), supervisor=SupervisorDeRisco(capital_em_conta=5000.0),
                        livro_ao_vivo=livro)
    r = reg.incluir(EAIgnicaoConfig(nome="ign_t"))
    try:
        svc = r.bridge.ea_service
        assert isinstance(svc, EAIgnicaoService) and svc.livro is livro
    finally:
        assert reg.remover("ign_t")


def test_cli_replay_lado_a_lado_sem_divergencia(tmp_path: Path) -> None:
    import pandas as pd
    from typer.testing import CliRunner

    from profittape.cli import app

    ts, px = _tape_com_ignicoes(1)
    pasta = tmp_path / "trade" / f"dt={DIA}" / "sym=WINFUT"
    pasta.mkdir(parents=True)
    pd.DataFrame({"ts_ns": ts, "trade_id": np.arange(len(ts)), "price": px,
                  "quantidade": 1, "trade_type": 2}).to_parquet(pasta / "part-0000.parquet")
    yml = tmp_path / "ea.yaml"
    yml.write_text("tipo: ignicao\nrefratario_s: 3600\nmax_operacoes_dia: 99\n"
                   "zerar_ate_hhmm: 2359\n", encoding="utf-8")
    r = CliRunner().invoke(app, ["ea-ignicao-replay", str(yml), "--raw", str(tmp_path)])
    assert r.exit_code == 0, r.output
    assert "[1/1] 2026-09-24  EA ops=6" in r.output and "estudo eventos=6" in r.output
    assert "eventos SO' NO EA (nao deveria haver): 0" in r.output
    assert "EA: alvo=4 stop=1" in r.output and "ESTUDO: alvo=4 stop=1" in r.output
    r = CliRunner().invoke(app, ["ea-ignicao-replay", str(tmp_path / "ea.yaml"),
                                 "--raw", str(tmp_path), "--dias", "2020-01-01"])
    assert r.exit_code != 0                                   # nenhum pregao
