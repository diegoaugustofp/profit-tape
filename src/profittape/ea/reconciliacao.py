"""
E3 da trilha de execucao: reconciliacao de posicao EA x corretora, com
parada de emergencia (zeragem automatica) na divergencia.

POR QUE ISTO EXISTE (docs/EA_ARQUITETURA.md, escada E0-E5)
------------------------------------------------------------
"o gestor guarda posicao em memoria e nunca confere com a DLL. Em
execucao real e' a origem classica de desastre." Um EA que acredita
estar zerado mas na verdade tem posicao (ordem duplicada, reconexao que
perdeu um fill, bug de contagem) so' descobre isso quando o prejuizo
aparece. O E3 e' a pergunta feita em voz alta, periodicamente: "o que eu
acho que tenho bate com o que a corretora diz que eu tenho?"

O QUE MEDE E O QUE ASSUME
--------------------------
`ReconciliadorPosicao.checar()` consulta `client.consultar_posicao`
(GetPositionV2 -- ver NAO VERIFICADO em profitdll/types.py) e compara
com `esperado` (o que o chamador ACREDITA que a posicao deveria ser --
0 na maior parte dos usos deste projeto, ja' que nenhum EA daqui carrega
posicao entre ticks hoje). Diverge -> zera a mercado (mesma familia
SendZeroPositionAtMarket do E2) e loga CRITICAL. Bate -> loga e segue.

Resultado IMPLAUSIVEL (ver PosicaoConsultada.plausivel) NUNCA aciona
zeragem -- so' alarma que a consulta em si esta' suspeita. Agir sobre
posicao mal lida e' pior que nao agir: pode zerar uma posicao que nao
existe (mandando ordem no lado errado) ou deixar aberta uma que existe.

A TRAVA (reaproveitada de ordem_teste.py, 2026-09-11)
-------------------------------------------------------
Mesma exigencia: (corretora, conta) tem que estar em `contas_vistas` e o
nome da corretora anunciado pela DLL tem que conter "simul". A zeragem
automatica deste modulo NUNCA toca conta real -- mesma garantia do E2,
nao uma nova.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog

from ..profitdll.client import EventoOrdem
from .config import RoteamentoConfig
from .ordem_teste import TravaSimulacao, exigir_simulador, exigir_ticker_especifico

log = structlog.get_logger(__name__)


@dataclass
class RelatorioReconciliacao:
    ticker: str
    corretora: int
    conta: str
    esperado: int
    t_consulta: float | None = None
    encontrado: int | None = None
    preco_medio: float | None = None
    plausivel: bool | None = None
    zeragem_ordem_id: int | None = None
    zeragem_status: list[str] = field(default_factory=list)
    t_zeragem_fill: float | None = None
    # bate | divergiu_zerado | divergiu_zeragem_falhou | implausivel | trava | erro
    resultado: str = ""
    erro: str = ""

    def resumo(self) -> dict[str, Any]:
        return {
            "resultado": self.resultado, "ticker": self.ticker, "corretora": self.corretora,
            "conta": self.conta, "esperado": self.esperado, "encontrado": self.encontrado,
            "preco_medio": self.preco_medio, "plausivel": self.plausivel,
            "zeragem_ordem_id": self.zeragem_ordem_id, "zeragem_status": self.zeragem_status,
            "erro": self.erro,
        }


class ReconciliadorPosicao:
    """
    Maquina de estados ticada pela thread principal do record, no mesmo
    padrao de `OrdemDeTeste` (tick() faz no maximo uma chamada de DLL).

        aguardando_horario -> consultando -> [zerando -> aguardando_zeragem] -> concluida

    O ramo `zerando` so' roda se `encontrado != esperado` E o resultado
    for plausivel.
    """

    def __init__(self, client: Any, roteamento: RoteamentoConfig, horario_hhmm: str,
                ticker: str, bolsa: str = "F", esperado: int = 0,
                timeout_zeragem_s: float = 10.0, relogio: Any = None) -> None:
        exigir_ticker_especifico(ticker)
        self._client = client
        self._rot = roteamento
        self._horario = horario_hhmm
        self._ticker, self._bolsa, self._esperado = ticker, bolsa, esperado
        self._timeout = timeout_zeragem_s
        self._agora = relogio or (lambda: datetime.now().strftime("%H:%M"))
        self._corretora, self._conta = roteamento.conta_para(False)
        if not roteamento.senha_roteamento:
            raise SystemExit("ROTEAMENTO_SENHA_ROTEAMENTO ausente no .env")
        self.estado = "aguardando_horario"
        self.rel = RelatorioReconciliacao(ticker, int(self._corretora), self._conta, esperado)
        self._t_limite = 0.0

    @property
    def concluida(self) -> bool:
        return self.estado == "concluida"

    def _concluir(self, resultado: str, erro: str = "") -> None:
        self.rel.resultado, self.rel.erro = resultado, erro
        self.estado = "concluida"
        nivel = log.info if resultado == "bate" else log.error
        nivel("ea.reconciliacao.concluida", **self.rel.resumo())

    def _eventos_de(self, ordem_id: int) -> list[EventoOrdem]:
        return [e for e in list(self._client.ordens_eventos) if e.profit_id == ordem_id]

    def tick(self) -> None:
        try:
            self._tick()
        except TravaSimulacao as e:
            log.error("ea.reconciliacao.TRAVA", motivo=str(e))
            self._concluir("trava", str(e))
        except Exception as e:
            log.error("ea.reconciliacao.erro", erro=repr(e))
            self._concluir("erro", repr(e))

    def _tick(self) -> None:
        if self.estado == "aguardando_horario":
            if self._agora() < self._horario:
                return
            self.estado = "consultando"
            return

        if self.estado == "consultando":
            exigir_simulador(self._client, self._corretora, self._conta)
            self.rel.t_consulta = time.monotonic()
            pos = self._client.consultar_posicao(self._corretora, self._conta,
                                                 self._ticker, self._bolsa)
            self.rel.encontrado = pos.quantidade_liquida
            self.rel.preco_medio = pos.preco_medio
            self.rel.plausivel = pos.plausivel
            log.info("ea.reconciliacao.consultada", ticker=self._ticker,
                     esperado=self._esperado, encontrado=pos.quantidade_liquida,
                     preco_medio=pos.preco_medio, lado_bruto=pos.lado_bruto,
                     plausivel=pos.plausivel, retorno_dll=pos.retorno)
            if not pos.plausivel:
                self._concluir(
                    "implausivel",
                    f"GetPositionV2 devolveu valores fora do esperado (lado={pos.lado_bruto}, "
                    f"qtd={pos.quantidade_liquida}) -- CONFIRA A POSICAO NO PROFIT "
                    "manualmente. Nao zerado automaticamente.")
                return
            if pos.quantidade_liquida == self._esperado:
                self._concluir("bate")
                return
            log.error("ea.reconciliacao.DIVERGENCIA", ticker=self._ticker,
                     esperado=self._esperado, encontrado=pos.quantidade_liquida)
            self.estado = "zerando"
            return

        if self.estado == "zerando":
            exigir_simulador(self._client, self._corretora, self._conta)
            dll = self._client._dll
            oid = int(dll.SendZeroPositionAtMarket(self._conta, self._corretora,
                                                   self._ticker, self._bolsa,
                                                   self._rot.senha_roteamento))
            self.rel.zeragem_ordem_id = oid
            if oid <= 0:
                self._concluir("divergiu_zeragem_falhou",
                               f"SendZeroPositionAtMarket devolveu {oid} -- "
                               "ZERAGEM AUTOMATICA FALHOU. CONFIRA A POSICAO NO PROFIT.")
                return
            log.error("ea.reconciliacao.zeragem_enviada", ordem_id=oid)
            self._t_limite = time.monotonic() + self._timeout
            self.estado = "aguardando_zeragem"
            return

        if self.estado == "aguardando_zeragem":
            assert self.rel.zeragem_ordem_id is not None
            for e in self._eventos_de(self.rel.zeragem_ordem_id)[len(self.rel.zeragem_status):]:
                self.rel.zeragem_status.append(e.status)
                log.error("ea.reconciliacao.callback", ordem_id=e.profit_id, status=e.status,
                         executada=e.executada, restante=e.restante, texto=e.texto)
                if e.executada >= e.qtd and e.qtd > 0:
                    self.rel.t_zeragem_fill = e.t_mono
            if self.rel.t_zeragem_fill is not None:
                self._concluir("divergiu_zerado")
            elif time.monotonic() > self._t_limite:
                self._concluir("divergiu_zeragem_falhou",
                               "zeragem sem fill confirmado -- CONFIRA A POSICAO NO PROFIT")
            return
