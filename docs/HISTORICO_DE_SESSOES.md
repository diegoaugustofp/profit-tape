# Histórico de sessões — profit-tape

Log cronológico, uma entrada por sessão de trabalho. Cada entrada resume
o que foi feito, organizado por assunto, com ponteiro para as
tags/versões entregues e os documentos de referência tocados.

**Este arquivo é sobre "o que aconteceu quando"** — para o estado ATUAL
de um assunto específico (não o histórico de como se chegou lá),
consulte o documento de assunto correspondente:
- `docs/RESEARCH_PLANO.md` — pesquisa, sinais, decisões de estratégia
- `docs/EA_ARQUITETURA.md` — arquitetura do EA, decisões de integração
- `docs/OPERACAO.md` — rotinas operacionais, infraestrutura
- `docs/BOAS_PRATICAS_PROGRESSO.md` — convenção de progresso/logs

## Como adicionar uma entrada nova (para sessões futuras)

> **Entrada por SESSÃO, nunca por marco intermediário.** Em 2026-08-30
> uma sessão longa ganhou duas entradas — uma escrita no meio (v1.12 a
> v1.30) e outra no fim (v1.12 a v1.42) — que se sobrepunham e ainda
> ficaram fora de ordem cronológica. Se a sessão continuar depois de já
> ter entrada, **edite a existente** em vez de acrescentar outra.
>
> Ordem do arquivo: **mais recente primeiro**.

Ao final de cada sessão, adicione uma entrada abaixo (mais recente no
topo), seguindo o modelo: data, resumo por assunto, tags entregues,
pendências que ficaram em aberto. Não repita detalhe que já está nos
documentos de assunto — só resuma e aponte.

---

## 2026-08-30/31 — drawdown: desenho, pré-voo e encerramento (v1.45–v1.47)

Continuação da sessão de 29/08, depois de atualizar o clone para
v1.44. Três perguntas já estavam fechadas na sessão do dia; esta abre a
única que o CONTRA da Rota B deixou explicitamente em aberto.

### Avaliação do estado, à luz do que a outra sessão fechou
- Rota B respondida (CONTRA) pelo caminho da fita — o que eu tinha
  chamado de "substrato correto" no fim de 29/08. Overshoot medido em
  zero: toda a discussão de 29c sobre limites de preenchimento era
  irrelevante na prática para o WINFUT. Registrado como correção do que
  eu argumentei.
- O diagnóstico do operador ("misturamos barra de preço com barra de
  volume") estava certo no centro (o problema ERA a barra) e errado nas
  bordas: não era específico de volume, e a Rota B era respondível
  neste modelo — não precisava ir para outro.
- Backfill histórico: fechado. `GetHistoryTrades` rejeita >30 dias; os
  25 pregões JÁ SÃO o máximo retroativo.
- **A barra de 4,07 não é feita de amostra**: 504 trials fixam o piso em
  3,05; 100 pregões só compram 0,28. Esperar 3 meses é a alavanca mais
  fraca, não a mais forte. Caminhos sem esperar levantados com risco e
  trade-off: recontar trials efetivos (maior efeito, maior risco
  epistêmico), WDO em paralelo (dado independente hoje, 1 trial),
  perguntas sem limiar de descoberta (drawdown, forward test, deploy do
  validado), gastar zero. Operador escolheu: drawdown, depois WDO,
  depois recontagem.

### Drawdown — desenho
- O CONTRA reframeia a pergunta: stop fixo tem custo esperado ≈ 0 em
  expectativa, com IC ±50/op. O trade-off pode ser só de variância.
- Regra 0 aplicada: DECOMPOR antes de escolher mecanismo. Três fontes,
  três mecanismos. Quarto mecanismo trazido pelo operador (trailing de
  150) registrado com três ressalvas: é distinto do que a Rota B testou,
  150 é prior e não calibração, e o modo de falha em sinal de cauda
  contrarian ("+150 → 0 → +400") é mensurável.
- Estimadores com argumento de não-viés ANTES do código (tempo de
  parada na fita / na sequência de operações). Portão em forma nova:
  separar componente de variância (embaralhado) de componente de regime.
- Decisões pendentes do operador: regra de aceite e grade de L.

### Pré-voo implementado (v1.45)
- Descoberta: `ea-replay-lote` NÃO persistia as operações. Registro rico
  no gestor (`historico_detalhado`, sem mudança de comportamento) +
  persistência em parquet.
- `decomposicao-drawdown`: 3 maiores drawdowns, três parcelas cada,
  regra de dominância fixada antes (≥ 0,50 senão DIFUSO), jackknife e
  bootstrap por pregão. Conferido à mão. 8 testes, 367 no total.
- Meu validador de âncoras ad hoc estava ERRADO (colapsava `--` em `-`);
  o oficial `tools/valida_ancoras.py` é o certo. Só ele daqui em diante.

### 31/08 — dois pré-voos falharam, do jeito certo (v1.46)
- 1a rodada: `data/raw` local só tinha 27/08 → 5 ops em 1 pregão →
  parcelas 1,00/1,00/1,00 por tautologia. Checagem de população pegou.
  Causa já documentada em OPERACAO.md como "recomendação não
  implementada". Agora implementada: `decomposicao-drawdown` recusa
  < 5 pregões.
- 2a rodada, apontada para o backup: 25 pregões, MAS **147 ops / +3883 /
  Calmar 2,85** contra **157 / +418 / 0,23** de 28/08. Mesmo código
  (`git diff` em `ea/`: zero linhas), mesmo config. Replay é
  determinístico ⇒ os ARQUIVOS diferem. Hipóteses: backup não é cópia
  fiel (incidente dos 96 footers + re-download via GetHistoryTrades sem
  reentregas), ou leu de curated (dedup). Toca o conflito de docs
  (errata 21/08 "sem duplicata" vs 22/08 "volume real é metade") — agora
  com número: 9× no P&L. **Anterior ao drawdown.** Nenhum dos dois tem
  direito a ser chamado de "a rodada de 25 dias".
- `inspect` ficou 8h mudo tentando responder: concatenava 25 pregões em
  memória sem imprimir. Corrigido (contagem por metadados em segundos,
  guarda de tamanho, `--dia`, progresso). 7 testes, 374 no total.

### 31/08 — resolvido: três rodadas, uma válida (v1.47)
- `duplicatas` em 07-24: 100% do dia entregue duas vezes, campos
  idênticos. Curated deduplica certo. 12 de 25 dias com backfill em
  dobro no raw; os 5 dias de realtime batem com curated (< 250 linhas):
  **o stream ao vivo é limpo**, o EA em produção vê o equivalente ao
  curated. Conflito de docs 21/08 vs 22/08 resolvido — os dois certos,
  sobre árvores diferentes.
- Replay sobre curated: **99 ops, +6356, Calmar 4,08**. Validação
  interna: os 13 dias limpos batem operação por operação com a rodada
  do backup. Determinismo confirmado.
- **A pergunta de drawdown está ENCERRADA**: Calmar 0,23 era artefato.
  Sobre dado válido não há problema de drawdown a resolver.
- Achado real da decomposição: trechos 2 e 3 dominados por −601, −626,
  −576 — **três perdas além do stop catastrófico de 500**, porque
  `motivo_de_saida` checa só no close da barra. O mecanismo vivo de
  proteção de capital não cumpre a própria spec. Correção = checagem
  contínua na fita; sessão de desenho (muda caminho de execução).
- Default de `ea-replay-lote --raiz-raw` → `data/curated` (decisão do
  operador, dado o fluxo real: raw local = só o último dia).
- Números anteriores marcados como contaminados no RESEARCH_PLANO
  (28/08 circuit breaker/Calmar; 27/08 MAE 4,5%).

### Pendências
- Sessão de desenho: stop catastrófico contínuo na fita (o EABridge já
  vê cada negócio; falta o gestor de risco reagir por negócio).
- Conferir `motivo` das três operações além do stop no
  `operacoes_replay.parquet`.
- Entender +64/op (EA) vs +18/op (research) no mesmo dado — o filtro
  "uma posição de cada vez" seleciona 99 de ~178 gatilhos.
- Refazer `mae-analise` e o acompanhamento do circuit breaker sobre
  curated (zero custo, só para os documentos pararem de citar números
  contaminados).
- Depois: WDO (caminho 2) e recontagem de trials (caminho 1).

### Pendências antigas (superadas)
- Operador: `inspect <backup> --contagem` e `inspect data\curated
  --contagem`; qual `--raiz-raw` usou na 2a rodada; `duplicatas` sobre
  um dia presente nas duas árvores.
- Só depois de reconciliar: `decomposicao-drawdown` sobre a árvore
  certa.
- Com a fonte dominante em mãos + regra de aceite + grade de L:
  pré-registro do trade-off.

## 2026-09-01/02 — a hipótese do operador, do zero ao teste (v1.51 a v1.74)

Entregas v1.51 a v1.74. **Um trial declarado** (2026), nenhum consumido
ainda — todas as rodadas foram depuração.

### O que aconteceu

A sessão anterior fechou com `absorcao_dir` levando CONTRA. Esta começou
com o operador trazendo **material próprio** sobre absorção x exaustão e
a percepção de que estava misturando dois conceitos.

**A formalização antiga media o OPOSTO do conceito.** `absorcao_dir` tem
extremos quando `|desloc_norm|` é GRANDE — marubozu, mediana 0,807 nas
barras pintadas. Absorção é `|desloc_norm|` PEQUENO: doji com pavio.
Correlação do evento novo com `z_absorcao_dir`: **−0,03**. Ortogonais.

**A hipótese nova saiu da leitura de tela dele**, não de mim procurando
fórmula bonita — as duas que tentei assim morreram: `absorcao_dir`
gastou 12 trials, e `esforco` já existia no `flow.py` como `absorcao`
(correlação +1,0000).

### O que ficou construído

    triagem            redundância/cauda/construção antes de pré-registrar
    absorcao_barra     estimador do pré-registro congelado
    absorcao_grafico   mesma coisa sobre dump do gráfico (amostra independente)
    absorcao_inspecao  por que ESTA barra marcou (ou não)
    absorcao_barra.ntsl  indicador, verificado contra o Python

### Estado do teste

Pré-registro **congelado**, portão passa, e as duas rodadas deram
`INCONCLUSIVO` por `n < 30`. Ambas foram **depuração**: cada uma revelou
um defeito de implementação contra o que o pré-registro já dizia.

**Trial de 2026 declarado** (02/01–30/04 e 01/06–23/07), aguardando dump.
2025 reservado.

### Três defeitos achados pela INSPEÇÃO VISUAL, nenhum por olhar retorno

1. **O contexto media o GAP NOTURNO.** `mov_contexto` atravessava a
   virada do pregão: mediana 3,58 nas 6 primeiras barras contra 0,80 no
   resto, com o habilitador em 3,0. **42% dos eventos caíam em 5% do
   pregão.** Achado na barra de 14/05 — "uma barra forte que INICIA o
   movimento", o oposto de absorção.
2. **A fórmula pintava marubozus.** Achado na barra de 31/08.
3. **O `z` divergia entre `.ntsl` e Python** em até 19,86. O texto
   congelado dizia "vs 50 barras" sem especificar se a barra atual
   entrava, e as duas implementações resolveram para lados opostos.

### A estrutura que o operador propôs

**Amostra de DEPURAÇÃO x amostra de TESTE.** A visual acha bug e defeito
de spec; a estatística responde a pergunta. Com o limite escrito: pode
questionar a FÓRMULA, não pode questionar a CALIBRAÇÃO.

### Erros meus, e o padrão que os une

`.ntsl` que não logava nada (indexei chamada de função, usei `Abs()`
inexistente, `Integer` no log). Guarda com acesso posicional dentro de
condição — "comportamento indefinido", e guarda que talvez não funcione
é pior que nenhuma. Purga corrigida no Python e **não** no `.ntsl`.
Módulo `recuperacao.py` construído sem ver que o `backfill` já fazia
aquilo. Dimensionamento errado em 29% por extrapolar janela curta.
Commit com suíte vermelha, **duas vezes**, por encadear `pytest | tail
&& git commit`.

O padrão: **nos três casos de divergência entre `.ntsl` e Python havia
teste, e nos três ele passou** — dois comparavam números, um comparava
contagem de campos. Nenhum comparava o que o código FAZ.

### Git

`git push origin HEAD:main` **orfanou** o commit da declaração de
período, feito pela web. E o refspec `nome:nome` dos bundles acumulou
**47 branches espúrios**, até o merge falhar com "refname is ambiguous".

## 2026-08-30/31 — sessão completa: CONTRA na absorção, equivalência fechada, Rota B respondida (v1.12 a v1.42)

**31 entregas. Zero trial gasto além dos 12 pré-registrados.** O
`trials.json` permanece em 504.

Três perguntas em aberto foram FECHADAS, todas com resposta negativa —
e negativo aqui é resultado, não fracasso.

### 1. Absorção direcional: CONTRA nas 12 células

Melhor célula com o sinal previsto e superando ambos os controles, mas
|t| 3,06 contra os 4,03 exigidos. A porta de "falta de poder" não abriu
por 0,03 de consistência.

A porta do pré-registro 3 (promover por falta de poder) não abriu:
maior consistência **0,82** contra os 0,85 exigidos.

**O achado que explica melhor que o IC**: `absorcao_dir` é
**sub-gaussiana por construção**. Os dois termos são limitados a
[-1,+1], logo o composto tem teto [-2,+2] — e o observado ficou em
**[-0,847; +0,897]**, menos da metade. |z| >= 2,5 aparece em 6% da
frequência de uma normal. A hipótese era sobre barras extremas; a
fórmula não consegue produzir barras extremas. Álgebra, não estatística.

### 2. Equivalência NTSL <-> profit-tape: FECHADA

    imbalance    EXATO   2001/2001, diferenca maxima 0,000000
    desloc_norm  1 tick  47% das barras, so em open/close
    z            2,4e-8  reproduz normalize.py

Causa única: o OHLC do gráfico usa o primeiro e o último negócio de
QUALQUER tipo; o do profit-tape usa só agressão.

**Três explicações, duas refutadas pelo próprio diagnóstico.** As duas
primeiras reproduziam o SINTOMA perfeitamente — divergência presente, do
tamanho previsto, ausente quando `imbalance` era exato. Em três momentos
teria sido possível fechar dizendo "divergiu como previsto", certo sobre
o sintoma e errado sobre a causa.

### 3. Rota B: CONTRA — o stop não detecta reversão

Pergunta aberta desde 2026-08-27, respondida. |t| máximo 0,76 nos sete
pontos, `n` suficiente em todos, IC95 contendo zero.

**O que destravou**: `F` exato lido do tape negócio a negócio. Os dois
estimadores anteriores morreram da mesma causa — o extremo de uma barra
não é tempo de parada, só é conhecido no fechamento e usa informação do
futuro dentro da barra. Com `F` = primeiro negócio a cruzar, o teorema
da parada opcional dá `E[preço_final - F] = 0`: o estimador é
não-enviesado POR TEOREMA, e o portão vira confirmação de implementação.

**Sensibilidade com RLP: resultado idêntico até a última casa**, com o
tape 39% maior. Nenhuma das 1.246 combinações mudou de status — um print
de RLP nunca foi o primeiro a cruzar um nível. Fecha com a equivalência
NTSL por caminho independente: cruzar um nível é fazer extremo novo, e o
RLP não faz extremo.

### Descobertas de infraestrutura que mudaram decisões

- **Orçamento real era 492 trials, não 42.** O `RESEARCH_PLANO`
  registrava "42 trials" desde 2026-08-23 e nunca foi atualizado; o
  `trials.json` real fecha em 492. 73% vieram de uma varredura de 8
  símbolos (WDOFUT, PETR4, VALE3, ITUB4, BOVA11, BBAS3, MGLU3, WEGE3)
  que rodou em ~1 minuto — e o contador está CERTO em cobrar por ela: os
  oito foram olhados procurando algum passar. `t_critico` saltou de 3,31
  para 4,03.
- **Buffer do console enche de trás para frente**: mais histórico no
  gráfico = log termina mais cedo. Três dumps vieram cada vez mais
  antigos antes de o padrão aparecer.
- **`WINFUT` no gráfico é série contínua ajustada**, com `k` mudando nas
  rolagens (1,020480 -> 1,000000 dentro da própria amostra).
- **Plugin Tape Reading confirmado ativo**; `AgressionVolBuy+Sell` é
  exatamente `QuantityVol(False, True)`.
- **`volume_barra` não era gravado** em lugar nenhum — só impresso na
  tela. Agora `features` grava `resumo.json`.

### NOVE erros meus, todos pegos por verificação e nenhum por cuidado

1. Calibração do portão errada em duas ordens de grandeza — bloqueou o
   braço de 1m sem motivo.
2. `_contar_buracos` falso por construção: devolvia zero para qualquer
   entrada.
3. Validador de âncoras achando zero links e reportando "nenhum
   quebrado" sobre nada — havia 23 quebrados.
4. Parser de número produzindo `NaN` silencioso; o comparador ignora
   `NaN`, então o campo sumiria em vez de acusar.
5. `str_replace` reportando sucesso sem alterar nada.
6. Teste do `z` na borda do parquet — janelas de conteúdo diferente por
   construção.
7. **Portão que não conseguia passar**: `CONTRA` inatingível por falta
   de amostra sintética.
8. **SHA errado numa verificação** que teria confirmado falsamente a
   versão errada.
9. **Commit com a suíte vermelha**: `pytest | tail && git commit` — o
   `tail` retorna zero.

O padrão que atravessa quase todos: **um verificador que falha de um
jeito que parece resultado.**

Tags `entregue-v1.12` a `entregue-v1.42`.


## 2026-08-29/30 — indicador de absorção para NTSL: do plano ao CONTRA

Sessão que começou com o pedido de planejar um indicador NTSL de barra
de absorção para o Profit Chart, e terminou com a hipótese encerrada
pelo próprio método, sem nenhuma linha de NTSL escrita.

**Inversão de arquitetura.** O roadmap inicial era indicador → sinal →
robô. O manual do NTSL mostrou que as funções de agressão são
licenciadas (Pro/Ultra/Scalper), que `VolumeAtPrice` tem histórico
documentadamente curto, que o livro não tem histórico nenhum na
automação, e que `SoAgressores` é **silenciosamente ignorado** sem o
opcional Plugin Tape Reading. Conclusão: pesquisa no profit-tape, NTSL
como camada de visualização e execução.

**Descoberta de orçamento.** O `RESEARCH_PLANO.md` registrava 42 trials
desde 2026-08-23; o `trials.json` real fechava em **492**, dos quais 360
(73%) vieram de uma varredura de 8 símbolos que rodou em ~1 minuto. O
`t_critico` efetivo saltou de 3,31 para 4,03. Registrado como lição:
varredura ampla é barata em máquina e cara em orçamento estatístico.

**Três erros meus, achados antes de custar trial.** (1) O gerador de
ruído do portão errou a escala em duas ordens de grandeza — barra de 7
ticks contra os 35 reais — o que inflou o viés de bounce e me levou a
bloquear o braço de 1m por engano; revogado após recalibração.
(2) `_contar_buracos` era falso por construção: a renumeração densa dos
baldes apagava os vazios e o contador devolvia zero para qualquer
entrada. (3) O `--log-file` dos comandos novos herdava o nível do
console e sairia vazio.

**Resultado.** CONTRA nas 12 células. Melhor célula: `z_absorcao_dir`
h=1 no 5m, IC −0,0342 no sinal previsto, superando ambos os controles,
mas com |t| 3,06 contra os 4,03 exigidos. A porta de "falta de poder" do
pré-registro 3 não abriu — maior consistência 0,82, contra os 0,85
exigidos. Detalhe em `RESEARCH_PLANO.md`.

**O que a sessão preservou.** Nada foi resgatado por reanálise. O
pré-registro de 2026-08-29e antecipou por escrito que o IC é fraco para
efeito de cauda e que mesmo assim seria o portão — e essa frase foi o
que impediu, no fim, transformar um negativo em "o teste era
inadequado".

Tags `entregue-v1.12` a `entregue-v1.20`.

## Sessão 2026-08-29 (revisão de desenho da Rota B)

Sessão de DESENHO, não de implementação — nenhuma linha de código de
comportamento foi escrita, deliberadamente (regra 7 da skill
`profit-tape-disciplina`). Versões entregues: `entregue-v1.06` (pré-registro),
`entregue-v1.07` (congelamento), `entregue-v1.08` (implementação),
`entregue-v1.09` (anulação + pré-registro 2),
`entregue-v1.10` (congelamento do pré-registro 2),
`entregue-v1.11` (estimador + portão, que reprovou o desenho).

### Rota B — revisão desde o início
Revisada a cadeia inteira de decisões (26/08 tensão original → 27/08
pré-registro → congelamento do par → implementação → colapso). Dois
achados:

- **O argumento de consistência estava invertido.** A checagem por
  close foi justificada como "medir e executar do mesmo jeito". A
  conclusão correta é a inversa: medir do jeito que se pretende
  EXECUTAR. `mae.py` não consome trial, remedir era barato. Como
  bônus: com h=3, Rota B só podia divergir de Rota A em t+1 e t+2 —
  dois pontos de decisão em troca de toda a complexidade.
- **Segundo defeito, que sobreviveu ao primeiro e nunca foi
  resolvido**: a decisão de Rota A rejeitou alvo fixo porque "cortaria
  as caudas que pagam a conta", e o congelamento instalou alvo em 120
  com p90 do MFE em 412,5. O elo 4 não refutou o elo 2 — passou por
  cima dele. **ALVO descartado como conceito para `z_agf_3`.**

### Pré-registro novo
"Existe reversão condicional em z_agf_3?" — separa duas hipóteses que
estavam misturadas: stop como LIMITE DE PERDA (a, motivado por Calmar
0,23) vs stop como DETECTOR DE REVERSÃO (b, afirmação inferencial
ainda não testada). Testa só (b), com grade de X fixada antes,
exigência de monotonicidade, contra-hipótese contrarian registrada, e
regra de parada. Não consome trial. **Congelado pelo operador em
2026-08-29**, antes de qualquer código e de qualquer contato com o
dado — alteração de critério exige pré-registro novo.

### Implementação
- `research/reversao.py` + comando `reversao-condicional`: executa o
  critério congelado literalmente (grade e n mínimo no código, não como
  opção de CLI). Comparação implementada entre grupos DISJUNTOS, não
  contra o incondicional que os contém — correção estatística
  registrada no `RESEARCH_PLANO.md`, não ajuste silencioso.
- 14 testes novos (279 no total), conferidos à mão antes dos
  automatizados. Bug real pego pelo próprio teste: o desfecho mais
  provável (ponto significativo sem n acima dele) não nomeava quais X
  ficaram curtos — corrigido o relato, não o teste.

### Resultado ANULADO, e a lição
- A rodada real (162 ops, 22 pregões) devolveu FAVORAVEL a (b), X*=60,
  com t entre −7,5 e −13,2. **Anulado**: o estimador tinha tautologia
  embutida — `MAE_intrabar >= perda bruta final` por construção, então
  o grupo "não tocou −X" não pode conter nenhum perdedor maior que X.
  A comparação era aritmeticamente forçada.
- Duas impressões digitais que confirmam: `dif` praticamente constante
  na grade inteira (efeito real ficaria mais forte com X), e o teste de
  honestidade sobre random walk puro devolvendo o MESMO FAVORAVEL com
  t ≈ −25.
- A regra 0 foi aplicada ao MECANISMO (stop contínuo faz sentido — e
  continua fazendo) mas não ao ESTIMADOR. Congelar um pré-registro não
  torna válido um estimador viciado.
- Anulação legítima porque o argumento é **a priori**: a álgebra é
  provável sem olhar o dado e o defeito se reproduz em ruído puro. Não
  é "não gostei do número" — dava para provar antes de rodar.
- **Regra nova**: teste de honestidade sobre ruído puro vira PORTÃO
  obrigatório antes de interpretar qualquer estimador novo, reportado
  no mesmo relatório do resultado real.

### Pré-registro 2 (2026-08-29b)
- Estimador corrigido: condicionamento e desfecho em segmentos
  **disjuntos** do caminho. Pergunta = "no instante τ em que eu sairia
  a −X, qual a expectativa de CONTINUAR?". Uma amostra contra zero, sem
  grupo de comparação — elimina de raiz o problema de subconjunto vs
  superconjunto.
- Custo medido BRUTO de propósito (cancela entre sair e segurar).
- Preenchimento `F` em dois limites (pessimista = extremo da barra de
  cruzamento, otimista = nível do stop), com leitura e escalonamento
  para o tape trade a trade definidos ANTES.
- Mesma grade de propósito — trocar grade junto com estimador tornaria
  impossível separar os dois efeitos.

### Pendências que ficaram em aberto
### Portão reprovou o pré-registro 2 — antes de tocar o dado real
- `research/remanescente.py` implementado, e o portão de honestidade
  rodou primeiro. Sobre ruído puro o limite **pessimista** devolve
  +28 a +33 pts com t entre 8 e 13: viés estrutural, não ruído.
- Causa: `F_pessimista` é o **extremo** da barra de cruzamento.
  Selecionar num extremo garante que o resto do caminho pareça
  favorável. É a mesma família do erro anterior, espelhada — um
  condicionava no extremo e media até o fim, este mede a partir dele.
- O veredito sobre ruído foi INCONCLUSIVO POR PREENCHIMENTO, que no
  critério congelado **manda construir o tape**. O ruído sozinho
  dispararia uma escalada de infraestrutura.
- Portão endurecido: ruído puro tem de devolver CONTRA (b). Qualquer
  outro veredito é reprovação.
- Dois defeitos meus corrigidos: gerador de ruído incoerente (amplitude
  sorteada por fora do passeio) e razão amplitude/desvio medida através
  da virada de pregão.
- **Segundo estimador inválido em dois — mas este morreu antes de tocar
  o dado.** É exatamente para isso que o portão existe.

### Pendências que ficaram em aberto
- Pré-registro 3: descartar o limite pessimista e usar o ruído como
  NULO EMPÍRICO em vez de zero.
- Checagem de pré-voo: reconciliar 162 ops/22 pregões contra os 336
  gatilhos/26 dias da análise de MAE de 27/08.
- Medição do custo em expectativa do stop-como-(a) — pré-registro
  separado, depois que (b) resolver.
- Todas as pendências da sessão anterior seguem abertas.

---

## Sessão 2026-08-27 a 2026-08-28 (sessão longa, ~um dia inteiro)

Sessão excepcionalmente longa e densa — do planejamento matinal até
correção de CI de madrugada do dia seguinte. Versões entregues:
`entregue-v0.73` até `entregue-v1.02` (aprox. 30 incrementos).

### Infraestrutura
- NSSM configurado e validado em produção (teste de resiliência real
  passou). `schtasks` trocado para chamar `nssm start`.
- Travamento de máquina tratado: ferramenta `triagem-inprogress`
  criada para automatizar a limpeza pós-incidente (promove arquivo com
  footer válido, quarentena o resto).
- `quarentena` ganhou filtro de data (`--dia`/`--desde`/`--ate`).
- Bug real de isolamento de teste corrigido (`cache_logger_on_first_use`
  vazava configuração global do `structlog` entre testes).
- **CI corrigido em 3 causas distintas, sequenciais**: (1) `pandas-stubs`
  faltando revelou 162 erros reais de tipo, corrigidos um a um; (2)
  `mypy` não conseguia nem parsear o stub do `numpy` (sintaxe Python
  3.12+, `python_version` do projeto desatualizado); (3) o interpretador
  Python 3.11 do próprio CI não sabe interpretar essa sintaxe,
  independente de configuração — matriz do `ci.yml` atualizada para
  3.12/3.13. Um teste intermitente (`sleep` fixo em teste de thread)
  também corrigido.
- **Lacuna de versionamento descoberta e corrigida**: `git push origin
  HEAD:main` nunca enviava as tags `entregue-vX.YY` — só a branch.
  Corrigido para sempre incluir `--tags`.

### EA — arquitetura
- Bug crítico de performance resolvido: `ea-replay` travava horas em
  `pyarrow.dataset().to_table()` — trocado por leitura arquivo-a-arquivo.
- Decisão de arquitetura fechada: EA roda **dentro** do processo do
  `record` (licença Nelogica permite só uma chave de ativação).
  Implementado e testado ponta a ponta (`EABridge` + `record --ea-config`).
- `lado_permitido` (restrição de direção) implementado, pré-registrado,
  testado: veredito **favorável** para venda-apenas (mesmo período, não
  out-of-sample nova).
- Curva de patrimônio/drawdown implementada e conectada ao
  `ea-replay-lote`.
- **Rota B (alvo/stop fixo) implementada, depois questionada com razão
  pelo operador**: o mecanismo de checagem só no fechamento de barra
  (não contínuo, tick a tick) não tem lógica de stop/alvo de verdade —
  identificado como o tipo de erro que a regra "valide o mecanismo antes
  de calibrar número" (skill `profit-tape-disciplina`) existe para
  evitar. **Ficou pendente**: desenhar do zero uma Rota B com checagem
  contínua (por trade, não por barra) antes de qualquer nova tentativa.
- `pydantic` das configs do EA (`SinalConfig`/`RiscoConfig`/`EAConfig`)
  ganhou `extra="forbid"` — fecha uma classe de falha silenciosa real
  (campo desconhecido no YAML era ignorado sem erro).

### Pesquisa
- MAE/MFE implementados, com correção de bug real (pool out-of-sample).
- Assimetria compra/venda confirmada por 3 métodos independentes
  convergindo na mesma direção.
- `risco-realizado` (VaR/ES) implementado — conexão de design real com
  a escolha de barras por volume (tempo intrínseco, mesma linhagem
  teórica do "volume clock" que já sustentava o projeto). Achado:
  sazonalidade intradiária afeta calibração de risco, não só o IC.
- `z_agf_8` (fluxo UBS) **fechado** nos dois fronts (ações: morto pelo
  custo, confirmado duas vezes; WINFUT: não passou no IC já testado em
  2026-08-23) — sem gastar trial novo.
- Correção de custo de ações real: planilha da XP decodificada, custo
  tem componente fixo + proporcional ao financeiro.
- Disciplina formalizada: `features` sem custo (roda sempre);
  `research` com custo real (só com dias novos suficientes acumulados).

### Documentação e disciplina
- `docs/BOAS_PRATICAS_PROGRESSO.md` criado (visibilidade de progresso
  em processos longos).
- Política de retenção disco local vs backup documentada (lacuna
  identificada, convenção fixa ainda não decidida).
- Dois *skills* criados: `profit-tape-disciplina` (metodologia —
  pré-registro, validar mecanismo antes de calibrar número, amostra
  pequena) e `profit-tape-engenharia` (versionamento, desenvolvimento,
  logs — inclui o procedimento de bootstrap de sessão nova a partir do
  GitHub).

### Pendências que ficaram em aberto
- Forward-test em DEMO com pregão real (infraestrutura pronta, nunca
  testada em condição real).
- Rota B: redesenhar com checagem contínua antes de tentar de novo.
- Zeragem por consumo de garantia (fora de escopo da curva de
  patrimônio atual).
- Segmentação de IC por horário (feita para risco, não para o IC do
  sinal em si).
- Robustez em regime de mercado diferente.
- `research` aguardando mais dias (decisão do operador).

---

## Sessões anteriores (antes de 2026-08-27)

Não recompiladas em detalhe aqui — o contexto desta sessão longa
começou com um resumo compactado de conversas anteriores (catalogadas
em `journal.txt`, junto aos transcripts brutos, fora deste
repositório). Se precisar de detalhe de uma sessão anterior a
2026-08-27, comece pelos documentos de assunto (`RESEARCH_PLANO.md`,
`EA_ARQUITETURA.md`) — eles têm entradas datadas desde 2026-08-23.

**Exceção reconstruída (2026-08-29, a pedido do operador)**: o incidente
de agendamento/crash do `record` em **2026-08-25** (próximo da tag
`entregue-v0.51`) foi documentado retroativamente em
`docs/OPERACAO.md` — a busca em conversas anteriores não localizou a
sessão original, mas o operador forneceu um fragmento do diagnóstico
da época que permitiu reconstruir o registro com precisão (tarefa
disparou no horário certo, processo crashou com exit code `1`, causa
exata nunca confirmada, decisão de não perseguir mais fundo e resolver
via NSSM). Ver a seção "INCIDENTE: agendamento disparou, processo
crashou, causa exata nunca encontrada" em `OPERACAO.md`.

---

## Sessão 2026-08-31 (tarde) — desenho do stop contínuo, instrumento do pré-voo

Sessão de DESENHO, continuação direta do encerramento do drawdown da
manhã. Nenhuma mudança de comportamento do EA.

- **Premissa confirmada** no `operacoes_replay.parquet`: as três perdas
  além do limite (−626, −601, −576 líquidos) são todas `STOP
  CATASTROFICO`, todas de VENDA, com excursões de 615/590/565 contra um
  limite de 500. Diferente do drawdown, esta premissa se sustenta.
- **Descoberta de percurso**: o caminho por trade já existe no `service.py`
  (`_on_trade` enfileira todo negócio, o loop já chama
  `processar_trade_bruto` para cada um). Não precisa de callback, thread
  nem mudança de latência — a implementação é cirúrgica.
- **Errata real achada no `mae.py`**: `pnl_medio_com_stop_hipotetico`
  modelava o stop do CLOSE saindo exatamente no limite, que é o
  comportamento do regime CONTÍNUO. Media o regime proposto e o rotulava
  como o atual; os dois nunca tinham sido separados. Removido.
- **Instrumento entregue** (`entregue-v1.48`): três regimes de saída,
  contagem no limiar por lado, excesso de conformidade, e o conjunto
  MARGINAL (com quantas terminam positivas) — o número que decide se a
  mudança é conformidade ou mecanismo novo.
- Conferido à mão antes dos testes (regra 4): 11 valores calculados no
  papel, todos batendo. 381 testes, ruff limpo, mypy strict limpo.

**Pendente**: rodar `features` + `mae-analise` e escrever o pré-registro
com o teto de frequência comprometido ANTES de ver o efeito no P&L.

### Continuação (2026-08-31c) — pré-voo rodou, pré-registro congelado

- **Pré-voo rodou** (`entregue-v1.48`): o modo de falha que se temia NÃO
  se materializou — 0 de 16 marginais terminaram positivas. O stop
  contínuo não corta caudas ganhadoras neste sinal.
- **Mas apareceu um custo não contado**: as marginais terminam em −390,3 e
  o contínuo as mata em −500 (~110 pts cada). O "270 pts a menos"
  registrado de manhã contou só a economia nas três que já batiam, e não
  que o contínuo também dispara onde hoje não dispara (venda 10 → 16).
- **Conformidade medida**: excesso do close além do limite — mediana 65,
  máximo 305. Um stop de 500 que sai em −805 não é um stop de 500.
- **Lacuna do instrumento v1.48 corrigida**: os três regimes de P&L saíam
  só agregados, e a compra (sem edge, 10 marginais contra 7 que já batem)
  puxava o agregado de um lado que o EA nem opera.
- **Pré-registro CONGELADO** (`entregue-v1.49`): não-inferioridade, não
  superioridade. IC95 bootstrap pareado (bloco de pregão) sobre a VENDA,
  aceita se o limite inferior > −3,0 pts/op. Limite fixado pelo operador
  antes de a quebra por lado existir; congelado no código, não exposto
  como opção de CLI.
- 389 testes, ruff limpo, mypy strict limpo. Dois cenários conferidos à
  mão antes dos testes (CONTRA e FAVORAVEL, IC determinístico com um dia).

**Pendente**: rodar e observar o veredito.

### Continuação (2026-08-31d) — CONTRA registrado, CI consertada, pré-registro de conformidade

- **Veredito da não-inferioridade: CONTRA** (−3,28 contra critério de
  −3,0). Mantido. Registradas as saídas erradas que a margem de 0,28
  tornava tentadoras, sobretudo trocar a semente do bootstrap.
- **Lição de construção de instrumento**: o gate virava com 2 pregões de
  dado novo (conta em 31/08d). Congelei um limiar sem verificar se o
  instrumento resolvia a diferença que ele decidia.
- **Incidente da CI resolvido** (7 testes vermelhos desde a v1.45):
  `--saida-operacoes` tem default relativo (`data/research/...`, v1.45) e
  os testes de `ea-replay-lote` não o sobrescreviam — escreviam dentro do
  repositório a partir do CWD. Onde o CWD é gravável passa silenciosamente
  (só suja a árvore); na CI, `PermissionError`.
- **Descoberta sobre a verificação de Claude**: o sandbox roda como
  **root**, que ignora permissão de diretório — demonstrado com `chmod
  555` (escrita bem-sucedida). Toda falha desta classe é invisível aqui.
  Guarda de regressão adicionada que falha por PRESENÇA DE ARQUIVO num CWD
  limpo, não por permissão — determinística em qualquer usuário. Verifiquei
  que a guarda falha de fato ao reintroduzir o bug.
- **Pré-registro de conformidade escrito** (31/08d), aguardando
  congelamento: critério determinístico, sem IC, mais os três termos
  aceitos explicitamente (efeito de expectativa de sinal desconhecido, 6
  disparos extras inseparáveis, risco residual de ~4 pts/op).
- 390 testes, coverage 78%, ruff limpo, mypy strict limpo. **Passei a
  rodar `pytest --cov` como a CI faz** — as entregas v1.46 a v1.49 foram
  verificadas sem ele.

## Sessão 2026-09-04 (noite) — scalp de Bollinger 15s: formalização e dump

Hipótese NOVA trazida pelo operador (spec `Scalping com bandas de
Bollinger.md`). Sessão de DESENHO primeiro; código só do que não depende
das dúvidas abertas. Documento vivo: `docs/BOLLINGER_SCALP.md`.

### Desenho
- Spec convertida em pontos (tick = 5): stop 40, alvos 40/65/100,
  trailing 25→10, passo 5. Com custo 11, a perna RP1 sozinha exige ~64%
  de acerto para empatar. MM70 de 6m = 7h de pregão (~"acima de ontem").
- Operador **descartou o 6 minutos** e espelhou os critérios: entrada
  vira **limitada no extremo da barra de correção** (t−2), válida só na
  barra t. Estocástico lento 8/3, linha %K. Execução parcial → pernas na
  ordem RP1→RP2→final.
- Equivalências provadas em dado sintético: Bollinger = limiar de z com a
  barra atual (o `zscore_rolante` NÃO serve: shift(1)/ddof=1), %K =
  100+%R, TR = (H−L)+gap, "MM70 sobe" = C_t > C_{t−70}.
- 16 dúvidas listadas; 10 fechadas; 6 abertas (TR, trailing, horário,
  barra vazia, custo, sinal com posição).

### Código (`entregue-v1.93`)
- `ntsl/bollinger_scalp.ntsl`: dump do 15s com os indicadores do PROFIT
  (não marca sinal — a referência não contém o que está sendo conferido).
  Janela de HORA além da de data: um pregão de 15s (~2.260 barras) não
  cabe no buffer de ~2.000. `CurrentBar` no log porque `Time` em HHMM
  repete 4 vezes.
- `research/bollinger_scalp.py` + comando `bollinger-scalp`: parser,
  todas as variantes que o manual deixa em aberto (ddof 0/1, %K/%D,
  ATR aritmética/Wilder), `equivalencia()` que mede qual bate, regra de
  entrada espelhada com `preco_limite` e tipo de execução
  (abertura/recuo), funil por cláusula (7.4), largura da banda e ATR em
  pontos (7.5).
- Conferido à mão antes dos testes (Bollinger nas duas variantes,
  estocástico, TR com e sem gap, regra em sequência construída). 18
  testes, incluindo o verificador que REPROVA (%K deslocado, H−L sem
  gap). 508 testes, ruff limpo, mypy strict limpo, `--cov` rodado.

**Pendente**: respostas às 6 dúvidas; dump de 15s do operador (duas
metades por pregão); rodar `bollinger-scalp`; ficha de seis linhas.

### Continuação (2026-09-05) — decisões fechadas, perfil de volume por horário

- Operador fechou as dúvidas: **TR fora do v1**; trailing atrás da
  máxima favorável e **RP1 parada** (fica em −40 até +40 ou stop);
  **entradas até 13h** (precisa de volume), zeragem 17:30 como seguro;
  custo 11 por contrato ida e volta; sinal com posição aberta ignorado;
  execução parcial → pernas na ordem RP1→RP2→final.
- Observação do operador sobre tick a tick (1 semana no Profit): a
  estratégia **não se valida dentro do Profit**. Dump do gráfico = TAXA;
  tape do recorder = EFEITO. Registrado em `docs/BOLLINGER_SCALP.md` 6.1.
- `research/perfil_volume_horario.py` + comando `perfil-volume-horario`
  (`entregue-v1.94`): volume de AGRESSÃO por faixa de 30 min, mediana
  entre pregões; `por_barra_15s` (negócios por barra) e
  `pct_da_abertura` (vs. primeira faixa completa) para o operador
  declarar a regra de horário em cima do número — mede, não escolhe.
  Conferido à mão (inclusive abertura parcial). 5 testes. 513 passando,
  ruff e mypy strict limpos.

**Pendente**: dump de 15s (duas metades por pregão) → `bollinger-scalp`;
`perfil-volume-horario` no curated → operador declara regra de horário;
ficha de seis linhas.

## Sessão 2026-09-07 — curadoria DeepScalper fechada, pré-registro da Fase 0

Sessão só de documentação; nenhum código tocado. Tag `entregue-v1.95`
(rebaseada sobre a v1.94 do operador, que chegou no meio).

### Curadoria (`docs/CURADORIA_DEEPSCALPER.md`)
- 15 fontes triadas. Aproveitadas: DeepScalper (paper), DeepLOB, iRDPG,
  EarnHFT. Referência parcial: TradeMaster. Estacionadas: FinPILOT,
  FinRL. Descartadas 8, com motivo, para não reabrir.
- **Achado principal**: o TradeMaster foi clonado e lido. O
  "DeepScalper" dele é DQN simples de 3 ações sobre dado DIÁRIO — sem
  branching, sem book, sem auxiliar de vol, custo fora do reward. Não
  existe implementação pública do paper completo.
- Duas correções de link no caderno (iRDPG apontava para o FinRL;
  EarnHFT/FinPILOT sem link específico).
- Regra de triagem que emergiu: blog de plataforma e site de afiliado
  não renderam em 6 de 6 casos.

### Pré-registro (`docs/RESEARCH_PLANO.md`, caminho G)
- Fases 0–5 com portões. O portão decisivo é a **Fase 2**:
  classificador supervisionado (LightGBM/DeepLOB) sobre features Tier 1
  + book, alvo Triple-Barrier já existente, testado em **forward** com
  ficha de 6 linhas (resultado binário → variância limitada). Critério
  FAVORÁVEL: +15 pts/op líquido no decil de maior confiança, n ≥ 150.
- RL (Fase 3) só se a Fase 2 der FAVORÁVEL e com ≥ 160 pregões de
  tape+book íntegros. Hiperparâmetros congelados (w=0,1, eta=1, h =
  barras que cobrem 120 min medidos), ≥ 10 seeds, sem grade.
- Tradução para o WIN congelada: passo = barra de 120k contratos, ação
  Δpos ∈ {−1,0,+1} com 1 contrato, fill como agressor (pior caso) + 11
  pts/op DENTRO do reward, zeragem no horário do EA.
- Não usa a amostra cega de 2025. Não toca o EA.

**Pendente (Fase 0, custo zero)**: contar pregões com book íntegro,
barras/hora (define `h`), distribuição do spread, barras/pregão (TAXA
da ficha forward).

## Sessão 2026-09-08 — `inventario-deepscalper` (Fase 0) e pasta separada do record

Tag `entregue-v1.96`.

- **Comando novo** `inventario-deepscalper`: as quatro contagens do
  pré-registro (barras/pregão, barras/hora → `h`, spread em ticks via
  `tiny_book`, pregões com book íntegro → faltantes para o portão de 160).
  Categoria `features`, zero trial. Dois cálculos conferidos à mão antes
  dos testes; a conferência do "lado vazio" pegou um defeito de ordem
  (filtro antes do ffill).
- **Operação**: operador separou o `record` numa pasta congelada em tag
  (`profit-tape-record`, venv próprio, `pip install .` sem `-e`), com o
  dev em `profit-tape`. Registrado em `docs/OPERACAO.md` com o ritual de
  promoção. Motivo real: `-e` faz o processo carregar módulo NOVO no
  meio do pregão.
- 522 testes, coverage 76%, ruff limpo, mypy strict limpo.

**Pendente**: rodar `inventario-deepscalper` no dado real e transcrever
o `resumo.json` para o `RESEARCH_PLANO.md`.

## Sessão 2026-09-08 (tarde) — inventário: spread em streaming (v1.97)

- Rodada real da v1.96 no dev: 28 pregões, TAXA = 100 barras/pregão,
  **h = 21 barras** (120 min). Book zerado no local → os streams de book
  estão só no backup (armadilha já registrada em OPERACAO.md).
- Na rodada com `--raw D:\backup_raw\data\raw` o dia 24/08 (623 MB de
  tiny_book) paginou: a v1.96 carregava o dia inteiro em pandas. Erro de
  desenho meu — o projeto já processa por partição justamente por isso.
- v1.97: `SpreadAcumulador` em streaming, memória constante, readahead
  do pyarrow limitado. 1e8 linhas: 12 s, 0,9 GB de pico. Coluna nova
  `spread_desordem`. 3 testes novos (525 total), ruff e mypy limpos.
- Venv do dev tinha um `~rofit-tape` (uninstall abortado pelo record
  segurando arquivo) que sombreava o editável; resolvido recriando o venv.

- A rodada da v1.96 no backup TERMINOU (lenta, não travada): 2 pregões
  com book íntegro, spread mediana 1 tick / p90 1,5 em 4 pregões.
  Transcrito no RESEARCH_PLANO com a leitura: portão da Fase 3 em
  ~abril/2027; custo ida-e-volta do simulador ≈ 16 pts/op (conferir se
  os 11 do EA já embutem spread). Tag `entregue-v1.98` (docs).

**Pendente**: decidir se a Fase 1 (simulador) começa agora; conferir a
composição do `custo_pontos_estimado`.

## Sessão 2026-09-08 (noite) — Fase 1: simulador de replay (v1.99)

- Decisão do operador: **custo 11 já inclui spread** → fill no close,
  sem modelo de book. Fase 1 iniciada.
- `research/simulador.py` + `simulador-conferir`. Reusa `GestorDeRisco`
  e `decidir()` do EA em vez de reescrever risco. Relógio = balde local
  (= `cum_total // volume_barra` do EA); balde pulado conta como barra.
  Colunas futuras (`labels.py`) removidas antes da política.
- Conferência 1 (5 barras à mão) e 2 (verificador de look-ahead) feitas.
  O verificador na primeira versão NÃO pegava o trapaceiro (lia o df
  original por closure); refeito por truncamento de prefixo com fábrica
  de política — agora reprova o caso que deve reprovar.
- Divergência prevista e tratada antes de rodar: z do EA zera a cada dia,
  z do features.parquet é contínuo. `preparar(z_por_dia=...)` iguala.
- 538 testes, ruff e mypy strict limpos.

- Conferência 3 no dado real: primeira rodada NÃO BATE (150 × 99) com o
  padrão "só sim = compras, só EA = vendas" → o replay era do
  `ea_venda_apenas.yaml`. Segunda rodada com esse yaml: **99/99, Δ=0,0,
  +6356 nos dois. BATE.** Fase 1 FECHADA (tag `entregue-v2.00`, docs).

## Sessão 2026-09-08 (noite, 2) — ficha forward da Fase 2 (rascunho v0)

Tag `entregue-v2.01`, só docs. Ficha de 7 linhas escrita no
RESEARCH_PLANO com três campos [MEDIR] (TAXA, nula, p*) que saem de
dado queimado via um `fase2-preparar` ainda não escrito. Decisões já
tomadas: h=3 (horizonte do sinal validado), k por variância no queimado,
HistGradientBoosting sem busca, triagem de redundância antes do treino,
forward = score diário em Python sobre o curated, não no EA, amostra
cega de 2025 intocada. Critério: n=150 eventos binários, +8 pp sobre a
nula E +15 pts/op; teto 60 pregões.

**Pendente**: `fase2-preparar` (mede e congela), depois preencher os
[MEDIR] e ligar.

## Sessão 2026-09-08 (noite, 3) — `fase2-preparar` (v2.02)

- `research/fase2.py` + comando: triagem de redundância, label por dia
  com desempate pelo tape, k por regra fixa, HistGradientBoosting fixo,
  split temporal 80/20, mede p*/nula/TAXA, congela pkl + json com sha256.
- Dependência nova: `scikit-learn>=1.5` no pyproject (só o
  HistGradientBoosting; LightGBM descartado).
- Achado de desenho: o `labels.py` do `features` deixa a barreira
  atravessar o dia — para a Fase 2 o label é recalculado por dia.
- Erro meu pego pelo teste (regra de k na borda), documentado no teste.
- 546 testes, ruff e mypy strict limpos.

**Pendente**: rodar no dado real → preencher os [MEDIR] da ficha →
congelar → `fase2-score` diário.

## Sessão 2026-09-08 (noite, 4) — ficha da Fase 2 congelada; `fase2-score` (v2.04)

- `fase2-preparar` rodou no real: p* 0,633, nula 0,337, TAXA 4,6,
  horizonte 33 pregões, k=1,5 (barreira mediana **274 pts** — um sigma
  de barra é ~180 pts; custo de 11 irrelevante, o problema é direção).
  DEPURAÇÃO n=23: acerto 0,304 < nula — ruído, não decide; adicionado
  acerto in-sample ao preparar como detector de bug.
- Ficha CONGELADA com os números e hashes no RESEARCH_PLANO.
- `fase2-score`: escora com modelo congelado, livro `forward_eventos.csv`
  com carimbo e dedupe, recusa dado queimado, placar fechado até n=50.
- `features --agentes`: lista fixa de agentes (o top-10 muda com o
  histórico e derrubaria coluna do modelo congelado).
- 549 testes, ruff e mypy strict limpos.

**Pendente (operador)**: checklist "um pregão olhado barra a barra"
com `--permitir-queimado` em 27/08; depois ligar o ritual diário.

---

## Sessão 2026-09-08 (noite) — trilha de execução aberta: E0 entregue

Retomada da avaliação honesta de 31/08 ("muita hipótese, nada em
execução"). O operador decidiu seguir a escada E0..E5 em paralelo à
acumulação, com o record ATIVO.

- **Levantamento sobre a v2.04** antes de propor: `ExecutorDeOrdens` nunca
  é construído fora de teste; `check_exports_ea_ordem` existe e ninguém
  chama; as funções de ordem são ligadas atrás de `hasattr` (silêncio se
  ausentes) e o manual as marca obsoletas em favor do `SendOrder` V2.
  **Nunca conferimos qual família a DLL instalada exporta.**
- **Correção do meu desenho de 31/08**: E1 não é "destravar o comando
  `ea`" (processo separado, colide com o record). O EA já roda dentro do
  record via EABridge, mas o record conecta com MarketLogin — rotear
  exige `DLLInitializeLogin`. E1 real = record com login completo. É o
  único degrau com impacto na captura; E0 tem zero.
- **E0 entregue** (`entregue-v2.05`): `doctor` inventaria exports de
  ordem/posição/callbacks por família e diz qual caminho (legado/V2)
  está completo para o E2. Informativo, não altera o veredito do doctor.
  Puro hasattr — roda com o record ligado.
- Manuais no projeto estão truncados (xref quebrado); nomes extraídos via
  `strings` dos dois PDFs.
- Escada registrada no `EA_ARQUITETURA.md` (não estava em doc nenhum).
- 556 testes, coverage 76%, ruff limpo, mypy strict limpo, com `--cov`.

**Pendente**: operador roda `profit-tape doctor` e manda a seção
EXECUCAO (E0). O resultado decide a família de funções do E2.

### Continuação (2026-09-08, noite) — E0 respondido, E1 entregue

- **E0 respondido pelo operador**: 36 de 36 exports presentes, caminhos
  legado e V2 ambos completos. O maior desconhecido do projeto se
  resolveu do melhor jeito. Decisão: E2 no caminho **legado** (é o que
  `execucao.py` já usa e testa; os PDFs truncados impedem ler o struct
  do V2; migração fica como degrau próprio depois do E4).
- Dois alertas da saída do `doctor` tratados pelo operador: `.env`
  desatualizado (não era senha malformada) e disco (raw vai para backup
  após o curate, diariamente).
- Registro: operador roda Python 3.14; a CI testa 3.12/3.13.
- **E1 entregue** (`entregue-v2.06`): `login_completo` no `ProfitClient`,
  `runtime.login_completo` no yaml (default False), `record
  --login-completo`. Três callbacks de roteamento que só contam;
  `contas_vistas` no heartbeat como prova de sessão. Fake ganhou
  `DLLInitializeLogin` com anúncio de contas e simulação de export
  ausente. Teste amarra cada callback ao slot certo (a armadilha
  history-de-negócios × history-de-ordens).
- Protocolo dos testes A (fora do pregão, impacto zero) e B (produção
  com a flag, perda recuperável por backfill) no `EA_ARQUITETURA.md`.
- 562 testes, coverage 76%, ruff limpo, mypy strict limpo, com `--cov`.

**Pendente (operador)**: teste A hoje após 18:30 com o record parado;
mandar as 4 linhas do log. Teste B só depois do A passar.

### Continuação (2026-09-08, 18:46) — teste A rodou; duas correções (v2.07)

- **Teste A provou o essencial**: login completo conecta (0), corretora
  chega em BROKER_CONNECTED(5), market data em 4, 9 tickers aceitos, 27
  eventos com 0 descartes. `NL_INTERNAL_ERROR` de 26/08 não voltou.
- **Erro de protocolo meu**: o teste durou 4 s — `encerrar_em: 18:30` do
  yaml de produção, teste às 18:46. Corrigido com `--sem-encerramento`.
- **Erro de código meu**: `contas=0`. Nunca chamava `GetAccount()`, e
  `roteamento_conectado` era LOGIN=0 — o mesmo bug que o `contas.py`
  corrigiu em 26/08, repetido por mim. O fake escondia (anunciava contas
  no login). Corrigido: `corretora_pronta` (ROTEAMENTO=5) separado do
  login; `GetAccount()` uma vez após a corretora, da thread principal,
  com espera limitada que nunca prende a captura; fake fiel à sequência
  real do log.
- 566 testes, coverage 76%, ruff/mypy limpos.

**Pendente (operador)**: repetir o teste A com `--sem-encerramento`, 2
minutos; o que falta provar é `contas>=1` no heartbeat.

### Continuação (2026-09-08, 20:14) — teste A PASSOU; contas=14 a explicar (v2.08)

- **Teste A repetido com `--sem-encerramento`: passou.** 2,1 min estável,
  `corretora_pronta=True`, `GetAccount()` retorno 0, zero descartes. E1
  provado fora do pregão.
- **`contas=14`** para um login com duas contas, com 8 eventos
  ROTEAMENTO=5 no log. Duplicata (re-anúncio por notificação) ou entrada
  real — o log não distinguia. v2.08: pares deduplicados + contador bruto
  + `profitdll.contas` com os pares `corretora:conta` uma vez. O teste B
  responde.
- Registro para o E2: ROTEAMENTO oscila 5→2→5; conferir `corretora_pronta`
  no momento do envio.
- 567 testes, coverage 76%, ruff/mypy limpos.

**Pendente (operador)**: teste B amanhã — `runtime.login_completo: true`
no yaml de produção antes do agendador subir; olhar 10 min de heartbeat;
mandar o `profitdll.contas`.
### Continuação (2026-09-08, sessão do scalp) — perfil de volume e primeiro dump de 15s (v2.09)

- `perfil-volume-horario` em 28 pregões: três regimes — manhã (pico
  10:00–10:30 a 134–151% da abertura, caindo até 47% às 12:30), platô
  da tarde 13:00–16:30 (36–41%), fechamento. O 13h é o joelho; regra
  por percentual cairia em cima do platô. Proposto 09–13h fixo.
- Dump de 15s (01/09 completo; 01–04/09 09–14h): equivalência FECHADA
  com dif_max 0,0 nos cinco campos — Bollinger populacional, %K lento,
  ATR = SMA21(TR). Profit desenha toda barra de 15s.
- **Achado 7.6**: a cláusula do estocástico (<20 / >80) dispara 0,75 e
  0 vezes por pregão; estrutural (mediana de Est(t−1) nos candidatos =
  72 na compra). Sem ela: ~60 / ~51 por pregão. Decisão do operador.
- **Achado em pontos**: TR mediano da barra de 15s = 49–64 pts > stop
  de 40. 65% das barras cabem o stop; 23% cabem stop e RP1. Reabre
  "stop fixo em ticks vs. fração do ATR".
- `entregue-v2.09`: verificador de TR corrigido (primeira barra do
  bloco = NaN, era o único "NAO BATE"); `diagnostico_clausulas` no
  comando (quantis do estocástico nos candidatos, % barras com TR ≥
  stop). 514 testes, ruff e mypy limpos.

### Continuacao (2026-09-09) — cobertura por pregao no funil (v2.10)

- O dump de 4 dias saiu com 03 e 04/09 pela metade (parametro igual
  nos 4 dias; o console nao guardou tudo). O "por pregao" dividia por
  4. Agora `cobertura_por_pregao` marca pregao inteiro (>= 80% do mais
  cheio) e o funil so' conta esses. Refeito: 86 / 58 candidatos por
  pregao em 09-13h; com estocastico extremo, 1,5 / 0.
- Regra pratica: um pregao por dump (09-13h = 960 linhas).
- Abertura: 09:00-09:02 e' leilao; barra nasce no primeiro negocio.
  Proposta: indicadores reiniciam por pregao + 21 barras de aquecimento.
- INCREMENTO_vX.md das entregas passa a sair em ASCII puro (o de v2.09
  saiu com acentos UTF-8 e ficou ilegivel no Windows).
- `tests/test_alertas_vigia.py::test_vigia_detecta_travado` falhou uma
  vez na suite completa e passou 5x isolado e na repeticao: depende de
  `time.sleep(0.05)` sob carga. Nao e' desta entrega; fica anotado.
- 569 testes, ruff e mypy strict limpos.

### Continuacao (2026-09-09, tarde) — v1 congelada e ficha escrita (v2.11)

- Operador decidiu: janela 09-13h com 21 barras de aquecimento;
  estocastico FORA do v1 (fica como variante "acelerador": com extremo,
  entrada a mercado na abertura de t); stop = fracao do ATR21 com
  k = 0,7 (a manha tem varias volatilidades: ATR21 mediano 81 / 119 /
  90 / 58 pts as 09 / 10 / 11 / 12h). Geometria da spec preservada
  como fracao do stop (alvos 1 / 1,625 / 2,5; trailing 0,625 / 0,25 /
  0,125) -- um numero novo so'.
- Funil v1 (2 pregoes inteiros, 09:08-13:00): 82 / 56 sinais por
  pregao; limitada tocada em 83% / 91%, 77% na abertura de t; sinais a
  cada 4 barras -> operacoes por pregao dependem da duracao, a medir no
  replay pelo tape.
- Ficha de seis linhas escrita (docs/BOLLINGER_SCALP.md §0): efeito
  binario na perna 1 (nula de lucro p1 = 0,59 apos custo), n = 370.
- Codigo: `marcar_sinais` com `usar_estocastico=False` por default,
  janela (aquecimento + 13h), `stop_pts` e geometria; conferencia a mao
  pegou o `round()` par do Python (162,5 -> 160): meio-tick agora vai
  para cima. 571 testes, ruff e mypy limpos.

**Proximo**: barras de 15s montadas do tape (com a equivalencia ja'
provada contra o grafico) e replay das tres pernas pelo tape -> TAXA de
operacoes e p1 de depuracao -> HORIZONTE final -> ligar.

### Continuação (2026-09-08, 22:29) — contas=14 explicado; E1 fechado fora do pregão (v2.09, só docs)

- `profitdll.contas unicas=2 callbacks=14`: duas contas (32006 simulador,
  1003 real), re-anunciadas pela DLL a cada notificação de corretora,
  inclusive durante a sessão. O E2 usa a lista deduplicada.
- Descoberta operacional: `profit-tape-record` usa `pip install .` sem
  `-e` (correto para produção), e o backfill de hoje rodou sobre código
  pré-v2.06 porque o install não foi refeito após o merge. A versão fixa
  `0.1.0` esconde isso. Proposta: `setuptools-scm` antes do E2.
- O backfill nunca lê `login_completo` (sempre MarketLogin, por desenho).

**Pendente (operador)**: (1) `git log --oneline entregue-v2.08..HEAD` no
`profit-tape-record` — 3 commits desconhecidos; (2) teste B amanhã com
`login_completo: true` no yaml de `profit-tape-record`.
### Continuacao (2026-09-09, noite) — cinco dumps inteiros e o replay pelo tape (v2.13)

- Cinco dumps de um pregao cada: equivalencia bate em todos; funil v1
  = 69 / 63 sinais por pregao, 117 tocados; espelho visivel no 03/09.
- `research/bollinger_replay.py` + comando `bollinger-replay`: barras
  de 15s do tape, comparacao tape x grafico (`--dumps`), replay das
  tres pernas negocio a negocio com a contabilidade completa dos sinais
  (posicao_aberta / circuit_breaker / nao_atravessou / operacao).
- Conferido a mao: recuo com trailing puxando a 1045 (+60/+45/+45,
  liquido 117), abertura a favor com stop cheio (-213), toque sem
  atravessar. 10 testes (espelho da venda, posicao aberta, circuit
  breaker, zeragem 17:30, barras do tape com RLP fora, comparacao,
  resumo). 581 testes, ruff e mypy limpos.
- Smoke end-to-end em curated sintetico + dump real: roda.

**Pendente (Diego)**: `profit-tape bollinger-replay WINFUT --dumps <pasta
dos dump*.txt>` no curated. A saida preenche OPERACOES por pregao e o
p1 de depuracao da ficha; a comparacao tape x grafico valida as barras.

### Continuação (2026-09-09, 15:25) — reconexão real durante o teste B: E1 fechado com evidência de produção

- Internet caiu duas vezes durante o pregão com `login_completo: true`
  em produção. A primeira, registrada em detalhe: ~83 s
  (15:23:42–15:25:05), roteamento e mercado fora do ar juntos, heartbeat
  com `linhas` congelada, `sem_evento_ha_s` até 79,3.
- Recuperação idêntica à sequência do teste A: tudo gerenciado pela DLL
  sozinha (`DLLInitializeLogin` nunca rechamado). `contas_callbacks`
  saltou +6 no restabelecimento — confirma de vez que a DLL re-anuncia
  contas a cada reconexão, não só no login inicial.
- **Validação ao vivo, não mais teórica**: `corretora_pronta` seguiu o
  estado real durante toda a queda — caiu e voltou sozinho. Confirma a
  necessidade de o E2 checar `corretora_pronta` no instante do envio.
- Lacuna real de dado nos ~83 s, registrada em `INTEGRIDADE_DOS_DADOS.md`
  — não é bug, `descartados=0` mede só fila cheia, não conexão caída.
- **E1 fechado.** Próximo passo: E2.

### Continuação (2026-09-10) — `compact`: reescrita do raw fragmentado (v2.23)

- Complemento do 72734a7 (causa raiz dos row groups de 15 linhas): o
  writer parou de gerar, mas os arquivos ja' no disco continuavam com
  34 mil row groups por arquivo. Novo comando `compact` e modulo
  `tools/compact.py` reescrevem particoes FECHADAS com `write_table`
  de tabela inteira, `row_group_size=1 Mi` explicito, zstd +
  estatisticas, `max_rows_per_file=5 M` como o sink.
- Conferencia empirica antes de codificar: `write_table` com
  `row_group_size` consolida 2.000 chunks de 15 linhas em 1 row group
  (e da' exatamente `ceil(linhas/rg)` -- virou o criterio da
  verificacao pos-escrita, que faz o comando FALHAR se o novo arquivo
  nao for melhor que o velho).
- Atomicidade em duas fases com manifesto por particao (`.compacting`
  invisivel aos leitores -> verificacao -> `_compact.manifest.json` ->
  remove originais -> promove -> remove manifesto). Retomada automatica
  na rodada seguinte. Detalhe em OPERACAO.md.
- Dia corrente e particao com `.inprogress` pulados por particao (nao
  aborta o comando, ao contrario do curate -- senao seria inutil em
  dia de pregao). Arquivo ilegivel fica no disco; os sadios ao lado
  sao compactados.
- Um bug pego pelo teste de atomicidade: temporario so' entrava na
  lista de limpeza DEPOIS da verificacao, entao falha entre gravar e
  verificar deixava `.compacting` orfao. Registrar antes de gravar.
- 16 testes novos (`tests/test_compact.py`): reducao de row groups com
  conteudo byte-igual, `.inprogress`, dia corrente, ZSTD podre, sem
  footer, falha antes do commit, verificacao rejeitando micro-lotes,
  crash no meio do commit + retomada, orfao, idempotencia, todos os
  streams, filtros, manifesto, CLI. 623 testes, ruff e mypy limpos.

**Pendente (Diego)**: `profit-tape compact --raw data\raw --log-file
logs\compact.jsonl` fora do horario de captura (ou durante -- o dia
corrente e' pulado). Depois, `curate` no dia 08/09 para medir o ganho
real de leitura.

### Continuacao (2026-09-10) — primeiro replay: tape x grafico nao bateu (v2.24)

- Replay em 30 pregoes: 398 operacoes (13,3/pregao), p1 = 0,49 (IC
  0,44-0,54) contra nula 0,59; pernas 2 e 3 quase nunca chegam ao alvo
  (8/390 e 0/398): o trailing a 0,25 stop atras da maxima esta' dentro
  do ruido da barra de 15s. PRELIMINAR e nao ajustado.
- Tape x grafico: open/close divergem em ~30% das barras, high/low em
  ~4% -> padrao de RLP. `bollinger-replay --dumps` agora compara tres
  conjuntos de negocios (agressao; +RLP; +RLP+leilao), ordena por
  (ts_ns, trade_id), e reporta a faixa horaria das barras que so' o
  grafico tem (buracos do tape: 94 em 04/09, 53 em 08/09).
- Resumo com os cortes PRE-DECLARADOS (abertura x recuo; compra x
  venda) e resultado por perna. 3 testes novos. 626 testes, ruff e
  mypy limpos.
- Perguntas ao operador: 02 e 03/09 nao estao no curated? Recorder
  teve buraco em 04 e 08/09?

### Continuacao (2026-09-10, tarde) — RLP no OHLC do grafico; defeito de processo na v2.13 (v2.25)

- Tape x grafico com tres candidatos: o grafico usa AGRESSAO + RLP
  (1-2 barras divergentes/dia; sinais 85/85, 67/67 em 01/09). Barras
  do replay passam a agressao + RLP; execucao continua contra agressao.
- DEFEITO DE PROCESSO: na v2.13 uma substituicao de texto nao casou
  (ruff format reformatou antes) e foi em silencio -- no codigo E nos
  testes. O replay tinha `break` no circuit breaker e `continue` mudo
  na posicao aberta; ~90% dos sinais sumiam. Reproduzido com as barras
  reais de 01/09: 152 sinais -> 5 operacoes com CB, 118 sem.
  Corrigido com edicao verificada (assert count == 1). REGRA NOVA:
  toda substituicao de texto por script confere que casou exatamente
  uma vez; str_replace com old_str e' o padrao.
- `--ignorar-circuit-breaker` no bollinger-replay (mesmo padrao do
  ea-replay-lote). 626 testes, ruff e mypy limpos.
- 02 e 03/09 nao estao no curated (licenca do backfill; fora de escopo).

### Continuacao (2026-09-10, noite) — veredito da depuracao: v1 CONTRA (v2.27, docs)

- `--ignorar-circuit-breaker` de fato no binario (v2.26, com teste de
  CLI). Replay da regra inteira: 2.916 operacoes em 30 pregoes, p1 =
  0,486 (IC 0,467-0,504) contra nula 0,61; pernas 2/3 com 47 e 2 alvos
  em ~2.900; -39 pts/operacao; R$ 640/dia so' de custo em 3 contratos.
- Veredito pela ficha: CONTRA. Forward NAO ligado. Nada ajustado.
- Proposto (5.6): medir conteudo direcional do sinal (retorno assinado
  e MFE/MAE em 1/4/16 barras vs. sem sinal) antes de qualquer variante.
  Variante de rompimento registrada como hipotese distinta.

### Continuacao (2026-09-11) — custo nao e' criterio; ficha corrigida (v2.28)

- Operador: a trava do forward pelo custo esta' errada -- custo e'
  condicao comercial (corretora, negociacao); o que deve existir e' um
  alerta de custo maximo. Correto. Ficha corrigida: nula a custo zero
  (p1 = 0,50), criterio em termos brutos, linha CUSTO MAXIMO = borda
  bruta por contrato, que vira alerta no EA contra custo_pontos_estimado.
- `bollinger-replay` imprime BORDA BRUTA (IC95) e CUSTO MAXIMO
  SUPORTADO por contrato. Teste novo. 628 testes, ruff e mypy limpos.
- No caso da v1 o veredito nao muda: p1 = 0,486 (IC ate' 0,504) nao
  supera 0,50; bruto = -6 pts/operacao; custo maximo suportado e'
  NEGATIVO. Nao e' a corretora que trava.
- Regra de edicao (assert count == 1) pegou um replace que nao casou
  nos testes; corrigido por linha, conferido antes de rodar.

### Continuacao (2026-09-11, tarde) — validacao por ordem real em demo; E2 dentro do record (v2.29)

- Operador: a validacao visual passa a ser por ORDEM REAL na conta de
  simulacao (ve ao vivo no grafico, audita pelo registro de ordens do
  Profit), com trava no codigo. Confirmado o desenho: trava em duas
  camadas conferidas contra o que a DLL anunciou (conta em
  contas_vistas + nome da corretora contem "simul"); demo mede
  mecanica e latencia, nao borda (simulador preenche no toque);
  pregoes de demo vao a PERIODOS_DECLARADOS como validacao_execucao.
- E2 ja' existia standalone (v2.22, nunca rodou na DLL real) mas so'
  contava o callback e nao tinha a trava pela DLL. Entregue o E2 DENTRO
  do record: `record --ordem-teste-em HH:MM`, `ea/ordem_teste.py`
  (maquina de estados na thread principal), `exigir_simulador`,
  client com nomes_corretoras e ordens_eventos, fake emitindo
  Accepted -> Filled. 10 testes, incluindo os que REPROVAM (XP como
  demo, conta nao anunciada, corretora nao pronta: zero Send*) e o
  ponta a ponta no RecorderService. 638 testes, ruff e mypy limpos.

**Pendente (Diego)**: rodar no pregao, `--ordem-teste-em` num horario
liquido (ex. 10:30), mandar o log de `ea.ordem_teste.*` e o registro
de ordens do Profit.

### Continuacao (2026-09-11, noite) — versao da DLL no doctor e no log (v2.30)

- Nelogica liberou a DLL 4.0.0.42 (callbacks de ordem sem atraso,
  SubscribeOfferBook, PID) e 4.0.0.41 (watchdog TSystemHealthState).
  Decisao: atualizar ANTES do E2, fora do pregao, pelo protocolo novo
  em OPERACAO.md (backup com versao no nome, doctor, teste A, teste B).
- `profitdll/versao.py`: versao do arquivo via VERSIONINFO (ctypes
  puro); `doctor` mostra `dll_versao`; `profitdll.inicializado` loga.
  640 testes, ruff e mypy limpos.

### Continuacao (2026-09-10, 22h) — backfill: a causa era o formato da data (v2.31)

- Script autocontido `diagnostico_historico.py` (fora do repo, para a
  Nelogica) provou na DLL 4.0.0.41: so' data = janela vazia (retorno 0,
  progresso 0 -> 100 em 15 ms, zero negocios); data com hora entrega
  (~17 milhoes de negocios recebidos na rodada). Artigo da Nelogica
  confirma formato estrito, 10 dias por chamada, progresso 100 = fim.
- Corrigido: `request_history` com hora; `_aguardar_entrega` espera
  progresso 100 e so' depois o quiesce; Ctrl+C remove a particao do dia
  interrompido; fake reproduz "so' data = vazio". 3 testes novos, 643
  passando, ruff e mypy limpos.
- Backfill de 02 e 03/09 pode ser refeito (dentro dos 30 dias).

### Continuacao (2026-09-10, 23h) — segunda camada: SubscribeTicker antes do historico (v2.32)

- Com a data com hora (v2.31) o backfill AINDA veio vazio: progresso 100
  em ~5 s, zero negocios. O diagnostico serializado, no mesmo dia e
  formato, entregou 6.148.231 negocios de 02/09 (09:03 a 18:31) -- a
  unica diferenca era o SubscribeTicker antes do pedido. Mecanica
  medida: ~50 s em 99 % (download) + ~60 s de rajada ate' o 100.
- Backfill assina cada ticker antes de pedir (nos dois caminhos);
  client ganha `ignorar_tempo_real` (backfill nao grava tempo real de
  hoje); `backfill.progresso_100_imediato` no log quando o 100 vem em
  < 1 s. 2 testes novos (ordem sub -> hist; sem particao de hoje).
  645 testes, ruff e mypy limpos.
- DLL em producao agora 4.0.0.42 (operador atualizou).

### Continuacao (2026-09-11, madrugada) — a causa real: 1a chamada de historico vem truncada (v2.33)

- Mesmo com data+hora e SubscribeTicker (v2.31/v2.32), o backfill ainda
  vinha vazio em 0,1s. Experimento decisivo: duas chamadas IDENTICAS
  seguidas para 02/09. A 1a devolveu 102.400 negocios, so' de 17:29 a
  18:31 (a cauda do dia). A 2a, identica, devolveu 6.148.231, o dia
  inteiro (09:03-18:31). Nao e' cache -- e' a 1a chamada de historico
  de um ticker NA SESSAO vindo truncada, ponto.
- `client.primar_historico`: uma chamada de priming, descartada (nunca
  chega no bus), uma vez por ticker por sessao, ANTES do laco real do
  backfill (nos dois caminhos, por-dia e por-periodo). Retry proprio se
  a recusa transitoria acontecer durante o priming.
- Fake atualizada para reproduzir a assimetria exata (1a chamada de um
  ticker trunca para a cauda; da 2a em diante, inteira) -- sem isso o
  teste do priming nao provaria nada.
- 3 testes ajustados (contagem de chamadas mudou com o priming
  entrando no meio) + 3 novos (formato+truncagem, priming resolve,
  ponta a ponta pelo executar_por_dia). 647 testes, ruff e mypy limpos.
- **Nao verificado**: se a truncagem e' por ticker (uma vez basta) ou
  por dia (cada dia precisaria de priming). O backfill de 02-03/09 e'
  o teste: se 03/09 vier inteiro sem re-primar, a hipotese se confirma.

### Continuacao (2026-09-11) — fechando a v1: direcao do sinal + rompimento (v2.35)

- Operador fechou a v1 (CONTRA, 5.5) e pediu as duas medicoes que
  ficaram em aberto: conteudo direcional (5.6) e a variante de
  rompimento (fiel a' spec original, espelhada para a compra).
- `research/direcao_sinal.py` + comando `bollinger-direcao`: retorno
  assinado e MFE/MAE em 1/4/16 barras a partir do fechamento de t-1,
  sinal x controle pareado por faixa de 30 min (sem reusar a propria
  barra de sinal como controle). Conferido a mao (retorno, mfe, mae
  nos dois lados) antes dos testes. 7 testes.
- `marcar_sinais(..., variante_entrada=)`: "retorno" (v1, extremo de
  t-2) ou "rompimento" (extremo de t-1, fiel a spec original). So' a
  referencia de entrada muda; resto identico. `bollinger-replay
  --variante retorno|rompimento|ambas` (ambas roda as duas e imprime
  comparacao lado a lado). 3 testes novos.
- Smoke de ponta a ponta dos dois comandos em curated sintetico. 656
  testes, ruff e mypy limpos.

**Pendente**: rodar `bollinger-direcao` e `bollinger-replay --variante
ambas` nos pregoes reais.
