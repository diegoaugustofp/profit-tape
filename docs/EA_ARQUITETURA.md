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
(ea/service.py, ainda esboco) pode prosseguir sem redesenho — record e
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
  execucao.py    STUB atras de dry_run — envio de ordem real bloqueado
  service.py     STUB — orquestracao (equivalente ao recorder/service.py)
```

### Por que decisao.py ja' tem logica real e o resto e' esboco

decisao.py e' pura (sinal numerico -> acao), zero I/O, testavel sem DLL
nenhuma -- por isso foi a unica parte que fez sentido implementar agora.
Ela ja' codifica a licao do teste de significancia entre quintis: Q4 vs Q5
saiu INDISTINGUIVEL (p=0.74, p=0.76) nos dois sinais que temos — entao a
entrada usa o EXTREMO (o quintil mais distante), nao um threshold no meio
que pareceria "mais sensivel" mas na verdade estaria operando numa
diferenca que a propria pesquisa mostrou ser ruido.

sinal.py, execucao.py, service.py sao esboco de proposito -- cada um tem
NotImplementedError explicito e docstring listando o que falta. Implementar
esses tres exige responder a pergunta de conexao acima, e mais:

## Pre-requisitos antes de qualquer ordem real (dry_run=False)

1. [RESOLVIDO 2026-08-26] Conexao simultanea — record e EA coexistem.
2. [RESOLVIDO 2026-08-26] sinal.py implementado, com EQUIVALENCIA EXATA
   comprovada contra o pipeline batch do research (1254+ barras
   comparadas em teste de escala, zero divergencia). Bug real pego no
   caminho: fechamento de barra precisa de contador cumulativo GLOBAL
   nunca resetado (mesma regra de bars.atribuir_barras via cum_prev),
   nao um contador por-barra — a primeira versao zerava a cada
   fechamento e o erro se acumulava silenciosamente.
3. execucao.py: bindings novos no ProfitClient para SendBuyOrder/
   SendSellOrder/SendZeroPosition + OrderChangeCallback/AccountCallback
   (o projeto nunca enviou ordem ate' agora, so' capturou dado).
4. Gestao de risco: stop por posicao, limite de perda diaria, o que fazer
   com ordem rejeitada. NAO DESENHADA AINDA -- nao e' detalhe para depois,
   e' bloqueador.
5. Forward-test em DEMO com dry_run=True primeiro (decisoes logadas, ordem
   NENHUMA enviada) -- comparar as decisoes logadas contra o que o research
   preveria, por dias suficientes, antes de sequer cogitar dry_run=False.
6. So' entao considerar mais sinais alem de z_agf_3/z_agf_4090 -- e so'
   apos passarem pelo MESMO funil (IC -> DSR -> quintis -> significancia).
