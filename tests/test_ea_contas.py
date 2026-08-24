"""
Testes de ea/contas.py com um fake MINIMO, dedicado -- diferente do
FakeProfitDLL principal (que so' simula DLLInitializeMarketLogin, o
caminho de captura). GetAccount/DLLInitializeLogin sao conceitos de
roteamento, fora do escopo do fake principal.
"""

from __future__ import annotations

import threading
import time

from profittape.config import Credenciais
from profittape.ea.contas import ContaEncontrada, listar_contas


class _FakeLoginCompleto:
    """
    Simula: conecta com sucesso, GetAccount() dispara o AccountCallback
    (em thread separada, como a DLL real faria) com 2 contas -- uma demo,
    uma real, do jeito que viria de verdade.
    """

    def __init__(self, contas: list[tuple[int, str, str, str]] | None = None) -> None:
        self._contas = contas if contas is not None else [
            (85, "XP Investimentos CCTVM S/A", "999888", "DIEGO AUGUSTO"),
            (85, "XP Investimentos CCTVM S/A", "111222", "DIEGO AUGUSTO (SIMULADOR)"),
        ]
        self._cb_state = None
        self._cb_account = None
        self.finalizado = False

    def DLLInitializeLogin(self, activation_key, user, password,
                           cb_state, cb_history, cb_order_change, cb_account,
                           cb_new_trade, cb_new_daily, cb_price_book,
                           cb_offer_book, cb_history_trade, cb_progress,
                           cb_tiny_book):
        self._cb_state = cb_state
        self._cb_account = cb_account

        def _emitir():
            time.sleep(0.05)
            cb_state(0, 0)   # conectado

        threading.Thread(target=_emitir, daemon=True).start()
        return 0

    def GetAccount(self):
        def _emitir_contas():
            time.sleep(0.05)
            for corretora_id, nome, account_id, titular in self._contas:
                self._cb_account(corretora_id, nome, account_id, titular)
        threading.Thread(target=_emitir_contas, daemon=True).start()
        return 0

    def DLLFinalize(self):
        self.finalizado = True
        return 0


def _cred() -> Credenciais:
    return Credenciais(activation_key="k", user="u", password="p", dll_path="fake")


def test_listar_contas_encontra_demo_e_real() -> None:
    fake = _FakeLoginCompleto()
    contas = listar_contas(_cred(), timeout_s=5.0, dll_injetada=fake)

    assert len(contas) == 2
    assert all(isinstance(c, ContaEncontrada) for c in contas)
    ids = {c.account_id for c in contas}
    assert ids == {"999888", "111222"}
    assert fake.finalizado is True   # sempre desconecta no fim


def test_listar_contas_sem_nenhuma_conta_devolve_lista_vazia() -> None:
    fake = _FakeLoginCompleto(contas=[])
    contas = listar_contas(_cred(), timeout_s=5.0, dll_injetada=fake)
    assert contas == []


def test_login_com_erro_de_retorno_levanta() -> None:
    import pytest

    class _FakeRecusa:
        def DLLInitializeLogin(self, *a, **kw):
            return -1   # simula recusa (credencial errada, por exemplo)

    with pytest.raises(SystemExit, match="DLLInitializeLogin devolveu"):
        listar_contas(_cred(), timeout_s=1.0, dll_injetada=_FakeRecusa())


def test_nunca_conecta_levanta_apos_timeout() -> None:
    import pytest

    class _FakeMudo:
        def DLLInitializeLogin(self, *a, **kw):
            return 0   # aceita mas NUNCA chama cb_state

    with pytest.raises(SystemExit, match="Nao conectou"):
        listar_contas(_cred(), timeout_s=0.3, dll_injetada=_FakeMudo())
