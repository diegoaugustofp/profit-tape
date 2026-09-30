# VWAP + Volume Profile (WIN) — fast-track

> **Status:** F2 — primeira rodada real feita (30/09, 46 dias): **Setup B com VP de ontem morto por taxa como escrito** (0,20 episódios/dia no local); barras validadas contra o Profit (112/113); rerodar em v3.91 com z contínuo, estimador de absorção corrigido, dias truncados excluídos e as variantes declaradas — **Criado:** 2026-09-29 (v3.86); F2 em v3.87–v3.89 — **Código:** `ea/vwap_sessao.py`, `ea/perfil_preco.py`, `research/vwapvp_conferir.py`, `research/vwapvp_replay.py`, comandos `vwapvp-conferir` e `ea-vwapvp-replay` — **Origem:** documento "A integração da VWAP e Volume Profile" (3 setups), decisões desta ficha tomadas em conversa de 29/09.

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

### F2 — segunda rodada (v3.91, a fazer)

Comando (a primeira rodada com cache custa ~1 min/dia; depois, segundos):

    profit-tape ea-vwapvp-replay --saida data/vwapvp_f2

Devolve: percentis 50/80/90/95 do estimador (p80 e p90 **congelados como
valor** — copiar para cá e para o YAML do F3); episódios por cláusula
(banda → nível → absorção → janela) por dia e por hora; sonda MFE/MAE/toque
na VWAP em 5/15/30/60 min para `c_nivel` (só local) e `c_janela` (evento
completo) e o subgrupo p90; diferença VAL/VAH bin a bin × pares; largura
2SD por hora. Nada é escolhido por resultado; os parâmetros são os desta
ficha.

## Veredito

Nenhum.

## Próximo passo

1. Operador roda `ea-vwapvp-replay --saida data/vwapvp_f2` (v3.89) e cola a
   saída: p80/p90 com z contínuo, tabela das 4 variantes, escolhida ou
   abandono.
2. Se houver escolhida: congelar p80/p90, fechar TAXA/HORIZONTE, EFEITO e
   CRITERIO da sonda dela, hora de início. Se abandono: fechar esta ficha
   com veredito "abandonado por taxa" e abrir a próxima.
3. F3: `sinal_vwapvp.py` + `service_vwapvp.py` + `config_vwapvp.py` + tipo
   `vwap_vp` no registro + YAML com os valores congelados; dry_run, um
   pregão com barras olhadas uma a uma.

## Onde está a discussão longa

Conversa de 29/09 (projeto profit-tape, chat "VWAP + Volume Profile"):
por que os gatilhos do documento não são discricionários mas
sub-especificados; por que medir o limiar no WIN em vez de importar 3:1
do ES; por que p90 é subgrupo e não segunda variante; por que corretora
não entra no gatilho.
