# EAs de PRECO — linha paralela enquanto o tape acumula (2026-09-13)

Estado (2026-09-14): **IFR2 FECHADA — CONTRA (3.3).** p1 = 0,492 IC95
[0,472; 0,512] em n = 2.452 (2023-2025); replicacao 2026 0,482. Sem
borda a custo zero. **ORB em F1**: funil por pregao entregue
(`eas-preco --ficha orb`), ficha continua em RASCUNHO ate' a TAXA ser
medida. 123 em rascunho.

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

## 3. Ficha IFR2 — v1 (2026-09-13, a congelar) — retorno a` media em extremo

### 3.0 O que o primeiro dump mediu (v0 -> v1)

`profit-tape eas-preco` sobre `dump_preco_15m.txt`: 6.580 barras, 174
pregoes (02/01–11/09/2026), 1 bloco contiguo, 37,8 barras/pregao.

**Equivalencia (com o verificador da v2.59, que tinha bug de
aquecimento — ver 3.0b):** ATR14 = **SMA do TrueRange** (dif 0,0, igual
ao Bollinger); MME8 **semeada no close** (0,45 pt); RSI = **Wilder**
(mediana 0,0; `rsi_ewm` identico — so' a semente difere); MME80 mediana
0,0. Os `dif_max` de 8 (RSI) e 323 (MME80) sao semente no inicio do
bloco, medidos ANTES do aquecimento por bug do verificador. A v2.60
corrige e imprime ONDE esta' o `dif_max`; a confirmacao final e' com a
rodada nova.

**Em pontos:** ATR14 p10/p50/p90 = 258 / 465 / 742. Com K = 1, D nos
sinais = 265 / 510 / 806. O stop catastrofico do `risco.py` e' **500 pts**
(2% de R$5.000 a R$0,20) — com K = 1 o seguro de cauda dispararia antes
do stop da estrategia em mais da metade dos sinais, e o teste mediria o
`risco.py`, nao o IFR2. **Decisao: K = 0,5** -> D mediano ~255 pts
(R$51/contrato), p90 ~400, dentro dos 500. E 255 e' o stop mediano da
Rota B: "so' arrisco o que ja' arrisco". Incompatibilidade de mecanismo,
nao calibracao — nenhum resultado foi olhado.

**Funil (7.4), compra + venda por pregao:**

| clausula | n | por pregao |
|---|---|---|
| extremo (RSI2 <= 10 / >= 90) | 1.887 | 10,85 |
| 1 sinal por excursao | 856 | 4,92 |
| + regime MME80 | 263 | **1,51** (corta 70%) |
| + janela 09:15–16:30 | 190 | 1,09 |
| (info) Eden | 1 | 0,01 |

A 1,09/pregao, n = 1.070 sao ~980 pregoes — 4+ anos. E' o caso literal
do 7.4: a clausula de regime derruba 3,3x o calendario. **Decisao (B), do
operador: o regime SAI da clausula e vira ESTRATIFICACAO reportada.** A
hipotese passa a afirmar menos ("exaustao de curto prazo, em qualquer
tendencia"); o primario e' o total; o estrato e' reportado, nunca
escolhido depois. Eden morre como variante: RSI2 em extremo e MME8
subindo nao coexistem (0 e 1 sinais).

**Estimador:** 190 sinais (v0): 89,5% resolvidos, **1,1% ambiguos**
(alvo e stop na mesma barra — o estimador binario serve), 9,5% zerados
por tempo (devem cair com D menor). Duracao ate' resolver: p50 4
barras (1h), p90 14.

### 3.0b Bug do verificador (7.3), corrigido na v2.60

`campo.startswith("mme8")` casava tambem com `mme80`: a MME80 foi
comparada a partir da barra 24 em vez da 240 (`n=6556` denunciou), e o
RSI nao tinha aquecimento. O verificador dizia NAO BATE com mediana 0,0
— o proprio sintoma. Correcao: aquecimento por chave EXATA, 5 x periodo
para as MMEs (sobra 0,005% da semente; com 3 x sobrava 0,26%, que de
uma semente 2.000 pts fora ainda e' 5 pts), 10 x periodo para o RSI;
`dif_max_em` imprime dia/hora/posicao no bloco. Teste de regressao
reproduz o caso (semente 2.000 pts fora, mesma formula) e exige BATE.

### 3.1 A ficha

    HIPOTESE   No WIN em M15, RSI(2) em extremo (<= 10 na compra, >= 90
               na venda) e' exaustao de curto prazo; entrando a mercado
               na abertura da barra seguinte, a barreira favoravel a
               0,5 x ATR14 bate antes da desfavoravel em mais de 50%
               das vezes. Em qualquer tendencia (o regime e' estrato).

    EVENTO     Barra M15 t fechada. COMPRA: RSI2(t) <= 10. VENDA:
               RSI2(t) >= 90. Um sinal por excursao (t-1 fora do
               extremo). Entrada a mercado na abertura de t+1 (t+1 no
               mesmo pregao). D = 0,5 x ATR14(t) ao tick, congelado;
               ATR14 = SMA14 do TrueRange, RSI = Wilder, indicadores
               continuos entre pregoes. Alvo = entrada + D, stop =
               entrada - D (espelho na venda). Posicao aberta ignora
               sinal. Janela: t fecha entre 09:15 e 16:30. Zeragem
               17:30.

    TAXA       MEDIDA (2026, 174 pregoes): ~4,9 sinais/pregao antes da
               janela; ~3,5/pregao esperado com a janela (a confirmar
               na rodada v2.60 — a v0 media 190/263 = 72% passando na
               janela). Duracao p50 4 barras: sobreposicao rara.

    EFEITO     p1 >= 0,56 contra p1 <= 0,50, meia-largura 3 pp -> n =
               1.070 operacoes. Barra ambigua (1,1% na v0) excluida e
               reportada; zerada por tempo excluida e reportada.

    CUSTO      D x (2 p1 - 1). Com D mediano ~255 pts, o p1 que EMPATA
    MAXIMO     11 pts e' 0,52 — o custo nao decide nada aqui. Alerta no
               EA: `custo_pontos_estimado` > D x (2 x 0,56 - 1) = ~31
               pts -> avisa e nao liga.

    HORIZONTE  Historico: a ~3,5/pregao, n = 1.070 sao ~305 pregoes.
               2026 (174) da' n ~600, meia-largura +-4 pp. Com 2025 no
               grafico (+~250 pregoes), n ~1.500: fecha com folga.
               Forward (F5): ~3,5/pregao -> n = 1.070 em ~14 meses; a
               conta em calendario e' do F5, nao daqui.

    CRITERIO   p1 >= 0,56 favoravel; p1 <= 0,50 contra; entre,
               inconclusivo. IC95 sempre. Reportados, nao decisorios:
               p1 por estrato (a favor / contra a MME80, compra /
               venda), P&L bruto em pontos por operacao (IC95), fracao
               ambigua e zerada por tempo.

    PARADA     Historico: UMA rodada de teste, depois de congelar.
               Amostra de DEPURACAO = os 20 pregoes mais recentes do
               dump (barras marcadas, olhadas uma a uma); TESTE = o
               resto, nao olhado na depuracao. Forward: olho em n/2 so'
               para defeito de especificacao, decido em n. Perdas
               seguidas, dia ruim, circuit breaker NAO autorizam parar.
               Mudar qualquer numero acima reinicia a contagem.

**Porta de volume (declarada, NAO implementada):** `absorcao` na barra
de sinal — a feature que ja' existe em `flow.py` e que e' o "por que"
deste setup. Entra como GATE (`filtro_fluxo.absorcao_min`). Hipotese
nova quando entrar; contagem reinicia.

**Em pontos (medido, K = 1 na v0; K = 0,5 na v1 = metade):**

| item | v0 (K=1) | v1 (K=0,5) |
|---|---|---|
| ATR14 p10 / p50 / p90 | 258 / 465 / 742 | idem |
| D nos sinais p10 / p50 / p90 | 265 / 510 / 806 | ~130 / ~255 / ~400 |
| stop catastrofico do risco.py | 500 | 500 |
| fracao ambigua | 1,1% | a medir (v2.60) |
| eventos/pregao (com janela) | 1,09 (com regime) | ~3,5 (sem regime, a medir) |

**Fora desta ficha (v1):** regime como clausula (v0, descartado por
7.4); Eden (0 sinais, morto); saida por RSI cruzando 50 / maxima dos N
anteriores (variancia ilimitada); estocastico, Bollinger, volume; duas
posicoes; K diferente de 0,5.

**Referencia externa:** `quantbrasil backtests run ifr2 WINFUT
--timeframe M15` e' uma SEGUNDA implementacao do mesmo padrao, util
para conferir a deteccao de sinal em barras conhecidas. Conferencia de
formula; nao e' calibracao nem prova.

### 3.0c O que os dois dumps mediram com a v2.60 (2026-09-13, noite)

| | 2026 (dump 1) | 2023–2025 (dump 2) |
|---|---|---|
| pregoes / barras | 174 / 6.580 | 749 / 28.083 |
| equivalencia | RSI Wilder, MME8/MME80 no close, ATR SMA, TR — **todos BATEM** (dif_max <= 0,03 fora do aquecimento) | idem (dif_max <= 0,12) |
| ATR14 p10/p50/p90 | 258 / 465 / 742 | 213 / 331 / 523 |
| D = 0,5 x ATR14 p10/p50/p90 | 145 / 245 / 375 | 120 / 175 / 265 |
| sinais/pregao (compra + venda) | **3,51** | **3,54** |
| estrato a favor / contra MME80 | 31% / 69% | 31% / 69% |
| ambigua / por tempo | **7,4%** / 0 | **7,4%** / 0 |
| duracao ate' resolver p50 / p90 | 1 / 3 barras | 1 / 3 barras |
| p1 que empata 11 pts | 0,522 | 0,531 |

**Estacionariedade do evento:** taxa e estratos identicos nos dois
periodos, com ATR mediano 40% diferente. A clausula nao depende do
regime de volatilidade.

**Mecanismo, dito em voz alta (regra 0):** com D = metade do ATR, a
mediana resolve NA BARRA DE ENTRADA. Na pratica a hipotese e' "depois
de um extremo de RSI2, a primeira excursao de 0,5 x ATR14 da barra
seguinte vai a favor". E' um mecanismo de exaustao imediata, nao de
reversao que se desenvolve em varias barras. A HIPOTESE abaixo diz isso.

**Os 7,4% ambiguos** sao as barras largas; excluir nao e' neutro. Abaixo
do corte de 10%, o estimador serve — com a mitigacao de conferir, na
amostra de DEPURACAO (que tem tape a partir de 24/07/2026), se os
ambiguos pendem para um lado. `eas-preco-teste` lista-os
(`sinais_<amostra>.csv`, classe=ambigua) com dia, hora e barra.

### 3.2 FICHA CONGELADA — IFR2 M15 (2026-09-13, `entregue-v2.61`)

    HIPOTESE   No WIN em M15, RSI(2) em extremo (<= 10 / >= 90) e'
               exaustao imediata: entrando a mercado na abertura da
               barra seguinte, a primeira excursao de 0,5 x ATR14 vai a
               favor (barreira favoravel antes da desfavoravel) em mais
               de 50% das vezes, em qualquer tendencia.

    EVENTO     Barra M15 t fechada, WINFUT, indicadores continuos entre
               pregoes. COMPRA: RSI2(t) <= 10 (Wilder). VENDA: RSI2(t)
               >= 90. Um sinal por excursao (t-1 fora do extremo).
               Janela: t fecha entre 09:15 e 16:30; t+1 no mesmo
               pregao. Entrada = open(t+1). D = 0,5 x ATR14(t) ao tick
               (meio-tick sobe), ATR14 = SMA14 do TrueRange. Alvo =
               entrada + D, stop = entrada - D (espelho na venda).
               Resolucao: primeira barra >= t+1 do mesmo dia em que
               alvo ou stop cabem em [low, high]; os dois na mesma
               barra = AMBIGUA (excluida, reportada); dia acaba sem
               tocar = POR TEMPO (excluida, reportada). Posicao aberta
               ignora sinal (no historico: sinais sao independentes,
               duracao p50 = 1 barra).

    TAXA       MEDIDA: 3,51 (2026) e 3,54 (2023-25) sinais/pregao.

    EFEITO     p1 >= 0,56 contra p1 <= 0,50; meia-largura 3 pp -> n =
               1.070 resolvidas. Nula a custo zero = 0,50 (barreiras
               simetricas).

    CUSTO      D x (2 p1 - 1). D mediano 175-245 pts: p1 de empate
    MAXIMO     0,52-0,53. Alerta no EA: custo_pontos_estimado > D x 0,12
               -> avisa e nao liga.

    AMOSTRAS   Por DATA, fixadas:
               TESTE       2023-01-01 .. 2025-12-31  (749 pregoes,
                           ~2.650 sinais, +-1,9 pp) -- PRIMARIO, UMA
                           rodada. `eas-preco-teste --amostra teste`
                           recusa a segunda.
               REPLICACAO  2026-01-01 .. 2026-08-13  (~154 pregoes,
                           ~540 sinais) -- reportada DEPOIS do
                           primario, sem veto sobre ele.
               DEPURACAO   2026-08-14 em diante (~20 pregoes) -- barras
                           olhadas uma a uma; ambiguas conferidas no
                           tape; NAO interpretavel. Corrigir formula
                           aqui e' permitido; ajustar numero, nao.

    HORIZONTE  Historico: fechado (n >> 1.070). Forward (F5): a
               ~3,5/pregao, n = 1.070 em ~305 pregoes (~14 meses); e'
               conta do F5, com a mesma ficha.

    CRITERIO   Sobre o TESTE: p1 >= 0,56 FAVORAVEL; p1 <= 0,50 CONTRA;
               entre, INCONCLUSIVO. IC95 de Wilson sempre. Reportados,
               sem veredito proprio: p1 por estrato (a favor / contra a
               MME80; compra / venda), P&L bruto e liquido em pontos
               por operacao (IC95), fracao ambigua e por tempo, e a
               tendencia das ambiguas no tape (depuracao).

    PARADA     Ordem obrigatoria: (1) DEPURACAO -- barras olhadas,
               formula conferida, ambiguas no tape; (2) TESTE -- uma
               rodada; (3) REPLICACAO -- reportada. Perdas seguidas,
               dia ruim, circuit breaker NAO autorizam nada. Mudar
               qualquer numero acima muda `hash_ficha` e reinicia:
               resultados com hash diferente nunca sao somados.

    CARIMBO    `eas-preco-teste` grava `git describe --tags` e o hash
               sha256 (12) dos parametros da ficha em cada saida.

**Porta de volume (declarada, NAO implementada):** `absorcao` na barra
de sinal, como GATE. Hipotese nova; contagem reinicia.

**O que a ficha congelada NAO autoriza:** rodar `teste` antes da
depuracao; rodar `teste` duas vezes (o `--forcar` exige motivo escrito e
so' vale para bug que faz o codigo passar a fazer o que a ficha ja'
dizia); escolher estrato depois; mudar K, limiares, janela ou datas das
amostras.

### 3.3 FECHAMENTO — CONTRA (2026-09-14, carimbo `entregue-v2.61` / `449b012649c4`)

Rodado na ordem da ficha: depuracao -> teste -> replicacao.

| amostra | pregoes | sinais | resolvidas | ambiguas | p1 | IC95 | P&L bruto/op | veredito |
|---|---|---|---|---|---|---|---|---|
| DEPURACAO (14/08–11/09/2026) | 20 | 77 | 73 | 5,2% | 0,466 | [0,356; 0,579] | -25,8 | nao interpretavel |
| **TESTE (2023–2025)** | 749 | 2.648 | 2.452 | 7,4% | **0,492** | **[0,472; 0,512]** | -4,8 | **CONTRA** |
| REPLICACAO (01/01–13/08/2026) | 154 | 534 | 492 | 7,7% | 0,482 | [0,438; 0,526] | -6,9 | CONTRA (reportada) |

Estratos no teste (reportados): a favor da MME80 0,505 [0,470; 0,540];
contra 0,486; compra 0,499; venda 0,485. Nenhum estrato tem IC fora
de 0,50, e o unico que passa de 0,50 no teste (a favor) da' 0,32 na
depuracao e 0,53 na replicacao — ruido.

**Por que e' CONTRA sem ambiguidade:** o IC inteiro do teste fica
abaixo de 0,50, e o teto de 0,512 nem paga o custo (D mediano 175 pts
x 0,024 = 4 pts brutos contra 11). Nao ha' borda a custo NENHUM. E' o
mesmo tipo de fechamento do scalp de Bollinger (retorno): nulo, nao
negativo.

**O que o fechamento assume:** que a formula esta' certa — os 77 sinais
da depuracao conferidos no grafico (barra de sinal, entrada, alvo,
stop). Defeito de FORMULA reabriria; defeito de numero, nao.

**O que NAO se faz agora:** K = 1, regime de volta a` clausula, RSI2 <=
5, saida por RSI 50. Cada um e' hipotese nova, e 2023-2025 ja' foi
QUEIMADO por esta. Qualquer variante futura precisa de amostra que
este teste nao tocou (2022 para tras, ou forward), com ficha propria.

**O que a linha de preco entregou aqui:** hipotese -> funil ->
congelamento -> depuracao -> teste -> replicacao, numa noite, sobre 923
pregoes, sem gastar um dia de calendario. Um forward disso levaria ~14
meses para dizer o que o historico disse em dois minutos. Esse e' o
argumento da linha: **reprovar rapido**.

## 4. Ficha ORB (rascunho v0) — rompimento da abertura

> **F1 (2026-09-14, `entregue-v2.62`):** `profit-tape eas-preco <dump>
> --ficha orb` faz o funil POR PREGAO (range presente -> A >= 20 pts ->
> rompeu ate' 11:45 -> lado da MME80 rompeu = SINAL), reporta o custo
> do regime ("o outro lado rompeu antes"), A e D em pontos, hora do
> gatilho, classes de resolucao e fracao ambigua. Sem p1.
>
> **Ambiguidade especifica do ORB, decidida antes de medir:** na barra
> do GATILHO o stop (= R_low + tick na compra) fica dentro do range, e
> o OHLC nao diz se foi tocado antes ou depois do rompimento. Stop
> tocado na barra do gatilho = AMBIGUA sempre; alvo, nao (esta' alem da
> entrada). Se a fracao passar de 10%, o ORB so' se valida com o tape
> (e o tape so' tem 2026 a partir de 24/07). E' o risco principal da
> ficha, junto com o horizonte — os dois saem do mesmo funil.


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
- Escolher entre variantes olhando RESULTADO. Olhar TAXA para afrouxar
  uma clausula restritiva demais e' o 7.4 e e' permitido ANTES de
  congelar — foi o que a v1 do IFR2 fez com o regime, e esta' escrito.
- Ajustar D depois de congelar. Antes, so' por incompatibilidade de
  mecanismo (foi o caso: K = 1 colidia com o stop catastrofico) —
  nunca por p1.
- Preencher `filtro_fluxo` em qualquer EA sem ficha propria.
- Rodar `eas-preco-teste --amostra teste` antes da depuracao, ou mais
  de uma vez.
