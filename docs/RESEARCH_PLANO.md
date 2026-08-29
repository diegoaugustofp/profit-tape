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
- [Como calcular o custo real de acoes — planilha da XP + modulo dedicado (2026-08-28)](#como-calcular-o-custo-real-de-ações-planilha-da-xp-módulo-dedicado-2026-08-28)

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
- [PRE-REGISTRO: existe reversao condicional em z_agf_3? (2026-08-29)](#pre-registro-existe-reversao-condicional-em-z_agf_3-2026-08-29)
  — revisao do desenho desde o inicio: ALVO descartado como conceito
  para este sinal (incompativel com edge de cauda); stop separado em
  duas hipoteses distintas (limite de perda vs detector de reversao).
- [IMPLEMENTADO: `reversao-condicional` — executa o pré-registro (2026-08-29)](#implementado-reversao-condicional-executa-o-pré-registro-2026-08-29)
- [RESULTADO ANULADO: o pré-registro de 2026-08-29 tinha estimador inválido](#resultado-anulado-o-pré-registro-de-2026-08-29-tinha-estimador-inválido)
- [PRE-REGISTRO 2: expectativa remanescente a partir do toque (2026-08-29b)](#pre-registro-2-expectativa-remanescente-a-partir-do-toque-2026-08-29b)
- ⚠ o pre-registro de 2026-08-29 rodou e o veredito foi ANULADO: o
  estimador tinha tautologia embutida (MAE_intrabar >= perda final,
  por construcao) e devolvia FAVORAVEL sobre ruido puro. Hipotese (b)
  segue SEM RESPOSTA; ver o pre-registro 2.

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

## PRE-REGISTRO: existe reversao condicional em z_agf_3? (2026-08-29)

> **CONGELADO em 2026-08-29 pelo operador**, antes de qualquer linha de
> código do teste e antes de qualquer contato com o dado. Hipótese,
> metodologia, grade de X, critério de decisão e regra de parada estão
> fixados a partir daqui. Alteração de qualquer um desses itens exige
> um pré-registro NOVO, com seção própria e data própria — não editar
> esta seção.

Registrado ANTES de rodar qualquer coisa. Nenhum código foi escrito
para responder esta pergunta até este documento ser congelado.

### Por que este pré-registro existe

Rota B (alvo/stop fixo, par 100/120) foi implementada em 2026-08-27 e
questionada com razão pelo operador logo depois: checagem só no
fechamento de barra não é stop/alvo contínuo de verdade. Ao revisar o
desenho **desde o início** (2026-08-29), apareceu um segundo defeito
que tinha sobrevivido ao primeiro, e uma ambiguidade que precisa ser
resolvida antes de qualquer redesenho.

**O segundo defeito** (não corrigido, registrado aqui): a decisão de
Rota A (2026-08-26) rejeitou alvo fixo com o argumento de que "alvo
fixo 2:1 cortaria exatamente as caudas ganhadoras que pagam a conta".
O congelamento do par (2026-08-27) instalou um alvo em 120 quando o p90
do MFE é 412,5 — sobre um sinal cujo edge vem de magnitude, não de
frequência (Q5 com ~43% de acerto). O elo 4 não refutou o elo 2; passou
por cima dele, porque a discussão naquele momento era sobre payoff
(1,2:1 vs 2:1), não sobre compatibilidade entre alvo fixo e edge de
cauda. **Alvo, como conceito, está fora deste pré-registro e fora do
redesenho de Rota B para z_agf_3.**

**A ambiguidade** que este documento existe para resolver: "usar stop"
significa duas coisas diferentes, que foram se misturando na conversa.

  (a) STOP COMO LIMITE DE PERDA. Sai quando a perda atinge X. Não
      afirma nada sobre o sinal. Custa expectativa e compra redução de
      drawdown — trade-off mensurável, não hipótese sobre o mercado.
      Motivação viva e legítima: Calmar 0,23 na rodada de 25 dias.

  (b) STOP COMO DETECTOR DE REVERSAO. Sai porque o movimento contra é
      EVIDENCIA de que o edge expirou. Isto é uma afirmação
      inferencial, testável, e ainda não testada.

(a) e (b) exigem mecanismos e justificativas diferentes. Este
pré-registro testa **apenas (b)**.

### Hipótese testada (H_b)

Existe uma magnitude de excursão adversa X tal que, condicionado a a
posição ter atingido -X pontos em algum momento da janela de holding, a
expectativa líquida remanescente até o fim da janela é pior que a
expectativa incondicional — e pior de forma sistemática, não pontual.

### Contra-hipótese, registrada ANTES

`z_agf_3` é contrarian: entra fazendo fade de um extremo de fluxo. Se o
preço anda contra depois da entrada, o extremo ficou MAIS extremo — em
reversão à média, movimento adverso pode ser melhora da entrada, não
refutação da tese. A intuição de "sinal reverteu, sai" é intuição de
seguidor de tendência e se inverte aqui.

Logo, um resultado na direção OPOSTA (expectativa condicional MAIOR que
a incondicional) é um achado genuíno e deve ser registrado como tal,
não descartado como anomalia. Mas NÃO autoriza automaticamente
"aumentar posição no adverso" — isso é pirâmide, proibida por design em
`ea/decisao.py`. Seria um pré-registro novo, separado.

### Categoria: NAO consome trial

Tradução econômica condicional sobre um sinal JA validado pelo IC —
mesma família de `mae.py`, `quintis.py`, `risco_realizado.py`,
`curva_patrimonio.py` (ver regra 2 da skill `profit-tape-disciplina`).
Não é hipótese de sinal nova, não sobe o limiar deflacionado.

### Metodologia, fixada ANTES de rodar

- **População**: gatilhos de `z_agf_3`, h=3, `threshold_entrada` 1.4,
  `direcao: contrarian`, `agent_id: 3`, `volume_barra` 120000,
  `janela_z` 50 — MESMA regra de entrada de `ea/decisao.py`. Lado
  **venda apenas** (o único com edge confirmado).
- **Pool out-of-sample**, nunca a amostra inteira (o bug real já
  corrigido em `mae.py` em 2026-08-27 — não repetir).
- **Purga estrutural de dia inteiro**: as últimas h barras de cada
  pregão ficam de fora, retorno nunca cruza fronteira de pregão (mesma
  regra de `retornos.py`).
- **Como medir "atingiu -X"**: excursão adversa **intrabar**
  (`MAE_intrabar`, já existente em `mae.py`, usando o HIGH da barra no
  lado vendido) — NAO por close. Este ponto é deliberado e é a correção
  direta do erro de Rota B: mede-se do jeito que se pretende EXECUTAR
  (um stop real é contínuo), não se executa do jeito que por acaso se
  mediu. O tape é trade a trade (`atribuir_barras` opera sobre negócio
  individual), então a ordenação intrabar é integralmente resolvível se
  o high/low de barra se mostrar grosseiro demais.
- **Resultado medido**: P&L LIQUIDO (bruto − `custo_pontos_estimado`
  11,0) no fechamento de t+3 — ou seja, o que a Rota A de fato entrega.
  A pergunta é "dado que tocou -X, o que a Rota A realiza no fim da
  janela?", não "quanto o stop teria salvado".
- **Grade de X, fixada agora**: {40, 60, 80, 100, 120, 150, 200} pts.
  Sete pontos, múltiplos redondos, escolhidos por cobertura da faixa
  onde o MAE observado vive (mediana 95), NAO por inspeção de
  resultado.
- **Estatística**: Welch t-test do subgrupo condicionado contra o
  incondicional (variâncias desiguais, tamanhos diferentes), com
  bootstrap por bloco de pregão inteiro para a dependência
  intradiária — padrão já usado no projeto.
- **Correção para múltiplas comparações**: 7 pontos de grade, mesma
  lógica do limiar deflacionado usada no IC. Um ponto isolado
  "significativo" numa grade de 7 não decide nada sozinho.
- **n mínimo por ponto**: subgrupo com n < 30 é REPORTADO mas marcado
  INCONCLUSIVO por construção, nunca interpretado.
- **Reportar SEMPRE todos os 7 pontos**, inclusive os que não deram
  nada. Reportar só o melhor ponto seria a mesma p-hacking que o
  pré-registro original de Rota B existia para evitar.

### Critério de decisão, definido ANTES de ver qualquer número

**FAVORAVEL a (b)** — as três condições, juntas:
  1. Existe X* na grade com expectativa condicional negativa e
     significativamente abaixo da incondicional (após a correção para
     as 7 comparações);
  2. MONOTONICIDADE: todos os X > X* da grade também negativos. A
     hipótese (b) prevê deterioração progressiva, não um buraco
     isolado. Mesmo raciocínio que já concluiu que a não-monotonicidade
     Q4→Q5 era ruído e o degrau Q3→Q4 era estrutura;
  3. n ≥ 30 no ponto X* e nos pontos acima dele.
  → (b) existe. X* vira o candidato a stop, DERIVADO da estrutura
  condicional, não da mediana de uma distribuição descritiva.

**CONTRA (b)**: nenhum X da grade produz expectativa condicional
distinguível da incondicional.
  → (b) é falso para este sinal. Stop só se justifica como (a), e aí o
  custo em expectativa precisa ser medido explicitamente — pré-registro
  separado, decisão consciente de trocar expectativa por drawdown.

**INCONCLUSIVO**: efeito presente mas não monótono, ou n insuficiente
nos pontos relevantes.
  → registrar, não decidir, aguardar mais pregões.

### Regra de parada

Proibido re-rodar com grade ajustada, threshold diferente, outro
horizonte ou outro lado depois de ver o resultado. Se der
INCONCLUSIVO, a única continuação legítima é acumular mais pregões e
rodar de novo com a MESMA grade. Qualquer grade nova exige
pré-registro novo, do zero.

### Explicitamente FORA deste pré-registro

- Escolha do número final do stop (mesmo se (b) der favorável — X* é
  candidato, não decisão).
- Qualquer implementação em `ea/risco.py`.
- Alvo, em qualquer forma (ver "segundo defeito" acima).
- Medição do custo em expectativa do stop-como-(a).

## IMPLEMENTADO: `reversao-condicional` — executa o pré-registro (2026-08-29)

`research/reversao.py` + comando `profit-tape reversao-condicional`.
Implementa **literalmente** o critério congelado — grade, n mínimo e
veredito estão no código, não como opção de linha de comando.

**Ponto estatístico registrado ao implementar** (correção de
implementação da mesma intenção, NÃO mudança de critério — registrado
explicitamente para não virar ajuste silencioso): o pré-registro
descreve a comparação como "condicional vs INCONDICIONAL". Está
implementado como "tocou -X" vs "NÃO tocou -X", grupos **disjuntos**,
porque o grupo incondicional CONTÉM o condicional — Welch entre
subconjunto e superconjunto tem amostras dependentes, subestima o erro
padrão da diferença e infla o t (anti-conservador). A média
incondicional continua reportada como referência descritiva; o TESTE
roda entre disjuntos.

**Significância exige as duas evidências**: |t| ≥ limiar deflacionado
de 7 comparações E intervalo de bootstrap por bloco que exclui zero. A
interseção é conservadora de propósito — o bootstrap por pregão é quem
trata a dependência intradiária, o Welch sozinho a ignora.

Conferido à mão antes dos testes automatizados (regra 4): Welch
(t=−5,656854, gl=3,8571 num cenário de 3 vs 4 observações), excursão
intrabar nos dois lados (HIGH no vendido = 30 pts, LOW no comprado =
22 pts no mesmo cenário — a assimetria é a classe de bug de sinal
invertido que já apareceu em fórmula de MFE neste projeto), e o purge
estrutural descartando janela que cruzaria o pregão.

14 testes novos, incluindo guarda de regressão sobre a grade congelada:
se `test_grade_esta_congelada` falhar, a pergunta certa é "onde está o
pré-registro novo?", não "como faço o teste passar?". 279 testes.

NÃO consome trial. `trials.json` não é tocado — o limiar deflacionado é
usado apenas para corrigir as 7 comparações desta grade.

## RESULTADO ANULADO: o pré-registro de 2026-08-29 tinha estimador inválido

O teste rodou (162 operações, 22 pregões, lado venda) e devolveu
**FAVORAVEL a (b), X\* = 60 pts**, com t entre −7,5 e −13,2 em toda a
grade. **Esse veredito está ANULADO.** Não é achado, é artefato.

### A identidade que quebra o estimador

Numa venda, `MAE_intrabar = max(high_i − entrada)` sobre a janela, e o
resultado é `entrada − close_final`. Como o `high` da última barra é
sempre ≥ o `close` dela:

    MAE_intrabar >= perda bruta final, SEMPRE, por construção.

Consequência direta: o grupo "não tocou −X" **não pode conter nenhuma
operação que perdeu mais de X** — o teto de perda dele é X, por
definição. E o grupo "tocou −X" recebe automaticamente todos os
perdedores grandes. A variável de condicionamento e o desfecho são
funções do MESMO caminho de preço, mecanicamente anticorrelacionadas.
O teste não media reversão; media a própria identidade.

### A impressão digital estava na tabela

A coluna `dif` ficou praticamente CONSTANTE na grade inteira (−404,
−360, −404, −392, −401, −428, −446). Um efeito estrutural real ficaria
mais forte conforme X sobe. Constância assim é assinatura de
tautologia, não de estrutura. E `media nao tocou` entre +219 e +382
pts líquidos por operação, com média incondicional de +14,96, não é
edge: é o subconjunto das operações que foram direto a favor,
selecionado depois do fato.

### Teste de honestidade (a prova)

O mesmo módulo, sobre RANDOM WALK PURO (drift zero, feature de ruído
independente do preço, zero edge por construção), n=841:

    X=40   media toc −48,42   media nao +110,55   dif −158,97   t −22,52  SIM
    X=100  media toc −93,64   media nao  +71,96   dif −165,60   t −27,26  SIM
    X=200  media toc −168,80  media nao  +21,85   dif −190,65   t −25,16  SIM
    VEREDITO SOBRE RUIDO PURO: FAVORAVEL a (b)

Mesma forma, mesma monotonicidade, t ≈ −25. **O estimador dá favorável
para nada.**

### A lição, e por que anular não é p-hacking ao contrário

A regra 0 (valide o MECANISMO antes de calibrar NÚMEROS) foi aplicada
corretamente ao mecanismo — stop contínuo faz sentido, e continua
fazendo. O que não foi validado foi o **ESTIMADOR**: a forma de medir.
É a mesma falha um nível abaixo de onde ela pegou a Rota B, e o
pré-registro congelou o estimador viciado. Congelar não torna válido.

A anulação é legítima porque o argumento é **a priori**: a álgebra
acima é provável sem olhar o dado, e o defeito se reproduz em ruído
puro. Não é "não gostei do número" — dava para provar isto ANTES de
rodar. Se a justificativa dependesse do resultado ter desagradado,
seria p-hacking ao contrário e a anulação não valeria.

**Regra nova, incorporada ao pré-registro seguinte**: nenhum estimador
novo é interpretado antes de passar por um teste de honestidade sobre
ruído puro. Deixa de ser boa prática opcional e vira PORTÃO obrigatório.

### O que o dado insinua, de raspão (pista, não achado)

Quem tocou −100 terminou em −92,5 bruto; quem tocou −200 terminou em
−216,5. A expectativa A PARTIR DO TOQUE parece rondar zero. É
enviesado (condicionar em MAE ≥ X significa que o pior real foi mais
fundo que X), então é pista para desenhar o teste certo, nunca
conclusão.

## PRE-REGISTRO 2: expectativa remanescente a partir do toque (2026-08-29b)

Registrado ANTES de qualquer código. Substitui o estimador anulado
acima; a pergunta de fundo (hipótese (b)) permanece a mesma e continua
sem resposta.

### A correção central

O condicionamento e o desfecho precisam viver em segmentos **disjuntos**
do caminho de preço. A pergunta passa a ser exatamente a decisão que um
stop toma:

> No instante τ em que eu sairia a −X, qual a expectativa de CONTINUAR
> até o fim da janela?

A perda que já aconteceu ANTES de τ é irrelevante para essa decisão — e
era justamente ela que o estimador anulado contava.

Estimador: para cada operação que toca −X dentro da janela,

    remanescente = (close_{t+h} − F) * lado

onde `F` é o preço de preenchimento do stop em τ. Operações que nunca
tocam −X são simplesmente EXCLUÍDAS. **Não há grupo de comparação** — é
uma pergunta de UMA amostra contra zero, o que elimina de raiz o
problema de subconjunto vs superconjunto do pré-registro anterior.

### Custo: medido BRUTO, de propósito

A comparação em τ é entre sair agora e segurar. Nos dois ramos paga-se
exatamente um giro (uma entrada, uma saída). O custo **cancela**. Medir
líquido aqui seria contá-lo duas vezes.

### O preenchimento F — dois limites, com escalonamento definido

Sem o tape trade a trade, `F` não é observável exatamente. Ficam dois
limites, ambos calculáveis a partir das barras:

- **PRIMÁRIO — pessimista**: `F` = extremo da barra de cruzamento (HIGH
  no vendido / LOW no comprado). Assume o pior preenchimento possível
  dentro da barra.
- **SENSIBILIDADE — otimista**: `F` = o próprio nível do stop
  (`entrada − X·lado`), preenchimento perfeito.

A assimetria é conhecida e registrada ANTES: o limite pessimista mede a
partir de um preço pior, o que faz o remanescente parecer MAIS POSITIVO
— ou seja, é conservador CONTRA (b). O limite otimista mede a partir do
nível, ignorando o overshoot real do cruzamento, o que faz o
remanescente parecer MAIS NEGATIVO — anti-conservador, tende A FAVOR de
(b). A verdade fica entre os dois.

Isso define a leitura, fixada agora:

- Os DOIS limites negativos e significativos → suporta (b) de forma
  robusta (o pessimista, que trabalha contra (b), não conseguiu matá-lo).
- Os DOIS positivos e significativos → direção INVERTIDA de forma
  robusta (o otimista, que trabalha a favor de (b), não conseguiu
  produzi-lo). É a contra-hipótese contrarian.
- Limites com SINAIS DIFERENTES → INCONCLUSIVO POR PREENCHIMENTO.
  Escalonamento definido, não julgamento: só então vale construir a
  leitura de `F` exato a partir do tape trade a trade (que existe —
  `atribuir_barras` opera sobre negócio individual). Não construir essa
  infraestrutura antes de ela ser necessária.
- Nenhum significativo → CONTRA (b): o stop é neutro em expectativa, e
  a discussão volta a ser (a), drawdown puro.

### PORTÃO DE HONESTIDADE (obrigatório, antes de interpretar qualquer coisa)

O mesmo estimador roda sobre RANDOM WALK PURO (drift zero, sem edge)
com amostra grande o bastante para o `n` não mascarar nada. Se o ruído
puro produzir veredito FAVORAVEL, **a rodada sobre dado real é NULA e
não se interpreta** — o estimador está viciado, exatamente como o
anterior. Este portão roda e é reportado JUNTO com o resultado real, no
mesmo relatório, sempre.

Expectativa teórica: sob martingal, pela parada opcional,
E[S_fim − S_τ] = 0. Um estimador correto deve devolver ≈ 0 no ruído.

### Metodologia, fixada ANTES

- População, purga de dia inteiro, pool out-of-sample, regra de entrada:
  IDÊNTICAS ao pré-registro anulado (essa parte não estava errada).
- Lado venda. Feature `z_agf_3`, h=3, threshold 1.4, contrarian.
- Grade X: **a mesma** {40, 60, 80, 100, 120, 150, 200}. Mantida de
  propósito — trocar a grade junto com o estimador tornaria impossível
  distinguir efeito de mudança de grade de efeito de mudança de método.
- n < 30 no ponto → reportado, NÃO interpretado.
- Todos os 7 pontos sempre reportados, nos dois limites de `F`.
- Estatística de UMA amostra contra zero, com bootstrap de bloco por
  pregão inteiro. Significância exige as duas evidências: |t| ≥ limiar
  deflacionado de 7 comparações E IC95 de bloco excluindo zero.
- Reportar também a distribuição de τ (em qual barra da janela o
  cruzamento ocorre) — diagnóstico, não critério.

### CHECAGEM DE PRÉ-VOO (antes de interpretar)

Reconciliar a contagem: a rodada anulada deu 162 operações em 22
pregões, enquanto a análise de MAE de 2026-08-27 falava em 336 gatilhos
em 26 dias. Pode ser só compra+venda somados lá, mas **confirmar, não
assumir** — se a população mudou por outro motivo, nada mais neste
teste é interpretável.

### Critério de decisão (mesma estrutura de sempre)

- **FAVORAVEL a (b)**: existe X\* com remanescente médio negativo e
  significativo nos DOIS limites de `F`, monotonicidade (todos os X > X\*
  também negativos) e n ≥ 30 em X\* e acima.
- **CONTRA (b)**: nenhum X produz remanescente distinguível de zero. O
  stop não detecta nada; só se justifica como (a).
- **INVERTIDO**: remanescente significativamente POSITIVO nos dois
  limites — sair a −X destrói valor. Achado genuíno, registrar; NÃO
  autoriza aumentar posição no adverso (pirâmide, proibida por design).
- **INCONCLUSIVO**: não monotônico, n insuficiente, ou limites de `F`
  com sinais diferentes (aí com escalonamento definido acima).

### Regra de parada

Proibido re-rodar com grade ajustada, threshold, horizonte ou lado
diferentes depois de ver o resultado. INCONCLUSIVO só se continua
acumulando pregões e rodando de novo com a MESMA grade e o MESMO
estimador. Estimador novo exige pré-registro novo — como este.

### Fora deste pré-registro

- Escolha do número final do stop (X\* é candidato, nunca decisão).
- Qualquer implementação em `ea/risco.py`.
- Alvo, em qualquer forma.
- Custo em expectativa do stop-como-(a) — pré-registro separado.
