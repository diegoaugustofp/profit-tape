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
  - service.py: orquestracao (equivalente ao recorder/service.py, mas
    para trading) -- proximo passo real, agora que sinal.py e
    execucao.py estao prontos.
  - Gestao de risco (stop, tamanho de posicao, limite de perda diaria)
    -- nao desenhada ainda, e' pre-requisito ANTES de qualquer envio
    de ordem real, nao um detalhe para depois.

JA IMPLEMENTADO E TESTADO:
  - config.py: EAConfig, SinalConfig, RoteamentoConfig
  - decisao.py: sinal -> acao, pura, testavel
  - sinal.py: construcao de barra ao vivo (streaming) + z-score, com
    EQUIVALENCIA EXATA comprovada contra o pipeline batch do research
    (bars.py+flow.py+normalize.py) -- 1254+ barras comparadas, zero
    divergencia. Bug real pego no caminho: o fechamento de barra usa
    contador cumulativo GLOBAL nunca resetado (mesma regra do batch),
    nao um contador por-barra -- a primeira versao zerava a cada
    fechamento e o erro se acumulava silenciosamente barra a barra.
  - contas.py: GetAccount via login completo (diagnostico)
  - execucao.py: ExecutorDeOrdens traduz Decisao -> SendMarketBuyOrder/
    SendMarketSellOrder/SendZeroPositionAtMarket (funcoes legadas planas,
    ordens A MERCADO por design do v1). Trava em camadas: dry_run=True
    default so' loga; dry_run=False sem executor explicito recusa;
    conta default e' SEMPRE demo. ARMADILHA conferida no manual: a ordem
    dos argumentos de SendZeroPositionAtMarket e' diferente (senha em
    5o lugar, nao 3o).
"""
