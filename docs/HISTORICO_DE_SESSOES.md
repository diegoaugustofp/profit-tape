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
