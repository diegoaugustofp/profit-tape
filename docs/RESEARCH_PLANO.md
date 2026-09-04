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
- [Segunda rodada de quintis — z_agf_3 h=1 passa no IC mas morre pelo custo (2026-08-26)](#segunda-rodada-de-quintis--z_agf_3-h1-passa-no-ic-mas-morre-pelo-custo-2026-08-26)
- [Resultado real do MAE + achado de assimetria compra/venda (2026-08-27)](#resultado-real-do-mae--achado-de-assimetria-compravenda-2026-08-27)
- [CORRECAO CRITICA: mae.py rodava sobre amostra inteira, nao out-of-sample (2026-08-27)](#correcao-critica-maepy-rodava-sobre-amostra-inteira-nao-out-of-sample-2026-08-27)

**z_agf_8 (fluxo UBS) — fechado**
- [FECHADO: z_agf_8 (fluxo UBS) descartado nos dois fronts (2026-08-27)](#fechado-z_agf_8-fluxo-ubs-descartado-nos-dois-fronts-2026-08-27)

**Acoes (VALE3/MGLU3/etc.) — mortas pelo custo**
- [Custo de transacao em ACOES na XP — ponderacao do operador (2026-08-26)](#custo-de-transacao-em-acoes-na-xp--ponderacao-do-operador-2026-08-26)
- [Conclusao final: sinais de acao morrem no teste economico (2026-08-26)](#conclusao-final-sinais-de-acao-morrem-no-teste-economico-2026-08-26)
- [Como calcular o custo real de acoes — planilha da XP + modulo dedicado (2026-08-28)](#como-calcular-o-custo-real-de-ações--planilha-da-xp--módulo-dedicado-2026-08-28)

**Restricao de direcao (venda apenas) — decisao aceita**
- [PRE-REGISTRO: Restricao de direcao — venda apenas (2026-08-27)](#pre-registro-restricao-de-direcao--venda-apenas-2026-08-27)
- [RESULTADO do pre-registro "Restricao de direcao — venda apenas" (2026-08-27)](#resultado-do-pre-registro-restricao-de-direcao--venda-apenas-2026-08-27)

**Rota B — implementada, depois questionada (PENDENTE redesenho)**
- [PRE-REGISTRO: Rota B (payoff fixo, alvo/stop) — preparacao (2026-08-27)](#pre-registro-rota-b-payoff-fixo-alvostop--preparacao-2026-08-27)
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
- [IMPLEMENTADO: `reversao-condicional` — executa o pré-registro (2026-08-29)](#implementado-reversao-condicional--executa-o-pré-registro-2026-08-29)
- [RESULTADO ANULADO: o pré-registro de 2026-08-29 tinha estimador inválido](#resultado-anulado-o-pré-registro-de-2026-08-29-tinha-estimador-inválido)
- [PRE-REGISTRO 2: expectativa remanescente a partir do toque (2026-08-29b)](#pre-registro-2-expectativa-remanescente-a-partir-do-toque-2026-08-29b)
- [PORTAO REPROVOU o desenho do pré-registro 2 (2026-08-29c)](#portao-reprovou-o-desenho-do-pré-registro-2-2026-08-29c)
- ⚠ o pre-registro de 2026-08-29 rodou e o veredito foi ANULADO: o
  estimador tinha tautologia embutida (MAE_intrabar >= perda final,
  por construcao) e devolvia FAVORAVEL sobre ruido puro. Hipotese (b)
  segue SEM RESPOSTA; ver o pre-registro 2.

**Risco (drawdown, VaR/ES, circuit breaker)**
- [DRAWDOWN: desenho da pergunta + pré-voo implementado (2026-08-30k)](#drawdown-desenho-da-pergunta--pré-voo-implementado-2026-08-30k)
- [DECOMPOSIÇÃO RODOU — e a premissa do drawdown caiu (2026-08-31)](#decomposição-rodou--e-a-premissa-do-drawdown-caiu-2026-08-31)
  — ENCERRADO: a premissa (Calmar 0,23) era dado contaminado; sobre
  curated Calmar 4,08. Achado real: stop catastrófico checado só no
  close, três perdas além de 500.
- [STOP CONTÍNUO: pré-voo instrumentado, três regimes de saída (2026-08-31b)](#stop-contínuo-pré-voo-instrumentado-três-regimes-de-saída-2026-08-31b)
  — premissa CONFIRMADA no parquet; instrumento entregue, resultado
  pendente da rodada do Diego. Errata: o antigo "pnl com stop
  hipotético" media o regime contínuo e o rotulava como o atual.
- [PRÉ-REGISTRO: stop contínuo, não-inferioridade (2026-08-31c) — CONGELADO](#pré-registro-stop-contínuo-não-inferioridade-2026-08-31c--congelado)
  — 0/16 marginais positivas (o modo de falha temido NÃO ocorre), mas o
  contínuo dispara onde hoje não dispara (venda 10→16). Critério: IC95
  pareado na venda, limite inferior > −3,0 pts/op.
- [RESULTADO: não-inferioridade deu CONTRA por 0,28 (2026-08-31c2)](#resultado-não-inferioridade-deu-contra-por-028-2026-08-31c2)
  — CONTRA, e o veredito fica. Lição: o gate virava com 2 pregões; o
  limiar foi congelado sem verificar se o instrumento resolvia a
  diferença.
- [PRÉ-REGISTRO: stop contínuo como CONFORMIDADE (2026-08-31d)](#pré-registro-stop-contínuo-como-conformidade-2026-08-31d)
  — aguardando congelamento. Critério determinístico, sem IC. Três termos
  aceitos explicitamente, incluindo efeito de expectativa de sinal
  desconhecido.
- [Curva de patrimonio / drawdown maximo (2026-08-27)](#curva-de-patrimonio--drawdown-maximo-2026-08-27)
- [Risco realizado (VaR/ES) — primeiro passo aplicado do RQ (2026-08-27)](#risco-realizado-vares--primeiro-passo-aplicado-do-rq-2026-08-27)
- [Resultado real do risco-realizado + correcao de bug de exibicao (2026-08-27)](#resultado-real-do-risco-realizado--correcao-de-bug-de-exibicao-2026-08-27)
- [Circuit breaker: com freio vs sem freio, num dia real (2026-08-27)](#circuit-breaker-com-freio-vs-sem-freio-num-dia-real-2026-08-27)
- [Acompanhamento continuo: efeito do circuit breaker com 25 dias (2026-08-28)](#acompanhamento-continuo-efeito-do-circuit-breaker-com-25-dias-2026-08-28)

**Absorcao direcional / barra de tempo (indicador NTSL) — EM ABERTO**
- [ORCAMENTO DE TRIALS: o total real e 492, nao 42 (2026-08-29d)](#orcamento-de-trials-o-total-real-e-492-nao-42-2026-08-29d)
- [PRE-REGISTRO (RASCUNHO, NAO CONGELADO): absorcao direcional em barra de tempo (2026-08-29e)](#pre-registro-rascunho-nao-congelado-absorcao-direcional-em-barra-de-tempo--winfut-1m5m-2026-08-29e)

- [RESULTADO DO PORTAO: passou no criterio congelado, mas o nulo empirico condena o braco de 1m (2026-08-29f)](#resultado-do-portao-passou-no-criterio-congelado-mas-o-nulo-empirico-condena-o-braco-de-1m-2026-08-29f)

- [PORTAO RECALIBRADO: o bloqueio do 1m era artefato meu; e o contador de buracos era falso (2026-08-29g)](#portao-recalibrado-o-bloqueio-do-1m-era-artefato-meu-e-o-contador-de-buracos-era-falso-2026-08-29g)

- [DECISAO DE AMOSTRA: os 25 pregoes ficam, com a truncagem registrada (2026-08-29h)](#decisao-de-amostra-os-25-pregoes-ficam-com-a-truncagem-registrada-2026-08-29h)

- [PRE-REGISTRO 3 (RASCUNHO, NAO CONGELADO): separar falta de poder de ausencia de efeito (2026-08-29i)](#pre-registro-3-rascunho-nao-congelado-separar-falta-de-poder-de-ausencia-de-efeito-2026-08-29i)

- [RESULTADO: CONTRA nas 12 celulas — a absorcao direcional morre nesta forma (2026-08-30)](#resultado-contra-nas-12-celulas--a-absorcao-direcional-morre-nesta-forma-2026-08-30)

- [A FORMULA NAO TEM CAUDA: absorcao_dir e sub-gaussiana por construcao (2026-08-30b)](#a-formula-nao-tem-cauda-absorcao_dir-e-sub-gaussiana-por-construcao-2026-08-30b)

- [ESTADO AO FIM DE 2026-08-30: o que esta aberto](#estado-ao-fim-de-2026-08-30-o-que-esta-aberto)

- [ROTA B: leitura de F pelo tape — a infraestrutura que destrava (2026-08-30c)](#rota-b-leitura-de-f-pelo-tape--a-infraestrutura-que-destrava-2026-08-30c)

- [PRE-REGISTRO 3 DA ROTA B (CONGELADO): expectativa remanescente com F exato (2026-08-30d)](#pre-registro-3-da-rota-b-congelado-expectativa-remanescente-com-f-exato-2026-08-30d)

- [IMPLEMENTADO: remanescente_tape executa o pre-registro 3 (2026-08-30e)](#implementado-remanescente_tape-executa-o-pre-registro-3-2026-08-30e)

- [RESULTADO DA ROTA B: CONTRA — o stop nao detecta reversao (2026-08-30i)](#resultado-da-rota-b-contra---o-stop-nao-detecta-reversao-2026-08-30i)

- [POLITICA DO HISTORICO DO GRAFICO: conjunto de validacao CEGO (2026-08-30j)](#politica-do-historico-do-grafico-conjunto-de-validacao-cego-2026-08-30j)

- [DIAGNOSTICO 2026-08-31: absorcao_dir E desloc_norm disfarcado, e o esforco NAO tem cauda](#diagnostico-2026-08-31-absorcao_dir-e-desloc_norm-disfarcado-e-o-esforco-nao-tem-cauda)

- [TRIAGEM DE FEATURE: a etapa que faltava entre formalizar e pre-registrar (2026-08-31)](#triagem-de-feature-a-etapa-que-faltava-entre-formalizar-e-pre-registrar-2026-08-31)

- [PRE-REGISTRO: ABSORCAO DE BARRA (CONGELADO 2026-08-31)](#pre-registro-absorcao-de-barra-congelado-2026-08-31)

- [AMOSTRA DE DEPURACAO x AMOSTRA DE TESTE (2026-09-02)](#amostra-de-depuracao-x-amostra-de-teste-2026-09-02)

- [QUANDO ABANDONAR UM DESENHO SEM ISSO SER P-HACKING (2026-09-03)](#quando-abandonar-um-desenho-sem-isso-ser-p-hacking-2026-09-03)

**Disciplina/processo do proprio research**
- [Decisoes aprovadas](#decisoes-aprovadas)
- [Pre-requisitos antes de escrever research/](#pre-requisitos-antes-de-escrever-research)
- [Disciplina: quando rodar features vs quando rodar research (2026-08-27)](#disciplina-quando-rodar-features-vs-quando-rodar-research-2026-08-27)

**Outras decisoes (2026-08-22/23, nao encaixam nas categorias acima)**
- [Persistencia de corretora — desenho refinado (ideia do operador, 2026-08-22)](#persistencia-de-corretora--desenho-refinado-ideia-do-operador-2026-08-22)
- [IMPLEMENTADO (2026-08-22) — regras finais do veredito, pos teste de honestidade](#implementado-2026-08-22--regras-finais-do-veredito-pos-teste-de-honestidade)
- [PRIMEIRA RODADA REAL + IDENTIFICACAO DO CLUSTER (2026-08-23)](#primeira-rodada-real--identificacao-do-cluster-2026-08-23)
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

> ⚠ **Parcialmente contaminado (descoberto 2026-08-31).** `mae-analise`
> lia `data/raw`; 12 dos 25 pregões tinham backfill em dobro. As
> conclusões QUALITATIVAS (assimetria compra/venda, MAE p99 > stop)
> foram depois confirmadas sobre curated pela Rota B na fita; os NÚMEROS
> (336 gatilhos, 4,5% batem o stop, medianas 95/120) precisam ser
> refeitos sobre curated antes de qualquer uso.

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

> ⚠ **NÚMEROS CONTAMINADOS (descoberto 2026-08-31).** Esta rodada leu
> `data/raw`, onde 12 dos 25 pregões tinham o backfill entregue DUAS
> vezes (cada negócio em dobro; barras de 120k fechando com metade do
> tempo de mercado). Os +418, Calmar 0,23, 157 operações e o efeito do
> circuit breaker −328 em 7 disparos **não descrevem o sinal**. Rodada
> válida (curated): 99 ops, +6356, Calmar 4,08, 4 disparos. Ver
> "DECOMPOSIÇÃO RODOU" de 2026-08-31.

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

> **CONGELADO em 2026-08-29 pelo operador**, antes de qualquer linha de
> código do estimador novo e antes de qualquer contato com o dado.
> Ficam fixados: o estimador (remanescente a partir de τ), a medição
> BRUTA, os dois limites de `F` com a leitura e o escalonamento, a
> grade, o portão de honestidade, a checagem de pré-voo, o critério de
> decisão e a regra de parada. Alteração de qualquer um exige
> pré-registro NOVO, com seção e data próprias — não editar esta seção.
>
> Precedente registrado junto: o pré-registro anterior também estava
> congelado e ainda assim teve o RESULTADO anulado, porque o defeito
> era do estimador e o argumento da anulação era *a priori*. Congelar
> protege contra ajuste oportunista de critério; **não** é certificado
> de que o método é válido. O portão de honestidade existe para cobrir
> exatamente essa lacuna.

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

## PORTAO REPROVOU o desenho do pré-registro 2 (2026-08-29c)

O portão de honestidade rodou **antes de qualquer contato com o dado
real** — e reprovou o próprio estimador que o pré-registro 2 congelou.
Nenhum número real foi olhado. Desta vez o defeito foi pego na hora
certa.

### O que o ruído puro devolveu

Random walk puro, drift zero, caminho contínuo, escala calibrada,
n≈1.400 por ponto:

    X     n     rem PESSIMISTA   t      rem OTIMISTA   t
    40   1362      +32,98      13,04       -7,21     -2,64
    100   734      +30,43      10,99       -5,51     -1,78
    200   162      +30,43       8,30       -1,83     -0,43

    VEREDITO SOBRE RUIDO: INCONCLUSIVO POR PREENCHIMENTO

### O achado: o limite "pessimista" não é um limite

Sobre dado sem edge nenhum, o limite pessimista devolve **+28 a +33
pontos, com t entre 8 e 13**. Não é ruído em torno de zero: é viés
estrutural, de magnitude comparável a um terço da amplitude média da
barra.

A causa é a mesma família do erro anterior, espelhada: `F_pessimista` é
o **extremo** da barra de cruzamento. Selecionar num extremo garante
que o resto do caminho pareça favorável — o preço esteve no pior ponto
da barra e o fechamento quase sempre volta dali. O estimador anterior
condicionava no extremo e media até o fim; este mede A PARTIR do
extremo. Os dois selecionam no mesmo lugar.

O limite otimista sai em -2 a -7 pts, viés pequeno e na direção
prevista (overshoot do cruzamento). É o único dos dois que chega perto
de calibrado.

### Consequência sobre o critério congelado

O veredito sobre ruído foi INCONCLUSIVO POR PREENCHIMENTO — que, no
critério congelado, **manda construir a leitura do tape trade a trade**.
Ou seja: o ruído sozinho dispara uma escalada de infraestrutura. O
gatilho de escalonamento do pré-registro 2 é inválido.

### O portão foi endurecido (e por quê)

O pré-registro 2 escreveu o portão como "reprova se der FAVORAVEL".
Estreito demais, como este resultado mostrou. Um estimador calibrado
tem que devolver **CONTRA (b)** — "não há nada aqui" — quando de fato
não há nada. Qualquer outro veredito sobre ruído puro é reprovação.
`portao_de_honestidade()` implementa esse critério mais duro.

### Dois defeitos meus, corrigidos no caminho

1. **Gerador de ruído incoerente**: a primeira versão sorteava a
   amplitude da barra por fora do passeio, produzindo barras cujo high
   jamais foi visitado por caminho nenhum. Um portão só vale se o ruído
   for um caminho de preço de verdade. Corrigido com sub-passos dentro
   da barra e extremos reais.
2. **Razão amplitude/desvio medida através da virada de pregão**, o que
   inflava o denominador e fazia a razão parecer menor. Corrigido para
   medir dentro do dia.

### Estado da hipótese (b)

**Segue sem resposta.** Não foi refutada nem confirmada. O que existe é
o segundo estimador inválido em dois — mas este morreu antes de tocar
o dado, que é exatamente o que o portão existe para fazer.

### Direção para o pré-registro 3 (ainda NAO pré-registrado)

Duas correções apontam para o mesmo lugar:

- **Descartar o limite pessimista.** Não é conservador, é enviesado.
  `F` = nível do stop é o único dos dois quase calibrado, e é também o
  que um stop de mercado de fato consegue em instrumento líquido.
- **Usar o ruído como NULO EMPIRICO, não zero.** O viés residual do
  limite otimista (-2 a -7 pts) é conhecido e mensurável. Em vez de
  supor que o estimador é não-enviesado, testar o real CONTRA a
  distribuição gerada por ruído com a mesma geometria de barra. Isso
  neutraliza qualquer viés estrutural remanescente, seja ele qual for.

Isto muda estimador e critério, então exige pré-registro novo — não se
edita o congelado.

## ORCAMENTO DE TRIALS: o total real e 492, nao 42 (2026-08-29d)

Este documento registrava "42 trials, limiar 2.209" desde 2026-08-23 e
nunca foi atualizado depois disso. O `data/research/trials.json` real
(lido do arquivo do operador em 2026-08-29) fecha em **492**, e
reconcilia exatamente:

    WINFUT 2026-08-23 (14 features x 3 horizontes)          42
    WINFUT 2026-08-23 (+ z_fluxo_nacional)                  45
    WINFUT 2026-08-26                                       45
    Varredura de 8 simbolos 2026-08-26 (WDOFUT, PETR4,
      VALE3, ITUB4, BOVA11, BBAS3, MGLU3, WEGE3)           360
                                                          ----
                                                           492

**73% do orcamento estatistico do projeto foi gasto numa varredura de
oito simbolos que rodou em ~1 minuto** (timestamps 02:04:35 a 02:05:54).
O contador esta CERTO em cobrar por ela: os oito foram olhados
procurando algum passar, entao o maximo foi selecionado entre todos —
e' exatamente a situacao que o teorema da estrategia falsa descreve.

### Consequencia sobre a barra

    limiar_z(492) = 3,048        limiar_z(504) = 3,055

Mas o limiar em Z nao e' a barra que uma feature enfrenta: a barra e'
`t_critico(limiar_z, folds-1)`, e a correcao de Student domina quando ha
poucos folds.

    folds     t_critico a 504 trials
      5              6,20
      8              4,56
     10              4,16
     12              3,93

Na rodada de 42 trials a barra era 3,31 com 5 folds. Hoje, com 5 folds,
seria 6,20 — inatingivel para qualquer feature de microestrutura.

Como `gerar_folds` produz `(n_dias - 3) / 2` folds (treino_min=3,
teste_dias=2), isso vira uma condicao sobre DADO, nao sobre criterio:
abaixo de ~23 pregoes no arquivo de features, gastar trial em qualquer
hipotese nova compra um `descarta` quase garantido.

### O que NAO se conclui daqui

Nao se zera, nao se particiona por simbolo, nao se afrouxa a regra. O
contador existe para nunca esquecer (`trials.py`: "sem persistencia, o
contador zeraria a cada rodada e o pesquisador se enganaria
honestamente"). O registro aqui e' de LICAO: uma varredura ampla e'
barata em tempo de maquina e cara em orcamento estatistico, e o preco
dela e' pago por todas as perguntas futuras. Varredura ampla, daqui em
diante, e' decisao consciente — nao "so' rodar em todos os simbolos para
ver".

## PRE-REGISTRO (RASCUNHO, NAO CONGELADO): absorcao direcional em barra de tempo — WINFUT 1m/5m (2026-08-29e)

> **CONGELADO em 2026-08-29 pelo operador**, antes de qualquer linha de
> codigo do teste e antes de qualquer contato com o dado. Hipotese,
> features, controles, timeframes, horizontes, janela de z, criterio de
> decisao e regra de parada estao fixados a partir daqui. Alteracao de
> qualquer um desses itens exige pre-registro NOVO, com secao propria e
> data propria — nao editar esta secao.
>
> O PORTAO DE HONESTIDADE continua bloqueante: congelar protege contra
> ajuste de criterio, nao certifica que o metodo e' valido (licao de
> 2026-08-29c, onde um pre-registro congelado e aparentemente rigoroso
> foi reprovado pelo proprio portao).

### Motivacao

Leitura visual do operador sobre grafico intradiario: existe uma barra
em que a agressao vai fortemente para um lado e o preco NAO acompanha —
a ponta passiva absorve. O objetivo final e' um indicador NTSL plotado
ao vivo no Profit Chart e, depois, um robo que entra no fechamento da
barra com stop no extremo dela. A pesquisa acontece AQUI (tape completo,
IC, trials contados); o NTSL e' camada de visualizacao e execucao, nao
de calibracao.

### O que ja foi refutado, e por que isto nao e' repeticao

`z_absorcao` e `z_imbalance` ja foram avaliados em h {1,3,10} nas
rodadas de 2026-08-23 e 2026-08-26 (constam de `trials.json`) e sairam
`descarta`. Este pre-registro difere em tres pontos, declarados ANTES:

1. **Barra de TEMPO**, nao barra de volume. Toda avaliacao anterior
   rodou sobre volume bars com relogio de agressao — que e' justamente
   o que apaga a estrutura de 1m/5m que a hipotese descreve.
2. **Direcional, nao crua.** `absorcao = vol_agr / range_ticks` nao tem
   lado; o mecanismo hipotetizado exige o lado.
3. A leitura visual e' sobre barras extremas, nao sobre associacao
   monotona em todas as barras.

Sobre o ponto 3, explicitamente: o IC e' um teste FRACO para efeito
concentrado em cauda, e mesmo assim ele fica sendo o portao. Resgatar
por quintil um sinal que o IC reprovou seria mover a trave depois do
resultado. Se o IC reprovar, a hipotese morre nesta forma.

### Features avaliadas (aprovadas pelo operador, 2026-08-29)

Em barra de tempo, todas ja na escala [-1, 1], sem parametro livre:

    imbalance    = (vol_buy - vol_sell) / vol_agr      [ja existe]
    desloc_norm  = (close - open) / (high - low)       [novo]
    absorcao_dir = imbalance - desloc_norm             [PRIMARIA]

A frase inteira do mecanismo: *o esforco foi para um lado e o preco
fechou para o outro*. Positivo = compradores agrediram e nao levaram,
logo previsao de QUEDA (IC esperado NEGATIVO).

    1. z_absorcao_dir    PRIMARIA
    2. z_desloc_norm     CONTROLE — reversao pura
    3. z_imbalance       CONTROLE — fluxo puro

Os controles existem porque `desloc_norm` isolado e' um proxy conhecido
de reversao de curtissimo prazo: sem eles, um `segue` da primaria nao
distinguiria absorcao de reversao simples com um passo a mais.

Timeframes: 1m e 5m. Horizontes CASADOS EM TEMPO DE RELOGIO, para que a
comparacao entre timeframes seja limpa:

    5m -> h {1, 3}      1m -> h {5, 15}      (ambos = 5 e 15 minutos)

### Isolamento em relacao a barra de volume (operador, 2026-08-29)

Instrucao explicita: a estrategia e' validada EM BARRA DE TEMPO, sem
misturar com o que foi medido em barra de volume. Consequencias
operacionais, nao apenas retoricas:

- O pipeline de features de tempo gera SOMENTE as tres colunas
  pre-registradas (`absorcao_dir`, `desloc_norm`, `imbalance`). Se
  gerasse o conjunto completo, o `research` — que avalia TODA coluna
  `z_` presente — cobraria 14 features x 2 horizontes = 28 trials por
  timeframe em vez de 6, estourando este pre-registro e reintroduzindo
  justamente as features de barra de volume que se quer manter fora.
- Arquivo de saida separado (`data/features_tempo/sym=X/tf=Nm/`), nunca
  sobrescrevendo `data/features/`.
- Os resultados de barra de volume NAO entram como evidencia a favor ou
  contra esta hipotese; entram so' como o registro de que a versao
  crua de `absorcao` ja foi tentada em outro regime de amostragem.

O que NAO muda: o contador de trials e' UM so'. Ele mede quantas vezes
se olhou, nao em qual tipo de barra. Barra de tempo nao abre orcamento
novo.

### Custo: CONSOME trial — 12

3 features x 2 timeframes x 2 horizontes. Total passaria de 492 para
504 (`limiar_z` 3,048 -> 3,055).

### PORTAO DE HONESTIDADE (bloqueante, antes de qualquer dado real)

Exigido pela licao de 2026-08-29c: dois estimadores morreram seguidos
por SELECAO NUM EXTREMO. `desloc_norm` seleciona pela posicao do
fechamento dentro dos proprios extremos da barra — mesma familia.

O vies concreto tem nome e direcao previsivel: ruido de microestrutura
no fechamento. Barra que fecha na minima tem probabilidade elevada de
ter o ultimo negocio agredido na venda; o fechamento seguinte tende a
voltar do bid. Isso gera autocorrelacao negativa MECANICA entre
`desloc_norm` e `ret_fut_h` — IC negativo, sem edge nenhum, na direcao
exata que a hipotese preve. Em 1m o efeito e' proporcionalmente maior
que em 5m (tick de 5 pontos no WIN), o que contaminaria TAMBEM a
comparacao entre timeframes.

Procedimento do portao:

- Gerar random walk com drift zero, caminho continuo, GRANULARIDADE DE
  TICK real (5 pts no WIN) e bounce bid-ask explicito. Sem o bounce o
  portao nao testa o vies que importa.
- Montar barras de tempo 1m e 5m sobre esse caminho, calcular as tres
  features, rodar o pipeline de IC COMPLETO.
- **Exigencia**: veredito `descarta` nas 12 celulas. Qualquer `segue`
  sobre ruido puro REPROVA o desenho, antes de gastar trial.
- Reportar tambem o IC medio de cada controle sobre ruido: se
  `z_desloc_norm` sair com IC sistematicamente negativo mesmo saindo
  `descarta`, o vies existe e precisa entrar como NULO EMPIRICO (mesma
  correcao apontada em 2026-08-29c), nao como zero.

Reprovacao no portao exige pre-registro NOVO. Nao se edita este.

### Condicao de dado, fixada agora

Rodar apenas com **folds >= 10** no arquivo de features (equivale a
>= 23 pregoes). Nao e' baixar a barra: e' exigir dado suficiente para
que a correcao de Student nao seja dominada por 4 graus de liberdade.
Com 5 folds a barra e' 6,20 e o resultado seria `descarta` por falta de
poder, gastando 12 trials para nao aprender nada.

### Metodologia, fixada ANTES

- Maquinario padrao: `retornos.py` (purga estrutural de dia inteiro),
  `walkforward.gerar_folds`, `ic.avaliar`, veredito de tres barras
  (magnitude / estabilidade / direcao), `inconclusivo` se folds < 4.
- **Janela de z-score casada em tempo de relogio, nao em barras**: se 5m
  usa 50 barras (250 min), 1m usa 250 barras. Fixar `n` igual nos dois
  tornaria a comparacao entre timeframes sem sentido — a normalizacao
  estaria medindo passados de duracao diferente.
- Barra sem agressao nenhuma no periodo e' DESCARTADA, nao preenchida:
  barra preenchida tem `range = 0` e `vol_agr = 0`, e produziria
  `desloc_norm` degenerado.
- `open/high/low/close` SO de agressao (leilao e RLP fora), igual a
  convencao ja travada em `FEATURES.md`. Guarda: `high == low` =>
  `desloc_norm := 0`.
- Reportar as 12 celulas, inclusive as que nao derem nada.

### Criterio de decisao, definido ANTES de ver qualquer numero

**FAVORAVEL** — as quatro condicoes JUNTAS:
  1. `z_absorcao_dir` sai `segue` em pelo menos um par (timeframe, h);
  2. o sinal do IC e' NEGATIVO (direcao prevista pela convencao);
  3. `|IC|` da primaria > `|IC|` de AMBOS os controles no mesmo par;
  4. mesmo sinal nos DOIS horizontes daquele timeframe.

**CONTRA**: nenhuma celula sai `segue`, ou sai `segue` com sinal
POSITIVO. Sinal positivo seria continuacao (momentum de
microestrutura) — achado legitimo, registrado, mas NAO autoriza
inverter o lado da operacao sem pre-registro novo.

**INCONCLUSIVO**: sai `segue` sem superar os controles (o efeito e'
reversao ou fluxo, nao absorcao), ou folds < 4.

### Regra de parada

Proibido re-rodar com outra definicao de `absorcao_dir`, outro
timeframe, outro horizonte ou outra janela de z depois de ver o
resultado. `INCONCLUSIVO` so' permite acumular mais pregoes e rodar de
novo com a MESMA grade.

### Sobre 1m vs 5m

Com uma rodada so', a comparacao e' DESCRITIVA. Se um timeframe passar e
o outro falhar nos dois horizontes, isso e' observacao registrada, nao
conclusao de que um e' melhor. A leitura visual do operador continua
sendo a hipotese, nao o resultado.

### Pre-requisito de engenharia (nao faz parte da hipotese)

Construtor de barra de TEMPO em `features/bars.py` — hoje so' existe
volume bar. Herda as regras ja travadas: nao atravessa dia, parcial do
fim de pregao descartada, RLP/leilao atribuidos a barra mas fora de
`vol_agr`. Categoria `features`: NAO consome trial. Conferencia a mao de
um exemplo minimo antes dos testes automatizados (regra 4 da skill
`profit-tape-disciplina`).

### Explicitamente FORA deste pre-registro

- Stop na maxima/minima da barra, R:R, e qualquer regra de saida.
- Custo de transacao e viabilidade economica.
- Qualquer linha de NTSL.
- Qualquer coisa em `ea/`.

Tudo isso so' existe se H sobreviver ao portao E ao IC.

## RESULTADO DO PORTAO: passou no criterio congelado, mas o nulo empirico condena o braco de 1m (2026-08-29f)

Rodado ANTES de qualquer contato com dado real, com o limiar que o teste
real vai enfrentar (`trials.json` = 492, + 12 desta hipotese => limiar_z
3,055). Nenhum trial gasto. Comando: `profit-tape portao-absorcao`.

### O binario: PASSOU

As 12 celulas da semente congelada sairam `descarta`. Pelo criterio
congelado, o desenho esta liberado.

### O nulo empirico: o binario passou por sorte da semente

Vinte tapes independentes, mesmo gerador. IC medio sob RUIDO PURO:

    tf  feature          h    ic_ruido   p05       p95      segue/20
    1m  z_absorcao_dir   5    +0,01793  +0,00586  +0,03188     0
    1m  z_absorcao_dir  15    +0,01376  -0,00418  +0,02702     0
    1m  z_desloc_norm    5    -0,02565  -0,03667  -0,01266     2
    1m  z_desloc_norm   15    -0,01587  -0,02954  -0,00035     0
    1m  z_imbalance      5    -0,02300  -0,03960  -0,00758     4
    1m  z_imbalance     15    -0,01361  -0,03156  +0,00698     2
    5m  z_absorcao_dir   1    +0,01486  -0,02105  +0,03597     0
    5m  z_absorcao_dir   3    +0,01316  -0,02130  +0,03526     0
    5m  z_desloc_norm    1    -0,01776  -0,03995  +0,01150     0
    5m  z_desloc_norm    3    -0,01438  -0,03372  +0,01660     0
    5m  z_imbalance      1    -0,01503  -0,05445  +0,03736     0
    5m  z_imbalance      3    -0,00480  -0,04277  +0,03434     0

Tres leituras, todas previstas por escrito antes de rodar:

1. **O vies existe e tem a direcao prevista.** `desloc_norm` e
   `imbalance` tem IC NEGATIVO sistematico sob ruido — bounce bid/ask no
   fechamento, exatamente o mecanismo antecipado no pre-registro.
2. **O vies e' maior em 1m que em 5m.** Em 1m as bandas p05-p95 de
   `z_desloc_norm` h=5 e `z_imbalance` h=5 NAO contem zero. Em 5m todas
   contem. O tick e' o mesmo nos dois; a amplitude da barra e' menor em
   1m (mediana 3 ticks contra 7), entao o bounce pesa proporcionalmente
   mais.
3. **Sob ruido puro, o criterio devolve `segue`**: 8 celulas em 240 (20
   tapes x 12), TODAS em 1m e TODAS nos dois controles. `z_imbalance`
   h=5 sozinho deu `segue` em 4 de 20 tapes — 20% de falso positivo onde
   o criterio deveria dar quase nada. A semente congelada calhou de ser
   uma das limpas.

### Consequencia sobre o criterio congelado

O braco de **5m esta limpo**: zero `segue` em 120 celulas de ruido, todas
as bandas contendo zero. Roda como congelado.

O braco de **1m esta contaminado**, e de um jeito que quebra duas partes
do criterio congelado, nao uma:

- A condicao 2 (IC negativo) confunde sinal com bounce: o nulo de
  `absorcao_dir` em 1m e' POSITIVO (+0,018), nao zero.
- A condicao 3 (primaria supera ambos os controles em |IC|) compara
  contra controles que ja carregam |IC| ~0,023-0,026 so' de artefato.

Nao se conserta isso editando o congelado. O 1m exige pre-registro NOVO,
com o nulo empirico como base de comparacao no lugar de zero — que e'
literalmente a correcao que 2026-08-29c ja tinha apontado.

### Observacao a NAO transformar em conclusao

A intuicao visual do operador era que sinais de 1m sao "menos confiaveis"
que os de 5m. O portao mostra que em 1m a MEDICAO e' enviesada. Sao duas
afirmacoes diferentes e uma nao prova a outra — o vies de medicao nao diz
nada sobre existir ou nao sinal em 1m. Registrado como coincidencia
interessante, nao como validacao da intuicao.

### Estado

- Braco 5m: liberado para gastar 6 trials (limiar 3,055; com 25 pregoes
  sao 11 folds, `t_critico` ~4,03).
- Braco 1m: BLOQUEADO ate pre-registro novo.
- Trials gastos ate aqui nesta hipotese: ZERO.

## PORTAO RECALIBRADO: o bloqueio do 1m era artefato meu; e o contador de buracos era falso (2026-08-29g)

`features-tempo WINFUT --segundos 300` rodou sobre os 25 pregoes reais
(24/07 a 27/08). Cinco dos seis checks de pre-voo bateram. O sexto
derrubou a calibracao do portao, e a investigacao dos dois pregoes
curtos derrubou um contador.

### Geometria real vs geometria simulada

    real (5m)     : range mediano 35 ticks, 113 barras/dia,
                    ~42.000 negocios por barra
    simulado (5m) : range mediano  7 ticks,  96 barras/dia,
                    ~100 negocios por barra

O gerador de ruido de 2026-08-29f errou a escala de negocios por barra
em mais de duas ordens de grandeza, e por consequencia a amplitude da
barra por um fator de 5. Como o bounce bid/ask e' de 1 tick FIXO, o vies
que ele injeta escala com `1 / amplitude` — numa barra de 7 ticks ele
pesa cinco vezes mais que numa de 35.

Isto foi previsto por escrito ANTES de rodar (docstring de
`gerar_tape_ruido`: "a amplitude efetivamente obtida e' reportada pelo
portao, para conferencia — nao se confia no default"). O que nao estava
previsto era o tamanho do erro.

### Portao rerodado com a geometria real (tpm=600, prob_passo=0,08)

Calibracao escolhida por reproduzir a geometria OBSERVADA (5m: 33 ticks
contra 35 reais; 1m: 15 ticks, coerente com os 35 do 5m divididos por
raiz de 5), nao por produzir algum resultado.

    zero `segue` em 156 celulas (12 congeladas + 144 de nulo empirico)
    todos os nulos empiricos em torno de zero, bandas p05-p95 contendo
    zero em TODAS as 12 celulas

O maior |ic_ruido_medio| caiu de 0,0257 para 0,0063.

### Consequencia: o bloqueio do braco de 1m e' REVOGADO

O bloqueio de 2026-08-29f dizia: nulo de `absorcao_dir` em 1m positivo
(+0,018) quebrando a condicao 2, e controles com |IC| ~0,025 de artefato
quebrando a condicao 3. Com geometria realista, nada disso sobrevive —
os nulos de 1m ficam em 0,002 a 0,003, com bandas contendo zero.

O bloqueio era artefato de calibracao, nao propriedade do desenho. Nao
foi o pre-registro que mudou; foi o instrumento que estava errado e foi
consertado. Registrado assim, e nao apagado, porque um portao que so'
aparece no historico quando confirma o que se queria nao e' portao.

CONDICAO para o 1m rodar: confirmar a geometria real de 1m com
`features-tempo WINFUT --segundos 60`. Os 15 ticks sao PREVISAO do
simulador, nao medicao. Se o 1m real vier bem abaixo (ex.: 6-8 ticks), a
contaminacao volta e o bloqueio volta com ela.

### BUG: `_contar_buracos` era falso por construcao

`buracos: 0` na saida real nao significava nada. `atribuir_barras_tempo`
renumerava os baldes densamente com `np.unique(return_inverse=True)`, o
que APAGA os baldes vazios; `_contar_buracos` media `diff(bar_id)` sobre
o resultado ja achatado e devolvia zero SEMPRE, para qualquer entrada.

Achado ao investigar dois pregoes curtos no log:

    2026-07-31 : 2.492.067 negocios, 71 barras (contra 113)
    2026-08-25 : 1.474.049 negocios, 54 barras (contra 113)

Corrigido: `bar_id` passa a ser o indice do balde RELATIVO ao primeiro
balde do dia, preservando os vazios. Conferido a mao (baldes 0, 1 e 12
=> 10 buracos) antes do teste automatizado.

Isso importa para o pre-registro porque o horizonte e' definido em tempo
de RELOGIO: com buraco no meio do pregao, "3 barras a frente" deixa de
ser "15 minutos a frente".

### DECISAO PENDENTE, a tomar ANTES do research (nao depois)

Os dois pregoes curtos precisam ser classificados por INTEGRIDADE DE
CAPTURA — recorder fora do ar, quarentena, incidente registrado — e nao
por resultado. Excluir dia depois de ver o IC seria escolha de amostra
pelo resultado, exatamente o que o resto do metodo existe para impedir.
Rerodar `features-tempo` com o contador corrigido diz quantos buracos
existem de fato em cada um.

## DECISAO DE AMOSTRA: os 25 pregoes ficam, com a truncagem registrada (2026-08-29h)

Tomada pelo operador ANTES de qualquer rodada de `research` — nenhum IC
foi calculado ate aqui. Registrar antes e' o ponto: excluir pregao depois
de ver o resultado seria escolher amostra pelo resultado.

### O que a geometria mostrou

    dia          barras 5m   x5    barras 1m
    2026-07-31       71     355       351
    2026-08-25       54     270       267
    (normal)        113     565       ~562-565

Os numeros batem, e o contador de buracos corrigido (2026-08-29g) fecha a
questao: `buracos = 0` no 5m e 6 em 13.568 barras no 1m. Os dois pregoes
curtos sao **TRUNCADOS, nao esburacados** — a captura pegou um bloco
CONTIGUO e parou.

Isso e' o cenario benigno: nenhum `ret_fut_h` do 5m atravessa lacuna de
captura, e no 1m sao 6 minutos ausentes (0,04%). A premissa de tempo de
RELOGIO do horizonte se sustenta.

### Incidentes correlatos (documentados pelo operador em v1.16)

`docs/OPERACAO.md` registra o incidente de 2026-08-25: a tarefa agendada
disparou as 08:50 e o processo CRASHOU (exit code 1, causa raiz nunca
confirmada). Isso torna 25/08 um PREFIXO — capturou da abertura ate o
crash. O operador lembra de um segundo incidente, de tipo oposto (record
que nao iniciou e perdeu a manha inteira), que seria um SUFIXO, mas sem
certeza de que corresponde a 31/07.

Se o par for esse, a amostra tem um pregao so'-manha e um so'-tarde, e o
desvio de composicao intradiaria se compensa em parte no agregado. Isso
e' INFERENCIA a partir dos incidentes, nao medicao — resolvida com um
`groupby` de primeiro/ultimo `ts_close` por dia, se valer a pena depois.

### Decisao

**Manter os 25 pregoes.** Justificativas, todas registradas antes:

1. As barras que existem sao integras — o truncamento nao corrompe barra
   nenhuma, so' reduz a contagem do dia.
2. A sequencia e' contigua, entao nenhum retorno atravessa lacuna.
3. Sao 2 pregoes em 25.
4. Excluir mudaria os folds de 11 para 10 (`t_critico` de 4,03 para
   4,16). Nao e' esse o motivo da decisao, mas fica registrado que o
   efeito foi conhecido ANTES e nao decidiu nada.

RESSALVA que acompanha a decisao: dois dos folds tem composicao
intradiaria diferente dos demais. Se o resultado final vier
INCONCLUSIVO, isto e' uma das explicacoes candidatas — registrada agora,
para nao ser inventada depois.

### Nota estrutural do operador

"Da forma como montamos a captura de dados pode haver perda de dados."
Isso vale para toda amostra futura, nao so' para estes dois dias: a
captura nao tem garantia de completude, e o pipeline precisa CONTINUAR
reportando cobertura por pregao em vez de assumi-la. O contador de
buracos e a contagem de barras por dia no log existem exatamente para
isso — e so' passaram a valer alguma coisa depois do bug de 2026-08-29g.

## Deflacao consistente quando a hipotese roda em duas invocacoes (2026-08-29h)

O pre-registro de 2026-08-29e gasta 12 trials: 6 no arquivo de 5m e 6 no
de 1m. Sao dois arquivos, logo duas chamadas de `research`. Sem cuidado,
a rodada que corresse PRIMEIRO seria julgada contra 498 trials e a
segunda contra 504 — o mesmo pre-registro com duas barras diferentes, e
um desconto para quem correu na frente.

`research --trials-previstos 504` deflaciona contra o total
PRE-REGISTRADO nas duas chamadas. O contador em disco continua somando
normalmente; muda so' contra que numero se deflaciona, nunca quanto se
cobra. E so' pode ENDURECER: valor menor que o total real e' ignorado
(mesma logica do piso de 1,96 em `limiar_deflacionado` — deflacao nunca
baixa a barra).

## PRE-REGISTRO 3 (RASCUNHO, NAO CONGELADO): separar falta de poder de ausencia de efeito (2026-08-29i)

> **CONGELADO em 2026-08-29 pelo operador**, ANTES de qualquer rodada de
> `research` sobre barra de tempo — zero trial gasto ate aqui, nenhum IC
> calculado. O limiar de 0,85, a exigencia de opt-in e o criterio
> revisado estao fixados a partir daqui; alteracao exige pre-registro
> novo, com secao e data proprias.
>
> O momento de escrever isto era este: notar depois de ver um `CONTRA`
> que "na verdade era falta de poder" seria mover a trave.

### O problema que este pre-registro resolve

O operador decidiu (2026-08-29) rodar agora e ir acumulando pregoes.
Isso colide com a regra de parada congelada em 2026-08-29e, que autoriza
continuar apenas se o veredito for `INCONCLUSIVO` — nao apos um
`CONTRA`.

E `CONTRA` e' o desfecho mais PROVAVEL da rodada 1, mesmo se o sinal
existir: com 25 pregoes sao 11 folds e `t_critico` 4,03. Ou seja, o
cenario mais provavel e' exatamente o que a regra congelada trata como
fim de linha.

Isso nao e' defeito do pre-registro anterior; e' o preco de congelar. A
correcao legitima e' um pre-registro NOVO, escrito antes do dado.

### A distincao, e por que ela e' aritmetica

O veredito tem tres barras cumulativas:

    1. MAGNITUDE    |IC| >= 2/sqrt(n_obs)
    2. ESTABILIDADE |t entre folds| >= t_critico(limiar, k-1)
    3. DIRECAO      mesmo sinal em >= 70% dos folds

Das tres, ESTABILIDADE e' a UNICA cujo limiar depende do numero de
folds: `t_critico` cai de 4,03 (11 folds) para 3,50 (23 folds) sem que
nada no dado mude. Uma celula que passa em 1 e 3 e falha SO em 2 esta
falhando na unica barra sensivel ao tamanho da amostra.

### A porta dos fundos que isso abriria, e como ela e' fechada

`t = IC_medio / (desvio_entre_folds / sqrt(k))`. Um |t| baixo vem de
poucos folds OU de desvio alto entre folds — e desvio alto e'
instabilidade REAL, nao falta de poder. A barra de direcao a 70% nao
separa os dois: com 11 folds, 8 sinais iguais passa, e 8-de-11 e'
compativel com moeda honesta (p = 0,11).

**Regra escolhida (opcao (a), operador, 2026-08-29)**: promover
`descarta` a `inconclusivo` exige consistencia de sinal >= **0,85**,
nao os 0,70 de `segue`. Quem tem sinal real e so' falta amostra tende a
ter direcao muito consistente; quem tem desvio alto entre folds, nao.

Implicacao sob ruido puro (moeda honesta), calculada ANTES:

    folds   minimo a 85%   p 1-lado
      11        10/11       0,00586
      13        12/13       0,00171
      16        14/16       0,00209
      18        16/18       0,00066
      23        20/23       0,00024

### Duas propriedades registradas antes, uma boa e uma ruim

BOA: o criterio APERTA conforme os folds crescem (de p=0,006 para
p=0,0002). Isso e' conservador na direcao certa — a porta existe para
falta de amostra, e estreita a medida que a amostra deixa de faltar.

RUIM: a porta pode fechar sobre um sinal real, fraco e persistente, cuja
consistencia de sinal nao sobe com o tamanho da amostra. Este e' um
custo aceito conscientemente, nao um efeito colateral descoberto depois.

### Criterio revisado, na integra

    segue        : as tres barras (inalterado)
    inconclusivo : folds < 4 ou t incalculavel (inalterado)
                   OU passa MAGNITUDE, falha ESTABILIDADE, e
                      consistencia_sinal >= 0.85          [NOVO]
    descarta     : qualquer outro caso

`segue` nao muda em nada. A regra nova so' pode mover celulas de
`descarta` para `inconclusivo` — nunca para `segue`, nunca o contrario.

### Retrocompatibilidade: OPT-IN obrigatorio

A regra NAO pode alterar `_veredito` para todo mundo. O historico de
barra de volume (492 trials, incluindo os dois `segue` de 2026-08-23)
foi julgado pela regra antiga; mudar a funcao reclassificaria
retroativamente celulas que ninguem rerodou. Entra como parametro
`promover_por_poder`, default `False`, com teste explicito provando que
sem ele o comportamento antigo fica IDENTICO (regra 5 da disciplina — e
a mesma classe de falha silenciosa que o `extra="forbid"` das configs do
EA fechou).

O relatorio precisa registrar QUAL regra foi usada, para que uma leitura
futura nao confunda `inconclusivo` das duas origens.

### O que este pre-registro NAO autoriza

- Nao afrouxa `segue`. Nenhuma celula passa a "valer" por causa disto.
- Nao autoriza rodar mais vezes que a cadencia acordada: rodada nova so'
  com pregoes novos suficientes (regra 2 da disciplina — semanal, nao
  diaria; com 2 pregoes novos paga-se 12 trials por ~8% de amostra).
- Nao muda a grade, os horizontes, a janela de z, nem as tres features
  do pre-registro de 2026-08-29e.
- `INCONCLUSIVO` continua significando "nao decide nada". Nao e'
  resultado parcial a favor.

## RESULTADO: CONTRA nas 12 celulas — a absorcao direcional morre nesta forma (2026-08-30)

Executado o pre-registro de 2026-08-29e com o criterio revisado de
2026-08-29i. Duas invocacoes, `--trials-previstos 504` nas duas,
`--promover-por-poder` nas duas. Trials: 492 -> 498 -> 504.

### 5m (h 1,3) — relatorio 20260830_123543

    feature          h   IC medio   desvio     t    consist.  veredito
    z_desloc_norm    1    0.0246    0.0372   2.19     0.64    descarta
    z_desloc_norm    3    0.0325    0.0790   1.36     0.73    descarta
    z_imbalance      3    0.0024    0.0787   0.10     0.45    descarta
    z_imbalance      1   -0.0069    0.0516  -0.44     0.55    descarta
    z_absorcao_dir   3   -0.0417    0.0791  -1.75     0.64    descarta
    z_absorcao_dir   1   -0.0342    0.0371  -3.06     0.73    descarta

### 1m (h 5,15) — relatorio 20260830_123558

    z_desloc_norm   15    0.0039    0.0302   0.43     0.64    descarta
    z_desloc_norm    5    0.0030    0.0244   0.41     0.73    descarta
    z_absorcao_dir  15   -0.0097    0.0316  -1.01     0.73    descarta
    z_imbalance      5   -0.0076    0.0245  -1.03     0.82    descarta
    z_imbalance     15   -0.0087    0.0237  -1.21     0.64    descarta
    z_absorcao_dir   5   -0.0097    0.0247  -1.31     0.82    descarta

### Veredito pelo criterio congelado: CONTRA

Nenhuma celula saiu `segue`. A porta do PRE-REGISTRO 3 nao abriu: a
maior consistencia foi 0,82, abaixo dos 0,85 exigidos. Pelo criterio de
2026-08-29e, `CONTRA` significa que **a hipotese encerra NESTA FORMA**.

A regra de parada autoriza acumular pregoes e rerodar apenas apos
`INCONCLUSIVO`. Nao foi o caso. Rerodar o mesmo comando produziria
numeros IDENTICOS (nao ha aleatoriedade no caminho) e custaria mais 6
trials.

### O que os numeros mostram, sem virar consolo

A melhor celula das doze foi `z_absorcao_dir` h=1 no 5m: IC -0,0342,
sinal NEGATIVO como a hipotese previa, superando ambos os controles em
magnitude (0,0342 contra 0,0246 e 0,0069). Precisava de |t| >= 4,03 e
entregou 3,06. Nem no mundo de 42 trials, onde a barra era 3,31, teria
passado.

Tres celulas de `z_absorcao_dir` das quatro tem o sinal previsto. Isso
NAO e' evidencia parcial a favor — com quatro celulas e sinal binario,
tres iguais e' o que uma moeda honesta entrega com frequencia alta.
Registrado para nao ser reinterpretado depois.

### Observacao descritiva, explicitamente NAO um resultado

O 5m tem magnitudes maiores que o 1m em toda a linha: |t| maximo 3,06
contra 1,31; |IC| medio 0,024 contra 0,007. A leitura visual do operador
de que o 5m carrega mais sinal que o 1m e' COMPATIVEL com isso.

Mas nao esta testado, e ha explicacao mecanica concorrente: o retorno de
uma barra de 1m tem razao sinal/ruido menor por barra, o que encolhe o
IC sem que a informacao total mude. Fica como material para gerar
hipotese futura, nunca como validacao da intuicao.

### O que este resultado NAO autoriza

- **Nao** autoriza resgatar por quintil, por corte de cauda, ou por
  qualquer analise condicional NESTES dados. Isso foi antecipado por
  escrito em 2026-08-29e ("o IC e' um teste FRACO para efeito
  concentrado em cauda, e mesmo assim ele fica sendo o portao").
  Dizer agora que o teste era inadequado seria mover a trave.
- **Nao** autoriza reajustar o limiar de 0,85 para que 0,82 passe.
- **Nao** autoriza implementar o indicador NTSL como SINAL. O roadmap
  era validar em Python e so' entao implementar; a validacao falhou.

### O que continua legitimo

- Pre-registro NOVO, com formalizacao diferente do mesmo fenomeno,
  escrito antes do dado e testado em amostra NOVA — com a ressalva
  honesta de que ele nasce depois de ter visto este CONTRA, e que seus
  trials somam no mesmo contador.
- Indicador NTSL como VISUALIZACAO exploratoria, rotulado como tal, para
  gerar hipotese a partir do grafico. O que `imbalance - desloc_norm`
  mediu pode simplesmente nao ser o que o operador ve na tela — o
  negativo e' sobre a FORMULA, nao sobre o fenomeno.
- Acumular pregoes. E' a unica alavanca gratuita: de 25 para 50 pregoes
  o `t_critico` cai de 4,03 para ~3,50 sem gastar trial nenhum.

## A FORMULA NAO TEM CAUDA: absorcao_dir e sub-gaussiana por construcao (2026-08-30b)

Achado ao calibrar o limiar do indicador NTSL por FREQUENCIA (quantas
barras inspecionar), nao por resultado. E' uma afirmacao sobre a FORMA
da variavel, derivada da distribuicao, nao do IC — nao reverte nem
reinterpreta o veredito CONTRA de 2026-08-30.

### Distribuicao observada (5m, 2.698 barras com z valido)

    media -0,004   desvio 1,027   min -2,44   max +2,69

    limiar   observado    normal    razao
     1,00      40,77%     31,73%    1,28x
     1,50      13,68%     13,36%    1,02x
     1,75       6,30%      8,01%    0,79x
     2,00       1,82%      4,55%    0,40x
     2,50       0,07%      1,24%    0,06x

    p90 = 1,60   p95 = 1,79   p99 = 2,10
    (normal:      1,64          1,96          2,58)

Ombros GORDOS, caudas MAGRAS. Sub-gaussiana — o oposto do que features
financeiras normalmente sao. Em |z| >= 2,5 a frequencia observada e' 6%
da que uma normal daria.

### A causa esta na algebra, nao no mercado

`absorcao_dir = imbalance - desloc_norm`, com os dois termos limitados a
[-1, +1] por construcao. Teto teorico do composto: [-2, +2].

    absorcao_dir observado: [-0,847; +0,897]

Menos da metade do intervalo teorico. E nenhum dos dois termos chega
perto do proprio extremo numa barra de 5m com ~42.000 negocios:
`imbalance = ±1` exigiria agressao 100% unilateral; `desloc_norm = ±1`
exigiria marubozu perfeito (abertura na minima E fechamento na maxima).

### Consequencia sobre a hipotese de 2026-08-29e

A hipotese era sobre barras EXTREMAS — a leitura visual do operador e'
sobre uma barra que se destaca. A formula escolhida **nao consegue
produzir barras extremas**: ela sabe dizer "esforco e resultado
discordaram", mas nunca "discordaram brutalmente", porque a discordancia
satura em ±2 e na pratica em ±0,9.

Isso e' uma explicacao CANDIDATA para o CONTRA, registrada como tal. Nao
e' prova de que a hipotese estaria certa com outra formula, e nao
autoriza reanalisar os dados de 2026-08-30.

### Direcao para uma formalizacao futura (nao pre-registrada ainda)

Para existir cauda, a formula precisa de um termo que POSSA ser extremo.
`absorcao = vol_agr / range_ticks` e' ilimitado: uma barra pode ter cinco
vezes o volume normal, enquanto nenhuma barra pode ter `imbalance` cinco
vezes maior que 1.

Registrado como observacao. Qualquer uso disso exige pre-registro NOVO,
escrito antes do dado, com trials contados no mesmo contador — e com a
ressalva honesta de que nasce depois de ter visto o CONTRA.

### Limiar do indicador NTSL, escolhido por FREQUENCIA

`Limiar = 1,75` — 6,3% das barras, ~7 por pregao no 5m, logo acima do
p95 observado (1,79).

A distincao que torna isso legitimo: escolher o limiar pela FREQUENCIA
("quero inspecionar as ~6% mais extremas") e' decidir quantas barras
olhar. Escolher pelo RESULTADO ("1,75 pegou umas boas") e' overfit
visual, e nao deixa de ser porque foi feito com o olho em vez de com um
otimizador. O limiar continua NAO VALIDADO nos dois casos.

## ESTADO AO FIM DE 2026-08-30: o que esta aberto

Atualizado ao fim da sessao (v1.42). `trials.json` = **504**.

### ENCERRADO nesta sessao

| pergunta | veredito | onde |
|---|---|---|
| Absorcao direcional prediz retorno? | **CONTRA** nas 12 celulas | 2026-08-30 |
| O indicador NTSL calcula o mesmo que o Python? | **SIM**, divergencia de 1 tick atribuida | 2026-08-30i |
| O stop e detector de reversao (hipotese b)? | **CONTRA**, confirmado com e sem RLP | 2026-08-30i/j |

Nenhum dos tres pode ser reaberto acumulando pregoes: CONTRA e' veredito
final pela regra de parada. Reabrir exige formalizacao NOVA com
pre-registro proprio, e a ressalva ja' escrita cobra a multiplicidade.

### PENDENTE, em ordem de CUSTO

**1. Acumular pregoes — custo ZERO, ja' rodando.**
E' a unica alavanca que baixa a barra sem gastar trial: 25 pregoes dao
`t_critico` 4,07; 100 dao 3,23. Depois satura (500 dao 3,09). Com ~25
pregoes/mes, sao ~3 meses ate 100. **Continua sendo a via principal**,
acima de qualquer ideia nova.

**2. Stop como CONTROLE DE DRAWDOWN — ENCERRADO 2026-08-31.**
→ premissa (Calmar 0,23) era dado contaminado; sobre curated 4,08.
  O que sobrou é correção do stop catastrófico existente (checagem
  contínua na fita) — sessão de desenho, não research.
E' o que o CONTRA de hoje deixou explicitamente em aberto. Nao e'
hipotese sobre o mercado: e' um trade-off mensuravel — quanto de
expectativa se paga por quanto de reducao de drawdown. Motivacao viva:
Calmar 0,23 na rodada de 25 dias. Exige pre-registro proprio; o de hoje
diz isso com todas as letras.

**3. Robustez de regime do `z_agf_3` — BLOQUEADA por instrumento.**
O gráfico tem anos de historico, mas `z_agf_3` vive em barra de VOLUME
com relogio de agressao e o grafico so' da barra de TEMPO. Uma variante
em barra de tempo SERIA testavel, mas e' feature nova e exige
pre-registro.

**4. Nova formalizacao da absorcao — so' com mais amostra.**
O CONTRA e' sobre a FORMULA, nao sobre o fenomeno. A direcao esta
registrada: para existir cauda, a formula precisa de termo ILIMITADO
(`vol_agr / range_ticks` e' ilimitado; `imbalance` nunca passa de 1).
Pre-registro NOVO, com a ressalva honesta de que nasce depois do CONTRA.

**5. Forward test em DEMO — custo zero de trial.**
Mecanica de execucao, nao evidencia estatistica.

### NAO AUTORIZADO

- Reanalisar os dados de 2026-08-30 por quintil, corte de cauda ou
  qualquer condicional (antecipado por escrito em 29e).
- Testar "a tendencia da grade" da Rota B: seria estimador novo DEPOIS
  de ver o resultado, e a ressalva do pre-registro 3 manda somar as
  tentativas ao contador.
- Implementar o indicador NTSL como SINAL, ou adicionar funcao de ordem
  ao `.ntsl`. Limiar 1,75 escolhido por frequencia de inspecao, NAO
  validado.
- Usar o backtest do Profit como validacao (ver politica do historico).
- Olhar o historico do grafico fora de um pre-registro congelado.

## ROTA B: leitura de F pelo tape — a infraestrutura que destrava (2026-08-30c)

Construida a pedido do operador ANTES do pre-registro, por ser
infraestrutura de MEDICAO (categoria `features`, nao consome trial) e
conferivel a mao contra um punhado de negocios.

`src/profittape/research/preenchimento.py`.

### O diagnostico: os dois estimadores morreram da mesma coisa

- **2026-08-29a**: condicionava em `MAE_intrabar >= X`, que usa o HIGH
  da barra. O grupo "nao tocou" ficava com teto de perda X por
  construcao. Sobre ruido puro, t ~ -25.
- **2026-08-29c**: media a partir de `F` = extremo da barra de
  cruzamento. Sobre ruido puro devolveu +30 pontos, t entre 8 e 13.

A raiz e' a mesma: **o extremo de uma barra nao e' um tempo de parada**.
Ele so' e' conhecido quando a barra FECHA — usa informacao do futuro
dentro da propria barra. Um stop real nao tem esse privilegio.

### Por que o tape resolve, e e' demonstravel ANTES de rodar

Com o tape, `F` e' o preco do PRIMEIRO NEGOCIO que atinge o nivel. Isso
e' um tempo de parada legitimo na filtracao dos negocios, e o teorema da
parada opcional se aplica direto: sob martingal,

    E[preco_final - F] = 0

O estimador DEVE devolver zero no ruido — por teorema, nao por
esperanca. E' o argumento *a priori* que a regra de anulacao exige, e
inverte o papel do portao de honestidade: passa a ser confirmacao de
implementacao, nao descoberta de vies.

### Medido sobre passeio aleatorio simetrico

    nivel  +20 pts:  n=5037  remanescente medio  -0,149  t -0,11
    nivel  +50 pts:  n=3761  remanescente medio  -0,428  t -0,31
    nivel +100 pts:  n=1925  remanescente medio  +0,826  t +0,51

Contra t ~ -25 e t ~ +13 dos anulados, no mesmo tipo de ruido.

### Decisao de desenho registrada: quais negocios disparam

Default `so_agressao=True`. RLP e' varejo internalizado bilateralmente —
nao consome liquidez do livro e nao deveria acionar uma ordem stop que
la' repousa. E' a mesma regra que ja' rege o relogio das barras e o
`vol_agr`; manter aqui evita duas definicoes de "negocio" no projeto.

O parametro existe porque a pergunta e' empirica: se a escolha mudar o
resultado de forma relevante, isso e' um achado sobre microestrutura e
precisa aparecer, nao ficar escondido num default.

### Semantica fixada

- Intervalo ABERTO no inicio: o negocio que originou a entrada nao
  dispara o proprio stop.
- `F` e' o preco NEGOCIADO, nao o nivel. A diferenca e' o overshoot do
  cruzamento; ignora-la seria supor preenchimento perfeito — o limite
  "otimista" do pre-registro anulado.
- Tape reordenado por tempo antes de qualquer busca: "primeiro negocio
  que cruza" so' faz sentido em sequencia ordenada, e um tape fora de
  ordem devolveria um `F` posterior sem erro visivel.

### Bug pego na conferencia a mao (regra 4)

O indice do preco era deslocado duas vezes: fatiava a janela e indexava
com o indice absoluto. O **timestamp saia certo e o preco vinha de outra
linha** — num agregado, `F` ficaria levemente torto sem nada parecer
quebrado. Tem teste proprio.

### O que ISTO NAO e'

Nao testa hipotese nenhuma. So' localiza o negocio. O estimador da
hipotese (b) — expectativa remanescente a partir de τ — exige
pre-registro NOVO, congelado antes de qualquer contato com dado real.

E o stop de corretora do Profit resolve a EXECUCAO (como manter um stop
continuo em producao); o tape resolve a MEDICAO (saber se o stop ajuda).
Sao problemas diferentes, e mistura-los seria repetir o erro original da
Rota B, que foi executar de um jeito e medir de outro.

## PRE-REGISTRO 3 DA ROTA B (CONGELADO): expectativa remanescente com F exato (2026-08-30d)

> **CONGELADO em 2026-08-30 pelo operador**, ANTES de qualquer contato
> com dado real para esta pergunta e antes de qualquer linha do
> estimador. Ficam fixados: o estimador, as fronteiras temporais, a
> grade, a decisao de multiplicidade, o portao, a checagem de pre-voo
> bloqueante, o criterio de decisao e a regra de parada. Alteracao de
> qualquer um exige pre-registro NOVO, com secao e data proprias — nao
> editar esta secao.
>
> Precedente que acompanha: os dois pre-registros anteriores desta mesma
> pergunta tambem estavam congelados. O primeiro teve o RESULTADO
> anulado; o segundo foi reprovado pelo portao antes de tocar o dado.
> **Congelar protege contra ajuste oportunista de criterio; nao
> certifica que o metodo e' valido.**

### A pergunta, inalterada desde 2026-08-29

Hipotese (b): o stop e' um DETECTOR DE REVERSAO?

> No instante τ em que eu sairia a −X, qual a expectativa de CONTINUAR
> ate o fim da janela?

Segue sem resposta. Nao foi refutada nem confirmada — o que existe sao
dois estimadores invalidos.

### O que muda: `F` exato

`preenchimento.localizar_toque` devolve o preco do PRIMEIRO NEGOCIO que
atinge o nivel. Isso e' um tempo de parada legitimo na filtracao dos
negocios, e pelo teorema da parada opcional, sob martingal,
`E[preco_final − F] = 0`.

**Duas consequencias que simplificam o desenho:**

1. **Os dois limites de `F` desaparecem.** Nao ha mais "pessimista" e
   "otimista", logo nao ha o ramo INCONCLUSIVO POR PREENCHIMENTO — que
   era justamente o gatilho invalido que o portao de 29c expos (o ruido
   sozinho disparava escalada de infraestrutura).
2. **A recomendacao de 29c fica SUPERADA, nao ignorada.** Ela mandava
   usar o nivel do stop e calibrar contra nulo empirico. Fazia sentido
   quando so' havia barras. Com `F` exato nao e' preciso escolher entre
   limites enviesados nem estimar um nulo: o estimador e' nao-enviesado
   por teorema, e o nulo e' zero.

Medido sobre passeio aleatorio (2026-08-30c): |t| <= 0,51 em tres
niveis, contra t ~ -25 e t ~ +13 dos anulados.

### Estimador

Para cada operacao que toca −X dentro da janela:

    remanescente = (close_{t+h} − F) * lado

Operacoes que nunca tocam sao EXCLUIDAS. **Nao ha grupo de comparacao** —
e' uma pergunta de UMA amostra contra zero, o que elimina de raiz o
problema de subconjunto vs superconjunto do primeiro estimador anulado.

### Fronteiras temporais — fixadas aqui porque e' onde um erro passaria calado

`z_agf_3` vive em **barra de volume**; a janela `t..t+h` esta em barras.
Mas `F` vem do TAPE, que precisa de fronteiras em nanossegundos. Sem
fixar a traducao, uma implementacao poderia usar o instante errado sem
produzir erro nenhum — so' um `F` sistematicamente deslocado.

    ts_entrada = ts_close da barra t      (o negocio que formou a entrada)
    ts_limite  = ts_close da barra t+h    (fim da janela)

As duas colunas existem em `flow.calcular`. Consequencias:

- Intervalo ABERTO em `ts_entrada`: o proprio negocio que originou a
  entrada nao dispara o stop (ja' e' a semantica de
  `localizar_toque`).
- A janela **nunca atravessa o dia**: se `t+h` cai em outro pregao, a
  operacao e' descartada — mesma purga estrutural de `retornos.py` e de
  `mae.py`, nao uma regra nova.
- O preco de entrada e' o `close` da barra t, que e' um preco NEGOCIADO
  de agressao. O nivel do stop e' `entrada - X * lado`.

### Custo: medido BRUTO, de proposito

Em τ a escolha e' entre sair agora e segurar. Nos dois ramos paga-se
exatamente um giro. O custo CANCELA; medir liquido seria conta-lo duas
vezes.

### Metodologia, fixada ANTES

- Populacao, purga estrutural de dia inteiro, pool out-of-sample e regra
  de entrada IDENTICAS aos pre-registros anteriores (essa parte nunca
  esteve errada).
- Lado **venda apenas** — o unico com edge confirmado. Feature
  `z_agf_3`, h=3, threshold 1,4, contrarian.
- **Grade X mantida**: {40, 60, 80, 100, 120, 150, 200}. Trocar a grade
  junto com o estimador tornaria impossivel separar efeito de metodo de
  efeito de grade.
- `so_agressao=True` no disparo do stop (decisao registrada em
  2026-08-30c). Reportar em SENSIBILIDADE o resultado com
  `so_agressao=False`: se a escolha mudar a conclusao, isso e' achado de
  microestrutura e tem que aparecer.
- n < 30 no ponto: REPORTADO, nunca interpretado.
- **Todos os 7 pontos sempre reportados**, inclusive os que nao derem
  nada. Reportar so' o melhor seria a p-hacking que o pre-registro
  original existia para evitar.
- Estatistica de UMA amostra contra zero, com bootstrap de bloco por
  pregao inteiro. Significancia exige as DUAS evidencias: |t| >= limiar
  deflacionado de 7 comparacoes E IC95 de bloco excluindo zero.
- Reportar a distribuicao de τ (em qual barra da janela ocorre o
  cruzamento) — diagnostico, nao criterio.

### PORTAO DE HONESTIDADE (bloqueante, antes de interpretar)

O mesmo estimador sobre passeio aleatorio puro, com a mesma geometria.
Exigencia: veredito **CONTRA (b)** — "nao ha nada aqui". Qualquer outro
veredito sobre ruido reprova.

Diferenca em relacao aos anteriores: aqui o portao e' CONFIRMACAO DE
IMPLEMENTACAO, nao descoberta de vies. A validade vem do teorema; o
portao verifica se o codigo corresponde a ele. Se reprovar, o bug esta
no codigo, nao no desenho.

### CHECAGEM DE PRE-VOO — BLOQUEANTE (carregada de 29b)

Reconciliar a contagem: a rodada anulada deu **162 operacoes em 22
pregoes**, enquanto a analise de MAE de 2026-08-27 falava em **336
gatilhos em 26 dias**. Pode ser compra+venda somados la', mas
**confirmar, nao assumir** — se a populacao mudou por outro motivo, nada
mais neste teste e' interpretavel.

Bloqueante: a reconciliacao roda e e' reportada ANTES de qualquer numero
do estimador. Nao reconciliou, nao interpreta.

### Criterio de decisao, definido ANTES

- **FAVORAVEL a (b)**: existe X* com remanescente medio NEGATIVO e
  significativo, MONOTONICIDADE (todos os X > X* tambem negativos) e
  n >= 30 em X* e acima.
  → X* vira candidato a stop, DERIVADO da estrutura condicional.
- **CONTRA (b)**: nenhum X produz remanescente distinguivel de zero.
  → o stop nao detecta nada; so' se justifica como (a), controle de
  drawdown, com custo em expectativa medido em pre-registro separado.
- **INVERTIDO**: remanescente significativamente POSITIVO — sair a −X
  destroi valor. Achado genuino, registrar; NAO autoriza aumentar
  posicao no adverso (piramide, proibida por design).
- **INCONCLUSIVO**: nao monotonico ou n insuficiente.

### Regra de parada

Proibido re-rodar com grade, threshold, horizonte ou lado diferentes
depois de ver o resultado. INCONCLUSIVO so' permite acumular pregoes e
rodar de novo com a MESMA grade e o MESMO estimador. Estimador novo
exige pre-registro novo.

### Multiplicidade — DECIDIDO, nao em aberto

Decisao do operador (2026-08-30): **manter a deflacao local sobre os 7
pontos da grade, sem somar ao `trials.json`.** O raciocinio, registrado
para poder ser cobrado depois:

O teorema da estrategia falsa conta o numero de tentativas DAS QUAIS SE
SELECIONOU O MAXIMO. Olhando o historico da hipotese (b):

  - **29a**: olhou dado real, resultado ANULADO com argumento *a
    priori* (a algebra do vies era demonstravel sem ver o numero). O
    projeto ja' julgou essa anulacao legitima exatamente porque nao
    dependeu do resultado — logo nao houve selecao.
  - **29c**: NUNCA tocou dado real; o portao pegou antes.
  - **este**: primeiro resultado que sera' interpretado.

Nao houve selecao sobre resultados, entao nao ha multiplicidade de
estimadores a corrigir. O que existe e' a grade, e ela esta coberta.

**RESSALVA QUE ACOMPANHA A DECISAO, e e' a parte que pode ser cobrada:**
se esta rodada sair INCONCLUSIVO e um QUARTO estimador for tentado
DEPOIS de ver o resultado, ai' havera selecao e a contagem tera' que
passar a incluir as tentativas. Fica escrito agora para que essa
correcao nao dependa de alguem lembrar.

### A grade e' ANINHADA — registrado antes de interpretar

Quem tocou −200 tocou −40 antes. Os 7 pontos nao sao testes
independentes: sao subconjuntos encaixados, fortemente e positivamente
dependentes.

Duas consequencias, as duas fixadas aqui:

1. **A deflacao por 7 comparacoes independentes e' CONSERVADORA** neste
   caso. Sob dependencia positiva o maximo de 7 estatisticas e' menos
   extremo que sob independencia, entao o limiar exigido e' mais alto
   que o necessario. Aceito de proposito: erra para o lado de nao
   afirmar.
2. **A monotonicidade exigida no criterio nao e' mecanica.** O
   encaixamento garante que o `n` cai conforme X sobe, nao que a MEDIA
   do remanescente siga qualquer direcao. Se fosse mecanica, a condicao
   nao valeria nada — e' por isso que esta escrito aqui, antes de olhar.

### Fora deste pre-registro

- Escolha do numero final do stop (X* e' candidato, nunca decisao).
- Qualquer implementacao em `ea/risco.py`.
- Alvo, em qualquer forma (fora desde 2026-08-26: alvo fixo cortaria as
  caudas ganhadoras de um sinal cujo edge vem de magnitude).
- Custo em expectativa do stop-como-(a) — pre-registro separado.
- Stop de corretora do Profit: e' EXECUCAO, nao medicao.

## IMPLEMENTADO: remanescente_tape executa o pre-registro 3 (2026-08-30e)

`src/profittape/research/remanescente_tape.py` +
`profit-tape rota-b-remanescente`. Modulo NOVO: `remanescente.py`, que
implementa o estimador reprovado em 29c, fica intacto — o historico de
um estimador invalido e' parte da auditoria, e a comparacao entre os
dois documenta a correcao.

### A ordem bloqueante esta no CODIGO

    1. checagem de pre-voo   (bloqueante)
    2. portao sobre ruido    (bloqueante)
    3. so' entao o dado real

`rodar()` levanta antes de tocar dado real se o portao nao devolver
CONTRA. Deixar a ordem a cargo de quem executa seria confiar exatamente
no ponto onde este projeto ja' falhou.

### PORTAO PASSOU

Ruido puro, 100 pregoes sinteticos, 10.000 barras de volume:

    X     n    media      t     IC95
     40  592   +0,287   0,066   [ -7,29 ; +8,40]
     60  490   -0,755  -0,167   [ -8,67 ; +7,97]
     80  405   -1,062  -0,230   [ -8,86 ; +7,25]
    100  339   +3,422   0,717   [ -4,96 ; +12,45]
    120  263   +2,624   0,524   [ -7,05 ; +12,52]
    150  177   +4,463   0,828   [ -5,03 ; +14,18]
    200   80   +8,000   1,147   [ -6,07 ; +23,88]

    VEREDITO SOBRE RUIDO: CONTRA  -> portao PASSOU

Comparacao com os dois estimadores anulados, no mesmo tipo de ruido:

    29a (condiciona no MAE_intrabar)  t ~ -25
    29c (F = extremo da barra)        +30 pts, t entre 8 e 13
    este (F = primeiro negocio)       |t| <= 1,15, medias em [-1; +8]

### DEFEITO ENCONTRADO NO PROPRIO PORTAO: ele nao conseguia passar

Com 25 pregoes de ruido, X=200 juntava n=18 — abaixo do minimo de 30 —
e `decidir` devolvia INCONCLUSIVO. Ou seja, o veredito CONTRA era
**inatingivel por construcao**, e o portao teria reprovado um estimador
comprovadamente calibrado.

**Um portao que nao consegue passar nao e' portao.** Corrigido: o
default de ruido virou 100 pregoes (derivado de fazer o ponto mais
esparso cruzar 30, nao escolhido por resultado), e amostra insuficiente
agora levanta ERRO explicito em vez de virar reprovacao silenciosa.

Isso e' um caso do mesmo padrao que ja' apareceu tres vezes hoje: um
verificador que falha de um jeito que parece resultado.

### Calibracao da geometria do ruido

Passo de ±1 tick por negocio faz a amplitude da barra ir com `5·raiz(N)`.
Para a amplitude cair na faixa da grade de X (40 a 200 pts), sao ~200
negocios por barra. Com 20.000 negocios/pregao, `volume_barra=200` da
~100 barras/pregao — a mesma ordem do real. Derivado da aritmetica, nao
ajustado por resultado.

### O que falta para responder a pergunta

Rodar sobre dado real, na maquina do operador (o tape nao esta no
sandbox):

    profit-tape rota-b-remanescente WINFUT

`--volume-barra` deixou de ser obrigatorio: o valor e' lido do
`resumo.json` ao lado do parquet ou, na falta dele, inferido de
`min(vol_agr)`. Ver a secao seguinte.

E rodar tambem com `--com-rlp`, como a sensibilidade congelada pede: se
a conclusao mudar, e' achado de microestrutura e tem que aparecer.

### O `volume_barra` nao era gravado em lugar nenhum (2026-08-30f)

O comando da Rota B pedia `--volume-barra` — o mesmo usado ao gerar as
features, porque o portao monta barras de ruido com a MESMA
granularidade e geometria diferente compara outra coisa.

So' que esse valor era apenas IMPRESSO NA TELA por `features`, e nunca
gravado. Quem fosse usar o parquet dias depois dependia de achar o
numero no scroll de um terminal antigo. **Pedir um dado que so' existe
no historico do console e' defeito de desenho, nao falha de memoria de
quem roda.**

Corrigido em dois niveis:

1. **`features` passa a gravar `resumo.json`** ao lado do parquet, com
   `volume_barra`, tick inferido, dias, contagens e agentes. Parametro
   que define o dado viaja junto com o dado.
2. **Para os parquets antigos, o valor e' INFERIDO** de `min(vol_agr)`:
   uma barra de volume so' fecha quando a agressao acumulada CRUZA o
   limiar, entao todo `vol_agr >= limiar` e o minimo e' o estimador mais
   proximo por cima. Reportado como "aproximado", nunca como exato.

O comando informa a origem do valor na saida — exato ou inferido — para
a diferenca nao ficar invisivel.

### CHECAGEM DE PRE-VOO: RECONCILIOU (2026-08-30g)

Primeira execucao na maquina do operador:

    pregoes            : 25
    gatilhos_brutos    : 385
    validos_compra     : 194
    validos_venda      : 178
    validos_ambos      : 372
    usados_neste_teste : 178   (venda apenas)

A duvida de 29b era se "336 gatilhos em 26 dias" incluia os dois lados,
enquanto a rodada anulada usava 162 (venda apenas, 22 pregoes).

**A hipotese estrutural CONFIRMA**: venda sozinha da' 178 contra 372 dos
dois lados — praticamente metade, e 178/25 pregoes = 7,1/dia contra
162/22 = 7,4/dia da rodada anulada. Mesma populacao.

**Ressalva registrada**: 372 em 25 pregoes da' 14,9/dia contra 336 em 26
dias = 12,9/dia, uma diferenca de ~15%. As duas amostras nao cobrem as
mesmas datas, entao a diferenca e' esperada — mas fica anotada, porque o
pre-registro exige confirmar e nao assumir. O que estava em duvida (se
336 eram os dois lados somados) esta respondido.

### DOIS DEFEITOS NO PORTAO, corrigidos (2026-08-30g)

**1. O gerador de ruido nao escalava com `volume_barra`.** Fixava 20.000
negocios de 1 contrato por pregao. Com o `volume_barra` real do WINFUT
(119.504, inferido de `min(vol_agr)`), o dia inteiro somava 20.000 de
volume e NENHUMA barra fechava — tudo virava parcial e era descartado.

A causa e' ter confundido duas escalas independentes:

  - **geometria do preco**: quantos NEGOCIOS cabem numa barra (~200 poem
    a amplitude na faixa da grade de X);
  - **escala de volume**: quantos CONTRATOS fecham a barra (o
    `volume_barra` real).

Corrigido separando: o numero de negocios controla a geometria, a
QUANTIDADE por negocio e' derivada de `volume_barra`.

**2. O erro nao dizia o que era.** O `groupby` vazio fazia `apply`
devolver um DataFrame com as colunas originais, e atribuir isso a uma
coluna unica estourava com "Cannot set a DataFrame with multiple
columns" — um erro do pandas, tres niveis abaixo, sem relacao aparente
com a causa. `flow.calcular` passa a checar e explicar.

Portao rodado de novo com `volume_barra=119504`: **CONTRA**, |t| <= 0,98
nos sete pontos. Passa.

### STREAMING POR PREGAO: 81 milhoes de negocios nao cabem na memoria (2026-08-30h)

`MemoryError` na primeira execucao real, pedindo 617 MiB para um unico
array. O tape de 25 pregoes do WINFUT tem **80.999.999 negocios**, e eu
carregava todos de uma vez com `pd.concat`.

O resto do projeto ja' fazia streaming por dia pela mesma razao ("o
dataset inteiro estourou 20 GB"). Este modulo nao seguiu o padrao.

**Funciona porque a janela nunca atravessa o pregao** (purga estrutural):
o stop de uma entrada do dia D so' pode ser tocado por negocios do dia D.
E os 7 pontos da grade saem da MESMA passada — dia por fora, grade por
dentro — em vez de reler o tape sete vezes.

Duas correcoes juntas:

1. **`preparar_tape` reduz COLUNAS antes de filtrar LINHAS.** O filtro
   booleano copia o frame; filtrar antes de reduzir fazia o pico carregar
   as sete colunas do curated em vez de duas.
2. **`apenas_dia` em `_remanescentes_tape`.** No streaming o tape so' tem
   um pregao; sem o filtro, entradas de outros dias nao encontrariam o
   toque e sairiam como "nunca tocou" — falso negativo SILENCIOSO, que
   reduziria o `n` de todos os pontos sem erro nenhum.

Teste de equivalencia: streaming e modo em memoria tem que devolver o
MESMO resultado. Otimizacao que muda a resposta nao e' otimizacao.

## RESULTADO DA ROTA B: CONTRA - o stop nao detecta reversao (2026-08-30i)

Executado o pre-registro 3 congelado em 2026-08-30d, na ordem exigida.
25 pregoes, 81 milhoes de negocios, lado venda, `z_agf_3` h=3.

### Os dois portoes bloqueantes passaram

    PRE-VOO   : 25 pregoes | 385 brutos | 194 compra + 178 venda = 372
                usados: 178 (venda). RECONCILIOU com 29b.
    PORTAO    : CONTRA sobre ruido puro -> passou

### Resultado

    limiar deflacionado (7 comparacoes): 1,96   |  so_agressao: True

      X     n   media       t      IC95              overshoot
     40   161  +17,329   0,758  [-36,45 ; +67,25]      0,062
     60   146   +9,726   0,406  [-43,36 ; +59,13]      0,000
     80   134   -2,500  -0,107  [-50,04 ; +45,50]      0,000
    100   124   -1,129  -0,047  [-50,09 ; +49,95]      0,000
    120   115   -4,348  -0,181  [-51,16 ; +43,57]      0,000
    150   103  -12,427  -0,547  [-56,70 ; +32,25]      0,000
    200    85  -13,000  -0,573  [-50,07 ; +27,42]      0,000

    VEREDITO: CONTRA

`n` suficiente nos sete pontos, |t| maximo 0,76, todos os IC95 contendo
zero.

### O que isso decide

**A hipotese (b) e' FALSA para este sinal.** O stop nao e' detector de
reversao: no instante em que se sairia a -X, a expectativa de continuar
ate o fim da janela e' indistinguivel de zero. Pergunta aberta desde
2026-08-27, agora respondida.

Pelo criterio congelado, o stop **so' se justifica como (a)** - controle
de drawdown -, e o custo em expectativa dessa escolha precisa ser medido
em **pre-registro separado**. Trocar expectativa por drawdown e' decisao
consciente, nao consequencia automatica deste resultado.

### A tendencia na grade e' OBSERVACAO, nao achado

A media cai de +17,3 para -13,0 conforme X sobe (correlacao -0,91 ao
longo da grade). Ordenado o bastante para tentar.

**Nao e' evidencia.** Nenhum ponto individual passa de |t| 0,76, e os
sete pontos sao subconjuntos ENCAIXADOS - quem tocou -200 tocou -40
antes -, entao essa correlacao nao e' um teste independente de nada.

Registrado explicitamente porque testar "a tendencia em si" seria um
ESTIMADOR NOVO DEPOIS DE VER O RESULTADO: exatamente a selecao que a
ressalva do pre-registro previu, e que obrigaria a somar as tentativas
ao contador.

### Achado lateral: o overshoot e' zero em instrumento liquido

`overshoot_medio` deu 0,000 em seis dos sete pontos e 0,062 no primeiro.
`F` coincide com o nivel do stop praticamente sempre: com ~3,5 milhoes
de negocios por pregao numa grade de 5 pontos, o primeiro negocio que
cruza cai EXATAMENTE no nivel.

Consequencia retroativa: toda a discussao de 29c sobre limites
"pessimista" e "otimista" de preenchimento era **irrelevante na
pratica** para este instrumento - os dois colapsam no mesmo numero. O
trabalho de construir `F` exato continua tendo valimento porque foi ele
que tornou o estimador nao-enviesado por teorema; mas o medo especifico
do preenchimento era infundado, e so' da' para saber isso medindo.

### Taxa de toque (diagnostico)

Sobre as 178 entradas de venda: 90% tocam -40, 70% tocam -100, 48%
tocam -200 dentro de 3 barras. Barras de ~119.504 de volume sao grandes
o bastante para o preco percorrer 200 pontos com frequencia.

### Contabilidade

Deflacao local sobre os 7 pontos, sem somar ao `trials.json`, como
DECIDIDO no pre-registro. `trials.json` permanece em 504.

### SENSIBILIDADE COM RLP: resultado IDENTICO, e isso e' um achado

Rodado `--com-rlp`, como o pre-registro exigia.

Primeiro a verificacao de que a flag de fato mudou o dado — sem ela,
"resultado identico" seria indistinguivel de "a flag nao funcionou":

    negocios por pregao, so agressao -> com RLP
      24/07  2.810.589 -> 3.917.214   (+39%)
      27/07  2.737.004 -> 3.889.802   (+42%)
      28/07  3.325.040 -> 4.576.388   (+38%)

Mais de um milhao de negocios por pregao entraram no tape. E os sete
pontos deram numeros **IDENTICOS ate a ultima casa** — mesmo `n`, mesma
media, mesmo `t`, mesmo overshoot de 0,062 em X=40.

**Nenhuma das 1.246 combinacoes (entrada x X) mudou de status.**

### O mecanismo, e por que ele fecha com a equivalencia NTSL

Um print de RLP NUNCA foi o primeiro a cruzar um nivel. Coerente com a
microestrutura: RLP imprime DENTRO do spread, entao nao alcanca um preco
que a agressao ainda nao tinha alcancado.

E' o MESMO mecanismo encontrado hoje na equivalencia NTSL, por um
caminho totalmente diferente: la', o RLP mexia em `open` e `close` (o
primeiro e o ultimo negocio da barra) mas o denominador `(high - low)`
batia em 79 de 80 barras. **Cruzar um nivel e' fazer extremo novo**, e o
RLP nao faz extremo.

Duas medicoes independentes, mesma conclusao sobre a microestrutura.

### Consequencia sobre a decisao de desenho

`so_agressao=True` estava registrado como decisao "empirica, nao obvia",
justificada por argumento (RLP nao consome liquidez do livro, logo nao
deveria acionar um stop que la' repousa). Agora e' melhor que
defensavel: e' **indiferente na pratica** para este instrumento.

O parametro fica, porque o argumento nao vale para instrumento ilíquido
nem para grade de tick mais grossa — mas para o WINFUT a escolha nao
muda nada, e isso esta medido em vez de suposto.

## POLITICA DO HISTORICO DO GRAFICO: conjunto de validacao CEGO (2026-08-30j)

Registrada ANTES de qualquer uso e ANTES de haver tentacao concreta.
Politica escrita depois da tentacao nao vale nada.

### O ativo que se gasta uma vez

O Profit Chart tem anos de historico que a captura via ProfitDLL nao
tem (25 pregoes em 2026-08-30). Esse historico **nunca foi olhado para
formar hipotese nenhuma**, e e' isso que o torna valioso.

Se for usado para aumentar o `n` de hipoteses formadas nos 25 pregoes,
vira apenas uma busca maior — o teorema da estrategia falsa cobra por
ela igual. Se for reservado, uma hipotese aprovada no tape pode levar
**UM tiro** nele, e isso e' a evidencia mais forte que este projeto
consegue produzir: fora da amostra, em regimes diferentes.

**Cada olhada informal queima uma parte do ativo.**

### REGRA

1. O historico do grafico e' **CEGO**. Nao se olha para formar hipotese,
   nao se olha para "dar uma conferida", nao se olha para calibrar
   limiar.
2. Uso permitido: **um** teste por hipotese, com pre-registro proprio,
   escrito e congelado ANTES de qualquer contato.
3. **Proibido combinar numa amostra unica** com o tape. Sao instrumentos
   de medicao diferentes (`desloc_norm` difere em 47% das barras, sempre
   1 tick em open/close) e a mistura destroi a propriedade de ser fora
   da amostra — que e' a unica razao de o conjunto valer alguma coisa.
4. Toda rodada sobre o grafico entra no `trials.json` normalmente.

### CORRECAO CRITICA (2026-08-31): a agressao so' existe na ULTIMA SEMANA

**Esta politica foi escrita com uma premissa ERRADA e precisa ser lida
com esta correcao.**

Medido: dump de 24/07 devolveu `AgressionVolBuy/Sell` = ZERO em 2.001
barras; dump de 24/08 a 31/08 (mesma semana) devolveu valores validos em
648 de 648, medianas 44.726 e 43.996. A documentacao do Profit confirma:
o dado **tick a tick e' retido por uma semana**.

E' limite de RETENCAO, nao de carregamento — nenhuma espera resolve. (A
hipotese anterior, "grafico recriado ainda nao baixou o dado", estava
errada; foi o operador quem achou a resposta na documentacao.)

**O que sobra do historico profundo do grafico:**

    OHLC + volume total          ANOS de historico
    agressao (imbalance, etc.)   ULTIMA SEMANA apenas

**Consequencia sobre esta politica**: o grafico continua sendo um
conjunto cego valioso, mas **so' para features que nao usem agressao**.
`imbalance`, `absorcao_dir` e as quatro cores estao TODAS fora — sao de
agressao.

Isso soma-se ao limite ja' registrado (o grafico so' da' barra de TEMPO,
e `z_agf_3` vive em barra de VOLUME). Os dois juntos reduzem o uso
imediato do historico do grafico a praticamente nada:

| feature | barra de tempo? | agressao? | testavel no grafico? |
|---|---|---|---|
| `z_agf_3` | nao (volume) | sim | **NAO** |
| `absorcao_dir` | sim | sim | so' na ultima semana |
| qualquer coisa de OHLC puro | sim | nao | **SIM**, anos |

**O que NAO muda**: a equivalencia ja' fechada (rodou dentro da janela,
2.001 barras) e o pipeline `profit-tape`, que captura via ProfitDLL e
ACUMULA em disco — e' justamente por isso que acumular tape continua
sendo a via principal.

### O que E' e o que NAO E' reproduzivel (medido em 2026-08-30)

    imbalance    EXATO      2001/2001, diferenca maxima 0,000000
    desloc_norm  1 tick     47% das barras, so em open/close
    z-score      2,4e-8     mesma janela, shift e divisor

    NAO reproduzivel:
      barra de VOLUME com relogio de agressao -> o grafico da barra de TEMPO
      qualquer coisa negocio a negocio        -> F exato, tick imbalance

**Consequencia que limita muito o uso imediato**: `z_agf_3`, o unico
sinal validado, vive em barra de VOLUME e **nao e' testavel no
grafico**. `absorcao_dir` seria testavel (barra de tempo) mas ja' recebeu
CONTRA.

### RESTRICOES OPERACIONAIS do Profit, medidas hoje

Estas limitam o que e' possivel extrair, e esquecer delas custou tres
dumps inuteis em 2026-08-30:

**Buffer do console ~2.000 linhas, que enche de TRAS PARA FRENTE.** A
carga de historico processa em ordem cronologica, entao o buffer enche a
partir da barra MAIS ANTIGA e para. Quanto mais historico o grafico tem,
mais CEDO o log termina. Reduzir o log por barra nao resolve (o buffer
conta linhas). A solucao e' `LogDataInicio`/`LogDataFim` no proprio
`.ntsl`, que suprimem so' o `ConsoleLog` e preservam o aquecimento do
z-score.

**"Tick a tick = 1 semana" e' limite de BACKTEST/AUTOMACAO**, e o
indicador nao o respeita — ele roda sobre tudo que o grafico carregou.
Observacao do operador que destravou o impasse.

**Extrair historico longo e' caro em passos manuais**: um dump de ~2.000
linhas por vez, com janela de data ajustada a mao. Para 300 pregoes com
log completo (113 barras/pregao) seriam ~17 dumps. E' viavel, mas
precisa entrar na conta antes de prometer amostra grande.

**Serie continua AJUSTADA**: `WINFUT` no grafico e' o contrato continuo,
com fator `k` que MUDA nas rolagens (medido: 1,020480 ate 11/08 e
1,000000 de 12/08 em diante — a rolagem caiu dentro da amostra). Nivel
de preco nao e' comparavel; razao e'. Qualquer feature que use nivel
precisa de `k` POR PREGAO.

### BACKTEST DO PROFIT NAO E' VALIDACAO

Registrado explicitamente porque a tentacao e' obvia e o custo seria
alto.

O modulo de backtest do Profit so' aceita **estrategias automatizadas**
(o codigo precisa conter funcoes do modulo backtest para ser
classificado como tal). Mas a limitacao que importa nao e' essa: e' que
o backtest dele **nao tem** validacao cruzada purgada, limiar
deflacionado, portao de honestidade nem contador de trials.

Usar o resultado dele como confirmacao importaria uma metodologia muito
mais fraca — exatamente a que os 504 trials e o `t_critico` de 4,07
existem para evitar. Uma curva de capital bonita no Profit seria mais um
SINTOMA batendo, e 2026-08-30 mostrou tres vezes seguidas que sintoma
batendo nao e' causa confirmada.

**Usos legitimos do NTSL**, ambos valiosos e nenhum deles evidencia
estatistica:
  - inspecao VISUAL (ver o que a formula deixou de fora);
  - mecanica de EXECUCAO em conta demo (forward test).

### Ganho de poder, para dimensionar a decisao

    pregoes  folds  t_critico   (limiar_z = 3,055 com 504 trials)
       25      11     4,07
       50      23     3,46
      100      48     3,23
      200      98     3,14
      500     248     3,09

O salto grande e' o primeiro: de 25 para 100 pregoes. Depois satura. A
via principal continua sendo **acumular tape** (zero trial, ja' rodando,
~3 meses ate 100 pregoes), nao extrair historico do grafico.

## DRAWDOWN: desenho da pergunta + pré-voo implementado (2026-08-30k)

Item 2 da lista de pendências. Descendente direto da separação (a)/(b)
feita em 29/08: o CONTRA da Rota B deixou (a) — stop como controle de
drawdown — explicitamente em aberto.

### O que o CONTRA da Rota B muda nesta pergunta

Se E[remanescente | tocou −X] ≈ 0 para todo X, um stop por operação em X
tem custo esperado em expectativa de **aproximadamente zero**: ao
disparar, sai-se em F ≈ nível e abre-se mão de E[close_fim − F] ≈ 0. O
"trade-off expectativa vs drawdown" pode nem ser trade-off em
expectativa — só em variância.

Ressalva que não pode sumir: os IC95 daquela rodada são da ordem de
**±50 pts por operação stopada**. O ponto estima zero; o intervalo não
sabe. "Custo ≈ 0" e "custo desconhecido dentro de ±50" são frases
diferentes, e a segunda é a verdadeira.

### Regra 0 aplicada: de onde vem o drawdown?

Antes de escolher mecanismo, decompor. Cada fonte aponta para um
mecanismo diferente:

| fonte do drawdown | mecanismo |
|---|---|
| poucas operações grandes | stop por operação mais apertado que 500 |
| sequência de perdas médias | circuit breaker / dimensionamento |
| um ou dois dias ruins | limite de perda diária |

O que já está medido aponta em direções conflitantes: o stop de 500 já
morde (4,5%, número de dado contaminado — ver 31/08) e MELHORA a média; o
circuit breaker deu −328 em 7 disparos; +629 num único dia de 25 diz
que a série é dominada por eventos raros.

### Quarto mecanismo, trazido pelo operador: TRAILING de 150 pts

Prática manual do operador no WIN: risco sempre 150 pts; ao andar
+150, stop vai a 0; ao andar +300, stop vai a +150 — sempre 150 atrás
do máximo. Aplicado à mão, às vezes falha; às vezes stopou e depois
andou, às vezes salvou. Empírico, sem estatística.

Três coisas a registrar sobre isso ANTES de qualquer medição:

1. **É mecanismo distinto do que a Rota B testou.** A Rota B mediu stop
   FIXO a partir da entrada. O trailing condiciona em outro evento
   ("chegou a +150 e devolveu 150"), e E[remanescente] nesse evento
   NÃO foi medido. Não se pode importar o CONTRA para cá.
2. **150 é PRIOR, não calibração.** Vem da operação discricionária, em
   outro relógio, outro sinal. `z_agf_3` com h=3 em barras de ~120k
   pode ter caminhos completamente diferentes. Mecanismo antes de
   número — o 150 entra na grade, não como resposta.
3. **Modo de falha específico num sinal de cauda contrarian:** o
   caminho "+150 → volta a 0 (stop) → corre a +400". O trailing corta
   exatamente a cauda que paga se essa forma for frequente em 3 barras.
   É mensurável, e é a pergunta.

Bônus que não é estatístico: mecanizar uma regra manual que "às vezes
falha" tem valor de consistência mesmo a benefício estatístico zero.
Mas o EA não é a operação manual — esse argumento não transfere o
número, só a motivação.

### Estimador, com o argumento de não-viés ANTES do código

- Stop por operação em X, e trailing: replay contrafactual sobre o
  TAPE. Toda operação que aciona sai em F (overshoot medido em zero);
  as demais seguem iguais. Recalcula-se curva, drawdown, Calmar.
  **F é tempo de parada na sequência de negócios** — para o fixo E para
  o trailing (o nível do trailing depende só do passado do caminho).
  Mesmo teorema que salvou a Rota B. Nenhum extremo de barra.
- Limite diário em L: replay sobre a SEQUÊNCIA DE OPERAÇÕES — após
  perda acumulada ≤ −L no dia, as seguintes não existem. Tempo de
  parada na sequência de operações, sem lookahead.
- Variabilidade: bootstrap por bloco de pregão.

### O portão aqui tem forma diferente

Sobre operações EMBARALHADAS (mesma marginal, sequência destruída), um
limite diário AINDA reduz drawdown — por variância, a custo zero. Isso
é real, não artefato. Então o portão não é pass/fail: o benefício
sobre o embaralhado é a componente de **variância**; o excesso sobre o
real é a componente de **regime** ("dia ruim continua ruim"). As duas
são legítimas, significam coisas diferentes, e o relatório precisa
separá-las em vez de somar.

### Seleção e reuso de amostra, às claras

São os mesmos 25 pregões da Rota B. Não é teste de descoberta, então
não há limiar deflacionado para hackear — mas escolher X depois de ver
a tabela ainda é seleção. Grade de X: a mesma congelada {40…200} + o
500 atual + o 150 do operador (já está). Grade de L e regra de aceite:
fixadas no pré-registro, ANTES.

Com 25 dias e um valendo +629, drawdown é estatística de 1 a 3
eventos. "Inconclusivo" precisa estar escrito antes, e é o resultado
mais provável.

### DECISÕES PENDENTES do operador (não são medição)

- **Regra de aceite**: quanto de expectativa se paga por quanto de
  redução de drawdown? Métrica (Calmar? drawdown a expectativa
  constante?) e tolerância.
- **Grade de L** (sugestão para reagir: {200, 300, 500, 800} pts).

### PRÉ-VOO IMPLEMENTADO: `decomposicao-drawdown`

Descritivo, não consome trial. Dois passos, porque o replay em lote
**não persistia as operações** — só imprimia o resumo e a lista morria
com o processo:

1. `GestorDeRisco.historico_detalhado`: registro rico por operação
   (lado, preços, barras, P&L, motivo). `historico_pnl` e
   `historico_operacoes` inalterados. **Não é mudança de
   comportamento** — o gestor decide igual, só anota mais.
   `ea-replay-lote` passa a persistir em
   `data/research/operacoes_replay.parquet` (`--saida-operacoes`).
2. `research/decomposicao_drawdown.py` + comando
   `decomposicao-drawdown`: os 3 maiores drawdowns, cada um decomposto
   em três parcelas (3 piores operações / pior dia / maior sequência,
   cada uma sobre a profundidade). **Regra de classificação fixada
   antes de ver número**: fonte dominante = maior parcela, só se
   ≥ 0,50; senão DIFUSO. As parcelas se sobrepõem, não somam 1, e uma
   pode passar de 1. Robustez: jackknife por pregão e bootstrap por
   bloco sobre o drawdown máximo.

Conferido à mão (série de 8 operações: drawdowns 260 e 40; parcelas
1,077 / 0,692 / 0,769). 8 testes novos, 367 no total.

Rodar: `ea-replay-lote -c config/ea_venda_apenas.yaml` (persiste), depois
`decomposicao-drawdown`.

## DECOMPOSIÇÃO RODOU — e a premissa do drawdown caiu (2026-08-31)

### Antes do resultado: três rodadas, uma válida

| rodada | árvore | ops | P&L | Calmar | status |
|---|---|---|---|---|---|
| 28/08 | `data/raw` local (mistura desconhecida) | 157 | +418 | 0,23 | **contaminada** |
| 31/08 a | `D:\backup_raw` (12 dias com backfill em dobro) | 147 | +3883 | 2,85 | **contaminada** |
| 31/08 b | `data/curated` | 99 | **+6356** | **4,08** | **válida** |

Prova do mecanismo: `duplicatas` em 07-24 → 100% do dia entregue duas
vezes, campos idênticos, reentrega benigna. Curated deduplica certo.
Validação interna do replay: **os 13 dias limpos batem operação por
operação** entre a rodada a e a b (07-29 +111, 08-04 +767, 08-11 +1284,
…, 08-27 +655). Replay determinístico confirmado; a diferença inteira
vem dos 12 dias dobrados (−363 → +2110).

O conflito de documentação se resolve: a errata de 21/08 ("histórico
sem duplicata") olhou um backfill limpo; o "volume real é metade" de
22/08 olhou uma árvore com backfill repetido. E os 5 dias de realtime
batem com curated a menos de 250 linhas: **o stream ao vivo é limpo, o
EA em produção vê o equivalente ao curated.** O relógio do EA ao vivo
NÃO está fora do relógio do research.

Decisão do operador: default de `ea-replay-lote --raiz-raw` passa a
`data/curated` — única árvore completa E limpa no fluxo real
(`data/raw` local = só o último dia; backup = histórico com dobras).

### A decomposição sobre dado válido

- 99 ops, 25 pregões, +6356. Drawdown máximo **1556 pts = R$311 (6,2%)**.
- Jackknife por pregão: [1056 ; 1788]. Bootstrap IC95: **[757 ; 2898]**.
  Estatística de um evento, como previsto.

| # | prof. | ops | dias | 3 piores | parc. OPS | DIA | SEQ | rótulo |
|---|---|---|---|---|---|---|---|---|
| 1 | 1556 | 16 | 6 (07-24→07-31) | −371, −336, −296 | 0,64 | 0,47 | 0,66 | sequência |
| 2 | 1056 | 6 | 2 | −601, −256, −166 | 0,97 | 0,76 | 0,97 | operações |
| 3 | 969 | 9 | 2 | −626, −576, −421 | 1,67 | 0,65 | 0,88 | operações |

**Trecho 1** é a primeira semana inteira, sem fonte dominante: o rótulo
"sequência" ganhou de "operações" por 0,02 — margem sem informação.
Limitação da regra fixada antes, registrada e não alterada: "difuso" só
dispara se NENHUMA parcela passa de 0,50, e aqui as três passaram.
Numa regra futura, difuso deveria ser "nenhuma domina as outras", não
"todas abaixo de 0,50".

**Trechos 2 e 3** são dominados por operações isoladas: −601, −626,
−576, −421.

### A premissa caiu

"Calmar 0,23, drawdown grande relativo ao retorno" — a motivação da
pergunta inteira — era artefato de dado dobrado. Sobre dado válido:
Calmar 4,08, R$311 de drawdown em R$5.000 ao longo de 25 dias.
**"Stop como controle de drawdown" está ENCERRADO como pergunta de
pesquisa** — não por ter sido respondida, mas porque a premissa era
falsa. Adicionar mecanismo para melhorar Calmar 4 é otimizar o que não
está quebrado, pagando ±50 pts/op de incerteza em expectativa.

### O achado real: o stop catastrófico não faz o que diz

Stop catastrófico = 500 pts (2% de R$5.000). Na rodada válida, três
perdas brutas de **−590, −615 e −565** — todas além do limite.
`risco.py::motivo_de_saida` checa `excursao_contra` só no CLOSE da
barra: se a barra fecha 615 contra, sai em 615. É a falha de
granularidade da Rota B, no mecanismo que já está vivo protegendo
capital.

Stop contínuo na fita teria capado os três em ~−511 líquidos: **270 pts
a menos**, trecho 2 de 1056 para ~966, trecho 3 de 969 para ~789. Não é
mecanismo novo; é fazer o existente cumprir a própria especificação.

É **sessão de desenho**, não patch: o EA decide na barra fechada; checar
por negócio muda o caminho de execução (callback de trade, latência,
thread). Já estava adiado como "Rota B redesign — checagem contínua".
Agora tem motivo concreto e três números. Pendência: conferir no
`operacoes_replay.parquet` o `motivo` dessas três operações.

### Para entender depois, não agora

EA rende +64/op sobre curated; o research mediu +18/op para o mesmo
sinal no mesmo dado. Compatível com ruído (EP ~32), mas a direção pede
olhar: o EA executa 99 de ~178 gatilhos por "uma posição de cada vez".
Se isso seleciona sistematicamente o primeiro gatilho de cada
aglomerado, é um filtro que ninguém pré-registrou.

## STOP CONTÍNUO: pré-voo instrumentado, três regimes de saída (2026-08-31b)

Sessão de DESENHO (regra 7) para a pendência aberta ontem: fazer o gestor
de risco reagir por negócio em vez de esperar o fechamento da barra.
Nenhuma mudança de comportamento do EA foi feita — só instrumentação de
medição, que não gasta trial.

### A premissa foi confirmada antes de qualquer coisa

Pendência explícita deixada ontem ("conferir no `operacoes_replay.parquet`
o `motivo` dessas três operações") — fechada:

| lado | entrada | saída | pnl líquido | motivo |
|---|---|---|---|---|
| −1 | 174090 | 174705 | −626 | STOP CATASTROFICO: 615 pts contra (limite 500) |
| −1 | 169055 | 169645 | −601 | STOP CATASTROFICO: 590 pts contra (limite 500) |
| −1 | 171630 | 172195 | −576 | STOP CATASTROFICO: 565 pts contra (limite 500) |

As três piores logo abaixo (−436, −421, −371) saíram por tempo, todas
abaixo de 500. **Todas as três são de venda.** Ao contrário do drawdown,
esta premissa se sustenta: o mecanismo vivo não cumpre a própria spec.

### Descoberta de percurso: o caminho por trade já existe

Ao vivo, `_on_trade` já enfileira TODO negócio e o loop principal já chama
`processar_trade_bruto(t)` para cada um — o que acontece é que o núcleo
retorna cedo quando a barra não fecha. Não é preciso callback novo, thread
nova nem mudança de latência: a cadência por negócio já está lá. Isso
torna a implementação cirúrgica, **não** dispensa o desenho.

### O risco de desenho, e por que ele precisa de número antes

O stop de 500 é seguro de CAUDA, não stop tático. Morde em 3 de 99
operações no close. A pergunta que decide tudo: **quantas operações tocam
−500 no meio da barra e voltam?** Se forem as mesmas 3, é conformidade
pura. Se dobrar ou mais, o guarda de cauda vira stop TÁTICO — e o projeto
já tem veredito sobre o que stop apertado faz num sinal de ~43% de acerto
que ganha por magnitude.

O relatório existente NÃO respondia isso: `mae.py` calculava
`mae_intrabar` mas só reportava p90/p99/máximo dele — a contagem no
limiar (`n_teria_batido_stop`) era calculada **só sobre `mae_close`**.

### ERRATA: o número antigo media o regime errado

`pnl_medio_com_stop_hipotetico` substituía o resultado por `-stop` sempre
que `mae_close` cruzava. Isso modela o stop saindo EXATAMENTE no limite —
que é o comportamento do regime CONTÍNUO, não do que roda hoje (o de hoje
sai no close da barra que cruzou: −615, não −500). **Aquele número media
o regime proposto e o rotulava como o atual; os dois regimes nunca tinham
sido separados.** Removido, com errata no relatório gerado.

### O que o instrumento passa a medir

- **Frequência** no limiar, nos dois regimes, quebrada POR LADO (o EA roda
  venda-apenas; a venda já bate mais no close, 6,2% contra 4,0%).
- **Conformidade**: o excesso do close além do limite quando cruza —
  média/mediana/máximo. É a falha de granularidade, medida (615 − 500 = 115).
- **Três regimes** de P&L bruto médio: sem stop / stop no CLOSE (preço real
  da barra que cruzou) / stop CONTÍNUO (~ −S na impressão que cruza).
- **Conjunto MARGINAL** — as operações com `mae_intrabar ≥ S` mas
  `mae_close < S`, as que só o contínuo mata: quantas são, qual o P&L
  delas se deixadas correr, e **quantas terminaram positivas**. Este é o
  número do veredito.

Limitação registrada e não corrigida: o regime contínuo é OTIMISTA por uma
granularidade de tick (modela saída exata em −S, mas uma impressão pode
pular o limite). High/low de barra não carrega a sequência de impressões
necessária para medir esse pulo.

Conferido à mão antes dos testes (regra 4): duas vendas, entrada 100, h=3,
stop=50 — 11 valores esperados calculados no papel, todos batendo
(marginal +10 positiva; excesso 15; médias −15,0 / −27,5 / −50,0).

### Ainda EM ABERTO — nada foi decidido

Rodar `features` + `mae-analise --feature z_agf_3 --horizonte 3
--threshold-entrada 1.4 --stop-catastrofico-pontos 500`. Só depois do
resultado da linha de VENDA se escreve o pré-registro, com teto de
frequência comprometido ANTES de ver o efeito no P&L.

Decisões de desenho já acordadas, a congelar no pré-registro:
1. Escopo: **só** o stop catastrófico vira contínuo. Saída por tempo
   continua na barra (é o relógio que o research mediu). Rota B fora.
2. Preço de saída: a impressão que cruzou, não o limite.
3. Reentrada na mesma barra: **proibida** (hoje sair no close já impede
   entrada naquela barra; liberar seria uma segunda mudança disfarçada).
4. `bar_id_saida`: id da barra em formação, com a saída marcada como
   intrabarra no log — senão `barras_duracao` mente.
5. Negócio descartado em `queue.Full`: o stop fica armado, o descarte só
   adia para a próxima impressão. Limitação conhecida, não tratada.

Critério de decisão será de **CONFORMIDADE, não de P&L**: os 270 pts em 3
operações não calibram nada (regra 3).

## PRÉ-REGISTRO: stop contínuo, não-inferioridade (2026-08-31c) — CONGELADO

### Resultado do pré-voo que motivou este pré-registro

`mae-analise` sobre curated, 336 gatilhos OOS, limiar 500:

| | close (hoje) | contínuo (proposto) | marginais |
|---|---|---|---|
| agregado | 17 (5,1%) | 33 (9,8%) | 16 |
| compra | 7 (4,0%) | 17 (9,8%) | 10 |
| **venda** | **10 (6,2%)** | **16 (9,9%)** | **6** |

**O modo de falha que se temia NÃO se materializou**: 0 de 16 marginais
terminaram positivas. O stop contínuo não está cortando caudas ganhadoras
neste sinal — as operações que tocam −500 intrabar e não no close são
perdedoras (pnl médio −390,3 se deixadas correr).

**Mas apareceu um custo que o registro de 31/08a não contava.** As
marginais terminam em −390,3 e o stop contínuo as mata em −500: cortar
cada uma custa ~110 pts. O "270 pts a menos" registrado antes contou só a
economia nas três que já batiam, e não contou que o contínuo **também
dispara onde hoje não dispara** (venda: 10 → 16).

Conformidade, medida: excesso do close além do limite — mediana 65,
máximo **305**. Um "stop de 500" que sai em −805 no pior caso não é um
stop de 500 pontos.

Agregado dos três regimes: sem stop +11,8 > close +9,7 > contínuo +9,5.
Os três em ordem decrescente — o stop, em qualquer forma, custa
expectativa. Isso não é argumento contra ele: é o prêmio do seguro.

### Motivação

O stop catastrófico é seguro de CAPITAL, não dispositivo de expectativa.
Ele não cumpre a própria especificação: checado só no close, deixa a perda
chegar a −805 num limite de 500. A mudança se justifica por
**conformidade e limitação de cauda**, não por P&L — e a diferença entre
os dois regimes de stop (+9,7 contra +9,5, com 33 de 336 afetadas) é
indistinguível de ruído.

**Se alguém apresentar esta mudança como ganho de 270 pts, está lendo
errado.**

### O que exatamente muda

Só o stop catastrófico passa a ser avaliado a cada negócio. Nada mais.
Congelado junto (decisões de desenho de 31/08b):

1. Saída por tempo continua na barra (é o relógio que o research mediu).
   Rota B fora de escopo (parada por CONTRA).
2. Preço de saída: a impressão que cruzou, não o limite.
3. Reentrada na mesma barra da saída: **proibida** (hoje sair no close já
   impede entrada naquela barra; liberar seria segunda mudança disfarçada).
4. `bar_id_saida` = id da barra em formação, saída marcada como intrabarra
   no log — senão `barras_duracao` mente.
5. `queue.Full`: o stop fica armado, o descarte só adia para a próxima
   impressão. Limitação conhecida, não tratada.

### CRITÉRIO DE DECISÃO — congelado ANTES da rodada

Enquadramento: **não-inferioridade, não superioridade.**

> Sobre o lado de **VENDA apenas**, IC95 bootstrap (bloco de pregão, 2000
> reamostragens, semente fixa) da diferença **pareada**
> `(stop contínuo − stop close)` em pts/operação.
> **Aceita** se o limite INFERIOR do IC for maior que **−3,0 pts/op**.
> **Rejeita** caso contrário, INDEPENDENTEMENTE do sinal da média.

Pareado de propósito: os dois regimes agem sobre as MESMAS operações, e a
diferença é exatamente zero em toda operação não afetada — comparar duas
médias soltas jogaria fora o pareamento e inflaria o ruído.

Venda apenas: o EA não opera compra, e a compra tem MAIS marginais que
operações que já batem (10 contra 7) sem edge nenhum (−1,4 bruto, abaixo
do custo) — ela contamina o agregado com um lado que não está em jogo.

O −3,0 foi fixado pelo operador **antes** de a quebra por lado existir.
Referência de calibração: a venda rende +26 bruto, custo ~11, ~15 pts/op
líquidos; ceder 3 é ceder ~1/5 do edge líquido em troca do teto da cauda.

Congelado no código como `mae.LIMITE_NAO_INFERIORIDADE_PTS`, **não**
exposto como opção de CLI (mesmo padrão de `reversao.py`): mudar exige
editar código e escrever pré-registro novo.

Não gasta trial: engenharia de risco sobre sinal já validado pelo IC.

### Estado

Instrumento entregue em `entregue-v1.49`. **Resultado ainda não observado.**

## RESULTADO: não-inferioridade deu CONTRA por 0,28 (2026-08-31c2)

Critério congelado: limite inferior do IC95 pareado na venda > −3,0 pts/op.

| lado | sem stop | stop CLOSE | stop CONTÍNUO | dif pareada | IC95 | afetadas |
|---|---|---|---|---|---|---|
| compra | −1,4 | +0,6 | −3,3 | **−3,94** | [−7,94 ; +0,21] | 16 |
| venda | +26,0 | +19,4 | +23,2 | **+3,86** | **[−3,28 ; +13,42]** | 16 |

**VEREDITO: CONTRA.** Observado −3,28 contra o critério de −3,0.

A quebra por lado se justificou sozinha: o agregado (+9,7 contra +9,5)
escondia dois efeitos de sinal oposto e magnitude parecida. Decidir pelo
agregado teria sido decidir sobre um número que não descreve nenhum dos
dois lados.

**O que foi rejeitado não é "o stop contínuo é pior".** A média pareada na
venda é favorável (+3,86). O que falhou foi demonstrar não-inferioridade
com 16 operações afetadas em 162 e um IC de 17 pontos de largura.

**Saídas erradas, registradas para não parecerem razoáveis depois**:
baixar o limiar para −4; usar a média em vez do IC; e sobretudo **rodar de
novo com outra semente** — com 2000 reamostragens o limite inferior tem
erro de Monte Carlo próprio e 0,28 pode caber dentro dele, então outra
semente provavelmente passaria. `semente=20260831` estava congelada no
pré-registro exatamente para isso não ser uma opção.

Lição de construção de instrumento (ver 31/08d para a conta): o gate
virava com **2 pregões** de dado novo. Antes de congelar um limiar,
verificar se o instrumento resolve a diferença que o limiar decide.

## PRÉ-REGISTRO: stop contínuo como CONFORMIDADE (2026-08-31d)

> **Status: aguardando congelamento pelo operador.** Nada implementado até
> este documento ser confirmado.

### O que veio antes, e por que este pré-registro existe

O pré-registro de não-inferioridade (31/08c) deu **CONTRA**: limite
inferior do IC95 pareado na venda em −3,28 contra um critério de −3,0.
**Esse veredito fica.** Não é reaberto, não é re-rodado com outra semente,
não tem o limiar ajustado. A pergunta "o P&L veta a mudança?" foi feita e
a resposta foi "não dá para demonstrar que não veta".

O que se aprendeu ao analisar o resultado é que **aquele gate não tinha
resolução para a pergunta**. Conta: a distância da média (+3,86) ao limite
inferior (−3,28) é 7,14; para passar de −3,0 bastaria essa distância cair
para 6,86 — 4%. Como a largura do IC escala com 1/√(pregões):

```
√(n/25) = 7,14/6,86 = 1,041   →   n ≈ 27 pregões
```

**Dois pregões separavam CONTRA de FAVORÁVEL.** Um gate que vira com dois
dias não estava medindo o dado; estava medindo quais dois dias entraram —
ainda mais com só 16 de 162 operações afetadas. O erro foi de construção,
e é meu (Claude): escolhi −3,0 sem verificar se o instrumento distinguia
−3,0 de −3,5. Não distinguia. Fica como lição registrada: **antes de
congelar um limiar, verificar se o instrumento resolve a diferença que o
limiar pretende decidir.**

Isso NÃO reabre o veredito. O que faz é mudar qual pergunta decide.

### A pergunta certa é de conformidade, não de expectativa

O stop catastrófico é seguro de CAPITAL. Ele não cumpre a própria
especificação: checado só no fechamento de barra, deixa a perda chegar a
−805 num limite de 500 (excesso mediana 65, máximo 305, medido em 336
gatilhos OOS).

Isso não é hipótese sobre o mercado; é um defeito de implementação de uma
spec já decidida. E ele **já contaminou análise real**: a decomposição de
drawdown de 31/08 concluiu que os trechos 2 e 3 eram "dominados por
operações isoladas" — as tais −626, −601, −576, que são desse tamanho
justamente porque o stop sai no close em vez de no limite. Toda
decomposição, curva de patrimônio e replay futuro carrega o defeito
enquanto ele existir. Corrigi-lo não muda a decisão de trading; muda a
confiabilidade de todo instrumento que mede o EA.

### Motivação declarada pelo operador

Corrigir um defeito conhecido para que resultados futuros não precisem ser
lidos com a ressalva "isto pode estar afetado pelo bug do stop".

### O que exatamente muda

Só o stop catastrófico passa a ser avaliado a cada negócio, no mesmo
`processar_trade_bruto` que já recebe todos eles. Congelado junto:

1. Saída por tempo continua avaliada na barra (é o relógio que o research
   mediu). Rota B permanece fora de escopo.
2. Preço de saída: a impressão que cruzou, não o limite.
3. Reentrada na mesma barra da saída: **proibida**.
4. `bar_id_saida` = id da barra em formação, com a saída marcada como
   intrabarra no log.
5. `queue.Full`: o stop fica armado; o descarte só adia para a próxima
   impressão. Limitação conhecida, não tratada.

### CRITÉRIO DE DECISÃO — conformidade, determinístico

> No replay dos 25 pregões de `data/curated`, **nenhuma operação fecha com
> excursão contra superior ao limite mais a granularidade da impressão que
> cruzou**. Verificado operação a operação em `operacoes_replay.parquet`,
> não por agregado.
>
> FAVORÁVEL se a condição vale para todas as operações.
> CONTRA se qualquer operação a viola — o que significaria que a
> implementação não faz o que diz, e o veredito seria sobre o código, não
> sobre o mercado.

Sem IC, sem bootstrap, sem tamanho de amostra: é verificação de
especificação. Não gasta trial.

### OS TRÊS TERMOS ACEITOS, escritos sem maquiagem

Registrados explicitamente para que ninguém (inclusive nós) leia esta
mudança depois como se ela tivesse sido validada por P&L:

1. **A pergunta de P&L foi feita e voltou inconclusiva.** Efeito estimado
   +3,86 pts/op na venda, IC95 [−3,28 ; +13,42]. **O sinal do efeito é
   desconhecido.** Este pré-registro aceita um efeito de expectativa
   desconhecido em troca de um mecanismo que cumpre a spec. É decisão do
   operador, não conclusão estatística.

2. **As 6 operações extras vêm junto e não dá para separar.** Não existe
   variante que corrija a conformidade sem armar o stop contra preço
   intrabarra: sair no limite exigiria preenchimento num preço que já
   passou. Na venda o stop passa de 10 para 16 disparos em 162 operações;
   as 6 novas custam ~110 pts cada (terminam em −390 em média se deixadas
   correr, e o stop as mata em −500).

3. **Risco residual nomeado.** A linha de compra deu −3,94 [−7,94 ; +0,21].
   Se o +3,86 da venda for ruído em torno de um valor verdadeiro parecido
   com o da compra, o custo é ~4 pts/op sobre ~15 pts/op de edge líquido.
   **Não dá para descartar isso com o dado atual.**

### O que este pré-registro NÃO autoriza

- Reabrir o veredito de não-inferioridade de 31/08c.
- Apresentar a mudança como ganho de P&L, ou citar os "270 pts" de 31/08a
  (número que contava só a economia nas três que já batiam, sem os
  disparos novos).
- Estender a checagem contínua a alvo, stop tático ou Rota B — cada um
  exigiria pré-registro próprio.

### Reexame previsto

Quando a fita acumulada dobrar (~50 pregões), refazer a medição dos três
regimes **como acompanhamento**, para saber o sinal real do efeito de
expectativa. Isso não é gate: a mudança já terá sido feita por
conformidade. Serve para saber quanto ela custou.

## DIAGNOSTICO 2026-08-31: absorcao_dir E desloc_norm disfarcado, e o esforco NAO tem cauda

653 barras de 5m, 24/08 a 31/08/2026, com agressao valida em todas.
Categoria `features`: descritivo, zero trial.

### 1. `absorcao_dir` correlaciona 0,9883 com `-desloc_norm`

Com a agressao funcionando perfeitamente, a formula mede praticamente a
MESMA coisa que media quando a agressao vinha ZERADA.

    desvio de imbalance    0,1175
    desvio de desloc_norm  0,4864     -> 4,1x maior
    corr(imbalance, desloc_norm)  +0,862
    corr(absorcao_dir, -desloc_norm)  +0,9883

Dois efeitos somados: `desloc_norm` domina a subtracao por 4x em desvio,
e o pouco que `imbalance` traria ja' esta contido nele (quem agride
empurra o preco).

**Isso amarra tres achados que pareciam separados**: a formula ser
sub-gaussiana, o CONTRA nas 12 celulas, e a ausencia de casos A abaixo.
Todos sintomas do mesmo defeito — `absorcao_dir` e' `desloc_norm`
disfarcado.

E valida por outro caminho a exigencia de `z_desloc_norm` como controle
obrigatorio no pre-registro: sem ele, um resultado positivo da absorcao
seria indistinguivel de um resultado do deslocamento puro.

### 2. O caso A e' RARO POR CONSTRUCAO

Das 34 barras pintadas: **ZERO casos A**, 18 `B_queda_sem_esforco` e 16
`B_alta_sem_esforco`.

    familia vermelha (z >= +1,75): z_imbalance de -2,09 a +0,07, mediana -1,25
    familia aqua     (z <= -1,75): z_imbalance de +0,22 a +1,98, mediana +0,91

O `imbalance` esta sistematicamente no sinal OPOSTO ao que o caso A
exige. Nao e' o limiar: com `LimiarImb = 0` ainda so' 1 caso A de 34.

A razao e' aritmetica. Para `z_absorcao_dir` ficar alto, `desloc_norm`
precisa ser baixo; como os dois andam juntos (+0,862), `imbalance`
tambem fica baixo — o sinal contrario ao do caso A.

**Consequencia para o indicador**: vermelho e aqua vao aparecer
raramente. Amarelo e fucsia sao o que a formula de fato detecta: livro
fino.

### 3. MINHA HIPOTESE DO ESFORCO ESTA REFUTADA

Registrado em 2026-08-30b: "para existir cauda, a formula precisa de um
termo ILIMITADO — `vol_agr / range_ticks` e' ilimitado". **Errado.**

    esforco (contratos por tick)
      p50 2.133 | p95 3.177 | p99 3.621 | max 4.268
      razao p99/p50 = 1,70x     (uma variavel de cauda daria 5x, 10x)

    esforco mediano por leitura:
      nao_pintou           2.130
      B_queda_sem_esforco  2.099
      B_alta_sem_esforco   2.323

Nao separa nada, e nao tem cauda.

**Causa**: `corr(vol_agr, amplitude_ticks) = +0,892`. Barra grande tem
mais volume E mais amplitude; dividir um pelo outro CANCELA os dois. A
correlacao do esforco com a amplitude cai para +0,095 — a divisao
normalizou bem demais.

### A licao, que vale mais que o esforco

Eu previ a propriedade "ilimitado" e conclui "portanto tem cauda". **Sao
coisas diferentes**: `absorcao_dir` e' limitado e sem cauda; `esforco` e'
ilimitado e tambem sem cauda.

Para a proxima formalizacao: nao basta o termo ser ilimitado — ele
precisa MEDIR ALGO QUE O OUTRO TERMO NAO MEDE. Uma razao entre duas
quantidades que ja' andam juntas e' quase constante por construcao, e
isso da' para verificar ANTES de gastar trial, com uma correlacao.

**Nenhuma direcao substituta esta proposta aqui.** Propor uma agora
seria escolher depois de ver o resultado — e sem um mecanismo que
sobreviva a esta checagem de redundancia, nao ha' pre-registro a
escrever.

## TRIAGEM DE FEATURE: a etapa que faltava entre formalizar e pre-registrar (2026-08-31)

`profit-tape triagem <coluna>` — categoria `features`, **zero trial**.
Olha so' a FORMA da variavel e **nunca toca em retorno**.

### O buraco no processo

O pipeline ia de "formalizei uma feature" direto para "pre-registrei um
teste". Duas formalizacoes morreram nessa lacuna, e as duas por
propriedades que uma correlacao revelaria em segundos:

| candidata | custo | defeito | como seria pego |
|---|---|---|---|
| `absorcao_dir` | **12 trials + CONTRA** | `corr(., -desloc_norm) = 0,9883` | redundancia |
| `esforco` | 0 (pego a tempo) | `corr(vol, amplitude) = +0,892` | razao entre partes |

A licao comum: **eu previ uma propriedade e conclui outra.** "Ilimitado"
nao implica "tem cauda"; "combina dois termos" nao implica "mede algo
novo". Prever nao e' verificar.

### As tres checagens

**Redundancia** — correlacao com cada feature existente E com o negativo
dela. O sinal engana: -0,988 parece "oposto, logo diferente", mas e' a
mesma informacao trocada de sinal. Acima de 0,95 em modulo, a candidata
e' uma feature existente renomeada.

**Cauda** — fracao de |z| >= 2,5 desvios, comparada com os 1,24% de uma
normal. Abaixo de metade disso, a variavel e' sub-gaussiana e uma
hipotese sobre eventos extremos nao tem o que medir.

**Razao entre partes** — se a candidata e' uma razao, mede a correlacao
entre numerador e denominador. Acima de 0,7, a razao e' quase constante
por construcao, e isso NAO aparece olhando so' a razao pronta.

### Erro meu no primeiro criterio de cauda

Usei a razao `p99/p50` do |z| com corte em 2,0. Ela **errava os dois
casos reais**: aprovava `absorcao_dir` (2,34x) e dava ao `esforco` mais
cauda que uma normal (4,30x contra 3,85x).

Razao entre dois quantis e' instavel e nao se compara a referencia
nenhuma. Trocado pela fracao acima de 2,5 desvios contra a normal, que
acerta os dois: 0,00x para `absorcao_dir`, 1,23x para o `esforco`.

O criterio errado so' apareceu porque rodei nos dois casos historicos
antes de aceitar o modulo — a mesma pratica que este comando existe para
institucionalizar.

### Rodada sobre o parquet real (25 pregoes, 2.723 barras)

    TRIAGEM DE `absorcao_dir`  ->  REPROVA
      !! REDUNDANTE com `desloc_norm` (correlacao -0,9863)
      !! SEM CAUDA: 0,0% acima de 2,5 desvios contra 1,24% de uma normal

           feature  correlacao  redundante
       desloc_norm     -0,9863        True
     z_desloc_norm     -0,9679        True
    tick_imbalance     -0,7890       False
         imbalance     -0,7807       False

O -0,9863 sobre 2.723 barras confirma o -0,9883 medido sobre as 653 do
dump. E apareceu um par que eu nao tinha visto: `z_desloc_norm` tambem
sai redundante (-0,9679).

Faixa observada de `absorcao_dir`: **[-0,8467; +0,8968]** contra o teto
teorico [-2,+2] — a mesma saturacao registrada em 2026-08-30b, agora
reproduzida por outro caminho.

### Candidata DERIVADA: `--expr`

A primeira versao so' aceitava coluna GRAVADA e falhava com "nao tem a
coluna `esforco`" — inutil para o caso de uso principal, que e' triar
candidata NOVA, por definicao ainda nao gravada.

    profit-tape triagem esforco \
      --expr "vol_agr / ((high - low) / 5)" \
      --numerador vol_agr --denominador "(high - low) / 5"

Usa `DataFrame.eval`, cujo parser e' restrito a operacoes sobre colunas:
nao aceita import, chamada arbitraria nem acesso a atributo.

### `esforco` JA' EXISTIA NO PIPELINE: correlacao +1,0000 com `absorcao`

A rodada de `esforco` no parquet real devolveu:

    !! REDUNDANTE com `absorcao` (correlacao +1,0000)

`flow.py`, linha 126, desde antes desta sessao:

    barras["absorcao"] = barras["vol_agr"] / np.maximum(range_ticks, 1.0)

E' **exatamente** a formula que eu propus como "o termo que falta", com
o comentario "muito volume andando pouco preco = absorcao alta" logo
acima. Eu li o `flow.py` varias vezes hoje — a definicao estava a poucas
linhas do `absorcao_dir` que eu vinha editando. Nao vi.

**A triagem pegou um erro que ela nao foi projetada para pegar.** Eu a
construi pensando em redundancia entre feature NOVA e existentes; ela
achou uma feature "nova" que E' uma existente.

### DUAS AFIRMACOES MINHAS SOBRE O `esforco`, AS DUAS ERRADAS

**"Nao tem cauda"** — baseada em `p99/p50 = 1,70x` sobre 653 barras, com
a metrica que eu mesmo depois identifiquei como errada. Com a metrica
certa e 2.723 barras: **1,33x a cauda de uma normal**, faixa de 290 a
5.198 contratos/tick, 18x entre extremos.

**"Razao entre partes correlacionadas fica quase constante"** — falso
como criterio. Duas medicoes derrubaram:

1. `esforco` tem corr +0,888 entre as partes E cauda mais gorda que a
   normal. Atenuar nao e' anular.
2. Uma razao construida quase CONSTANTE de proposito (ruido de 0,2%)
   TAMBEM passa no teste de cauda — porque o z-score e' **invariante a
   escala**, e padronizar apaga justamente a informacao de "quao pequena
   e' a variacao".

O criterio nao estava mal calibrado: **media a coisa errada**, e nenhum
limiar conserta. **Removido do veredito**, mantido como diagnostico.
Criterio que reprova por motivo errado gasta a confianca de todos os
outros.

Sobra a REDUNDANCIA como unico criterio bloqueante — e' o que pegou os
dois casos reais (`absorcao_dir` com -0,9863, `esforco` com +1,0000).

### O que a triagem NAO faz

Nao diz se a feature PREDIZ alguma coisa. **PASSA nao autoriza nada** —
so' significa que nao da' para descartar olhando a forma. **REPROVA e'
bloqueante** para pre-registro.

## PRE-REGISTRO: ABSORCAO DE BARRA (CONGELADO 2026-08-31)

> **CONGELADO pelo operador**, antes de qualquer contato com retorno.
> Toda a fase de desenho olhou SO' a forma das variaveis (categoria
> `features`): frequencia, distribuicao e redundancia. **Nenhum retorno
> foi consultado.**

### De onde a hipotese veio, e por que isso importa

Nao veio de mim procurando formula com propriedade bonita — as duas que
tentei assim morreram no mesmo dia (`absorcao_dir` gastou 12 trials;
`esforco` ja' existia como `absorcao`). Veio da leitura de tela do
operador, confrontada com material proprio dele sobre absorcao x
exaustao.

**A formula antiga media o OPOSTO do conceito.** `absorcao_dir` tem
extremos quando `|desloc_norm|` e' GRANDE (marubozu, mediana 0,807 nas
barras pintadas); absorcao e' `|desloc_norm|` PEQUENO (doji com pavio).
Medido: correlacao do evento novo com `z_absorcao_dir` = **-0,03**. Sao
coisas ortogonais, e o CONTRA das 12 celulas nao diz nada sobre esta.

### Hipotese

> Uma barra em que o preco ANDOU e VOLTOU, com esforco grande, apos um
> movimento local relevante, indica reversao desse movimento.

Absorcao = **esforco grande, alcance grande, resultado nulo**. Os tres
sao necessarios; o terceiro sozinho e' indistinguivel de barra parada.

### Definicao do evento — CONJUNCAO, nao formula unica

    |desloc_norm|  <=  0,25      resultado nulo
    z_amplitude    >=  0,50      alcance (vs 50 barras)
    z_vol_agr      >=  0,50      esforco  (vs 50 barras)

**Conjuncao de proposito.** Combinar os tres num numero unico repetiria
o erro do `absorcao_dir`, em que a subtracao escondia dois casos
opostos.

Cortes escolhidos por FREQUENCIA de inspecao (~4,2/pregao), mesmo
precedente do limiar 1,75 — nunca por resultado.

### Contexto (habilitador de direcao)

    mov6 = (close[t-1] - close[t-7]) / range_medio_50
    habilitador: |mov6| >= 3
    direcao: CONTRARIA ao movimento (mov6 > 0 -> viés de BAIXA)

**Por que o contexto e' obrigatorio**: o `imbalance` NAO serve para dar
direcao aqui. Medido nos eventos: mediana 0,014 contra 0,085 no geral —
seis vezes menor, e nenhum evento passa de 0,05. Faz sentido
mecanicamente: **absorcao equilibra o fluxo por definicao**, entao
neutraliza justamente o campo que mediria o lado.

**Tres definicoes de contexto foram testadas e NAO separaram** (todas
descritivas, sem retorno):

    contagem de candles consecutivos : eventos 21,4% vs base 22,5% (0,95x)
    rompimento de topo/fundo de 20b  : so' 7 de 28 eventos tem lado
    referencias do dia anterior      : razao 0,75-0,90x, ou seja, MENOS
                                        que a base

**A que separou** foi movimento em multiplos do range, janela curta:
mediana 3,42 nos eventos contra 0,88 na base. Janela de **6 barras**
(~30 min) derivada da descricao do operador sobre o tamanho da perna,
nao da varredura.

**K = 3, nao 5.** O operador propos 5; com 5 o lado de alta projeta 17
eventos, abaixo do minimo de 30. Reduzido para 3 por RESTRICAO DE
AMOSTRA, com nenhum retorno consultado.

### Estimador

Retorno de **2 barras** apos o evento, no sentido do viés, BRUTO.
Horizonte fixado pelo operador.

    retorno = (close[t+2] - close[t]) * lado,  lado = -sign(mov6)

Uma amostra contra zero, POR LADO SEPARADO. Purga estrutural de dia
inteiro (janela nunca atravessa o pregao).

### Metodologia, fixada ANTES

- Barra de TEMPO 5m, `features_tempo/sym=WINFUT/tf=5m`.
- `so_agressao=True` — RLP imprime dentro do spread e nunca faz extremo
  (medido duas vezes), entao infla volume no nivel sem ser absorcao.
- Os DOIS lados reportados sempre, mesmo o que nao der nada.
- n < 30 no lado: REPORTADO, nunca interpretado.
- Significancia exige as DUAS evidencias: |t| >= limiar deflacionado
  para 2 comparacoes E IC95 de bootstrap por pregao excluindo zero.
- **Controles pre-registrados** (diagnostico, nao criterio): o mesmo
  retorno em (a) barras com o contexto mas SEM o evento, e (b) eventos
  SEM o habilitador de contexto. Se (a) ou (b) der o mesmo que a
  conjuncao, o evento nao acrescenta nada.

### PORTAO DE HONESTIDADE (bloqueante)

O mesmo estimador sobre passeio aleatorio, com a mesma geometria de
barra. Exigencia: veredito CONTRA. Qualquer outro reprova.

Aqui o portao NAO e' confirmacao de teorema (diferente da Rota B): o
estimador seleciona por condicoes sobre a propria barra, e selecao
sempre merece suspeita de vies. Se reprovar, o desenho esta errado.

### Criterio de decisao, definido ANTES

- **FAVORAVEL**: pelo menos um lado com retorno medio POSITIVO e
  significativo, n >= 30.
- **CONTRA**: nenhum lado distinguivel de zero.
- **INVERTIDO**: retorno significativamente NEGATIVO — a leitura de
  absorcao esta ao contrario. Achado genuino, registrar.
- **INCONCLUSIVO**: n < 30 nos dois lados.

### Regra de parada

Proibido re-rodar com cortes, K, janela ou horizonte diferentes depois
de ver o resultado. INCONCLUSIVO so' permite acumular pregoes e rodar de
novo com os MESMOS parametros.

### Contabilidade

2 comparacoes (um teste por lado), deflacao local, como a convencao ja'
estabelecida na Rota B. **Toda a fase de desenho foi `features`** —
frequencia, distribuicao, redundancia — e nao entra no contador.

Ficou registrado que QUATRO definicoes de contexto foram examinadas.
Nenhuma olhou retorno, mas a multiplicidade existe: se esta rodada sair
INCONCLUSIVO e outra definicao de contexto for tentada depois de ver o
resultado, a contagem tera' que incluir as tentativas.

### IMPLEMENTADO e PORTAO PASSOU (2026-08-31)

`research/absorcao_barra.py` + `profit-tape absorcao-barra`. Ordem
bloqueante no codigo: portao sobre ruido, depois dado real.

    PORTAO sobre 97.200 barras de ruido puro:

                           grupo    n   media      t   sig
           evento+contexto BAIXA   72   7,986  0,707  False
            evento+contexto ALTA   50  23,500  1,748  False
    CONTROLE contexto sem evento 6543  -1,224 -0,994  False
    CONTROLE evento sem contexto 1870  -0,663 -0,290  False

    VEREDITO SOBRE RUIDO: CONTRA -> PASSOU

Os controles tambem em zero confirmam que nao ha' vies de selecao no
desenho — que era a suspeita legitima, ja' que o estimador seleciona
barras por condicoes sobre elas mesmas.

### DEFEITO NO GERADOR DE RUIDO, e o que ele revelou

Primeira versao sorteava o volume da barra INDEPENDENTE do caminho do
preco. Medido: `corr(amplitude, volume)` = **+0,012 no ruido contra
+0,892 no real**. Como o evento exige amplitude E volume altos ao mesmo
tempo, no ruido isso virava produto de probabilidades independentes — 3
eventos em 60 dias contra ~2,5 por pregao no real.

Nao era so' falta de amostra: **ruido com geometria errada testa outro
estimador**. Corrigido sorteando o numero de NEGOCIOS por barra, que
determina ao mesmo tempo a amplitude (quantos passos o preco da') e o
volume.

**E sobrou uma diferenca que NAO e' defeito do gerador:**

    |desloc_norm| mediano nas barras de amplitude alta
      ruido (passeio aleatorio) : 0,654
      WINFUT real               : 0,495

O mercado produz muito mais barras que ANDAM E VOLTAM do que um passeio
aleatorio produziria — o evento e' 2,4x mais frequente no real (4,6%
contra 1,9%). Isso e' reversao a media intrabarra, e e' precisamente o
fenomeno que a hipotese afirma existir.

Consequencia para o portao: ele NAO precisa reproduzir a frequencia do
real. Precisa responder se, quando esses eventos ocorrem POR ACASO, o
retorno seguinte e' zero. Menos eventos so' exige mais dias — 900.

### RESULTADO: INCONCLUSIVO por amostra (2026-08-31)

Rodado sobre os 25 pregoes (24/07 a 27/08), 2.723 barras. Portao passou
antes.

                           grupo    n  n_sufic     media      t   sig
           evento+contexto BAIXA   28    False   -59,821 -0,710  False
            evento+contexto ALTA   20    False  -113,500 -1,527  False
    CONTROLE contexto sem evento  247     True   -10,789 -0,567  False
    CONTROLE evento sem contexto   54     True   -46,852 -1,231  False

    VEREDITO: INCONCLUSIVO -- n < 30 nos dois lados

**Nao interpretado**, por regra congelada. Os quatro grupos deram media
negativa, INCLUSIVE os dois controles — e controles negativos junto
sugerem deriva da amostra, nao efeito do evento. Nada disso e'
significativo e nada disso autoriza leitura.

### ERRO DE DIMENSIONAMENTO MEU

Projetei 62 eventos (38 BAIXA + 25 ALTA); sairam 48 (28 + 20).
**Superestimei em 29%.**

Causa: extrapolei do dump de 24-31/08 — seis pregoes de volatilidade
acima da media da amostra — para os 25 pregoes, assumindo regime
constante. Nao verifiquei essa suposicao.

Licao para o proximo dimensionamento: taxa de evento depende de regime,
e janela curta e recente nao representa a amostra inteira.

### O QUE A REGRA DE PARADA AUTORIZA

    PERMITIDO: acumular pregoes e rodar de novo com os MESMOS parametros
    PROIBIDO : mexer em K, cortes, janela ou horizonte

Baixar `K` de 3 para 2 traria mais eventos e e' a tentacao obvia. Seria
mudar parametro DEPOIS de ver o resultado, e invalidaria a rodada.

**Faltam ~12 pregoes** pela taxa observada (nao projetada): BAIXA chega a
30 em 27 pregoes, ALTA em 38. Duas a tres semanas de captura.

Isto reforca a prioridade ja' registrada: **acumular pregoes e' a via
principal**, e agora com um consumidor concreto esperando.

### AMOSTRA DO GRAFICO como conjunto INDEPENDENTE (decisao 2026-08-31)

Decisao do operador diante do INCONCLUSIVO: em vez de esperar ~12
pregoes, usar o historico do grafico como **amostra independente**,
consumindo trial.

**Por que e' viavel aqui e nao era antes**: o evento precisa so' de OHLC
+ volume TOTAL de agressao. `QuantityVol(False, True)` entrega isso em
historico profundo. `AgressionVolBuy/Sell` — retido por UMA SEMANA — nao
e' necessario, porque o evento mede ESFORCO, nao desequilibrio.

**Independente, nao continuacao do pool.** Duas amostras separadas que
concordem valem mais que uma maior. Se o efeito aparecer nas duas, e'
forte; se aparecer so' numa, aprendeu-se sobre estabilidade.

**Sobreposicao com 24/07-27/08 e' RECUSADA no codigo.** A independencia
e' a unica razao de usar esta fonte: sobrepor transformaria "duas
amostras que concordam" em "a mesma amostra contada duas vezes", e o
segundo resultado pareceria confirmacao.

**Risco tecnico medido**: o OHLC do grafico diverge do tape em 1 tick em
~47% das barras (causa: RLP como primeiro/ultimo negocio). Simulado o
efeito sobre o evento — **~4% dos eventos mudariam de classificacao**.
Ruido de medicao aceitavel, e muito menor do que seria se o evento
dependesse de `imbalance`.

`research/absorcao_grafico.py` + `profit-tape absorcao-grafico`. Os
campos calculados sao RECALCULADOS em Python e os logados pelo `.ntsl`
servem de CONFERENCIA — mesmo desenho da equivalencia: usar o numero
logado seria confiar que os lados concordam; recalcular MEDE se
concordam.

### O PERIODO TEM QUE SER DECLARADO ANTES (lacuna fechada, 2026-08-31)

Levantado pelo operador: recusar sobreposicao com o capturado **nao
basta**. Nada impediria dumpar maio, ver o resultado, e depois dumpar
marco. Cada dump seria "um tiro", mas o CONJUNTO seria uma busca — e o
ultimo resultado pareceria confirmacao.

Essa lacuna existia e nao estava protegida em lugar nenhum.

**Fechada em CODIGO, nao so' em texto**: `docs/PERIODOS_DECLARADOS.json`
tem que conter o periodo, com `motivo`, e estar COMMITADO antes do dump.
`profit-tape absorcao-grafico` recusa qualquer periodo fora do
declarado, e recusa tambem dump que EXTRAPOLE o declarado (declarar maio
e dumpar maio+junho seria ampliar depois do fato).

O git carimba a ordem: a declaracao precede o dado, e isso e'
verificavel por terceiro. Nao depende de ninguem lembrar.

**Regra que acompanha:**

1. Escolher por criterio EXTERNO ao resultado — calendario,
   disponibilidade, tamanho de amostra. Nunca por desempenho.
2. **Cada periodo declarado consome trial, tenha sido rodado ou nao.**
   Declarar cinco e rodar um ainda e' escolher entre cinco.
3. Nao editar nem remover entrada depois de rodada. O historico de
   tentativas e' parte do resultado.

O `motivo` e' cobravel: **se nao puder ser dito antes de ver o dado, nao
e' criterio.**

**Quanto dumpar**: o lado ALTA precisa de 30 eventos a ~0,8/pregao, entao
~38 pregoes. Buffer de ~2.000 linhas = ~18 pregoes por dump, com
`MostrarSoEvento(0)` (os controles precisam das barras que NAO
dispararam). Dois a tres dumps, em periodo anterior a 24/07.

### ERRATA 2026-09-01: o `z` estava AMBIGUO no texto congelado

Achada pela conferencia entre o `.ntsl` e o Python, sobre 2.260 barras
de maio/2026:

    desloc_norm    dif maxima 2,5e-06   -> exato
    mov_contexto   dif maxima 6,8e-07   -> exato
    z_amplitude    dif maxima 19,86     -> FORMULA DIFERENTE
    z_vol_agr      dif maxima  7,51     -> FORMULA DIFERENTE

**O texto congelado dizia "vs 50 barras"**, sem especificar se a propria
barra entrava. As duas implementacoes resolveram para lados OPOSTOS: o
`.ntsl` percorre `for nIndex := 1 to JanelaZ` (so' anteriores), o Python
usava `rolling()` incluindo a atual.

Consequencia: **o indicador que se OLHA e o estimador que DECIDE
marcavam conjuntos de barras diferentes.**

**Desambiguado pela definicao do `.ntsl`**, decidida pelo operador por
MECANISMO: "atipica em relacao ao normal recente" compara contra a
HISTORIA, e incluir a propria barra na referencia atenua justamente o
que se quer detectar — a barra grande infla a propria media e o proprio
desvio.

### Por que isto e' ERRATA e nao mudanca oportunista

1. **As duas rodadas deram INCONCLUSIVO POR n < 30** (28/20 no parquet,
   8/16 em maio). Nenhum retorno foi interpretado — nao houve selecao
   sobre resultado.
2. A desambiguacao veio da **comparacao NTSL x Python**, um argumento de
   mecanismo, nao de qual versao produz numero melhor.
3. O texto congelado era genuinamente ambiguo; nao houve troca de
   criterio, houve especificacao do que faltava.

**Consequencia conhecida, registrada DEPOIS da decisao**: excluir a
barra atual aumenta o `z` das barras extremas, logo tende a produzir
MAIS eventos. Isso ajuda o problema de amostra — e por isso mesmo fica
escrito que a decisao foi tomada pelo conceito, antes de a consequencia
ser calculada.

**Multiplicidade**: se esta especificacao tambem sair INCONCLUSIVO e uma
TERCEIRA for tentada depois de ver o resultado, ai' havera selecao e a
contagem tera' que incluir as tentativas.

Portao refeito com o estimador corrigido: **CONTRA**, |t| 0,86 e 1,44,
controles em zero. Passa.

### INSPECAO POR BARRA: investigar nao e' overfit, ajustar e' (2026-09-02)

`profit-tape absorcao-inspecionar 2026-08-27`. Categoria `features`:
mostra o valor de cada condicao e a FOLGA ate o corte. Nao toca em
retorno, nao consome trial.

**Investigar por que uma barra ficou de fora e' legitimo.** Foi assim que
se descobriu que a formula antiga pintava MARUBOZUS enquanto o conceito
era DOJI com pavio. Sem olhar barras concretas, aquele erro continuaria
de pe'.

**Vira overfit em dois pontos:**

1. **Ajustar o corte para a barra entrar.** Baixar `MAX_DESLOC_NORM` de
   0,25 para 0,28 porque uma barra especifica ficou de fora e' calibrar
   ao julgamento sobre AQUELES dados — mesmo sem olhar retorno.
2. **Inspecionar o periodo que ainda vai ser testado.** A cegueira se
   perde, nao porque se viu retorno, mas porque as decisoes posteriores
   passam a carregar aquele olhar.

**Periodos JA' QUEIMADOS** (livres para inspecao): parquet 24/07-27/08 e
o maio do grafico, os dois ja' com veredito.
**Periodo CEGO**: o que estiver declarado e ainda nao rodado.

A FOLGA e' o que torna a inspecao util: falhar por 0,01 sugere corte
apertado; falhar por 0,60 sugere que a barra nao e' o que se procura.
Sem o numero as duas parecem iguais.

O resumo conta falhas por condicao. **Se uma condicao sozinha reprova
quase tudo, ela define o evento na pratica e as outras estao
decorativas** — exatamente o defeito do `absorcao_dir`, onde o
`desloc_norm` dominava a subtracao. Vale checar se voltou por outro
caminho.

Se a inspecao mostrar que a formalizacao nao captura a leitura, o
caminho e' **pre-registro NOVO**, testado em dado que ele nao viu — nunca
ajuste do que esta congelado.

### DECISAO DE MANTER a janela de 6 barras (2026-09-02)

Levantado pelo operador: `mov_contexto` e' uma diferenca por JANELA
MOVEL, entao ela **cai enquanto o preco continua subindo**, se a alta
desacelera. Demonstrado: preco subindo o tempo todo e `mov6` despencando
de 6,56 para 1,23 — com `K=3`, o habilitador DESLIGA na barra 10.

Isso e' tensao real com o conceito: o habilitador exige movimento ainda
RAPIDO nas ultimas 6 barras, enquanto "apos uma sequencia de alta"
inclui alta que ja' perdeu folego. E' justamente quando absorcao e
exaustao teriam mais chance.

**DECISAO DO OPERADOR: manter.** O argumento e' dele e e' forte —
trocar a janela fixa por topos e fundos parece mais fiel, mas introduz
**mais parametros livres**: como definir um fundo, qual escolher, quanto
precisa durar. Cada um e' uma decisao a mais passivel de ser tomada
olhando dados. A janela de 6 barras e' grosseira, mas e' **UM** numero,
fixado antes. Trocar precisao conceitual por tres parametros novos
costuma piorar.

"30 minutos no tf=5m e' suficiente para determinar o lado da agressao e
tomar a decisao por ela. E os proprios numeros medidos irao nos dizer o
caminho."

### OBSERVACAO VISUAL do operador, com a ressalva que ele mesmo deu

No parquet (amostra de DEPURACAO):

> A barra **fucsia** fez sentido na marcacao. Pegou um fundo, foi a
> minima do dia, e o movimento posterior foi longo — barras grandes logo
> apos, depois barras pequenas sem muito deslocamento.
>
> As **aqua** apareceram no meio do movimento.

**Ressalva registrada pelo proprio operador, e ela e' o que separa
observacao de evidencia:**

> "Isso e' uma analise POS-FATO. Facil de ver no grafico e assumir que
> foi o melhor ponto." E sobre o aqua: "pode ser so' o movimento que
> falhou; em outros dias teria dado certo."

**E ele evitou navegar pelo grafico em varios dias, de proposito**, para
nao criar vies e comecar a decidir pelo resultado. Isso protege a
amostra cega sem ninguem ter pedido.

**O que o teste ja' responde**: os dois lados sao reportados SEPARADOS,
nunca somados. Se o fucsia funciona e o aqua nao, a assimetria aparece
sem mudar nada. **Descartar o lado aqua por causa desta observacao seria
escolher o lado depois de ver o desfecho** — os dois continuam sendo
reportados, inclusive o que nao der nada.

Precedente: o `z_agf_3` so' teve edge na venda. Assimetria entre lados
nao seria novidade neste instrumento, e ha' mecanismo plausivel —
absorcao num fundo e' acumulacao, num topo e' distribuicao, e as duas
nao precisam ter a mesma dinamica.

**Nota sobre a tensao do horizonte**: o operador disse estar "menos
preocupado se capturamos o movimento todo ou se acertamos os times".
Isso ATENUA (nao dissolve) a tensao registrada antes sobre 2 barras nao
medirem movimento longo — um sinal que pega um fundo tambem produz
retorno positivo em 2 barras.

### TRIAL 2026, parte 1: rodado (2026-09-03)

    9.105 barras | 81 pregoes | 02/01 a 30/04/2026
    40 eventos -> 24 BAIXA, 16 ALTA
    VEREDITO: INCONCLUSIVO (n < 30 nos dois lados)

**Nao interpretado**, por regra congelada. Os sinais variam entre as
tres amostras ja' rodadas, o que e' esperado com `n` pequeno e nao
sustenta leitura nenhuma.

**O que E' interpretavel: a implementacao.** A conferencia ficou limpa
nos QUATRO campos, inclusive `mov_contexto` (dif maxima 1,77e-06) — o
`.ntsl` e o Python sao a mesma coisa. Era o defeito de fundo desde
2026-08-31.

E a purga esta comprovadamente ativa: `mov_contexto` tem 560 barras a
menos que os z, e 560/81 = **6,9 por pregao**, contra `JanelaContexto+1
= 7`. Bate exato.

**Taxa de evento consistente entre amostras independentes:** 0,50/pregao
em maio (20 pregoes) e 0,49 em jan-abr (81). O dimensionamento agora tem
base.

### TRIAL 2025 DECLARADO, e a decisao tomada ANTES do combinado

Projecao com a taxa observada: 2026 inteiro fora das amostras queimadas
da' ~118 pregoes -> **BAIXA ~35, ALTA ~23**. O lado ALTA nao alcanca o
minimo nem somando a parte 2.

Diante disso, duas saidas legitimas, e a escolha foi feita **antes de
rodar o combinado** — nao depois de ver que ele nao bastava:

    A) aceitar INCONCLUSIVO no lado ALTA e reportar so' a BAIXA
    B) declarar 2025 como trial adicional          <- ESCOLHIDA

**2025 declarado**: 02/01 a 30/12/2025, ~250 pregoes -> BAIXA ~75, ALTA
~50. Passa nos dois lados.

### 2025 e 2026 sao amostras INDEPENDENTES, nao um pool

Decidido junto com a declaracao, e a escolha muda o que o resultado
significa.

**Nao juntar** os dois numa amostra so'. Juntar daria ~370 pregoes e
folga confortavel, mas transformaria dois trials declarados num numero
so' e perderia a informacao mais valiosa: **se o efeito e' estavel entre
anos**.

Mesmo argumento que ja' foi usado para tratar o grafico como
independente do parquet. Se o efeito aparecer nos dois, e' forte. Se
aparecer so' num, aprendeu-se sobre estabilidade — e isso e' resposta,
nao ruido.

Consequencia aceita: **2026 provavelmente fecha INCONCLUSIVO no lado
ALTA**, e esta' tudo bem. Um veredito parcial honesto vale mais que um
pool montado para alcancar significancia.

### VEREDITO DE 2026 ANULADO ANTES DE SER LIDO (2026-09-03)

A rodada do combinado (119 pregoes, 64 eventos) devolveu **CONTRA** com
n=34 e n=30 — os dois acima do minimo pela primeira vez.

**O veredito NAO vale**, e a razao esta na propria saida:

    conferencia          parte 1 sozinha    combinado
      z_amplitude           4,89e-06          6,20
      z_vol_agr                  0,0          0,78
      mov_contexto          1,77e-06          0,70

**Causa: a CONCATENACAO cria um buraco.** O dump junta 02/01-30/04 com
01/06-23/07, e maio nao esta la'. O `.ntsl` calculou sobre o grafico
CONTINUO (abril -> maio -> junho); o Python le' o arquivo (abril ->
junho). Nas primeiras 50 barras de junho, a janela movel do Python pegava
ABRIL enquanto a do NTSL pegou MAIO.

**Por que isso muda o veredito e nao e' detalhe**: o lado ALTA tem n=30,
exatamente o minimo. Descartar as barras contaminadas remove eventos — um
so' ja' leva a 29, e o CONTRA vira INCONCLUSIVO.

### Duas correcoes

**1. Janela movel nao atravessa buraco na amostra.** Mesmo principio da
purga de dia: referencia movel nao cruza descontinuidade. Aqui a
descontinuidade e' de AMOSTRA, nao de pregao. Blocos contiguos separados
por salto de mais de 10 dias (fim de semana longo e feriado nao contam).

**2. Divergencia na conferencia INTERROMPE a rodada.** Ela ja' estava
sendo calculada e reportada — e o comando seguiu ate o veredito assim
mesmo. Relatar nao basta: **quem le' um veredito tende a ler o
veredito**. Divergencia acima de 1e-03 aborta com a causa provavel.

Portao refeito com a correcao: CONTRA, |t| 0,81 e 1,56.

### RESULTADO DO TRIAL 2026 (2026-09-03)

Conferencia LIMPA nos quatro campos (pior: 5,88e-06) — o `.ntsl` e o
Python sao a mesma coisa, e o veredito vem do estimador correto.

    13.399 barras | 119 pregoes | 02/01 a 23/07/2026
    62 eventos

                           grupo   n  n_sufic   media      t   sig
           evento+contexto BAIXA  34    True   +38,307  0,700  False
            evento+contexto ALTA  28   False   -43,604 -0,637  False
    CONTROLE contexto sem evento 632    True   +11,509  0,848  False
    CONTROLE evento sem contexto 264    True   -14,107 -0,605  False

    VEREDITO GLOBAL (criterio congelado): CONTRA

### O GLOBAL AFIRMA MAIS DO QUE UM LADO SUSTENTA

    BAIXA  n=34  ->  CONTRA        (medido, nao distinguivel de zero)
    ALTA   n=28  ->  INCONCLUSIVO  (n < 30, NAO interpretado)

O criterio congelado manda INCONCLUSIVO so' quando `n < 30` nos DOIS
lados, entao o caso MISTO cai em CONTRA por eliminacao — e o texto
realmente diz isso. Mas "CONTRA" afirma que a absorcao nao antecipa
reversao em NENHUM lado, e com `n = 28` de um deles isso **nao esta
medido**.

Mesma classe de ambiguidade do `z`: o texto congelado nao cobriu o caso,
e a implementacao resolveu por eliminacao.

**O global fica como congelado** — muda-lo depois de ver o resultado
seria o que a disciplina proibe. A saida passa a reportar o veredito
POR LADO, para o excesso ficar visivel em vez de escondido no rotulo.

### Leitura honesta deste trial

**O lado BAIXA (aqua) tem resposta: CONTRA.** Com n=34, media +38,3 pts e
t=0,70, a absorcao apos alta nao antecipa queda neste sinal e neste
horizonte.

**O lado ALTA (fucsia) segue sem resposta**, e e' justamente o lado que a
observacao visual do operador apontava como o que fazia sentido. **2025
ja' esta declarado** e projeta ~50 eventos ali.

Nota: o `n` caiu de 30 para 28 apos a correcao de bloco contiguo — as
barras logo apos a emenda perderam o `z`, como devem. A projecao de que
2026 nao alcancaria o minimo na ALTA (~23) estava certa em direcao.

### Fora deste pre-registro

- **Exaustao**: e' processo de SEQUENCIA, nao evento de barra — objeto
  de escala diferente. Material do operador da' base de 2 a 5 candles,
  acima de 20 vira indecisao. Desenho proprio, pre-registro proprio.
- Nivel de PRECO (footprint). O tape permite reconstruir volume por
  preco com lado agressor (demonstrado: 327 niveis numa barra), mas todo
  o pipeline e' de barra, e o operador le' o grafico, nao o Times &
  Trades. Refinamento posterior.
- Qualquer implementacao no EA.
- Alvo e stop.

## AMOSTRA DE DEPURACAO x AMOSTRA DE TESTE (2026-09-02)

Estrutura proposta pelo operador, e ela nomeia o que ja' vinha
acontecendo de fato.

### A observacao que a motivou

**O que vem pegando erro neste projeto e' a analise VISUAL do grafico,
sem olhar numero.** Nenhum dos defeitos de hoje veio de olhar retorno:

    contexto medindo o GAP NOTURNO      achado na barra de 14/05
    formula pintando MARUBOZU           achado na barra de 31/08
    z divergindo entre .ntsl e Python   achado na conferencia

Os tres questionavam a FORMULA, nunca a calibracao.

### O limite, que precisa ficar escrito

**PODE** — questiona a formula:
  - "o contexto esta medindo o gap noturno" -> BUG
  - "isso pinta marubozu, o conceito era doji" -> DEFEITO DE SPEC

**NAO PODE** — questiona a calibracao:
  - "se eu baixar K para 2,5 fica melhor" -> ajuste a' amostra
  - "esta variante marca barras mais bonitas" -> escolha entre variantes
    NO DADO

A diferenca: o criterio e' o **CONCEITO descrito ANTES**, nao "qual
versao parece melhor NESTAS barras". Olhar cem barras e escolher a
variante que mais agrada e' fitting, mesmo sem ver retorno nenhum.

### A separacao

| amostra | quais | serve para | resultado |
|---|---|---|---|
| **DEPURACAO** | parquet 24/07-27/08, maio do grafico | achar bug e defeito de spec, inspecao visual | **NAO interpretavel** |
| **TESTE** | periodo declarado, cego | responder a pergunta | um tiro |

**Os vereditos ja' obtidos no parquet e em maio nao contam como
resultado.** Foram rodadas de depuracao, e cada uma revelou um defeito
de implementacao contra o que o pre-registro ja' dizia. Isso e' debug,
nao busca — mas so' enquanto as correcoes vierem de DEFEITO, nunca de
resultado.

**O limite dessa licenca**: "corrigir ate funcionar" vira busca ainda
que cada passo seja defensavel. Por isso o resultado interpretavel tem
que vir de dado NAO usado na depuracao.

### TRIAL 2026 declarado

    parte 1: 02/01 a 30/04/2026   (~82 pregoes)
    parte 2: 01/06 a 23/07/2026   (~37 pregoes)

Excluem 04-29/05 (dump de maio) e 24/07-27/08 (parquet), que sao
depuracao. **As duas partes sao UM trial**: uma decisao de onde olhar,
executada em varios dumps por limite de buffer.

A ~0,5 evento/pregao (taxa medida apos a purga), ~60 eventos, ~30 por
lado — no limite do minimo.

**2025 fica RESERVADO** para o trial seguinte. Nao dumpar antes de 2026
ter veredito.

### ERRATA 2026-09-02: a purga nao valia para o CONTEXTO

`mov_contexto` e' uma DIFERENCA DE PRECO e atravessava a virada do
pregao — medindo o **gap noturno** em vez da perna intradiaria.

    |mov_contexto| mediana, barras 1-6 do dia : 3,58
    |mov_contexto| mediana, demais barras     : 0,80
    habilitador exige                          : 3,00

Disparava quase automaticamente na abertura: **10 dos 24 eventos (42%)
nas 6 primeiras barras**, que sao 5% do pregao. Taxa de 20% ali contra
0,7% no resto.

Achado pelo operador na inspecao visual de 14/05: "uma barra forte que
INICIA o movimento depois de uma sequencia de barras fracas" — o oposto
de absorcao.

**A purga vale SO' no contexto.** `z_amplitude`, `z_vol_agr` e
`range_medio` sao grandezas INTRABARRA, que o gap nao corrompe. Purgar
as tres custaria as 50 primeiras barras de cada pregao (46% da amostra)
sem corrigir defeito nenhum.

Efeito: eventos em maio caem de 24 para 10, **zero** nas primeiras
barras.

### EXPECTATIVA ESTRUTURAL do operador, registrada ANTES de qualquer resultado (2026-09-02)

Dita antes de ver numero, e por isso vale como hipotese datada:

> Poucos sinais por dia. Dia direcional: poucos eventos, talvez 2, num
> pullback importante com bastante volume. Dias laterais: mais eventos,
> movimentos menores. Alguns pegam movimento LONGO, outros pequenos.

Taxa medida apos a purga: **0,5 evento/pregao** — compativel com "poucos
sinais".

**TENSAO COM O PRE-REGISTRO ATUAL, registrada e NAO resolvida agora:**

1. "Alguns pegam movimentos longos" **nao e' mensuravel em 2 barras**. O
   horizonte teta o resultado: movimento de meia hora aparece como
   numero pequeno, indistinguivel de sinal fraco.
2. "Uns grandes, outros pequenos" e' sobre a **DISTRIBUICAO**; o
   estimador testa a **MEDIA**. Sinal com poucos acertos grandes e
   muitos empates pode ter media positiva, `t` baixo, e sair CONTRA
   sendo exatamente o esperado.

**Nao mexer no pre-registro atual por causa disso.** Ele testa uma
pergunta legitima e restrita — o preco reverte em 10 minutos. Trocar o
horizonte depois de duas rodadas inconclusivas seria escolher parametro
sabendo o resultado.

Isto e' material para o PROXIMO pre-registro: horizonte maior, ou saida
por evento em vez de numero fixo de barras, e criterio sobre a forma da
distribuicao em vez da media.

## QUANDO ABANDONAR UM DESENHO SEM ISSO SER P-HACKING (2026-09-03)

Levantado pelo operador, e a distincao e' dele:

> "A disciplina nao pode nos impedir de mudar de direcao ao
> identificarmos uma decisao errada. E nao errada porque vi o dado e
> quero enquadra-lo, mas porque ela fica impossivel de ser executada."

### O criterio que separa os dois casos

Um desenho pode ser abandonado quando a impossibilidade e' demonstravel
por **quantidade que nao depende da direcao do resultado**.

A quantidade e' o **EFEITO MINIMO DETECTAVEL**:

    EMD = 1,96 x desvio / raiz(n)

O desvio e' propriedade da distribuicao de retornos daqueles eventos. Ele
seria o mesmo se a media tivesse dado positiva, negativa ou zero. **A
media observada nao entra na conta.**

Se o EMD exige um efeito implausivel para o fenomeno, o desenho nunca
teve como responder — e isso e' fato sobre o DESENHO, nao sobre o
resultado.

### Aplicado ao pre-registro de absorcao

    desvio dos eventos individuais:  319 pts (BAIXA), 362 pts (ALTA)
    EMD:                             107 pts (BAIXA), 134 pts (ALTA)
    amplitude MEDIA de uma barra 5m: 244 pts

**O desenho so' enxerga efeito de 107 pontos LIQUIDOS em 10 minutos** —
0,44 da amplitude de uma barra inteira, de deslocamento medio sustentado
em duas barras. Nenhum sinal razoavel produz isso sistematicamente.

Para detectar a media observada seriam ~267 eventos por lado: a 0,5
evento/pregao, **mais de mil pregoes, quatro anos**.

**O `CONTRA` do trial 2026 nao diz "nao ha efeito". Diz "nao ha efeito
grande o bastante para este desenho ver".**

### O que o operador ja' tinha previsto

A expectativa registrada em 2026-09-02, ANTES de qualquer resultado:

> "Alguns pegam movimento LONGO, outros pequenos."

Variancia alta e' exatamente isso — e variancia alta e' o que mata um
teste de MEDIA. A tensao registrada na epoca ("movimento longo nao e'
mensuravel em 2 barras") nao era teorica: **e' a razao pela qual nao ha'
como concluir.**

### A regra, para nao virar escapatoria

Abandonar desenho por falta de poder exige, TODAS:

1. O EMD calculado **so' da variancia e do n** — jamais da media
   observada.
2. Argumento de por que o EMD e' implausivel, **em unidade do
   instrumento** (aqui: fracao da amplitude de uma barra), nao "achei
   alto".
3. O desenho novo tem que atacar a **razao sinal/ruido**, nao so'
   aumentar `n`. Se a saida proposta e' "mais dados", o desenho antigo
   estava certo e a resposta e' esperar.
4. Registrar o EMD do desenho NOVO **antes** de rodar. Se ele tambem for
   implausivel, nao vale a pena.

**O que NAO autoriza abandono**: resultado ter dado na direcao errada,
`n` ter faltado pouco, ou o veredito ser desagradavel.

## DESENHO 2 medido antes de congelar: REPROVADO pela regra 4 (2026-09-03)

Rascunho em `docs/DESENHO_2_absorcao_com_risco.md`. **Nao congelado, e
provavelmente nao sera'.**

### O que ele propunha

Mesma entrada do desenho 1; muda so' a gestao. Stop no extremo da janela
`[t-6, t]` afastado 20 pts, piso 150 (opera com o piso), teto 500 (NAO
opera), alvo fixo de 1.000, saida as 17:30 e ultima entrada as 17:00.

### O motivo de propor, e por que estava errado

O argumento era: o stop TRUNCA a cauda de perda, e a cauda produz o
desvio de 319 do desenho 1.

    DESENHO 1 (2 barras, bruto)      desvio 319 pts
    DESENHO 2 (stop ~220, alvo 1000) desvio 452 pts

**A variancia PIOROU.** O stop trunca a PERDA em ~220, mas o alvo abre o
GANHO ate 1.000 — a distribuicao vira bimodal, muitos -220 e alguns
+1.000. Isso e' mais dispersao que retornos continuos de duas barras.

Eu estava certo sobre a perda e errado no LIQUIDO: nao considerei que o
alvo alarga o outro lado na mesma medida.

### O EMD reprova

    n= 30 -> EMD 0,66 unidades
    n= 45 -> EMD ~0,54          <- 2025 projeta ~40 e ~45 por lado
    n=211 -> EMD 0,25

Contra 0,44 do desenho 1. **O desenho novo e' PIOR.** A regra 4 do
criterio de abandono — registrar o EMD do desenho novo antes de rodar —
reprova.

**Ressalva**: sao 8 operacoes na depuracao, e o desvio pode estar mal
estimado. Mas o mecanismo (perda truncada, ganho aberto) e' aritmetica da
distribuicao e nao depende de amostra. Alvo de 4-5x o stop TEM que dar
dispersao maior que retorno curto.

### O que o diagnostico mostrou sobre a GEOMETRIA

    saidas: 7 stop, 1 alvo
    MFE mediana: 0,65 do risco
    MFE p90:     4,52 do risco

Na maioria das operacoes o preco nem se aproxima do alvo. Um alvo de
1.000 com stop de 220 exige o preco andar 4x o risco, e a MFE diz que ele
geralmente anda menos de 1x.

Isso nao e' resultado sobre a hipotese — e' sobre a geometria do
desenho. **Nao proponho desenho 3 aqui**: escolher alvo ou stop olhando
esses numeros seria calibrar depois de ver o dado.

### Codigo entregue para o operador refazer com amostra maior

`profit-tape desenho2-emd <dump>` roda na amostra de DEPURACAO. Se o
desvio cair com mais operacoes, a conclusao muda — e essa e' a unica
coisa que reabre o desenho.

### EMD do DESENHO 2 com amostra adequada (2026-09-04)

Rodado sobre os 119 pregoes de 2026 (60 eventos, 49 operadas). A
estimativa de 8 operacoes dava desvio 452; com 49 caiu para **396,6** —
mas continua ACIMA dos 319 do desenho 1.

    n necessario para EMD = 0,25 unidades (61 pts):

      DESENHO 1  desvio 319,0  ->  105 eventos operados
      DESENHO 2  desvio 396,6  ->  162 operados
                                +  18% descartados (stop > 500)
                                =  199 eventos brutos

    DESENHO 2 precisa de 1,89x mais eventos.

**Confirmado com amostra adequada: o desenho 2 e' pior.** A variancia
maior e os descartes se somam.

### E a conta que vale para os DOIS

    a 0,5 evento/pregao:
      DESENHO 1 -> 210 pregoes
      DESENHO 2 -> 398 pregoes

**2025 tem ~250 pregoes. Nenhum dos dois chega.**

O problema nao e' o desenho 2 ser ruim. E' que **a razao sinal/ruido
deste sinal, medida em pontos de retorno, exige mais dados do que existe
ao alcance** — em qualquer das duas formulacoes.

### O que isto NAO significa

Nao significa que a absorcao nao funciona. Significa que **medir o efeito
pela MEDIA do retorno em pontos** e' um instrumento fraco demais para o
tamanho de amostra disponivel.

### A geometria, que e' o dado mais informativo do dia

    saidas: 43 stop | 5 alvo | 1 tempo   -> alvo bate em 10% das vezes
    MFE mediana: 0,86 do risco
    MFE p90:     3,10 do risco
    custo do alvo fixo: -102 pts por operacao

O preco tipicamente anda **menos de 1x o risco** a favor. Um alvo de
1.000 com stop mediano de 255 exige 3,9x — e isso acontece em 10% dos
casos.

**Nao proponho desenho 3.** Escolher alvo ou stop olhando esses numeros
seria calibrar depois de ver o dado, e essa e' a linha que a sessao
inteira respeitou.

### Custo desta descoberta: ZERO trials

A regra 4 do criterio de abandono — medir o EMD do desenho novo ANTES de
congelar — fez exatamente o que devia. O desenho 2 foi reprovado sem
gastar 2025, que continua intocado.

### Diagnostico POR LADO, e o que ele custa (2026-09-04)

`profit-tape desenho2-emd` passa a reportar tudo separado por lado.

**Nem toda metrica esta' na mesma distancia do resultado:**

    GEOMETRIA (longe)      risco p50/p90, descartados por passar de 500
    PERTO DO RESULTADO     stop/alvo/tempo, MFE, custo do alvo

Quebrar os tres ultimos por lado responde, na pratica, **"qual lado
funciona melhor"**.

**Permitido**, porque 2026 virou DEPURACAO para o desenho 2 quando foi
usado para dimensiona-lo. Era exatamente para isso que a separacao
depuracao/teste existia.

**O custo, que precisa ficar declarado antes:** se um desenho futuro
descartar um lado PORQUE ele foi pior aqui, isso e' **selecao**.
Legitima num fluxo depuracao/teste, mas exige declaracao — e o teste vai
para 2025, o unico periodo cego que resta.

**O que NAO vale**: olhar isto e depois dizer que o desenho novo saiu "do
mecanismo". Se saiu daqui, saiu do dado, e a multiplicidade tem que ser
contada.

### O GARGALO TEM NOME: o contexto, nao a hipotese (2026-09-04)

Decomposto o trial 2026 (13.399 barras, 119 pregoes):

    ABSORCAO (as 3 condicoes)  326 barras = 2,4%  = 2,7 por pregao
    CONTEXTO (|mov6| >= 3)     694 barras = 5,2%  = 5,8 por pregao
    OS DOIS JUNTOS              62 barras          = 0,52 por pregao

**Absorcao NAO e' rara.** Acontece 2,7 vezes por pregao. O que e' raro e'
absorcao APOS MOVIMENTO FORTE — a conjuncao derruba de 326 para 62, e e'
essa escassez que torna o desenho incapaz de responder.

E as duas condicoes **andam juntas**: se fossem independentes dariam 17
eventos, deram 62 — 3,7x acima do acaso. O contexto seleciona algo real,
nao filtra por filtrar.

### Rodar 2025 no desenho 2: NAO recomendado

    EMD que 2025 produziria, com os desvios ja medidos:
      BAIXA  n~40  ->  0,48 unidades
      ALTA   n~45  ->  0,50 unidades
      (alvo de plausibilidade: 0,25)

O resultado seria quase certamente "nao distinguivel de zero" **de novo
por falta de poder**, e 2025 e' o ULTIMO periodo cego. Gasto nisso, um
desenho futuro nasce sem amostra de teste virgem.

### CURVA DE PODER: `profit-tape curva-poder`

Mede o EMD em funcao de `K`, usando **variancia e n** — a media do
retorno nao entra em nenhuma linha.

Baixar `K` **nao elimina a direcao**: `sign(mov6)` existe em toda barra.
Some so' a exigencia de que o movimento seja GRANDE.

**Mas ENFRAQUECE a hipotese**: "absorcao apos movimento FORTE" vira
"absorcao apos movimento". E' afirmacao diferente e mais fraca, e essa e'
a troca — nao apenas ganhar amostra.

**A curva NAO autoriza rodar varios K no teste e ficar com o melhor.** Um
K, um pre-registro, declarado antes com a hipotese que ele implica.

Reporta o **pior lado**, porque o veredito precisa dos dois: a media dos
dois esconderia um lado sem amostra atras do outro.

### O balanco honesto

**Eliminado e nao volta**: `absorcao_dir` media o oposto do conceito;
`esforco` ja' existia como `absorcao`; contexto por contagem de candles,
por rompimento e por referencias do dia anterior nao separam; stop como
detector de reversao levou CONTRA por teorema.

**Descoberto sobre o problema**: absorcao e' comum e anda junto com
movimento forte; o alvo de 1.000 esta alem do p90 da excursao favoravel;
media de retorno em pontos exige 210+ pregoes de EVENTOS.

**Nao se moveu**: nenhum sinal validado.

**O risco real, dito por escrito**: pode ser que medir por MEDIA DE
RETORNO nunca funcione com a amostra disponivel. Se a curva mostrar que
nem `K = 0` alcanca o plausivel, a resposta nao e' outro desenho — e'
mudar o TIPO de pergunta.

### K = 1 CONFIRMADO pelo operador (2026-09-04)

**A justificativa nao veio da tabela de EMD**, e e' por isso que ela
vale:

> "K=1 e' quase metade do meu stop maximo. Sem medir nada, acho razoavel
> entrar numa posicao a partir de um sinal que ja' andou a metade do meu
> stop."

    K = 1  ->  244 pontos liquidos nos 30 min anteriores
    stop mediano medido no desenho 2:  255 pontos

A regra vira: **"so' entro se o preco ja' andou, antes, o equivalente ao
risco que vou assumir".** Movimento previo e risco na mesma escala.

Custo em poder, declarado ANTES:

    K = 3  ->  62 eventos, menor lado 28, EMD 0,55  (o congelado)
    K = 1  -> 216 eventos, menor lado 96, EMD 0,34  (escolhido)
    K = 0  -> 326 eventos, menor lado 152, EMD 0,25

**K = 0 foi recusado por MECANISMO, nao por numero**: com `|mov6|` perto
de zero o preco praticamente nao andou, e `sign(mov6)` vira sorteio —
direcao tirada de ruido ADICIONA variancia em vez de informar. Sao 56 dos
326 eventos (17%) com menos de 122 pontos de deslocamento previo.

**O operador optou por NAO olhar o grafico antes de decidir**, e a razao
esta certa: a justificativa do stop nao depende de quais barras ele
viu, e olhar so' poderia contamina-la.

### O DESVIO E' CONSTANTE EM TODO O K — achado inesperado

    K=0,0  371,0    K=1,0  369,9    K=2,0  375,1    K=3,0  339,0

**Todo o ganho de EMD vem de `n`, nada de reducao de variancia.** O
contexto nao seleciona eventos menos ruidosos; so' seleciona menos
eventos.

Isso NAO significa que o contexto e' inutil: ele pode selecionar eventos
de EFEITO maior, e isso e' imensuravel sem olhar a media.

### O LIMIAR DE 0,25 UNIDADES E' MEU, NAO MEDIDO

Registrado porque `K = 0` bateu exatamente nele. O 0,25 saiu de um
julgamento que escrevi em `triagem_poder.py` — se fosse 0,20, `K = 0`
reprovaria; se 0,30, `K = 0,5` passaria.

**0,25 unidades = 61 pontos liquidos em 10 minutos.** A pergunta que
decide nao e' estatistica: e' se um sinal de absorcao pode mover isso em
media. Julgamento sobre o mercado, e do operador.

## TRIAL 2025 — VEREDITO DO DESENHO 3: INVERTIDO (2026-09-04)

    28.176 barras | 250 pregoes | 02/01 a 30/12/2025 | 469 eventos

    conferencia Python x .ntsl: LIMPA (pior campo 8,13e-06)

                           grupo      n   media       t   sig
           evento+contexto BAIXA    251  + 6,614   0,361  False
            evento+contexto ALTA    216  -36,250  -1,996  TRUE
    CONTROLE contexto sem evento  10305  - 4,553  -2,296  False
    CONTROLE evento sem contexto    260  -15,041  -0,738  False

    VEREDITO pelo criterio congelado: INVERTIDO

**Pela primeira vez a amostra foi suficiente com folga** (251 e 216
contra o minimo de 30) e a conferencia entre os dois lados ficou limpa.

### TRES RESSALVAS, e todas pesam contra a leitura otimista

**1. O resultado e' MARGINAL ao extremo.**

    |t| = 1,996  contra limiar 1,960   -> folga de 0,036
    IC95 = [-75,918 ; -0,177]          -> o topo esta a 0,177 de zero,
                                          num intervalo de 76 (0,2% da largura)

Passa pelos dois criterios pela margem minima possivel.

**2. O CONTROLE tem |t| MAIOR que o evento.**

    evento+contexto ALTA          n=  216  media -36,25  t -1,996
    CONTROLE contexto sem evento  n=10305  media - 4,55  t -2,296

O controle sao barras com `|mov6| >= 1` e **sem absorcao**. Elas tambem
rendem retorno negativo na direcao contraria ao movimento — ou seja, o
preco tende a **CONTINUAR** no sentido do movimento. Isso e' MOMENTUM, e
aparece em 10.305 barras que nao tem absorcao nenhuma.

**A pergunta que o controle levanta e' se o -36,25 e' absorcao ou e' o
mesmo momentum, apenas mais forte por acaso numa amostra de 216.** O
pre-registro diz que controle e' diagnostico e nao criterio — entao o
veredito nao muda —, mas a duvida fica registrada.

**3. A multiplicidade real e' 4, nao 2.**

Duas variantes da mesma hipotese foram testadas: desenho 1 (K=3) em 2026
e desenho 3 (K=1) em 2025, dois lados cada.

O `limiar_deflacionado` devolve 1,96 para 2 e para 4 comparacoes, porque
para `n` pequeno o `E[max Z]` fica ABAIXO do piso e o piso vence. Isso e'
deliberado e correto (deflacao so' pode SUBIR a barra). Mas a
consequencia e' que **a multiplicidade das duas variantes nao foi
penalizada**:

    1 comparacao  -> 5,0% de chance de passar por acaso
    2 comparacoes -> 9,8%
    4 comparacoes -> 18,5%

Com 4 comparacoes e folga de 0,036, a chance de isto ser acaso e'
substancial.

### O QUE O RESULTADO CONTRADIZ

**A leitura visual do operador.** Ele observou que o fucsia "pegou um
fundo, foi a minima do dia, e o movimento posterior foi longo". O lado
fucsia (ALTA) e' justamente o que deu retorno NEGATIVO: depois da
absorcao apos queda, o preco tendeu a **cair mais**.

Ele mesmo tinha marcado a ressalva: "e' uma analise POS-FATO, facil de
ver no grafico e assumir que foi o melhor ponto". A ressalva estava
certa.

### LEITURA HONESTA

Isto **nao e'** evidencia de que absorcao funciona invertida. E':

- um efeito marginal (folga 0,036),
- num lado so',
- com um controle sem absorcao mostrando a mesma direcao com |t| maior,
- e sem penalizacao pela multiplicidade de 4 comparacoes.

O que ha' de solido: **o lado BAIXA tem resposta clara** — media +6,6,
`t` 0,361 com n=251. A absorcao apos alta nao antecipa queda, e agora com
amostra folgada.

**NAO ha' quarta variante disponivel.** 2025 era o ultimo periodo cego.
Qualquer teste adicional exige dado novo — capturado adiante pelo
`record`, ou 2024 e anteriores do grafico, que passariam a ser uma nova
declaracao com a multiplicidade acumulada contada.

## FASE DE ENTENDIMENTO (nomeada pelo operador, 2026-09-04)

> "Precisamos explorar os achados com mais dados. Nossos proximos passos
> e' identificar isso para explicar mais, e nao so' aprova/reprova."

**Ela nao existia.** Todo o pipeline respondia aprova ou reprova; nada
respondia **onde e quando**.

### O que a media esconde

Uma media de -4,55 sobre 10.305 barras pode ser duas coisas opostas:

    (a) -4,5 em quase toda barra   -> difuso, nao operavel, morre no custo
    (b) -40 nos dias que andam,
        0 nos dias parados         -> CONCENTRADO, e talvez operavel

A media nao distingue, e o pre-registro nao foi feito para explicar.

### A regra da fase

**Diagnostico em amostra QUEIMADA e' ilimitado.** Decompor por lado, tipo
de dia, hora, regime — quantas vezes quiser, sem gastar trial.

**Mas ele NAO valida.** Qualquer numero achado assim e' HIPOTESE. Testar
exige declaracao propria e amostra que nao seja aquela.

### A armadilha que o modulo admite sozinho

Decompor em muitas celulas **garante** que alguma pareca significativa.
Com 12 celulas sob H0, a chance de ao menos uma passar de |t| 1,96 e'
**46%**. `resumir()` reporta celulas olhadas contra esperadas por acaso —
sem isso, destacar a mais forte de doze parece achado e e' aritmetica.

### `profit-tape decompor-efeito`

Decompoe por LADO e por TIPO DE DIA:

    forma do dia    |close - open| / range   -> oscilou / misto / andou
    tamanho do dia  range                    -> parado / medio / amplo

**Duas limitacoes que o comando declara na saida:** a forma do dia usa o
dia INTEIRO, entao nao serve para decidir em tempo real — serve para
EXPLICAR. E os tercis sao do proprio periodo, nao limiares
transferiveis.

### Primeiro uso, em maio (DEPURACAO, 817 observacoes de controle)

    dia que ANDOU     AQUA +48,0 (t 2,20)   FUCSIA -44,9 (t -2,16)
    dia que OSCILOU   AQUA +17,5 (t 0,88)   FUCSIA +24,4 (t 1,06)

Nos dias que andaram, os dois lados sao fortes e em **sentidos
opostos**; nos que oscilaram, os dois sao fracos. Coerente com a
intuicao do operador: **o efeito se concentra nos dias que andam**.

5 celulas extremas de 12, contra 0,6 esperadas — mais que acaso, e ainda
assim **nao e' evidencia**: maio ja' foi usado varias vezes, a forma do
dia so' e' conhecida no fim, e os tercis sao locais.

### O que isto abre, e o que ainda falta

Se o efeito for mesmo concentrado, a pergunta seguinte **nao e'** se ele
existe — e' se da' para **identificar o tipo de dia ANTES**, e isso e'
outra hipotese, com pre-registro proprio.
