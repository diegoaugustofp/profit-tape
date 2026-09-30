# VWAP + Volume Profile (WIN) — fast-track

> **Status:** F2 — F1 conferido contra o Profit (25/09 e 28/09); replay entregue, **ainda não rodado no curated real** — **Criado:** 2026-09-29 (v3.86); F2 em v3.87 — **Código:** `ea/vwap_sessao.py`, `ea/perfil_preco.py`, `research/vwapvp_conferir.py`, `research/vwapvp_replay.py`, comandos `vwapvp-conferir` e `ea-vwapvp-replay` — **Origem:** documento "A integração da VWAP e Volume Profile" (3 setups), decisões desta ficha tomadas em conversa de 29/09.

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
| "absorção / exaustão" | `absorcao_dir = imbalance − desloc_norm`, z de 50 barras M5 — o estimador que já existe (`absorcao_dir.ntsl`, `research/absorcao_barra.py`) | reuso; **sozinho foi REPROVADO no IC em 30/08** (CONTRA nas 12 células). Aqui é gate em LOCAL, hipótese diferente; não é evidência |
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

### F2 — replay

Não rodado no curated real (o sandbox não o tem). Comando:

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

1. Operador roda `ea-vwapvp-replay --saida data/vwapvp_f2` (todos os dias do
   curated; 24/07 é o primeiro e não tem referência) e cola a saída aqui.
2. Com a saída: congelar p80/p90, fechar TAXA e HORIZONTE, escrever EFEITO e
   CRITERIO a partir da sonda (alvo/stop em pontos), decidir a hora de
   início. Se HORIZONTE > 6 meses, afrouxar **antes** de ligar e anotar.
3. F3: `sinal_vwapvp.py` + `service_vwapvp.py` + `config_vwapvp.py` + tipo
   `vwap_vp` no registro + YAML com os valores congelados; dry_run, um
   pregão com barras olhadas uma a uma.

## Onde está a discussão longa

Conversa de 29/09 (projeto profit-tape, chat "VWAP + Volume Profile"):
por que os gatilhos do documento não são discricionários mas
sub-especificados; por que medir o limiar no WIN em vez de importar 3:1
do ES; por que p90 é subgrupo e não segunda variante; por que corretora
não entra no gatilho.
