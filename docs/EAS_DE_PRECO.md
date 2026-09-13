# EAs de PRECO — linha paralela enquanto o tape acumula (2026-09-13)

Estado: **tres fichas em RASCUNHO, NAO CONGELADAS.** Congelam quando a
TAXA de cada uma estiver MEDIDA (`profit-tape eas-preco` sobre o dump
M15) e os numeros em pontos preenchidos. Ate' la' nenhuma delas gasta
amostra de TESTE.

Ordem decidida pelo operador: **IFR2 primeiro**, ORB em seguida, 123
depois. Fase de cada uma na tabela da secao 1 do `EA_ARQUITETURA.md`.

## 0. Por que esta linha existe

O operador assumiu o custo de P&D por 6 meses porque e' o prazo minimo
para o tape acumular. Nao quer esperar 6 meses para ter o primeiro EA
em execucao. A resposta nao e' "coloca algo rodando para pagar a
infra" (custo afundado nao decide estrategia) — e':

**EA de preco nao tem o problema de historico.** Candle de WIN existe
por anos. Ele pode ser validado HOJE com amostra de teste de verdade,
coisa que o EA de fluxo nao consegue ainda. E' esse argumento que
sustenta a linha, e so' ele.

Duas decisoes de desenho que vem junto:

1. **O EA nasce sabendo que vai evoluir.** Cada EA de preco tem uma
   PORTA DE VOLUME declarada na ficha (qual feature de fluxo entraria,
   onde). A porta existe desde o dia 1 na interface; o conteudo chega
   pela disciplina — incluir a feature e' HIPOTESE NOVA, com ficha nova
   e contagem reiniciada (carimbo de versao), nunca upgrade.
2. **Toda inclusao de variavel passa pela disciplina inteira** (triagem
   7.2, poder, 7.4, pre-registro). Vale para os tres, sempre.

## 1. O que muda no pipeline F0-F6 para um EA de preco

O pipeline da secao 0 do `EA_ARQUITETURA.md` continua. O que muda e' a
FONTE de cada fase, porque a amostra e' candle e nao tape:

| Fase | EA de fluxo | EA de preco |
|---|---|---|
| F1 Features | `curated` do tape | **dump do grafico M15** (`ntsl/preco_m15.ntsl`) hoje; `RequestSerieHistory` serie de BARRAS (10.000 candles, ~270 pregoes em M15) quando implementada |
| F2 Triagem | funil + EMD sobre o tape | funil por clausula sobre o dump (`eas-preco`) + ATR/amplitudes em PONTOS |
| F4 Depuracao | replay pelo tape | **duas amostras**: DEPURACAO = dump mais recente (barras olhadas uma a uma); TESTE = historico anterior, nao olhado durante a depuracao. Uma rodada. |
| F5 Forward | E4 em demo | igual — mesma escada E0-E5, mesmo `--ea-modo-ticker exclusivo` |

**Onde o candle NAO basta (licao 6.1 do Bollinger):** com barreiras
simetricas, a barra em que alvo e stop cabem juntos nao diz quem bateu
primeiro. Em M15 isso e' raro se D >= ATR14 (a medir: `eas-preco`
reporta a fracao). Regra: no historico, barra ambigua e' EXCLUIDA do p1
e reportada; no periodo com tape (24/07 em diante) a ordem intrabarra
sai do tape, como na Rota B. Se a fracao ambigua passar de ~10%, o
estimador binario nao serve e a ficha volta ao desenho.

**Estimador em todas as tres: BINARIO com barreiras simetricas** (alvo
= stop = D). Nula a custo zero = 50%; variancia limitada; horizonte sai
de uma conta. Borda bruta por operacao = D x (2 p1 - 1). Com custo de 11
pts ida-e-volta, a borda paga o custo so' se

    D x (2 p1 - 1) > 11     ->     a p1 = 0,56:  D > 92 pts
                                   a p1 = 0,60:  D > 55 pts

Isso e' o **custo maximo** de cada ficha, em pontos, e vira alerta no EA
(igual ao Bollinger): se `custo_pontos_estimado` > borda bruta medida,
o EA avisa e nao liga.

**Multi-EA:** os tres operam WIN. Com `--ea-modo-ticker exclusivo` so'
um fica posicionado por vez; `sinais_sem_vaga` no heartbeat mede o
custo estatistico disso (4.4b). Nao e' problema em F4 (historico, cada
um sozinho); e' problema em F5/F6 e fica visivel no log.

## 2. Convencoes comuns as tres fichas

- Barra: **M15**, WINFUT, indicadores CONTINUOS entre pregoes (e' o que
  o grafico plota e o que o dump entrega; reiniciar por pregao seria
  outra hipotese).
- Tick = 5 pts. Meio-tick arredonda para CIMA (`arredondar_ao_tick`).
- Regime: `MME80` de fechamento. Compra so' com `close > MME80`, venda
  so' com `close < MME80`. Uma clausula, uma variante — o funil reporta
  a variante Eden (MME8 > MME80, ambas subindo) SO' como informacao,
  nao como opcao a escolher depois.
- Entrada a MERCADO na abertura de t+1 (o EA ve o fechamento de t e
  manda a ordem; no historico, referencia = open(t+1)). Excecao: ORB e
  123 entram por ordem STOP no rompimento (a referencia e' o nivel
  rompido + 1 tick).
- Uma posicao por vez por EA. Sinal com posicao aberta e' ignorado.
- Ultima entrada: barra que fecha ate' 16:30. Zeragem forcada 17:30;
  operacao zerada por tempo NAO conta no p1 (reportada a parte).
- ATR14 = **SMA14 do TrueRange** (variante que o Profit calcula,
  medida no Bollinger: `AvgTrueRange(n, 0)` = SMA, Wilder erra ate' 73
  pts). RSI(2): variante (Wilder ou SMA) **a medir** pelo `eas-preco` —
  o manual nao diz.
- Custo: 11 pts ida-e-volta por contrato (`custo_pontos_estimado`).
- Circuit breaker de 3 perdas: mantido, e' risco, nao veredito.

## 3. Ficha IFR2 (rascunho v0) — retorno a` media em extremo

    HIPOTESE   No WIN em M15, RSI(2) em extremo (<= 10 na compra,
               >= 90 na venda) e' exaustao de curto prazo; entrando a
               favor do regime (lado da MME80) na abertura da barra
               seguinte, a barreira favoravel a 1 x ATR14 bate antes da
               desfavoravel em mais de 50% das vezes.

    EVENTO     Barra M15 t fechada. COMPRA: RSI2(t) <= 10 e close(t) >
               MME80(t). VENDA: RSI2(t) >= 90 e close(t) < MME80(t).
               Entrada a mercado na abertura de t+1. D = 1,0 x ATR14(t)
               ao tick, congelado. Alvo = entrada + D, stop = entrada -
               D (espelho na venda). Sem re-entrada enquanto RSI2 nao
               sair do extremo (< 10 ou > 90 continuo nao gera sinal
               novo — um sinal por excursao). Posicao aberta ignora
               sinal. Janela de entrada: t fecha entre 09:15 e 16:30.

    TAXA       A MEDIR (`eas-preco`, funil por clausula). Se < 1
               evento/pregao somando os dois lados, HORIZONTE estoura
               e a ficha volta ao desenho ANTES de congelar (7.4).

    EFEITO     p1 >= 0,56 contra p1 <= 0,50, meia-largura 3 pp ->
               n = 1.070 operacoes. Barra ambigua excluida e reportada.

    CUSTO      D x (2 p1 - 1) por operacao. Com D = ATR14, paga 11 pts
    MAXIMO     a p1 = 0,56 so' se ATR14 >= 92 pts — o `eas-preco`
               reporta p10/p50/p90 do ATR14 em pontos; se p50 < 92, a
               borda so' existe em dia de volatilidade acima da mediana
               e isso tem que estar na ficha antes de congelar.

    HORIZONTE  Historico: n vem do dump, nao do calendario. A X
               eventos/pregao, precisa de 1.070 / X pregoes de M15 — o
               `eas-preco` diz se o historico do grafico basta. Forward
               (F5): mesma conta, em calendario.

    CRITERIO   p1 >= 0,56 favoravel; p1 <= 0,50 contra; entre, inconclusivo.
               IC95 sempre. Secundario, so' reportado: P&L bruto em
               pontos por operacao (IC95) e fracao zerada por tempo.

    PARADA     Historico: UMA rodada de teste, depois de congelar, sobre
               amostra nao olhada na depuracao. Forward: olho em n/2 so'
               para defeito de especificacao (barras marcadas), decido
               em n. Perdas seguidas, dia ruim, circuit breaker NAO
               autorizam parar. Mudar qualquer numero acima reinicia.

**Porta de volume (declarada, NAO implementada):** `absorcao` na barra
de sinal — a feature que ja' existe em `flow.py` e que e' o "por que"
deste setup (exaustao = agressao que nao move preco). Entra como GATE
(`filtro_fluxo.absorcao_min`): so' entra se absorcao(t) >= limiar.
Hipotese nova quando entrar; contagem reinicia.

**Em pontos (preencher com o `eas-preco`):**

| item | valor |
|---|---|
| ATR14 p10 / p50 / p90 | a medir |
| D = ATR14 ao tick, p50 | a medir |
| eventos/pregao (compra / venda) | a medir |
| fracao de barras ambiguas (alvo e stop na mesma barra) | a medir |

**Fora desta ficha (v0):** saida por RSI cruzando 50 (regra classica do
QuantBrasil, alvo na maxima dos N anteriores) — variancia ilimitada,
estimador pior; fica como variante registrada. Estocastico, Bollinger,
volume. Duas posicoes.

**Referencia externa:** `quantbrasil backtests run ifr2 WINFUT
--timeframe M15` e' uma SEGUNDA implementacao do mesmo padrao, util
para conferir a deteccao de sinal em barras conhecidas. Conferencia de
formula; nao e' calibracao nem prova.

## 4. Ficha ORB (rascunho v0) — rompimento da abertura

    HIPOTESE   O range das duas primeiras barras M15 (09:00-09:30) do
               WIN concentra a decisao do dia: o primeiro rompimento
               dele, a favor do regime, continua ate' a barreira
               favoravel a 1 x amplitude do range antes de voltar a
               barreira desfavoravel, em mais de 50% das vezes.

    EVENTO     R_high / R_low = max/min das barras 09:00-09:15 e
               09:15-09:30. A = R_high - R_low. A partir de 09:30:
               ordem STOP de compra em R_high + 1 tick e de venda em
               R_low - 1 tick, OCO, valida ate' 12:00. Regime: so' o
               lado da MME80 fica armado (close(09:30) > MME80 arma
               so' a compra; < MME80 so' a venda). Executou uma,
               cancela a outra. D = A ao tick. Alvo = entrada + D, stop
               = entrada - D. UMA operacao por pregao. Sem entrada se A
               < 4 ticks (20 pts) — range degenerado.

    TAXA       <= 1 / pregao por construcao. A MEDIR: fracao de pregoes
               em que o rompimento acontece ate' 12:00.

    EFEITO     Mesmo estimador: p1 >= 0,56 vs <= 0,50 -> n = 1.070.
               **Problema conhecido:** a <= 1/pregao, n = 1.070 sao
               4+ anos de M15. Alternativas, a decidir ANTES de
               congelar: (a) efeito maior, p1 >= 0,60 -> n = 600 (~3
               anos); (b) aceitar o historico que o grafico tiver e
               declarar a meia-largura que ele permite (270 pregoes ->
               +-6 pp, so' enxerga p1 >= 0,60). Nenhuma das duas e'
               gratis; a (b) afirma menos e diz isso.

    CUSTO      D x (2 p1 - 1). Com D = A, o `eas-preco` reporta p50 de
    MAXIMO     A em pontos. Se p50(A) < 92 pts, mesma ressalva do IFR2.

    HORIZONTE  = pregoes de historico disponiveis. E' a ficha com MAIOR
               risco de nao fechar; se o grafico nao tiver >= 3 anos de
               M15, ela vai para forward em F5 com a meia-largura que o
               historico deu, e diz isso na propria ficha.

    CRITERIO   como IFR2.
    PARADA     como IFR2.

**Porta de volume:** volume agredido acumulado no rompimento vs. mediana
do horario (o `perfil-volume-horario` ja' existe): so' entra se a barra
de rompimento tem agressao acima da mediana da faixa 09:30-10:00.

**Em pontos:** amplitude A p10/p50/p90 — a medir. Fracao de pregoes com
rompimento ate' 12:00 — a medir.

**Fora da v0:** range de 09:00-10:00 (outra hipotese), segundo
rompimento, trailing.

## 5. Ficha 123 (rascunho v0) — continuacao em pullback

    HIPOTESE   Um fundo de 3 barras M15 (a 2a com a menor minima), a
               favor do regime, e' pullback numa tendencia; o rompimento
               da maxima da 3a barra continua ate' a barreira favoravel
               a 1 x (entrada - stop) antes de voltar ao stop, em mais
               de 50% das vezes. Espelho na venda.

    EVENTO     Barras t-2, t-1, t fechadas. COMPRA: low(t-1) < low(t-2)
               e low(t-1) < low(t) (a 2a e' a menor minima; empate NAO
               forma padrao). Regime: close(t) > MME80(t). Ordem STOP
               de compra em high(t) + 1 tick, valida SO' durante t+1;
               nao executou, cancela. Stop = low(t-1) - 1 tick. D =
               entrada - stop, ao tick. Alvo = entrada + D. VENDA:
               espelho (high(t-1) maior maxima, stop de venda em low(t)
               - 1 tick, stop em high(t-1) + 1 tick). Sem entrada se D
               < 4 ticks. Janela: t fecha entre 09:30 e 16:30.

    TAXA       A MEDIR. O padrao bruto e' frequente; regime + execucao
               em t+1 filtram. Funil por clausula obrigatorio.

    EFEITO     p1 >= 0,56 vs <= 0,50 -> n = 1.070.

    CUSTO      D varia por sinal (e' geometrico, nao ATR). `eas-preco`
    MAXIMO     reporta p10/p50/p90 de D em pontos; se p50 < 92, mesma
               ressalva. Sinais com D pequeno sao os que menos pagam
               custo — mas o corte em D e' calibracao, entao fica em 4
               ticks fixo (degenerado), nao ajustado.

    HORIZONTE  1.070 / (eventos por pregao) pregoes de historico.
    CRITERIO   como IFR2.
    PARADA     como IFR2.

**Porta de volume:** agressao/delta na barra t+1 de rompimento — "so'
entro se o rompimento veio com agressor". E' a mesma porta do ORB;
implementa-se uma vez.

**Em pontos:** D p10/p50/p90 — a medir. Eventos/pregao com e sem regime
— a medir. Fracao com Inside Bar (info) — a medir.

**Fora da v0:** filtro Inside Bar (a pagina do QuantBrasil o oferece;
fica registrado, o funil reporta quantos sinais ele deixaria passar);
filtro Eden completo (MME8 e MME80 subindo) — reportado como info;
alvo por amplitude dos 3 candles (assimetrico, variancia maior).

**Referencia externa:** `quantbrasil.com.br/estrategias/123-de-compra/`
e `backtests run` do QuantBrasil com o setup 123 em WINFUT M15 —
segunda implementacao para conferir deteccao. So' isso.

## 6. A porta de volume — interface, nao conteudo

O que existe desde o dia 1 (em F4, quando o EA de preco for escrito):

```yaml
# ea_ifr2.yaml (exemplo; campos exatos definidos em F4)
tipo_barra: tempo        # novo: "tempo" (M15) ou "volume" (o atual)
periodo_barra_s: 900
filtro_fluxo: null       # AUSENTE = sem filtro. extra="forbid".
```

`filtro_fluxo` e' um bloco opcional, `None` por default, e o EA tem UM
ponto de gate (`GateDeFluxo.permite(barra) -> bool`) entre "sinal de
preco disparou" e "manda ordem". `SemFiltro` e' a implementacao
default. Quando uma feature de fluxo passar pela disciplina, ela vira
uma implementacao do gate e um bloco preenchido — e o carimbo de versao
reinicia a contagem daquele EA.

Por que a porta e' um GATE e nao um termo do sinal: gate mantem o sinal
de preco identico (comparavel com o historico); termo mudaria a
hipotese inteira.

## 7. O que este documento NAO autoriza

- Rodar p1 sobre o dump antes de a ficha estar congelada.
- Escolher entre variantes (Eden vs MME80, Inside Bar sim/nao) olhando
  o funil — o funil MEDE taxa, nao escolhe. A variante da v0 ja' esta'
  escrita acima.
- Ajustar D (1,0 x ATR, 1,0 x A) — sao numeros declarados, nao
  calibrados. Mudar = ficha nova.
- Preencher `filtro_fluxo` em qualquer EA sem ficha propria.
