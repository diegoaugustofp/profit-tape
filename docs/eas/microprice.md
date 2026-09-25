# Microprice / queue imbalance (WIN) — fast-track

> **Status:** protótipo — **Criado:** 2026-09-24 (v3.63) — **Assunto:** scalper de topo de livro no WINFUT, em modo fast-track (sem pré-registro longo); config `config/ea_microprice.yaml`, código `ea/sinal_microprice.py` + `ea/service_microprice.py`.

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

Nenhum ainda.
