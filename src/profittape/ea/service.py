"""
STUB — orquestracao do EA (equivalente ao recorder/service.py, para trading).

DESENHO PRETENDIDO (nao implementado):
  - Conecta via DLLInitializeLogin (login COMPLETO -- as MESMAS credenciais
    de config.Credenciais que o record usa, so' com mais servicos
    habilitados, roteamento incluso; NAO existe credencial de DLL separada
    para o EA -- ver correcao registrada em config.py e
    docs/EA_ARQUITETURA.md).
  - Roteamento de ordem usa RoteamentoConfig (config.py) -- id_account_demo
    por padrao, id_account_real so' com EAConfig.usar_conta_real=True
    explicito.
  - Para cada sinal em EAConfig.sinais: mantem um ConstrutorDeSinalAoVivo
    (sinal.py, ainda nao implementado).
  - A cada barra fechada: decisao.decidir() -> execucao.executar().
  - Mesma disciplina operacional do recorder: log estruturado, heartbeat,
    alertas Telegram (reusa alertas.py), encerramento gracioso.

PRE-REQUISITOS antes de qualquer linha de codigo aqui:
  1. Confirmar DLLInitializeLogin funcionando em HORARIO COMERCIAL (teste
     de 2026-08-26 rodou de madrugada e falhou com erro -2147483647 --
     causa provavel: janela de disponibilidade do servico de roteamento,
     nao concorrencia -- ver item 2. Reteste as 08:00 ou 19:00 local, fora
     do pregao, e roda GetAccount() para confirmar os dois IDAccount).
  2. [RESOLVIDO 2026-08-26] Duas conexoes simultaneas (record com
     DLLInitializeMarketLogin + EA com DLLInitializeLogin) COEXISTEM sem
     conflito -- testado com record estavel por ~2min, sem nenhuma
     interrupcao durante a tentativa de login completo em paralelo. Ver
     docs/EA_ARQUITETURA.md para o registro completo do teste.
  3. [RESOLVIDO 2026-08-26] sinal.py implementado — equivalencia exata
     comprovada contra o pipeline batch do research. Uso pretendido aqui:
     uma instancia de ConstrutorDeSinalAoVivo por simbolo, alimentada
     trade a trade pelo callback da DLL; cada BarraFechada devolvida vai
     direto para decisao.decidir().
  4. [RESOLVIDO 2026-08-26] execucao.py implementado e testado (10
     testes com DLL falsa). Uso pretendido aqui: um ExecutorDeOrdens por
     simbolo, construido com a dll conectada e RoteamentoConfig; cada
     Decisao devolvida por decisao.decidir() vai para executar(decisao,
     dry_run, executor).
  5. Gestao de risco desenhada — ULTIMO bloqueador antes do forward-test.

Ate' la', este arquivo existe so' para documentar o formato que o service
do EA vai ter -- nao instancie.
"""

from __future__ import annotations


class EAService:
    def __init__(self, *_args, **_kwargs) -> None:
        raise NotImplementedError(
            "EAService e' esboco -- ver docstring do modulo e "
            "docs/EA_ARQUITETURA.md para os pre-requisitos antes de "
            "implementar."
        )
