"""
Testes de ExecutorDeOrdens com DLL falsa. Dois grupos: a ORDEM DOS
ARGUMENTOS do SendZeroPositionAtMarket (senha em 5o lugar, DIFERENTE das
Send*Order onde vem em 3o -- armadilha real do manual, conferida
caractere a caractere) e a trava `exigir_conta_anunciada` (E4,
2026-09-11) -- par (corretora, conta) tem que ter sido anunciado pela
DLL, testado com a mesma seriedade do que precisa passar.
"""

from __future__ import annotations

import time

import pytest

from profittape.ea.config import RoteamentoConfig, SinalConfig
from profittape.ea.decisao import decidir
from profittape.ea.execucao import ExecutorDeOrdens, executar
from profittape.ea.ordem_teste import TravaSimulacao
from profittape.profitdll.client import EventoOrdem

_SINAL = SinalConfig(
    feature="z_agf_3", horizonte=3, agent_id=3, threshold_entrada=1.0, direcao="contrarian"
)


class _FakeDllOrdens:
    """Registra cada chamada com os argumentos NA ORDEM em que chegaram.
    Se `emitir_fill` estiver ligado, agenda um EventoOrdem de fill no
    client dono (via `_client_dono`), simulando o OrderChangeCallback."""

    def __init__(
        self, retorno: int = 12345, emitir_fill: bool = True, preco_fill: float = 140000.0
    ) -> None:
        self.retorno = retorno
        self.chamadas: list[tuple[str, tuple]] = []
        self.emitir_fill = emitir_fill
        self.preco_fill = preco_fill
        self._client_dono: _FakeClient | None = None

    def _registrar(self, nome: str, args: tuple) -> int:
        self.chamadas.append((nome, args))
        if self.emitir_fill and self._client_dono is not None and self.retorno > 0:
            self._client_dono.ordens_eventos.append(
                EventoOrdem(
                    t_mono=time.monotonic(),
                    profit_id=self.retorno,
                    corretora=0,
                    conta="",
                    ticker="",
                    qtd=1,
                    executada=1,
                    restante=0,
                    lado=0,
                    preco=self.preco_fill,
                    preco_medio=self.preco_fill,
                    status="Filled",
                    texto="",
                    data="",
                )
            )
        return self.retorno

    def SendMarketBuyOrder(self, *args):
        return self._registrar("SendMarketBuyOrder", args)

    def SendMarketSellOrder(self, *args):
        return self._registrar("SendMarketSellOrder", args)

    def SendZeroPositionAtMarket(self, *args):
        return self._registrar("SendZeroPositionAtMarket", args)


class _FakeClient:
    """O suficiente de ProfitClient para ExecutorDeOrdens: `_dll`,
    `contas_vistas` (a trava), `ordens_eventos` (confirmacao de fill)."""

    def __init__(self, dll: _FakeDllOrdens, contas_vistas: list[tuple[int, str]]) -> None:
        self._dll = dll
        self.contas_vistas = contas_vistas
        self.nomes_corretoras: dict[int, str] = {}
        self.ordens_eventos: list[EventoOrdem] = []
        dll._client_dono = self


def _rot() -> RoteamentoConfig:
    # Corretoras DIFERENTES por conta, como a licenca real (2026-08-31):
    # demo=32006 'Simulador', real=1003 'XP'. A fixture antiga tinha uma
    # corretora unica ('85'), o que escondia a troca.
    return RoteamentoConfig(
        senha_roteamento="s3nh4",
        id_account_demo="DEMO123",
        id_corretora_demo="85",
        id_account_real="REAL456",
        id_corretora_real="1003",
    )


def _client(
    dll: _FakeDllOrdens | None = None, contas_vistas: list[tuple[int, str]] | None = None
) -> _FakeClient:
    dll = dll or _FakeDllOrdens()
    vistas = contas_vistas if contas_vistas is not None else [(85, "DEMO123"), (1003, "REAL456")]
    return _FakeClient(dll, vistas)


def _executor(
    client: _FakeClient, usar_conta_real: bool = False, timeout_fill_s: float = 2.0
) -> ExecutorDeOrdens:
    return ExecutorDeOrdens(
        client,
        _rot(),
        ticker="WINV26",
        bolsa="F",
        quantidade=1,
        usar_conta_real=usar_conta_real,
        timeout_fill_s=timeout_fill_s,
    )


def test_comprar_chama_market_buy_com_conta_demo_por_default() -> None:
    c = _client()
    ex = _executor(c)
    d = decidir(_SINAL, valor_atual=-1.5, posicao_atual=0)  # contrarian: compra
    r = ex.executar(d)

    assert r.enviada and r.ordem_id == 12345
    nome, args = c._dll.chamadas[0]
    assert nome == "SendMarketBuyOrder"
    # ordem dos argumentos das Send*Order: conta, corretora, senha, ticker, bolsa, qtd
    assert args == ("DEMO123", "85", "s3nh4", "WINV26", "F", 1)


def test_vender_chama_market_sell() -> None:
    c = _client()
    ex = _executor(c)
    d = decidir(_SINAL, valor_atual=1.5, posicao_atual=0)  # contrarian: vende
    r = ex.executar(d)
    assert r.enviada
    assert c._dll.chamadas[0][0] == "SendMarketSellOrder"


def test_zerar_usa_ordem_de_argumentos_DIFERENTE_senha_em_quinto() -> None:
    """A armadilha do manual: SendZeroPositionAtMarket recebe
    (conta, corretora, TICKER, BOLSA, senha) — senha em 5o, nao em 3o."""
    c = _client()
    ex = _executor(c)
    d = decidir(_SINAL, valor_atual=1.5, posicao_atual=3)  # comprado + sinal contra -> zera
    r = ex.executar(d)

    assert r.enviada
    nome, args = c._dll.chamadas[0]
    assert nome == "SendZeroPositionAtMarket"
    assert args == ("DEMO123", "85", "WINV26", "F", "s3nh4")


def test_conta_real_exige_flag_explicita() -> None:
    c = _client()
    ex = _executor(c, usar_conta_real=True)
    d = decidir(_SINAL, valor_atual=1.5, posicao_atual=0)
    ex.executar(d)
    assert c._dll.chamadas[0][1][0] == "REAL456"


def test_retorno_negativo_da_dll_vira_recusa_nao_excecao() -> None:
    """Ordem recusada e' um estado NORMAL de operacao (ex.: fora de horario,
    saldo, ativo bloqueado) — reporta e loga, nao crasha o EA inteiro."""
    c = _client(_FakeDllOrdens(retorno=-2147483647))
    ex = _executor(c)
    d = decidir(_SINAL, valor_atual=1.5, posicao_atual=0)
    r = ex.executar(d)
    assert not r.enviada
    assert r.ordem_id is None
    assert "RECUSADA" in r.motivo


def test_acao_nada_nao_chama_dll() -> None:
    c = _client()
    ex = _executor(c)
    d = decidir(_SINAL, valor_atual=0.2, posicao_atual=0)  # zona neutra
    r = ex.executar(d)
    assert not r.enviada
    assert c._dll.chamadas == []


def test_construcao_falha_cedo_sem_senha_roteamento() -> None:
    """Config invalida falha na CONSTRUCAO, nao no meio do pregao na
    primeira ordem."""
    rot = RoteamentoConfig(senha_roteamento="", id_corretora="85", id_account_demo="DEMO123")
    with pytest.raises(SystemExit, match="SENHA_ROTEAMENTO"):
        ExecutorDeOrdens(_client(), rot, "WINV26", "F", 1)


def test_construcao_falha_cedo_com_quantidade_invalida() -> None:
    with pytest.raises(ValueError, match="positiva"):
        ExecutorDeOrdens(_client(), _rot(), "WINV26", "F", 0)


def test_executar_com_executor_delega_quando_dry_run_falso() -> None:
    c = _client()
    ex = _executor(c)
    d = decidir(_SINAL, valor_atual=1.5, posicao_atual=0)
    r = executar(d, dry_run=False, executor=ex)
    assert r is not None and r.enviada
    assert len(c._dll.chamadas) == 1


def test_executar_dry_run_nunca_toca_dll_mesmo_com_executor() -> None:
    """dry_run=True e' a camada 1: mesmo com executor valido em maos,
    NAO envia — so' loga."""
    c = _client()
    ex = _executor(c)
    d = decidir(_SINAL, valor_atual=1.5, posicao_atual=0)
    r = executar(d, dry_run=True, executor=ex)
    assert r is None
    assert c._dll.chamadas == []


# ---------------------------------------------------------------------
# trava exigir_conta_anunciada (E4, 2026-09-11)
# ---------------------------------------------------------------------
def test_trava_REPROVA_conta_nao_anunciada_pela_dll() -> None:
    """Mesmo com senha e config validas, se a DLL nunca anunciou esse par
    (corretora, conta) nesta sessao, a ordem NAO sai."""
    c = _client(contas_vistas=[(1003, "REAL456")])  # so' a REAL foi anunciada
    ex = _executor(c)  # demo, mas demo nao esta' em contas_vistas
    d = decidir(_SINAL, valor_atual=1.5, posicao_atual=0)
    with pytest.raises(TravaSimulacao, match="nao foi anunciada"):
        ex.executar(d)
    assert c._dll.chamadas == []


def test_trava_confere_a_cada_envio_nao_so_na_construcao() -> None:
    """A lista de contas vistas pode mudar entre a construcao e o envio
    (ela so' se popula apos GetAccount()) -- a checagem tem que rodar de
    novo a cada `executar()`, nao confiar num snapshot antigo."""
    c = _client(contas_vistas=[])  # nada anunciado ainda na construcao
    ex = _executor(c)
    d = decidir(_SINAL, valor_atual=1.5, posicao_atual=0)
    with pytest.raises(TravaSimulacao):
        ex.executar(d)
    c.contas_vistas.append((85, "DEMO123"))  # GetAccount() chega depois
    r = ex.executar(d)
    assert r.enviada


# ---------------------------------------------------------------------
# confirmacao de fill, slippage e latencia (E4, 2026-09-11)
# ---------------------------------------------------------------------
def test_fill_confirmado_calcula_slippage_e_latencia() -> None:
    """Compra com preco de referencia 140000, fill em 140005 -- slippage
    positivo (contra o EA, encheu mais caro). Latencia > 0."""
    c = _client(_FakeDllOrdens(preco_fill=140005.0))
    ex = _executor(c)
    d = decidir(_SINAL, valor_atual=-1.5, posicao_atual=0)  # compra
    r = ex.executar(d, preco_referencia=140000.0)
    assert r.fill_confirmado and r.preco_fill == 140005.0
    assert r.slippage_pts == pytest.approx(5.0)
    assert r.latencia_ms is not None and r.latencia_ms >= 0


def test_venda_com_fill_melhor_que_referencia_da_slippage_negativo() -> None:
    """Venda com preco de referencia 140000, fill em 140010 -- MELHOR para
    quem vende (vendeu mais caro) -- slippage negativo (a favor)."""
    c = _client(_FakeDllOrdens(preco_fill=140010.0))
    ex = _executor(c)
    d = decidir(_SINAL, valor_atual=1.5, posicao_atual=0)  # venda
    r = ex.executar(d, preco_referencia=140000.0)
    assert r.slippage_pts == pytest.approx(-10.0)


def test_zerar_nao_calcula_slippage_lado_neutro() -> None:
    c = _client(_FakeDllOrdens(preco_fill=140000.0))
    ex = _executor(c)
    d = decidir(_SINAL, valor_atual=1.5, posicao_atual=3)  # zera
    r = ex.executar(d, preco_referencia=139000.0)
    assert r.fill_confirmado and r.slippage_pts is None


def test_sem_fill_dentro_do_timeout_nao_quebra_e_marca_nao_confirmado() -> None:
    c = _client(_FakeDllOrdens(emitir_fill=False))
    ex = _executor(c, timeout_fill_s=0.2)
    d = decidir(_SINAL, valor_atual=1.5, posicao_atual=0)
    r = ex.executar(d, preco_referencia=140000.0)
    assert r.enviada and not r.fill_confirmado
    assert r.preco_fill is None and r.slippage_pts is None


# ---------------------------------------------------------------------
# ticker agregador (E4, 2026-09-11): o `symbol` da EAConfig e' "WINFUT"
# (serve para gerar o sinal), mas a ProfitDLL nao aceita agregador no
# envio de ordem (medido no E2: "Ordem invalida"). ExecutorDeOrdens
# precisa da MESMA trava que OrdemDeTeste/ReconciliadorPosicao ja' tem.
# ---------------------------------------------------------------------
def test_ticker_agregador_bloqueia_na_construcao() -> None:
    from profittape.ea.ordem_teste import TickerAgregadorInvalido

    with pytest.raises(TickerAgregadorInvalido):
        ExecutorDeOrdens(_client(), _rot(), "WINFUT", "F", 1)


def test_apenas_simulador_reprova_conta_real_mesmo_anunciada() -> None:
    """Sem apenas_simulador, uma conta REAL anunciada pela DLL passaria
    (exigir_conta_anunciada e' universal). Com apenas_simulador=True
    (E4), so' o nome da corretora contendo 'simul' passa -- mesma trava
    forte do E2/E3, agora tambem aqui."""
    c = _client(contas_vistas=[(1003, "REAL456")])
    c.nomes_corretoras = {1003: "XP Investimentos CCTVM S/A"}
    ex = ExecutorDeOrdens(c, _rot(), "WINV26", "F", 1, usar_conta_real=True,
                          apenas_simulador=True)
    d = decidir(_SINAL, valor_atual=1.5, posicao_atual=0)
    with pytest.raises(TravaSimulacao, match="nao e' o Simulador"):
        ex.executar(d)
    assert c._dll.chamadas == []


def test_apenas_simulador_aceita_simulador_anunciado() -> None:
    c = _client(contas_vistas=[(85, "DEMO123")])
    c.nomes_corretoras = {85: "Simulador"}
    ex = ExecutorDeOrdens(c, _rot(), "WINV26", "F", 1, apenas_simulador=True)
    d = decidir(_SINAL, valor_atual=1.5, posicao_atual=0)
    r = ex.executar(d)
    assert r.enviada
