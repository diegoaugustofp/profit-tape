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

### Continuacao (2026-09-11, noite) — FECHAMENTO: as duas variantes sao CONTRA

- 32 pregoes (02-03/09 recuperados pelo priming). Retorno (v1): p1=0,480
  IC(0,432-0,528), bruto -4,7 IC(-21,6 a 12,2) -- null, consistente com
  a medicao anterior. Rompimento: p1=0,415 IC(0,360-0,473), bruto -22,0
  IC(-43,0 a -0,9) -- NEGATIVO, os dois intervalos fora do neutro.
- Veredito: FECHADO. As duas variantes sao CONTRA pelo criterio bruto.
  Nenhum EA de scalp de Bollinger vai a producao com este desenho.
  A medicao de direcao pura (5.6) nao foi necessaria -- ja havia duas
  tentativas concretas reprovadas.
- Nenhum codigo mudou nesta entrada; so' documentacao (5.8).
## Sessão 2026-09-11 — forward da Fase 2 LIGADO; score deixa de mostrar desfecho (v2.37)

- Checklist fechado em 08/09: `--permitir-queimado` em 27/08 mostrou 7
  eventos com horas, barreiras (249–344 pts) e lados coerentes. 7/7 ali
  é o modelo retreinado recitando um dia que viu — tubulação, não
  evidência.
- Primeiro `score` forward: `--desde 2026-08-28`, 23 eventos gravados
  em `forward_eventos.csv` (28/08, 31/08, 01/09, 04/09, 09/09, 10/09).
  02/09, 03/09 e 08/09 sem linha — a v2.04 não distinguia "sem evento"
  de "sem dia"; a v2.05 lista os dias escorados sem evento.
- **Defeito de disciplina corrigido**: a v2.04 imprimia label/acerto/pnl
  por evento no modo forward, tornando o "placar fechado até n=50"
  decorativo. v2.05: forward mostra só dia/hora/lado/conf/barreira; os
  desfechos ficam no CSV e aparecem nos checkpoints. `--permitir-queimado`
  continua mostrando tudo (é para inspecionar).
- Observação estrutural registrada sem ação: 15/23 eventos são venda; o
  modelo treinou com −1 dominante e o forward começou numa alta
  (178k→190k). A PARADA da ficha não autoriza reagir a isso.
- Esta entrega foi originalmente carimbada v2.05 numa sessão paralela à
  do `doctor` (que ficou com a tag v2.05 real) e NUNCA foi aplicada; o
  `fase2-score` da v2.36 ainda imprimia o desfecho. Reaplicada sobre a
  v2.36 como v2.37 (2026-09-11).
- A partir daqui: ritual diário `curate` → `features --agentes` →
  `fase2-score --dia`. Checkpoint de sanidade em n=50 (~6 pregões a
  partir de agora), veredito em n=150.

### Continuação (2026-09-11) — livro do forward duplicava ao inserir dias (v2.38)

- Operador recuperou 02 e 03/09 e re-escorou `--desde 2026-08-28`: o
  `bar_id` contínuo de todos os dias seguintes deslocou +243 e o livro,
  chaveado por (dia, bar_id), gravou **11 duplicatas** (43 em vez de
  32). O checkpoint de n=50 teria aberto cedo.
- v2.38: chave do livro = (dia, ts_open); livro antigo sem ts_open é
  recusado com instrução; `--reconstruir-livro` (com `--desde`) guarda
  o antigo como `forward_eventos.antes_<ts>.csv` e regrava do zero — o
  score é determinístico, então os 32 voltam iguais.
- Estado do forward após reconstrução: **32 eventos em 8 pregões com
  evento** (28/08–10/09; 08/09 sem evento). 3,56 eventos/pregão contra
  4,6 da ficha — com isso n=150 chega em ~42 pregões, ainda dentro do
  teto de 60.
- Lição de processo: chave de livro forward nunca pode depender de
  índice acumulado; só de (dia, timestamp).

### Continuacao (2026-09-11, pregao) — E2 rodou: 'Ordem invalida' com ticker WINFUT (v2.39)

- E2 rodou pela 1a vez na DLL real, 10:30, conta 1000357256/Simulador
  (32006) -- a TRAVA funcionou (contas_vistas mostrou XP 1003 tambem
  presente e nao foi usada). Compra aceita pela DLL (ordem_id real),
  callback devolveu `OrderNotCreated / "Ordem invalida."` em 671 ms.
  Zeragem recusada em seguida (nao havia posicao para zerar -- esperado,
  ja' que a compra nunca abriu). Nenhuma ordem apareceu no Profit,
  coerente com "nunca existiu na bolsa".
- Causa provavel: `OrdemDeTeste` usava ticker="WINFUT" (o alias do
  Profit/Nelogica que resolve para o contrato vigente em DADO --
  subscribe, GetHistoryTrades -- mas nao e' instrumento negociavel na
  B3; a bolsa tem WINV26, WINZ26 etc., nao "WINFUT"). Operador levantou
  hipotese alternativa ("cross order" desativado no Profit); busca nao
  confirmou esse termo especifico -- fica registrada como hipotese nao
  descartada, mas o log ja' explica a rejeicao sem precisar dela.
- `--ordem-teste-ticker` no `record` (default ainda "WINFUT", com AVISO
  explicito `recorder.ordem_teste_ticker_generico` quando usado assim).
  `OrdemDeTeste` aceita ticker. 2 testes novos. 660 testes, ruff e mypy
  limpos.

**Pendente (Diego)**: rodar de novo com `--ordem-teste-ticker WINV26`
(confirmar que ainda e' o contrato vigente) num horario liquido. Se
ainda vier "Ordem invalida", a hipotese do "cross order" ganha forca e
vale checar essa configuracao no Profit antes de mais uma rodada.

### Continuacao (2026-09-11) — confirmado: ticker agregador nunca funciona no envio (v2.40)

- Operador trouxe a fonte primaria: manual da Nelogica, "Como rotear
  ordens com a ProfitDLL" (ajuda.nelogica.com.br/hc/pt-br/articles/
  13312468554651). Citacao literal: "A ProfitDLL nao faz substituicao
  automatica (cross-order) para o contrato corrente, entao tickers
  agregadores nao sao aceitos no envio de ordens." O "cross order" que
  o operador via no Profit e' real -- so' funciona DENTRO do grafico,
  nunca na API. Minha hipotese de v2.39 (ticker generico e' a causa)
  fica confirmada pela fonte, nao so' por inferencia do log.
- v2.39 tinha isso como AVISO (`--ordem-teste-ticker`, default WINFUT
  com warning). Promovido para BLOQUEIO: `exigir_ticker_especifico` em
  `ea/ordem_teste.py` levanta `TickerAgregadorInvalido` na construcao
  de `OrdemDeTeste` para WINFUT/WDOFUT/INDFUT/DOLFUT/BGIFUT (lista de
  agregadores conhecidos, prefixo). `ticker` deixou de ter default
  inseguro -- agora e' obrigatorio. O record converte a excecao em
  SystemExit no STARTUP, antes de qualquer conexao -- nao 10 minutos
  depois, no pregao, com "Ordem invalida" vindo da B3 (foi exatamente
  isso que aconteceu as 10:30 de hoje).
- 2 testes reescritos (o antigo testava so' o aviso; agora testa o
  SystemExit) + todos os que criavam OrdemDeTeste passaram a usar
  WINV26 explicito. 661 testes, ruff e mypy limpos.

**Pendente (Diego)**: rodar o E2 de novo com
`--ordem-teste-ticker WINV26` (ou o contrato vigente na data) num
horario liquido.

### Continuacao (2026-09-11) — E2 FECHADO: resultado=ok na DLL real (v2.41)

- Rodou com `--ordem-teste-ticker WINV26`, 12:30. `resultado=ok`.
  Esteira real: compra `ClientCreated` (x2, "Enviando ordem ao
  HadesProxy" / "Enviado ao servidor de ordens.") -> `HadesCreated`
  ("Criação") -> `Filled` a 189370,0. Latencia: 19,6 ms ate' o 1o
  callback, 72,6 ms ate' o fill. Zeragem: mesma esteira, fill a
  189365,0 em 62,5 ms. Zero contratos em aberto no fim. Operacao
  visivel no grafico do Profit -- os dois canais (log e Profit)
  concordam.
- A logica de `OrdemDeTeste` ja' era robusta a esteira (confere
  `executada >= qtd`, nao faz match de string) -- nao precisou
  mudar. A FAKE estava desatualizada (simulava so' Accepted ->
  Filled); atualizada para a esteira real, para os testes continuarem
  representativos. 661 testes, ruff e mypy limpos.
- **E2 fechado.** Latencia do simulador (fila vazia) e' otimista, nao
  e' a borda real de mercado -- isso continua para o E3/forward.

### Continuacao (2026-09-11) — E3 entregue: reconciliacao de posicao (v2.42)

- Operador pediu para fechar o E3 sem demora. Implementado:
  `profitdll/types.py` (structs V2: TConnectorAccountIdentifier,
  TConnectorAssetIdentifier, TConnectorTradingAccountPosition, a
  partir do manual, extraido em sessao anterior); `bindings.py`
  (GetPositionV2 vinculado); `client.py` (`consultar_posicao` +
  `PosicaoConsultada`, com teste de plausibilidade); `ea/reconciliacao.py`
  (`ReconciliadorPosicao`, maquina de estados no padrao do E2, reusa
  `exigir_simulador`); gancho no record (`--reconciliar-em
  --reconciliar-ticker --reconciliar-esperado`).
- Decisao invertida frente ao E2: GetPositionV2 (struct fixa) em vez da
  GetPosition legada (ponteiro variavel com strings embutidas, mais
  fragil) -- o manual marca a legada como obsoleta a favor da V2.
- NAO VERIFICADO contra a DLL real (sandbox Linux, sem DLL). Offsets
  calculados pelo ctypes internamente consistentes (alinhamento natural
  de 8 bytes) mas isso so' confirma coerencia, nao correspondencia.
  `consultar_posicao` bloqueia acao sobre resultado implausivel (lado
  fora de 0/1/2, quantidade absurda).
- Conferido a mao com uma DLL minima manuscrita (vendida/comprada/
  zerada/implausivel) antes dos testes formais. 11 testes novos, com
  fake `GetPositionV2` (preenche a struct via ponteiro). 672 testes,
  ruff e mypy limpos.

**Pendente (Diego)**: primeira consulta REAL deve ser so' leitura
(esperado = posicao conferida manualmente no Profit ANTES), nao um
horario onde zeragem automatica poderia disparar. Se bater, a struct
esta' certa e da' para confiar na zeragem automatica dali em diante.

### Continuacao (2026-09-11, noite) — 1a consulta real: layout errado, safety net funcionou (v2.43)

- Primeira consulta real do E3 (19:45): `lado_bruto=-56` (impossivel --
  so' existe 0/1/2). `plausivel=False` -> NAO zerou, so' alarmou. O
  teste de plausibilidade fez exatamente o que devia: nenhum dano.
- Investigado: o manual usa `packed record` explicitamente em OUTRAS
  structs (TAssetIDRec, TAccountRec) -- a extracao do PDF preserva a
  palavra quando presente. TConnectorTradingAccountPosition genuinamente
  NAO e' marcada `packed` no texto. Ou seja, o alinhamento natural
  (minha suposicao original) tem base textual -- e mesmo assim o valor
  veio errado. Adivinhar de novo (tentar `_pack_=1` as cegas) seria o
  mesmo erro ao contrario, sem medir nada.
- Adicionado dump bruto: `PosicaoConsultada.bruto_hex` (so' quando
  implausivel) + log `ea.reconciliacao.dump_bruto_para_depuracao`.
  Tecnica: comparar os bytes de campos de ENTRADA que NOS escrevemos
  (corretora=32006 -> bytes `06 7d 00 00` em little-endian) contra o
  dump, para achar o offset REAL empiricamente em vez de supor. Testado
  numa fake propria antes (auto-consistente, nao prova nada sobre a DLL
  real, mas confirma que a tecnica de busca funciona). 672 testes, ruff
  e mypy limpos.

**Pendente (Diego)**: rodar `--reconciliar-em` de novo (mesmo comando).
Vai vir `implausivel` de novo (esperado -- ainda nao corrigi o layout).
Me manda o log `ea.reconciliacao.dump_bruto_para_depuracao` inteiro
(bruto_hex). A partir dele eu reconstruo o offset real dos campos e
corrijo a struct definitivamente -- sem mais um segundo palpite.

### Continuacao (2026-09-11, noite) — layout confirmado: era a plausibilidade, nao a struct (v2.44)

- Decodificado o dump bruto da consulta das 20:00, byte a byte (blocos
  de 8, como int64/double). Achado decisivo: offsets 96/104/112/120
  reproduziram EXATOS os precos e quantidades do E2 de hoje (189365.0/1,
  189370.0/1) -- e offset 200 ecoou position_type=2, que EU tinha
  escrito. Toda a struct (entrada e saida) estava correta desde o
  inicio; so' `open_side` (offset 88) veio 0xc8=200, fora de {0,1,2},
  e so' porque a posicao estava ZERADA -- lado nao tem sentido para
  quantidade zero, e a DLL nao escreve nada limpo ali nesse caso.
- Corrigido: `open_side` so' e' validado quando `open_quantity != 0`.
  Docstring de `consultar_posicao` atualizada para refletir o que esta'
  confirmado (posicao zerada) e o que ainda nao (posicao aberta).
- 2 testes novos (zerado com lado sujo = plausivel; quantidade != 0 com
  lado invalido = continua implausivel). 674 testes, ruff e mypy
  limpos.

**Pendente (Diego)**: rodar `--reconciliar-em` de novo. Deve vir
`resultado=bate` desta vez (posicao zerada, layout confirmado). O teste
com posicao ABERTA (comprar e reconciliar sem zerar antes) ainda fica
para uma proxima rodada, quando fizer sentido.

### Continuacao (2026-09-11, noite) — structs confirmadas contra o exemplo oficial da Nelogica (v2.45)

- Operador trouxe `profitTypes.py` e `profit_dll.py`, exemplos oficiais
  da Nelogica com uso real de GetPositionV2 (`printPosition()`).
  Comparacao campo a campo: as tres structs V2 que eu tinha reconstruido
  do manual em PDF sao IDENTICAS a`s oficiais -- confirma que a
  reconstrucao anterior (e a decodificacao do dump de ontem) estava
  certa em tudo, EXCETO um detalhe: os campos `Byte` (Version, OpenSide,
  FeedType, PositionType) sao SEM SINAL (`c_ubyte`), eu tinha usado
  `c_byte`. O byte 0xc8 da consulta das 20:00 e' 200 sem sinal, nao -56
  -- nao mudou a conclusao de ontem (200 tambem invalido), mas corrige
  um bug real que importaria para uma posicao aberta de verdade.
- Corrigido em `types.py`. Offsets nao mudam (Byte tem 1 byte com ou
  sem sinal); so' a INTERPRETACAO do valor muda para valores > 127.
- Achados de bonus, registrados sem implementar agora:
  `TConnectorZeroPosition` (zeragem V2 struct-based) e
  `TSystemHealthState` (watchdog da DLL, `Responsive`/`Frozen`).
- 674 testes (nenhum quebrou -- a mudanca so' afeta valores > 127, que
  nenhum teste usava), ruff e mypy limpos.

**As structs V2 agora tem duas fontes independentes de confirmacao**:
o dump real decodificado byte a byte (ontem) e o exemplo oficial da
Nelogica (hoje). Confianca alta para posicao zerada; posicao aberta
ainda sem teste real.

### Continuacao (2026-09-11, noite) — confirmacao cruzada: TradeType bate com o oficial (v2.46)

- Operador completou o conjunto de 3 exemplos oficiais da Nelogica
  (main.py, profit_dll.py, profitTypes.py -- o ultimo ja' estava no
  project knowledge, idem ao enviado). Aproveitado para conferir
  `domain/enums.py:TradeType` (usado em TODO o projeto -- backfill,
  curate, replay do scalp, perfil de volume) contra `TTradeType` do
  arquivo oficial: os 22 codigos batem 1:1, nomes e valores, inclusive
  RLP=13 -- que a sessao de 21/08 tinha corrigido por MEDICAO empirica
  (25% de um pregao de WIN no codigo 13), nao por manual. Duas fontes
  independentes convergindo no mesmo numero. So' comentario adicionado;
  nenhum valor mudou. 674 testes, ruff e mypy limpos.

### Continuacao (2026-09-11, noite) — E4 entregue: forward em demo com ordens reais (v2.47)

- Operador confirmou: E4 e' para `z_agf_3` (venda + Rota B,
  `ea_venda_rota_b.yaml`), a estrategia que ja' roda em dry_run hoje --
  e o pre-requisito 5 da escada (comparar decisoes logadas em dry_run
  contra o que o research previa) considerado satisfeito.
- Achado: trabalho de E4 tinha comecado em sessao anterior
  (`execucao.py` ja' tinha confirmacao de fill/slippage/latencia e
  `exigir_conta_anunciada`) mas ficou sem commitar -- sobrevivia como
  modificacao local nao commitada, carregada silenciosamente entre
  `git checkout -b` desta sessao. Revisado, testado, e completado.
- Dois bugs REAIS de producao, ambos pre-existentes, nenhum novo:
  `EAService` nunca passava `preco_referencia` para `executar()`
  (slippage nunca seria calculado de verdade); o comando standalone
  `ea-ordem-teste` construia `ExecutorDeOrdens(client._dll, ...)` em
  vez de `ExecutorDeOrdens(client, ...)` -- bug latente desde o
  refactor que deu ao executor acesso a `contas_vistas`, nunca pego
  porque nenhum teste tinha chegado tao longe.
- Lacuna de seguranca fechada: `ExecutorDeOrdens` nao tinha
  `exigir_ticker_especifico` -- o `symbol` da EAConfig e' "WINFUT", o
  agregador. Sem a trava, E4 cairia no MESMO defeito do E2 de ontem.
  Novo parametro `apenas_simulador` (usa `exigir_simulador`, a
  checagem forte, em vez da universal).
- `recorder/service.py`: `dry_run=False` deixa de ser bloqueado, mas
  SO' em demo -- `usar_conta_real=False` e `apenas_simulador=True`
  HARDCODED, nao configuraveis. Dependencia circular (bridge antes do
  client; executor real depois do client) resolvida em duas fases,
  religando `client._on_trade_extra` apos a montagem (seguro: `connect()`
  le o atributo de novo a cada chamada, nao captura no `__init__`).
- Bug sutil do mypy no caminho: reuso de nome de variavel entre dois
  blocos independentes mascarava um buraco de tipo real
  (`object.tamanho_posicao` nao acusava erro) -- corrigido tipando o
  atributo via `TYPE_CHECKING` e renomeando a variavel local.
- `--ea-ticker-ordem` na CLI, obrigatorio quando o ea_config tem
  `dry_run: false`. 690 testes (16 novos/ajustados so' nesta rodada:
  6 no gancho do record, 3 na trava de ticker/apenas_simulador do
  executor, os demais ajustes de fixture), ruff e mypy strict limpos.

**NAO VERIFICADO CONTRA A DLL REAL** -- toda a cadeia do E4 (fill,
slippage, latencia, as duas fases de montagem) so' foi testada contra
a fake. Pendente (Diego): primeira rodada real num horario controlado,
olhando o primeiro sinal disparar de verdade e conferindo no Profit
antes de deixar rodar o pregao inteiro sem supervisao -- mesmo espirito
do protocolo que o E3 usou.

### Continuacao (2026-09-11, 21h) — E3 confirmado com posicao ABERTA real (v2.48)

- Operador abriu 1 WINV26 comprada manualmente pelo grafico do Profit,
  deixou aberta. `--reconciliar-esperado 0` leu lado_bruto=1,
  encontrado=1, preco_medio=188820.0 -- `open_side=1` dentro do
  intervalo valido, nao mais so' o caso degenerado de quantidade zero
  (v2.44). Detectou a divergencia, zerou a mercado, confirmou pela
  mesma esteira do E2 (ClientCreated x2 -> HadesCreated -> Filled),
  resultado=divergiu_zerado. Fecha a ultima lacuna documentada do E3.
- Regra operacional descoberta: com o record em login completo E a
  reconciliacao ativa, operacao manual pelo Profit e' derrubada na
  proxima consulta -- desenho funcionando como esperado (qualquer
  posicao que o EA nao reconhece como sua vira divergencia), nao
  defeito. Documentado como incompatibilidade estrutural: nao operar
  manualmente enquanto --reconciliar-em/E4 estiver ativo na sessao.
- 1 teste novo espelhando o evento real (compra com divergencia e
  zeragem -- a combinacao que faltava; venda-com-divergencia e
  compra-sem-divergencia ja' existiam separados). 691 testes, ruff e
  mypy limpos.

### Continuacao (2026-09-11, fim de semana) — revisao do EA_ARQUITETURA + plano do E5 (v2.49)

- `EA_ARQUITETURA.md` reestruturado: o topo agora tem ESTADO ATUAL
  (secoes 0-4), o resto continua sendo historico cronologico. Regra
  declarada no cabecalho: quando topo e historico divergirem, o topo
  vence.
- **Pipeline de desenvolvimento de EA (F0-F6)** definido e cada EA
  enquadrado: z_agf_3 em F5 (forward demo montado, sem sinal real
  ainda), DeepScalper Fase 2 em F3/F4 (forward ligado 09/09, placar
  fechado ate' n=50), scalp de Bollinger nas duas variantes em F4
  REPROVADO. Regra F4->F5 registrada: depuracao mede BORDA, forward
  demo mede EXECUCAO -- estrategia sem borda nunca deve chegar em F5.
- **Revisao das pendencias historicas**: TODAS as 5 pendencias
  declaradas no corpo antigo ja' estavam resolvidas e o texto nunca
  tinha sido atualizado (teste de concorrencia, NotImplementedError,
  EABridge+--ea-config, dry_run=False recusado, arquitetura de longo
  prazo). Marcadas como resolvidas com ponteiro para onde/quando.
  Titulos historicos desatualizados corrigidos com marca [historico].
- **CORRECAO IMPORTANTE**: eu tinha escrito no resumo da sessao anterior
  que E5 = "producao/conta real". Errado -- a escada original
  (2026-09-08) define **E5 = multi-EA**. Producao e' a fase F6 do
  pipeline, decisao separada. Corrigido no documento.
- **Plano do E5 escrito como PROPOSTA** (secao 4), aguardando validacao:
  4 acoplamentos que exigem refatoracao (o perigoso e' capital global --
  hoje cada EAService acha que tem os R$5.000 inteiros), desenho com
  `SupervisorDeRisco` + `LivroDePosicoes` + fan-out, e 6 passos
  entregaveis (E5.0-E5.5). Pergunta aberta que muda o tamanho do
  trabalho: os EAs vao operar o MESMO ticker simultaneamente?
- E5.0 e E5.1 sao codigo puro -- podem ser feitos sem pregao.

### Continuacao (2026-09-11) — E5 redesenhado com SUBCONTAS; E5.0 e E5.1 entregues (v2.50)

Decisoes do operador que mudaram o desenho do E5:
- **Subcontas separam a execucao**: cada EA na sua. Resolve o netting
  (na mesma conta, compra de um EA anula venda do outro e ninguem sabe
  de quem e' o que). Com subconta, `SendZeroPosition` volta a funcionar
  direto e a reconciliacao desagrega naturalmente.
- **Consequencia obrigatoria**: a familia LEGADA (SendMarketBuyOrder,
  SendZeroPositionAtMarket) nao tem parametro de subconta. So' a V2
  struct-based tem (`SubAccountID` dentro de TConnectorAccountIdentifier)
  -- confirmado no main.py oficial. Operador decidiu MIGRAR TUDO para
  V2. Isso exige revalidar E2/E3/E4 ao vivo, porque a legada e' a unica
  familia que foi validada de verdade.
- **Risco e' INFORMATIVO, nunca limitante**: o sistema calcula e
  apresenta (capital recomendado, exposicao somada, cobertura) e AVISA
  -- nunca impede. Se o operador opera com R$2.000 onde o recomendado
  e' R$5.000, executa mesmo assim; o risco, inclusive de zeragem por
  falta de margem, e' dele. A conta precisa suportar os N EAs -- dito
  explicitamente. Zeragem em cascata fica FORA do escopo.
- Nota preservada no desenho: o circuit breaker de perdas consecutivas
  continua trava DE VERDADE -- protege contra DEFEITO de estrategia,
  nao contra escolha de capital. Sao coisas diferentes.

Entregue:
- `ea/supervisor.py` (E5.0): `SupervisorDeRisco` informativo.
  `capital_recomendado_para()` e' a inversa da formula do
  `GestorDeRisco` -- confere com o default historico (stop 500 pts,
  1 WIN, risco 2% -> R$5.000). Alerta em 3 niveis, detecta subconta
  compartilhada e EA sem subconta em multi-EA. NAO tem `pode_abrir`
  nem `bloqueado` -- e um teste garante que nao volte a ter.
- `ea/livro.py` (E5.1): `LivroDePosicoes`, posicao por (EA, subconta,
  ticker), preco medio ponderado, virada de lado, reconciliacao que
  ATRIBUI dono a divergencia (possivel so' por causa da subconta) e
  marca posicao orfa como "(ninguem)" -- o caso da operacao manual que
  o E3 encontrou ao vivo.
- Conferido a mao antes dos testes formais nos dois modulos. 23 testes
  novos, 714 no total, ruff e mypy limpos.

**Pendente**: E5.2 (migrar execucao para V2 com SubAccountID) em
diante. E5.3, E5.5 e E5.6 exigem pregao.

### Continuacao (2026-09-11) — E5 redesenhado: record NUNCA para (v2.51)

Operador levantou dois problemas no plano v1 do E5, os dois corretos:

1. **"Se o record iniciou uma estrategia eu nao inicio uma nova sem
   reiniciar o record. Isso gera perda de dados."** Certo: hoje
   `--ea-config` e' lido UMA vez, na construcao do RecorderService.
   Captura perdida e' o unico ativo do projeto que nao da' para refazer.
   Novo principio: o record e' servico de captura que roda o pregao
   inteiro; EAs entram e saem DELE em tempo de execucao.
2. **"Um yaml pra cada corre o risco de 2 EA diferentes erroneamente
   configurarem a sub conta igual."** Certo: volta o netting
   silenciosamente. Resolvido mantendo 1 arquivo por EA (identidade num
   lugar so'; um mestre criaria duas fontes de verdade) mas com colisao
   virando RECUSA de inclusao, nao so' alerta.

OBSTACULO TECNICO descoberto ao redesenhar: `connect()` captura
`on_trade_extra` numa VARIAVEL LOCAL antes de registrar o callback --
trocar `client._on_trade_extra` depois de conectado NAO tem efeito. Por
isso o fan-out precisa ser um DESPACHANTE estavel (registrado 1x,
consultando lista mutavel sob lock curto), nao troca de atributo.

Desenho novo (secao 4 reescrita):
- `DespachanteDeEAs`: registrado 1x como on_trade_extra, lista de
  bridges mutavel sob lock curto. EA com bug nao derruba os outros nem
  a captura (regra herdada do on_trade_extra atual).
- `RegistroDeEAs`: recusa inclusao se (subconta, ticker) ja' ocupado,
  se o nome repetir, ou se a subconta nao existir de fato na corretora
  (`GetSubAccounts`).
- `--ea-dir`: pasta varrida pelo laco de monitoramento (que ja' roda a
  cada 0,5 s). YAML novo -> inclui; removido -> retira. Auditavel por
  git, sem porta de rede nem daemon novo.
- Retirada SEMPRE graciosa: EA com posicao aberta entra em modo "so'
  fecha" e so' sai depois de zerar -- sumir com posicao aberta criaria
  a posicao orfa que o LivroDePosicoes marca como "(ninguem)".

Tambem verificado no manual (respondendo pergunta do operador): **a DLL
NAO cria subconta** -- so' funcoes de leitura (GetAccount*,
GetSubAccount*). Criar e' pela XP/Nelogica. O codigo valida a
existencia e recusa subir EA com subconta inexistente, listando as
disponiveis. Simulador suporta subcontas (confirmado pelo operador).

So' documentacao nesta entrega. 714 testes, ruff e mypy limpos.

### Continuacao (2026-09-11) — ea-contas lista subcontas (v2.52, parte do E5.2)

- `GetSubAccountCount` e `GetSubAccounts` vinculados (assinaturas
  conferidas contra `profit_dll.py` oficial); `TConnectorAccountIdentifierOut`
  adicionada (campos de texto sao BUFFER FIXO `c_wchar * 100`, nao
  ponteiro -- a DLL preenche, nos alocamos).
- `ea/contas.py`: `listar_subcontas()` + campo `subcontas` em
  `ContaEncontrada`. Uma consulta por conta UNICA (depois do dedup, se
  fosse antes rodaria 2x a toa) e ANTES do DLLFinalize. Falha na
  enumeracao NAO derruba a listagem de contas -- a conta ja' foi
  descoberta, subconta e' informacao adicional.
- `profit-tape ea-contas` mostra as subcontas de cada conta e, quando
  nao ha' nenhuma, explica que a DLL NAO cria (criacao e' pela
  XP/Nelogica) e que o E5 precisa de uma por EA.
- Fake (ambas: a do projeto e a local de test_ea_contas) ganhou
  subcontas configuraveis. 5 testes novos, incluindo DLL sem suporte e
  erro NL na contagem. 719 testes, ruff e mypy limpos.

**Pendente**: o resto do E5.2 (migrar ENVIO de ordem para a familia V2
com SubAccountID) e o E5.4 (despachante dinamico).

### Continuacao (2026-09-11) — subcontas BLOQUEADAS pela licenca (v2.53)

- `ea-contas` rodou na DLL real: 2 contas, ZERO subcontas -- mas o
  operador TEM subcontas criadas (2 no Simulador, 1 na XP, visiveis no
  Profit Chart). O app de teste oficial da Nelogica devolve
  `GetSubAccounts: NL_LICENSE_NOT_ALLOWED` -- confirma que nao e' erro
  nosso: a chave de ativacao nao tem o recurso liberado.
- DEFEITO NOSSO que o teste expos: `listar_subcontas` tratava qualquer
  retorno negativo como aviso silencioso e devolvia lista vazia. O
  operador leu "subcontas: nenhuma" (que sugere "e' so' criar") quando
  a verdade era "a licenca nem deixa perguntar" -- mandou procurar
  problema no lugar errado. Corrigido: `SubcontasIndisponiveis`
  (excecao propria, com `por_licenca`), campo
  `subcontas_indisponiveis` na conta, e a CLI passa a dizer
  explicitamente NAO FOI POSSIVEL CONSULTAR + o que fazer.
- `-2147483630` adicionado a tabela de erros NL.
- **Impacto no E5**: o desenho de subcontas separadas fica BLOQUEADO
  ate' a Nelogica liberar. Alternativa registrada: multi-EA em tickers
  DIFERENTES (WIN e WDO) dispensa subconta, porque nao ha' netting
  entre ativos distintos.
- 3 testes novos (licenca negada nao vira "sem subconta"; conta sai
  marcada; outro erro NL nao e' confundido com licenca). 721 testes.

### Continuacao (2026-09-11) — caminho B: 1 EA por TICKER, subcontas descartadas (v2.54)

- Operador leu a documentacao da Nelogica ("Modulo de Subcontas") e viu
  que estavamos usando o conceito errado: subconta e' infraestrutura de
  MESA PROPRIETARIA (conta Master administrando operadores, perfis de
  risco, corretagem por operador), nao mecanismo para separar
  estrategias do mesmo operador. O NL_LICENSE_NOT_ALLOWED nao era
  recurso a ativar -- e' produto de outro publico.
- Operador tambem identificou a confusao que causou a volta: o que ele
  cria no Profit e' CARTEIRA, que e' agrupamento de visualizacao DENTRO
  da mesma conta de roteamento -- a ordem vai para a mesma conta na B3,
  entao carteira NAO separa posicao e o netting continuaria. Nao
  resolveria nem se a DLL a expusesse.
- **Decisao: caminho B.** Cada EA opera um TICKER diferente (WIN e WDO).
  Entre ativos distintos nao ha' netting por definicao. Isso dispensa
  subconta, mantem SendZeroPositionAtMarket funcionando (zera por ativo
  = por EA), deixa o E3 desagregado de graca, e **cancela o E5.2** -- a
  familia LEGADA (ja' validada no E2/E3/E4) continua servindo, nao ha'
  necessidade de migrar para V2.
- Restricao declarada: dois EAs NAO podem operar o mesmo ticker. O
  `RegistroDeEAs` (E5.4) recusa -- e' a trava que substitui a subconta.
- `ea-contas` passa a explicar o que subconta realmente e', para nao
  induzir a pedir liberacao de algo que nao resolveria nosso problema.
- Secao 4 reescrita (4.2, diagrama 4.4, trava do 4.5, tabela 4.7).
  721 testes, ruff e mypy limpos.

**Proximo**: E5.4 (DespachanteDeEAs + RegistroDeEAs + --ea-dir), codigo
puro, sem pregao.

### Continuacao (2026-09-13) — E5.4a: despachante e registro (v2.55)

- `ea/despachante.py`: `DespachanteDeEAs`, o alvo FIXO de
  `on_trade_extra`. Resolve o obstaculo tecnico identificado no
  redesenho: `connect()` captura o hook numa variavel local, entao
  trocar `client._on_trade_extra` depois de conectado nao tem efeito --
  o fan-out tem que ser um alvo estavel com lista mutavel por dentro.
  Lista e' TUPLA imutavel trocada inteira (copy-on-write): `publicar`
  le sem lock nenhum no hot path. Excecao de um EA nao impede os
  outros nem propaga para o callback da DLL.
- `ea/registro.py`: `RegistroDeEAs`, dono das regras de entrada. A
  trava central do caminho B: **1 EA por ticker** -- dois EAs no mesmo
  ativo voltariam a netar e a reconciliacao nao saberia de quem e' a
  divergencia. Recusa tambem nome duplicado. Remocao e' graciosa
  (`bridge.parar()` chama `encerrar_dia()`, que zera posicao) e libera
  o ticker.
- `EAConfig.nome` (opcional): identidade estavel do EA. Sem ele, o nome
  do arquivo serve -- mas declarar e' melhor, porque renomear o arquivo
  deixa de trocar a identidade.
- **Dois defeitos pegos na conferencia a mao**, invisiveis na leitura do
  codigo: (1) `remover` nao tirava o EA do supervisor -- apos remover 1
  de 2 EAs, o resumo mostrava 3 EAs e pedia R$15.000; (2) o alerta
  `ea_sem_subconta` disparava sempre no caminho B, onde ninguem tem
  subconta por desenho -- ruido constante ensina a ignorar alerta.
  Corrigidos, com teste para cada um.
- 19 testes novos (8 despachante incl. concorrencia, 11 registro).
  740 no total, ruff e mypy limpos.

**Pendente**: E5.4b -- `--ea-dir` e a integracao no `RecorderService`.

### Continuacao (2026-09-13) — E5.4b: EAs entram e saem com o record rodando (v2.56)

- `--ea-dir <pasta>`: yaml novo INCLUI um EA a quente; yaml removido
  RETIRA (graciosamente -- zera posicao antes de sair). Varredura a cada
  5 s pela thread principal (o laco ja' roda a 0,5 s; varrer disco nessa
  frequencia seria desperdicio e incluir EA nao e' urgencia).
- `--capital-em-conta`: alimenta o SupervisorDeRisco. Puramente
  informativo, como decidido -- calcula e avisa, nunca impede.
- O despachante virou o `on_trade_extra` SEMPRE, registrado uma vez.
  Isso **eliminou a logica de duas fases do E4** (que trocava
  `client._on_trade_extra` depois de construir o client): um caminho a
  menos, e o mais fragil deles.
- O EA inicial (`--ea-config`) passou a entrar pelo MESMO caminho de um
  EA a quente (`_incluir_ea`), com as mesmas travas. Antes eram dois
  caminhos; agora o que vale no pregao vale no startup.
- Tratamento de erro assimetrico, de proposito: NA CONSTRUCAO um EA mal
  configurado mata o processo (nao ha' captura a perder, e subir um
  record que o operador acha que vai operar -- mas nao vai -- e' pior
  que nao subir). EM EXECUCAO nada derruba: yaml torto, ticker
  repetido, pasta ilegivel, pre-requisito faltando -- tudo logado, EA
  nao entra, captura segue. Flag `_em_execucao` distingue.
- Defeito pego rodando: `_em_execucao` estava definido DEPOIS do bloco
  que inclui o EA inicial -- AttributeError na construcao. Ordem
  corrigida.
- 9 testes novos, incluindo o central (incluir EA com o record ja'
  capturando, confirmando que ele recebe trades e que a captura nao
  sofre descarte). 749 testes, ruff e mypy limpos.

**Pendente**: E5.5 e E5.6, que exigem pregao.

### Continuacao (2026-09-13) — E5.4c: modo exclusivo, 2 EAs no mesmo ticker (v2.57)

- Operador propos: em vez de proibir 2 EAs no mesmo ticker, deixar os
  dois rodando e impedir que o segundo ENTRE enquanto o primeiro estiver
  posicionado. Resolve o netting pela raiz -- ele so' existe se houver
  duas posicoes simultaneas.
- Regras escolhidas: quem sinaliza PRIMEIRO fica com a vaga; quem perde
  DESCARTA o sinal (nao fica em espera -- ao abrir a vaga o sinal ja'
  estaria velho); vaga liberada quando o dono zera.
- `ea/vagas.py` (`VagasPorTicker`): lock de verdade, nao tupla imutavel
  como o despachante -- aqui a operacao e' leitura-e-escrita atomica
  ("pega se estiver livre"), que snapshot sem lock nao resolve. Cada
  bridge roda na sua thread, entao a disputa e' real (teste com 20
  threads simultaneas confirma que so' um ganha). Um EA NAO consegue
  liberar a vaga de outro.
- `--ea-modo-ticker unico|exclusivo`. O default (`unico`) mantem o
  comportamento anterior identico.
- Vaga liberada tambem no `encerrar_dia`, nos DOIS caminhos (com e sem
  posicao aberta) -- senao um EA removido a quente logo apos zerar
  travaria o ticker para sempre.
- `sinais_sem_vaga` no heartbeat: o custo estatistico do modo exclusivo
  (a medicao de cada EA fica condicionada ao que o outro fazia) esta'
  documentado em 4.4b e visivel no log, nao escondido.
- 12 testes novos. 761 no total, ruff e mypy limpos.

### Continuacao (2026-09-13) — revisao do plano: o que fechou, o que falta (v2.58)

- Secoes de estado do EA_ARQUITETURA revisadas contra o codigo real:
  - **Secao 1** (EAs): nada mudou desde 11/09 -- explicitado que o
    trabalho recente foi TODO em infraestrutura, que e' ortogonal a`s
    estrategias. Os dois EAs vivos seguem parados esperando pregao.
  - **Secao 2** (escada): E5 detalhado em sub-passos (E5.0 a E5.6) com
    o estado de cada um. E5.2 e E5.3 marcados CANCELADOS (subconta e'
    produto de mesa proprietaria). Duas licoes novas: `on_trade_extra`
    capturado em variavel local no `connect()`, e a assimetria do
    tratamento de erro de EA (construcao mata, execucao nunca).
  - **Secao 3** (pendencias): reorganizada por VIABILIDADE -- o que
    esta' bloqueado por pregao, o que da' para fazer sem, e divida
    tecnica sem urgencia.
  - **Secao 3b (nova)**: entregue x APLICADO. O remoto estava em v2.55
    com v2.56/v2.57 entregues mas nao aplicadas -- distincao que uma
    sessao futura precisa ver para nao construir sobre `origin/main`
    desatualizado.
  - **Secao 4**: titulo e status corrigidos (dizia "com SUBCONTAS",
    conceito ja' descartado; e "E5.0/E5.1 implementados, resto
    pendente", quando todo o codigo ja' esta' pronto).

So' documentacao. 761 testes, ruff e mypy limpos.

### Continuacao (2026-09-13, noite) — EAs de PRECO: tres fichas e o inicio do IFR2 (v2.59)

Decisao do operador: o custo de P&D esta' assumido por 6 meses (prazo
minimo para o tape acumular), mas o primeiro EA em execucao nao espera
esses 6 meses. Nasce a linha de **EAs de PRECO** — validaveis HOJE
porque candle de WIN tem anos de historico — desenhados com a PORTA DE
VOLUME na interface desde o dia 1, e com a regra de que toda variavel
nova passa pela disciplina inteira.

- `docs/EAS_DE_PRECO.md` (novo): por que a linha existe; o que muda no
  pipeline F0-F6 para EA de preco (fonte = candle, estimador binario
  com barreiras simetricas, barra ambigua excluida, DEPURACAO x TESTE);
  tres fichas em RASCUNHO — **IFR2** (RSI2 extremo a favor da MME80, D
  = 1 x ATR14), **ORB** (rompimento do range 09:00-09:30, D =
  amplitude), **123** (fundo de 3 barras, stop de compra acima da 3a,
  stop na minima da 2a, alvo simetrico); custo maximo em pontos (D >
  92 pts a p1 = 0,56 para pagar 11); a porta de volume como GATE
  (`filtro_fluxo: null`, `extra="forbid"`); o que o documento NAO
  autoriza. ORB tem risco de HORIZONTE declarado (<= 1 op/pregao).
- `docs/EA_ARQUITETURA.md`: os tres na tabela da secao 1 com fase (IFR2
  F1, ORB F0, 123 F0); pendencias 8 e 9 (dump M15 + `eas-preco`;
  `RequestSerieHistory` de barras ganha dono); secao 5 nova resumindo a
  linha e as regras.
- `ntsl/preco_m15.ntsl` (novo): dump M15 com OHLC, RSI2, MME8, MME80,
  ATR14, TR calculados pelo Profit. Um dump serve as tres fichas (~54
  pregoes por dump de console). Segue as convencoes do
  `bollinger_scalp.ntsl`. A assinatura `RSI(periodo, tipo)` e' a
  suposicao a confirmar ao compilar (fallback `RSI(2)` no cabecalho).
- `research/eas_preco.py` + `profit-tape eas-preco` (novos): parser
  (CAMPOS congelados, espelho do .ntsl), variantes em aberto (RSI
  Wilder com semente SMA / exponencial / simples; MME semeada no close
  ou na SMA; ATR aritmetica / Wilder), equivalencia Python x Profit,
  funil por clausula do IFR2 (extremo -> excursao -> regime -> janela
  -> t+1), ATR14 e D em pontos com o p1 que empata o custo, fracao de
  barras ambiguas e duracao ate' resolver. **Nao calcula qual barreira
  bateu** — categoria `features`, zero trial.
- RSI de Wilder conferido A MAO antes dos testes (regra 4); o exemplo
  esta' no docstring e fixado no teste. 16 testes novos. 777 no total,
  ruff e mypy limpos.

Proximo passo (operador): aplicar o `preco_m15.ntsl` no grafico M15 do
WINFUT, tirar quantos dumps o historico permitir (janelas de data sem
sobreposicao), rodar `profit-tape eas-preco <dump>` e trazer o funil, os
pontos e a fracao ambigua para preencher a ficha IFR2 e congelar.

### Continuacao (2026-09-13, noite) — primeiro dump M15, ficha IFR2 v1, bug do verificador (v2.60)

O operador rodou o `eas-preco` no primeiro dump (174 pregoes de 2026).
Tres coisas sairam dele:

1. **Bug do verificador (7.3)**: `startswith("mme8")` casava com `mme80`
   — MME80 comparada da barra 24 em vez da 240, RSI sem aquecimento. O
   "NAO BATE" com mediana 0,0 era o proprio sintoma. Corrigido: chave
   exata, aquecimento 5 x periodo (a conta da semente residual esta' no
   codigo), `dif_max_em` imprime onde esta' a maior diferenca. Teste de
   regressao com semente 2.000 pts fora, mesma formula, exige BATE.
2. **K = 1 colidia com o risco.py**: D mediano 510 pts, p90 806, contra
   o stop catastrofico de 500. Decidido K = 0,5 (D ~255, o stop
   mediano da Rota B). Mecanismo, nao calibracao.
3. **Regime MME80 cortava 70% dos sinais** (1,09/pregao -> 980 pregoes
   para n). Decisao (B) do operador: regime sai da clausula, vira
   estrato reportado. Eden morto (0 sinais).

Ficha IFR2 v1 escrita em `docs/EAS_DE_PRECO.md` 3 com os numeros
medidos e o que ainda falta para congelar (rodada com a v2.60; 2025 se
o grafico carregar). IFR2 na tabela: F2->F3. 778 testes, ruff e mypy
limpos.

### Continuacao (2026-09-13, madrugada) — IFR2 CONGELADA e `eas-preco-teste` (v2.61)

Segundo dump (2023-2025, 749 pregoes) + primeiro dump com a v2.60: todas
as equivalencias BATEM; taxa 3,5 sinais/pregao e estratos 31/69
identicos nos dois periodos (ATR mediano 40% diferente); 7,4% ambiguo,
duracao mediana 1 barra. Mecanismo redito em voz alta: "exaustao
imediata -- a primeira excursao de 0,5 x ATR14 da barra seguinte".

- `docs/EAS_DE_PRECO.md` 3.0c (tabela dos dois dumps) e **3.2 FICHA
  CONGELADA**: amostras por DATA (TESTE 2023-25 primario, uma rodada;
  REPLICACAO 2026 ate' 13/08, reportada sem veto; DEPURACAO 14/08 em
  diante, nao interpretavel), ordem obrigatoria depuracao -> teste ->
  replicacao, carimbo de versao (tag + hash da ficha).
- `research/eas_preco_teste.py` + `profit-tape eas-preco-teste` (novos):
  resultado binario por sinal, p1 com IC de Wilson (conferido a mao
  7/10 -> 0,397-0,892), veredito pelo criterio da ficha, estratos SO'
  reportados (sem veredito proprio), portao de amostra por data (recusa
  dia fora), lock de UMA rodada no `teste` (`--forcar` exige motivo,
  gravado), carimbo `git describe` + sha256 dos parametros. Lista as
  ambiguas para conferir no tape; NAO as resolve (pendencia: ordem
  intrabarra pelo tape na depuracao).
- EA_ARQUITETURA: IFR2 em **F3 — CONGELADA**, proximo passo = F4 na
  ordem da ficha. 11 testes novos; 789 no total, ruff e mypy limpos.

### Continuacao (2026-09-14) — IFR2 REPROVADO; ORB entra em F1 (v2.62)

- IFR2 rodado na ordem da ficha. TESTE (2023-25, n=2.452): p1 = 0,492
  IC95 [0,472; 0,512] -> CONTRA; replicacao 2026: 0,482. Nenhum estrato
  com IC fora de 0,50. Nulo a custo zero. Fechamento em
  `EAS_DE_PRECO.md` 3.3, com o que NAO se faz (variantes sobre amostra
  ja' queimada). Tabela: F4 -- REPROVADO.
- ORB: `eas-preco --ficha orb` -- funil por PREGAO, custo do regime
  medido ("outro lado rompeu antes"), A/D em pontos, hora do gatilho,
  classes. Decisao de estimador antes de medir: stop tocado na barra do
  gatilho e' AMBIGUA sempre (o OHLC nao ordena contra o rompimento). O
  teste do cenario pegou essa lacuna na primeira versao do codigo.
- 6 testes novos; 795 no total, ruff e mypy limpos.

### Continuacao (2026-09-14) — correcao contra 4.9; IFR2 trial 2 (K=1); ORB v1 (v2.63)

- **Erro meu, duas vezes:** encolhi D pelo stop catastrofico (K = 0,5 no
  IFR2; proposta de 0,25 x A no ORB). Contraria a decisao 4.9 (risco e'
  informativo, nunca limita). Corrigido: capital RECOMENDADO por
  contrato passa a ser calculado e reportado nos dois funis (D x R$0,20
  / 2%); regra 5 da secao 5 do EA_ARQUITETURA registra o incidente.
- **IFR2 trial 2, K = 1**, declarado ANTES de rodar (`EAS_DE_PRECO.md`
  3.4): unica mudanca e' K; IC de 97,5% (Bonferroni por 2 trials) e
  FAVORAVEL exige IC acima de 0,50. Ultimo trial da familia neste
  historico. `eas_preco_teste.TRIAL = 2`.
- **ORB v1** (4.1): regime vira estrato (decisao do operador), os dois
  lados armados OCO, gatilho dos dois lados na mesma barra = fora,
  D = A. Funil v0 medido em 923 pregoes registrado em 4.0 (98% rompem,
  gatilho mediano na primeira barra, A dobrou em 2026, ambiguidade
  6,8% / 2,4%). Congela depois de remedir com o regime como estrato.
- 797 testes, ruff e mypy limpos.

### Continuacao (2026-09-14, manha) — IFR2 familia fechada; ORB CONGELADA; teste por ficha (v2.64)

- IFR2 trial 2 (K = 1): teste 0,486 IC97,5% [0,464; 0,509] -> CONTRA;
  replicacao 0,479. Familia fechada sobre este historico
  (`EAS_DE_PRECO.md` 3.5). Sem trial 3.
- ORB funil v1 remedido: 0,96-0,98 sinais/pregao, gatilho ambiguo 2%/0,
  ambigua 0,3%/0, por tempo 11,6%/23,5%. Ficha CONGELADA (4.2), trial 1.
- `eas_preco_teste`: parametros, TRIAL e hash POR FICHA (`FICHAS`);
  `z_ic(trial)` por Bonferroni; `resolver_orb` (resultado fora do funil,
  como no IFR2) reporta o P&L na zeragem 17:30 das operacoes por tempo;
  arquivos `resultado_<ficha>_<amostra>.json`; `--ficha orb` na CLI;
  placar tolera zero sinais. 799 testes, ruff e mypy limpos.

### Continuacao (2026-09-14, tarde) — ORB inconclusivo; replicacao 2 declarada (v2.65)

- ORB teste 2023-25: p1 = 0,524 IC95 [0,485; 0,562] n=636 -> INCONCLUSIVO;
  replicacao 2026 0,496 [0,406; 0,586]. Estrato contra-MME80 0,557 no
  teste, 0,442 na replicacao: registrado como o caso de manual.
- Replicacao 2 declarada ANTES de rodar: todo o historico nao tocado
  (out/2015-dez/2022) como UMA amostra; veredito final no combinado;
  por-ano reportado. `AMOSTRAS["historico_2015_22"]`, `combinar()` com
  recusa de hash diferente, `eas-preco-combinar` na CLI. 801 testes.

### Continuacao (2026-09-14, noite) — ORB fechado (CONTRA em 10 anos); 123 em F1 (v2.66)

- ORB historico 2015-22: 0,478 [0,454; 0,503] n=1.631; combinado
  2015-2026: **0,491 [0,471; 0,511] n=2.382 -> CONTRA**. Nenhum ano com
  IC fora de 0,50. Fechamento em `EAS_DE_PRECO.md` 4.5, com a
  observacao do operador (por tempo "acertava o lado") registrada como
  backlog da porta de volume, sem acao.
- 123: `marcar_123` / `contar_clausulas_123` / `ambiguidade_123` /
  `rodar_123` (`eas-preco --ficha 123`); `resolver_123` SEQUENCIAL
  (posicao aberta ignora sinal -> `ignorado_posicao`, contado);
  `FICHAS["123"]` trial 1. Expectativa declarada antes: provavelmente
  nulo. 9 testes novos; 808 no total, ruff e mypy limpos.

### Continuacao (2026-09-14, noite) — 123 CONGELADA (v2.67, so' docs)

Funil do 123 nos tres dumps: 3,3-3,5 sinais/pregao com regime, estavel;
ambigua 5-7%; por tempo 13-17%; D p50 430-620. Regime fica como
clausula (sem razao do 7.4; e' o mecanismo). Ficha congelada sem mudar
numero; sequencia inteira declarada (depuracao -> teste -> replicacao
-> historico -> combinado), veredito no combinado, trial 1.

### Continuacao (2026-09-14, noite) — 123: borda pequena e real; F5 desenhado (v2.68, so' docs)

- 123 combinado 2015-26: p1 = 0,5285 IC95 [0,515; 0,542] n = 5.444 — o
  IC EXCLUI 0,50; onze de doze anos acima. Inconclusivo pelo criterio
  (0,56) e o P&L (+17 bruto [-4; +38], +6 liquido) explica por que.
  Errata: a expectativa "provavelmente nulo" estava errada.
- Operador decidiu: 123 vai para F5 como PORTADOR da estrutura
  multi-EA, medindo EXECUCAO (slippage <= 6 pts, n = 100, ~50
  pregoes) e gravando a amostra da porta de volume. Ficha de forward
  de seis linhas e os 7 passos de implementacao em `EAS_DE_PRECO.md`
  5.4; pendencia 10 no EA_ARQUITETURA. Codigo comeca na proxima sessao.
- Execucao do 123 decidida: ORDENS REAIS (stop de entrada, stop de
  protecao + limitada de alvo, cancelamento pelo EA), nao emulacao —
  protecao na corretora sobrevive a queda de conexao. Residuo (par
  orfao, entrada nao cancelada) mitigado por reconciliacao de ORDENS
  ao reconectar (passo 4b). E2b (stop/limitada/cancel na demo) entra
  antes do passo 4. Passo 1 (barra de tempo) comeca na proxima sessao.

### Continuacao (2026-09-14, noite) — E2b: stop / limitada / cancel / OCO na demo (v2.70)

- `EventoOrdem` ganha `cl_ord_id`, `tipo`, `stop_preco` (o callback ja'
  entregava; ninguem lia). `bindings.py`: `SendStopBuyOrder`/
  `SendStopSellOrder` (limite, gatilho, qtd) e `SendCancelOrder` (conta,
  corretora, ClOrdID, senha em 4o) — assinaturas do profit_dll.py
  oficial, a conferir ao vivo.
- `ea/ordem_teste_b.py`: `OrdemDeTesteB`, maquina de estados ticada
  pelo record: mercado -> stop longe aceita e cancelada -> OCO de saida
  (stop venda + limitada venda) -> cancela a outra. Zera em qualquer
  falha; trava do E2 antes de cada Send*. `record --ordem-teste-b-em`.
- Fake DLL: ordens pendentes, cancelamento por ClOrdID, execucao
  automatica de uma perna. 7 testes (ciclo completo, timeout do OCO
  cancela as duas e zera, trava, stop mudo zera). 815 no total.
### 2026-09-14 (pregao) — E5.5 VALIDADO ao vivo; erro repetido corrigido (v2.71)

> NOTA DE NUMERACAO: esta entrega nasceu como v2.59 numa sessao que
> trabalhava em paralelo com outra (a dos EAs de PRECO). As duas
> partiram da v2.58 e a outra chegou primeiro ao remoto, ocupando as
> tags v2.59 a v2.70. Este trabalho foi rebaseado sobre a v2.70 e
> renumerado para **v2.71**. Licao: com duas sessoes no mesmo
> repositorio, conferir `git ls-remote --tags` ANTES de escolher o
> numero da tag.

**E5.5 validado por completo.** `z_agf_win` (WINFUT) subiu junto com o
record e rodou 5 horas; `venda_apenas` (WDOFUT) foi incluido A QUENTE
as 19:51, com o record em 47,6M de linhas. `descartados=0` o tempo
todo, fila estavel (pico 9.963 num total de 47M), ~25k linhas/s
sustentadas. O EA em cima da captura nao custou nada a ela.

- A trava de 1 EA por ticker funcionou ao vivo: `venda_apenas` estava
  com `symbol: WINFUT` e foi RECUSADO; o operador trocou para WDOFUT e
  entrou na varredura seguinte, sem reiniciar nada.
- Primeira operacao real do EA em dry_run: venda a 187435 (z_agf_3=1.98),
  **stop catastrofico batido a 545 pts contra** (limite 500), -556 pts
  liquidos, circuit breaker disparou na 3a perda seguida (-828 no dia).
  **Anomalia a investigar**: a ficha da Rota B preve stop de 100 pts;
  o preco andou 545 contra antes de qualquer saida. Ou a barra de
  120.000 contratos demorou demais a fechar num movimento rapido, ou a
  aplicacao do stop nao esta' saindo quando deveria. Analise offline,
  nao precisa de pregao.

**DEFEITO corrigido (achado pelo operador no log):** um yaml recusado
era reprocessado a cada varredura, gerando a MESMA linha de erro a cada
5 s -- ~25 repeticoes em 2 minutos, e seriam milhares num pregao
inteiro. Agora `_ea_falhas_conhecidas` guarda (caminho, mtime_ns): a
recusa sai UMA vez; editar o arquivo muda o mtime e provoca nova
tentativa na varredura seguinte, sem reiniciar; tirar o arquivo da
pasta esquece a falha. 3 testes novos. 764 no total.

### 2026-09-14 (noite) — E2b FECHADO ao vivo; fake alinhada; status reescrito (v2.72)

- E2b ao vivo (17:32, WINV26, Simulador): `resultado=ok` de primeira.
  Esteira medida: pendente `ClientCreated x2 (sem ClOrdID) ->
  HadesCreated -> New`; cancel `-> Canceled`; stop legada = `StopLimit`;
  cancel devolve 0. Latencias no EA_ARQUITETURA. Fake DLL alinhada.
- `docs/ESTADO_E_CAMINHOS.md` reescrito para 2026-09-14: as duas linhas
  (fluxo / preco), a escada, os 7 passos do F5 do 123 com estado, o que
  anda sozinho, o backlog, e a ordem recomendada. Repositorio local
  sincronizado com o remoto (v2.71: E5.5 validado, yaml recusado uma
  vez por versao).

### 2026-09-14 (noite) — passo 1 do F5 do 123: barra de TEMPO no EA (v2.73)

- `ea/barra_tempo.py`: `ConstrutorDeBarraDeTempo` — grade hh:00/15/30/45
  (periodo tem que dividir uma hora), fecha pelo trade ou pelo relogio,
  buraco sem barra vazia, trade fora de ordem levanta. `BarraFechada`
  com `vol_agr_compra/venda` e `n_trades` (defaults; barra de volume
  intacta). Equivalencia com resample do pandas em teste.
- `research/barra_tempo_conferir.py` + `profit-tape barra-tempo-conferir`:
  barras do TAPE (construtor do EA) x barras do GRAFICO (dump), barra a
  barra, por dia — item 2 do checklist do forward no dado real. Teste
  com dump adulterado acusa a barra certa.
- 8 testes novos; 826 no total, ruff e mypy limpos.

### 2026-09-15 — passo 1 FECHADO no dado real; fim de sessao e barra parcial (v2.74)

`barra-tempo-conferir` em 28/08 e 11/09: 69/69 barras com dado completo
identicas ao tick. As duas diferencas viraram regra no construtor:
(a) o grafico dobra os negocios de 18:30+ na barra 18:15 -> `fim_sessao_hhmm`;
(b) a primeira barra depois de ligar e' `parcial` (record de 11/09 entrou
as ~09:50: open/low 75 e 155 pts fora) -> excluida da conta e, no EA, de
sinal e indicador. 10/09: sem tape por queda de conexao; backfill do
operador. 829 testes.

### 2026-09-15 — passo 2 do F5 do 123: semente da MME80 (v2.75)

- `ea/semente.py`: `IndicadorMME` (alpha 2/(n+1), semeado em valor
  dado), `construir_semente` (mme80_ntsl da ultima barra do parquet +
  ponte pelo tape com o construtor do EA; dia util sem >= 30 barras e
  nao declarado feriado -> INVALIDA com o dia no motivo), `conferir_no_dia`
  (recursao pelo tape de D contra o mme80_ntsl do grafico em D).
- `profit-tape semente-conferir <parquet> --dia D [--feriado ...]`.
- 7 testes (semente exata, ponte, dia faltando / feriado, tape fino,
  sem parquet, recursao reproduz o grafico ao centesimo). 836 no total.

### 2026-09-15 — passo 2 fechado no dado real; passo 3: SinalPreco123 (v2.76)

- `semente-conferir`: 28/08 dif 0,0 em 38 barras; 11/09 -15,5 -> -7 pts
  ao longo do dia (os 3 closes de 09:00-09:30 sem tape), como previsto.
  Regra decidida: dia com o EA ligado depois da 09:00 nao arma sinal
  (`ea.dia_incompleto`); a MME segue para convergir no dia seguinte.
- `research.eas_preco.avaliar_123`: a formula escalar da ficha;
  `marcar_123` (10 anos) conferida contra ela por equivalencia.
- `ea/sinal_123.py`: `SinalPreco123` -> `Candidato123` (niveis, validade
  ate' o fim de t+1, MME, fluxo da barra t). Parcial: alimenta a MME,
  reinicia a janela. Criterio de parcial refinado: 1o trade > 60 s
  depois do inicio da barra (`ts_primeiro_ns` na BarraFechada).
- 4 testes novos (equivalencia EA x research em barras aleatorias, dia
  incompleto, parcial, niveis/validade/fluxo). 840 no total.

### 2026-09-15 — passo 4 do F5 do 123: ciclo de ordens (v2.77)

- `ea/execucao.py`: `enviar_stop`, `enviar_limitada`, `cancelar`, `zerar`,
  `eventos_de` — assincronos, mesmas travas (`_trava`), assinaturas e
  esteira do E2b.
- `ea/ciclo_123.py`: `CicloDeOrdens123` — a maquina do 5.4 com os dois
  modos (real por callbacks no tick; dry_run com fills pelo tape no
  on_trade), um candidato por vez, validade da entrada ate' o fim de
  t+1, OCO pelo EA, zeragem 17:30, slippage/latencia por ordem e
  `OperacaoRegistrada` por operacao; avisos CONFIRA em timeout.
- 9 testes (dry: alvo, stop, nao executou, zeragem, ignorados; real:
  ciclo completo por callbacks, cancel no fim de t+1, cancel nao
  confirmado, stop recusada). 849 no total.

### 2026-09-15 — F5 do 123: passos 4b, 5, 6 e 7 (codigo) (v2.78)

- 4b: `CicloDeOrdens123.reconciliar_apos_reconexao()` (cancela todas as
  ordens do ticker, consulta posicao, re-arma saida / fecha
  `reconciliado` / zera orfa / limpa pendente); `SendCancelOrders` no
  bindings e `cancelar_todas`/`consultar_posicao` no executor; o
  servico dispara na transicao `corretora_pronta` False -> True.
- 5: `ea/gate_fluxo.py` — `GateDeFluxo`, `SemFiltro`, `construir_gate`
  recusa qualquer conteudo sem ficha.
- 6: `ea/registro_123.py` — JSONL por dia, uma linha por operacao, com
  carimbo, fluxo da barra t e da barra do gatilho, ordens e desfecho.
- 7: `ea/config_123.py` (`EA123Config`, `carregar_config_ea` por tipo),
  `ea/service_123.py` (`EA123Service` com `tick()`), `config/ea_123.yaml`
  (dry_run: true), registro/recorder aceitam os dois tipos, bridge
  chama `tick()`. Modo exclusivo: o 123 ocupa a vaga ao armar e libera
  ao fechar (`sinais_sem_vaga` contado).
- 15 testes novos; 859 no total, ruff e mypy limpos. Falta: pregao em
  dry_run (7a) com barras e ordens olhadas; depois E4 (7b).
- v2.79: `semente-conferir` com `--dia` sem tape (a vespera do pregao)
  quebrava com KeyError('dif') depois de a semente ja' ter saido valida.
  Agora devolve so' a semente e uma nota. Semente de 15/09 conferida:
  187.995,23, ponte pelo 14/09 (34 barras; faltam 18:00/18:15).

### 2026-09-15 — perfis de instrumento; WDO declarado; acoes registradas (v2.80)

- `eas_preco.PERFIS` / `usar_instrumento` (WIN default intacto; WDO:
  tick 0,5, 1 pt = R$10, custo 0,30 pt, fim de sessao 18:00);
  `arredondar_ao_tick` le o tick em tempo de chamada (default de
  funcao capturava TICK_WIN na importacao); hash da ficha inclui o
  perfil (`parametros_da_ficha`); `--instrumento` em `eas-preco`,
  `eas-preco-teste`, `eas-preco-combinar`.
- `EAS_DE_PRECO.md` 8: ficha por instrumento, multiplicidade declarada,
  WDO com as tres fichas na versao congelada do WIN, acoes com lista
  fechada e o que muda (sem tape, bolsa B, E2 a refazer). 862 testes.
- v2.81: perfil WDO com fim de sessao 18:30 (ultima barra 18:15,
  confirmada no dump); rotulos do funil e da CLI com os valores do
  instrumento (estavam fixos em 20/11/0,20 — os calculos ja' eram os
  certos); 8.2 corrigido: acoes TEM tape (PETR4/VALE3/ITUB4/BBAS3 no
  record); funil WDO 2023-25 registrado em 8.1. Nota: o dump do WDO e' a
  serie ajustada (8 decimais).
- v2.82 (docs): WDO — funis das tres fichas nos tres dumps registrados;
  fichas CONGELADAS como as do WIN, com o perfil wdo; sequencia declarada.

### 2026-09-15 — WDO fechado (3 fichas, nenhuma sobrevive); trial por instrumento (v2.83)

- WDO combinado 2015-2026: IFR2 0,492 CONTRA; ORB 0,517 inconclusivo;
  123 0,514 [0,499; 0,528] inconclusivo — nao replica o WIN (por-ano
  sem o padrao 11/12). Seis testes de preco em dois futuros, todos
  0,49-0,53: o 123 do WIN fica como portador, nao aposta.
- `eas_preco_teste.TRIALS` por (ficha, instrumento): IFR2 do WDO saiu
  com IC 97,5% (trial da familia no WIN); corrigido, veredito igual.
- 863 testes.

### 2026-09-15 — ficha 9: 123 + gate de volume de candle (v2.84)

- Decisao do operador: gate de volume -> gap de abertura -> max/min da
  vespera -> acoes. Fichas 9 (rascunho v0, a medir), 10 e 11 (declaradas).
- `eas_preco.perfil_volume_horario` (mediana por hhmm nos 20 pregoes
  anteriores), `marcar_123_gate` (subconjunto + complemento),
  `rodar_123_gate`, `--ficha 123gate` no funil; `eas_preco_teste`:
  familia "123gate" trial 1, `resolver_123(gate=True/False)`,
  complemento reportado no teste e no combinado.
- Barra de tempo ganha `vol_total` (todos os trades); `barra-tempo-conferir`
  reporta a diferenca de volume EA x grafico (equivalencia que o gate
  ao vivo precisa). 4 testes novos; 867 no total.
