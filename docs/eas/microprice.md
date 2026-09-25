# Microprice / queue imbalance (WIN) — fast-track

> **Status:** DESCARTADO como taker (2026-09-25); passiva pendente de modelo de fila — **Criado:** 2026-09-24 (v3.63), **revisado** 2026-09-25 (v3.64) — **Assunto:** scalper de topo de livro no WINFUT, em modo fast-track (sem pré-registro longo); config `config/ea_microprice.yaml`, código `ea/sinal_microprice.py` + `ea/service_microprice.py`.

## Identidade, fase e estado

EA `tipo: "microprice"` na esteira multi-EA. **Fase:** protótipo em
dry_run; nenhum pregão rodado, nenhum replay lido ainda.

## Mecanismo em uma frase

Fila do bid muito maior que a do ask (I ≫ 0) tende a ser consumida por
último: o próximo movimento do mid é mais provável para cima.

## Por que o limiar é em I e não em ticks

`microprice = mid + I·spread/2`, logo `|microprice − mid| ≤ spread/2`.
No WIN (spread mediano 1 tick = 5 pts) o microprice nunca se afasta do
mid mais que 2,5 pts nem do último negócio mais que 1 tick. "Desvio > X
ticks" com X ≥ 1 só dispararia com spread largo. Conferido à mão:
bid 100000×300 / ask 100005×100 → 100003,75.

## O obstáculo conhecido antes de rodar

Taker nos dois lados: a operação nasce em −1 spread (−5 pts) e ainda
paga `custo_pontos_estimado` (11 pts). Break-even ≈ mid andando ~3 ticks
a favor. O desbalanço de topo, na literatura, prevê o **próximo tick**
— não três. Por isso existe a SONDA: separa "prevê?" de "paga o custo?".
Se a sonda for positiva e as operações negativas, o próximo passo é
entrada PASSIVA (limitada no próprio lado), não outro limiar.

## Regras

- Entrada: I ≥ `limiar_entrada` (compra, paga o ask) ou ≤ −limiar
  (vende, paga o bid), persistindo `persistencia_ms`, com spread ≤
  `spread_max_ticks`, topo ≥ `qtd_min_topo`, livro com menos de
  `livro_max_idade_ms`, dentro de `janela_inicio/fim`, fora do cooldown.
- Saída (primeiro que ocorrer): alvo, stop (marcados no lado oposto),
  `I·lado ≤ −limiar_saida`, `tempo_max_s`, fim da janela.
- Dia: bloqueia em `max_perdas_seguidas` ou `perda_max_dia_pontos`.

## Ficha rápida (forward)

    HIPOTESE   I no topo prevê a direção do mid no curto prazo
    EVENTO     o de cima, com os parâmetros do yaml (sha no log)
    TAXA       a medir no replay (ops/pregão)
    CRITERIO   sonda h5s media_pts > 0 E liquido/op > 0 no replay; só
               então 1 pregão ao vivo em dry_run; só então E4 em demo
    PARADA     mudou parâmetro = contagem nova (carimbo config_sha)

## Como rodar

    profit-tape ea-micro-replay config/ea_microprice.yaml --de 2026-09-10
    # ao vivo, dry_run, com o livro ligado:
    profit-tape record ... --ea-dir <pasta> --ea-livro-ao-vivo --ea-modo-ticker exclusivo

## Resultados

### v3.63 — replay 24/09 (config `2eca75e3eba3`, custo 11, taker) — DEPURAÇÃO

Um pregão, não decide nada; serve para achar defeito.

- Sonda (3.334 bordas): mid a favor +0,90 pt em 1 s (39,7% a favor /
  24,6% contra), +1,55 em 5 s, +3,69 em 30 s. **Prevê direção; o tamanho
  é pequeno.**
- 12 operações, 1 ganho, bruto −50, líquido −182; bloqueou por 8 perdas
  seguidas. Duração média **0,39 s**, 8 de 12 saídas por
  `imbalance_inverteu`: a saída disparava na primeira piscada de I (sem
  persistência, avaliado a cada 50 ms). As operações mediram o SPREAD,
  não o sinal — defeito de desenho, corrigido no v3.64.
- `livro_cruzado` 19.660 e `spread_largo` 55.859 avaliações. Suspeita:
  o tiny_book chega um lado por mensagem e o topo reconstruído trava
  entre as duas. v3.64 mede.

### Custo real (nota do operador, 24/09)

2 idas e voltas de 1 contrato: bruto R$ 119,00, líquido R$ 116,19. Da
diferença de R$ 2,81, R$ 1,19 é IRRF de 1% (antecipação de IR, não
custo). Taxas: R$ 1,62 / 2 = **R$ 0,81 ≈ 4 pts por ida e volta**. O
default de 11 pts do projeto superestimava ~3×.

Break-even do mid, com custo 4: taker/taker > 9 pts; passiva/taker > 4;
passiva/passiva > −1 (se o fill não for adverso).

### v3.64 — mudanças (contagem nova: `config_sha` muda)

- `persistencia_saida_ms: 300` — a inversão de I também tem que durar.
- `sonda_refratario_s: 5` — re-gatilho do mesmo lado em < 5 s não conta.
- `custo_pontos_estimado: 4.0`.
- Variante `config/ea_microprice_passiva.yaml`: limitada no próprio lado,
  fill pessimista pelo topo (compra em P executa com ask ≤ P ou bid < P,
  isto é, assume fim da fila), cancela só por validade (2 s). Não cancela
  na inversão: no replay sem latência isso evitaria exatamente os fills
  adversos. Só dry_run/replay.
- Replay imprime `cruzado:` — episódios, duração p50/p90/p99/máx, % até
  50 ms e amostras com a idade do lado não atualizado.

**Leitura do próximo replay:** se `cruzado` tiver p90 ≤ ~50 ms, é
artefato de reconstrução (e o filtro já o descarta). Se durar segundos,
é outra coisa — olhar as amostras antes de interpretar o I.

### v3.64 — 10 pregões (10/09–23/09, config `538457d8a0d0`, taker) — VEREDITO

346 operações, bruto −1.435 (−4,1/op ≈ o spread), líquido −2.819. Todos
os dias negativos. Sonda: h1s positiva em **10/10 dias** (+0,80 a +1,33),
h5s em 10/10 (+0,57 a +1,69); h30s entre −0,02 e +3,36 — tendência do
dia, não sinal (o +4,7 de 24/09 era isso). Livro cruzado: p90 1,5–3,2 ms
em todos os dias; as amostras longas são o leilão de abertura.

**Veredito: taker DESCARTADO.** O sinal é real e estável (~+1,2 pt em
1–5 s) e ~8× menor que o break-even taker (~9). Passiva: não medida com
honestidade — o fill pessimista só executa depois de o preço andar 1 tick
contra. Reabre só com modelo de posição na fila pelo tape. Uso possível
do I: FILTRO para outros EAs (não entrar contra desbalanço forte).
