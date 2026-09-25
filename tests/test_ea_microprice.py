"""EA de microprice / queue imbalance: nucleo puro, servico, replay e esteira."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from profittape.ea.config import EAConfig
from profittape.ea.config_123 import EA123Config, carregar_config_ea
from profittape.ea.config_microprice import EAMicropriceConfig
from profittape.ea.decisao import Acao
from profittape.ea.livro_ao_vivo import TopoDoLivro
from profittape.ea.service_microprice import EAMicropriceService, replay_tiny_book
from profittape.ea.sinal_microprice import (
    DecisorMicroprice,
    hhmm_brt,
    ler_topo,
    microprice,
)

MS = 1_000_000
S = 1_000_000_000
RAIZ = Path(__file__).resolve().parents[1]


def _ts(h: int, m: int, s: int = 0) -> int:
    """Hora BRT de 24/09/2026 em ns UTC."""
    return int(dt.datetime(2026, 9, 24, h + 3, m, s, tzinfo=dt.UTC).timestamp()) * S


T0 = _ts(10, 0)


def _cfg(**kw: object) -> EAMicropriceConfig:
    base: dict[str, object] = {"tipo": "microprice", "persistencia_ms": 300,
                               "cooldown_s": 0, "qtd_min_topo": 20}
    base.update(kw)
    return EAMicropriceConfig(**base)  # type: ignore[arg-type]


def _topo(bid: float, qb: int, ask: float, qa: int, ts: int) -> TopoDoLivro:
    return TopoDoLivro("WINFUT", bid, qb, ask, qa, ts)


# ---------------------------------------------------------------- formula
def test_microprice_conferido_a_mao() -> None:
    t = _topo(100000, 300, 100005, 100, T0)
    assert microprice(t) == pytest.approx(100003.75)
    # identidade que justifica o limiar em I, nao em ticks
    mid, spread = 100002.5, 5.0
    assert microprice(t) == pytest.approx(mid + t.desequilibrio * spread / 2)


def test_microprice_nunca_passa_de_meio_spread() -> None:
    for qb, qa in [(1, 10_000), (10_000, 1), (50, 50)]:
        m = microprice(_topo(100000, qb, 100005, qa, T0))
        assert m is not None and abs(m - 100002.5) <= 2.5


def test_hhmm_brt() -> None:
    assert hhmm_brt(_ts(9, 15)) == 915
    assert hhmm_brt(_ts(17, 20, 59)) == 1720


@pytest.mark.parametrize("topo,motivo", [
    (None, "sem_livro"),
    (_topo(100005, 50, 100005, 50, T0), "livro_cruzado"),
    (_topo(100000, 50, 100010, 50, T0), "spread_largo"),
    (_topo(100000, 5, 100005, 5, T0), "topo_raso"),
    (_topo(100000, 50, 100005, 50, T0 - 6 * S), "livro_velho"),
])
def test_filtros_do_topo(topo: TopoDoLivro | None, motivo: str) -> None:
    assert ler_topo(topo, _cfg(), T0).motivo == motivo


# ---------------------------------------------------------------- decisor
def test_persistencia_e_entrada_taker() -> None:
    d = DecisorMicroprice(_cfg())
    t = _topo(100000, 400, 100005, 100, T0)          # I = +0,6
    assert d.avaliar(t, T0).acao == Acao.NADA
    assert d.avaliar(t, T0 + 299 * MS).acao == Acao.NADA
    av = d.avaliar(t, T0 + 300 * MS)
    assert av.acao == Acao.COMPRAR and av.lado == 1
    assert av.preco == 100005                        # paga o ASK


def test_persistencia_reinicia_se_o_desbalanco_cai() -> None:
    d = DecisorMicroprice(_cfg())
    forte, fraco = (_topo(100000, 400, 100005, 100, T0),
                    _topo(100000, 100, 100005, 100, T0))
    d.avaliar(forte, T0)
    d.avaliar(fraco, T0 + 200 * MS)
    assert d.avaliar(forte, T0 + 350 * MS).acao == Acao.NADA   # recomecou
    assert d.avaliar(forte, T0 + 650 * MS).acao == Acao.COMPRAR


def test_venda_simetrica_paga_o_bid() -> None:
    d = DecisorMicroprice(_cfg())
    t = _topo(100000, 100, 100005, 400, T0)
    d.avaliar(t, T0)
    av = d.avaliar(t, T0 + 300 * MS)
    assert av.acao == Acao.VENDER and av.preco == 100000


def _comprado(cfg: EAMicropriceConfig | None = None) -> DecisorMicroprice:
    d = DecisorMicroprice(cfg or _cfg())
    d.abrir(1, 100005, T0, 0.6)
    return d


def test_saida_no_alvo_marca_pelo_bid_e_desconta_custo() -> None:
    d = _comprado()
    # mid subiu 3 ticks: bid 100015 -> bruto 10, ainda nao e' alvo (15)
    assert d.avaliar(_topo(100015, 400, 100020, 100, T0 + S), T0 + S).acao == Acao.NADA
    av = d.avaliar(_topo(100020, 400, 100025, 100, T0 + 2 * S), T0 + 2 * S)
    assert av.acao == Acao.ZERAR and av.motivo == "alvo" and av.preco == 100020
    campos = d.fechar(av.preco, T0 + 2 * S, av.motivo)
    assert campos["pnl_bruto"] == 15 and campos["pnl_liquido"] == 4


def test_mid_parado_da_menos_um_spread() -> None:
    """A conta que mata o taker: entrou e saiu no mesmo livro = -spread-custo."""
    d = _comprado()
    campos = d.fechar(100000, T0 + S, "teste")
    assert campos["pnl_bruto"] == -5 and campos["pnl_liquido"] == -16


def test_saida_por_imbalance_stop_e_tempo() -> None:
    d = _comprado()
    av = d.avaliar(_topo(100000, 100, 100005, 120, T0 + S), T0 + S)
    assert (av.acao, av.motivo) == (Acao.ZERAR, "imbalance_inverteu")

    d = _comprado()
    av = d.avaliar(_topo(99990, 400, 99995, 100, T0 + S), T0 + S)
    assert (av.acao, av.motivo) == (Acao.ZERAR, "stop")

    d = _comprado()
    av = d.avaliar(_topo(100005, 400, 100010, 100, T0 + 30 * S), T0 + 30 * S)
    assert (av.acao, av.motivo) == (Acao.ZERAR, "tempo")


def test_janela_de_entrada_e_zeragem_no_fim() -> None:
    d = DecisorMicroprice(_cfg())
    cedo = _ts(9, 10)
    t = _topo(100000, 400, 100005, 100, cedo)
    d.avaliar(t, cedo)
    assert d.avaliar(t, cedo + 400 * MS).motivo == "fora_da_janela"

    d = _comprado()
    fim = _ts(17, 20)
    av = d.avaliar(_topo(100005, 400, 100010, 100, fim), fim)
    # tempo tambem venceria; o que importa e' que zera
    assert av.acao == Acao.ZERAR


def test_lado_permitido_e_bloqueio_por_perdas() -> None:
    d = DecisorMicroprice(_cfg(lado_permitido="venda"))
    t = _topo(100000, 400, 100005, 100, T0)
    d.avaliar(t, T0)
    assert d.avaliar(t, T0 + 400 * MS).motivo == "lado_nao_permitido"

    d = DecisorMicroprice(_cfg(max_perdas_seguidas=2))
    for i in range(2):
        d.abrir(1, 100005, T0 + i * S, 0.6)
        d.fechar(100000, T0 + i * S + MS, "stop")
    assert d.stats.bloqueado
    t10 = _topo(100000, 400, 100005, 100, T0 + 10 * S)
    d.avaliar(t10, T0 + 10 * S)
    assert d.avaliar(t10, T0 + 11 * S).motivo == "bloqueado"


def test_sonda_mede_mid_a_favor_independente_da_posicao() -> None:
    d = DecisorMicroprice(_cfg(sonda_horizontes_s=[1.0]))
    t = _topo(100000, 400, 100005, 100, T0)
    d.avaliar(t, T0)
    d.avaliar(t, T0 + 300 * MS)                      # gatilho: mid 100002,5
    d.avaliar(_topo(100005, 400, 100010, 100, T0 + 1300 * MS), T0 + 1300 * MS)
    s = d.sonda.resumo()
    assert s["gatilhos"] == 1
    assert s["h1s"] == {"n": 1, "media_pts": 5.0, "pct_a_favor": 100.0, "pct_contra": 0.0}


# ---------------------------------------------------------------- servico
def test_replay_ponta_a_ponta_com_encerramento() -> None:
    cfg = _cfg(avaliacao_ms=1)
    ev = [(T0, 0, 100000.0, 400), (T0 + 2 * MS, 1, 100005.0, 100),
          (T0 + 400 * MS, 1, 100005.0, 100),         # persiste -> compra
          (T0 + 500 * MS, 0, 100020.0, 400),         # bid 100020... cruzado
          (T0 + 501 * MS, 1, 100025.0, 100)]         # -> alvo
    svc = replay_tiny_book(cfg, ev)
    r = svc.decisor.resumo()
    assert r["operacoes"] == 1 and r["saidas"] == {"alvo": 1}
    assert r["pnl_bruto_pts"] == 15.0 and not r["posicionado"]


def test_encerrar_dia_zera_posicao_aberta_no_topo() -> None:
    cfg = _cfg(avaliacao_ms=1)
    ev = [(T0, 0, 100000.0, 400), (T0 + 2 * MS, 1, 100005.0, 100),
          (T0 + 400 * MS, 1, 100005.0, 100)]
    svc = replay_tiny_book(cfg, ev)
    r = svc.decisor.resumo()
    assert r["operacoes"] == 1 and r["saidas"] == {"encerramento do dia": 1}
    assert r["pnl_bruto_pts"] == -5.0                  # saiu no bid


def test_servico_sem_livro_nunca_opera() -> None:
    relogio = [T0]
    svc = EAMicropriceService(_cfg(), livro=None, relogio=lambda: relogio[0], carimbo="t")
    for i in range(20):
        relogio[0] = T0 + i * 100 * MS
        svc.tick()
    assert svc.decisor.stats.operacoes == 0
    assert svc.decisor.stats.filtros["sem_livro"] > 0


def test_servico_com_vaga_recusada_nao_abre() -> None:
    class Vagas:
        def tentar_ocupar(self, *_: object, **__: object) -> bool:
            return False

        def liberar(self, *_: object) -> None: ...

    from profittape.domain.events import TinyBook
    from profittape.ea.livro_ao_vivo import EstadoDoLivro
    livro, relogio = EstadoDoLivro(), [T0]
    livro.atualizar(TinyBook(T0, "WINFUT", "F", 0, 100000.0, 400))
    livro.atualizar(TinyBook(T0, "WINFUT", "F", 1, 100005.0, 100))
    svc = EAMicropriceService(_cfg(), livro=livro, vagas=Vagas(),
                              relogio=lambda: relogio[0], carimbo="t")
    svc.tick()
    relogio[0] = T0 + 400 * MS
    svc.tick()
    assert svc.sem_vaga == 1 and svc.decisor.posicao is None


def test_dry_run_false_sem_executor_recusa() -> None:
    with pytest.raises(SystemExit):
        EAMicropriceService(_cfg(dry_run=False), carimbo="t")


# ---------------------------------------------------------------- esteira
def test_yaml_do_repositorio_carrega_como_microprice() -> None:
    cfg = carregar_config_ea(RAIZ / "config" / "ea_microprice.yaml")
    assert isinstance(cfg, EAMicropriceConfig) and cfg.dry_run


def test_campo_desconhecido_falha_alto(tmp_path: Path) -> None:
    p = tmp_path / "x.yaml"
    p.write_text('tipo: "microprice"\nlimiar_ticks: 2\n', encoding="utf-8")
    with pytest.raises(Exception, match="limiar_ticks"):
        carregar_config_ea(p)


def test_retrocompat_tipos_antigos_inalterados() -> None:
    assert isinstance(carregar_config_ea(RAIZ / "config" / "ea_123.yaml"), EA123Config)
    assert type(carregar_config_ea(RAIZ / "config" / "ea_venda_apenas.yaml")) is EAConfig


def test_registro_monta_o_servico_microprice() -> None:
    from profittape.ea.despachante import DespachanteDeEAs
    from profittape.ea.livro_ao_vivo import EstadoDoLivro
    from profittape.ea.registro import RegistroDeEAs
    from profittape.ea.supervisor import SupervisorDeRisco

    livro = EstadoDoLivro()
    reg = RegistroDeEAs(DespachanteDeEAs(), supervisor=SupervisorDeRisco(capital_em_conta=5000.0),
                        livro_ao_vivo=livro)
    r = reg.incluir(_cfg(nome="micro_t"))
    try:
        svc = r.bridge.ea_service
        assert isinstance(svc, EAMicropriceService) and svc.livro is livro
    finally:
        assert reg.remover("micro_t")
