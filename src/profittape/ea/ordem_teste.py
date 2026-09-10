"""
E2 da trilha de execucao, DENTRO do record: uma ordem de teste na conta
de simulacao, com o callback de ordem CONFIRMADO, e a trava que so'
deixa passar a corretora Simulador.

POR QUE DENTRO DO RECORD
------------------------
Uma chave de ativacao = uma conexao com a DLL. O simulador da Nelogica
so' preenche com mercado aberto, e no pregao a conexao e' a de producao.
Entao o E2 real roda na conexao do record, ticado pela thread principal
do `_loop_monitoramento` (nunca de dentro de um callback: reentrar na
DLL de um callback e' indefinido). O `ea-ordem-teste` standalone (v2.22)
continua valendo fora do pregao -- mas fora do pregao nao ha' fill.

A TRAVA (decisao do operador, 2026-09-11)
-----------------------------------------
Duas camadas, as duas conferidas contra o que a DLL ANUNCIOU, nao contra
texto de config:
  1. o par (corretora, conta) que vai receber a ordem tem que estar em
     `client.contas_vistas` (a DLL anunciou essa conta nesta sessao);
  2. o NOME da corretora, como veio no AccountCallback, tem que conter
     "simul". Corretora 32006 chama-se "Simulador"; a XP (1003) nao.
A trava roda na construcao E imediatamente antes de cada Send*. Sem
opcao de desligar aqui: este modulo nao envia para conta real, ponto.

O QUE O E2 PROVA
----------------
- a familia legada (SendMarketBuyOrder / SendZeroPositionAtMarket)
  funciona na DLL instalada, na conexao de producao;
- o OrderChangeCallback chega, com que status e em quanto tempo
  (latencia envio -> primeiro callback, envio -> preenchimento);
- a zeragem funciona e a posicao termina em zero.
Nao prova borda, slippage real (simulador preenche no toque) nem nada
sobre estrategia.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

import structlog

from ..profitdll.client import EventoOrdem
from .config import RoteamentoConfig

log = structlog.get_logger(__name__)


class TravaSimulacao(RuntimeError):
    """A conta escolhida nao e' de simulacao segundo a DLL. Nao envia."""


class _ClientRoteamento(Protocol):
    contas_vistas: list[tuple[int, str]]
    nomes_corretoras: dict[int, str]
    ordens_eventos: Any
    _dll: Any

    @property
    def corretora_pronta(self) -> bool: ...


def exigir_simulador(client: _ClientRoteamento, corretora: str, conta: str) -> None:
    """
    Levanta TravaSimulacao se (corretora, conta) nao for uma conta de
    simulacao ANUNCIADA PELA DLL nesta sessao. Usado antes de cada envio.
    """
    try:
        cid = int(corretora)
    except (TypeError, ValueError) as e:
        raise TravaSimulacao(f"corretora '{corretora}' nao e' numerica") from e
    par = (cid, str(conta))
    if par not in client.contas_vistas:
        raise TravaSimulacao(
            f"conta {par} nao foi anunciada pela DLL nesta sessao "
            f"(vistas: {client.contas_vistas}). Nao envio."
        )
    nome = client.nomes_corretoras.get(cid, "")
    if "simul" not in nome.lower():
        raise TravaSimulacao(
            f"corretora {cid} chama-se '{nome}' segundo a DLL -- nao e' o "
            f"Simulador. Este modo NUNCA envia para conta real. Nao envio."
        )


@dataclass
class RelatorioOrdemTeste:
    ticker: str
    quantidade: int
    corretora: int
    conta: str
    t_envio_compra: float | None = None
    ordem_id_compra: int | None = None
    t_primeiro_callback_compra: float | None = None
    t_fill_compra: float | None = None
    preco_medio_compra: float | None = None
    status_compra: list[str] = field(default_factory=list)
    t_envio_zeragem: float | None = None
    ordem_id_zeragem: int | None = None
    t_fill_zeragem: float | None = None
    preco_medio_zeragem: float | None = None
    status_zeragem: list[str] = field(default_factory=list)
    resultado: str = ""  # ok | compra_recusada | timeout_fill | zeragem_recusada | trava | erro
    erro: str = ""

    def resumo(self) -> dict[str, Any]:
        def _ms(a: float | None, b: float | None) -> float | None:
            return round((b - a) * 1000, 1) if a is not None and b is not None else None

        return {
            "resultado": self.resultado,
            "ticker": self.ticker,
            "quantidade": self.quantidade,
            "corretora": self.corretora,
            "conta": self.conta,
            "ordem_id_compra": self.ordem_id_compra,
            "latencia_primeiro_callback_ms": _ms(
                self.t_envio_compra, self.t_primeiro_callback_compra
            ),
            "latencia_fill_compra_ms": _ms(self.t_envio_compra, self.t_fill_compra),
            "preco_medio_compra": self.preco_medio_compra,
            "status_compra": self.status_compra,
            "ordem_id_zeragem": self.ordem_id_zeragem,
            "latencia_fill_zeragem_ms": _ms(self.t_envio_zeragem, self.t_fill_zeragem),
            "preco_medio_zeragem": self.preco_medio_zeragem,
            "status_zeragem": self.status_zeragem,
            "erro": self.erro,
        }


class OrdemDeTeste:
    """
    Maquina de estados ticada pela thread principal do record.

        aguardando_horario -> enviando_compra -> aguardando_fill ->
        zerando -> aguardando_zeragem -> concluida
    (qualquer estado -> concluida com `resultado` de erro)

    `tick()` e' chamado a cada 0,5 s. Cada passo faz no maximo UMA chamada
    de DLL e volta. Timeouts curtos: o record nao pode ficar refem disto.
    """

    def __init__(
        self,
        client: _ClientRoteamento,
        roteamento: RoteamentoConfig,
        horario_hhmm: str,
        ticker: str = "WINFUT",
        bolsa: str = "F",
        quantidade: int = 1,
        timeout_fill_s: float = 10.0,
        relogio: Any = None,
    ) -> None:
        if quantidade != 1:
            raise ValueError("E2 e' UM contrato. Quantidade maior e' outro degrau.")
        self._client = client
        self._rot = roteamento
        self._horario = horario_hhmm
        self._ticker, self._bolsa, self._qtd = ticker, bolsa, quantidade
        self._timeout = timeout_fill_s
        self._agora = relogio or (lambda: datetime.now().strftime("%H:%M"))
        # demo, SEMPRE: conta_para(False). A trava confere contra a DLL.
        self._corretora, self._conta = roteamento.conta_para(False)
        if not roteamento.senha_roteamento:
            raise SystemExit("ROTEAMENTO_SENHA_ROTEAMENTO ausente no .env")
        self.estado = "aguardando_horario"
        self.rel = RelatorioOrdemTeste(ticker, quantidade, int(self._corretora), self._conta)
        self._t_limite = 0.0

    # ------------------------------------------------------------------
    @property
    def concluida(self) -> bool:
        return self.estado == "concluida"

    def _concluir(self, resultado: str, erro: str = "") -> None:
        self.rel.resultado, self.rel.erro = resultado, erro
        self.estado = "concluida"
        log.info("ea.ordem_teste.concluida", **self.rel.resumo())

    def _eventos_de(self, ordem_id: int) -> list[EventoOrdem]:
        return [e for e in list(self._client.ordens_eventos) if e.profit_id == ordem_id]

    def _enviar(self, chamada: str) -> int:
        # A trava, de novo, a um passo da DLL. corretora_pronta AGORA
        # (evento real de 09/09: oscila durante queda de rede).
        exigir_simulador(self._client, self._corretora, self._conta)
        if not self._client.corretora_pronta:
            raise TravaSimulacao("corretora nao esta' pronta neste instante")
        dll = self._client._dll
        if chamada == "compra":
            return int(
                dll.SendMarketBuyOrder(
                    self._conta,
                    self._corretora,
                    self._rot.senha_roteamento,
                    self._ticker,
                    self._bolsa,
                    self._qtd,
                )
            )
        # ATENCAO: senha em 5o lugar (ver bindings.py)
        return int(
            dll.SendZeroPositionAtMarket(
                self._conta, self._corretora, self._ticker, self._bolsa, self._rot.senha_roteamento
            )
        )

    # ------------------------------------------------------------------
    def tick(self) -> None:
        try:
            self._tick()
        except TravaSimulacao as e:
            log.error("ea.ordem_teste.TRAVA", motivo=str(e))
            self._concluir("trava", str(e))
        except Exception as e:
            log.error("ea.ordem_teste.erro", erro=repr(e))
            self._concluir("erro", repr(e))

    def _tick(self) -> None:
        if self.estado == "aguardando_horario":
            if self._agora() < self._horario:
                return
            log.info(
                "ea.ordem_teste.iniciando",
                horario=self._horario,
                ticker=self._ticker,
                corretora=self._corretora,
                conta=self._conta,
                contas_vistas=self._client.contas_vistas,
                nomes=self._client.nomes_corretoras,
            )
            self.estado = "enviando_compra"
            return

        if self.estado == "enviando_compra":
            self.rel.t_envio_compra = time.monotonic()
            oid = self._enviar("compra")
            self.rel.ordem_id_compra = oid
            if oid <= 0:
                self._concluir("compra_recusada", f"SendMarketBuyOrder devolveu {oid}")
                return
            log.info("ea.ordem_teste.compra_enviada", ordem_id=oid)
            self._t_limite = time.monotonic() + self._timeout
            self.estado = "aguardando_fill"
            return

        if self.estado == "aguardando_fill":
            assert self.rel.ordem_id_compra is not None
            evs = self._eventos_de(self.rel.ordem_id_compra)
            for e in evs[len(self.rel.status_compra) :]:
                self.rel.status_compra.append(e.status)
                if self.rel.t_primeiro_callback_compra is None:
                    self.rel.t_primeiro_callback_compra = e.t_mono
                log.info(
                    "ea.ordem_teste.callback",
                    ordem_id=e.profit_id,
                    status=e.status,
                    qtd=e.qtd,
                    executada=e.executada,
                    restante=e.restante,
                    preco_medio=e.preco_medio,
                    texto=e.texto,
                )
                if e.executada >= e.qtd and e.qtd > 0:
                    self.rel.t_fill_compra = e.t_mono
                    self.rel.preco_medio_compra = e.preco_medio
            if self.rel.t_fill_compra is not None:
                self.estado = "zerando"
            elif time.monotonic() > self._t_limite:
                log.warning(
                    "ea.ordem_teste.fill_nao_confirmado",
                    status=self.rel.status_compra,
                    nota="zerando mesmo assim",
                )
                self.rel.resultado = "timeout_fill"
                self.estado = "zerando"
            return

        if self.estado == "zerando":
            self.rel.t_envio_zeragem = time.monotonic()
            oid = self._enviar("zeragem")
            self.rel.ordem_id_zeragem = oid
            if oid <= 0:
                self._concluir(
                    "zeragem_recusada",
                    f"SendZeroPositionAtMarket devolveu {oid} -- CONFIRA A POSICAO NO PROFIT",
                )
                return
            log.info("ea.ordem_teste.zeragem_enviada", ordem_id=oid)
            self._t_limite = time.monotonic() + self._timeout
            self.estado = "aguardando_zeragem"
            return

        if self.estado == "aguardando_zeragem":
            assert self.rel.ordem_id_zeragem is not None
            evs = self._eventos_de(self.rel.ordem_id_zeragem)
            for e in evs[len(self.rel.status_zeragem) :]:
                self.rel.status_zeragem.append(e.status)
                log.info(
                    "ea.ordem_teste.callback",
                    ordem_id=e.profit_id,
                    status=e.status,
                    qtd=e.qtd,
                    executada=e.executada,
                    restante=e.restante,
                    preco_medio=e.preco_medio,
                    texto=e.texto,
                )
                if e.executada >= e.qtd and e.qtd > 0:
                    self.rel.t_fill_zeragem = e.t_mono
                    self.rel.preco_medio_zeragem = e.preco_medio
            if self.rel.t_fill_zeragem is not None:
                self._concluir(self.rel.resultado or "ok")
            elif time.monotonic() > self._t_limite:
                self._concluir(
                    self.rel.resultado or "timeout_zeragem",
                    "zeragem sem fill confirmado -- CONFIRA A POSICAO NO PROFIT",
                )
            return
