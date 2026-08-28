"""
Envio de ordem — implementado, com trava de seguranca em camadas.

CAMADAS DE PROTECAO (todas precisam ser atravessadas para uma ordem real):
  1. dry_run=True (default em EAConfig): so' LOGA a decisao, nunca toca DLL.
  2. Sem um ExecutorDeOrdens construido explicitamente (exige RoteamentoConfig
     valido + dll conectada via login completo), dry_run=False RECUSA.
  3. RoteamentoConfig.conta_para(): default SEMPRE demo; conta real exige
     usar_conta_real=True explicito E ROTEAMENTO_ID_ACCOUNT_REAL no .env.
  4. service.py (orquestracao) continua esboco — nao existe caminho em
     producao que chegue aqui ainda; forward-test em DEMO e gestao de
     risco continuam pre-requisitos ANTES de qualquer uso real (ver
     docs/EA_ARQUITETURA.md).

FUNCOES DA DLL USADAS (legadas planas — ver decisao de design em
profitdll/bindings.py): SendMarketBuyOrder / SendMarketSellOrder /
SendZeroPositionAtMarket. Ordens A MERCADO por design do EA v1: segue
sinal com stop largo, sem gestao de preco limite. Retorno Int64 > 0 e' o
ID local da ordem (comparavel com o retorno do OrderChangeCallback);
retorno <= 0 e' erro.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from .config import RoteamentoConfig
from .decisao import Acao, Decisao

log = structlog.get_logger(__name__)


@dataclass
class ResultadoOrdem:
    enviada: bool
    ordem_id: int | None       # ID local (retorno da DLL) quando enviada
    motivo: str


class ExecutorDeOrdens:
    """
    Traduz Decisao -> chamada de DLL. Uma instancia por simbolo.

    dll_injetada: em teste, um fake com os mesmos metodos; em producao, o
    handle carregado via load_dll + DLLInitializeLogin JA' CONECTADO (a
    conexao e' responsabilidade do service, nao daqui).
    """

    def __init__(self, dll: Any, roteamento: RoteamentoConfig,
                ticker: str, bolsa: str, quantidade: int,
                usar_conta_real: bool = False) -> None:
        if quantidade <= 0:
            raise ValueError("quantidade precisa ser positiva")
        self._dll = dll
        self._rot = roteamento
        self._ticker = ticker
        self._bolsa = bolsa
        self._quantidade = quantidade
        self._usar_conta_real = usar_conta_real
        # Resolve a conta JA' NA CONSTRUCAO — se estiver mal configurada,
        # falha ruidosamente antes de qualquer sinal aparecer, nao no meio
        # do pregao na primeira ordem.
        self._conta = roteamento.conta_para(usar_conta_real)
        if not roteamento.senha_roteamento:
            raise SystemExit(
                "ROTEAMENTO_SENHA_ROTEAMENTO nao configurada no .env — "
                "necessaria para qualquer envio de ordem, mesmo em demo."
            )

    def executar(self, decisao: Decisao) -> ResultadoOrdem:
        if decisao.acao == Acao.NADA:
            return ResultadoOrdem(False, None, "acao NADA — nada a enviar")

        if decisao.acao == Acao.COMPRAR:
            ordem_id = self._dll.SendMarketBuyOrder(
                self._conta, self._rot.id_corretora, self._rot.senha_roteamento,
                self._ticker, self._bolsa, self._quantidade)
            verbo = "compra a mercado"
        elif decisao.acao == Acao.VENDER:
            ordem_id = self._dll.SendMarketSellOrder(
                self._conta, self._rot.id_corretora, self._rot.senha_roteamento,
                self._ticker, self._bolsa, self._quantidade)
            verbo = "venda a mercado"
        elif decisao.acao == Acao.ZERAR:
            # ATENCAO ordem de argumentos DIFERENTE: senha em 5o lugar
            # (depois de ticker/bolsa) — conferido no manual, ver bindings.py.
            ordem_id = self._dll.SendZeroPositionAtMarket(
                self._conta, self._rot.id_corretora,
                self._ticker, self._bolsa, self._rot.senha_roteamento)
            verbo = "zerar a mercado"
        else:  # pragma: no cover — enum fechado
            raise ValueError(f"acao desconhecida: {decisao.acao}")

        if ordem_id > 0:
            log.info("ea.ordem_enviada", verbo=verbo, ordem_id=ordem_id,
                     ticker=self._ticker, quantidade=self._quantidade,
                     conta_demo=(not self._usar_conta_real),
                     motivo=decisao.motivo)
            return ResultadoOrdem(True, ordem_id, verbo)

        log.error("ea.ordem_recusada", verbo=verbo, retorno=ordem_id,
                  ticker=self._ticker, motivo=decisao.motivo)
        return ResultadoOrdem(False, None,
                              f"{verbo} RECUSADA pela DLL (retorno {ordem_id})")


def executar(decisao: Decisao, dry_run: bool = True,
            executor: ExecutorDeOrdens | None = None) -> ResultadoOrdem | None:
    """
    Ponto de entrada usado pelo service. dry_run=True (default) so' loga;
    dry_run=False exige um ExecutorDeOrdens construido explicitamente —
    sem ele, RECUSA (camada 2 da protecao, ver docstring do modulo).
    """
    if dry_run:
        log.info("ea.decisao_dry_run", acao=decisao.acao.value,
                 motivo=decisao.motivo, sinal=round(decisao.sinal_valor, 3),
                 feature=decisao.feature)
        return None
    if executor is None:
        raise RuntimeError(
            "dry_run=False sem ExecutorDeOrdens — construir um exige "
            "RoteamentoConfig valido e dll conectada, de proposito. Ver "
            "docs/EA_ARQUITETURA.md para os pre-requisitos que continuam "
            "abertos (gestao de risco, forward-test em DEMO)."
        )
    return executor.executar(decisao)
