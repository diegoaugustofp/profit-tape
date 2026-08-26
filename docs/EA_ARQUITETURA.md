# EA de fluxo por corretora — arquitetura (esboco, 2026-08-24)

## Decisao: ProfitDLL/Python, nao NTSL — e por que

Verificado nos manuais (nao suposto):
- **NTSL tem BalanceAgent()/VolumeAgent() por AgentID** -- daria pra ler o
  mesmo tipo de fluxo que sustenta agf_3/fluxo_nacional. MAS o proprio
  manual diz que BalanceAgent "nao executa em backtest" -- so' tempo real,
  historico limitado a ontem. Ou seja: **nao da' pra validar a estrategia
  DENTRO do NTSL** -- so' operar as cegas e ver o resultado ao vivo.
- **ProfitDLL tem SendOrder/SendBuyOrder/SendSellOrder/SendZeroPosition**
  nativos -- da' pra fechar o ciclo inteiro (captura -> pesquisa -> decisao
  -> ordem) na mesma linguagem, reusando o MESMO codigo que ja' foi testado
  (flow.py, normalize.py) em vez de reimplementar em NTSL e arriscar
  divergencia sutil entre o que foi validado e o que roda.

Trade-off aceito conscientemente: NTSL roda dentro do Profit Chart, mais
perto da corretora, sem depender do notebook/processo Python ficar de pe'.
O plano e' desenvolver e forward-testar em Python primeiro; portar para
NTSL so' DEPOIS de validado — igual ja' estava registrado no roadmap para
o SMC, agora aplicado ao sinal que realmente sobreviveu ao funil.

## Correcao de desenho (2026-08-24, o operador identificou o erro)

A primeira versao deste documento confundia DOIS problemas diferentes,
tratando os dois com "credencial separada". Sao problemas distintos, com
solucoes distintas:

**Problema 1 — login na ProfitDLL.** activation_key, user, password: e' o
MESMO login do Diego para tudo (DLLInitializeLogin so' habilita mais
servicos que DLLInitializeMarketLogin, roteamento incluso -- nao e' uma
conta diferente). Nao existe "credencial EA separada" aqui a menos que
exista uma segunda chave de ativacao de verdade, que nao e' o caso.

**Problema 2 — roteamento de ordem, real x simulacao.** SendBuyOrder/
SendSellOrder/SendZeroPosition recebem pwcIDAccount, pwcIDCorretora,
pwcSenha (confirmado no manual) — pwcSenha e' a "senha de roteamento",
DISTINTA da senha de login. O Diego tem DUAS contas (real e demo),
reveladas via GetAccount()/AccountCallback, cada uma com seu proprio
pwcIDAccount. **E' AQUI que mora a seguranca financeira real** -- nao na
conexao da DLL. RoteamentoConfig.conta_para() e' o unico ponto de decisao
entre as duas: default sempre demo, conta real exige
EAConfig.usar_conta_real=True explicito.

## Pergunta RESOLVIDA (2026-08-26) — teste de concorrencia real

**Resultado: as duas conexoes COEXISTEM sem conflito.**

Teste executado apos o fechamento do pregao (03:30 UTC, ~00:30 local),
seguindo o "Caminho recomendado" que estava registrado aqui: record de
teste (DLLInitializeMarketLogin, WINFUT trades, sem encerrar_em) rodando
havia ~2 minutos e estavel, com heartbeats regulares (uptime_min
crescendo 0.1 -> 1.2, arquivos/linhas estaveis, ZERO evento
profitdll.estado de desconexao) quando `ea-contas` (DLLInitializeLogin,
login completo) foi disparado num segundo terminal. O record NAO foi
afetado em nenhum momento -- heartbeat identico antes, durante e depois
da tentativa do ea-contas.

O ea-contas em si falhou (DLLInitializeLogin devolveu -2147483647), mas
por causa DIFERENTE e nao relacionada a concorrencia: horario — 03:32
UTC e' madrugada, plausivel que o servico de LOGIN COMPLETO (roteamento
de ordem) tenha janela de disponibilidade mais restrita que o de MARKET
DATA (que fica aberto mais horas para consulta de grafico historico fora
do pregao). Precisa reteste em horario comercial (mesmo fora do pregao —
ex.: 08:00 ou 19:00 local) para confirmar login completo funcionando; a
pergunta de CONCORRENCIA, porem, ja esta respondida com confianca.

IMPLICACAO PRATICA: a arquitetura de processo SEPARADO para o EA
(ea/service.py, hoje implementado) pode prosseguir sem redesenho — record e
EA podem rodar ao mesmo tempo, cada um com sua propria conexao, sem
disputa de sessao. Nao elimina os OUTROS pre-requisitos (sinal.py,
execucao.py, gestao de risco) — so' remove esta duvida especifica do
caminho critico.

## Estrutura do modulo (src/profittape/ea/)

```
ea/
  __init__.py    Doc do escopo e por que e' processo separado do record
  config.py      EAConfig, SinalConfig, RoteamentoConfig (IMPLEMENTADO)
  decisao.py     Sinal -> Acao, pura, testavel, IMPLEMENTADO (11 testes)
  sinal.py       IMPLEMENTADO — streaming trade-a-trade, equivalencia
                 exata comprovada contra o pipeline batch (ver abaixo)
  execucao.py    IMPLEMENTADO — ExecutorDeOrdens, ordens a mercado atras de dry_run — envio de ordem real bloqueado
  service.py     IMPLEMENTADO — EAService, forward-test via CLI `ea` — orquestracao (equivalente ao recorder/service.py)
```

### Por que decisao.py ja' tem logica real e o resto e' esboco

decisao.py e' pura (sinal numerico -> acao), zero I/O, testavel sem DLL
nenhuma -- por isso foi a unica parte que fez sentido implementar agora.
Ela ja' codifica a licao do teste de significancia entre quintis: Q4 vs Q5
saiu INDISTINGUIVEL (p=0.74, p=0.76) nos dois sinais que temos — entao a
entrada usa o EXTREMO (o quintil mais distante), nao um threshold no meio
que pareceria "mais sensivel" mas na verdade estaria operando numa
diferenca que a propria pesquisa mostrou ser ruido.

sinal.py, execucao.py e service.py estao IMPLEMENTADOS (2026-08-26); o
que resta de esboco e' apenas a gestao de risco -- cada modulo tem
NotImplementedError explicito e docstring listando o que falta. Implementar
esses tres exige responder a pergunta de conexao acima, e mais:

## Gestao de risco — DESENHADA E IMPLEMENTADA (2026-08-26, ea/risco.py)

Framework do operador registrado na integra: preservacao de capital,
expectativa matematica favoravel sobre taxa de acerto, mao fixa.

DECISAO CENTRAL — Rota A escolhida pelo operador:

A tensao real: o framework do operador mede sucesso por payoff (alvo >=
2x o stop), mas o sinal validado (z_agf_3 h=3, +18.14 pts liquidos) foi
medido com saida por TEMPO — entra no fechamento da barra extrema, sai
exatamente 3 barras depois, sem stop tatico nem alvo. O pct_positivo do
Q5 e' ~43%: o sinal ERRA a maioria e ganha por MAGNITUDE — alvo fixo
2:1 cortaria exatamente as caudas ganhadoras que pagam a conta.

  ROTA A (escolhida): fidelidade ao procedimento validado. Saida por
  tempo (horizonte do sinal) + stop CATASTROFICO largo derivado da conta
  de capital do operador (2% de R$5.000 = R$100 = 500 pts com 1 contrato
  WIN) — quase nunca tocado, existe como seguro de cauda, nao distorce a
  expectativa medida.

  ROTA B (evolucao futura, NAO implementada): overlay de alvo/stop com
  payoff 2:1. Exige research proprio ANTES: analise MAE/MFE dos trades
  do Q5 (quanto andou contra/a favor antes do horizonte), grid de
  stop/alvo PRE-REGISTRADO, consumindo trials. So' substitui a saida
  por tempo se MEDIR melhora sobre os +18.14 — nunca por suposicao.

O que traduziu para codigo (ea/risco.py, GestorDeRisco):
  - Circuit breaker: 3 perdas LIQUIDAS consecutivas -> bloqueia novas
    entradas ate' o proximo dia (ganho liquido zera a sequencia; ganho
    bruto menor que o custo CONTA como perda).
  - Saida por tempo no horizonte exato do sinal que abriu a posicao.
  - Stop catastrofico com prioridade sobre a saida por tempo.
  - Sem piramide por construcao (abertura com posicao aberta = excecao).
  - Mao fixa por construcao (nenhum codigo de escalonamento existe).
  - P&L do dia acumulado e logado (heartbeat + encerramento).

O que do framework NAO precisa de codigo (ja garantido por design):
  - Sem preco medio / sem parciais: decisao.py nunca piramida, saida e'
    sempre integral.
  - Sem meta diaria de ganho: nao existe contador de lucro que pare o EA.
  - Stop inalteravel: o catastrofico e' fixo na entrada, nao ha codigo
    que o mova.
  - "Mesma mao por >= 100 trades": tamanho_posicao fixo no config;
    mudanca e' decisao humana explicita de config, nunca automatica.

FLUXO POR BARRA (Rota A): com posicao aberta, o SINAL E' IGNORADO — so'
o risco manda (saida por tempo ou catastrofica). decidir() so' e'
consultado zerado e desbloqueado. E' a versao executavel mais fiel ao
que o research mediu (sem posicoes sobrepostas).

## Pre-requisitos antes de qualquer ordem real (dry_run=False)

1. [RESOLVIDO 2026-08-26] Conexao simultanea — record e EA coexistem.
2. [RESOLVIDO 2026-08-26] sinal.py implementado, com EQUIVALENCIA EXATA
   comprovada contra o pipeline batch do research (1254+ barras
   comparadas em teste de escala, zero divergencia). Bug real pego no
   caminho: fechamento de barra precisa de contador cumulativo GLOBAL
   nunca resetado (mesma regra de bars.atribuir_barras via cum_prev),
   nao um contador por-barra — a primeira versao zerava a cada
   fechamento e o erro se acumulava silenciosamente.
3. [RESOLVIDO 2026-08-26] execucao.py implementado: ExecutorDeOrdens
   com as funcoes LEGADAS planas (SendMarketBuyOrder/SendMarketSellOrder/
   SendZeroPositionAtMarket — o manual as marca obsoletas em favor de
   SendOrder V2 struct-based, mas menos partes moveis > future-proofing
   para a primeira ordem do projeto; migracao V2 registrada como evolucao
   futura). Ordens A MERCADO por design do v1. Trava em camadas: dry_run
   default, executor explicito obrigatorio, conta demo default. ARMADILHA
   conferida: SendZeroPositionAtMarket tem senha em 5o lugar, nao 3o.
   10 testes com DLL falsa verificando inclusive a ordem exata dos
   argumentos de cada chamada.
4. [RESOLVIDO 2026-08-26] Gestao de risco desenhada e implementada
   (ea/risco.py, ver secao acima). Rota A: saida por tempo + stop
   catastrofico + circuit breaker de 3 perdas.
5. Forward-test em DEMO com dry_run=True primeiro (decisoes logadas, ordem
   NENHUMA enviada) -- comparar as decisoes logadas contra o que o research
   preveria, por dias suficientes, antes de sequer cogitar dry_run=False.
6. So' entao considerar mais sinais alem de z_agf_3/z_agf_4090 -- e so'
   apos passarem pelo MESMO funil (IC -> DSR -> quintis -> significancia).
