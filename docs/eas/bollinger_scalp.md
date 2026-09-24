# Ficha — Scalp de Bollinger modificada (15 s), três variantes + filtro de book

> **Status:** fechado (suspensa) — **Revisado:** 2026-09-24 — **Assunto:** scalp intradiário em barras de 15 s sobre banda estreita, com replay pelo tape; três variantes INCONCLUSIVAS (o CONTRA foi revogado em 23/09 porque os sinais vêm em clusters de 2,56); pendente um teste retrospectivo em amostra limpa da variante com filtro de book quando n ≥ 60.

## Identidade

| | |
|---|---|
| Linha | preço 15 s + estocástico de 6 min + (última variante) topo do livro (`tiny_book`) |
| Instrumento | WINFUT |
| Código | `research/bollinger_scalp.py`, `bollinger_replay.py`, `bollinger_contexto.py`, `diagnostico_multitf.py`; NTSL `ntsl/bollinger_scalp.ntsl` |
| Config de EA | nenhuma — nunca chegou a EA nem a forward |
| Origem | especificação do operador, 2026-09-04 |

## Fase e estado

**F4 — SUSPENSA (2026-09-24).** Nenhuma variante mostrou borda; nenhuma
foi refutada com o rigor declarado. Decisão de 24/09: **sem forward**;
a regra da variante 10.1 fica congelada e um teste retrospectivo roda
na PRIMEIRA vez em que a amostra limpa (pregões a partir de 2026-09-09)
atingir **n ≥ 60 operações** — não antes, não depois. A ~3,2 op/pregão,
início de outubro.

## Mecanismo em uma frase

Na manhã do WIN, com o preço trabalhando acima de uma banda estreita
(0,38 σ / 21 em 15 s), uma correção de uma barra seguida de retomada é
continuação; compra-se o reteste (v1 retorno) ou o rompimento (v1
rompimento) com stop de 0,7 × ATR21 e alvos de 1 / 1,625 / 2,5 stops.
As variantes seguintes acrescentam um filtro de contexto (estocástico
lento de 6 min < 20 / > 80) e um filtro de resistência à frente
(desequilíbrio do topo do livro).

## Regras comuns (todas as variantes)

- Barra de 15 s, indicadores reiniciados a cada pregão; janela da 22ª
  barra até 12:59:45; zeragem 17:30.
- Compra: t−2 vermelha com close > B_sup; t−1 branca com close > B_sup.
  Venda: espelho na banda inferior.
- Lote 3; stop 0,7 × ATR21(t−1) ao tick; alvos 1 / 1,625 / 2,5 stops;
  trailing nas pernas 2 e 3 (ativa a 0,625, puxa 0,25 atrás, passo
  0,125). Circuit breaker de 3 perdas. Custo 11 pts/contrato.
- Estimador: p1 = alvo1 antes do stop, na perna 1 (nula 0,50); borda
  bruta em pts/op (IC95). Custo máximo suportado = alerta, não veredito.

## Pré-registros (na ordem)

### v1 retorno (2026-09-04/05, `entregue-v2.11`)
Limitada de compra em high(t−2), válida em t. n alvo 1.070 (±3 pp),
decisão em n=370; p1 ≥ 0,56 favorável; ≤ 0,50 contra.

### v1 rompimento (2026-09-11)
Limitada em high(t−1). Mesmo critério.

### Rompimento + estocástico de contexto (2026-09-23, §8)
Filtro: %K lento (8/3) de 6 min, da última barra de 6 min fechada antes
de t: compra < 20, venda > 80. **3ª tentativa da família → Bonferroni
α = 0,05/3, IC 98,3%** da borda bruta; poder exige n ≥ 60. Um tiro.
Depois de rodar descobriu-se **defeito de especificação**: a "limitada"
nunca esperava romper (§9); remedição pré-registrada com ordem STOP
(§9.4), mesma amostra, mesmo critério.

### Filtro de book "menos resistência à frente" (2026-09-23, §10.1)
Regra do rompimento + contexto, MAIS: compra passa se desequilíbrio
= (qtd_bid − qtd_ask)/(qtd_bid + qtd_ask) > 0 no último estado do
`tiny_book` na barra do sinal; venda se < 0. Taxa ~3,2 op/pregão.
Critério: IC95 de Wilson de p1 vs 0,50. Poder declarado antes:
detecta bem que é RUIM, mal que é BOA (p1 0,47 ficaria invisível em 6
meses). Não trocar o corte de 0 pela mediana depois; RLP é hipótese
independente, fica fora.

## Resultados (replay pelo tape, 32-42 pregões, 24/07 a 08/09 — quatro rodadas sobre três variantes)

| variante | n | p1 | IC95 p1 | borda bruta pts/op | IC da borda | veredito original | veredito final |
|---|---|---|---|---|---|---|---|
| v1 retorno (limitada em high(t−2)) | 417 | 0,480 | 0,432–0,528 | −4,7 | −21,6 a +12,2 | null | **INCONCLUSIVO** |
| v1 rompimento (limitada em high(t−1)) | 289 | 0,415 | 0,360–0,473 | −22,0 | −43,0 a −0,9 | CONTRA (5.8) | **INCONCLUSIVO** (revogado, §12) |
| rompimento + contexto, limitada (§8.7) | 320 | 0,438 | 0,384–0,492 | −26,0 | 98,3%: −47,7 a −4,3 | CONTRA | **INCONCLUSIVO** (revogado, §12) — e a limitada era defeito de especificação (§9) |
| rompimento + contexto, ordem STOP (§9.5) | 271 | 0,432 | 0,374–0,491 | −18,1 | 98,3%: −39,9 a +3,7 | INCONCLUSIVO | **INCONCLUSIVO** |

**Clustering medido (2026-09-23, `diagnostico-multitf`):** 616 sinais
em 241 janelas de 6 min → cluster médio 2,56 (máx. 7), n efetivo 241.
Com deff 2,56 o IC da limitada vai a (−54,5; +2,5). **O CONTRA de 5.8 e
8.7 está REVOGADO**: assumia independência que o dado não sustenta.

Validações fechadas: indicadores de 15 s vs Profit `dif_max = 0,0`;
estocástico de 6 min `dif_max = 0,0`; OHLC de 6 min diverge com 0,81%
de impacto na decisão (cosmético, §15); ordem stop implementada e o
defeito da limitada corrigido.

## Veredito

**INCONCLUSIVO nas três variantes.** "Não achamos borda" não é
"provamos que não há" — a distinção epistêmica importa, mesmo que nada
vá a produção de qualquer forma.

## Próximo passo

Teste retrospectivo da regra 10.1 (rompimento + contexto + book) na
primeira vez em que a amostra limpa (≥ 2026-09-09) tiver n ≥ 60.
Critério e regra: os de 10.1/10.2, sem alteração. Desfecho mais
provável, declarado antes: INCONCLUSIVO.

## Onde está a discussão longa

`BOLLINGER_SCALP.md` inteiro — §0 (ficha v1), §5.7-5.8 (fechamento das
duas v1), §8 (pré-registro contexto), §9 (defeito e remedição), §10
(ficha de book), §11-12 (clustering), §13 (decisão sem forward), §15
(estado final).
