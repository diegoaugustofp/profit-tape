"""
STUB — envio de ordem. Fica atras de dry_run ate' forward-test confirmar.

O QUE FALTA:
  1. Metodos no ProfitClient (profitdll/client.py) para send_buy_order /
     send_sell_order / send_zero_position -- bindings novos sobre
     SendBuyOrder/SendSellOrder/SendZeroPosition da ProfitDLL (confirmados
     existentes no manual: recebem pwcIDAccount, pwcIDCorretora, pwcSenha
     -- ver RoteamentoConfig em config.py para de onde vem cada um).
  2. OrderChangeCallback / AccountCallback -- para saber se a ordem foi
     aceita, executada, rejeitada. Sem isso o EA fica cego sobre o proprio
     resultado.
  3. Gestao de risco ANTES de qualquer envio real: stop de perda por
     posicao, limite de perda diaria, o que fazer se a ordem for rejeitada
     (retry? aborta o dia?). NADA disso esta desenhado ainda -- e' pre-
     requisito, nao detalhe para depois.

dry_run=True (o default em EAConfig) faz este modulo so' LOGAR a decisao
que teria sido executada, nunca falar com a DLL. E' o modo em que o EA
deve rodar durante TODO o forward-test inicial -- inclusive depois de
implementado de verdade, o roteamento sempre vai para id_account_demo
(RoteamentoConfig.conta_para(usar_conta_real=False) por padrao) ate' haver
decisao explicita e documentada de operar com id_account_real.
"""

from __future__ import annotations

import structlog

from .decisao import Decisao

log = structlog.get_logger(__name__)


def executar(decisao: Decisao, dry_run: bool = True) -> None:
    if dry_run:
        log.info("ea.decisao_dry_run", acao=decisao.acao.value,
                 motivo=decisao.motivo, sinal=round(decisao.sinal_valor, 3),
                 feature=decisao.feature)
        return
    raise NotImplementedError(
        "envio de ordem real nao implementado -- ver docstring do modulo. "
        "dry_run=False so' pode ser ligado apos: (1) send_order no "
        "ProfitClient (usando RoteamentoConfig.conta_para() para o "
        "IDAccount, NUNCA hardcoded), (2) OrderChangeCallback, "
        "(3) gestao de risco desenhada e testada, (4) forward-test em "
        "DEMO validando a decisao."
    )
