# EAs de PRECO — linha paralela enquanto o tape acumula (2026-09-13)

Estado (2026-09-14, noite): **IFR2 FECHADA (familia CONTRA). ORB FECHADO
— CONTRA no combinado de 10 anos (4.5).** **123 em F1**: funil entregue
(`eas-preco --ficha 123`), ficha v0 em rascunho ate' medir. Ultimo dos
tres candidatos declarados.

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

## 5. Ficha 123 (rascunho v0) — continuacao em pullback

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
