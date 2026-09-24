"""
E2b da trilha de execucao (2026-09-14), DENTRO do record: as familias de
ordem que o ciclo do 123 exige (EAS_DE_PRECO.md 5.4) provadas UMA VEZ na
conta de simulacao, com o callback de ordem lido de verdade -- ClOrdID,
tipo, stop, status.

POR QUE EXISTE
--------------
O E2 provou mercado + zeragem. O 123 com ordens REAIS (decisao do
operador: protecao na corretora sobrevive a queda de conexao) precisa
de tres coisas que o executor nunca mandou: ordem STOP, ordem LIMITADA
e CANCELAMENTO. E precisa do OCO feito pelo EA (a DLL nao tem): duas
pernas vivas, uma executa, o EA cancela a outra.

O QUE O E2b FAZ, NA ORDEM (1 contrato, ticker especifico, Simulador)
-------------------------------------------------------------------
    1. compra a MERCADO (E2, ja' provado) -> fill = preco de referencia
    2. STOP de compra LONGE (ref + longe_pts): tem que ser ACEITA (callback
       com ClOrdID) e depois CANCELADA por SendCancelOrder(ClOrdID) ->
       callback de cancelamento. Prova a familia stop e o cancelamento
       sem risco de execucao (esta' longe).
    3. OCO de saida da posicao comprada: STOP de venda em ref - d e
       LIMITADA de venda em ref + d, as duas de uma vez. Espera uma
       executar (o mercado toca uma delas) -> cancela a outra ->
       confirma o cancelamento. Posicao volta a zero pela perna que
       executou. E' exatamente o ciclo de saida do 123.
    4. Se nada executar em `timeout_oco_s`: cancela as duas e ZERA a
       mercado. Se um cancelamento nao confirmar: ZERA a mercado e
       termina com "CONFIRA AS ORDENS NO PROFIT".

O QUE PROVA
-----------
- SendStopBuyOrder / SendStopSellOrder / SendSellOrder / SendCancelOrder
  existem na DLL instalada com as assinaturas declaradas em bindings.py;
- o OrderChangeCallback entrega ClOrdID e os status de aceite,
  execucao e cancelamento (quais strings; latencias);
- o OCO por EA fecha: uma perna executa, a outra cancela.
Nao prova borda nem slippage real (o simulador preenche no toque).

TRAVA: a mesma do E2 (`exigir_simulador` antes de CADA Send*). Sem
opcao de desligar.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog

from ..profitdll.client import EventoOrdem
from ..profitdll.errors import normalizar_retorno
from .config import RoteamentoConfig
from .ordem_teste import (
    TravaSimulacao,
    _ClientRoteamento,
    exigir_simulador,
    exigir_ticker_especifico,
)

log = structlog.get_logger(__name__)

TICK = 5.0


def _ao_tick(p: float) -> float:
    return round(p / TICK) * TICK


def _status_cancelada(e: EventoOrdem) -> bool:
    s = e.status.lower()
    if "cancel" in s:
        return True
    return e.restante == 0 and e.executada == 0 and s not in ("", "clientcreated", "hadescreated")


def _status_rejeitada(e: EventoOrdem) -> bool:
    s = e.status.lower()
    return "notcreated" in s or "reject" in s or "rejeit" in s or "invalid" in s


@dataclass
class PernaOrdem:
    nome: str          # compra_mercado | stop_longe | stop_venda | limite_venda | zeragem
    funcao: str                     # nome da funcao da DLL
    t_envio: float | None = None
    profit_id: int | None = None
    cl_ord_id: str = ""
    tipo: str = ""
    status: list[str] = field(default_factory=list)
    t_primeiro_callback: float | None = None
    t_fill: float | None = None
    preco_medio: float | None = None
    t_cancel_envio: float | None = None
    t_cancel_confirmado: float | None = None
    preco: float = 0.0
    stop: float = 0.0

    def resumo(self) -> dict[str, Any]:
        def _ms(a: float | None, b: float | None) -> float | None:
            return round((b - a) * 1000, 1) if a is not None and b is not None else None
        return {"funcao": self.funcao, "profit_id": self.profit_id, "cl_ord_id": self.cl_ord_id,
                "tipo": self.tipo, "preco": self.preco, "stop": self.stop, "status": self.status,
                "latencia_primeiro_callback_ms": _ms(self.t_envio, self.t_primeiro_callback),
                "latencia_fill_ms": _ms(self.t_envio, self.t_fill), "preco_medio": self.preco_medio,
                "latencia_cancel_ms": _ms(self.t_cancel_envio, self.t_cancel_confirmado)}


@dataclass
class RelatorioOrdemTesteB:
    ticker: str
    corretora: int
    conta: str
    longe_pts: float
    distancia_pts: float
    preco_ref: float | None = None
    pernas: dict[str, PernaOrdem] = field(default_factory=dict)
    perna_oco_executada: str = ""
    resultado: str = ""
    erro: str = ""

    def resumo(self) -> dict[str, Any]:
        return {"resultado": self.resultado, "erro": self.erro, "ticker": self.ticker,
                "corretora": self.corretora, "conta": self.conta, "preco_ref": self.preco_ref,
                "longe_pts": self.longe_pts, "distancia_pts": self.distancia_pts,
                "perna_oco_executada": self.perna_oco_executada,
                "pernas": {k: v.resumo() for k, v in self.pernas.items()}}


class OrdemDeTesteB:
    """
    Maquina de estados ticada pela thread principal do record (0,5 s).
    Cada passo faz no maximo UMA chamada de DLL e volta.

        aguardando_horario -> compra_mercado -> aguardando_fill_compra
        -> stop_longe -> aguardando_aceite_longe -> cancelando_longe
        -> aguardando_cancel_longe -> armando_oco -> aguardando_oco
        -> cancelando_outra -> aguardando_cancel_outra -> concluida
        (timeout do OCO: cancelando_ambas -> zerando -> aguardando_zeragem)
        (qualquer erro: zerando -> ... -> concluida com resultado de erro)
    """

    def __init__(self, client: _ClientRoteamento, roteamento: RoteamentoConfig,
                 horario_hhmm: str, ticker: str, bolsa: str = "F",
                 longe_pts: float = 300.0, distancia_pts: float = 15.0,
                 slack_limite_pts: float = 50.0,
                 timeout_s: float = 10.0, timeout_oco_s: float = 180.0,
                 relogio: Any = None) -> None:
        exigir_ticker_especifico(ticker)
        if longe_pts < 100 or distancia_pts < TICK:
            raise ValueError("longe_pts >= 100 e distancia_pts >= 1 tick: o teste e' seguro "
                             "por construcao")
        self._client, self._rot = client, roteamento
        self._horario, self._ticker, self._bolsa = horario_hhmm, ticker, bolsa
        self._longe, self._dist, self._slack = longe_pts, distancia_pts, slack_limite_pts
        self._timeout, self._timeout_oco = timeout_s, timeout_oco_s
        self._agora = relogio or (lambda: datetime.now().strftime("%H:%M"))
        self._corretora, self._conta = roteamento.conta_para(False)
        if not roteamento.senha_roteamento:
            raise SystemExit("ROTEAMENTO_SENHA_ROTEAMENTO ausente no .env")
        self.estado = "aguardando_horario"
        self.rel = RelatorioOrdemTesteB(ticker, int(self._corretora), self._conta,
                                        longe_pts, distancia_pts)
        self._t_limite = 0.0
        self._posicao_aberta = False
        self._a_cancelar: list[str] = []

    # ------------------------------------------------------------------
    @property
    def concluida(self) -> bool:
        return self.estado == "concluida"

    def _concluir(self, resultado: str, erro: str = "") -> None:
        self.rel.resultado, self.rel.erro = resultado, erro
        self.estado = "concluida"
        log.info("ea.ordem_teste_b.concluida", **self.rel.resumo())

    def _eventos_de(self, profit_id: int) -> list[EventoOrdem]:
        return [e for e in list(self._client.ordens_eventos) if e.profit_id == profit_id]

    def _trava(self) -> Any:
        exigir_simulador(self._client, self._corretora, self._conta)
        if not self._client.corretora_pronta:
            raise TravaSimulacao("corretora nao esta' pronta neste instante")
        return self._client._dll

    def _enviar(self, perna: PernaOrdem) -> int:
        dll = self._trava()
        c, k, s = self._conta, self._corretora, self._rot.senha_roteamento
        t, b = self._ticker, self._bolsa
        perna.t_envio = time.monotonic()
        if perna.funcao == "SendMarketBuyOrder":
            oid = dll.SendMarketBuyOrder(c, k, s, t, b, 1)
        elif perna.funcao in ("SendStopBuyOrder", "SendStopSellOrder"):
            oid = getattr(dll, perna.funcao)(c, k, s, t, b, perna.preco, perna.stop, 1)
        elif perna.funcao == "SendSellOrder":
            oid = dll.SendSellOrder(c, k, s, t, b, perna.preco, 1)
        elif perna.funcao == "SendZeroPositionAtMarket":
            oid = dll.SendZeroPositionAtMarket(c, k, t, b, s)     # senha em 5o
        else:
            raise ValueError(perna.funcao)
        perna.profit_id = int(oid)
        self.rel.pernas[perna.nome] = perna
        log.info("ea.ordem_teste_b.enviada", perna=perna.nome, funcao=perna.funcao,
                 profit_id=perna.profit_id, preco=perna.preco, stop=perna.stop)
        return int(oid)

    def _cancelar(self, perna: PernaOrdem) -> int:
        dll = self._trava()
        if not perna.cl_ord_id:
            raise RuntimeError(f"{perna.nome}: sem ClOrdID no callback -- nao da' para cancelar")
        perna.t_cancel_envio = time.monotonic()
        # (conta, corretora, ClOrdID, senha) -- senha em 4o. Ver bindings.py.
        r = normalizar_retorno(int(dll.SendCancelOrder(
            self._conta, self._corretora, perna.cl_ord_id,
            self._rot.senha_roteamento)))
        log.info("ea.ordem_teste_b.cancel_enviado", perna=perna.nome,
                 cl_ord_id=perna.cl_ord_id, retorno=r)
        return r

    def _absorver(self, perna: PernaOrdem) -> None:
        """Le os callbacks novos da perna; atualiza ClOrdID, status, fill, cancel."""
        assert perna.profit_id is not None
        for e in self._eventos_de(perna.profit_id)[len(perna.status):]:
            perna.status.append(e.status)
            if perna.t_primeiro_callback is None:
                perna.t_primeiro_callback = e.t_mono
            if e.cl_ord_id and not perna.cl_ord_id:
                perna.cl_ord_id = e.cl_ord_id
            if e.tipo and not perna.tipo:
                perna.tipo = e.tipo
            log.info("ea.ordem_teste_b.callback", perna=perna.nome, profit_id=e.profit_id,
                     cl_ord_id=e.cl_ord_id, tipo=e.tipo, status=e.status, qtd=e.qtd,
                     executada=e.executada, restante=e.restante, preco=e.preco,
                     stop=e.stop_preco, preco_medio=e.preco_medio, texto=e.texto)
            if e.executada >= e.qtd and e.qtd > 0 and perna.t_fill is None:
                perna.t_fill, perna.preco_medio = e.t_mono, e.preco_medio
            if perna.t_cancel_envio is not None and _status_cancelada(e):
                perna.t_cancel_confirmado = e.t_mono

    def _rejeitada(self, perna: PernaOrdem) -> bool:
        assert perna.profit_id is not None
        return any(_status_rejeitada(e) for e in self._eventos_de(perna.profit_id))

    # ------------------------------------------------------------------
    def tick(self) -> None:
        try:
            self._tick()
        except TravaSimulacao as e:
            log.error("ea.ordem_teste_b.TRAVA", motivo=str(e))
            self._concluir("trava", str(e))
        except Exception as e:
            log.error("ea.ordem_teste_b.erro", erro=repr(e), estado=self.estado)
            if self._posicao_aberta:
                self.rel.erro = repr(e)
                self.estado = "zerando"
            else:
                self._concluir("erro", repr(e))

    def _armar_timeout(self, s: float) -> None:
        self._t_limite = time.monotonic() + s

    def _tick(self) -> None:  # maquina de estados linear, um estado por bloco
        st = self.estado
        if st == "aguardando_horario":
            if self._agora() < self._horario:
                return
            log.info("ea.ordem_teste_b.iniciando", horario=self._horario, ticker=self._ticker,
                     corretora=self._corretora, conta=self._conta,
                     contas_vistas=self._client.contas_vistas)
            self.estado = "compra_mercado"
            return

        if st == "compra_mercado":
            p = PernaOrdem("compra_mercado", "SendMarketBuyOrder")
            if self._enviar(p) <= 0:
                self._concluir("compra_recusada", "SendMarketBuyOrder devolveu <= 0")
                return
            self._posicao_aberta = True
            self._armar_timeout(self._timeout)
            self.estado = "aguardando_fill_compra"
            return

        if st == "aguardando_fill_compra":
            p = self.rel.pernas["compra_mercado"]
            self._absorver(p)
            if p.t_fill is not None:
                self.rel.preco_ref = _ao_tick(p.preco_medio or 0.0)
                self.estado = "stop_longe"
            elif time.monotonic() > self._t_limite:
                self.rel.resultado = "timeout_fill_compra"
                self.estado = "zerando"
            return

        if st == "stop_longe":
            ref = self.rel.preco_ref or 0.0
            p = PernaOrdem("stop_longe", "SendStopBuyOrder",
                           stop=_ao_tick(ref + self._longe),
                           preco=_ao_tick(ref + self._longe + self._slack))
            if self._enviar(p) <= 0:
                self.rel.resultado = "stop_recusado"
                self.rel.erro = "SendStopBuyOrder devolveu <= 0"
                self.estado = "zerando"
                return
            self._armar_timeout(self._timeout)
            self.estado = "aguardando_aceite_longe"
            return

        if st == "aguardando_aceite_longe":
            p = self.rel.pernas["stop_longe"]
            self._absorver(p)
            if self._rejeitada(p):
                self.rel.resultado, self.rel.erro = "stop_rejeitado", f"status={p.status}"
                self.estado = "zerando"
            elif p.cl_ord_id:
                self.estado = "cancelando_longe"
            elif time.monotonic() > self._t_limite:
                self.rel.resultado, self.rel.erro = "stop_sem_callback", f"status={p.status}"
                self.estado = "zerando"
            return

        if st == "cancelando_longe":
            p = self.rel.pernas["stop_longe"]
            self._cancelar(p)
            self._armar_timeout(self._timeout)
            self.estado = "aguardando_cancel_longe"
            return

        if st == "aguardando_cancel_longe":
            p = self.rel.pernas["stop_longe"]
            self._absorver(p)
            if p.t_cancel_confirmado is not None:
                self.estado = "armando_oco"
            elif time.monotonic() > self._t_limite:
                self.rel.resultado = "cancel_nao_confirmado"
                self.rel.erro = ("stop longe sem callback de cancelamento -- "
                                 "CONFIRA AS ORDENS NO PROFIT")
                self.estado = "zerando"
            return

        if st == "armando_oco":
            ref = self.rel.preco_ref or 0.0
            ps = PernaOrdem("stop_venda", "SendStopSellOrder",
                            stop=_ao_tick(ref - self._dist),
                            preco=_ao_tick(ref - self._dist - self._slack))
            pl = PernaOrdem("limite_venda", "SendSellOrder", preco=_ao_tick(ref + self._dist))
            if self._enviar(ps) <= 0:
                self.rel.resultado, self.rel.erro = "stop_venda_recusado", "SendStopSellOrder <= 0"
                self.estado = "zerando"
                return
            if self._enviar(pl) <= 0:
                self.rel.resultado, self.rel.erro = "limite_recusada", "SendSellOrder <= 0"
                self._a_cancelar = ["stop_venda"]
                self.estado = "cancelando_ambas"
                return
            self._armar_timeout(self._timeout_oco)
            self.estado = "aguardando_oco"
            return

        if st == "aguardando_oco":
            ps, pl = self.rel.pernas["stop_venda"], self.rel.pernas["limite_venda"]
            self._absorver(ps)
            self._absorver(pl)
            for p in (ps, pl):
                if self._rejeitada(p):
                    self.rel.resultado = "perna_oco_rejeitada"
                    self.rel.erro = f"{p.nome}: {p.status}"
                    self._a_cancelar = [q.nome for q in (ps, pl) if q is not p and q.cl_ord_id]
                    self.estado = "cancelando_ambas"
                    return
            executada = ps if ps.t_fill is not None else pl if pl.t_fill is not None else None
            if executada is not None:
                self.rel.perna_oco_executada = executada.nome
                self._posicao_aberta = False
                self._outra = pl if executada is ps else ps
                self.estado = "cancelando_outra"
            elif time.monotonic() > self._t_limite:
                self.rel.resultado = "timeout_oco"
                self._a_cancelar = [p.nome for p in (ps, pl) if p.cl_ord_id]
                self.estado = "cancelando_ambas"
            return

        if st == "cancelando_outra":
            self._cancelar(self._outra)
            self._armar_timeout(self._timeout)
            self.estado = "aguardando_cancel_outra"
            return

        if st == "aguardando_cancel_outra":
            self._absorver(self._outra)
            if self._outra.t_cancel_confirmado is not None:
                self._concluir("ok")
            elif time.monotonic() > self._t_limite:
                self._concluir("cancel_outra_nao_confirmado",
                               f"{self._outra.nome} sem callback de cancelamento -- "
                               "CONFIRA AS ORDENS NO PROFIT (posicao ja' zerada pela outra perna)")
            return

        if st == "cancelando_ambas":
            for nome in self._a_cancelar:
                p = self.rel.pernas[nome]
                if p.cl_ord_id and p.t_cancel_envio is None:
                    self._cancelar(p)
            self._armar_timeout(self._timeout)
            self.estado = "aguardando_cancel_ambas"
            return

        if st == "aguardando_cancel_ambas":
            pend = [self.rel.pernas[n] for n in self._a_cancelar]
            for p in pend:
                self._absorver(p)
            todos = all(p.t_cancel_confirmado is not None for p in pend)
            if todos or time.monotonic() > self._t_limite:
                if not todos:
                    self.rel.erro = (self.rel.erro + " | ").strip(" |") + \
                        "cancelamento nao confirmado -- CONFIRA AS ORDENS NO PROFIT"
                self.estado = "zerando" if self._posicao_aberta else "concluida_por_erro"
            return

        if st == "concluida_por_erro":
            self._concluir(self.rel.resultado or "erro", self.rel.erro)
            return

        if st == "zerando":
            p = PernaOrdem("zeragem", "SendZeroPositionAtMarket")
            if self._enviar(p) <= 0:
                self._concluir(self.rel.resultado or "zeragem_recusada",
                               (self.rel.erro + " | ").strip(" |") +
                               "SendZeroPositionAtMarket <= 0 -- CONFIRA A POSICAO NO PROFIT")
                return
            self._armar_timeout(self._timeout)
            self.estado = "aguardando_zeragem"
            return

        if st == "aguardando_zeragem":
            p = self.rel.pernas["zeragem"]
            self._absorver(p)
            if p.t_fill is not None:
                self._posicao_aberta = False
                self._concluir(self.rel.resultado or "ok_com_zeragem", self.rel.erro)
            elif time.monotonic() > self._t_limite:
                self._concluir(self.rel.resultado or "timeout_zeragem",
                               (self.rel.erro + " | ").strip(" |") +
                               "zeragem sem fill -- CONFIRA A POSICAO NO PROFIT")
            return
