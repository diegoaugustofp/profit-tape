# Scalp de Bollinger modificada (15s) — hipótese em formalização

Estado: **ANTES do pré-registro**. Este documento é o texto que vai
virar a ficha de seis linhas do forward (skill `disciplina-forward`)
quando as dúvidas abertas fecharem e a TAXA for medida. Nada aqui foi
calibrado: os números são os que o operador opera.

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
  aberta, sinal ignorado (comportamento atual do EA — a confirmar).
- As três barras no mesmo pregão.
- Execução parcial de n contratos → as n primeiras pernas na ordem
  RP1 → RP2 → final (a confirmar: "só RP1" com 1 contrato foi dito; com
  2, RP1+RP2 é a leitura).

Saída: 3 pernas de 1 contrato. Stop 8 ticks em todas. Alvos 8 / 13 /
20 ticks. Trailing só nas pernas 2 e 3: ativa a 5 ticks a favor, puxa
o stop para 2 ticks, arrasta a cada 1 tick.

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

O que o manual do NTSL **não diz**, e o dump mede: se o desvio da
Bollinger é populacional ou amostral; se `SlowStochastic()` devolve %K
lento ou %D; se `AvgTrueRange(21, 0)` é SMA do TrueRange. Candidatos
todos calculados em `indicadores()`; `equivalencia()` diz qual bate.

## 5. Ferramentas (entregue-v1.93)

- `ntsl/bollinger_scalp.ntsl` — dump do 15s: OHLC + os indicadores do
  Profit. Não marca sinal, de propósito: o Profit é a referência e a
  referência não pode conter o que está sendo conferido.
- `profit-tape bollinger-scalp <dump>` — equivalência + largura da banda
  e ATR em pontos + funil por cláusula. Categoria `features`, zero trial.

O buffer do console retém ~2.000 linhas e **um pregão de 15s tem
~2.260**: use `LogHoraInicio/Fim` e dumpe em duas metades. Identidade
da barra é (data, `CurrentBar`), porque `Time` em HHMM repete 4 vezes.

## 6. Dúvidas abertas (bloqueiam a ficha)

1. True Range: fora do v1 (sugestão), ou `ATR21` / `SMA21(ATR21)` com
   qual limiar em pontos?
2. Trailing: 2 ticks atrás da **máxima favorável**? A perna RP1 mantém
   −40 quando as outras vão para +15?
3. Horário de operação, máximo de operações/dia, circuit breaker de 3
   perdas mantido? Margem de 3 contratos com R$ 5.000?
4. Barra de 15s sem negócio: o Profit desenha ou pula? (o dump
   responde: buraco em `Time` com `CurrentBar` contíguo = pulou)
5. `custo_pontos_estimado = 11` é por contrato, ida e volta?
6. Sinal com posição aberta é ignorado?

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
