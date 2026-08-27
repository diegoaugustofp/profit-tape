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

## CORRIGIDO (2026-08-27) — a conclusao anterior estava ERRADA por interpretacao

**A secao abaixo ("Pergunta RESOLVIDA") concluiu errado.** Mantida
riscada para nao apagar o historico do raciocinio, mas NAO USAR.

O QUE MUDOU: teste de 2026-08-27 (00:10-00:11 local) rodou o MESMO
experimento, mas com o `ea-contas` conectando de VERDADE (nao mais
falhando de imediato como ontem) -- e revelou o padrao real:

  00:10:53 -- record (Terminal 1) ATIVO e saudavel (heartbeat normal).
             ea-contas (Terminal 2) tenta conectar -> FALHA imediata
             (-2147483647), IDENTICO ao padrao de ontem.
  00:11:04 -- operador da' Ctrl+C no record. Desconecta limpo.
  00:11:09 -- ea-contas roda de novo, AGORA com o record ja' desconectado
             -> CONECTA PERFEITAMENTE, lista a conta.

CONCLUSAO CORRIGIDA: as duas conexoes NAO coexistem -- mas de um jeito
especifico que a leitura de ontem confundiu. A conexao JA ESTABELECIDA
(record) nao e' derrubada; e' a SEGUNDA tentativa de conexao que FALHA
em se estabelecer enquanto a primeira estiver ativa. "O record nao foi
afetado" (verdade, confirmada de novo) NAO significa "as duas coexistem"
(falso) -- sao conclusoes diferentes, e o registro de ontem apresentou a
primeira como se fosse a segunda. Erro de interpretacao da evidencia,
nao de dado incorreto.

IMPLICACAO CRITICA PARA O FORWARD-TEST: o teste de ontem/hoje foi
MarketLogin (record) + LoginCompleto (ea-contas). O plano de amanha usa
MarketLogin (record) + MarketLogin (ea em dry_run, mesma funcao dos
dois lados, corrigido em service.py). NAO TESTADO ainda se duas conexoes
MarketLogin tambem colidem do mesmo jeito -- se a trava for "uma sessao
por chave de ativacao" (nao especifica de MarketLogin vs LoginCompleto),
o forward-test de amanha tambem falharia ao tentar conectar enquanto o
record (agendado via schtasks) ja estiver rodando.

TESTE PENDENTE, urgente antes de confiar no plano de amanha: dois
`record` simultaneos (MarketLogin + MarketLogin), mesma credencial,
pastas de dado diferentes -- ver se o SEGUNDO consegue conectar com o
PRIMEIRO ja ativo. Se falhar do mesmo jeito, o forward-test do EA
precisa rodar DENTRO do mesmo processo/conexao do record (consumindo os
trades que ele ja' esta capturando), nao como processo separado com
conexao propria -- mudanca de arquitetura real, nao cosmetica.

## Pergunta RESOLVIDA (2026-08-26) — teste de concorrencia real ~~[SUPERADO, ver acima]~~

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

## Zeragem automatica da XP — pesquisa e decisao de horario (2026-08-26)

Pergunta do operador: quando a corretora zera automaticamente posicoes de
day trade que ficam abertas demais? No simulador (dry_run) isso nunca
acontece; no real, importa muito -- custo de zeragem compulsoria e' alto.

FONTES (Manual de Risco XP + relato de atendimento oficial da XP no
Reclame Aqui):
  1. Garantia de day trade e' calculada ate' 15 min antes do fechamento do
     pregao regular no segmento BMF (onde WIN/WDO operam) -- ou 10 min
     antes quando ha' leilao.
  2. A zeragem automatica de RISCO ocorre em 3 situacoes: garantia
     consumida por resultado negativo, posicao de day trade levada ao
     leilao de fechamento, ou saldo negativo -- SEM aviso previo, a
     mercado.

Confirmado pelo operador (2026-08-26): pregao 9h-18h; em dia de
vencimento de serie, fecha 15 min mais cedo (~17:45).

DECISAO: --encerrar-em default do comando `ea` mudou de 18:20 para
**17:30** -- folga de seguranca generosa sobre o cenario mais apertado
(vencimento, ~17:45), nao apenas o dia normal (~17:45 tambem, calculando
do fechamento as 18:00). Nunca depender de precisao de minuto contra o
risco da corretora.

RESIDUAL NAO RESOLVIDO: o stop catastrofico (500 pts) e o circuit
breaker (3 perdas) protegem contra a causa "garantia consumida por
resultado negativo", mas em PONTOS DE PRECO, nao em GARANTIA DISPONIVEL
NA CONTA calculada pela XP -- num cenario de estresse extremo (spread
muito alargado), a zeragem da XP poderia teoricamente disparar ANTES do
nosso proprio stop. Sem solucao no v1; mitigado na pratica por operar
tamanho minimo (1 contrato) e capital dentro do minimo recomendado
(R$5.000) durante todo o forward-test.

## DLLInitializeLogin: NL_INTERNAL_ERROR persistente + correcao de design (2026-08-26)

**O erro decodificado**: -2147483647 e' literalmente `NL_INTERNAL_ERROR`
("Erro interno"), codigo generico do proprio manual (secao de codigos de
erro, junto de NL_NOT_INITIALIZED, NL_INVALID_ARGS, NL_WAITING_SERVER,
NL_NO_LOGIN). Nao e' um erro do Windows, e' do fornecedor -- e o manual
nao detalha QUANDO ele dispara para DLLInitializeLogin especificamente.

**Duas ocorrencias, horarios bem diferentes**: madrugada (03:32 UTC) e
noite (20:44 local, apos o fechamento do pregao). Mesmo codigo exato nos
dois casos. Isso ENFRAQUECE a hipotese anterior ("janela de
disponibilidade do servico de roteamento") -- horarios tao diferentes com
o MESMO erro sugerem causa estrutural, nao temporal.

**Hipotese de assinatura de callback DESCARTADA**: conferidas TAccountCallback
(4 parametros), TOrderChangeCallback (17 parametros) e THistoryCallback (16
parametros) EXATAMENTE contra o manual, tipo a tipo -- bindings.py bate
100%. Nao e' bug de ctypes.

**Causa provavel NAO CONFIRMADA**: permissao de roteamento/operacoes pode
nao estar habilitada para esta chave de ativacao na XP (algo contratual,
similar a adesao de RLP), ou instabilidade do backend de roteamento
independente de horario. So' o suporte XP/Nelogade confirma. PROXIMA ACAO:
abrir chamado com a XP citando NL_INTERNAL_ERROR em DLLInitializeLogin,
mencionando que DLLInitializeMarketLogin (mesma chave/usuario/senha)
funciona perfeitamente todo dia -- isola o problema para roteamento
especificamente.

**CORRECAO DE DESIGN (nao esperar a XP para seguir)**: service.py usava
DLLInitializeLogin SEMPRE, mesmo em dry_run=True -- desnecessario, ja' que
dry_run nunca envia ordem, so' precisa de dado de mercado. Corrigido:
dry_run=True usa DLLInitializeMarketLogin (o MESMO que o record usa todo
dia, comprovadamente confiavel); DLLInitializeLogin so' e' usado quando
dry_run=False (que ja' exige ExecutorDeOrdens explicito de qualquer
forma). O forward-test de amanha NAO fica bloqueado por este problema.

O bloqueio genuino que PERMANECE: qualquer coisa que precise de
roteamento (ea-contas, e eventualmente dry_run=False) continua
inutilizavel ate' a causa ser identificada e corrigida — via suporte XP.

## Investigacao adicional: por que o client.py (record) nao teve este problema? (2026-08-26)

Pergunta direta do operador: o record usa a classe ProfitClient para
conectar, o EA nao -- essa diferenca explica o NL_INTERNAL_ERROR?

INVESTIGACAO: ProfitClient.connect() (profitdll/client.py) NUNCA chama
DLLInitializeLogin -- so' DLLInitializeMarketLogin, sempre. Ou seja, NAO
EXISTE, em nenhum lugar deste projeto, um precedente de DLLInitializeLogin
ja' ter funcionado -- contas.py foi a PRIMEIRA vez que este caminho foi
exercitado. Nao e' "funciona no record e quebra no EA"; e' "nunca
testamos isso antes de ontem".

Conferido o connect() inteiro: depois do DLLInitializeMarketLogin, so' ha'
logica especifica de offer book V2 (irrelevante para roteamento). NENHUM
passo escondido de pre-requisito para DLLInitializeLogin foi encontrado
no client.py -- porque ele nunca toca essa funcao.

GAP REAL encontrado (nao a causa confirmada, mas defesa que faltava):
client.py roda check_exports() ANTES de conectar (confere que a DLL expoe
as funcoes esperadas, falha com mensagem clara se nao). contas.py pulava
essa checagem inteiramente. Corrigido: check_exports_ea_contas() (nova
funcao em bindings.py, escopo separado de check_exports -- record nao
deve exigir funcoes de roteamento que uma DLL so-market-data legitimamente
nao tem) roda logo antes de GetAccount() ser chamado.

LIMITE HONESTO desta correcao: NL_INTERNAL_ERROR e' um codigo de retorno
de uma funcao que EXISTE e RODA -- nao um AttributeError de funcao
ausente. A checagem de exports nao teria pego nem teria corrigido este
erro especifico; e' defesa contra uma causa DIFERENTE (versao de DLL
divergente) que tambem nao tinha sido descartada ate agora. Depois desta
correcao, se o erro persistir, a causa NAO e' export ausente -- reforca
ainda mais a hipotese de algo do lado da XP (permissao de roteamento).

199 testes (5 novos: check_exports_ea_contas + regressao dedicada).

## ACHADO CRITICO: dois bugs reais na deteccao de estado (2026-08-26, 23:46)

Nova execucao de `ea-contas` produziu uma sequencia RICA de estados (a
sessao conectou de verdade desta vez) que, decodificada pela tabela do
manual (secao TStateCallback), revelou:

```
tipo=3 valor=0   ATIVACAO_VALIDA
tipo=0 valor=0   LOGIN_CONNECTED
tipo=1 valor=1   ROTEAMENTO_CONNECTING
tipo=1 valor=2   ROTEAMENTO_CONNECTED
tipo=2 valor=1   MARKET_CONNECTING
tipo=2 valor=2   MARKET_WAITING
tipo=1 valor=4   ROTEAMENTO_BROKER_CONNECTING
tipo=1 valor=5   ROTEAMENTO_BROKER_CONNECTED  (x4)
tipo=0 valor=0   LOGIN_CONNECTED (repetido)
tipo=2 valor=4   MARKET_CONNECTED
--- ~2.5s depois, tudo cai sozinho: ---
tipo=0 valor=1   LOGIN_INVALID
tipo=1 valor=0   ROTEAMENTO_DISCONNECTED
tipo=2 valor=0   MARKET_DISCONNECTED
tipo=3 valor=1   ATIVACAO_INVALIDA
```

**A sessao conectou TOTALMENTE (login, roteamento, corretora x4, market
data) e ~2.5s depois foi derrubada por inteiro, terminando em
ATIVACAO_INVALIDA.** Isto e' NOVO e MELHOR informacao que o
NL_INTERNAL_ERROR generico de antes -- aponta fortemente para o servidor
aceitar a conexao inicialmente e depois REVOGAR por alguma checagem de
permissao/entitlement que so' completa alguns segundos depois (hipotese:
a chave de ativacao pode nao ter roteamento/operacoes habilitado, e o
backend valida isso de forma assincrona, tarde).

**DOIS BUGS REAIS encontrados e corrigidos no nosso codigo ao investigar
isto** (nao explicam a causa raiz do lado da XP, mas eram bugs de
verdade):

1. **contas.py chamava GetAccount() cedo demais.** So' esperava
   tipo=LOGIN valor=0 (o PRIMEIRO dos 4 sinais de conexao) -- nao
   tipo=ROTEAMENTO valor=BROKER_CONNECTED(5), que e' o que de fato indica
   que a corretora/conta esta pronta. client.py (record) ja' fazia isso
   certo para market data (checa tipo==MARKET_DATA, nao tipo==LOGIN) --
   contas.py nao seguiu o mesmo padrao. Corrigido: agora espera
   BROKER_CONNECTED antes de chamar GetAccount().

2. **Deteccao de erro de estado NUNCA disparava, em lugar nenhum do
   projeto** (contas.py E service.py): o codigo checava "valor < 0" como
   sinal de erro -- mas TODOS os codigos de erro documentados no manual
   (LOGIN_INVALID=1, ROTEAMENTO_DISCONNECTED=0, ATIVACAO_INVALIDA=1, etc.)
   sao NAO-NEGATIVOS. Essa checagem estava morta desde sempre. Corrigido:
   decodificacao propria por tipo, usando os enums novos (LoginResult,
   RoteamentoResult, MarketDataResult, AtivacaoResult em domain/enums.py),
   com ATIVACAO_INVALIDA tratada como erro real e decodificado (nao mais
   silenciosa).

**PROXIMA ACAO CONCRETA**: com a correcao aplicada, rode `ea-contas` de
novo. Se a mensagem agora for "ATIVACAO INVALIDADA" de forma clara (em
vez de "Nenhuma conta retornada" generico), confirma exatamente esta
hipotese -- e da' a informacao EXATA para o chamado com a XP: "a sessao
conecta totalmente (login, roteamento, corretora, market data) e e'
invalidada ~2-3s depois com CONNECTION_ACTIVATE_INVALID -- a chave de
ativacao tem permissao de roteamento/operacoes habilitada para esta
conta?"

200 testes (6 novos/atualizados em test_ea_contas.py, incluindo replay
exato desta sequencia real).

## Nota do operador: corretora_id=32006 e' provavelmente codigo Nelogica do simulador, nao da XP (2026-08-26)

Observacao importante para quando a conta real for habilitada: o
corretora_id=32006 retornado por GetAccount() na conta demo/simulador
provavelmente e' um codigo INTERNO da Nelogica para o ambiente de
simulacao, nao o codigo real da XP como corretora. E' plausivel que a
conta REAL, quando habilitada, venha com um corretora_id DIFERENTE.

Nao exige mudanca de codigo agora -- RoteamentoConfig.id_corretora ja'
e' um campo configuravel no .env, nunca hardcoded em lugar nenhum do
codigo (conferido). So' um lembrete operacional: quando a XP habilitar
a conta real para esta chave, RODAR `ea-contas` DE NOVO -- nao assumir
que o mesmo corretora_id=32006 vale para a conta real tambem.
