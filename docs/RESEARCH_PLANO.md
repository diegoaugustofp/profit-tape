# Plano do modulo research/ (decidido 2026-08-22, pre-implementacao)

Registro das decisoes de desenho ANTES de escrever codigo, para o research
nascer com metodo travado e nao com parametros escolhidos depois de ver
resultado (isso seria p-hacking — o proprio projeto ja rejeitou esse padrao).

## Decisoes aprovadas

1. ALVO: IC de Spearman de cada feature Tier 1 contra ret_h em barras de
   volume, horizontes h in {1, 3, 10} barras. Multi-horizonte para ver decay
   do sinal, nao um ponto isolado.

2. PURGING: gap entre treino e teste = holding maximo do triple-barrier;
   embargo de +1 barra. Minimo para nao vazar rotulo sobreposto (Lopez de
   Prado).

3. VALIDACAO: WALK-FORWARD, nao CPCV. Decisao explicita do operador
   (2026-08-22). Justificativa: com ~19 pregoes, CPCV (N=6, k=2 -> 15 combos)
   daria falsa sensacao de robustez que a amostra nao sustenta. Walk-forward
   e' honesto sobre o que 19 dias podem dizer. MIGRAR para CPCV quando o
   record diario acumular ~40+ pregoes.

4. DSR: cada feature x horizonte conta como trial. Contador PERSISTIDO em
   disco (nao mental), somando entre rodadas — o Deflated Sharpe precisa do
   numero real de tentativas historicas para nao mentir depois de meses.

5. SAIDA: relatorio markdown versionado por rodada — dado usado, parametros,
   trials acumulados, veredito por feature (segue / descarta / inconclusivo).

## Persistencia de corretora — desenho refinado (ideia do operador, 2026-08-22)

MUDANCA DE ENQUADRAMENTO: em vez de testar "o fluxo do agente N (numero cego)
preve retorno?", testar a hipotese ECONOMICA "fluxo de VAREJO preve retorno de
forma diferente de fluxo INSTITUCIONAL?". Isto e' a hipotese classica de
microestrutura smart money vs dumb money, e tem significado — nao e' garimpo
sobre codigos arbitrarios.

Intuicao a testar (nao a assumir):
  - Fluxo INSTITUCIONAL (ex.: Morgan Stanley, BTG institucional) tende a ser
    informado -> possivel CONTINUACAO de retorno.
  - Fluxo de VAREJO (ex.: XP, Clear, Rico, Modal) tende a ser ruidoso/contrario
    -> possivel REVERSAO.

Implementacao proposta:
  a. Tabela de classificacao agent_id -> perfil {VAREJO, INSTITUCIONAL, MISTO,
     DESCONHECIDO}. Construida a partir de data/ref/agentes.csv (nomes reais
     via GetAgentNameById) + curadoria manual do operador (ele conhece o
     mercado B3). Fica versionada em data/ref/perfil_corretora.csv.
  b. Features agregadas por perfil, nao so' por agente:
       - fluxo_liquido_varejo    = compra_varejo - venda_varejo  (por barra)
       - fluxo_liquido_inst      = compra_inst   - venda_inst
       - divergencia_perfil      = sinal(fluxo_inst) vs sinal(fluxo_varejo)
         (barras onde institucional e varejo estao em lados OPOSTOS — o setup
          classico: seguir o institucional contra o varejo)
  c. Testar IC dessas features de perfil contra ret_h, com o MESMO rigor
     (walk-forward, purging, DSR contando cada uma como trial).
  d. Teste de persistencia por perfil: autocorrelacao diaria do fluxo_liquido
     de cada perfil + IC defasado (o fluxo institucional de hoje preve o
     retorno de amanha melhor que o de varejo?).

CUIDADOS METODOLOGICOS registrados:
  - A classificacao VAREJO/INST e' uma HIPOTESE do operador, nao verdade
    revelada. Uma corretora pode ter mesa institucional E corretora de varejo
    sob o mesmo codigo (por isso o rotulo MISTO existe). Rotular errado
    enfraquece o teste — melhor MISTO/DESCONHECIDO honesto que forcar binario.
  - Classificar DEPOIS de ver qual classificacao da' IC melhor seria p-hacking.
    A tabela perfil_corretora.csv deve ser congelada ANTES de rodar o IC, com
    base em conhecimento de mercado, nao em resultado.
  - Cada variante de classificacao testada (ex.: "e se XP fosse MISTO?") conta
    como trial adicional no DSR. Nao ha almoco gratis em reclassificar ate'
    o sinal aparecer.
  - Volume real e' ~metade do bruto (reentregas idempotentes deduplicadas no
    curate, confirmado 2026-08-22). Features de fluxo devem rodar sobre o
    CURATED, nunca sobre o raw, senao o volume por perfil vem inflado 2x.

## Pre-requisitos antes de escrever research/
  - [x] 19 pregoes capturados com footer duravel (recaptura em andamento)
  - [ ] curate rodado -> dataset deduplicado
  - [ ] agents rodado -> agentes.csv com nomes reais
  - [ ] operador preenche perfil_corretora.csv (curadoria manual)
  - [ ] features rodado sobre curated

## REVISAO DA HIPOTESE DE PERFIL (2026-08-22, operador)

O operador puxou os SHORT NAMES (GetAgentShortNameById, mais util que o nome
juridico) dos agentes de maior volume:
    3    -> XP
    85   -> BTG
    1618 -> Ideal
    120  -> Genial
    8    -> UBS
    39   -> Agora

INSIGHT METODOLOGICO: o operador REJEITOU a classificacao varejo/institucional
simples ao ver os nomes — XP, BTG, Ideal, Genial atendem varejo E tem mesa
institucional/estrangeira sob o MESMO codigo de agente. Rotular XP como
"varejo" seria forcar os dados numa hipotese conveniente. Recuar disso e' a
decisao certa.

NOVA HIPOTESE (mais forte): NACIONAL vs ESTRANGEIRO, nao varejo/institucional.
Motivacao ancorada em evento REAL e datado: agosto/2026 registrou grande
saida de capital estrangeiro da B3. Se esse foi o fluxo dominante na janela de
dados, entao nacional/estrangeiro nao e' classificacao arbitraria — e' a
variavel que de fato movia o mercado nesses pregoes.

VANTAGENS desta hipotese sobre a anterior:
  1. Ancorada em evento macro real (saida de estrangeiro em agosto), nao
     numa taxonomia generica — menos sujeita a ser artefato estatistico.
  2. VERIFICAVEL contra dado externo independente: B3/CVM publicam saldo
     diario de investidor estrangeiro, e o Trade Hunter MCP (flow-foreign)
     traz fluxo estrangeiro/institucional/varejo consolidado. Isso permite
     VALIDAR a classificacao de corretora ANTES de testar previsao:
       - classificar corretoras por perfil nacional/estrangeiro
       - agregar fluxo liquido por perfil no dado tick-a-tick
       - checar se correlaciona com o saldo estrangeiro OFICIAL da B3 nos
         mesmos dias
       - se correlaciona -> classificacao validada; se nao -> esta errada,
         descoberto SEM gastar trial de p-hacking em previsao de retorno
  3. Alinha com a stack do operador (Trade Hunter flow-foreign ja' mapeado).

RISCO desta hipotese, registrado honestamente:
  - Classificar uma corretora como "estrangeira" ou "nacional" e' aproximado:
    a corretora e' o CANAL, nao o investidor final. XP pode rotear tanto
    pessoa fisica brasileira quanto fundo estrangeiro. O codigo de agente
    identifica a corretora, nao a origem do capital. Entao "fluxo via
    corretoras com forte presenca estrangeira" e' uma PROXY, nao a verdade.
    A validacao contra o saldo oficial da B3 (item 2 acima) e' o que mede
    quao boa e' essa proxy — se for ruim, a hipotese cai por dado, nao por
    opiniao.

ACAO: operador vai pesquisar a melhor forma de classificar (o proprio
reconheceu que precisa investigar mais). perfil_corretora.csv permanece
CONGELADO antes do IC, seja qual for o eixo escolhido. GetAgentShortNameById
agora exposto (client.agent_name(id, curto=True)); comando `agents` grava
short_name + nome + coluna 'perfil' vazia para curadoria manual.

## Revisao critica da taxonomia de 6 niveis (2026-08-22, operador pesquisou)

Operador trouxe uma taxonomia de 6 categorias de corretoras B3 (varejo puro,
banco tradicional integrado, banco digital, institucional/atacado, private/
alta renda, especializada em trading/HFT).

TENSAO IDENTIFICADA: essa taxonomia classifica por FAIXA DE PATRIMONIO/PERFIL
DE CLIENTE, nao por NACIONAL/ESTRANGEIRO (a hipotese da secao anterior). Sao
eixos diferentes. Aplicando aos agentes reais de maior volume:

  3    XP     -> cat.1 varejo puro         (encaixe limpo, alta confianca)
  39   Agora  -> cat.2 banco varejo        (encaixe limpo, alta confianca)
  85   BTG    -> cat.5 private             (BAIXA confianca — BTG e' dono da
                                             Warren, tem mesa institucional
                                             E app de varejo digital; e'
                                             provavelmente o mais MISTO da
                                             lista, nao o mais "private")
  120  Genial -> cat.5 private             (media confianca — tambem tem
                                             plataforma de varejo digital)
  8    UBS    -> AUSENTE da taxonomia dada; por analogia a Goldman/Morgan
                 Stanley seria cat.4 (institucional estrangeiro) — decisao
                 do operador, nao inferida aqui
  1618 Ideal  -> cat.6 trading/HFT         (a mais reveladora, ver abaixo)

INSIGHT: Ideal (agente 1618, alto volume) e' descrita na propria pesquisa do
operador como "infraestrutura eletronica avancada, algoritmos, execucao
automatizada" — isso NAO e' um perfil de investidor (rico/pobre, nacional/
estrangeiro). E' um perfil de ESTILO DE EXECUCAO: fluxo algoritmico/HFT,
provavelmente market-making ou arbitragem. Comportamento esperado
qualitativamente diferente de fluxo direcional humano: algo/HFT tende a
REVERSAO (provisao de liquidez, gestao de inventario) enquanto fluxo
direcional informado tende a CONTINUACAO.

TERCEIRO EIXO CANDIDATO (emergiu da pesquisa, nao buscado deliberadamente):
  3. DISCRICIONARIO vs ALGORITMICO/HFT — teoricamente pode ser o eixo MAIS
     relevante para order flow em WIN futures especificamente, dado o
     background do operador em trading sistematico.

TRES EIXOS CANDIDATOS agora, nao um:
  1. Varejo vs institucional        — REJEITADO pelo operador (mistura
                                       demais nos codigos reais de maior
                                       volume: XP/BTG/Ideal/Genial atendem
                                       ambos sob o mesmo agent_id)
  2. Nacional vs estrangeiro         — motivado pelo evento real de saida de
                                       estrangeiro em ago/2026; UNICO eixo
                                       verificavel contra dado externo
                                       (saldo B3/CVM, Trade Hunter
                                       flow-foreign) ANTES de gastar trial
                                       em previsao de retorno
  3. Discricionario vs algoritmico   — emergiu do caso Ideal; sem validacao
                                       externa facil, mas apelo teorico
                                       forte para order flow especificamente

DECISAO PENDENTE (operador): qual eixo roda PRIMEIRO na rodada 1 do research.
Recomendacao registrada: eixo 2 primeiro (tem o crivo de validacao externa
que os outros nao tem — filtra hipotese ruim ANTES do IC custar trial). Eixo
3 como candidato natural para rodada 2, nao descartado. Eixo 1 fica
arquivado — o proprio operador o invalidou ao ver os agent_id reais.

Cada eixo testado formalmente = trials adicionais no DSR (nao e' "so' mais
uma classificacao para ver de graca" — mistura de eixos data-snooping se
todos forem testados na mesma rodada sem contabilizar).

## Classificacao final de 2 camadas (2026-08-22, operador)

Estrutura decidida: `perfil_corretora.csv` ganha DUAS colunas derivadas de
UMA classificacao de base, para nao forcar tudo num eixo so'.

  COLUNA 1 (grupo, 5 categorias, granular):
    HFT | ESTRANGEIROS | INSTITUCIONAIS | VAREJO | OUTROS

  COLUNA 2 (eixo_nac_estr, BINARIO, DERIVADO da coluna 1 por regra fixa):
    VAREJO          -> NACIONAL
    ESTRANGEIROS    -> ESTRANGEIRO
    INSTITUCIONAIS  -> ver PROCEDIMENTO DE DUAS ETAPAS abaixo (nao e' auto)
    HFT             -> EXCLUIDO do eixo binario (nem nacional nem estrangeiro;
                        participa SO' do eixo discricionario-vs-algoritmico,
                        que e' o dele — nao forcar Ideal numa direcao que
                        ninguem consegue justificar)
    OUTROS          -> EXCLUIDO (baixa confianca, nao entra em nenhum eixo
                        ate' virar um dos quatro acima)

PROCEDIMENTO DE DUAS ETAPAS para o grupo INSTITUCIONAIS no eixo binario
(travado ANTES de qualquer correlacao ser calculada — a fuga de um erro
metodologico real: "considerar Institucionais como proxy parcial" so' e'
valido se o peso for decidido por evidencia, nao ajustado para bater com o
gabarito oficial):

  ETAPA 1 — proxy ESTREITO: Estrangeiro = so' grupo ESTRANGEIROS (nomes
    inequivocamente estrangeiros: Goldman, Morgan Stanley, JP Morgan, UBS).
    Calcula fluxo liquido diario desse grupo, correlaciona contra o saldo
    OFICIAL de estrangeiro da B3/CVM (via Trade Hunter flow-foreign) nos
    mesmos pregoes. Registra o coeficiente ANTES de ir para a etapa 2.

  ETAPA 2 — teste INDEPENDENTE do grupo INSTITUCIONAIS: calcula fluxo
    liquido diario do grupo INSTITUCIONAIS SEPARADAMENTE (nao somado ao
    proxy), e correlaciona ele TAMBEM contra o mesmo saldo oficial B3/CVM.
      - SE correlacionar significativamente -> evidencia EMPIRICA (nao
        intuicao) de que essas mesas carregam fluxo estrangeiro relevante;
        amplia-se o proxy (Estrangeiro = ESTRANGEIROS + INSTITUCIONAIS) e
        registra-se o motivo com o coeficiente que justificou.
      - SE NAO correlacionar -> Institucionais fica DE FORA do eixo binario
        (mas continua existindo na coluna 1, disponivel para outras
        perguntas). Nao se ajusta peso fracionario para forcar correlacao —
        e' binario incluir/excluir, decidido pelo proprio dado.

    Isto e' EXPLORATORIO (2 correlacoes contra serie externa, nao contra
    retorno) — nao conta como trial de previsao no DSR (DSR conta trials de
    IC-vs-retorno, nao de validacao de classificacao contra serie oficial).
    Mas fica registrado e versionado como parte do metodo, nao descartado
    como "so' um teste rapido".

CHECAGEM EMPIRICA ANTES DE CONSTRUIR O PIPELINE INTEIRO: computar % do
volume total por grupo (coluna 1) assim que o CSV for preenchido. Risco
identificado: o grupo ESTRANGEIROS estreito (so' nomes inequivocos) pode ser
uma fatia pequena do volume observado nos agentes de maior volume do WINFUT
(o top 5 hoje e' XP/BTG/Ideal/Genial/UBS-ou-Agora — so' UBS cai limpo em
ESTRANGEIROS). Se a fatia for muito pequena (ex. <2% do volume), 19 pregoes
podem nao ter poder estatistico para detectar correlacao alguma contra o
saldo B3/CVM, e vale saber isso ANTES de montar o pipeline completo, nao
depois de rodar tudo e nao achar nada.

## IMPLEMENTADO (2026-08-22) — regras finais do veredito, pos teste de honestidade

O modulo research/ foi implementado com teste de honestidade obrigatorio:
feature preditiva POR CONSTRUCAO deve sair 'segue', ruido puro deve sair
'descarta'. O teste pegou DOIS furos antes de qualquer dado real:

1. E[max Z] para N pequeno fica ABAIXO de 1.96 (N=2 -> 0.56) — usar a formula
   pura DILUIA o criterio. Corrigido: barra = max(1.96, E[max Z]).
2. t-stat de 5 folds tem cauda de Student (4 g.l.), nao de Z — e um azar de
   seed produziu ruido com IC -0.05 consistente em TODOS os folds, passando
   por t+consistencia. Corrigido com a barra de MAGNITUDE.

REGRAS FINAIS (tres barras cumulativas para 'segue'):
  1. MAGNITUDE   |IC medio| >= 2/sqrt(n_obs de teste)
  2. ESTABILIDADE |t entre folds| >= t-critico(limiar deflacionado, k-1 g.l.)
  3. DIRECAO     mesmo sinal em >= 70% dos folds
  + inconclusivo se folds < 4; trials acumulados em data/research/trials.json.

Comando: profit-tape research --features data/features --symbol WINFUT

## PRIMEIRA RODADA REAL + IDENTIFICACAO DO CLUSTER (2026-08-23)

42 trials, limiar 2.209. Dois 'segue', ambos IC NEGATIVO (contrarian):
z_agf_3 (XP) h=3 e z_agf_4090 h=1. Identificacao do operador: 4090 =
Santander/Toro, canal SO-VAREJO (o 27 e' o codigo misto com tesouraria);
92 = Warren (varejo); 114 = Itau-varejo; 88 = CM Capital (nao conhecido,
vazio honesto).

LEITURA: o cluster de IC negativo e' quase todo canal de varejo nacional
(XP, Toro, Warren, Itau, BTG); o de IC positivo (fraco, nenhum passou) e'
DMA/institucional (Ideal, Agora, Genial, UBS). Os dois 'segue' sao os dois
canais mais PUROS de varejo — onde a hipotese previa. Serie oficial da B3
(data/ref/fluxo_participantes_b3_oficial.csv) confirma por fonte
independente: PF comprou durante o exodo estrangeiro de agosto (todos os
pregoes negativos de 04/08 a 19/08, pico -4.7bi em 11/08).

RESSALVA DE REGIME (registrada): a janela contem uma quebra (jul entrada ->
ago exodo). Nao da' para distinguir 'varejo e' contrarian sempre' de
'comprar contra exodo foi contrarian em agosto'. RETESTE OBRIGATORIO quando
o record diario acumular semanas de regime diferente. O z_agf_3 h=1 falhou
SO na barra de magnitude (0.0414 < 0.0487) — a regra fica como esta;
afrouxar depois de ver resultado seria p-hacking.

PROXIMO: comando `perfil-validar` implementado — correlaciona fluxo diario
por perfil (tick nosso) com a serie oficial ANTES do IC de perfil.
Ressalva: oficial = a vista, nosso = WIN; proxy x proxy, >=0.4 valida
direcao. Depois: quintis em pontos vs custo para os dois 'segue'.

## CONCLUSAO DA VALIDACAO DE PERFIL (2026-08-23, aceita pelo operador)

Resultado de `perfil-validar` sobre os 21 pregoes de WIN, classificacao real
(8 codigos ESTRANGEIRO: UBS, Merrill, JP Morgan, Necton, Morgan Stanley,
Citigroup, Goldman, Stonex):

  NACIONAL     pearson=0.524  concordancia=0.684  VALIDA
  ESTRANGEIRO  pearson=0.212  concordancia=0.737  NAO_VALIDA

Causa identificada (nao e' erro de rotulo): dos 8 codigos ESTRANGEIRO, so' o
UBS(8) aparece no top-10 de volume do WIN — os outros sete (Merrill, JP
Morgan, Necton, Morgan Stanley, Citigroup, Goldman, Stonex) tem volume baixo
demais para carregar sinal. O Pearson de 0.212 e' quase todo UBS diluido por
ruido de baixo volume.

CONCLUSAO ACEITA: no WIN, capital estrangeiro nao e' capturavel via
classificacao de corretora com os dados de agente disponiveis — a corretora
identifica quem EXECUTA, nao quem e' o beneficiario final, e essa distancia
parece maior no futuro de indice que no a vista (onde a serie oficial da B3
mede o saldo por exigencia de identificacao na liquidacao). Isto e' um
resultado de pesquisa legitimo, obtido SEM gastar trial de IC — a validacao
pre-registrada funcionou exatamente como desenhada.

DECISAO: NACIONAL segue para o IC (validado). ESTRANGEIRO fica de fora nesta
forma — na pratica, o teste de perfil vira NACIONAL vs RESTO, preservando a
motivacao original (varejo nacional comprando contra o exodo).

HIPOTESE FUTURA (operador, especulativa, registrada para nao se perder):
capital estrangeiro pode ser mais capturavel via classificacao de corretora
no mercado A VISTA (acoes) que no WIN — a serie oficial mede exatamente esse
mercado, entao a granularidade de identificacao deveria ser maior ali.
Testavel quando houver volume suficiente de PETR4/VALE3/ITUB4 no curated
(mesmo comando perfil-validar, symbol=PETR4 etc.) — SEM custar trial, e' a
mesma validacao pre-IC, so' aplicada a outro simbolo. Nao e' acao imediata;
registrado para quando o record diario acumular dado de acoes suficiente.

## fluxo_nacional implementado (2026-08-23)

Feature agregada de perfil, unica que passou na validacao (NACIONAL,
pearson=0.524). flow.calcular ganhou parametro opcional agentes_nacionais:
mesma formula do agf_id ((comprado-vendido)/vol_agr), mas somando TODOS os
agentes classificados NACIONAL — inclui agentes pequenos que nao entrariam
no top-N individual. pipeline.gerar carrega data/ref/agentes.csv por padrao
(--perfis para apontar outro, ou vazio para omitir; roda igual sem o CSV).
z_fluxo_nacional entra automaticamente no research (qualquer coluna z_*).
ESTRANGEIRO deliberadamente NAO implementado (nao validou). 101 testes.

## Teste de diferenca entre quintis adjacentes (2026-08-23)

quintis.md dos dois 'segue' (custo 11pts) mostrou NAO-MONOTONICIDADE:
Q4 mais negativo que Q5 em AMBOS z_agf_3 e z_agf_4090 (Q3 ate positivo em
z_agf_4090). Implementado teste de Welch (diagnostico, NAO consome trial —
compara quintil contra quintil da MESMA feature ja avaliada, nao testa
feature nova contra retorno) entre cada par de quintis adjacentes.

Uso: `profit-tape quintis "feat:h" --custo-pontos N` agora imprime e grava
Q1v2, Q2v3, Q3v4, Q4v5 com t de Welch, p-valor bicaudal (normal, gl grande) e
veredito DIFEREM/indistinguivel a 5%. Decide se a nao-monotonicidade
observada e' estrutura real (operar no Q4, nao esperar o Q5) ou ruido de
amostra pequena (~330 obs/quintil, 18 dias) que nao deve guiar a entrada do
EA.

## Resultado do teste de diferenca entre quintis (2026-08-23)

Rodado sobre os dois 'segue' com custo real informado (11 pts round-trip
automatizado, R$2,19/contrato a R$0,20/pt):

CONCLUSAO: a nao-monotonicidade Q4-pior-que-Q5 observada no relatorio
anterior e' RUIDO, nao estrutura. Q4 vs Q5 saiu 'indistinguivel' nos dois
sinais (z_agf_3 p=0.738; z_agf_4090 p=0.756) — com ~330-340 obs/quintil, a
diferenca entre extremo (Q5) e quase-extremo (Q4) esta dentro do que acaso
produz. NAO desenhar a entrada do EA em torno do Q4 esperando capturar algo
que o Q5 nao capturaria; a regra simples 'sinal no extremo -> opera' segue
sendo a escolha defensavel.

UNICA estrutura interna real encontrada: z_agf_4090 (Toro/Santander-varejo)
tem transicao Q3->Q4 estatisticamente significativa (t=-3.13, p=0.002) — Q3
(sinal neutro, ~0) tem retorno liquido POSITIVO (+4.18pts), Q4 (sinal
moderado, ~0.5) ja e' claramente negativo (-34.96pts). Sugere um "gatilho":
o edge liga de forma abrupta ao sair da zona neutra, nao escala
proporcionalmente ao valor do sinal. Pode informar uma regra de entrada por
THRESHOLD (operar quando |sinal| > lim proximo do limite Q3/Q4) em vez de
proporcional — mas e' desenho de EA, etapa futura; 341 obs/perna ainda e'
cedo para fixar o threshold exato. z_agf_3 (XP) nao mostrou nenhuma
transicao interna distinguivel — tratar como aproximadamente monotonico
dentro do erro, sem otimizar ponto de entrada alem de "extremo".

Resultado NEGATIVO da hipotese motivadora (Q4>Q5) e' o metodo funcionando:
evitou levar um padrao que pareceria insight na tabela bruta para o desenho
do EA sem base estatistica.

## Segunda rodada de quintis — z_agf_3 h=1 passa no IC mas morre pelo custo (2026-08-26)

Com 23 dias (2 a mais), z_agf_3 passou a "segue" tambem em h=1 (antes so'
h=3/h=10), com t=-3.95 e consistencia=1.00 (10/10 folds na mesma direcao).
Tabela de quintis (custo real 11pts) revelou hierarquia clara entre os
quatro pares testados:

  z_agf_3   h=10 : spread liquido +52.55 pts -- MAIS ROBUSTO, ~5x o custo
  z_agf_3   h=3  : spread liquido +18.14 pts -- solido, Q3->Q4 significativo (p=0.043)
  z_agf_4090 h=1 : spread liquido +0.20 pts  -- vivo mas SEM MARGEM nenhuma
  z_agf_3   h=1  : spread bruto so +10.15 pts -- MORTO, nem chega no custo de 1 perna

CONCLUSAO: z_agf_3 h=1 passa no IC (estatistica) mas morre no teste
economico (quintis) -- exemplo pratico de por que os dois testes sao
necessarios e nenhum substitui o outro. NAO entra em nenhuma implementacao
de EA apesar do "segue" no relatorio de IC.

LEITURA SOBRE O SINAL: z_agf_3 parece ficar mais forte com o horizonte —
plausivel que a reversao contra o fluxo de varejo (XP) nao se manifeste
de imediato, precisando de mais tempo para o mercado corrigir o excesso.
h=1 e' o mais marginal dos tres, e foi o ultimo a cruzar o limiar
deflacionado (que so' subiu com mais trials acumulados).

DECISAO: qualquer EA futuro baseado em z_agf_3 deve usar h=3 ou h=10,
nunca h=1 -- apesar do "segue" na tabela de IC.

## Custo de transacao em ACOES na XP — ponderacao do operador (2026-08-26)

Antes de rodar quintis sobre os sinais novos de acao (MGLU3, ITUB4),
registrado um ponto real de custo que precisa ser resolvido primeiro:

Tabela de custo XP fornecida pelo operador (Bruto fixo R$97,37 em todos):
  Day trade + RLP                              : custo R$22,34  (23% do bruto)
  Swing 1 dia, autoatendimento                  : custo R$72,18  (74% do bruto)
  Swing 5 dias c/ financiamento (BTC 20% a.a.)  : custo R$108,88 (LIQUIDO NEGATIVO)
  Swing 1 dia via escritorio credenciado        : custo R$136,88 (LIQUIDO NEGATIVO)

CONCLUSAO PARCIAL: manter posicao overnight em acao e' inviavel para o
tipo de IC fino que estamos encontrando (0.05-0.09) -- custo de
carregamento (BTC + custodia) cresce mais rapido que o sinal sustenta.

MAS os sinais achados (MGLU3 z_fluxo_nacional h=1, ITUB4 z_tick_imbalance
h=10) sao em HORIZONTE DE BARRA, no ~100-120 barras/dia -- h=10 e' uma
fracao pequena de UM pregao. Se o EA sempre zera antes do fechamento
(mesma disciplina do encerrar_em do record), esses sinais sao day trade
por natureza, nao swing.

PERGUNTA EM ABERTO, decide se os sinais de acao sao viaveis ou nao: a
XP exclui RLP para "estrategias automatizadas" tambem em ACOES, como ja'
documentado que faz em FUTUROS (WIN paga R$1,00/contrato/ordem
automatizado vs <R$1 manual)? Se sim, o custo real de um EA em acoes fica
perto dos 74% (autoatendimento), nao dos 23% (day trade+RLP) -- e' o
mesmo padrao do WIN se repetindo. NAO CONFIRMADO — precisa checar com a
XP ou documentacao de conta antes de assumir qualquer custo para o
--custo-pontos do quintis em acoes.

RESPOSTA PARCIAL DO OPERADOR (2026-08-26): ele ADERIU ao RLP na conta,
tanto para acoes quanto para indice — mas isso e' preferencia de
ROTEAMENTO DA CONTA (vale para ordem manual). A pergunta que continua
sem resposta e' mais especifica: ordem marcada como vinda de sistema
AUTOMATIZADO (API/DLL) e' excluida do RLP pela XP independente da
adesao da conta — exatamente como ja documentado acontecer no WIN? So'
a XP/assessor confirma isso, nao e' algo que a adesao geral ao RLP
resolve sozinha.

Dimensionamento de posicao (operador, 2026-08-26): capital R$20.000 para
acoes, risco maximo 1% por operacao = R$200. Lote calculado por
risco/distancia-do-stop, que ainda nao foi definida (design de EA,
propositalmente adiado). Custo em pontos por acao depende do lote —
caminho mais simples sem entrar em estrategia: pedir ao operador para
rodar o MESMO simulador de custo da XP com um lote realista de MGLU3/
ITUB4 no cenario "Day trade + RLP", e converter o R$ resultante para
pontos dividindo pelo numero de acoes.

## Conclusao final: sinais de acao morrem no teste economico (2026-08-26)

Com o custo real da XP (0.026 pts/acao, RLP+day-trade, lote 500,
confirmado que RLP vale igual p/ automatizado em acoes — diferente do
WIN onde automatizado sempre paga taxa fixa extra):

  z_fluxo_nacional h=1 (MGLU3): spread bruto +0.003 pts -- irrelevante
    frente a qualquer custo. %>0 liquido = 2.7%-4.6% em TODOS os
    quintis -- perderia dinheiro em ~95-97% das barras, mesmo SEM
    custo algum. Achado metodologico: t altissimo no IC (-6.45) mediu
    CONSISTENCIA DE DIRECAO entre folds, nao magnitude nem taxa de
    acerto -- os dois sao coisas diferentes, e este e' o exemplo mais
    claro ate agora de direcao consistente com magnitude nula.

  z_tick_imbalance h=10 (ITUB4): mais perto de viver, ainda morre.
    Spread bruto +0.045 pts vs custo do par 2x0.026=0.052 -- perde por
    pouco. Taxa de acerto degrada suavemente 42% (Q1) -> 29% (Q5),
    padrao mais parecido com o WIN, mas sem magnitude suficiente
    nessa escala de preco.

CONCLUSAO: nenhum sinal de acao testado ate agora sobrevive ao teste
economico, mesmo com custo real e baixo (RLP). z_agf_3/z_agf_4090 no
WIN continuam os UNICOS sinais que passaram pelo funil completo (IC +
quintis + significancia). Isso NAO invalida o metodo -- e' exatamente
o resultado que o funil existe para produzir.
