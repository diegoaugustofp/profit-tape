"""
Testes de ExecutorDeOrdens com DLL falsa. O teste que mais importa aqui e'
a ORDEM DOS ARGUMENTOS do SendZeroPositionAtMarket — a senha vem em 5o
lugar (depois de ticker/bolsa), DIFERENTE das Send*Order onde vem em 3o.
Armadilha real do manual, conferida caractere a caractere; um erro aqui
corromperia a chamada em silencio no Windows real.
"""

from __future__ import annotations

import pytest

from profittape.ea.config import RoteamentoConfig, SinalConfig
from profittape.ea.decisao import decidir
from profittape.ea.execucao import ExecutorDeOrdens, executar

_SINAL = SinalConfig(feature="z_agf_3", horizonte=3, agent_id=3,
                     threshold_entrada=1.0, direcao="contrarian")


class _FakeDllOrdens:
    """Registra cada chamada com os argumentos NA ORDEM em que chegaram."""

    def __init__(self, retorno: int = 12345) -> None:
        self.retorno = retorno
        self.chamadas: list[tuple[str, tuple]] = []

    def SendMarketBuyOrder(self, *args):
        self.chamadas.append(("SendMarketBuyOrder", args))
        return self.retorno

    def SendMarketSellOrder(self, *args):
        self.chamadas.append(("SendMarketSellOrder", args))
        return self.retorno

    def SendZeroPositionAtMarket(self, *args):
        self.chamadas.append(("SendZeroPositionAtMarket", args))
        return self.retorno


def _rot() -> RoteamentoConfig:
    # Corretoras DIFERENTES por conta, como a licenca real (2026-08-31):
    # demo=32006 'Simulador', real=1003 'XP'. A fixture antiga tinha uma
    # corretora unica ('85'), o que escondia a troca.
    return RoteamentoConfig(senha_roteamento="s3nh4",
                            id_account_demo="DEMO123", id_corretora_demo="85",
                            id_account_real="REAL456", id_corretora_real="1003")


def _executor(dll, usar_conta_real: bool = False) -> ExecutorDeOrdens:
    return ExecutorDeOrdens(dll, _rot(), ticker="WINFUT", bolsa="F",
                            quantidade=1, usar_conta_real=usar_conta_real)


def test_comprar_chama_market_buy_com_conta_demo_por_default() -> None:
    dll = _FakeDllOrdens()
    ex = _executor(dll)
    d = decidir(_SINAL, valor_atual=-1.5, posicao_atual=0)   # contrarian: compra
    r = ex.executar(d)

    assert r.enviada and r.ordem_id == 12345
    nome, args = dll.chamadas[0]
    assert nome == "SendMarketBuyOrder"
    # ordem dos argumentos das Send*Order: conta, corretora, senha, ticker, bolsa, qtd
    assert args == ("DEMO123", "85", "s3nh4", "WINFUT", "F", 1)


def test_vender_chama_market_sell() -> None:
    dll = _FakeDllOrdens()
    ex = _executor(dll)
    d = decidir(_SINAL, valor_atual=1.5, posicao_atual=0)    # contrarian: vende
    r = ex.executar(d)
    assert r.enviada
    assert dll.chamadas[0][0] == "SendMarketSellOrder"


def test_zerar_usa_ordem_de_argumentos_DIFERENTE_senha_em_quinto() -> None:
    """A armadilha do manual: SendZeroPositionAtMarket recebe
    (conta, corretora, TICKER, BOLSA, senha) — senha em 5o, nao em 3o."""
    dll = _FakeDllOrdens()
    ex = _executor(dll)
    d = decidir(_SINAL, valor_atual=1.5, posicao_atual=3)    # comprado + sinal contra -> zera
    r = ex.executar(d)

    assert r.enviada
    nome, args = dll.chamadas[0]
    assert nome == "SendZeroPositionAtMarket"
    assert args == ("DEMO123", "85", "WINFUT", "F", "s3nh4")


def test_conta_real_exige_flag_explicita() -> None:
    dll = _FakeDllOrdens()
    ex = _executor(dll, usar_conta_real=True)
    d = decidir(_SINAL, valor_atual=1.5, posicao_atual=0)
    ex.executar(d)
    assert dll.chamadas[0][1][0] == "REAL456"


def test_retorno_negativo_da_dll_vira_recusa_nao_excecao() -> None:
    """Ordem recusada e' um estado NORMAL de operacao (ex.: fora de horario,
    saldo, ativo bloqueado) — reporta e loga, nao crasha o EA inteiro."""
    dll = _FakeDllOrdens(retorno=-2147483647)
    ex = _executor(dll)
    d = decidir(_SINAL, valor_atual=1.5, posicao_atual=0)
    r = ex.executar(d)
    assert not r.enviada
    assert r.ordem_id is None
    assert "RECUSADA" in r.motivo


def test_acao_nada_nao_chama_dll() -> None:
    dll = _FakeDllOrdens()
    ex = _executor(dll)
    d = decidir(_SINAL, valor_atual=0.2, posicao_atual=0)    # zona neutra
    r = ex.executar(d)
    assert not r.enviada
    assert dll.chamadas == []


def test_construcao_falha_cedo_sem_senha_roteamento() -> None:
    """Config invalida falha na CONSTRUCAO, nao no meio do pregao na
    primeira ordem."""
    rot = RoteamentoConfig(senha_roteamento="", id_corretora="85",
                           id_account_demo="DEMO123")
    with pytest.raises(SystemExit, match="SENHA_ROTEAMENTO"):
        ExecutorDeOrdens(_FakeDllOrdens(), rot, "WINFUT", "F", 1)


def test_construcao_falha_cedo_com_quantidade_invalida() -> None:
    with pytest.raises(ValueError, match="positiva"):
        ExecutorDeOrdens(_FakeDllOrdens(), _rot(), "WINFUT", "F", 0)


def test_executar_com_executor_delega_quando_dry_run_falso() -> None:
    dll = _FakeDllOrdens()
    ex = _executor(dll)
    d = decidir(_SINAL, valor_atual=1.5, posicao_atual=0)
    r = executar(d, dry_run=False, executor=ex)
    assert r is not None and r.enviada
    assert len(dll.chamadas) == 1


def test_executar_dry_run_nunca_toca_dll_mesmo_com_executor() -> None:
    """dry_run=True e' a camada 1: mesmo com executor valido em maos,
    NAO envia — so' loga."""
    dll = _FakeDllOrdens()
    ex = _executor(dll)
    d = decidir(_SINAL, valor_atual=1.5, posicao_atual=0)
    r = executar(d, dry_run=True, executor=ex)
    assert r is None
    assert dll.chamadas == []
