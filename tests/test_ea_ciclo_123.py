"""ea/ciclo_123.py -- o ciclo de ordens do 123 (passo 4 do F5)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import pandas as pd

from profittape.ea.ciclo_123 import CicloDeOrdens123
from profittape.ea.semente import IndicadorMME
from profittape.ea.sinal import BarraFechada
from profittape.ea.sinal_123 import SinalPreco123

NS = 1_000_000_000
P15 = 900 * NS
T0900 = int(pd.Timestamp("2026-09-11 12:00:00", tz="UTC").value)


def _b(i: int, o: float, h: float, lo: float, c: float) -> BarraFechada:
    t = T0900 + i * P15
    return BarraFechada(bar_id=t // P15, ts_open_ns=t, ts_close_ns=t + P15, open=o, high=h,
                        low=lo, close=c, vol_agr=1, agf={})


def _ciclo(executor: Any | None = None) -> CicloDeOrdens123:
    # MME 139000 -> close 140000 acima -> regime de compra
    return CicloDeOrdens123(SinalPreco123(IndicadorMME(80, 139000.0)), executor=executor)


def _armar_compra(c: CicloDeOrdens123) -> None:
    """3 barras: 09:00, 09:15 (menor minima), 09:30 = t -> compra armada:
    entrada 140055, stop 139795, alvo 140315."""
    c.on_barra(_b(0, 140000.0, 140100.0, 139900.0, 140050.0))
    c.on_barra(_b(1, 140050.0, 140080.0, 139800.0, 140000.0))
    c.on_barra(_b(2, 140000.0, 140050.0, 139900.0, 140020.0))
    assert c.estado == "entrada_pendente" and c.op is not None
    assert c.op.entrada.nivel == 140055.0


# ------------------------------------------------------------- dry_run
def test_dry_run_alvo() -> None:
    c = _ciclo()
    _armar_compra(c)
    t = T0900 + 3 * P15                                # dentro de t+1 (09:45)
    c.on_trade(t + NS, 140050.0)                       # nao toca
    c.on_trade(t + 2 * NS, 140060.0)                   # cruza 140055 -> fill 140060
    assert c.estado == "posicionado" and c.op is not None
    assert c.op.entrada.fill == 140060.0 and c.op.entrada.slippage_pts == 5.0
    c.on_trade(t + 3 * NS, 140320.0)                   # toca o alvo -> fill AO NIVEL
    assert c.estado == "livre" and len(c.operacoes) == 1
    op = c.operacoes[0]
    assert op.desfecho == "alvo" and op.alvo is not None and op.alvo.fill == 140315.0
    assert op.pnl_pts == 140315.0 - 140060.0
    assert op.stop is not None and not op.stop.viva                       # OCO cancelou


def test_dry_run_stop_e_ignorado_posicao() -> None:
    c = _ciclo()
    _armar_compra(c)
    t = T0900 + 3 * P15
    c.on_trade(t + NS, 140060.0)
    # novo padrao enquanto posicionado -> ignorado_posicao
    c.on_barra(_b(3, 140060.0, 140100.0, 139850.0, 140000.0))
    c.on_barra(_b(4, 140000.0, 140050.0, 139700.0, 140020.0))
    c.on_barra(_b(5, 140020.0, 140040.0, 139900.0, 140030.0))
    assert c.ignorados_posicao == 1 and c.estado == "posicionado"
    c.on_trade(T0900 + 6 * P15 + NS, 139790.0)         # toca o stop -> fill no trade
    assert c.estado == "livre"
    op = c.operacoes[0]
    assert op.desfecho == "stop" and op.stop is not None and op.stop.fill == 139790.0
    assert op.stop.slippage_pts == 5.0                 # venda a 139790 contra nivel 139795
    assert op.pnl_pts == 139790.0 - 140060.0


def test_dry_run_nao_executou_cancela_no_fim_de_t1() -> None:
    c = _ciclo()
    _armar_compra(c)
    c.on_trade(T0900 + 3 * P15 + NS, 140000.0)         # dentro de t+1, nao toca
    c.on_trade(T0900 + 4 * P15, 140000.0)              # 10:00 = fim de t+1
    assert c.estado == "livre" and c.operacoes[0].desfecho == "nao_executou"
    assert c.operacoes[0].entrada.status[-1] == "DRY_CANCEL"


def test_dry_run_zeragem_1730() -> None:
    c = _ciclo()
    _armar_compra(c)
    c.on_trade(T0900 + 3 * P15 + NS, 140060.0)         # posicionado
    t1730 = int(pd.Timestamp("2026-09-11 20:30:00", tz="UTC").value)
    c.on_trade(t1730 + NS, 140100.0)
    assert c.estado == "livre"
    op = c.operacoes[0]
    assert op.desfecho == "zeragem" and op.zeragem is not None and op.zeragem.fill == 140100.0
    assert op.pnl_pts == 40.0
    assert op.stop is not None and not op.stop.viva and op.alvo is not None and not op.alvo.viva


def test_dry_run_ignorado_pendente_e_hb() -> None:
    c = _ciclo()
    _armar_compra(c)
    c.on_barra(_b(3, 140000.0, 140050.0, 139850.0, 140000.0))   # t+1 sem fill (on_trade nao veio)
    c.on_barra(_b(4, 140000.0, 140050.0, 139700.0, 140020.0))
    c.on_barra(_b(5, 140020.0, 140040.0, 139900.0, 140030.0))
    assert c.ignorados_pendente == 1
    assert c.hb()["estado"] == "entrada_pendente" and c.hb()["dry_run"]


# --------------------------------------------------------------- real
@dataclass
class _Ev:
    t_mono: float
    profit_id: int
    cl_ord_id: str
    status: str
    qtd: int = 1
    executada: int = 0
    preco_medio: float = 0.0
    texto: str = ""


class ExecutorFake:
    """Emula o E2b: aceite -> New; fill/cancel injetados pelo teste."""

    def __init__(self) -> None:
        self.chamadas: list[tuple[str, dict[str, Any]]] = []
        self.eventos: dict[int, list[_Ev]] = {}
        self._n = 100
        self.cl_por_id: dict[int, str] = {}

    def _nova(self, nome: str, **kw: Any) -> int:
        self._n += 1
        self.chamadas.append((nome, kw))
        cl = f"NELO.{self._n}"
        self.cl_por_id[self._n] = cl
        self.eventos[self._n] = [_Ev(time.monotonic(), self._n, "", "ClientCreated"),
                                 _Ev(time.monotonic(), self._n, cl, "New")]
        return self._n

    def enviar_stop(self, lado: str, gatilho: float, limite: float) -> int:
        return self._nova("enviar_stop", lado=lado, gatilho=gatilho, limite=limite)

    def enviar_limitada(self, lado: str, preco: float) -> int:
        return self._nova("enviar_limitada", lado=lado, preco=preco)

    def cancelar(self, cl_ord_id: str) -> int:
        self.chamadas.append(("cancelar", {"cl_ord_id": cl_ord_id}))
        return 0

    def zerar(self) -> int:
        return self._nova("zerar")

    def eventos_de(self, profit_id: int) -> list[_Ev]:
        return list(self.eventos.get(profit_id, []))

    # injecoes
    def preencher(self, profit_id: int, preco: float) -> None:
        self.eventos[profit_id].append(_Ev(time.monotonic(), profit_id, self.cl_por_id[profit_id],
                                           "Filled", executada=1, preco_medio=preco))

    def confirmar_cancel(self, profit_id: int) -> None:
        self.eventos[profit_id].append(_Ev(time.monotonic(), profit_id, self.cl_por_id[profit_id],
                                           "Canceled"))


def test_real_ciclo_completo_por_callbacks() -> None:
    ex = ExecutorFake()
    c = _ciclo(ex)
    _armar_compra(c)
    assert ex.chamadas[0] == ("enviar_stop", {"lado": "compra", "gatilho": 140055.0,
                                              "limite": 140105.0})
    c.tick()                                            # New chegou, sem fill
    assert c.estado == "entrada_pendente" and c.op is not None
    assert c.op.entrada.cl_ord_id == "NELO.101"
    ex.preencher(101, 140060.0)
    c.tick()
    assert c.estado == "posicionado"
    assert [n for n, _ in ex.chamadas[1:3]] == ["enviar_stop", "enviar_limitada"]
    assert ex.chamadas[1][1] == {"lado": "venda", "gatilho": 139795.0, "limite": 139745.0}
    assert ex.chamadas[2][1] == {"lado": "venda", "preco": 140315.0}
    c.tick()
    ex.preencher(103, 140315.0)                         # alvo executa
    c.tick()
    assert c.estado == "saindo"
    assert ex.chamadas[-1] == ("cancelar", {"cl_ord_id": "NELO.102"})   # cancela o stop
    ex.confirmar_cancel(102)
    c.tick()
    assert c.estado == "livre"
    op = c.operacoes[0]
    assert op.desfecho == "alvo" and op.pnl_pts == 255.0
    assert op.entrada.slippage_pts == 5.0 and op.avisos == []
    assert op.stop is not None and op.stop.resumo()["latencia_cancel_ms"] is not None


def test_real_entrada_nao_executa_e_e_cancelada_no_fim_de_t1() -> None:
    ex = ExecutorFake()
    c = _ciclo(ex)
    _armar_compra(c)
    c.tick()
    c.on_trade(T0900 + 4 * P15, 140000.0)              # fim de t+1
    assert c.estado == "cancelando_entrada"
    assert ex.chamadas[-1] == ("cancelar", {"cl_ord_id": "NELO.101"})
    ex.confirmar_cancel(101)
    c.tick()
    assert c.estado == "livre" and c.operacoes[0].desfecho == "nao_executou"


def test_real_cancel_nao_confirmado_avisa_e_libera() -> None:
    ex = ExecutorFake()
    c = CicloDeOrdens123(SinalPreco123(IndicadorMME(80, 139000.0)), executor=ex, timeout_s=0.05)
    _armar_compra(c)
    c.tick()
    c.on_trade(T0900 + 4 * P15, 140000.0)
    time.sleep(0.08)
    c.tick()
    assert c.estado == "livre"
    assert any("CONFIRA" in a for a in c.operacoes[0].avisos)


def test_real_stop_recusada_fecha_com_erro() -> None:
    ex = ExecutorFake()
    ex.enviar_stop = lambda **kw: -1  # type: ignore[method-assign]
    c = _ciclo(ex)
    _armar_compra_sem_assert = c.on_barra
    _armar_compra_sem_assert(_b(0, 140000.0, 140100.0, 139900.0, 140050.0))
    _armar_compra_sem_assert(_b(1, 140050.0, 140080.0, 139800.0, 140000.0))
    _armar_compra_sem_assert(_b(2, 140000.0, 140050.0, 139900.0, 140020.0))
    assert c.estado == "livre" and c.operacoes[0].desfecho == "erro"


# ---------------------------------------------------------------- 4b
@dataclass
class _Pos:
    quantidade_liquida: int
    plausivel: bool = True


class ExecutorFakeReconc(ExecutorFake):
    def __init__(self, posicao: int, plausivel: bool = True) -> None:
        super().__init__()
        self.posicao = posicao
        self.plausivel = plausivel

    retorno_cancelar_todas: int = 0

    def cancelar_todas(self) -> int:
        self.chamadas.append(("cancelar_todas", {}))
        if self.retorno_cancelar_todas:
            return self.retorno_cancelar_todas
        return 0

    def consultar_posicao(self) -> _Pos:
        return _Pos(self.posicao, self.plausivel)


def test_reconciliacao_posicionado_e_posicao_igual_rearma_saida() -> None:
    ex = ExecutorFakeReconc(posicao=1)
    c = _ciclo(ex)
    _armar_compra(c)
    c.tick()
    ex.preencher(101, 140060.0)
    c.tick()
    assert c.estado == "posicionado"
    c.tick()                     # absorve os callbacks de stop e alvo (ClOrdID)
    rel = c.reconciliar_apos_reconexao()
    assert rel["acao"] == "rearmou_saida" and c.estado == "posicionado"
    # cancelamento ORDEM A ORDEM (funcao singular, provada no E2b) -- a
    # plural nao foi testada ao vivo e ficou de fora (decisao de 17/09)
    assert "cancelar_todas" not in [n for n, _ in ex.chamadas]
    assert set(rel["canceladas"]) == {"stop", "alvo"}
    nomes = [n for n, _ in ex.chamadas]
    assert nomes[-2:] == ["enviar_stop", "enviar_limitada"]


def test_reconciliacao_posicionado_mas_zero_fecha_reconciliado() -> None:
    ex = ExecutorFakeReconc(posicao=0)
    c = _ciclo(ex)
    _armar_compra(c)
    c.tick()
    ex.preencher(101, 140060.0)
    c.tick()
    rel = c.reconciliar_apos_reconexao()
    assert rel["acao"] == "fechou_reconciliado" and c.estado == "livre"
    assert c.operacoes[0].desfecho == "reconciliado" and c.operacoes[0].pnl_pts is None


def test_reconciliacao_orfa_zera_e_pendente_limpa() -> None:
    ex = ExecutorFakeReconc(posicao=-1)
    c = _ciclo(ex)
    rel = c.reconciliar_apos_reconexao()                     # livre, mas ha' posicao
    assert rel["acao"] == "zerou_orfa" and ("zerar", {}) in ex.chamadas
    ex2 = ExecutorFakeReconc(posicao=0)
    c2 = _ciclo(ex2)
    _armar_compra(c2)
    rel2 = c2.reconciliar_apos_reconexao()                   # entrada pendente, sem posicao
    assert rel2["acao"] == "limpou_pendentes" and c2.estado == "livre"
    assert c2.operacoes[0].desfecho == "nao_executou"


def test_gate_e_vagas_no_ciclo() -> None:
    class Nega:
        def permite(self, c: Any, b: Any) -> bool:
            return False

    c = CicloDeOrdens123(SinalPreco123(IndicadorMME(80, 139000.0)), gate=Nega())
    _armar_compra_sem = c.on_barra
    _armar_compra_sem(_b(0, 140000.0, 140100.0, 139900.0, 140050.0))
    _armar_compra_sem(_b(1, 140050.0, 140080.0, 139800.0, 140000.0))
    _armar_compra_sem(_b(2, 140000.0, 140050.0, 139900.0, 140020.0))
    assert c.estado == "livre" and c.rejeitados_gate == 1

    from profittape.ea.vagas import VagasPorTicker
    v = VagasPorTicker()
    assert v.tentar_ocupar("WINFUT", "outro")
    # a DISPUTA de vaga so' existe entre EAs REAIS (2026-09-21): o ciclo aqui
    # tem executor (modo real, com o executor falso do E2b)
    ex = ExecutorFake()
    c2 = CicloDeOrdens123(SinalPreco123(IndicadorMME(80, 139000.0)), vagas=v,
                          symbol="WINFUT", nome="ea_123", executor=ex)
    c2.on_barra(_b(0, 140000.0, 140100.0, 139900.0, 140050.0))
    c2.on_barra(_b(1, 140050.0, 140080.0, 139800.0, 140000.0))
    c2.on_barra(_b(2, 140000.0, 140050.0, 139900.0, 140020.0))
    assert c2.estado == "livre" and c2.sinais_sem_vaga == 1
    v.liberar("WINFUT", "outro")
    c2.on_barra(_b(3, 140020.0, 140060.0, 139700.0, 140000.0))
    c2.on_barra(_b(4, 140000.0, 140050.0, 139900.0, 140030.0))
    c2.on_barra(_b(5, 140030.0, 140050.0, 139950.0, 140040.0))
    assert c2.estado == "entrada_pendente" and v.dono("WINFUT") == "ea_123"
    c2.tick()                                               # absorve o aceite
    c2.on_trade(T0900 + 7 * P15, 140000.0)                  # fim de t+1: pede cancel
    for pid in list(ex.eventos):
        ex.confirmar_cancel(pid)
    c2.tick()
    assert c2.estado == "livre" and v.dono("WINFUT") is None


def test_ea_simulado_nao_toma_nem_respeita_vaga() -> None:
    """2026-09-21: com o 123 REAL e o z_agf_win SIMULADO, uma posicao
    simulada nao pode bloquear um sinal real (nem o contrario contaminar a
    medicao do simulado). A vaga so' protege contra duas posicoes REAIS."""
    from profittape.ea.vagas import VagasPorTicker
    v = VagasPorTicker()
    assert v.tentar_ocupar("WINFUT", "ea_real")                    # dono REAL
    c = CicloDeOrdens123(SinalPreco123(IndicadorMME(80, 139000.0)), vagas=v,
                         symbol="WINFUT", nome="ea_simulado")      # dry_run
    _armar_compra(c)                                               # NAO bloqueado
    assert c.sinais_sem_vaga == 0
    assert v.dono("WINFUT") == "ea_real"                           # e nao tomou
    assert v.simulados["ea_simulado"] == 1
    # e um simulado armado nao impede um real de ocupar
    v.liberar("WINFUT", "ea_real")
    assert v.tentar_ocupar("WINFUT", "outro_real")


def test_reconciliacao_com_posicao_INVERTIDA_zera_em_vez_de_deixar_aberta() -> None:
    """Caso levantado pelo operador em 22/09: stop e alvo sao ordens
    INDEPENDENTES na corretora (a DLL nao tem OCO nativo). Com o EA parado,
    se as DUAS pernas executarem, a posicao inverte. Antes caia no `else`:
    registrava `nao_executou` e deixava a posicao invertida aberta."""
    ex = ExecutorFakeReconc(posicao=-1)        # EA comprado; na volta, VENDIDO 1
    c = _ciclo(ex)
    _armar_compra(c)
    c.tick()
    ex.preencher(101, 140060.0)
    c.tick()
    assert c.estado == "posicionado"
    c.tick()
    rel = c.reconciliar_apos_reconexao()
    assert rel["acao"] == "zerou_inesperada"
    nomes = [n for n, _ in ex.chamadas]
    assert "zerar" in nomes and "cancelar_todas" in nomes
    assert c.operacoes[-1].desfecho == "erro"
    assert c.estado == "livre"


def test_reconciliacao_com_posicao_orfa_continua_zerando() -> None:
    ex = ExecutorFakeReconc(posicao=1)          # posicao sem operacao conhecida
    c = _ciclo(ex)
    rel = c.reconciliar_apos_reconexao()
    assert rel["acao"] == "zerou_orfa" and "zerar" in [n for n, _ in ex.chamadas]


def test_limpeza_incompleta_quando_a_dll_recusa_ou_a_posicao_e_implausivel() -> None:
    """23/09: a 1a tentativa saiu as 08:22 (mercado fechado) -- a DLL recusou
    com NL_INVALID_ARGS e a posicao veio implausivel. Isso NAO e' conclusao:
    e' 'ainda nao deu certo', e quem chama tenta de novo."""
    ex = ExecutorFakeReconc(posicao=0)
    ex.retorno_cancelar_todas = -2147483645          # NL_INVALID_ARGS
    c = _ciclo(ex)
    rel = c.limpeza_na_subida()
    assert rel["acao"] == "incompleta_tentar_de_novo" and rel["cancel_todas_ok"] is False

    ex2 = ExecutorFakeReconc(posicao=0, plausivel=False)
    rel2 = _ciclo(ex2).limpeza_na_subida()
    assert rel2["acao"] == "incompleta_tentar_de_novo" and rel2["posicao_implausivel"] is True


def test_limpeza_na_subida_cancela_tudo_e_zera_orfa() -> None:
    """Processo anterior MORREU com ordens vivas: o EA novo nao conhece os
    ClOrdIDs. Na subida: cancela TODAS as ordens do ativo e zera se houver
    posicao."""
    ex = ExecutorFakeReconc(posicao=0)
    c = _ciclo(ex)
    assert c.limpeza_na_subida()["acao"] == "limpo"
    assert [n for n, _ in ex.chamadas] == ["cancelar_todas"]
    ex2 = ExecutorFakeReconc(posicao=-1)
    c2 = _ciclo(ex2)
    assert c2.limpeza_na_subida()["acao"] == "zerou_orfa"
    assert [n for n, _ in ex2.chamadas] == ["cancelar_todas", "zerar"]


def test_limpeza_na_subida_nao_cancela_ordens_de_outro_ea_real() -> None:
    """SendCancelOrders cancela TODAS as ordens do ativo na conta: se outro
    EA real ja' opera o ticker, cancelaria as dele."""
    from profittape.ea.vagas import VagasPorTicker
    v = VagasPorTicker()
    assert v.tentar_ocupar("WINFUT", "outro_real")
    ex = ExecutorFakeReconc(posicao=1)
    c = CicloDeOrdens123(SinalPreco123(IndicadorMME(80, 139000.0)), executor=ex,
                         vagas=v, symbol="WINFUT", nome="ea_novo")
    assert c.limpeza_na_subida()["acao"] == "adiada_vaga_de_outro"
    assert ex.chamadas == []


def test_limpeza_na_subida_nao_roda_em_dry_run() -> None:
    c = _ciclo()
    assert c.limpeza_na_subida() == {}


def _posicionar_vendido(ex: Any) -> CicloDeOrdens123:
    """Ciclo REAL e VENDIDO. MME 141.000 (close abaixo -> regime de venda);
    barra do meio com a MAIOR maxima. O stop de saida e' de COMPRA, e o
    limite fica 50 pts ACIMA do gatilho."""
    c = CicloDeOrdens123(SinalPreco123(IndicadorMME(80, 141000.0)), executor=ex)
    c.on_barra(_b(0, 140000.0, 140100.0, 139900.0, 140050.0))
    c.on_barra(_b(1, 140050.0, 140200.0, 139950.0, 140000.0))   # maior maxima
    c.on_barra(_b(2, 140000.0, 140050.0, 139900.0, 139950.0))   # t
    assert c.estado == "entrada_pendente" and c.op is not None
    assert c.op.entrada.nivel == 139895.0                       # minima de t - 5
    c.tick()
    ex.preencher(c.op.entrada.profit_id, 139895.0)
    c.tick()
    assert c.estado == "posicionado" and c.op.stop is not None
    assert c.op.candidato.stop == 140205.0                      # maxima de t-1 + 5
    assert c.op.stop.lado == "compra"
    return c


LIMITE_DO_STOP = 140205.0 + 50.0        # gatilho + folga: calculado AQUI, de
                                        # proposito, para estes testes rodarem
                                        # tambem no codigo ANTIGO (sem o campo
                                        # `limite`) e reprovarem por ASSERCAO


def test_o_stop_guarda_o_limite_enviado() -> None:
    c = _posicionar_vendido(ExecutorFakeReconc(posicao=-1))
    assert c.op is not None and c.op.stop is not None
    assert c.op.stop.limite == LIMITE_DO_STOP


def test_stop_que_dispara_e_NAO_executa_zera_a_mercado() -> None:
    """PRE-REGISTRO 22/09 (EA_ARQUITETURA 9), caso 1: negocio alem do LIMITE
    e sem fill em 2 s de tempo de mercado -> cancela as duas pernas, zera a
    mercado, desfecho `stop` com `stop_protegido`."""
    ex = ExecutorFakeReconc(posicao=-1)
    c = _posicionar_vendido(ex)
    alem = LIMITE_DO_STOP + 30.0                        # saltou por cima do limite
    t0 = T0900 + 20 * P15
    c.on_trade(t0, alem)                                # 1o negocio alem: so' marca
    assert c.estado == "posicionado" and "zerar" not in [n for n, _ in ex.chamadas]
    c.on_trade(t0 + 1 * NS, alem + 5)                   # 1 s: ainda na carencia
    assert c.estado == "posicionado"
    c.on_trade(t0 + 3 * NS, alem + 10)                  # 3 s: protege
    assert "zerar" in [n for n, _ in ex.chamadas]
    assert c.op.stop_protegido is True
    assert c.op.resumo()["preco_disparou_protecao"] == alem + 10
    ex.preencher(ex._n, alem + 10)                      # fill da zeragem
    c.tick()
    assert c.operacoes[-1].desfecho == "stop" and c.estado == "livre"


def test_fill_do_stop_dentro_da_carencia_NAO_dispara_protecao() -> None:
    """Caso 2: o callback do fill chega dentro dos 2 s -> saida normal."""
    ex = ExecutorFakeReconc(posicao=-1)
    c = _posicionar_vendido(ex)
    alem = LIMITE_DO_STOP + 30.0
    t0 = T0900 + 20 * P15
    c.on_trade(t0, alem)
    ex.preencher(c.op.stop.profit_id, c.op.candidato.stop)   # stop executou no gatilho
    c.tick()
    assert c.op.stop.fill == c.op.candidato.stop
    c.on_trade(t0 + 5 * NS, alem)                            # passou dos 2 s
    assert "zerar" not in [n for n, _ in ex.chamadas]
    assert c.op.stop_protegido is False


def test_preco_entre_o_gatilho_e_o_limite_NAO_dispara_protecao() -> None:
    """Caso 3: o limite ainda pode executar -- nao e' salto."""
    ex = ExecutorFakeReconc(posicao=-1)
    c = _posicionar_vendido(ex)
    entre = c.op.candidato.stop + 20.0                       # < limite (stop+50)
    t0 = T0900 + 20 * P15
    for k in range(6):
        c.on_trade(t0 + k * NS, entre)
    assert c.op.stop_protegido is False
    assert "zerar" not in [n for n, _ in ex.chamadas]


def test_volta_para_dentro_do_limite_reinicia_a_carencia() -> None:
    ex = ExecutorFakeReconc(posicao=-1)
    c = _posicionar_vendido(ex)
    alem, dentro = LIMITE_DO_STOP + 30.0, c.op.candidato.stop + 10.0
    t0 = T0900 + 20 * P15
    c.on_trade(t0, alem)
    c.on_trade(t0 + 1 * NS, dentro)                          # voltou
    c.on_trade(t0 + 3 * NS, alem)                            # conta do zero
    assert c.op.stop_protegido is False
    c.on_trade(t0 + 6 * NS, alem)                            # 3 s depois do reinicio
    assert c.op.stop_protegido is True


def test_fill_atrasado_depois_da_zeragem_fecha_a_operacao_uma_vez_so() -> None:
    """Caso 4: o stop tinha executado e o callback chegou depois. A zeragem
    a mercado e' idempotente (posicao ja' zerada) e a operacao fecha UMA vez."""
    ex = ExecutorFakeReconc(posicao=-1)
    c = _posicionar_vendido(ex)
    alem = LIMITE_DO_STOP + 30.0
    t0 = T0900 + 20 * P15
    c.on_trade(t0, alem)
    c.on_trade(t0 + 3 * NS, alem)                            # protege
    assert c.estado == "zerando"
    ex.preencher(c.op.stop.profit_id, c.op.candidato.stop)   # callback atrasado do stop
    ex.preencher(ex._n, alem)                                # e o da zeragem
    c.tick()
    assert len(c.operacoes) == 1 and c.estado == "livre"


def test_posicao_contraria_zera_na_hora_em_vez_de_esperar_a_4b() -> None:
    """Bug corrigido em 22/09: dizia '(4b zera)', mas a 4b so' roda na volta
    de uma queda de conexao."""
    ex = ExecutorFakeReconc(posicao=-1)
    c = _posicionar_vendido(ex)
    ex.preencher(c.op.stop.profit_id, c.op.candidato.stop)   # stop executou
    c.tick()
    assert c.estado == "saindo"
    ex.preencher(c.op.alvo.profit_id, c.op.candidato.alvo)   # e o alvo tambem
    c.tick()
    assert "zerar" in [n for n, _ in ex.chamadas]
    assert c.operacoes[-1].desfecho == "stop"
