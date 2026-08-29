# Plano do modulo research/ (decidido 2026-08-22, pre-implementacao)

Regras de desenho, decisoes de sinal/estrategia, e resultados -- em ordem
cronologica abaixo. Para navegar rapido por ASSUNTO em vez de ler tudo em
ordem, use o indice agrupado abaixo (2026-08-28, adicionado porque o
arquivo cresceu demais para navegar so' por titulo cronologico).

## Indice por assunto

**Perfil de agente / classificacao**
- [REVISAO DA HIPOTESE DE PERFIL (2026-08-22, operador)](#revisao-da-hipotese-de-perfil-2026-08-22-operador)
- [Revisao critica da taxonomia de 6 niveis (2026-08-22, operador pesquisou)](#revisao-critica-da-taxonomia-de-6-niveis-2026-08-22-operador-pesquisou)
- [Classificacao final de 2 camadas (2026-08-22, operador)](#classificacao-final-de-2-camadas-2026-08-22-operador)
- [CONCLUSAO DA VALIDACAO DE PERFIL (2026-08-23, aceita pelo operador)](#conclusao-da-validacao-de-perfil-2026-08-23-aceita-pelo-operador)
- [fluxo_nacional implementado (2026-08-23)](#fluxo_nacional-implementado-2026-08-23)

**z_agf_3 / z_agf_4090 (os sinais validados do WINFUT)**
- [Teste de diferenca entre quintis adjacentes (2026-08-23)](#teste-de-diferenca-entre-quintis-adjacentes-2026-08-23)
- [Segunda rodada de quintis — z_agf_3 h=1 passa no IC mas morre pelo custo (2026-08-26)](#segunda-rodada-de-quintis-z_agf_3-h1-passa-no-ic-mas-morre-pelo-custo-2026-08-26)
- [Resultado real do MAE + achado de assimetria compra/venda (2026-08-27)](#resultado-real-do-mae-achado-de-assimetria-compravenda-2026-08-27)
- [CORRECAO CRITICA: mae.py rodava sobre amostra inteira, nao out-of-sample (2026-08-27)](#correcao-critica-maepy-rodava-sobre-amostra-inteira-nao-out-of-sample-2026-08-27)

**z_agf_8 (fluxo UBS) — fechado**
- [FECHADO: z_agf_8 (fluxo UBS) descartado nos dois fronts (2026-08-27)](#fechado-z_agf_8-fluxo-ubs-descartado-nos-dois-fronts-2026-08-27)

**Acoes (VALE3/MGLU3/etc.) — mortas pelo custo**
- [Custo de transacao em ACOES na XP — ponderacao do operador (2026-08-26)](#custo-de-transacao-em-acoes-na-xp-ponderacao-do-operador-2026-08-26)
- [Conclusao final: sinais de acao morrem no teste economico (2026-08-26)](#conclusao-final-sinais-de-acao-morrem-no-teste-economico-2026-08-26)
- [Como calcular o custo real de acoes — planilha da XP + modulo dedicado (2026-08-28)](#como-calcular-o-custo-real-de-acoes-planilha-da-xp-modulo-dedicado-2026-08-28)

**Restricao de direcao (venda apenas) — decisao aceita**
- [PRE-REGISTRO: Restricao de direcao — venda apenas (2026-08-27)](#pre-registro-restricao-de-direcao-venda-apenas-2026-08-27)
- [RESULTADO do pre-registro "Restricao de direcao — venda apenas" (2026-08-27)](#resultado-do-pre-registro-restricao-de-direcao-venda-apenas-2026-08-27)

**Rota B — implementada, depois questionada (PENDENTE redesenho)**
- [PRE-REGISTRO: Rota B (payoff fixo, alvo/stop) — preparacao (2026-08-27)](#pre-registro-rota-b-payoff-fixo-alvostop-preparacao-2026-08-27)
- [Rota B: par CONGELADO, e uma tensao real revelada (2026-08-27)](#rota-b-par-congelado-e-uma-tensao-real-revelada-2026-08-27)
- [DECISAO: par empirico aceito (2026-08-27)](#decisao-par-empirico-aceito-2026-08-27)
- ⚠ ver `docs/HISTORICO_DE_SESSOES.md`, sessao 2026-08-27/28: mecanismo
  questionado com razao pelo operador DEPOIS da implementacao -- checagem
  so' no fechamento de barra nao e' stop/alvo continuo de verdade.
  Redesenho pendente antes de tentar de novo.

**Risco (drawdown, VaR/ES, circuit breaker)**
- [Curva de patrimonio / drawdown maximo (2026-08-27)](#curva-de-patrimonio-drawdown-maximo-2026-08-27)
- [Risco realizado (VaR/ES) — primeiro passo aplicado do RQ (2026-08-27)](#risco-realizado-vares-primeiro-passo-aplicado-do-rq-2026-08-27)
- [Resultado real do risco-realizado + correcao de bug de exibicao (2026-08-27)](#resultado-real-do-risco-realizado-correcao-de-bug-de-exibicao-2026-08-27)
- [Circuit breaker: com freio vs sem freio, num dia real (2026-08-27)](#circuit-breaker-com-freio-vs-sem-freio-num-dia-real-2026-08-27)
- [Acompanhamento continuo: efeito do circuit breaker com 25 dias (2026-08-28)](#acompanhamento-continuo-efeito-do-circuit-breaker-com-25-dias-2026-08-28)

**Disciplina/processo do proprio research**
- [Decisoes aprovadas](#decisoes-aprovadas)
- [Pre-requisitos antes de escrever research/](#pre-requisitos-antes-de-escrever-research)
- [Disciplina: quando rodar features vs quando rodar research (2026-08-27)](#disciplina-quando-rodar-features-vs-quando-rodar-research-2026-08-27)

**Outras decisoes (2026-08-22/23, nao encaixam nas categorias acima)**
- [Persistencia de corretora — desenho refinado (ideia do operador, 2026-08-22)](#persistencia-de-corretora-desenho-refinado-ideia-do-operador-2026-08-22)
- [IMPLEMENTADO (2026-08-22) — regras finais do veredito, pos teste de honestidade](#implementado-2026-08-22-regras-finais-do-veredito-pos-teste-de-honestidade)
- [PRIMEIRA RODADA REAL + IDENTIFICACAO DO CLUSTER (2026-08-23)](#primeira-rodada-real-identificacao-do-cluster-2026-08-23)
- [Resultado do teste de diferenca entre quintis (2026-08-23)](#resultado-do-teste-de-diferenca-entre-quintis-2026-08-23)

---

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

## Resultado real do MAE + achado de assimetria compra/venda (2026-08-27)

Rodado sobre 336 triggers reais de z_agf_3 h=3 (threshold=1.4):

  MAE_close: media=114.9  mediana=105.0  p90=395  p99=742  max=815
  15/336 (4.5%) teriam batido o stop de 500pts antes do horizonte natural
  pnl medio SEM stop hipotetico: +4.3 pts (BRUTO)
  pnl medio COM stop hipotetico: +7.1 pts

CONCLUSAO 1 (stop catastrofico): o stop JA ESTA mordendo de verdade
(4.5% nao e' desprezivel, MAE p99 supera o stop) -- mas o EFEITO no pnl
medio e' POSITIVO (+7.1 > +4.3): os casos que bateriam o stop, se
deixados correr, teriam terminado PIORES que -500 na media. O stop
esta funcionando como seguro de verdade, nao cortando caudas
ganhadoras -- SEM tensao com a Rota A nesta dimensao.

CONCLUSAO 2 (mais importante, achado NOVO): +4.3 pts bruto combinado
e' menor que o custo de transacao (~11pts) -- e revela uma ASSIMETRIA
real entre compra e venda que o threshold simetrico do ea.yaml estava
escondendo. Reconstruindo os quintis por lado (z_agf_3 h=3, 2026-08-25):
  Q1 (compra, extremo baixo): bruto +6.41 -- fraco, LIQUIDO NEGATIVO (-4.59) sozinho
  Q5 (venda, extremo alto):   bruto +33.73 -- forte, LIQUIDO POSITIVO (+22.73) sozinho

O sinal funciona bem VENDENDO contra o XP comprando forte, mas NAO
funciona comprando contra o XP vendendo forte -- ao tratar os dois
lados com o mesmo threshold, o lado fraco (compra) dilui o lado forte
(venda) no resultado combinado.

FERRAMENTA: mae.py agora quebra estatisticas por lado
(stats_compra/stats_venda: n, pnl_bruto_medio, mae_close_mediana,
pct_batido_stop) -- confirma isso direto nos 336 triggers reais, nao
so' inferido da tabela de quintis antiga.

DECISAO PENDENTE (do operador, nao automatica): considerar threshold
assimetrico, ou desativar o lado de compra, exigiria pre-registro
proprio antes de mudar o comportamento do EA -- mesma disciplina de
sempre, nao e' ajuste gratuito so' porque os numeros sugerem.

9 testes novos em test_mae.py. 237 testes.

## CORRECAO CRITICA: mae.py rodava sobre amostra inteira, nao out-of-sample (2026-08-27)

O resultado real do MAE (336 triggers) mostrou venda bruto=+11.6 pts --
bem menor que os +33.73 inferidos da tabela de quintis (que usa pool
out-of-sample). Investigando a discrepancia: mae.py NUNCA restringia aos
dias de teste do walk-forward -- rodava sobre TODA a amostra, misturando
dias de TREINO (que o IC usou para o proprio processo de avaliacao) com
dias de TESTE. quintis.py sempre seguiu essa disciplina (uniao dos
blocos de teste via gerar_folds); mae.py nao replicou isso -- descuido
meu, nao decisao deliberada.

CORRIGIDO: mae.py agora restringe ao MESMO pool out-of-sample que
quintis.py usaria, com os mesmos parametros treino_min/teste_dias
(default 3/2, iguais aos do research/quintis). Os dois numeros passam a
ser genuinamente comparaveis.

PENDENTE: re-rodar mae-analise com a correcao aplicada e comparar o novo
numero de venda (deve se aproximar mais de +33.73, ou revelar mais uma
camada de nuance se ainda divergir -- amostras diferentes por construcao
mesmo restrita: quintil Q5 e' os ~20% mais extremos, enquanto o threshold
exato de 1.4 do ea.yaml captura TUDO acima disso, uma populacao um pouco
mais ampla e portanto potencialmente mais fraca na margem).

2 testes novos (vazamento in-sample detectado + purge de dia sobrevive a
reindexacao apos filtro OOS). 240 testes.

## Circuit breaker: com freio vs sem freio, num dia real (2026-08-27)

Resultado real do operador (3 dias, WINFUT): com o circuit breaker
ligado, dia 26/08 parou em -578pts apos 3 perdas seguidas. Rodado de
novo com --ignorar-circuit-breaker (so' para analise), o mesmo dia
CONTINUOU e terminou em +187pts -- as 5 operacoes seguintes aquele dia
recuperaram tudo e ainda deram lucro. Agregado dos 3 dias melhorou de
-1402 (com freio) para -637 (sem freio); taxa de acerto subiu de 33.3%
para 47.1% (mais perto do ~43% que o proprio quintil ja sugeria).

LEITURA CORRETA, registrada para nao repetir o erro de decidir com
amostra pequena: isto NAO decide se max_perdas_consecutivas=3 esta mal
calibrado. So' 1 dos 3 dias disparou o freio -- n=1 evento nao decide
nada sobre a distribuicao real de "o que acontece depois de 3 perdas"
para este sinal. O freio protege contra o PIOR CASO, nao maximiza o
resultado esperado de UM dia -- julgar a regra por um unico evento
realizado e' o mesmo erro logico ja discutido para o sinal em si,
aplicado a gestao de risco.

FERRAMENTA: `ea-replay-lote --comparar-circuit-breaker` -- para todo
dia em que o freio disparar de verdade, carrega o parquet UMA vez e
roda DUAS simulacoes (com e sem freio) sobre o MESMO dado (sem reler o
arquivo duas vezes -- a leitura e' a parte cara). Mostra os dois
resultados lado a lado, com nota de cautela explicita no relatorio
contra decisao prematura.

PROXIMO PASSO: acumular MUITOS eventos de disparo do freio (semanas de
captura) antes de considerar ajustar max_perdas_consecutivas -- so' a
distribuicao de "com vs sem freio" atraves de dezenas de disparos
decide se a regra de 3 perdas esta bem calibrada para este sinal
especifico, ou se e' generica demais (herdada do framework de risco
geral do operador, nao derivada da pesquisa de z_agf_3).

5 testes novos (nova flag + validacao de combinacao invalida). 251
testes.

## PRE-REGISTRO: Restricao de direcao — venda apenas (2026-08-27)

Registrado ANTES de rodar o teste, pela mesma disciplina de sempre —
metodologia congelada antes de olhar o numero final.

### Motivacao
Tres fontes independentes convergiram na mesma assimetria: MAE (300
triggers OOS, 2026-08-27) mostrou compra bruto -3.7pts/op, venda
+22.0pts/op. EA replay em 163 operacoes reais (24 dias, 2026-07-24 a
2026-08-26) confirmou: compra -28.9pts/op liquido (n=78), venda
+20.2pts/op liquido (n=85) — e o resultado se manteve estavel mesmo
ampliando para 295 operacoes (compra -25.0, venda +16.1) ao incluir os
dias em que o circuit breaker bloqueou entradas.

### O QUE NAO E' este teste
NAO e' validacao out-of-sample nova. Roda sobre o MESMO periodo (23-24
dias) que revelou a assimetria -- e' confirmacao de engenharia sobre
padrao ja' observado, mesma categoria que mae.py/quintis.py (nao
consome trial de significancia do IC, porque nao e' uma nova hipotese
sobre se z_agf_3 preve preco -- isso ja' esta validado; e' uma decisao
de QUAL PARTE do sinal ja' validado operar). Circular por construcao se
tratado como "prova" -- e' engenharia, nao prova.

### Implementado
- SinalConfig.lado_permitido: "ambos" (default, nunca muda o
  comportamento historico) | "compra" | "venda".
- decidir() suprime a ABERTURA do lado restrito (vira Acao.NADA) --
  NUNCA suprime ZERAR (protecao de posicao existente continua sempre
  ativa, independente da restricao).
- config/ea_venda_apenas.yaml: mesma config do ea.yaml, so'
  lado_permitido: venda.

### Regra de decisao (congelada ANTES de ver o resultado)
Comparar `ea-replay-lote --comparar-circuit-breaker` do ea.yaml
(baseline, ambos os lados) contra ea_venda_apenas.yaml, no MESMO
periodo de dias:
  - Favoravel a restringir: pnl total da variante venda-apenas > pnl
    total do baseline, E razao ganho/perda >= a do baseline.
  - Inconclusivo: diferenca pequena, dentro do que amostra de ~85-148
    operacoes poderia gerar por variancia sozinha -- NAO decide nada,
    so' registra.
  - Contra restringir: pnl da variante pior que o baseline (indicaria
    que o circuit breaker/interacao entre os dois lados tem efeito
    protetor que a analise isolada por lado nao capturava).

### O que NAO muda so' com este teste
dry_run continua True. Nenhuma decisao de usar isto em producao
(dry_run=False) decorre deste teste sozinho -- gestao de risco e
forward-test em DEMO continuam pre-requisitos, ja' documentados em
EA_ARQUITETURA.md.

3 testes novos de decisao.py (lado_permitido venda/compra/ambos,
confirmando que ZERAR nunca e' suprimido). 257 testes.

## RESULTADO do pre-registro "Restricao de direcao — venda apenas" (2026-08-27)

Comparacao rodada no mesmo periodo (24 dias, 2026-07-24 a 2026-08-26),
`--comparar-circuit-breaker` nos dois:

|                          | baseline (ambos) | venda apenas |
|---|---|---|
| operacoes totais         | 163              | 142          |
| pnl total                | -533.0 pts       | +3228.0 pts  |
| taxa de acerto           | 47.2%            | 52.8%        |
| ganho medio              | +204.1           | +206.9       |
| perda media              | -189.0           | -183.4       |
| razao ganho/perda medio  | 1.080            | 1.128        |
| dias com freio disparado | 12/24            | 7/24         |
| efeito liquido do freio  | +757 pts         | +79 pts      |

Checagem de consistencia: soma das 142 operacoes individuais = +3228.0,
bate exatamente com o total declarado. compra: n=0 nas duas tabelas por
lado -- confirma que lado_permitido=venda suprimiu 100% das aberturas
de compra, nenhuma escapou.

### VEREDITO, pela regra CONGELADA antes de rodar

**FAVORAVEL** -- os dois criterios pre-registrados se confirmam:
  - pnl total venda-apenas (+3228) > baseline (-533): SIM
  - razao ganho/perda venda-apenas (1.128) >= baseline (1.080): SIM

### Leitura honesta (registrada ANTES do resultado, mantida)

Isto NAO e' surpresa estatistica nova -- e' consequencia quase
aritmetica do que ja se sabia: removendo um componente documentado
como perdedor (compra, -2253 a -3677 pts total em varias amostras) de
uma combinacao com um componente ganhador (venda, +1720 a +3228 pts
total), o resultado combinado melhora NA MESMA AMOSTRA que revelou essa
divisao. Confirmatorio de engenharia, nao prova estatistica
independente. A validacao de verdade e' prospectiva: como isto se
comporta em dias NOVOS, capturados a partir de 2026-08-27 em diante,
que nunca influenciaram a decisao de restringir o lado.

Achado adicional nao previsto no criterio formal, mas relevante: o
efeito liquido do circuit breaker caiu de +757 para +79 pts na
variante venda-apenas -- faz sentido, boa parte do que o freio
protegia era justamente sequencias de perda do lado de compra, que
agora nao existem mais.

### O que ISTO NAO decide (mantido do pre-registro original)

dry_run continua True. Nenhuma decisao sobre dry_run=False decorre
deste resultado sozinho -- gestao de risco (ja desenhada) e
forward-test em DEMO continuam pre-requisitos, EA_ARQUITETURA.md.

### Proximo passo (nao automatico, decisao do operador quando fizer sentido)

Acompanhar a MESMA comparacao (ea.yaml vs ea_venda_apenas.yaml)
conforme dias novos se acumularem a partir de agora -- cada dia novo
capturado dai em diante e' validacao prospectiva de verdade, nao mais
releitura do periodo que gerou a hipotese.

## Curva de patrimonio / drawdown maximo (2026-08-27)

Pergunta real do operador: "qual o tamanho de conta (saldo) necessario
para essa estrategia? Posso concluir que e' positiva, mas o saldo
exigido ser alto demais pode nao valer a pena."

IMPLEMENTADO: research/curva_patrimonio.py::calcular_curva_patrimonio()
-- algoritmo padrao de drawdown maximo (peak-to-trough) sobre o
historico cronologico real de operacoes ja simulado pelo EA. Devolve:
saldo final, drawdown maximo (R$ e %), capital minimo sugerido
(drawdown x 1.5 por padrao), calmar ratio (retorno/drawdown).

IMPORTANTE, escopo deliberadamente limitado: isto mede so' RUINA POR
P&L (saldo caindo a zero ou perto). NAO cobre zeragem por CONSUMO DE
GARANTIA da B3/XP (a corretora pode exigir mais margem por contrato num
dia de volatilidade alta, mesmo com saldo positivo e folgado) -- isso
exigiria cruzar com a tabela de margem real, fora de escopo aqui e
registrado como pendencia SEPARADA em EA_ARQUITETURA.md.

Drawdown em R$ e' INDEPENDENTE do capital_inicial escolhido (tamanho de
posicao e' fixo, 1 contrato) -- capital_inicial so' decide SE aquele
drawdown, aplicado aquele capital, teria zerado a conta. Conectado ao
`ea-replay-lote`: usa `todas_operacoes` (ordem cronologica real, nao
agrupada por lado) + `ea_cfg.risco.capital`/`valor_ponto_reais`.

7 testes no modulo de calculo (valores conferidos a mao, incluindo o
caso de conta zerando e a independencia do capital_inicial sobre o
drawdown em R$) + 1 teste de integracao no CLI. 276 testes.

## PRE-REGISTRO: Rota B (payoff fixo, alvo/stop) — preparacao (2026-08-27)

Registrado ANTES de rodar qualquer teste economico com alvo/stop --
mesma disciplina de sempre. Rota B ficou registrada em EA_ARQUITETURA.md
desde ontem como "evolucao futura, exige research proprio (MAE/MFE)
antes de substituir a saida por tempo". Hoje: MFE implementado
(mae.py), a decisao metodologica de COMO escolher o par continua em
aberto, registrada aqui com cuidado.

### O risco metodologico real que este pre-registro existe para evitar

Testar VARIOS pares de stop/alvo e escolher o que "deu melhor" e' a
MESMA forma de overfitting que justifica DSR/trials/limiar deflacionado
em todo o resto do projeto -- so' que aplicada ao lado economico em vez
do IC. Se isto vira uma busca (grid search) sobre combinacoes, e'
p-hacking disfarcado de engenharia, mesmo sem tocar no calculo do IC.

### Regra decidida: UM par, nao um grid

Rota B, quando for testada de verdade, testa **UM UNICO par** de
stop/alvo por sinal -- escolhido por PRINCIPIO a partir das distribuicoes
de MAE/MFE ja calculadas, nunca por selecao apos ver o resultado
economico. Principio proposto (a confirmar quando o teste for de fato
rodado): alvo = mediana do MFE_close do lado testado; stop = mediana do
MAE_close do mesmo lado -- ambos arredondados para o multiplo de 5 ou 10
mais proximo ANTES de rodar, nunca ajustados depois.

### O que ainda falta (NAO implementado, proximo passo real)

1. Rodar `mae-analise` com `--comparar-circuit-breaker`-like quebra por
   lado (ja existe) para pegar MFE_close_mediana especificamente do lado
   de venda (dado o resultado de hoje sobre a restricao de direcao) --
   e' o candidato natural, ja que e' o lado com edge confirmado.
2. Com os numeros de MAE/MFE do lado de venda em maos, congelar o par
   stop/alvo exato (numero, nao formula) NESTA secao, antes de escrever
   qualquer linha de codigo que implemente a saida por alvo/stop.
3. So' entao: estender GestorDeRisco com uma saida por ALVO opcional
   (paralela a saida por tempo, nao substituindo sem comparar as duas) --
   mudanca de codigo real, deliberadamente adiada para uma sessao com
   atencao plena (nao no fim de um dia longo), testada com o mesmo rigor
   de tudo que foi construido hoje.
4. Comparar (mesma disciplina de "Restricao de direcao"): saida por
   ALVO/stop fixo vs saida por TEMPO (Rota A), no MESMO periodo,
   criterio de favoravel/desfavoravel/inconclusivo definido ANTES de ver
   o resultado.

### O que JA esta pronto para o proximo passo

- `mae.py` calcula MFE_close (media, mediana, p10, p90) -- complemento
  simetrico do MAE, mesma disciplina de janela/purge/OOS.
- Quebra por lado do MAE (ja existente desde a analise de assimetria)
  aplica-se igual ao MFE -- so' falta rodar e ler o numero.

3 testes novos de MFE (valores conferidos a mao, compra e venda,
relatorio inclui a secao). 280 testes.

## Risco realizado (VaR/ES) — primeiro passo aplicado do RQ (2026-08-27)

Discussao com o operador sobre a literatura de Realized Quantiles (RQ,
Journal of Business & Economic Statistics 2021): estimar quantis de
risco direto de retorno de alta frequencia, em "tempo intrinseco"
(transformado pela atividade de negociacao, nao pelo relogio).

CONEXAO DE DESIGN, nao coincidencia: "tempo intrinseco" e' exatamente o
conceito de "volume clock" (Easley/Lopez de Prado/O'Hara) que ja
motivou a escolha de barras por VOLUME neste projeto desde o inicio.
Nossas barras JA SAO amostragem em tempo intrinseco -- a fundacao
teorica do RQ ja esta embutida na arquitetura, sem esforco extra.

IMPLEMENTADO (primeiro passo, escopo deliberadamente limitado -- NAO a
maquinaria completa do paper, que projeta quantil intradiario para VaR
DIARIO via relacao de escala de autossimilaridade, nao validada aqui):
research/risco_realizado.py --
  - var_es_realizado(): VaR (quantil empirico) + Expected Shortfall
    (media da cauda que excede o VaR) de retorno de barra, por nivel de
    confianca.
  - nivel_implicado_por_limiar(): pergunta INVERSA -- dado um limiar ja'
    escolhido (ex.: os 500pts do stop catastrofico), que nivel de
    confianca empirico ele representa? Responde diretamente "o stop
    esta bem calibrado contra o comportamento real do instrumento, ou
    e' arbitrario"?
  - var_es_por_faixa_horario(): a MESMA pergunta segmentada por faixa
    de horario -- necessario porque o padrao em U de volume/
    volatilidade intradiaria (ja documentado neste projeto) quebra a
    suposicao de estacionariedade se agrupado sem segmentar. Conecta
    diretamente ao item pendente "segmentacao de IC por horario" --
    o mesmo trabalho de condicionamento serve aos dois.

NAO consome trial: engenharia/descricao sobre o INSTRUMENTO
(incondicional a qualquer sinal), mesmo espirito de mae.py/quintis.py.

Comando `profit-tape risco-realizado --symbol WINFUT --limiar-pontos 500
--por-horario`.

8 testes (valores conferidos a mao, incluindo a segmentacao por horario
com regimes de volatilidade propositalmente diferentes). 291 testes.

PROXIMO PASSO (nao automatico): rodar sobre o dado real do WINFUT e
comparar o nivel de confianca implicado pelos 500pts contra o esperado
-- se vier muito baixo (ex.: so' 90% em vez de 99%+), e' evidencia
concreta de que o stop catastrofico deveria ser recalibrado com base no
comportamento empirico do instrumento, nao so' na regra de capital.

## Resultado real do risco-realizado + correcao de bug de exibicao (2026-08-27)

Rodado sobre 2135 barras do WINFUT (23 dias):

  Agregado: 500pts = 98.69% de confianca (1.31% das barras excedem)
  Consistente na direcao com o MAE (4.5% de operacoes bateriam o stop
  dentro da janela de 3 barras -- numero diferente pois mede janela
  multi-barra, nao barra isolada, mas aponta a mesma direcao geral).

  Por horario -- O ACHADO QUE IMPORTA: na ABERTURA, 500pts cai ENTRE o
  VaR_90 (360) e o VaR_95 (564) -- ou seja, na abertura especificamente
  o stop cobre so' ~90-95% de confianca, bem ABAIXO dos 98.69%
  agregados. O meio do pregao (mais calmo, n=1696 de 2135 barras) dilui
  o numero geral, escondendo que na abertura o stop protege bem menos.
  Fechamento (n=89, so' 1 barra na cauda do nivel 99.5%) e' amostra
  fragil demais para confiar com a mesma forca.

IMPLICACAO: se as entradas do EA se concentrarem na abertura (fluxo
mais intenso), o stop catastrofico esta, na pratica, mais perto de
90-95% de confianca do que os 98.69% agregados sugerem. Nao decide
sozinho mudar o stop -- registra a evidencia concreta de que a
sazonalidade intradiaria (ja' documentada) afeta a calibracao de
risco tanto quanto afeta o IC.

BUG DE EXIBICAO corrigido: mesma familia do bug ja corrigido em
quintis.py (v0.58) -- um float_format UNICO (.2f) aplicado a tabela
inteira fazia nivel_confianca=0.995 arredondar para "0.99",
colidindo visualmente com o nivel 0.99 de verdade (os VALORES de
VaR/ES estavam sempre corretos, so' o ROTULO do nivel colidia). Nao
detectado antes por descuido meu (o padrao de correcao ja existia,
nao foi reaproveitado ao escrever risco_realizado hoje). Corrigido
com formatters por coluna -- nivel_confianca em percentual (99.0%
vs 99.5%, inequivoco).

1 teste de regressao dedicado. 301 testes.

## Disciplina: quando rodar features vs quando rodar research (2026-08-27)

Pergunta real do operador: acumular dias antes de rodar, ou rodar
sempre? Duas ferramentas, duas regras bem diferentes -- nunca
formalizado por escrito ate agora.

### features todos -- SEM custo, rodar sempre que convier

Recalcula barras/z-scores sobre TODO o curated acumulado. Nao consome
trial, nao tem orcamento -- so' custa tempo de maquina. Rodar toda vez
que o curate terminar, sem pensar duas vezes.

### research -- TEM custo real (trials.json, limiar deflacionado sobe
### a CADA rodada, nao importa quantos dias novos foram adicionados)

Rodar com poucos dias novos desde a ultima vez gasta orcamento
estatistico por muito pouca evidencia genuinamente nova -- proximo do
mesmo problema que o DSR existe para penalizar.

REGRA (decorre diretamente da estrutura do walk-forward, nao e'
arbitraria): so' rodar `research` de novo quando pelo menos
`teste_dias` (default 2) dias NOVOS tiverem se acumulado desde a
ultima rodada -- e' o minimo para formar um bloco de teste out-of-
sample genuinamente novo. Menos que isso, o "novo" trial nao testa
quase nada de fato novo.

Mais conservador (recomendado quando nao ha pressa): esperar uma
semana inteira de pregoes acumulados, nao so' o minimo de 2 dias --
cada rodada de research vale mais a pena com mais dado novo por trial
gasto.

PRATICA: antes de rodar `research`, checar quantos dias novos existem
desde o `- dias:` do ultimo relatorio gerado em data/research/. Se for
menor que teste_dias, esperar mais.

## FECHADO: z_agf_8 (fluxo UBS) descartado nos dois fronts (2026-08-27)

Hipotese: momentum institucional (IC positivo, UBS, aparecendo em varios
ativos). Testado em dois fronts, ambos negativos:

**Acoes (VALE3, MGLU3)**: morto pelo custo nos dois horizontes (h=1,
h=3), CONFIRMADO DUAS VEZES -- primeiro com custo generico (0.026
pts/acao), depois com custo corrigido a partir da planilha real da XP
(0.005 pts/acao para MGLU3, calculado com formula exata replicada e
conferida). Com o custo correto (5x MENOR que o testado antes), o
padrao "%>0 liquido" normalizou (deixou de ser uniformemente baixo em
todos os quintis, evidencia de que o custo antigo estava mal
calibrado) -- mas o Q5 continua liquido NEGATIVO nos dois horizontes
(edge bruto ~0.002pts, menor que o proprio custo real de 0.005pts).
Morte mais honesta que a primeira vez, nao mais dependente de custo
duvidoso.

**WINFUT**: ja' estava na lista de features testadas na rodada
ORIGINAL de research (2026-08-23T11:21:32Z, 42 trials, 21 dias,
arquivo=sym=WINFUT) -- NAO passou no filtro de IC/DSR em nenhum dos 3
horizontes testados (1, 3, 10). So' z_agf_3 h=3 e z_agf_4090 h=1
passaram naquela rodada. Confirmado via leitura direta de trials.json
(match EXATO de string, nao substring -- z_agf_85/z_agf_88 sao
strings DIFERENTES que colidem em buscas ingenuas tipo grep/
Select-String) -- SEM gastar trial novo, so' lendo o que ja' estava
registrado.

CONCLUSAO: a hipotese do fluxo institucional do UBS, nesta formulacao
especifica (z_agf_8), nao se sustentou em nenhum lugar testado.
Fechado -- nao reabrir sem feature/hipotese NOVA (ex.: outra
transformacao do mesmo fluxo, ou outro agente institucional).

## Rota B: par CONGELADO, e uma tensao real revelada (2026-08-27)

Seguindo o principio ja' pre-registrado (mediana do MAE/MFE do lado de
venda, arredondado ANTES de ver o resultado economico), com n=336
triggers (26 dias):

  MAE_close mediana (venda) = 95.0  -> arredondado p/ 100
  MFE_close mediana (venda) = 120.0 -> ja' redondo

PAR CONGELADO: stop=100 pts, alvo=120 pts.

TENSAO REAL: payoff implicito = 120/100 = 1.2:1 -- bem abaixo do 2:1
que motivou a consideracao original da Rota B (alinhado ao framework
geral de analise de preco do operador). Nao e' erro de calculo -- e' o
que a mediana real do MFE mostra ser tipicamente alcancavel dentro da
janela de holding deste sinal especifico.

TRES CAMINHOS, nenhum decidido automaticamente:
1. Aceitar o par empirico (1.2:1) -- coerente com o dado, nao com a
   preferencia original de payoff.
2. Usar quantil mais otimista para o alvo (ex.: p90 do MFE=412.5) --
   precisaria ser uma escolha de PRINCIPIO decidida agora, nao
   selecionada depois de ver o resultado; maioria das operacoes NAO
   bateria esse alvo mais distante, saindo por tempo mesmo assim.
3. Concluir que payoff 2:1 nao e' compativel com este sinal -- manter
   Rota A (saida por tempo) como esta, arquivar Rota B para z_agf_3
   especificamente (poderia ainda fazer sentido para outro sinal no
   futuro).

PENDENTE: decisao do operador entre os 3 caminhos ANTES de escrever
qualquer codigo em risco.py. Implementacao do overlay continua
deliberadamente adiada (mudanca real de comportamento de risco,
merece sessao com atencao plena).

## DECISAO: par empirico aceito (2026-08-27)

Operador optou pelo caminho 1: aceitar o par empirico como esta,
sem forcar o payoff 2:1 original.

**Rota B, especificacao final para implementacao futura:**
- stop = 100 pts
- alvo = 120 pts
- payoff implicito = 1.2:1
- lado: venda (o unico com edge confirmado) -- ou ambos os lados, a
  decidir junto com a decisao ja pendente de "Restricao de direcao
  venda apenas" (as duas mudancas de design deveriam ser avaliadas
  coerentemente, nao independentes uma da outra)
- feature/horizonte: z_agf_3 h=3 (o sinal onde este MAE/MFE foi
  medido -- nao generalizar para outro sinal sem medir o proprio
  MAE/MFE dele)

Implementacao (extensao de risco.py com saida por alvo/stop fixo,
paralela a saida por tempo) continua PENDENTE -- proxima sessao,
codigo real de mudanca de comportamento de risco.

## Acompanhamento continuo: efeito do circuit breaker com 25 dias (2026-08-28)

Rodada com ea_venda_apenas.yaml (25 dias, 2026-07-24 a 2026-08-27, 157
operacoes): taxa de acerto 51,0% (primeira vez cruzando 50%), razao
ganho/perda 1,00 exato (neutro, nao claramente favoravel nem
desfavoravel), pnl total +418 -- mas 08/27 sozinho rendeu +629 (sem
esse dia, os outros 24 somariam -211). Amostra ainda sensivel a poucos
dias fortes.

Circuit breaker (7 disparos, 25 dias): efeito liquido REVERTEU para
NEGATIVO (-328 pts -- salvou 1014, custou 1342) -- diferente das
rodadas anteriores (24 dias, venda-apenas) onde o efeito era proximo
de neutro/levemente positivo (+79pts). n=7 ainda nao e' "muitos
eventos" o suficiente para recalibrar max_perdas_consecutivas, mas a
tendencia de piorar conforme mais dias entram merece continuar sendo
acompanhada -- NAO decidir nada ainda.

Calmar ratio desta rodada: 0,23 (fraco) -- drawdown grande relativo ao
retorno liquido, mesmo com edge medio positivo confirmado. Sinal de
eficiencia de capital ainda baixa, complementar (nao contraditorio) ao
resultado agregado positivo.

Observacao tecnica: valores extremos nas operacoes individuais desta
rodada (+524, -386, +409...) excedem os limiares 100/120 da Rota B --
confirma que esta rodada usou ea_venda_apenas.yaml (Rota A, saida por
tempo), NAO ea_venda_rota_b.yaml. Comparacao direta com Rota B sobre
este mesmo periodo de 25 dias ainda nao foi feita.

## Como calcular o custo real de ações — planilha da XP + módulo dedicado (2026-08-28)

A planilha real de custos da XP está versionada em
`docs/referencias/custos_acoes_xp.xlsx`. Não recalcule à mão nem reuse
um número fixo entre ativos — o custo tem componente FIXO (corretagem,
por ordem) e componente PROPORCIONAL (taxas B3, sobre o financeiro),
então **não é constante por ação entre ativos de preços diferentes**,
mesmo mantendo o mesmo risco exposto (achado real que motivou este
módulo: `0,026 pts/ação` genérico distorceu o teste de `z_agf_8` em
MGLU3 — corrigido depois, ver seção "Custo de transação em ACOES").

**Uso direto pelo terminal** (o jeito mais rápido, para pegar o número
antes de rodar `quintis`):
```powershell
profit-tape custo-acoes --preco 4.59 --financeiro 10000
```
Devolve o `custo_por_acao_reais` pronto para colar em
`--custo-pontos` do comando `quintis` — **específico do ativo e do
financeiro escolhido**, nunca reaproveitar entre ativos diferentes.

**Uso programático** (`src/profittape/research/custo_acoes.py`):
- `carregar_parametros_xp(caminho_xlsx)` — lê os parâmetros da aba
  "Parametros" da planilha (corretagem fixa, taxas B3, taxa
  operacional XP). Se a XP mudar taxas no futuro, atualize a planilha
  e rode de novo — não há número fixo no código.
- `custo_giro_dia_trade(preco, quantidade, parametros)` — replica
  exatamente a fórmula da aba "Calculadora" (Day Trade, nunca aluguel
  BTC — o EA nunca carrega posição overnight). Devolve financeiro,
  custo total do giro em R$, custo por ação, e custo como % do
  financeiro.
- `custo_pontos_para_quintis(preco, financeiro_alvo, caminho_xlsx)` —
  atalho de conveniência, mesmo resultado do comando CLI.

Fórmula validada linha por linha contra o exemplo já preenchido na
própria planilha (`preço=37,52`, `qtd=300` → `custo_giro=12,18514784`,
conferido à mão antes de confiar no código — 4 testes automatizados em
`tests/test_custo_acoes.py`, incluindo o achado de assimetria entre
VALE3/MGLU3 como caso de regressão).
