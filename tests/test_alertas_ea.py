"""Avisos do EA no Telegram (v4.04): armou / encerrou.

Duas coisas a provar:
  1. o notificador NUNCA segura a thread do EA (Telegram lento ou fora do
     ar nao pode atrasar o tape nem a gestao do stop);
  2. cada um dos cinco EAs avisa ao armar e ao encerrar -- e, sem
     `ligar_avisos_ea`, nao avisa nada (replay/CLI/testes em silencio).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator

import pytest

from profittape import alertas
from profittape.alertas import (
    ConfigAlertas,
    NotificadorAssincrono,
    avisar_ea,
    ea_armou,
    ea_encerrou,
)

_CFG = ConfigAlertas(bot_token="x", chat_id="y")


class _Captura:
    def __init__(self) -> None:
        self.textos: list[str] = []

    def avisar(self, texto: str) -> None:
        self.textos.append(texto)

    def com(self, trecho: str) -> list[str]:
        return [t for t in self.textos if trecho in t]


@pytest.fixture
def captura() -> Iterator[_Captura]:
    c = _Captura()
    alertas._notificador_ea = c  # type: ignore[assignment]
    yield c
    alertas._notificador_ea = None


# ------------------------------------------------------------ notificador
def test_avisar_nao_bloqueia_com_telegram_travado() -> None:
    liberar = threading.Event()
    enviados: list[str] = []

    def envio_travado(texto: str, cfg: ConfigAlertas | None) -> bool:
        liberar.wait(5)
        enviados.append(texto)
        return True

    n = NotificadorAssincrono(_CFG, maxsize=3, envio=envio_travado)
    t0 = time.monotonic()
    for i in range(10):
        n.avisar(f"m{i}")
    assert time.monotonic() - t0 < 0.5              # nunca espera o HTTP
    # 1 na mao da thread + 3 na fila; o resto descartado e contado
    assert n.descartados >= 6 and n.enfileirados + n.descartados == 10
    liberar.set()
    n.parar(timeout_s=5)
    assert enviados[0] == "m0" and len(enviados) == n.enfileirados
    assert n.enviados == n.enfileirados and n.falhas == 0


def test_envio_que_levanta_nao_mata_a_thread() -> None:
    chamadas: list[str] = []

    def envio(texto: str, cfg: ConfigAlertas | None) -> bool:
        chamadas.append(texto)
        if texto == "a":
            raise RuntimeError("boom")
        return False

    n = NotificadorAssincrono(_CFG, envio=envio)
    n.avisar("a")
    n.avisar("b")
    n.parar(timeout_s=5)
    assert chamadas == ["a", "b"] and n.falhas == 2


def test_parar_com_telegram_fora_do_ar_respeita_o_teto() -> None:
    n = NotificadorAssincrono(_CFG, envio=lambda t, c: time.sleep(10) or True)
    n.avisar("x")
    t0 = time.monotonic()
    n.parar(timeout_s=0.3)
    assert time.monotonic() - t0 < 2


def test_desligado_e_no_op() -> None:
    assert alertas._notificador_ea is None
    avisar_ea("nada")                  # nao levanta, nao faz nada
    ea_armou("x", 1, 100.0, dry_run=True)
    ea_encerrou("x", "alvo", 1.0, dry_run=True)


def test_ligar_sem_config_fica_desligado() -> None:
    alertas.ligar_avisos_ea(None)
    assert alertas._notificador_ea is None


def test_ligar_e_desligar() -> None:
    alertas.ligar_avisos_ea(_CFG)
    try:
        assert isinstance(alertas._notificador_ea, NotificadorAssincrono)
    finally:
        alertas.desligar_avisos_ea(timeout_s=2)
    assert alertas._notificador_ea is None


# --------------------------------------------------------------- formato
def test_formato_armou_e_encerrou(captura: _Captura) -> None:
    ea_armou("ea_123", "compra", 140055.0, dry_run=True, alvo=140315.0, stop=139795.0,
             detalhe="stop de entrada")
    ea_armou("vwap", -1, 130000.0, dry_run=False)
    ea_encerrou("ea_123", "alvo", 255.0, dry_run=True, pnl_dia=255.0)
    ea_encerrou("vwap", "stop", -40.5, dry_run=False)
    ea_encerrou("ea_123", "nao_executou", None, dry_run=True)
    assert captura.textos == [
        "🎯 [SIMULADO] ea_123 armou COMPRA @ 140055 | alvo 140315 | stop 139795"
        " | stop de entrada",
        "🎯 [REAL] vwap armou VENDA @ 130000 | alvo - | stop -",
        "🟢 [SIMULADO] ea_123 encerrou (alvo) +255.0 pts | dia +255.0 pts",
        "🔴 [REAL] vwap encerrou (stop) -40.5 pts",
        "⚪ [SIMULADO] ea_123 encerrou (nao_executou) sem P&L",
    ]


def test_formato_com_dado_estranho_nao_levanta(captura: _Captura) -> None:
    ea_armou("x", object(), "nao-numero", dry_run=True)  # type: ignore[arg-type]
    ea_encerrou("x", "?", "nao-numero", dry_run=True)
    assert captura.textos == []        # engoliu e logou; o EA segue


# ------------------------------------------------- os cinco EAs, ponta a ponta
def test_123_avisa_armou_e_encerrou_no_alvo(captura: _Captura) -> None:
    from tests.test_ea_ciclo_123 import NS, P15, T0900, _armar_compra, _ciclo
    c = _ciclo()
    _armar_compra(c)
    assert captura.com("armou COMPRA @ 140055 | alvo 140315 | stop 139795")
    t = T0900 + 3 * P15
    c.on_trade(t + 2 * NS, 140060.0)
    c.on_trade(t + 3 * NS, 140320.0)
    assert captura.com("encerrou (alvo) +255.0 pts")
    assert len(captura.textos) == 2


def test_123_avisa_encerramento_sem_execucao(captura: _Captura) -> None:
    from tests.test_ea_ciclo_123 import NS, P15, T0900, _armar_compra, _ciclo
    c = _ciclo()
    _armar_compra(c)
    c.on_trade(T0900 + 3 * P15 + NS, 140000.0)
    c.on_trade(T0900 + 4 * P15, 140000.0)
    assert captura.com("encerrou (nao_executou) sem P&L")


def test_ignicao_avisa_entrada_e_saida(captura: _Captura) -> None:
    from profittape.ea.livro_ao_vivo import TopoDoLivro
    from tests.test_ea_ignicao import _svc, _t, _Tr
    agora = [_t(62)]
    svc = _svc(TopoDoLivro("WINFUT", 188495.0, 10, 188500.0, 10, agora[0]), agora)
    svc.processar_trade_bruto(_Tr(_t(0), 188000))
    svc.processar_trade_bruto(_Tr(_t(60), 188500))
    assert len(captura.com("[SIMULADO]")) == 1 and captura.com("armou COMPRA @ 188500")
    agora[0] = _t(700)
    svc.livro.topo = TopoDoLivro("WINFUT", 189020.0, 10, 189025.0, 10,  # type: ignore[union-attr]
                                 agora[0])
    svc.processar_trade_bruto(_Tr(_t(699), 189030))
    op = svc.operacoes[-1]
    assert captura.com(f"encerrou (alvo) {op['pnl_liquido']:+.1f} pts")


def test_microprice_avisa_entrada_e_encerramento_do_dia(captura: _Captura) -> None:
    from profittape.ea.service_microprice import replay_tiny_book
    from tests.test_ea_microprice import MS, T0, _cfg
    ev = [(T0, 0, 100000.0, 400), (T0 + 2 * MS, 1, 100005.0, 100),
          (T0 + 400 * MS, 1, 100005.0, 100)]
    replay_tiny_book(_cfg(avaliacao_ms=1), ev)
    assert len(captura.com("armou COMPRA")) == 1
    assert len(captura.com("encerrou (encerramento do dia)")) == 1


def test_vwapvp_avisa_cada_operacao(captura: _Captura, tmp_path) -> None:  # type: ignore[no-untyped-def]
    import datetime as dt

    from profittape.ea.service_vwapvp import replay_servico_do_dia
    from tests.test_ea_vwap_vp_f2 import _curated_dois_dias
    from tests.test_ea_vwapvp_servico import _cfg
    svc = replay_servico_do_dia(_cfg(janela_inicio_hhmm=930), dt.date(2026, 9, 25),
                                _curated_dois_dias(tmp_path))
    assert len(captura.com(" armou ")) == len(svc.operacoes)
    assert len(captura.com(" encerrou ")) == len(svc.operacoes)


def test_fluxo_avisa_abertura_e_fechamento(captura: _Captura) -> None:
    from profittape.ea.service import EAService
    from tests.test_ea_service import _alimentar, _config
    svc = EAService(_config())
    _alimentar(svc, 4000)
    svc.encerrar_dia()
    n = len(svc.gestor.historico_detalhado)
    assert n > 0, "o sintetico precisa gerar ao menos uma operacao"
    assert len(captura.com(" armou ")) == n
    assert len(captura.com(" encerrou ")) == n
