"""
EA de fluxo por corretora (fase de ESBOCO — nao operacional ainda).

Consome os sinais validados pelo research/ (docs/RESEARCH_PLANO.md):
z_agf_3 (XP) e z_agf_4090 (Toro/Santander-varejo) ate' agora, os unicos que
sobreviveram walk-forward + DSR + teste de quintis + teste de significancia
entre quintis. Mais sinais entram aqui SO' apos passar pelo mesmo funil.

Por que processo SEPARADO do record, nao integrado:
  1. Isolamento de falha. O record levou semanas de dureza para ficar
     confiavel (fsync, verificacao de footer, retry de conexao). Um EA
     tem modos de falha DIFERENTES (ordem rejeitada, posicao presa,
     stop nao executado) que nao devem ter chance nenhuma de derrubar
     a captura -- processos separados, sem memoria compartilhada,
     garantem isso por construcao.
  2. A pergunta se DUAS CONEXOES SIMULTANEAS a DLL (record com
     DLLInitializeMarketLogin + EA com DLLInitializeLogin) coexistem
     ou uma derruba a outra NAO ESTA CONFIRMADA no manual -- ver
     docs/EA_ARQUITETURA.md. Nao e' resolvida por credencial separada
     (login da DLL e' UM SO, o do Diego -- ver config.py); e' resolvida
     testando com cautela, de preferencia fora do horario de pregao.

SEGURANCA FINANCEIRA (dinheiro real x simulacao) e' um problema DIFERENTE
do acima, resolvido em outro lugar: RoteamentoConfig.conta_para() em
config.py e' o unico ponto de decisao entre id_account_demo e
id_account_real -- default sempre demo, real exige EAConfig.usar_conta_
real=True explicito. Ver correcao registrada em config.py (2026-08-24,
o operador identificou que a versao anterior confundia login de DLL com
conta de roteamento).

O QUE AINDA NAO ESTA PRONTO (deliberado, nao esquecido):
  - execucao.py: envio de ordem real. Fica atras de dry_run=True ate'
    forward-test em DEMO confirmar a decisao.py contra dado ao vivo.
  - service.py: construcao de barra ao vivo a partir de trade tick-a-
    tick (reaproveitando bars.py/flow.py, mas em streaming continuo
    em vez de arquivo fechado) -- trabalho novo, nao existe ainda.
  - Gestao de risco (stop, tamanho de posicao, limite de perda diaria)
    -- nao desenhada ainda, e' pre-requisito ANTES de qualquer envio
    de ordem real, nao um detalhe para depois.
"""
