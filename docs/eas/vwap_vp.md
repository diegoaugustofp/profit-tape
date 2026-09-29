# VWAP + Volume Profile (WIN) — fast-track

> **Status:** F1 — módulos puros entregues e conferíveis; nenhum replay, nenhum pregão rodado — **Criado:** 2026-09-29 (v3.86) — **Código:** `ea/vwap_sessao.py`, `ea/perfil_preco.py`, `research/vwapvp_conferir.py`, comando `vwapvp-conferir` — **Origem:** documento "A integração da VWAP e Volume Profile" (3 setups), decisões desta ficha tomadas em conversa de 29/09.

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

## Ficha rápida (forward) — a completar em F2

    HIPOTESE   preço em ±2SD ∧ VAH/VAL de ontem ∧ absorção acima de p80 volta à VWAP
    EVENTO     barra M5 fechada com: |z_vwap| >= 2; |close − VAH| <= 25 pts (venda) ou
               |close − VAL| <= 25 (compra); absorcao_dir·lado >= p80 (valor congelado);
               09:30–17:00; sem posição; fora de cooldown
    TAXA       A MEDIR EM F2, por cláusula (±2SD só / +VAH-VAL / +absorção / +janela)
    EFEITO     p_alvo >= 0,58 vs 0,50 (binário: VWAP antes do stop)
    HORIZONTE  A CALCULAR de TAXA × EFEITO; se > 6 meses, afrouxar (±1,5SD ou tolerância 50)
    CRITERIO   IC 95% de p_alvo acima de 0,50 = favorável; abaixo = contra; cruza = inconclusivo
    PARADA     olhar só no n da linha HORIZONTE. Subgrupos declarados (p90, z_agf_3 >= 1,4,
               com/sem RLP) respondem DEPOIS do principal e não autorizam trocar o gatilho.
               Mudou parâmetro = contagem nova (carimbo tag + sha do YAML).

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

    profit-tape vwapvp-conferir --dia 2026-09-26 --dia 2026-09-29 --histograma-csv out/vp.csv

No Profit, mesmo dia: VWAP com bandas de 2 desvios e Volume Profile com
área de valor 70%. Devem bater em até 1 bin. Se "todos" não bater e
"agressao_rlp" bater, o gráfico exclui o leilão — anotar aqui e trocar o
D3 **antes** de F2, nunca depois.

## Resultados

Nenhum. F1 entregue em v3.86 sem dado real olhado — o sandbox não tem o
curated. A conferência é do operador.

## Veredito

Nenhum.

## Próximo passo

1. Operador roda `vwapvp-conferir` em 2–3 dias e bate contra o Profit;
   anota aqui o que divergiu (algoritmo da área de valor, conjunto de
   negócios, bin).
2. F2 (v3.87): `ea-vwapvp-replay` sobre o curated — distribuição do
   estimador de absorção por barra M5 (p80/p90 congelados como valor),
   eventos/pregão por cláusula, distância ±2SD→VWAP por horário, sonda em
   1/5/15 min. Só então a ficha rápida fecha TAXA/HORIZONTE.
3. F3: EA na esteira, dry_run, um pregão com barras olhadas uma a uma.

## Onde está a discussão longa

Conversa de 29/09 (projeto profit-tape, chat "VWAP + Volume Profile"):
por que os gatilhos do documento não são discricionários mas
sub-especificados; por que medir o limiar no WIN em vez de importar 3:1
do ES; por que p90 é subgrupo e não segunda variante; por que corretora
não entra no gatilho.
