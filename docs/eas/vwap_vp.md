# VWAP + Volume Profile (WIN) — fast-track

> **Status:** **FECHADA (01/10, v4.08).** Três setups do documento respondidos pelos dados em 46 dias: A existe como evento (1,87/dia) e não como confluência (0,22/dia com o POC), e como evento é simétrico-a-contra; B morto por taxa; C sem LVN num perfil de 17–20 M contratos. Sobreviveu **uma** assimetria, `continuacao_tarde`, em demo desde 01/10. Eventos congelados em código para reavaliação em dados NOVOS (ver "Plano forward"). — **Criado:** 2026-09-29 (v3.86); fechada em v4.08 —

## Identidade, fase e estado

EA `tipo: "vwap_vp"` na esteira multi-EA (F3, ainda não escrito). Fase:
F1 — VWAP de sessão e perfil por preço recalculados do tape curado, para
bater contra o gráfico do Profit **antes** de qualquer replay. Setup B
primeiro; A e C são fichas futuras que empilham abaixo desta.

## Mecanismo em uma frase (Setup B)

Preço esticado a 2 desvios da VWAP **no mesmo nível** em que ontem o
mercado aceitou valor (VAH/VAL) e com a agressão sendo absorvida tende a
voltar para a VWAP — o extremo estatístico do dia coincide com uma borda
de valor conhecida, e o fluxo que chegou lá já não move o preço.

## O que o documento de origem deixava em palavras, e o que virou número

| palavra | definição adotada | de onde |
|---|---|---|
| "absorção / exaustão" | **v3.90:** `absorcao_comp = max(imb,0)·(1−des)` para a venda em +2SD (compradores agridem e o preço não sobe); `absorcao_vend = max(−imb,0)·(1+des)` para a compra; z de 50 barras contínuo em cada série | definição fiel ao documento. A v3.87 reaproveitou `absorcao_dir = imb − des` (Rota B, reprovado sozinho em 30/08) e o único episódio da 1ª rodada mostrou que ele dispara em **vendedores batendo com o preço caindo** — momento, não exaustão. Corrigido ANTES da 2ª rodada; `absorcao_dir` fica no CSV como coluna |
| "VAH / VAL / POC" | perfil por preço em bins de 25 pts; POC = bin de maior volume; área de valor 70% expandindo bin a bin para o vizinho maior | `ea/perfil_preco.py` — algoritmo a **conferir contra o Profit** (D4) |
| "banda ±2 SD" | desvio ponderado pelo volume, populacional, da sessão | `ea/vwap_sessao.py` |
| "agressão / delta" (A e C) | `agr_compra − agr_venda` por bin, tipos 2/3 | `perfil_preco.delta_no_bin` — fichas futuras |

## Decisões congeladas (29/09)

- **D1** Setup B primeiro; confirmação = absorção existente. A (pullback
  VWAP+POC, precisa de "tendência" e "rejeição") e C (LVN, precisa de
  definição de LVN olhada na tela e do perfil M5 por horário, que só fica
  completo ~2 semanas após 10/09) vêm depois, cada um com ficha própria.
- **D2** VP de referência = **dia útil anterior, fixo**, construído do
  curated no arranque com cache por assinatura (mesmo esquema do
  `cache_barras`). VP em desenvolvimento é v2.
- **D3** VWAP e VP com **todos** os negócios (agressão + RLP + leilão): é o
  que o Profit plota e o que se confere na tela. Delta por nível só
  agressão; RLP e leilão contados à parte para gravar com/sem RLP de graça.
  O `vwapvp-conferir` imprime três conjuntos (todos / agressão+RLP /
  agressão) — a diferença se mede, não se assume.
- **D4** bin 25 pts. LVN = bin < 30% da média de ±2 vizinhos; HVN = máximo
  local ≥ 50% do POC. **Chute declarado**, parâmetro e não constante; só o
  Setup C depende disso.
- **D5** limiar do estimador de absorção = **percentil 80** da
  distribuição por barra M5 na amostra queimada, **congelado como valor**
  (não recalculado ao vivo). p90 é subgrupo pré-declarado.
- **D6** stop e alvo em pontos, fixados só depois da tabela de distância
  ±2SD→VWAP por horário (checkpoints 10h/12h/14h/16h do `vwapvp-conferir`).
- **Barra:** M5. M1 muda a estatística de barra para negócio; não usar
  sem medir de novo.
- **Corretora:** não entra no gatilho. `z_agf_3` da barra é gravado em
  cada observação como subgrupo. C2 da ignição (saldo por corretora) não
  sustentou a hipótese e já paga seu forward (H-C2inv); não repetir aqui.

## Ficha rápida (forward) — fecha com a saída do `ea-vwapvp-replay`

    HIPOTESE   preço em ±2SD ∧ VAH/VAL de ontem ∧ absorção acima de p80 volta em direção à VWAP
    EVENTO     barra M5 fechada com: |z_vwap| >= 2; |close − VAH| <= 25 pts (venda) ou
               |close − VAL| <= 25 (compra); z_absorcao·lado >= p80 (VALOR congelado pelo
               replay); 09:30–17:00; sem posição; cooldown 30 min
    TAXA       A MEDIR: `ea-vwapvp-replay` dá episódios/dia por cláusula e por hora
    EFEITO     A DEFINIR PELA SONDA. A linha anterior (p_alvo >= 0,58, binário "VWAP antes do
               stop") foi RETIRADA em 29/09: a banda +2SD está a 1.000–1.160 pts da VWAP a
               partir de 12h (F1) e o binário com stop de 50 não mede nada. O replay dá MFE/MAE
               em 5/15/30/60 min e a fração que toca a VWAP; alvo e stop saem em pontos daí
    HORIZONTE  A CALCULAR de TAXA × EFEITO; se > 6 meses, afrouxar (±1,5SD ou tolerância 50)
               ANTES de ligar, e anotar aqui
    CRITERIO   a fixar junto com EFEITO (IC 95% do que a sonda escolher como métrica)
    PARADA     olhar só no n da linha HORIZONTE. Subgrupos declarados (p90, z_agf_3 >= 1,4,
               com/sem RLP, área de valor por pares) respondem DEPOIS do principal e não
               autorizam trocar o gatilho. Mudou parâmetro = contagem nova (carimbo tag + sha).

## Regras (o suficiente para reimplementar — F3, ainda não escrito)

- Entrada: no fechamento da barra M5 que satisfaz EVENTO, a mercado, 1
  contrato, contra o extremo (venda em +2SD/VAH, compra em −2SD/VAL).
- Saída (primeiro que ocorrer): toque na VWAP (alvo, marcado a cada
  negócio), stop em pontos além do nível (D6), `tempo_max_s`, 17:00.
- Dia: bloqueio por `max_perdas_seguidas` e `perda_max_dia_pontos`.
- Cada observação grava: `absorcao_valor`, `absorcao_p80`, `absorcao_p90`,
  `z_vwap`, distância ao nível, `z_agf_3`, `delta_bin` com e sem RLP,
  `config_sha`, tag.

## Como conferir (F1)

    profit-tape vwapvp-conferir                      # os 2 últimos dias do curated
    profit-tape vwapvp-conferir --dia 2026-09-25 --dia 2026-09-28 --histograma-csv data/vp.csv

No Profit, mesmo dia, Volume Profile com **"negócios de leilão" DESLIGADO**
(ligado, o Profit soma o call num preço médio — 183.504,25 em 28/09 — que o
tape não tem, e o POC muda de bin). O POC do Profit deve cair dentro do
`poc_faixa`. O Profit **não marca VAL/VAH** e não deixa configurar o %: o
algoritmo da área de valor não é conferível na tela — o replay calcula os
dois (bin a bin e pares) e mede a diferença. Fim de semana e dia em captura
são recusados pelo comando.

## Resultados

### F1 — conferência contra o Profit (29/09, dias 25/09 e 28/09, 5,4–5,6 M negócios/dia)

| | 25/09 | 28/09 |
|---|---|---|
| VWAP todos / agr+RLP / agr | 184326 / 184322 / 184324 | 183977 / 183979 / 183979 |
| SD final | 486 | 554 |
| 2SD em pts às 10h / 12h / 14h / 16h | 579 / 1003 / 1047 / 993 | 748 / 1145 / 1158 / 1160 |
| POC (bin 25) | 184575 — Profit 184578 ✓ | 184100 — Profit 184100 ✓ (leilão desligado) |
| VAL / VAH (bin a bin) | 183775 / 184900 | 183550 / 184975 |
| RLP | 26,1% do volume | 25,9% |

O que isso decidiu:

- **D3 fechado:** RLP e leilão movem a VWAP em **4 pts**. "Todos" fica; a
  conferência de VWAP na tela é dispensável.
- **POC é um platô, não um ponto:** os 8 maiores bins ficam a 3% um do outro
  numa faixa de ~150 pts (25/09: 184475–184650; 28/09: 184000–184150).
  `poc_faixa` (bins ≥ 90% do máximo) passa a ser gravado; alvo ancorado em
  POC tem ±100 pts de indeterminação por construção. Setup B fica nas bordas.
- **RLP é uniforme por nível** (26–27% em todo bin, inclusive no POC e no
  183500 disputado): não desenha o perfil. Chute de RLP concentrado em nível
  morto por dado.
- **Delta por nível na escala do dia é ~0 em todo lugar** (±11 k sobre
  470 k no POC de 28/09). Delta só significa algo em janela (Setup A).
- **A banda dobra entre 10h e 12h** — "z = 2" às 09:40 é um esticão de ~400
  pts, às 14h de 1.100. O replay conta episódios por hora; a janela pode
  precisar começar às 10:00.
- **HVN/LVN como definidos não servem**: 25/09 só LVN na cauda de cima; 28/09
  9 HVN e 1 LVN no fundo. Perfil de 17 M contratos em 92 bins é liso. Fica
  para a ficha do Setup C, com outra definição.
- Em 28/09 a +2SD cruzou o VAH de 25/09 (184900) entre 12h e 16h — o evento
  existiu pelo menos uma vez. A taxa é do replay.

### F2 — primeira rodada (30/09, v3.87, 46 dias 24/07–28/09, 2.875 s)

    Estimador (z x lado), 2844 barras: p50=-0,02 p80=1,00 p90=1,37 p95=1,64   [NAO congelar: ver defeito 1]
    c_banda          barras=550  episodios=151  /dia=3,36
    c_nivel          barras= 15  episodios=  9  /dia=0,20
    c_absorcao_p80   barras=  1  episodios=  1  /dia=0,02
    c_janela         barras=  0  episodios=  0  /dia=0,00
    c_banda por hora: 9h:8 10h:34 11h:18 12h:19 13h:17 14h:12 15h:9 16h:10 17h:16 18h:8
    c_nivel por hora: 11h:1 13h:1 14h:1 15h:2 17h:2 18h:2
    2SD mediana por hora: 9h:619 10h:761 11h:1026 12h:1138 13h+:1186–1229
    Sonda c_nivel (n=9, VWAP a 1216 pts): MFE med 60–75, MAE med 105–115 (p75 até 330), 0% tocou VWAP
    Area de valor bin x pares (45 dias): |dif| mediana 1 bin, max 8–13; plato do POC mediana 100 pts

**Leitura (30/09):**

- **Morto por taxa, como o documento o escreve.** A cláusula de local
  sozinha (banda ∧ 25 pts do VAH/VAL de ontem) dá 9 episódios em 45
  pregões. n=100 levaria ~500 pregões. É raro por construção: a banda tem
  1.000–1.230 pts de largura de 11h em diante e o VAH de ontem é um ponto;
  exigir os dois a 25 pts é exigir a coincidência de referências
  independentes. Absorção e janela não são a causa — chegam a 1 e 0.
- Os 9 eventos de local, sem absorção, **não reverteram** (MAE > MFE em
  todo horizonte, 0% tocou a VWAP). n=9 não conclui; registrado como
  observação na direção do risco "dia de tendência atropela reversão".
- `c_banda` sozinha tem taxa operável (3,36/dia) e é a única cláusula com
  amostra. Pico às 10h, quando a banda ainda tem 760 pts.
- Área de valor bin a bin × pares: irrelevante na mediana (1 bin), grande
  na exceção (8–13). Some da ficha como decisão; fica gravada como subgrupo.

**Defeitos da rodada (corrigidos em v3.89):**

1. O z de absorção reiniciava a cada dia (janela de 50 barras M5 = 250 min):
   o estimador só existia de ~13:10 em diante, 2.844 de 5.144 barras (55%).
   No gráfico a janela atravessa dias. **p80 = 1,00 e p90 = 1,37 NÃO estão
   congelados** — foram medidos só em tardes. Não muda a taxa de `c_nivel`.
2. Os negócios de todos os dias ficavam em memória para a sonda (~4 GB).
   Agora a sonda é calculada por dia para toda barra com |z| ≥ 1,5 e vai
   para o cache junto com as barras: a rodada cara acontece uma vez.

**Regra de escolha da variante — aceita em 30/09, ANTES da segunda rodada:**
variantes declaradas (z_banda, tolerância) = (2,0, 25) (2,0, 50) (1,5, 25)
(1,5, 50), só com contagens. Escolhida = a mais restritiva (menor taxa em
`c_nivel`; empate → maior z, menor tolerância) com **≥ 1 episódio/dia em
`c_janela`**. A sonda é impressa só para `c_banda` (linha de base) e para
a escolhida. Nenhuma chega → **abandono por taxa** do Setup B com VP de
ontem, decisão de poder tomada antes de olhar resultado; o desenho
seguinte (banda sozinha? VP de ontem como regime "abriu dentro/fora da
VA", em vez de toque a 25 pts?) é ficha nova com contagem nova.
[Provável] nenhuma chega: 0,2 × 2 × 2 = 0,8 no melhor caso.

**Validação das barras (30/09, export do Profit de 28/09):** 112 de 113
barras M5 idênticas em OHLC e volume (`vol_total` = `QuantityVol`). A última
(18:20–18:25) tem no Profit +22 k contratos e fechamento 183855: é o call de
fechamento, que o tape não recebe — mesmo fenômeno da opção "leilão" do
Volume Profile. Irrelevante para a janela e para as bordas. A primeira barra
(09:00) sai `volume_confiavel=False` embora bata exatamente: falso positivo
da regra de parcial no `barra_tempo`, módulo compartilhado com EAs em
forward — não tocado. O CSV traz `hhmm` (fechamento) e `hhmm_abertura`
(rótulo do Profit).

**Mecanismo da absorção corrigido (v3.90, antes da 2ª rodada).** O único
episódio de absorção da 1ª rodada (27/07 18:10, +2,68 SD, no VAH de 24/07)
era vendedores agredindo (imb −0,26) com o preço caindo (des −0,56):
`absorcao_dir` = +0,30, z 1,03 > p80. Isso é momento vendedor, não
"exaustão do fluxo comprador". O estimador reaproveitado dá positivo em
duas situações opostas. Definição nova, conferida à mão (compra 30/venda 10
subindo 20% do range → 0,40; caindo até a mínima → 1,0; a barra de 27/07 →
comp 0, vend 0,116). Pego pela pergunta "como é calculado" — regra 1 da
disciplina, mecanismo antes do número, aplicada tarde mas antes de ligar.

**Dias truncados (v3.91, declarado antes da 2ª rodada).** O `barras.csv` da
1ª rodada mostra 31/07 começando às 12:35 (71 barras) e 15/09 às 10:05
(101). Neles a VWAP "de sessão" começa no meio do pregão — desvio e bandas
errados o dia inteiro — e o perfil que alimentam (03/08 e 16/09) é
incompleto. Regra: **dia sem a barra das 09:00 ou com < 110 barras sai de
tudo** (distribuição, episódios, referência); o dia seguinte usa o último
dia **completo** como referência. Buraco do book (27/08–04/09) não entra:
o replay lê só negócios, e o tape de negócios está inteiro nesse trecho.

**Verificação dos cálculos de cima (30/09, do `barras.csv`):** `dist_vah`/
`dist_val` de 28/09 = `close − 184900` / `close − 183775` em todas as barras
(diferença 0,0), os números do perfil batido no Profit; VWAP/SD às 10:00 =
os do `conferir`; `z_vwap` de 27/07 18:10 refeito à mão = 2,683. O que
resta e só o operador pode fazer: no Profit com VWAP + bandas de 2 desvios,
confirmar que o fechamento das barras `c_banda` está fora da banda (se não
estiver, é definição do desvio — o meu é ponderado por volume e
populacional — e não erro); e nas 9 barras `c_nivel`, que o fechamento está
colado no VAH/VAL **do dia anterior**. Os zeros de `c_janela`/`p90` são
subconjuntos de `c_absorcao_p80` (1 barra às 18:10): aritmética, não cálculo.

### F2 — segunda rodada (30/09, v3.91, 46 dias completos 24/07–30/09, 566 s)

    EXCLUIDOS: 2026-07-31 (71 barras, comeca 1230), 2026-09-15 (101, comeca 1000)
    Estimador (lado exausto, z50 continuo), 5148 barras: p50=-0,39 p80=0,92 p90=1,59 p95=2,23
    z_banda tol   c_banda  c_nivel  c_abs_p80  c_janela  c_abs_p90  c_janela_p90
      2,0    25     3,47     0,20       0,13      0,04       0,00          0,00
      2,0    50     3,47     0,24       0,13      0,04       0,00          0,00
      1,5    25     7,07     0,31       0,13      0,04       0,00          0,00
      1,5    50     7,07     0,40       0,20      0,11       0,07          0,07
    NENHUMA variante chega a 1/dia em c_janela -> abandono por taxa
    c_banda por hora (z=2): 9h:9 10h:34 11h:18 12h:18 13h:16 14h:13 15h:11 16h:11 17h:18 18h:8
    2SD mediana por hora: 9h:621 10h:772 11h:1031 12h:1147 13h+:1186–1280
    Sonda c_banda (linha de base, n=156, VWAP a 1068 pts):
       5 min  MFE 78 (p25 30)   MAE 100 (p75 195)   tocou VWAP 1%
      15 min  MFE 145 (55)      MAE 185 (359)       7%
      30 min  MFE 185 (71)      MAE 250 (541)       12%
      60 min  MFE 220 (90)      MAE 315 (641)       13%
    Area de valor bin x pares: |dif| mediana 1 bin (max 8–13); plato do POC mediana 100 pts

**Leitura:** o local (banda ∧ VAH/VAL de ontem) é raro por construção e a
absorção do lado exausto, agora com o mecanismo certo, deixa 0,13/dia
antes da janela. A linha de base da banda sozinha (n=156, descritiva,
amostra queimada) tem excursão **contra** maior que a favor em todo
horizonte e 13% de retorno à VWAP em 60 min: o preço a 2 desvios tende a
continuar, não a voltar. Um EA de "reversão na banda sozinha" nasceria
contra a própria linha de base.

Comando (barras e sonda em cache; qualquer variação responde em segundos):

    profit-tape ea-vwapvp-replay --saida data/vwapvp_f2

Devolve: percentis 50/80/90/95 do estimador (p80 e p90 **congelados como
valor** — copiar para cá e para o YAML do F3); episódios por cláusula
(banda → nível → absorção → janela) por dia e por hora; sonda MFE/MAE/toque
na VWAP em 5/15/30/60 min para `c_nivel` (só local) e `c_janela` (evento
completo) e o subgrupo p90; diferença VAL/VAH bin a bin × pares; largura
2SD por hora. Nada é escolhido por resultado; os parâmetros são os desta
ficha.

## Validação NTSL — o circuito que faltava (v3.93)

Tudo até aqui foi pego contra o gráfico ou contra um export, nunca por
teste. O que restava sem conferência de tela: os `z`, a absorção (e a sua
entrada, `AgressionVolBuy/Sell`, que **nunca foi batida** com
`vol_agr_compra/venda` do tape), a VWAP e as bandas. O circuito é o mesmo
do `absorcao_dir.ntsl` (2,4e-08): o indicador loga uma linha por barra, o
Python recalcula das suas barras em cache e **mede**.

- `ntsl/vwapvp_conferir.ntsl` (gráfico M5 WINFUT): VWAP de sessão **por
  barra** ((H+L+C)/3 × QuantityVol acumulado desde a abertura) com bandas,
  imbalance, desloc, absorção comp/vend, z50 (divisor Janela−1, barra atual
  fora, janela atravessa dias), estimador. Pinta amarelo em |z| ≥ 2 e
  vermelho com estimador ≥ 0,916 (só visual). Dump `VWAPVP|…` de 21 campos.
  `CalcDataInicio` desliga o cálculo antes da data (gráfico desde 2021
  trava com os laços de 50 por barra); deixe ≥ 2 pregões antes de
  `LogDataInicio`, o aquecimento do z, que é o mesmo do Python
  (`--aquecimento-dias 2`).
- `profit-tape vwapvp-ntsl-equivalencia --log <dump>`: três blocos.
  **1. Exatas** (mesma fórmula; espera-se ~1e-8): OHLC, vol, imbalance,
  desloc, absorção, z, estimador, VWAP/SD/z por barra. **2. Agressão,
  medida**: razão Profit/tape em compra e venda — ~1,00 se o Profit exclui
  RLP, ~1,35 se inclui (26%/74%). É o número que decide se a absorção do
  replay é a que se vê no gráfico. **3. VWAP por negócio × por barra** em
  pontos, por hora: quanto vale a aproximação do gráfico.
- `profit-tape vwapvp-ntsl-niveis`: gera `ntsl/vwapvp_niveis_gerado.ntsl`
  com VAH/VAL/POC do último dia completo anterior como constantes por
  data, para **ver** no gráfico onde as barras `c_nivel` caíram e bater o
  POC com o Volume Profile nativo (leilão desligado).

Alinhamento feito antes da conferência: o `ZRolante` do replay usava
desvio populacional; o `absorcao_dir.ntsl` usa divisor (Janela−1). Python
alinhado ao arquivo de referência (skill 3.1); p80/p90 mudam ~1%. Dias em
que o tape tem menos barras que o gráfico (31/07, 15/09) são listados na
saída: as 50 barras seguintes têm z diferente pelos dois lados, esperado.

**Conferência fechada (01/10, v3.95, dump de 28/09):** com a barra do
call como zero nos dois lados, `absorcao_comp/vend`, `z_comp`, `z_vend` e
`estimador` bateram **113/113 a zero**. Restam diferentes só a barra das
18:20 nas colunas de preço/volume (call de fechamento) e `vwap_bar` a
2×10⁻⁵ pt (Float). Bloco 3: desvio por barra 3,2% menor na mediana (p05
−10%), mas `z_bar − z_negócio` mediana −0,007 — a VWAP por barra também se
desloca e os efeitos se cancelam na média; o que sobra é dispersão: 5
barras a |z| ≥ 2 por negócio, 7 por barra, **2 trocam de veredicto** (~2%
das barras do dia). É o tamanho real da aproximação do gráfico.

**Resultado da conferência (30/09, dump de 28/09, 113 barras):** OHLC,
volume, agressão, imbalance, absorção, desvio e z por barra **exatos** em
112/113 — a exceção é a barra das 18:20 (call de fechamento, que o
gráfico tem e o tape não). `AgressionVolBuy/Sell` = `vol_agr_compra/venda`
do tape barra a barra (razão 1,000): **o Profit exclui RLP da agressão**, a
absorção do replay é a do gráfico. `vwap_bar` difere 2×10⁻⁵ pt (precisão
do Float). VWAP por negócio × por barra: mediana 12 pts, p95 20, máx 33. O
único vazamento: a absorção da barra das 18:20 difere e entra na janela do
z das 50 primeiras barras do dia seguinte (50 `z_comp` diferentes, máx
0,09). Regra v3.95, nos dois lados: **a barra que abre às 18:20 entra como
zero nas séries de absorção** — fora de qualquer janela de evento.

Limites, declarados: a VWAP por negócio do replay **não é reproduzível
em NTSL** (o gráfico não tem negócios); o que se confere é a aproximação
por barra, e o bloco 3 mede a distância. A VWAP nativa do Profit é um
terceiro objeto, com definição não documentada; se as bandas dela não
baterem com as do indicador, é definição, não erro.

## Veredito

**Abandonado por taxa (30/09).** Decisão de poder pela regra aceita antes
da rodada: nenhuma das 4 variantes pré-declaradas chega a 1 episódio/dia;
a melhor dá 0,11 (um a cada 9 pregões; n=100 levaria ~4 anos). Não é
veredito sobre a hipótese — ela não foi testada, porque o evento não
acontece com frequência testável. Setups A e C do documento não foram
testados e não serão como escritos: A exige coincidência de duas
referências móveis (VWAP e um POC que é platô de 100 pts); C exige um LVN
que um perfil liso de 17 M contratos não tem.

**O que sobrevive:** `ea/vwap_sessao.py`, `ea/perfil_preco.py` (POC e
barras M5 batidos no Profit) e o replay com cache — infraestrutura para
qualquer ficha que use VWAP/bandas/perfil como cláusula ou regime.

## Fichas seguintes — eventos DECLARADOS em 01/10, antes de contar

Aceitos pelo operador: (1) rejeição intrabarra e (2) banda como
continuação. As cláusulas estão congeladas em
`EVENTOS_DECLARADOS` (`research/vwapvp_replay.py`) e o
`ea-vwapvp-taxa` só CONTA (episódios/dia, por hora, por cláusula) —
nenhuma sonda até cada ficha estar escrita:

    REJEICAO  (venda; compra = espelho; VWAP/SD da barra ao fechar)
      toque       high >= vwap + 2sd  E  close < vwap + 2sd
      janela      E 09:30 <= abertura < 17:00
      nivel       E |close − VAH_ontem| <= 25           (subgrupo de local)
      janela_abs  janela E estimador >= p80, SEM nivel  (subgrupo de absorção)
      barra que toca os dois lados não conta
    CONTINUACAO (a favor do estiramento)
      banda           |z_close| >= 2   (= c_banda)
      janela          E 09:30 <= abertura < 17:00
      primeira_do_dia E primeira barra do dia a satisfazer banda

Para VER no gráfico: `profit-tape vwapvp-ntsl-setupb` gera o indicador
único com os níveis por data e quatro cores (amarelo banda; aqua
banda∧nível; vermelho Setup B completo; fúcsia banda∧absorção sem
nível). As barras aqua são os 9 eventos de 45 pregões — é por isso que
o B morreu.

### Taxa (01/10, 46 dias, cooldown 30 min) — só contagem

    REJEICAO        toque 4,24/dia (191)  janela 3,27 (147; 45% antes das 11h)  nivel 0,02 (1)  janela_abs 0,64 (29)
    CONTINUACAO     banda 3,47 (156)      janela 2,82 (127)                     primeira_do_dia 0,96 (43)
    REJEICAO_NIVEL  fura 3,02 (136)       janela 2,31 (104; plana ao longo do dia)  esticado 0,36 (16)  primeira 0,64 (29)

O que a contagem decide: banda e nível de ontem **não se combinam**
(1 e 16 episódios) — três fichas separadas, nenhuma com as duas
cláusulas. A rejeição na banda é evento de manhã (SD de 200–400 pts); a
rejeição no nível é plana ao longo do dia — não depende da largura da
banda do próprio dia.

### Sonda em fração da distância à VWAP (v3.99) — unidade proposta pelo operador

`ea-vwapvp-sonda`: para a cláusula `janela` de cada evento, excursão a
favor e contra como **fração da distância até a VWAP no sinal** (a
distância varia de 600 a 1.300 pts conforme a hora), a fração de
episódios que alcança 25/50/75/100% dela, e a excursão contra que passa
de 50/100% — por horizonte (5/15/30/60 min) e partida em manhã (< 11h) e
tarde. Continuação: a favor em SD (para longe), contra = volta à VWAP.
Cache v3 grava sonda para todas as barras (rumo à VWAP). FAST-TRACK:
calibração na amostra queimada, declarada; o que sair vira alvo/stop
da ficha uma vez.

### Sonda (01/10, 46 dias) — leitura

- **Rejeição na banda: morta como reversão.** A favor e contra simétricas
  em todo horizonte e metade do dia (tarde 60 min: alcança 50% em 31%,
  passa 50% contra em 31%; manhã: 100% em 54% a favor e 56% contra — a
  banda estreita das 10h é atravessada nos dois sentidos).
- **Rejeição no nível: manhã morta** (VAH de ontem colado na VWAP de hoje,
  frações explodem; em pontos é contra). **Tarde, marginal:** VWAP (100%)
  alcançada em 34% em 60 min vs 15% contra do mesmo tamanho; em 50%
  simétrico. Só 51 de 104 furos têm o lado rumo à VWAP.
- **Continuação à tarde é o único assimétrico com amostra** (88): em 60
  min a favor ≥ 0,5 SD em 60%, ≥ 1 SD em 30%; volta de 50% da distância à
  VWAP em **14%**, 100% em 2%. Mediana 352 pts a favor × 200 contra. De
  manhã simétrico (49% × 41%).

### Regras candidatas — simuladas episódio a episódio (v3.100)

A sonda dá excursões, não a **ordem** em que alvo e stop acontecem.
`ea-vwapvp-regra` simula nas barras M5 do cache: alvo/stop/tempo, custo
11 pts, mesma barra toca os dois = stop (conservador), saída por tempo
ao fechamento. `REGRAS_CANDIDATAS`, declaradas a partir da sonda:
`continuacao_tarde` (alvo 0,5 SD, stop 50% da distância à VWAP, 60 min),
`continuacao_tarde_1sd`, `nivel_tarde_vwap` (alvo e stop = 100% da
distância, só rumo à VWAP), `banda_tarde_meio` (controle, esperado ≈ 0).
Devolve PnL por trade com IC95 da média, saídas, pior dia. Amostra
queimada: o que der positivo com IC acima de zero vai para a demo como
EA; o que não der, fecha.

### Regras simuladas (01/10, 46 dias, custo 11, mesma barra = stop)

    continuacao_tarde      n=88 (1,91/dia)  alvo 52  stop 10  tempo 26  media +47  IC95 [−23, +116]  mediana +163  70% pos  total +4.114  pior dia −766  DD −3.647
    continuacao_tarde_1sd  n=88             alvo 25  stop 12  tempo 51  media +62  IC95 [−21, +145]  mediana +126  61% pos  total +5.483  mediana diária NEGATIVA
    nivel_tarde_vwap       n=41 (0,89/dia)  alvo 10  stop 6   tempo 25  media −29  IC95 [−150, +91]   -> fecha
    banda_tarde_meio       n=81 (controle)  alvo 23  stop 22  tempo 36  media −18  IC95 [−108, +71]   -> ≈ 0 como a sonda previa (simulador sanado)

Decomposição da `continuacao_tarde`: alvo 52 × +241, stop 10 × −587
(2,4 vitórias por stop), tempo 26 × −98. Nenhuma passa no critério "IC
inteiro acima de zero" (precisaria de ~190 trades, 100 pregões).
Decisão do operador em 01/10, fast-track: **vai para a demo como está**;
a demo é a amostra nova. Não se aperta stop nem se corta hora olhando os
88 (seria a terceira olhada na mesma amostra).

## EA `ea_vwapvp_continuacao` (v4.00) — ficha de demo

    EVENTO     barra M5 fechada, abertura em [11:00, 17:00), |close − VWAP| >= 2 SD
               (VWAP de sessão por negócio, SD ponderado por volume, todos os negócios);
               lado a FAVOR do esticão; cooldown 30 min desde o último sinal operado
    ENTRADA    a mercado no 1º negócio após o fechamento (dry_run: preço desse negócio)
    ALVO       entrada ± 0,5 × SD do sinal (~250 pts)     STOP  entrada ∓ 50% da distância à VWAP (~570)
    TEMPO      60 min       ZERAGEM 18:00       LIMITES 6 op/dia, 3 perdas seguidas, −1.200 pts/dia
    TAXA       1,9/dia (27 de 46 dias com trade)
    EFEITO     esperado +47 ± 35 pts/trade (amostra queimada); DD esperado ~3,6 k pts/contrato
    MORTE      escrita antes de ligar: drawdown acumulado > 7.000 pts OU 40 trades com média
               negativa -> desliga e fecha esta ficha. Mudou parâmetro = contagem nova (sha).
    SUBGRUPOS  avaliados OFFLINE nos dados do forward (o serviço loga z, sd, dist, hhmm de
               cada sinal; o tape segue gravado): alvo 1 SD, stop 1 SD, corte por hora, VP
               de ontem como regime. Nenhum vira EA sem contagem nova.

Diferenças declaradas entre o EA e o simulador: entrada no 1º negócio
após a barra (não no close); alvo/stop conferidos negócio a negócio (não
em high/low de barra); níveis de alvo/stop são os do SINAL (close), não
do fill. `ea-vwapvp-servico-replay --dia` roda o código do vivo num dia
do curated para bater com `ea-vwapvp-regra` (mesmos sinais, mesmo lado,
mesma barra — testado no sintético).

**Subida:** `dry_run: true` no YAML; um pregão em dry_run com as barras
de sinal olhadas no gráfico (o `vwapvp_setupb_gerado.ntsl` pinta amarelo
o que o EA chama de sinal, com a ressalva da VWAP por barra); depois
`dry_run: false` e E4 na demo pelo `RUNBOOK_E4.md`. Inclusão a quente
pela pasta `--ea-dir`. Não precisa de `--ea-livro-ao-vivo`.

### Subgrupos da rejeição no nível — declarados 01/10 (noite), só contagem (v4.01)

Do que o operador viu no VAH de 25/09 (a 390 pts do POC; 9,8% do volume
do dia acima dele): a área de valor é assimétrica por construção e a
borda perto do POC é "fina". Borda fina prevê **movimento**, não direção
(é também o LVN do Setup C); quem dá a direção é o regime. Subgrupos,
todos `janela ∧ condição`, contados pelo `ea-vwapvp-taxa`:

    fina          espessura POC→borda furada <= 15 bins (375 pts)
    grossa        > 15 bins
    dentro        VWAP de hoje, na barra do furo, dentro de [VAL, VAH] de ontem
    abriu_dentro  abertura do dia dentro da área de ontem
    fina_dentro   fina E dentro

A saída imprime p25/p50/p75 da espessura nos furos para ver onde o 15
cai. Sonda só depois de contado e declarado qual combinação, se alguma,
vira ficha. Não toca no EA em demo.

### Setup A — declarado e contado (01/10, v4.06), depois de VISTO no pregão

Eu tinha escrito "não testar A como escrito: exige a coincidência de duas
referências móveis" — juízo estrutural, [Provável], sem medição. Em 01/10
o operador viu nos candles 19–23 (10:30–10:50): dia de queda (−3,3 SD às
10:05), pullback até a VWAP (187966→187886) **sentada no platô do POC de
30/09 (187825–187900)**, cinco testes em 25 min, o candle 22 furando até
o VAH de 30/09 (188275, a 10 pts) e fechando abaixo, mínima nova às 11:00.
O Setup A completo, com as duas referências. O juízo estava errado para
esse dia; a contagem diz para quantos.

    RETORNO_VWAP  (a favor do lado esticado s)
      toque      antes nesta sessão |z| >= 2 do lado s; barra toca a VWAP (low <= VWAP <= high)
                 e fecha do lado s
      janela     09:30–17:00
      poc_perto  |VWAP − POC de ontem| <= 250 pts      (a cláusula "VP" do Setup A)
      primeira   primeiro toque do dia

Teste com as barras reais de 01/10 (export do Profit): 10:30 e 10:45
contam; 10:40 (fechou acima da VWAP) e 11:00 (não tocou) não. Só
contagem; sonda e regra pelo mesmo caminho dos outros, se houver taxa.

### Taxa dos subgrupos e do Setup A (01/10, 46 dias)

    REJEICAO_NIVEL  fina 0,36 (16)  grossa 2,00 (90)  dentro 1,24 (56)  abriu_dentro 1,22 (55)  fina_dentro 0,13 (6)
                    espessura POC->borda furada: p25 18  p50 21  p75 43 bins (fina = <= 15 esta' abaixo do p25)
    RETORNO_VWAP    toque 2,20 (99)  janela 1,87 (84; plano no dia)  poc_perto 0,22 (10)  primeira 0,67 (30)

**O padrão de três dias:** o VP de ontem como **ponto** (VAH/VAL a 25 pts,
POC a 250 pts) cai sempre para ~0,2/dia — B e A iguais; como **regime**
(VWAP dentro da área de ontem) fica em ~1,2/dia. É assim que o VP entra
em qualquer ficha deste projeto, se entrar. O Setup A existe como evento
(voltar à VWAP depois de esticão, 1,87/dia) e não como confluência.

Declarado para sonda, duas e mais nenhuma: `retorno_vwap` na janela (84)
e `rejeicao_nivel × dentro` (56) — `ea-vwapvp-sonda --clausula
rejeicao_nivel=n_dentro --clausula retorno_vwap=v_janela`.

### Sondas condicionadas (01/10, fecham A e o regime)

    RETORNO_VWAP tarde (67): contra >= a favor em pontos em todo horizonte (60 min: 330 x 230).
      Depois do pullback a VWAP o preco ATRAVESSA mais do que retoma: o momento ja' se gastou.
      Manha (17): 525 a favor x 420 contra aos 30 min -- volatilidade das 10h, nao direcao.
    REJEICAO_NIVEL x dentro, tarde (43): identica a sem condicao (VWAP alcancada 38% x 34%;
      contra 50% em 51% x 49%; 310 x 295 pts). O regime nao acrescentou nada. Manha morta.

## Veredito final (01/10)

Cinco eventos, duas sondas condicionadas, quatro regras simuladas sobre
46 dias: **uma** assimetria com expectativa positiva (`continuacao_tarde`,
+47 pts/trade, IC cruzando zero), já em demo. O VP de ontem sobreviveu só
como contagem de regime (1,2/dia) e o regime não moveu a sonda. Continuar
declarando eventos sobre os mesmos 46 dias é olhar a amostra pela quinta
vez; esta ficha para aqui.

## Primeiro pregão de dry_run (01/10) e correção de relógio (v4.09)

    ea.vwapvp.resumo: barras 112  sinais 8  operacoes 1  alvo 1  duracao 386 s
                      pnl bruto +330  liquido +319  filtrados: fora_da_janela 2, posicionado 1, cooldown 4
                      codigo entregue-v4.01  config_sha a171e12aa9c0

Contabilidade fecha: 8 = 2 antes das 11h + 1 operado + 1 posicionado + 4
em cooldown (um único episódio de 6 barras na janela). **n=1: não diz nada
sobre a regra.** O que o resumo trouxe e importa: `atraso_max_dia_s=634`
(negócio 55055640, tipo 3, `is_edit=False`, evento 17:22:05 UTC, medido
17:32:40), `fila_pico_ea=4818`.

Lendo o código por causa disso, dois defeitos MEUS no serviço, latentes
(não afetaram o resultado de hoje — a posição durou 386 s):
1. `tick()` comparava relógio de parede com ts de evento: uma entrega
   atrasada de L s antecipava a saída por TEMPO em L s e a zeragem das
   18:00 em L s (só age com o bridge sem fila, mas é o caso de um stall a
   montante). Agora a referência é o relógio de parede em que o último
   negócio CHEGOU, com o tempo de evento extrapolado.
2. Negócio atrasado (ts anterior à barra em formação) levantava
   `TradeForaDeOrdem` até o bridge e deixava `_ultimo_preco`/`_ultimo_ts`
   no valor antigo. Agora é contado (`trades_fora_de_ordem` no resumo),
   avisado (3 primeiros e a cada 100) e ignorado inteiro.
Não muda regra, parâmetro nem o sha do YAML; muda o carimbo de código. O
processo do record em execução ainda roda o código antigo até a próxima
subida.

**Mesmo padrão NÃO tocado:** `service_ignicao.tick` passa o relógio de
parede ao timer de 60 min ("diferença de segundos num timer de 60 min" —
o pressuposto vale para segundos, não para 634 s). Forward em curso, sha
congelado: só registrado.

## Plano forward (operador, 01/10): o pool de seis meses

O operador quer um pool de EAs descorrelacionados em seis meses de
captura, e a barreira nomeada é "se o desenho não for preciso, encerra".
A saída não é adivinhar melhor: **a amostra forward das hipóteses é o
tape, não o EA.** O tape é gravado todo pregão; o cache do replay
reconstrói barras, VWAP, perfil e sondas em segundos. O que fica
congelado hoje é a **definição dos eventos largos** (já em código,
`EVENTOS_DECLARADOS`: furo no nível de ontem 3/dia, toque na banda 4,
retorno à VWAP 2, continuação 3) com espessura, regime, hora, absorção e
distância gravados por barra.

Declarado agora, para não virar escolha depois:

1. **Janeiro/2027 (≈ 60 pregões a partir de 02/10):** rodar `ea-vwapvp-taxa`,
   `ea-vwapvp-sonda` e `ea-vwapvp-regra` SÓ sobre os dias ≥ 02/10 (dados
   que ninguém olhou). As regras candidatas de `REGRAS_CANDIDATAS` são
   as de 01/10; nenhuma nova antes disso.
2. O que der assimetria nesses 60 vira regra declarada e roda em
   `dry_run` por mais 60 (abril): dry_run é o estágio NORMAL de todo
   candidato; E4 é promoção, não ponto de partida. Cinco candidatos em
   dry_run custam zero e não ocupam vaga.
3. Raridade custa tempo linearmente: evento a 0,2/dia dá 25 ocorrências
   em seis meses e não valida nem a 70% de acerto. Um EA raro pode entrar
   no pool **pequeno e declarado como não validado**; não pode entrar
   como validado antes de ~1 ano.
4. O que a família VP acrescentaria ao pool é reversão em nível com
   memória de ontem — o oposto da continuação. É a descorrelação que o
   operador quer; persegue-se pelo caminho 1–2, não na amostra velha.

## Próximo passo

1. Aplicar v4.00; `ea-vwapvp-servico-replay --dia 2026-09-28` e comparar com
   `trades_continuacao_tarde.csv` do mesmo dia.
2. Um pregão em dry_run; olhar as barras de sinal no gráfico.
3. E4 demo. Registrar aqui cada pregão com tag + sha do YAML.

(Histórico da sonda, abaixo.) Operador roda `ea-vwapvp-regra --saida data/vwapvp_regra` e cola; com a TAXA de cada
cláusula, escreve-se a ficha de 6 linhas de (1) e de (2) — EFEITO e
CRITERIO declarados ANTES da sonda — e só então a sonda da ficha
congelada. Nenhum passo nesta ficha. Qualquer desenho seguinte é **ficha nova, pré-registrada
antes de olhar mais dados**, escolhido entre o que a linha de base mostrou
ter amostra: a banda ±2SD (3,5/dia; 7/dia a 1,5) — como **continuação**
(a direção que a linha de base sugere, hipótese invertida à maneira da
H-C2inv) ou com o VP de ontem como **regime** ("abriu dentro/fora da VA")
em vez de toque a 25 pts. A amostra do replay está queimada para as duas;
o teste é forward.

## Onde está a discussão longa

Conversa de 29/09 (projeto profit-tape, chat "VWAP + Volume Profile"):
por que os gatilhos do documento não são discricionários mas
sub-especificados; por que medir o limiar no WIN em vez de importar 3:1
do ES; por que p90 é subgrupo e não segunda variante; por que corretora
não entra no gatilho.
