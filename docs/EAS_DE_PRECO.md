# EAs de PRECO — linha paralela enquanto o tape acumula (2026-09-13)

Estado (2026-09-14, noite): **IFR2 FECHADA (familia CONTRA). ORB FECHADO
— CONTRA no combinado de 10 anos (4.5).** **123: borda PEQUENA e REAL (5.3)** — p1 = 0,5285 IC95 [0,515;
0,542] em 5.444, onze de doze anos acima de 0,50; abaixo do 0,56
operacional. **Desenho de F5 em 5.4**: o 123 vai para forward como
PORTADOR da estrutura multi-EA, medindo EXECUCAO, e acumulando a amostra
da porta de volume.

**Regra da linha inteira (2026-09-14, apos erro meu, duas vezes):
capital NUNCA restringe uma ficha.** E' a decisao 4.9 do
`EA_ARQUITETURA.md` — risco e' informativo. O funil CALCULA o capital
recomendado por contrato (D x R$0,20 / 2%) e apresenta; o operador
decide. D vem do mecanismo, nunca do stop catastrofico.

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
sinais = 265 / 510 / 806.

> **ERRO, corrigido em 2026-09-14.** Aqui eu decidi K = 0,5 porque D
> passava do stop catastrofico de 500 pts do `risco.py`. Isso contraria
> a decisao 4.9 do `EA_ARQUITETURA.md` (risco e' INFORMATIVO, nunca
> limita a estrategia), que o operador ja' tinha tomado. O trial 1 foi
> rodado com K = 0,5 e vale para K = 0,5. O trial 2 (3.4) testa K = 1,
> como a ficha v0 pedia. O que o sistema faz com o capital e' CALCULAR
> e reportar (D x R$0,20 / 2%: K = 1 -> ~R$5.100 por contrato no D
> mediano de 2026).

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

### 3.4 TRIAL 2 — K = 1 (declarado 2026-09-14, ANTES de rodar; `entregue-v2.63`)

**Por que existe:** o K = 0,5 do trial 1 nasceu de uma premissa errada
(3.0c). A ficha como foi desenhada (v0, K = 1) nunca foi testada. O
funil de K = 1 ja' foi medido na v0 (2026): 9,5% por tempo, 1,1%
ambiguo, duracao maior — mecanismo diferente do trial 1: reversao que se
DESENVOLVE, nao excursao imediata.

**O que muda em relacao a 3.2:** so' K (0,5 -> 1,0). Regime continua
estrato; janela, excursao, amostras, ordem, tudo identico. `hash_ficha`
muda; resultados dos dois trials nunca se somam.

**O preco de usar 2023-2025 pela segunda vez:** IC de **97,5%**
(Bonferroni, 0,05 / 2 trials) em vez de 95%, e FAVORAVEL exige, alem de
p1 >= 0,56, que o limite inferior desse IC fique acima de 0,50. CONTRA
e INCONCLUSIVO como antes. `eas-preco-teste` ja' aplica (`TRIAL = 2`).

**O que este trial NAO autoriza:** um trial 3. Se K = 1 der CONTRA ou
INCONCLUSIVO, a familia IFR2 em M15 fecha sobre este historico —
qualquer variante futura precisa de amostra nova (2022 para tras, ou
forward).

**Ordem (a mesma):** depuracao (14/08+) -> teste (2023-25, `--saida`
NOVA, ex.: `eas_preco_teste_k1`) -> replicacao (2026 ate' 13/08).

### 3.5 FECHAMENTO DO TRIAL 2 — CONTRA (2026-09-14, `entregue-v2.63` / `a0ee1342c69e`)

| amostra | resolvidas | ambiguas | por tempo | p1 | IC 97,5% | P&L bruto/op |
|---|---|---|---|---|---|---|
| DEPURACAO | 68 | 0 | 9 | 0,412 | [0,289; 0,547] | -94 |
| **TESTE 2023-25** | 2.478 | 0,9% | 5,6% | **0,486** | **[0,464; 0,509]** | -9,5 |
| REPLICACAO 2026 | 491 | 0,4% | 7,7% | 0,479 | [0,429; 0,529] | -13 |

Estratos: nenhum com IC fora de 0,50 (a favor da MME80 no teste: 0,509
[0,468; 0,549]). Com K = 1 a ambiguidade cai a 0,9% e a duracao sobe —
mecanismo "reversao que se desenvolve" medido limpo. E' nulo tambem.

**A familia IFR2 em M15 esta' FECHADA sobre este historico.** Dois
trials, dois CONTRA, o segundo com criterio deflacionado. Nao ha' trial
3. Qualquer variante (RSI <= 5, saida por RSI 50, outro timeframe) e'
familia nova, com amostra que estes dois nao tocaram.

## 4. Ficha ORB — CONGELADA (2026-09-14, 4.2) — rompimento da abertura

### 4.0 O que o funil v0 mediu (`eas-preco --ficha orb`, `entregue-v2.62`)

| | 2023–2025 | 2026 |
|---|---|---|
| pregoes | 749 | 174 |
| range presente / A >= 20 pts / rompeu ate' 11:45 | 99,5% / 99,5% / **98,5%** | 98,9% / 98,9% / 97,7% |
| lado da MME80 rompeu (v0, regime na clausula) | 74,1% | 71,8% |
| "o outro lado rompeu antes" (custo do regime) | 12,7% dos sinais | 12,1% |
| A p10/p50/p90 (pts) | 474 / 726 / 1.198 | 813 / **1.333** / 2.067 |
| gatilho p10/p50/p90 (HHMM) | 09:30 / 09:30 / 10:30 | 09:30 / 09:45 / 10:39 |
| classes: resolvida / por tempo / ambigua | 82% / 11% / 6,8% | 75% / 22% / 2,4% |
| barras ate' resolver p50 / p90 | 5 / 32 | 7 / 34 |

**Leituras:** (1) o rompimento e' quase certo (98%) e mediano na
PRIMEIRA barra depois do range — a aposta e' "a direcao da excursao de
A a partir do rompimento"; (2) o regime custa 25% dos pregoes e em 12%
dos sinais faz entrar depois de um rompimento contrario ja' falhado —
caso 7.4, **decisao do operador: regime vira ESTRATO**; (3) A dobrou de
2023-25 para 2026 — D = A acompanha a vol, e o capital recomendado
acompanha D (2026: ~R$13.250 por contrato no p50, ~R$20.300 no p90;
informativo, 4.9); (4) 22% por tempo em 2026 com D = 1.333 pts e' o
dia nao andar 1 range depois do rompimento — reportado, nao decisivo;
(5) ambiguidade 6,8% / 2,4%: o estimador serve; a regra "stop na barra
do gatilho = ambigua" nao estourou.

**Erro corrigido:** propus D = 0,25 x A para caber no stop catastrofico.
Contra 4.9. D = A, como a ficha v0 diz.

### 4.0b Funil v1 remedido (regime = estrato, `entregue-v2.63`)

| | 2023–2025 | 2026 |
|---|---|---|
| SINAL (primeiro rompimento, um lado so' na barra) | **722 / 749 = 0,964** | **170 / 174 = 0,977** |
| gatilho dos dois lados na mesma barra (fora) | 16 (2,1%) | 0 |
| estrato compra / venda | 49% / 51% | 48% / 52% |
| estrato a favor / contra MME80 | 59% / 41% | 60% / 40% |
| classes: resolvida / por tempo / ambigua | 636 / 84 / **2** | 130 / 40 / **0** |
| por tempo (fracao) | 11,6% | **23,5%** |
| gatilho p50 / p90 | 09:30 / 10:15 | 09:30 / 10:15 |
| capital recomendado p50 / p90 (R$/contrato, informativo) | 7.250 / 11.950 | 13.275 / 20.650 |

Ambiguidade praticamente zero (a regra "stop na barra do gatilho" nao
custa nada com D = A: o stop fica a uma amplitude inteira). O que pesa
e' o **por tempo**: 12–24% dos pregoes nao andam uma amplitude para
nenhum lado depois do rompimento. Excluir do p1 (binario) e' correto;
excluir sem dizer o que valeram, nao — o `eas-preco-teste --ficha orb`
reporta o P&L medio dessas operacoes na zeragem de 17:30 (close da
ultima barra − entrada), fora do p1 e dentro do P&L reportado.

Resolvidas: 636 + 130 = **766** -> meia-largura +-3,5 pp no total;
+-3,9 pp so' no teste (636). Declarado.

### 4.1 A ficha (texto da v1, congelado em 4.2 sem alteracao)

    HIPOTESE   O range das duas primeiras barras M15 do WIN (09:00-09:30)
               concentra a decisao do dia: o primeiro rompimento dele,
               para qualquer lado, continua por mais uma amplitude do
               range antes de voltar a amplitude oposta, em mais de 50%
               das vezes.

    EVENTO     R_high / R_low = max/min das barras 09:00 e 09:15; A =
               R_high - R_low >= 20 pts. Das 09:30 ate' a barra 11:45
               inclusive: ordem STOP de compra em R_high + tick e de
               venda em R_low - tick, OCO. A primeira barra que toca um
               dos niveis e' o gatilho; se toca os DOIS na mesma barra,
               gatilho ambiguo, pregao fora (reportado). Entrada = nivel
               rompido. D = A ao tick. Alvo = entrada + D, stop = entrada
               - D (espelho na venda). UMA operacao por pregao. Regime
               (close(09:15) vs MME80) = ESTRATO reportado. Resolucao:
               a partir da barra do gatilho, inclusive; stop tocado NA
               barra do gatilho = AMBIGUA (o OHLC nao ordena contra o
               rompimento); alvo tocado nela = favoravel; depois, a
               primeira barra que toca alvo ou stop (os dois = ambigua);
               17:30 sem tocar = POR TEMPO. Ambigua e por tempo:
               excluidas do p1, reportadas.

    TAXA       A MEDIR com o regime como estrato. Esperado ~0,95-0,98
               por pregao (98% rompem; menos os gatilhos ambiguos).

    EFEITO     p1 >= 0,56 contra <= 0,50. Com ~900 sinais (923 pregoes)
               a meia-largura e' ~+-3,3 pp: um pouco acima dos 3 pp.
               Aceito, declarado.

    CUSTO      D x (2 p1 - 1). D mediano 725-1.325 pts: p1 de empate
    MAXIMO     0,504-0,508. Irrelevante.

    CAPITAL    Reportado, nunca limitante (4.9): D x R$0,20 / 2%.
               2023-25 p50 ~R$7.250; 2026 p50 ~R$13.250, p90 ~R$20.300.

    AMOSTRAS   As mesmas por data: TESTE 2023-25 (primario, uma
               rodada); REPLICACAO 2026 ate' 13/08; DEPURACAO 14/08+.
               (O ORB e' familia DIFERENTE do IFR2: trial 1 nesta
               amostra para esta familia.)

    HORIZONTE  Historico: ~900 sinais. Forward: ~1 op/pregao -> n =
               1.070 em ~4 anos. O forward do ORB NAO fecha sozinho: se
               for para F5, e' com o n do historico como base e o
               forward como replicacao continua, declarado assim.

    CRITERIO   como IFR2 (p1 >= 0,56 favoravel; <= 0,50 contra; IC95
               sempre); estratos (a favor/contra MME80, compra/venda)
               reportados, sem veredito.

    PARADA     depuracao -> teste -> replicacao; nada autoriza parar
               antes; qualquer numero mudado reinicia.

**Porta de volume:** agressao acumulada na barra do gatilho vs. mediana
da faixa 09:30-10:00 (`perfil-volume-horario`), como gate.

**Fora da v1:** range de 09:00-10:00; segundo rompimento; trailing;
regime na clausula (v0, medido e descartado por 7.4); D diferente de A.

### 4.2 CONGELAMENTO (2026-09-14, `entregue-v2.64`)

A ficha 4.1 congela como esta', com estes numeros preenchidos:

    TAXA       0,964 (2023-25) / 0,977 (2026) sinais por pregao.
    EFEITO     +-3,9 pp no teste (636 resolvidas); +-3,5 pp somando a
               replicacao (766). Enxerga p1 >= 0,56 contra 0,50 com
               folga; nao enxerga 0,53.
    POR TEMPO  11,6% / 23,5%. Fora do p1; P&L na zeragem reportado.
    AMBIGUA    0,3% / 0%.
    TRIAL      1 da familia ORB nesta amostra. IC 95%.
    CARIMBO    hash da ficha em `resultado_orb_<amostra>.json`.

Ordem: DEPURACAO (dias >= 14/08/2026) -> TESTE (2023-25, uma rodada)
-> REPLICACAO (2026 ate' 13/08). Mesmos dumps do IFR2.

**O que a ficha NAO autoriza:** escolher o estrato a favor da MME80
depois (foi clausula na v0, virou estrato por 7.4, e o funil v0 ja'
mostrou o que ele custa); D diferente de A; janela diferente; trial 2
sem declaracao previa e criterio deflacionado.

### 4.3 TESTE e REPLICACAO — INCONCLUSIVO (2026-09-14, `entregue-v2.64` / `7ae066bb3efb`)

| amostra | pregoes | sinais | resolvidas | por tempo (zeragem) | p1 | IC95 | P&L bruto/op | veredito |
|---|---|---|---|---|---|---|---|---|
| DEPURACAO | 20 | 20 | 15 | 5 (-347) | 0,600 | [0,36; 0,80] | +324 | nao interpretavel |
| **TESTE 2023-25** | 749 | 722 | 636 | 84 (-47) | **0,524** | **[0,485; 0,562]** | +37 [-26; +100] | **INCONCLUSIVO** |
| REPLICACAO 2026 | 154 | 149 | 115 | 34 (-10) | 0,496 | [0,406; 0,586] | -9 | CONTRA (reportada) |
| combinado | 903 | 871 | 751 | 118 | 0,519 | ~[0,483; 0,555] | | inconclusivo |

Estratos no teste: a favor MME80 0,503; **contra 0,557 [0,494; 0,617]**;
compra 0,544; venda 0,503. Na replicacao o "contra" virou **0,442**
(-153 pts/op). Caso de manual: estrato que brilha numa amostra e apaga
na outra. Ficou escrito antes que ele nao decidia — e nao decidiu.

**Leitura:** o primeiro candidato da linha que nao morreu. Se o ORB tem
borda, ela esta' entre 0 e ~5 pp — abaixo do 0,56 declarado como
minimo que vale operar. Forward a ~1 op/pregao nao resolve (4 anos).

### 4.4 REPLICACAO 2 — declarada ANTES de rodar (2026-09-14, `entregue-v2.65`)

O grafico carrega desde out/2015. **Todo o historico que o teste nao
tocou — out/2015 a dez/2022 — entra como UMA amostra
(`--amostra historico_2015_22`), declarada agora, inteira.** Nao e'
"rodo 2020-22 e vejo": parada opcional e' p-hacking. Veredito FINAL do
ORB sobre o COMBINADO teste + replicacao + historico
(`eas-preco-combinar`), ~2.400 resolvidas esperadas, +-2 pp: enxerga
0,53. Por-ano REPORTADO como estrato — 2020 (pandemia, circuit
breakers) aparece la', sem que ninguem o tire depois. Dia sem as barras
09:00/09:15 cai em `range_ok = False`, contado, fora.

Mesma ficha (4.1/4.2), mesmo hash `7ae066bb3efb`; o combinar recusa
hash diferente. Criterio: p1 >= 0,56 e IC acima de 0,50 = FAVORAVEL; <=
0,50 = CONTRA; entre = INCONCLUSIVO, e ai' o ORB FECHA como "borda, se
existe, menor do que a que vale operar". Nao ha' terceira replicacao.

### 4.5 FECHAMENTO — CONTRA (2026-09-14, `entregue-v2.65` / `7ae066bb3efb`)

| amostra | pregoes | resolvidas | por tempo (zeragem) | p1 | IC95 | P&L bruto/op |
|---|---|---|---|---|---|---|
| TESTE 2023-25 | 749 | 636 | 84 (-47) | 0,524 | [0,485; 0,562] | +37 |
| REPLICACAO 2026 | 154 | 115 | 34 (-10) | 0,496 | [0,406; 0,586] | -9 |
| HISTORICO 2015-22 | 1.782 | 1.631 | 87 (+26) | 0,478 | [0,454; 0,503] | -29 |
| **COMBINADO** | 2.685 | **2.382** | 205 (-10) | **0,491** | **[0,471; 0,511]** | -10 |

Por ano (reportado): nenhum ano com IC fora de 0,50. 2015-17 abaixo de
0,45; 2019, 2021, 2023-25 entre 0,52 e 0,54; 2020 (pandemia) 0,478 —
nem melhor nem pior que a vizinhanca. Estratos no combinado: a favor
da MME80 0,484; contra 0,500; compra 0,495; venda 0,487.

**Leitura:** o 0,524 do teste era a borda superior de uma faixa de
ruido de dez anos. Nulo a custo zero, como o IFR2. Capitulo fechado;
sem trial 2.

**Backlog (observacao do operador na depuracao, sem acao agora):** nas
operacoes por tempo o lado da entrada era frequentemente o certo e o
alvo ficava perto. Isso e' exatamente a porta de volume declarada
(agressao no rompimento como gate) — hipotese nova, com ficha propria e
amostra que estes testes nao tocaram, quando o tape permitir.

**O que a linha diz depois de dois fechamentos:** dois setups publicos
de preco, M15, no futuro mais liquido do Brasil, 10 anos, estimador
limpo: nulos. Evidencia sobre a CATEGORIA — o que existe de graca em
preco no WIN M15 ja' foi arbitrado. O 123 (5) e' da mesma categoria e
roda com essa expectativa dita antes.

## 5. Ficha 123 — borda pequena e real; F5 desenhado (5.4) — continuacao em pullback

> **F1 (2026-09-14, `entregue-v2.66`):** `eas-preco --ficha 123` faz o
> funil por barra (padrao -> regime -> janela -> D >= 20 -> gatilho em
> t+1 = SINAL), reporta o sinal sem regime e o inside bar como
> informacao, D e capital em pontos, ambiguidade (barra do gatilho:
> stop tocado = ambigua). `eas-preco-teste --ficha 123` ja' existe:
> resolve SEQUENCIAL no dia — sinal com posicao aberta e' `ignorado_posicao`,
> contado, fora do p1. Trial 1 da familia. Expectativa declarada antes
> de medir: provavelmente nulo (4.5). A ficha congela depois do funil,
> com a decisao do regime (clausula ou estrato) tomada pelo 7.4.


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

### 5.1 Funil medido (`entregue-v2.66`, tres dumps, 2.705 pregoes)

| | 2015–22 | 2023–25 | 2026 |
|---|---|---|---|
| padrao de 3 barras (compra + venda) por pregao | 15,7 | 16,3 | 16,6 |
| + regime MME80 | 7,8 | 8,0 | 8,2 |
| + janela 09:30–16:30 | 6,1 | 6,0 | 6,1 |
| + D >= 20 pts | idem (nunca corta) | idem | idem |
| **+ gatilho em t+1 = SINAL** | **3,47** | **3,38** | **3,32** |
| (info) sinal sem exigir regime | 6,97 | 6,77 | 6,67 |
| (info) sinal com inside bar | 1,0 | 1,0 | 1,0 |
| D p10 / p50 / p90 (pts) | 320 / 620 / 1.285 | 225 / 430 / 910 | 280 / 595 / 1.188 |
| capital recomendado p50 / p90 (R$/contrato, informativo) | 6.200 / 12.850 | 4.300 / 9.100 | 5.950 / 11.880 |
| classes: resolvida / ambigua / por tempo | 80% / 7,1% / 13% | 77% / 6,4% / 17% | 78% / 5,4% / 16% |
| duracao p50 / p90 | 4 / 15 | 4 / 19 | 4,5 / 19 |

**Decisoes, antes de congelar:**

1. **Regime fica como CLAUSULA** (v0). Corta metade dos sinais, mas
   sobram 3,4/pregao — ~8.700 sinais em 2015-25, nenhum problema de
   horizonte. Sem razao do 7.4 para afrouxar, e o regime e' o mecanismo
   ("pullback em tendencia"). O "sem regime" e' informacao, nao opcao.
2. Ambiguidade 5-7% — a maior dos tres (o stop na minima da 2a barra
   fica perto da entrada; a barra do gatilho pode visitar os dois).
   Abaixo do corte de 10%; excluida e reportada.
3. A regra sequencial ("posicao aberta ignora sinal") tira mais alguns:
   `ignorado_posicao`, contado, fora do p1.
4. Nenhum numero muda. Inside bar e "sem regime" ficam fora.

### 5.2 CONGELAMENTO (2026-09-14, `entregue-v2.67`) — ficha v0 sem alteracao

    TAXA       3,3-3,5 sinais/pregao (antes da regra sequencial),
               estavel em tres periodos.
    EFEITO     p1 >= 0,56 contra <= 0,50. Teste 2023-25: ~1.900
               resolvidas, +-2,2 pp. Combinado 2015-26: ~7.300, +-1,1 pp.
    AMOSTRAS   As mesmas por data. SEQUENCIA INTEIRA DECLARADA AGORA,
               sem parada opcional: DEPURACAO (14/08+) -> TESTE
               (2023-25, uma rodada) -> REPLICACAO (2026 ate' 13/08)
               -> HISTORICO_2015_22 -> COMBINADO. Veredito FINAL no
               combinado; por-ano reportado. Trial 1 da familia, IC 95%.
    CRITERIO   como as outras: >= 0,56 e IC acima de 0,50 = FAVORAVEL;
               <= 0,50 = CONTRA; entre = INCONCLUSIVO = fecha.
    EXPECTATIVA (dita antes, 4.5): provavelmente nulo. Se nao for, e' a
               primeira borda de preco da linha, e o proximo passo e'
               a ficha de F5 com a porta de volume — hipotese nova.

### 5.3 RESULTADO — INCONCLUSIVO pelo criterio; borda PEQUENA e REAL (2026-09-14, `entregue-v2.67` / `5daf43b4afba`)

| amostra | pregoes | resolvidas | ambiguas | por tempo (zeragem) | ignorados | p1 | IC95 | P&L bruto/op |
|---|---|---|---|---|---|---|---|---|
| DEPURACAO | 20 | 39 | 2 | 8 (+148) | 12 | 0,410 | [0,27; 0,57] | -85 |
| TESTE 2023-25 | 749 | 1.467 | 129 (5,1%) | 371 (+20) | 564 | 0,520 | [0,495; 0,546] | +17 |
| REPLICACAO 2026 | 154 | 302 | 21 | 80 (-42) | 112 | 0,556 | [0,500; 0,611] | +51 |
| HISTORICO 2015-22 | 1.782 | 3.675 | 330 (5,3%) | 683 (+31) | 1.488 | 0,530 | [0,513; 0,546] | +14 |
| **COMBINADO** | 2.685 | **5.444** | 480 (5,2%) | 1.134 (+22) | 2.164 | **0,5285** | **[0,515; 0,542]** | **+17 [-4; +38]** |

Por ano: 2016-2026 todos entre 0,507 e 0,560; so' 2015 (tres meses, n
= 136) abaixo de 0,50. Compra 0,528, venda 0,529.

**O que e':** o IC do combinado EXCLUI 0,50 — efeito pequeno, estavel em
onze anos, estatisticamente real. O primeiro da linha. **O que nao e':**
uma borda que vale operar como esta'. O criterio era 0,56, e os pontos
mostram por que: P&L bruto +17 pts/op com IC [-4; +38], liquido +6 —
o p1 exclui 0,50 mas o P&L nao exclui zero, porque os vencedores tem D
menor que os perdedores (padrao grande falha mais). Com as por tempo
(+22 na zeragem): ~7 pts liquidos por sinal, ~2 sinais/pregao, R$2,80
por dia por contrato sobre ~R$6.000 recomendados. Real, marginal.

**Errata:** a expectativa que declarei antes de medir ("provavelmente
nulo", 4.5) estava errada. Fica registrado.

**Veredito pela ficha:** INCONCLUSIVO -> fecha como EA de preco PURO.
**O que abre:** e' exatamente o caso para o qual a porta de volume foi
declarada no dia 1 — borda pequena e real que um gate de fluxo pode
concentrar. Hipotese nova, ficha propria, amostra que estes testes nao
tocaram: o tape (24/07/2026 em diante) e o forward. E' o desenho 5.4.

### 5.4 DESENHO DE F5 — o 123 como PORTADOR (2026-09-14, decidido pelo operador)

**Papel.** O 123 vai para forward em demo (E4) nao como aposta de P&L,
mas como (a) o primeiro EA com sinal REAL a atravessar a estrutura
multi-EA em producao, (b) a medicao de EXECUCAO que decide se 7 pts
liquidos sobrevivem a` execucao, e (c) o gerador da amostra da porta
de volume — cada sinal gravado com as features de fluxo da barra do
gatilho, para a ficha do gate nascer de dado que nenhum teste tocou.

**O que o forward NAO consegue em 6 meses:** re-verificar p1 = 0,53.
Distinguir 0,53 de 0,50 pede n ~4.300 (+-1,5 pp) — a 2 resolvidas por
pregao, seis anos. Nao e' o objetivo, e esta' escrito para ninguem
"esperar o forward confirmar".

**Ficha de forward (seis linhas):**

    HIPOTESE   A borda de 0,53 do 123 (~17 pts brutos/op) sobrevive a`
               execucao real: slippage de entrada + saida <= 6 pts.
    EVENTO     O mesmo da ficha 5.2, com a execucao definida: ORDENS
               REAIS NA CORRETORA (decisao do operador, 2026-09-14 —
               execucao, nao hipotese). Fechou t com padrao -> ordem
               STOP de entrada em X; t+1 fechou sem executar -> EA
               cancela. Entrada executou -> EA manda stop de protecao
               (STOP) e alvo (LIMITADA) juntos; um executou -> EA
               cancela o outro (OCO e' do EA; a DLL nao tem). Zeragem
               17:30 (a que ja' existe). Regime, janela, D >= 20,
               posicao aberta ignora sinal: identicos. 1 contrato.
               `filtro_fluxo: null`.
    TAXA       ~3,4 sinais/pregao antes da regra sequencial; ~2
               operacoes resolvidas/pregao (medido em 2.685 pregoes).
    EFEITO     Slippage medio (fill real - nivel teorico, entrada e
               saida somados) com meia-largura +-3 pts. Com desvio
               esperado ~15 pts: n = 100 operacoes.
    HORIZONTE  ~50 pregoes (2,5 meses). Reportados junto, sem
               veredito: p1 acumulado com IC, P&L liquido REAL em
               pontos, fracao ambigua RESOLVIDA PELO TAPE, latencia
               sinal->fill, `sinais_sem_vaga` do modo exclusivo.
    CRITERIO   slippage <= 6 pts: o 123 paga a execucao (e vira
               candidato a F6 com o gate); > 12 pts: nao paga, o 123
               so' vive com o gate; entre: inconclusivo, continua ate'
               n = 200. Parada: olho em n = 50 SO' para defeito de
               execucao (ordem nao saiu, fill fora da barra); decido
               em n = 100. Perdas seguidas nao autorizam nada.

**Por que stop real e nao emulacao pelo tape (operador):** com a
conexao caida, a emulacao deixaria a posicao SEM stop ate' o EA voltar
— e ele poderia voltar com o preco ja' alem da barreira. Com ordem
real a protecao esta' na corretora, nao no processo. Nao ha' emulacao
em nenhuma fase; logo "emulacao -> stop real" saiu da lista do que
reinicia a contagem.

**Residuo honesto da escolha:** com a conexao caida o PAR stop+alvo
tambem fica vivo na corretora — se o stop executar e o preco voltar ao
alvo, a limitada abre posicao CONTRARIA; um stop de entrada nao
cancelado no fim de t+1 pode executar horas depois. A E3 ja' zera
divergencia de POSICAO ao reconectar; falta o equivalente para ORDENS
(passo 4b).

**Carimbo.** Tag do codigo + hash do YAML (`ea_123.yaml`) em cada
observacao.

**O que precisa existir (nesta ordem, cada passo entregue e testado):**

1. **Barra de TEMPO no EA** — **ENTREGUE (v2.73)**:
   `ea/barra_tempo.py`, `ConstrutorDeBarraDeTempo(periodo_s=900)`.
   Alinhado em hh:00/15/30/45 (grade UTC = grade da bolsa porque o
   fuso e' inteiro; periodo tem que dividir uma hora, senao e' erro).
   Fecha pelo primeiro trade que cruza a fronteira OU pelo relogio
   (`avancar_relogio`, no tick de 0,5 s — sem isso a ultima barra do
   dia nunca fecha). Buraco nao inventa barra vazia. Trade fora de
   ordem levanta. `BarraFechada` ganhou `vol_agr_compra`,
   `vol_agr_venda`, `n_trades` (insumo do gate). Equivalencia com
   `resample('15min')` do pandas medida em teste (5.000 trades, OHLC e
   volumes por lado identicos). **Conferido no dado REAL (v2.74):**
   `barra-tempo-conferir` em 28/08 e 11/09 — 69 de 69 barras com dado
   completo dos dois lados IDENTICAS ao tick. As duas diferencas
   viraram regra: (a) o grafico DOBRA os negocios de 18:30 em diante
   na barra 18:15 (`fim_sessao_hhmm=1830`); (b) a primeira barra depois
   de ligar pode ser PARCIAL (`BarraFechada.parcial=True`, o EA nao a
   usa). 10/09 sem tape por queda de conexao — backfill do operador.
2. **Semente dos indicadores** — **ENTREGUE (v2.75)**: `ea/semente.py`.
   A MME80 e' semeada no `mme80_ntsl` da ULTIMA barra do parquet do
   grafico (valor do proprio Profit, sem aquecimento) e, se o parquet
   parar antes da vespera, a PONTE vem do tape: os dias que faltam sao
   reconstruidos com o `ConstrutorDeBarraDeTempo` e a recursao continua
   barra a barra. Validade: todo dia util entre o fim do parquet e a
   vespera precisa de >= 30 barras de tape ou estar declarado feriado
   — senao a semente e' INVALIDA com o dia no motivo, e o EA nao arma.
   A barra parcial entra na MME (o close esta' certo); o que ela
   invalida e' geometria. `profit-tape semente-conferir <parquet> --dia
   D` mede, no dado real, a recursao do dia inteiro contra o
   `mme80_ntsl` do grafico. Quando `RequestSerieHistory` existir,
   substitui o parquet — mesmo contrato. O 123 nao usa ATR (D e'
   geometrico), entao so' a MME80 precisa de semente.
3. **`SinalPreco123`** — **ENTREGUE (v2.76)**: `ea/sinal_123.py`. No
   fechamento de t aplica `eas_preco.avaliar_123` (a formula ESCALAR da
   ficha, nova no research; `marcar_123` vetorizada e' conferida contra
   ela por teste de equivalencia em barras aleatorias — mesmos
   candidatos, mesmos niveis, mesma MME) e arma `Candidato123(lado,
   entrada, stop, alvo, D, valido_ate = fim de t+1, mme80, fluxo da
   barra t)`. Regras que so' existem ao vivo (decididas 15/09): **dia
   incompleto** (primeira barra vista nao e' a 09:00 completa -> nenhum
   sinal no dia, MME segue atualizando, `ea.dia_incompleto`); **barra
   parcial** alimenta a MME e reinicia a janela de 3 barras; regime com
   a MME ja' atualizada pelo close de t. Criterio de parcial refinado
   no construtor: primeira barra E 1o trade > 60 s depois do inicio
   (09:00 com 1o trade em 09:00:07 e' completa). Posicao nao mora aqui.
3b. **E2b — familias de ordem que o executor nao tem.** Hoje so'
   mercado (E2) e zeragem (E3). Entram: STOP de compra/venda
   (`SendStopBuyOrder`/`SendStopSellOrder`, existem na DLL, faltam no
   `bindings.py`), LIMITADA (`SendBuyOrder`/`SendSellOrder`, declaradas,
   nunca usadas) e CANCELAMENTO (`SendCancelOrder`). **CODIGO PRONTO
   (v2.70)**: `record --ordem-teste-b-em HH:MM` roda a sequencia inteira
   na demo (mercado -> stop longe + cancel -> OCO -> cancela a outra),
   ver EA_ARQUITETURA "E2b". Falta rodar ao vivo.
4. **Ciclo de ordens do 123** — **ENTREGUE (v2.77)**: `ea/ciclo_123.py`,
   `CicloDeOrdens123` — livre -> entrada_pendente (STOP, vale ate' o
   fim de t+1) -> posicionado (STOP de protecao + LIMITADA de alvo,
   juntas) -> saindo (cancela a outra perna) -> livre; cancelando_entrada
   no fim de t+1; zeragem 17:30 cancela o que estiver vivo e zera a
   mercado. Um candidato por vez: `ignorados_posicao` e
   `ignorados_pendente` contados. Dois modos, um ciclo: REAL (executor
   estendido com `enviar_stop` / `enviar_limitada` / `cancelar` /
   `zerar`, assincronos; fills e cancelamentos lidos dos callbacks no
   `tick`, status do E2b) e DRY_RUN (fills simulados pelo tape no
   `on_trade`: stop no primeiro trade que cruza, limitada AO NIVEL).
   Por ordem: nivel, fill, `slippage_pts` (sinal do lado; positivo =
   contra o EA), latencias de aceite, fill e cancelamento; por operacao,
   `OperacaoRegistrada` com desfecho e P&L em pontos. Timeouts e
   cancelamento nao confirmado deixam AVISO ("CONFIRA NO PROFIT") e
   liberam o ciclo — a limpeza e' do 4b.
4b. **Reconciliacao de ORDENS ao reconectar** — **ENTREGUE (v2.78)**:
   `CicloDeOrdens123.reconciliar_apos_reconexao()`, disparada pelo
   servico na transicao `corretora_pronta` False -> True. Politica: (1)
   `SendCancelOrders` do ticker (todas as vivas — em vez de enumerar
   com `GetOrders`, que exigiria mais uma ida a` DLL); (2) consulta a
   posicao (`GetPositionV2`, E3); (3) posicionado e posicao igual ->
   re-arma stop + alvo; posicionado e zero -> `reconciliado` (uma perna
   executou na queda, P&L desconhecido); livre e posicao != 0 -> ZERA a
   orfa; pendente e zero -> `nao_executou`. `SendCancelOrders`
   declarada no bindings, a conferir ao vivo como o E2b.
5. **`GateDeFluxo`** — **ENTREGUE (v2.78)**: `ea/gate_fluxo.py`,
   protocolo `permite(candidato, barra_t)`, `SemFiltro` default;
   `filtro_fluxo: null` no YAML (`extra="forbid"`); qualquer conteudo
   e' RECUSADO por `construir_gate` ate' existir ficha. O ciclo conta
   `rejeitados_gate`.
6. **Registro do sinal** — **ENTREGUE (v2.78)**: `ea/registro_123.py`,
   JSONL por dia (`data/forward/ea_123/sinais_123_<dia>.jsonl`), uma
   linha por operacao fechada: carimbo (tag + sha256 do YAML),
   candidato, fluxo da barra t (`vol_agr_compra/venda`, `n_trades`) e
   da barra do GATILHO (t+1), ordens com nivel/fill/slippage/latencias,
   desfecho, P&L. E' o F1 do gate.
7. **`ea_123.yaml` + esteira** — **ENTREGUE (v2.78)**: `config/ea_123.yaml`
   (`tipo: "123"`, `dry_run: true`); `ea/config_123.py` (`EA123Config`,
   `carregar_config_ea` escolhe pelo tipo); `ea/service_123.py`
   (`EA123Service`: semente no arranque, sem semente sobe sem armar,
   barra de tempo, `tick()` para relogio/callbacks/reconexao); registro
   e recorder aceitam os dois tipos; o bridge chama `tick()` quando
   existe. **Falta o pregao em dry_run** (7a) e depois o E4 (7b).

**O que reinicia a contagem:** qualquer numero da ficha 5.2; mudar
o tipo de ordem de qualquer perna; ligar o gate. **O que nao reinicia:**
bug que faz o codigo passar a fazer o que a ficha ja' diz.

**Capital:** informativo, por sinal, no log: D x R$0,20 / 2%. Mediano
~R$6.000 por contrato; p90 ~R$12.000.

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

## 8. Outros instrumentos — WDO declarado; acoes registradas (2026-09-15)

**Regra:** a ficha e' POR INSTRUMENTO. O mecanismo (IFR2, ORB, 123) e' o
mesmo; os numeros que ela congela — tick, custo, sessao, D minimo — sao
do instrumento, e cada instrumento reinicia a contagem de trials. O
`eas_preco` tem PERFIS (`usar_instrumento`, `--instrumento` nos tres
comandos); o hash da ficha inclui o perfil, entao resultado de WIN e de
WDO nunca se somam. O default e' o WIN com os valores dos 10 anos: nada
mudou para quem nao passa `--instrumento`.

**Multiplicidade, declarada antes:** 3 setups x N instrumentos. A lista
e' FECHADA aqui; nao se acrescenta instrumento depois de olhar
resultado. O que convence nao e' um p1 acima de 0,56 num teste — e' o
que convenceu no 123: por-ano consistente (11 de 12). Cada instrumento
segue a sequencia inteira (depuracao -> teste -> replicacao ->
historico -> combinado) com o criterio de sempre.

### 8.1 WDO (mini-dolar) — DECLARADO, tres fichas, a medir

Perfil (`PERFIS["wdo"]`): tick 0,5 pt; 1 pt = R$10/contrato; custo
ida-e-volta 0,30 pt (~R$3, a conferir na nota); janela 09:15-16:30 (IFR2)
/ 09:30-16:30 (123); range ORB 09:00 e 09:15, entradas ate' 11:45;
zeragem 17:30; fim de sessao 18:30 (mesma grade do WIN: ultima barra
18:15, 37,5 barras/pregao — confirmado no dump 2023-25). D minimo 4
ticks = 2 pts. O dump do WDO e' a serie continua AJUSTADA (precos com 8
decimais): a geometria e' a mesma; ao vivo os niveis caem na grade de
0,5, e o EA arredonda ao tick.

**Funil 2023-25 (15/09):** 123 2,84 sinais/pregao, D p50 14 pts, ambigua
4,5%, por tempo 19%; ORB 0,94/pregao, A p50 25 pts, ambigua 1,7%, por
tempo 15%; IFR2 3,45/pregao, ATR14 p50 9,9 pts, ambigua 0,9%, por tempo
6%. Custo irrelevante nos tres (p1 de empate 0,506-0,514). Faltam os
dumps 2015-22 e 2026 para congelar.

Ordem: as tres fichas como estao (v0 do IFR2 com K = 1 e regime
estrato? NAO — para o WDO cada ficha comeca da versao que foi
CONGELADA no WIN: IFR2 = 3.2 com K = 1, ORB = 4.1, 123 = 5.2). Funil
nos tres dumps (2015-22, 2023-25, 2026) -> congelar com os pontos do
WDO -> sequencia. Expectativa dita antes: IFR2 e ORB provavelmente
nulos (foram nulos no WIN por dez anos e o dolar e' tao arbitrado
quanto); o 123 e' a pergunta.

Por que WDO primeiro: mesma DLL, mesmo executor provado (bolsa "F"),
tape acumulando desde 24/07, e ticker DIFERENTE do WIN — caminho B
puro, sem modo exclusivo: e' o E5.6 como foi desenhado (123 no WIN e
o que sobreviver no WDO, ordens reais, sem netting).

O que o operador faz: dumps do grafico M15 do WDOFUT (mesmo
`preco_m15.ntsl`, mesmas janelas de data) e
`profit-tape eas-preco <dump> --ficha 123 --instrumento wdo --saida ...`
(idem `orb`, `ifr2`).

### 8.1b WDO — TRES FICHAS CONGELADAS (2026-09-15, `entregue-v2.82`)

Funis nos tres dumps (2015-22: 1.715 pregoes; 2023-25: 749; 2026: 175,
ate' 14/09), equivalencia batendo em todos:

| | 123 | ORB | IFR2 |
|---|---|---|---|
| sinais/pregao (15-22 / 23-25 / 26) | 2,76 / 2,84 / 2,75 | 0,96 / 0,94 / 0,97 | 3,50 / 3,45 / 3,54 |
| D p50 (pts) | 20 / 14 / 12 | 30 / 25 / 18 | 15 / 10,5 / 8 |
| ambigua | 4,4 / 4,5 / 5,0% | 0,7 / 1,7 / 1,8% | 0,6 / 0,9 / 0,6% |
| por tempo | 15 / 19 / 17% | 10 / 15 / 12% | 4,5 / 6,3 / 6,8% |
| capital p50 (R$/contrato, informativo) | 10.000 / 7.000 / 6.000 | 15.250 / 12.750 / 8.900 | 7.500 / 5.250 / 4.000 |
| p1 de empate (custo 0,30) | 0,507-0,512 | 0,505-0,508 | 0,510-0,519 |

Taxas identicas as do WIN por familia; a vol do dolar caiu pela metade
de 2015 a 2026 e a taxa nao se mexeu. Nenhuma razao de 7.4 para mudar
clausula. **Congeladas como as do WIN**: IFR2 = 3.2 com K = 1 e regime
estrato; ORB = 4.1 (D = A, regime estrato); 123 = 5.2 (regime clausula).
Perfil `wdo` (tick 0,5; custo 0,30 pt; fim de sessao 18:30). Cada uma
e' trial 1 da sua familia no WDO; hash da ficha inclui o perfil.

Sequencia, as tres de uma vez, declarada: DEPURACAO (14/08+) -> TESTE
(2023-25, uma rodada) -> REPLICACAO (2026 ate' 13/08) -> HISTORICO
(2015-22) -> COMBINADO; veredito no combinado; por-ano reportado;
inconclusivo = fecha. Expectativa dita antes: IFR2 e ORB provavelmente
nulos; o 123 e' a pergunta. Nota: 2015-22 tem 36,4 barras/pregao (o WDO
fechava mais cedo em parte do periodo) — o funil usa os rotulos, nada
muda.

### 8.1c WDO — FECHADO: nenhuma das tres sobrevive (2026-09-15, `entregue-v2.82`)

| ficha (hash) | resolvidas | p1 | IC95 | P&L bruto/op (pts) | por-ano | veredito |
|---|---|---|---|---|---|---|
| 123 (`5663e5d29f10`) | 4.431 | 0,514 | [0,499; 0,528] | -0,1 | 2016-17 fortes, 2020-23 < 0,50, 2024-25 > 0,50 | INCONCLUSIVO -> fecha |
| ORB (`fad0bc2bf119`) | 2.171 | 0,517 | [0,496; 0,538] | +0,7 | 0,43 a 0,58, sem padrao | INCONCLUSIVO -> fecha |
| IFR2 (`5aaa0f6ac7fc`) | 8.612 | 0,492 | [0,482; 0,503]* | -0,3 | nenhum ano com IC fora de 0,50 | **CONTRA** |

*O relatorio saiu com IC 97,5% (TRIAL da familia no WIN); no WDO e'
trial 1 e o IC95 acima e' o correto — veredito igual. Corrigido na
v2.83: trial por (ficha, instrumento).

**O que isso diz sobre o 123 do WIN, sem suavizar:** seis testes de
preco em dois futuros, todos entre 0,49 e 0,53; o unico com IC fora de
0,50 e' o 123 no WIN. A borda dele continua real (n = 5.444, onze anos
de doze), mas NAO replicou no dolar — parece mais o topo de uma faixa
de efeitos pequenos do que um mecanismo geral. Nao reabre nada;
reforca a decisao ja' tomada: o 123 no WIN e' portador e medidor de
execucao, nao aposta de P&L. A porta de volume continua sendo a unica
hipotese com chance de transformar 0,53 em algo que pague.

**Consequencia para o E5.6:** o caminho B com WDO dependia de algo
sobreviver la'. O segundo EA com ordens reais volta a ser o de fluxo
(Rota B) no modo exclusivo com o 123, como estava desenhado — ou um EA
declaradamente nulo no WDO so' para provar dois tickers com ordens
reais (infra, nao estrategia). Decisao do operador.

### 8.2 Acoes — REGISTRADO, nao agora

> Com o que a linha de preco mostrou em dois futuros, a expectativa
> declarada para as acoes fica ainda mais baixa. Continuam registradas.


Lista fechada (liquidez e spread apertado em M15): **PETR4, VALE3,
ITUB4, BBDC4, BBAS3**. Nada de small caps: com tick de R$0,01 o custo
proporcional come uma borda de 0,53.

O que muda, e por que fica para depois — **corrigido em 15/09**: eu
tinha escrito que acao nao tem tape; o record captura PETR4, VALE3,
ITUB4, BBAS3 (e BOVA11, MGLU3, WEGE3) desde o inicio. Entao porta de
volume, semente por ponte e ambigua pelo tape VALEM para quatro das
cinco da lista (BBDC4 nao e' capturada — a incluir no record quando
chegar a vez). O que continua diferente: pregao 10:00-17:00, lote de
100, preco em centavos, custo em % e nao em pontos; o executor foi
provado em bolsa "F" — bolsa "B" exige refazer a E2 (uma ordem real na
demo) antes de qualquer E4. A ordem (WDO primeiro) nao muda: o
argumento dela e' o caminho B, nao o tape. Perfil de instrumento por
acao a escrever quando chegar a vez. Expectativa dita antes:
provavelmente nulo na maioria; se uma sobreviver com onze anos
consistentes, ai' se refaz a E2 para bolsa B.

**Fora da lista, declarado:** BIT, ouro, contratos cheios (INDFUT,
DOLFUT — mesma exposicao dos minis com menos liquidez para 1 lote).
