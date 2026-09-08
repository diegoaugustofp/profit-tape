"""
E1 (2026-09-08): o record sobe com DLLInitializeLogin em vez de MarketLogin.

O unico degrau da trilha de execucao com impacto na captura. O que se
prova aqui, contra o FakeProfitDLL:
  - default: NADA muda (MarketLogin, contadores mudos, zero mudanca de
    comportamento para todo caller existente);
  - login_completo=True: chama DLLInitializeLogin com cada callback no
    SLOT CERTO (trocar dois compila e corrompe a pilha na DLL real),
    a captura continua identica, e a sessao de roteamento e' anunciada
    (AccountCallback) -- que e' o que o heartbeat do teste A vai ler;
  - DLL sem o export: falha CEDO, com mensagem, nao AttributeError.
"""
from __future__ import annotations

import pytest

from profittape.pipeline.bus import EventBus
from profittape.profitdll.client import ProfitClient
from profittape.profitdll.errors import LoginFailed
from profittape.testing.fake_dll import FakeProfitDLL


def _client(fake: FakeProfitDLL, **kw: object) -> ProfitClient:
    return ProfitClient(dll_path="x", activation_key="k", user="u", password="p",
                        bus=EventBus(), dll=fake, **kw)  # type: ignore[arg-type]


def test_default_continua_market_login_sem_nenhuma_mudanca() -> None:
    fake = FakeProfitDLL(eventos_por_ativo=1)
    c = _client(fake)
    c.connect(timeout_s=5)
    try:
        assert fake.modo_init == "market"
        assert c.login_completo is False
        assert c.conectado_market
        # no MarketLogin as callbacks de roteamento existem mas ficam mudas
        assert c.contadores_roteamento == {"ordem_mudanca": 0,
                                           "ordem_historico": 0, "conta": 0}
        assert c.contas_vistas == []
    finally:
        c.disconnect()


def test_login_completo_usa_dllinitializelogin_e_anuncia_contas() -> None:
    fake = FakeProfitDLL(eventos_por_ativo=1,
                         contas=((32006, "SIMULADOR", "DEMO-1"),
                                 (1234, "XP", "REAL-9")))
    c = _client(fake, login_completo=True)
    c.connect(timeout_s=5)
    try:
        assert fake.modo_init == "login"
        assert c.conectado_market          # a captura continua sendo o gate
        assert c.conectado_login           # e a sessao de roteamento subiu
        assert c.contadores_roteamento["conta"] == 2
        assert c.contas_vistas == [(32006, "DEMO-1"), (1234, "REAL-9")]
    finally:
        c.disconnect()


def test_cada_callback_no_slot_certo() -> None:
    """A armadilha real: self._cb['history'] e' THistoryTradeCallback
    (negocios, slot de MERCADO); o THistoryCallback de ORDENS e' outro.
    O fake guarda os slots com nomes distintos -- conferimos identidade."""
    fake = FakeProfitDLL(eventos_por_ativo=1)
    c = _client(fake, login_completo=True)
    c.connect(timeout_s=5)
    try:
        assert fake._cb["hist_ordem"] is c._cb["ordem_historico"]
        assert fake._cb["ordem_mudanca"] is c._cb["ordem_mudanca"]
        assert fake._cb["account"] is c._cb["conta"]
        assert fake._cb["hist"] is c._cb["history"]       # negocios, nao ordens
        assert fake._cb["trade"] is c._cb["trade"]
        assert fake._cb["state"] is c._cb["state"]
    finally:
        c.disconnect()


def test_captura_identica_nos_dois_modos() -> None:
    """O que o teste B do E1 vai medir ao vivo, medido aqui no fake:
    mesmo numero de trades chega ao bus nos dois logins."""
    def _contar(login_completo: bool) -> int:
        fake = FakeProfitDLL(eventos_por_ativo=200, seed=7)
        bus = EventBus()
        c = ProfitClient(dll_path="x", activation_key="k", user="u", password="p",
                         bus=bus, dll=fake, login_completo=login_completo)
        c.connect(timeout_s=5)
        try:
            c.subscribe_trades("WINFUT", "F")
            for th in fake._threads:            # o fake emite em thread propria
                th.join(timeout=5)
            total = 0
            while True:
                lote = bus.drain(timeout=0.3, max_batch=10_000)
                if not lote:
                    break
                total += len(lote)
            return total
        finally:
            c.disconnect()
    n_market, n_login = _contar(False), _contar(True)
    assert n_market == n_login == 200


def test_dll_sem_o_export_falha_cedo_com_mensagem() -> None:
    fake = FakeProfitDLL(eventos_por_ativo=1, com_login_completo=False)
    c = _client(fake, login_completo=True)
    with pytest.raises(LoginFailed, match="DLLInitializeLogin"):
        c.connect(timeout_s=5)
    assert fake.modo_init is None          # nao chegou a inicializar nada


def test_callbacks_de_roteamento_so_contam_nao_fazem_io() -> None:
    """Regra do arquivo client.py: callback nao faz trabalho. As tres
    novas sao chamaveis com qualquer coisa e so' incrementam."""
    from profittape.profitdll.types import TAssetIDRec
    fake = FakeProfitDLL(eventos_por_ativo=1)
    c = _client(fake, login_completo=True)
    c.connect(timeout_s=5)
    try:
        antes = dict(c.contadores_roteamento)
        ativo = TAssetIDRec("WINFUT", "F", 0)
        c._cb["ordem_mudanca"](ativo, 1, 1, 0, 1, 1, 100.0, 0.0, 0.0, 7,
                               "M", "DEMO-1", "T", "cl", "Filled", "d", "")
        c._cb["ordem_historico"](ativo, 1, 1, 0, 1, 1, 100.0, 0.0, 0.0, 7,
                                 "M", "DEMO-1", "T", "cl", "Filled", "d", "")
        assert c.contadores_roteamento["ordem_mudanca"] == antes["ordem_mudanca"] + 1
        assert c.contadores_roteamento["ordem_historico"] == antes["ordem_historico"] + 1
    finally:
        c.disconnect()
