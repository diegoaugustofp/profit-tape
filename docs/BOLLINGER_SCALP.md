# Scalp de Bollinger modificada (15s) — hipótese em formalização

Estado (2026-09-09): **ficha escrita (§0), v1 congelada**. Falta a
depuração pelo tape (replay das três pernas) para preencher os dois
campos "a medir" antes de ligar o forward. Nada aqui foi calibrado a
resultado: os números são os do operador ou medidos em features.

## 0. Ficha de seis linhas (v1, `entregue-v2.11`)

    HIPOTESE   Na manha do WIN, com o preco trabalhando acima da banda
               estreita (0,38 sigma / 21 em 15s), uma correcao de uma
               barra seguida de retomada e' continuacao: comprar o
               reteste do topo da correcao, com stop de 0,7 x ATR21 e
               alvos de 1 / 1,625 / 2,5 stops, paga o custo. Espelho
               na venda.

    EVENTO     Barra de 15s, indicadores reiniciados a cada pregao,
               janela = a partir da 22a barra do dia ate' 12:59:45.
               t-2 vermelha e close > B_sup; t-1 branca e close > B_sup;
               em t, limitada de compra em high(t-2), lote 3, cancela
               se nao executar em t. Sem estocastico. Sinal com posicao
               aberta e' ignorado. Stop = 0,7 x ATR21(t-1) ao tick
               (meio-tick para cima), congelado; alvos 1 / 1,625 / 2,5
               stops; trailing nas pernas 2 e 3: ativa a 0,625 stop,
               puxa para 0,25 atras da maxima favoravel, passo 0,125;
               perna 1 nao se move. Zeragem 17:30. Execucao parcial de
               n contratos -> pernas RP1, RP2, final nessa ordem.
               Circuit breaker de 3 perdas mantido.

    TAXA       SINAIS: 82 compra + 56 venda por pregao (09:08-13:00,
               2 pregoes inteiros medidos no grafico); limitada tocada
               em 83% / 91% deles, 77% ja' na abertura de t. Sinais a
               cada 4 barras na mediana -> a maioria cai dentro de uma
               operacao aberta. OPERACOES por pregao: A MEDIR no replay
               pelo tape (depuracao). Ordem de grandeza esperada: 10-30.

    EFEITO     Resultado BINARIO por operacao na perna 1: alvo1 (+1
               stop) antes do stop (-1 stop), ordem intrabarra pelo
               tape. Nula de lucro apos custo (11 pts) com stop mediano
               62 pts: p1 = 0,59. Quero enxergar p1 >= 0,65 contra
               p1 <= 0,55: meia-largura de 5 pp -> n = 370 operacoes.
               Secundario, so' reportado: P&L total das 3 pernas em
               pontos, por operacao e por pregao.

    HORIZONTE  n = 370 / (operacoes por pregao). A 20 por pregao, ~19
               pregoes (1 mes); a 10, ~37 (2 meses); a 5, ~74 (3,5
               meses). Todos < 6 meses. Numero final depois do replay.

    CRITERIO   Ao atingir n = 370: p1 >= 0,65 favoravel; p1 <= 0,55
               contra; entre os dois, inconclusivo (e o P&L secundario
               nao promove um inconclusivo). IC de 95% reportado sempre.

    PARADA     Olho em n = 185 (metade) so' para defeito de
               especificacao (barras marcadas, uma a uma), NAO para
               veredito. Decido em n = 370. Sequencia de perdas, dia
               ruim ou circuit breaker NAO autorizam parar antes: sao
               risco, nao veredito. Mudanca de qualquer numero acima
               reinicia a contagem (carimbo de versao).

Variantes registradas para DEPOIS (nao v1): estocastico como
"acelerador" (com <20 / >80, entrada a mercado na abertura de t em vez
de limitada); regra de horario por volume (perfil medido, platô 13-16h).

Origem: especificação do operador em 2026-09-04
(`Scalping com bandas de Bollinger.md`), consolidada em conversa na
mesma data. O 6 minutos (MM70, estocástico direcional) foi
**descartado** pelo operador; só o 15s conta.

## 1. Regra consolidada (compra; a venda é o espelho exato)

Tudo na barra de 15s. `B_sup/B_inf` = Bollinger(desvio 0,38; 21;
aritmética). `Est` = estocástico lento (8, média 3), **linha %K lento**.

| barra | condição |
|---|---|
| t−2 (correção) | vermelha (`close < open`) **e** `close > B_sup` |
| t−1 (sinal) | branca (`close > open`) **e** `close > B_sup` **e** `Est(t−1) < 20` |
| t (entrada) | na abertura de t, **ordem limitada de compra em `high(t−2)`**, lote 3. Não executou até o fim de t → cancela |

Venda: banda inferior, `Est(t−1) > 80`, limitada em `low(t−2)`.

- Doji (`close = open`) não é vermelho nem branco: não forma sequência.
- Sem cooldown: qualquer nova sequência é sinal novo. Com posição
  aberta, sinal ignorado (confirmado 2026-09-05).
- As três barras no mesmo pregão.
- Execução parcial de n contratos → as n primeiras pernas na ordem
  RP1 → RP2 → final (confirmado 2026-09-05).

Saída: 3 pernas de 1 contrato. Stop 8 ticks em todas. Alvos 8 / 13 /
20 ticks. Trailing só nas pernas 2 e 3: ativa a 5 ticks a favor, puxa
o stop para 2 ticks atrás da máxima favorável, arrasta a cada 1 tick.
**A perna RP1 não se move**: fica em −8 ticks até bater +8 ou o stop
(confirmado 2026-09-05).

Horário (2026-09-05): **entradas até 13:00**, porque a estratégia
precisa de volume. Encerramento forçado às 17:30 como seguro (redundante
na prática; o EA já tem hora de encerrar). O corte de 13h é o
provisório: `profit-tape perfil-volume-horario` mede o perfil de
agressão por faixa de 30 min (mediana entre pregões), e a regra por
volume — se houver — é declarada pelo operador em cima desses números,
**antes** de qualquer replay que olhe resultado.

True Range: **fora do v1** (2026-09-05). Fica só medido (ATR21 em
pontos no `bollinger-scalp`) para decisão futura. Circuit breaker de 3
perdas: mantido (não foi revogado).

## 2. Em pontos do WIN (tick = 5 pts) — regra 7.5

| item | ticks | pontos |
|---|---|---|
| stop | 8 | 40 |
| RP1 / RP2 / final | 8 / 13 / 20 | 40 / 65 / 100 |
| trailing: ativa / puxa para / passo | 5 / 2 / 1 | 25 / 10 / 5 |
| meia-largura da banda 0,38σ | **a medir** (`bollinger-scalp` reporta) | |

Com `custo_pontos_estimado = 11` (a confirmar: por contrato, ida e
volta), a perna RP1 é +29 líquido contra −51 no stop: **sozinha,
precisa de ~64% de acerto para empatar**. As pernas 2/3 pagam a conta,
se pagarem — é isso que o forward mede.

Slippage: com stop de 40, **cada tick de slippage é 12,5% do risco**.
Emular stop/alvo com ordem a mercado não é neutro aqui.

## 3. Mudança de natureza vs. a especificação original

A spec original era rompimento (venda: stop na perda da mínima). A
regra consolidada é **retorno**: limitada no extremo da barra de
correção. Consequência: se a barra de sinal fechou aquém do limite, a
ordem executa **na abertura** de t (equivale a mercado); se fechou
além, espera o **recuo** e pode não executar. O funil conta os dois
separadamente — são regimes de preenchimento diferentes.

Toque no limite não é preenchimento: na fila da B3 o preço pode tocar
sem executar. O OHLC diz "tocou"; o replay pelo tape é quem resolve.

## 4. Equivalências verificadas (nada de "biblioteca de indicadores")

Em 3.000 barras sintéticas, identidade algébrica, sem dado real:

| original | equivalente | resultado |
|---|---|---|
| `close > Bollinger_sup(k, n)` | `(close − SMA_n)/DP_n > k`, barra atual **incluída** | 0 divergências, ddof 0 ou 1 |
| `zscore_rolante` do projeto | — | diverge (shift(1), ddof=1): 43/2.980 barras. **Não reaproveitar** |
| estocástico rápido %K | `100 + Williams %R` | erro 1e−14; `%K > 50 ⟺ close acima do meio da faixa` |
| True Range | `(H−L) + gap` contra o close anterior | identidade; difere de H−L em 44% das barras (as com gap) |
| "MM70 subindo" | `close_t > close_{t−70}` | identidade exata (descartado com o 6m, fica registrado) |

O que o manual do NTSL **não diz**, o dump mediu (01–04/09/2026, 2.249 +
3.160 barras, `dif_max` em pontos):

| campo do Profit | variante que bate | dif_max | a outra variante |
|---|---|---|---|
| `BollingerBands(0.38, 21, 0)` | desvio **populacional** (ddof=0) | 0,0 | amostral erra até 3,2 pts |
| `SlowStochastic(8, 3, 0)` | **%K lento** (SMA3 do %K rápido) | 0,0 | %D erra até 28; %K rápido até 60 |
| `AvgTrueRange(21, 0)` | **SMA21 do TrueRange** | 0,0 | Wilder erra até 73 pts |
| `TrueRange` | `(H−L) + gap` vs. close anterior | 0,0 | — |

A primeira barra do dump é a exceção: o Profit tem o close do dia
anterior (gap de 625 pts em 01/09), o Python não — fica NaN.

O Profit **não pula barra de 15s sem negócio**: 563 minutos de 01/09,
todos com 4 barras. Dúvida fechada.

## 5. Ferramentas (entregue-v1.93)

- `ntsl/bollinger_scalp.ntsl` — dump do 15s: OHLC + os indicadores do
  Profit. Não marca sinal, de propósito: o Profit é a referência e a
  referência não pode conter o que está sendo conferido.
- `profit-tape bollinger-scalp <dump>` — equivalência + largura da banda
  e ATR em pontos + funil por cláusula. Categoria `features`, zero trial.

O buffer do console retém ~2.000 linhas e **um pregão de 15s tem
~2.260**: use `LogHoraInicio/Fim` e dumpe em duas metades. Identidade
da barra é (data, `CurrentBar`), porque `Time` em HHMM repete 4 vezes.

## 5.1 O que o dump de 01–04/09 mostrou (2026-09-08) — em pontos

**Banda**: meia-largura de 0,38σ = 19 pts no dia inteiro, 26 pts nas
manhãs (4–5 ticks). "Acima da banda" é `close > SMA21 + ~4 ticks`.

**Funil (janela 09–13h, só os 2 pregões inteiros do dump — 03 e 04/09
vieram pela metade; compra / venda por pregão)**:

| cláusula | compra | venda |
|---|---|---|
| + t−2 correção fora da banda (candidatos) | 86 | 58 |
| + estocástico(t−1) extremo (<20 / >80) | **1,5** | **0** |

Abertura (2026-09-09): 09:00–09:02 é leilão e o índice demora a abrir;
a primeira barra nasce no primeiro negócio de agressão (leilão =
`trade_type 4`, fora das barras). Proposta declarada: **janela dos
indicadores reinicia a cada pregão** (o close de ontem não é informação
para um scalp de 15s) e **sem entrada nas primeiras 21 barras** do dia
(~09:08). Diverge do gráfico só nesses 5 minutos. Aguardando
confirmação.

**O estocástico seca a hipótese, e é estrutural (7.6)**: entre os
candidatos a compra, `Est(t−1)` tem mediana 72 e p5 = 41; abaixo de 20,
1 em 164 no dia, 3 em 238 nas manhãs. Venda acima de 80: zero. Um
branco fechando acima da banda superior fecha, por construção, no topo
da faixa de 8 barras; o %K lento (média de três %K rápidos) não
consegue estar no fundo dela ao mesmo tempo. Nem em t−2 (a correção):
0 abaixo de 20. Abandonar a cláusula antes do replay não é p-hacking —
ela nunca dispara. A leitura alternativa do próprio texto do operador
("acima de 50 = perna de alta") manteria ~90% dos candidatos (148/164).
**Decisão pendente do operador.**

**O stop é menor que a barra**: TR mediano de 15s = 49 pts (dia) / 64
(manhãs). **65% das barras têm TR ≥ 40** (o stop cabe em uma barra);
**23% têm TR ≥ 80** (stop e RP1 na mesma barra). A spec pede 8 ticks num
mercado onde a barra de 15s anda 10–13 ticks. A própria spec previu
("TR amplo vs. stop de 8 → aguardar") — no WIN a 180 mil, "aguardar" é
o estado normal. Reabre a decisão "TR fora do v1" como pergunta de
desenho: stop em ticks fixos ou em fração do ATR? **Pendente.**

Estranhezas do dump a esclarecer: barras começam às 09:02:45 nos dois
dias completos (11 barras de abertura ausentes); 03 e 04/09 só têm
12:24–14:00 no dump de 4 dias, com recorte idêntico.

## 5.2 Cinco pregões inteiros no gráfico (2026-09-09) e o replay pelo tape

Dumps de um pregão cada (01, 02, 03, 04, 08/09), buffer segura o dia:
equivalência bate nos cinco (dif_max 0,0 em todos os campos). Funil v1
(janela 09:08–13:00): **69 sinais de compra e 63 de venda por pregão**,
tocados 59 / 58 = **117 por pregão**. O espelho aparece: 03/09 (dia de
baixa) deu 47 compras e 79 vendas.

`profit-tape bollinger-replay` (`entregue-v2.13`): barras de 15s
montadas do **tape** (agressão; balde de 15s no relógio; indicadores
reiniciam por pregão), regra v1, e as três pernas executadas negócio a
negócio — limitada em t (abertura se o primeiro negócio já está a
favor; recuo só se um negócio **atravessa** o limite), stop/alvo por
perna, trailing atrás da máxima favorável, zeragem 17:30, circuit
breaker de 3 perdas líquidas seguidas, sinal com posição aberta
ignorado. `--dumps` compara as barras do tape com as do gráfico nos
mesmos dias (OHLC e sinais) — a prova de que o replay vê o que o
operador vê. Saída: `operacoes.parquet` (uma linha por sinal, com
`motivo_nao_exec` ou as três pernas) e o resumo com p1, IC95 de Wilson,
nula de lucro, operações por pregão.

Assunções do replay, registradas: lote 3 inteiro; alvo no toque; stop
no preço do stop (slippage zero); stop antes do alvo no mesmo negócio;
custo 33 pts por operação (11 × 3).

## 5.3 Primeiro replay (2026-09-10, 30 pregões) — INVÁLIDO, ver 5.4

Tape × gráfico **não bateu**: high/low divergem em ~4% das barras,
open/close em ~30%. Padrão de RLP (imprime dentro do spread). A v2.24
mede três conjuntos de negócios (agressão; +RLP; +RLP+leilão) e reporta
qual reproduz o gráfico. Também: 94 barras faltando no tape em 04/09 e
53 em 08/09 (buraco do recorder?), e 02–03/09 ausentes do curated.

Com essa ressalva: 398 operações (13,3/pregão), **p1 = 0,49, IC 0,44–
0,54** contra nula de lucro 0,59; P&L líquido −35 pts/operação. Pernas:
1 = 195 alvos / 203 stops; 2 = 8 alvos / 390 stops; **3 = 0 alvos /
398 stops**. Duração mediana 17 s. Leitura de mecanismo, não de número:
o trailing (puxa para 0,25 stop após 0,625) coloca o stop a ~15 pts do
preço num mercado de barra de 60; as pernas 2 e 3 morrem no ruído e a
perna 3 nunca vê 2,5 stops. A entrada, com barreira simétrica, não se
distingue de moeda nesta amostra. Nada foi ajustado: é amostra de
depuração e o dado ainda não está limpo. Próximo: equivalência das
barras fechada, rerodar, e só então conversa de desenho.

## 5.4 O que o segundo replay mostrou (2026-09-10, v2.25)

**Barras**: o gráfico do Profit monta o OHLC com **agressão + RLP**.
Com esse conjunto, 1–2 barras divergentes por dia (contra ~700) e os
sinais batem exatamente onde o tape está inteiro (01/09: 85/85,
67/67). Leilão não muda nada. As barras do replay passam a usar
agressão + RLP; a **execução** continua contra agressão (RLP não é um
preço em que a ordem do operador necessariamente executa). Recorder
começou tarde em 04/09 (09:26) e 08/09 (10:01); 02 e 03/09 não foram
capturados (licença do backfill — fora deste escopo).

**Defeito de processo na v2.13**: uma substituição de texto não casou
(o `ruff format` reformatou o laço antes) e foi em silêncio, nos testes
também. O replay ainda tinha `break` no circuit breaker e `continue`
mudo na posição aberta: ~90% dos sinais sumiam da contagem. Corrigido
com edição verificada (`assert count == 1`) — regra nova de engenharia.

**Taxa da regra**, reproduzida com as barras reais de 01/09: 152
sinais; com circuit breaker, **5 operações** (145 bloqueadas); sem,
**118 operações** (13 ignoradas por posição aberta, 21 não
atravessadas). As "13,3 operações por pregão" da 5.3 eram o circuit
breaker fechando cada pregão nos primeiros minutos. O `--ignorar-
circuit-breaker` mede a regra inteira.

**Resultado (5.3, ainda válido como direção, não como número)**: p1 ≈
0,49 é a perna 1 se comportando como moeda; pernas 2/3 positivas em
61% das vezes com média ≈ 0 (o trailing paga +0,375 stop quase sempre
e −1 stop no resto); custo de 33 pts por operação é a perda inteira.
Rerodar com barras corrigidas, com e sem circuit breaker, antes da
conversa de desenho.

## 6. Dúvidas — fechadas em 2026-09-05, exceto as que o dump responde

Fechadas: TR fora do v1; trailing atrás da máxima favorável, RP1
parada; entradas até 13h, zeragem 17:30; custo 11 por contrato ida e
volta; sinal com posição aberta ignorado; parcial → pernas em ordem.

Fechada pelo dump (2026-09-08): o Profit desenha toda barra de 15s.

Ainda em aberto:
1. Margem de 3 contratos com R$ 5.000 (conferir na corretora).
2. Máximo de operações por dia: não declarado — sem limite no v1 além
   do circuit breaker.
3. **Estocástico** (5.1): manter como está (taxa ~0), trocar pela
   leitura de tendência (>50 / <50), ou retirar.
4. **Stop vs. barra** (5.1): 8 ticks fixos ou fração do ATR21.
5. Horário: 09:00–13:00 fixo, joelho da curva de volume medida em 28
   pregões (12:30 = 47% da abertura; 13:00–16:30 = platô de 36–41%).
   Proposto em 2026-09-08, aguardando confirmação.

## 6.1 Tick a tick: onde a estratégia pode e não pode ser validada

Observação do operador (2026-09-05), a partir do que o `absorcao_barra`
ensinou: dentro do Profit, tick a tick vale **1 semana** para
backtest/automação. Numa barra de 15s com stop e alvo a 40 pts, o
high/low não diz quem bateu primeiro — sem tick a tick o backtest do
Profit é opinião. Logo: **esta estratégia não se valida dentro do
Profit**, a mesma conclusão que fundou o projeto em ProfitDLL/Python.

Divisão de fontes, então:
- **dump do gráfico de 15s** → TAXA de gatilhos (funil) e equivalência
  dos indicadores. Só barras.
- **tape do recorder** (24/07 em diante, +1 pregão/dia) → EFEITO: qual
  perna bate primeiro, a limitada executou ou não, ordenação intrabarra.
  Sem o limite de 1 semana.

## 7. O que ainda não existe no código (e a ordem)

| peça | estado |
|---|---|
| barra de 15s ao vivo (fecha pelo relógio, não por volume) | ❌ |
| ordem limitada, stop, alteração, cancelamento na DLL (`SendBuyOrder`, `SendStopSellOrder`, `SendChangeOrder`, `SendCancelOrder` existem na DLL, não no `bindings.py`) e rastreio de estado de ordem | ❌ |
| posição com 3 pernas e parciais (`GestorDeRisco` é integral por design) | ❌ |
| trailing | ❌ |
| replay com ordenação intrabarra pelo tape (base existe na Rota B) | parcial |

Ordem: dump → equivalência medida → funil (TAXA) → ficha de seis linhas
→ replay pelo tape com 3 pernas → só então execução. Nada de EA antes
de a ficha existir (skill disciplina, regra 1).
