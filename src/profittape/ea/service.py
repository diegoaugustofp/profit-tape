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
  1. Confirmar (fora do horario de pregao, sem risco) se DLLInitializeLogin
     funciona -- roda GetAccount() uma vez e confirma que devolve os dois
     IDAccount (demo e real).
  2. Confirmar se abrir uma SEGUNDA conexao (DLLInitializeLogin, processo
     do EA) enquanto o record ja' tem DLLInitializeMarketLogin aberto
     coexiste ou derruba a captura -- NAO CONFIRMADO no manual, teste
     controlado necessario (docs/EA_ARQUITETURA.md).
  3. sinal.py e execucao.py (send_order real) implementados e testados.
  4. Gestao de risco desenhada.

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
