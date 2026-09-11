"""
Envio de ordem — implementado, com trava de seguranca em camadas.

CAMADAS DE PROTECAO (todas precisam ser atravessadas para uma ordem real):
  1. dry_run=True (default em EAConfig): so' LOGA a decisao, nunca toca DLL.
  2. Sem um ExecutorDeOrdens construido explicitamente (exige RoteamentoConfig
     valido + dll conectada via login completo), dry_run=False RECUSA.
  3. RoteamentoConfig.conta_para(): default SEMPRE demo; conta real exige
     usar_conta_real=True explicito E ROTEAMENTO_ID_ACCOUNT_REAL no .env.
  4. exigir_conta_anunciada (E4, 2026-09-11): o par (corretora, conta) que
     vai receber a ordem tem que ter sido ANUNCIADO PELA DLL nesta sessao
     -- pega o erro classico de conta/corretora desencontrada, em
     qualquer modo (demo ou real). Quem integra este executor para um
     modo que NUNCA pode tocar conta real (E4: forward em demo) chama
     `exigir_simulador` (mais forte, confere o NOME da corretora) na
     camada de cima, antes de construir -- ver recorder/service.py.

FUNCOES DA DLL USADAS (legadas planas — ver decisao de design em
profitdll/bindings.py): SendMarketBuyOrder / SendMarketSellOrder /
SendZeroPositionAtMarket. Ordens A MERCADO por design do EA v1: segue
sinal com stop largo, sem gestao de preco limite. Retorno Int64 > 0 e' o
ID local da ordem (comparavel com o retorno do OrderChangeCallback);
retorno <= 0 e' erro.

CONFIRMACAO DE FILL, SLIPPAGE E LATENCIA (E4, 2026-09-11)
-----------------------------------------------------------
Ate' aqui (E2/E3) "ordem enviada" so' significava "a DLL aceitou"
(ordem_id > 0) -- nunca se esperou o preenchimento de verdade. E4 e'
justamente medir isto: depois de enviar, espera o OrderChangeCallback
confirmar `executada >= quantidade` (mesmo mecanismo de
`ordens_eventos` do E2/ordem_teste.py), e so' entao calcula:
  latencia_ms   = tempo do envio ate' o callback de fill
  slippage_pts  = (preco_fill - preco_referencia) * sinal_do_lado
    sinal_do_lado = +1 para compra (preco maior = pior), -1 para venda
    (preco menor = pior) -- slippage positivo e' SEMPRE contra o EA,
    negativo e' a favor (encheu melhor que o preco de referencia).
`preco_referencia` e' o close da barra que gerou o sinal -- o preco que
o research assumiu como entrada ao medir o resultado historico. Sem
fill confirmado dentro do timeout, os campos ficam None e o resultado
sinaliza isso explicitamente (nao e' erro fatal -- ordem pode ter sido
aceita e preenchida sem o callback chegar a tempo; CONFIRA NO PROFIT).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import structlog

from .config import RoteamentoConfig
from .decisao import Acao, Decisao
from .ordem_teste import exigir_conta_anunciada, exigir_simulador, exigir_ticker_especifico

log = structlog.get_logger(__name__)


@dataclass
class ResultadoOrdem:
    enviada: bool
    ordem_id: int | None       # ID local (retorno da DLL) quando enviada
    motivo: str
    # Preenchidos so' quando a ordem foi enviada E o fill foi aguardado
    # (ver docstring do modulo). None em dry_run ou se o fill nao
    # confirmou dentro do timeout.
    preco_fill: float | None = None
    latencia_ms: float | None = None
    slippage_pts: float | None = None
    fill_confirmado: bool = False


class ExecutorDeOrdens:
    """
    Traduz Decisao -> chamada de DLL. Uma instancia por simbolo.

    `client`: o ProfitClient JA' CONECTADO (a conexao e' responsabilidade
    de quem monta o service, nao daqui) -- precisa ser o client completo,
    nao so' o handle da DLL, porque a trava (`exigir_conta_anunciada`) e
    a confirmacao de fill (`client.ordens_eventos`) leem estado dele.
    Em teste, um fake com os mesmos atributos/metodos.
    """

    def __init__(self, client: Any, roteamento: RoteamentoConfig,
                ticker: str, bolsa: str, quantidade: int,
                usar_conta_real: bool = False,
                apenas_simulador: bool = False,
                timeout_fill_s: float = 10.0) -> None:
        if quantidade <= 0:
            raise ValueError("quantidade precisa ser positiva")
        # Trava (E4, 2026-09-11, achada tarde -- so' OrdemDeTeste e
        # ReconciliadorPosicao tinham isto): `ticker` PRECISA ser o
        # contrato ESPECIFICO em vigor. O `symbol` da EAConfig e' "WINFUT"
        # -- serve para gerar o sinal (barra de volume, dado de mercado),
        # mas a ProfitDLL nao aceita agregador no ENVIO de ordem (medido
        # 2026-09-11 no E2: "Ordem invalida"). Quem monta o ExecutorDeOrdens
        # tem que passar o contrato vigente separadamente -- nunca reusar
        # `ea_cfg.symbol` aqui.
        exigir_ticker_especifico(ticker)
        self._client = client
        self._rot = roteamento
        self._ticker = ticker
        self._bolsa = bolsa
        self._quantidade = quantidade
        self._usar_conta_real = usar_conta_real
        # apenas_simulador (E4): quando True, TODA chamada confere o NOME
        # da corretora (exigir_simulador), nao so' que a conta foi
        # anunciada. E4 e' "forward em demo com ordens reais" por
        # definicao -- quem liga este modo NUNCA deveria conseguir tocar
        # conta real mesmo com usar_conta_real=True por engano na config.
        self._apenas_simulador = apenas_simulador
        self._timeout_fill = timeout_fill_s
        # Resolve a conta JA' NA CONSTRUCAO — se estiver mal configurada,
        # falha ruidosamente antes de qualquer sinal aparecer, nao no meio
        # do pregao na primeira ordem.
        # Corretora e conta viajam JUNTAS. Ate 2026-08-31 a conta vinha de
        # `conta_para()` e a corretora de `self._rot.id_corretora` -- um
        # campo unico. Com a licenca corrigida, `ea-contas` mostrou que a
        # demo esta na corretora 32006 (Simulador) e a real na 1003 (XP):
        # usar conta real com a corretora do campo unico enviaria a ordem
        # da XP com o ID do simulador. Nao da' erro de configuracao.
        self._corretora, self._conta = roteamento.conta_para(usar_conta_real)
        if not roteamento.senha_roteamento:
            raise SystemExit(
                "ROTEAMENTO_SENHA_ROTEAMENTO nao configurada no .env — "
                "necessaria para qualquer envio de ordem, mesmo em demo."
            )

    def _eventos_de(self, ordem_id: int) -> list[Any]:
        return [e for e in list(self._client.ordens_eventos) if e.profit_id == ordem_id]

    def _aguardar_fill(self, ordem_id: int, quantidade: int,
                       t_envio: float) -> tuple[bool, float | None, float | None]:
        """Poll em ordens_eventos ate' `executada >= quantidade` ou o
        timeout. Devolve (confirmado, preco_medio, latencia_ms)."""
        limite = time.monotonic() + self._timeout_fill
        vistos = 0
        while time.monotonic() < limite:
            eventos = self._eventos_de(ordem_id)
            for e in eventos[vistos:]:
                if e.executada >= quantidade and quantidade > 0:
                    latencia_ms = (e.t_mono - t_envio) * 1000
                    return True, float(e.preco_medio), latencia_ms
            vistos = len(eventos)
            time.sleep(0.05)
        return False, None, None

    def executar(self, decisao: Decisao,
                preco_referencia: float | None = None) -> ResultadoOrdem:
        if decisao.acao == Acao.NADA:
            return ResultadoOrdem(False, None, "acao NADA — nada a enviar")

        # Camada 4: par (corretora, conta) tem que ter sido anunciado
        # pela DLL nesta sessao -- antes de CADA envio, nao so' na
        # construcao (a lista de contas so' se popula apos GetAccount()).
        # `apenas_simulador=True` (E4) exige tambem o NOME da corretora
        # conter "simul" -- checagem mais forte, mesma de OrdemDeTeste.
        if self._apenas_simulador:
            exigir_simulador(self._client, self._corretora, self._conta)
        else:
            exigir_conta_anunciada(self._client, self._corretora, self._conta)
        dll = self._client._dll

        t_envio = time.monotonic()
        if decisao.acao == Acao.COMPRAR:
            ordem_id = dll.SendMarketBuyOrder(
                self._conta, self._corretora, self._rot.senha_roteamento,
                self._ticker, self._bolsa, self._quantidade)
            verbo, sinal_lado = "compra a mercado", 1
        elif decisao.acao == Acao.VENDER:
            ordem_id = dll.SendMarketSellOrder(
                self._conta, self._corretora, self._rot.senha_roteamento,
                self._ticker, self._bolsa, self._quantidade)
            verbo, sinal_lado = "venda a mercado", -1
        elif decisao.acao == Acao.ZERAR:
            # ATENCAO ordem de argumentos DIFERENTE: senha em 5o lugar
            # (depois de ticker/bolsa) — conferido no manual, ver bindings.py.
            ordem_id = dll.SendZeroPositionAtMarket(
                self._conta, self._corretora,
                self._ticker, self._bolsa, self._rot.senha_roteamento)
            verbo, sinal_lado = "zerar a mercado", 0
        else:  # pragma: no cover — enum fechado
            raise ValueError(f"acao desconhecida: {decisao.acao}")

        if ordem_id <= 0:
            log.error("ea.ordem_recusada", verbo=verbo, retorno=ordem_id,
                      ticker=self._ticker, motivo=decisao.motivo)
            return ResultadoOrdem(False, None,
                                  f"{verbo} RECUSADA pela DLL (retorno {ordem_id})")

        log.info("ea.ordem_enviada", verbo=verbo, ordem_id=ordem_id,
                 ticker=self._ticker, quantidade=self._quantidade,
                 conta_demo=(not self._usar_conta_real), motivo=decisao.motivo)
        confirmado, preco_fill, latencia_ms = self._aguardar_fill(
            ordem_id, self._quantidade, t_envio)
        slippage_pts = None
        if (confirmado and preco_fill is not None
                and preco_referencia is not None and sinal_lado != 0):
            slippage_pts = (preco_fill - preco_referencia) * sinal_lado
        if confirmado:
            log.info("ea.ordem_preenchida", ordem_id=ordem_id, preco_fill=preco_fill,
                     latencia_ms=round(latencia_ms, 1) if latencia_ms else None,
                     slippage_pts=(round(slippage_pts, 1)
                                  if slippage_pts is not None else None))
        else:
            log.error("ea.ordem_sem_confirmacao_de_fill", ordem_id=ordem_id,
                      timeout_s=self._timeout_fill,
                      nota="ordem foi ACEITA pela DLL mas o callback de fill nao "
                           "chegou dentro do timeout -- CONFIRA NO PROFIT")
        return ResultadoOrdem(True, ordem_id, verbo, preco_fill=preco_fill,
                              latencia_ms=latencia_ms, slippage_pts=slippage_pts,
                              fill_confirmado=confirmado)


def executar(decisao: Decisao, dry_run: bool = True,
            executor: ExecutorDeOrdens | None = None,
            preco_referencia: float | None = None) -> ResultadoOrdem | None:
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
    return executor.executar(decisao, preco_referencia=preco_referencia)
