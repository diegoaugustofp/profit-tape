# Fichas de estratégia — índice

> **Status:** vivo — **Revisado:** 2026-09-25 — **Assunto:** uma ficha por estratégia/EA (vivas e mortas), com o pré-registro congelado, os resultados por trial e o veredito; é o único lugar onde o estado de uma estratégia é mantido.

## Regra de dono

A ficha é o **documento de origem** do estado de cada estratégia. As
tabelas de `EA_ARQUITETURA.md` §1 e de `ESTADO_E_CAMINHOS.md` §1 apontam
para cá e não têm autoridade própria; se divergirem da ficha, a ficha
vence e a tabela é corrigida.

Cada ficha tem as mesmas seções, nesta ordem: identidade; fase e estado;
mecanismo em uma frase; regras (o suficiente para reimplementar);
pré-registro congelado (com a tag); resultados por trial; veredito;
próximo passo; onde está a discussão longa. **O pré-registro congelado
não se edita** — uma versão nova empilha abaixo, com o que a motivou.

## As estratégias

| ficha | linha | fase | veredito | trials consumidos | tag/ref |
|---|---|---|---|---|---|
| [`z_agf_3.md`](z_agf_3.md) — venda + Rota B | fluxo (tape) | **F5** montado, sem ordem real disparada | sinal validado no IC; Rota B como controle de drawdown (stop não detecta reversão) | — (sinal validado antes do regime de trials) | v2.47 |
| [`deepscalper_fase2.md`](deepscalper_fase2.md) — classificador | fluxo (tape) | **F3→F4**, forward ligado 2026-09-11 | placar fechado; sanidade n=50 OK (2026-09-24) | 1 (em curso) | v2.04 / v3.58 |
| [`bollinger_scalp.md`](bollinger_scalp.md) — 3 variantes + book | preço 15 s + book | **F4 — SUSPENSA** | INCONCLUSIVO nas três (CONTRA revogado em 23/09); teste retrospectivo em amostra limpa pendente (n ≥ 60) | 3 | v2.11 … v3.59 |
| [`ifr2_m15.md`](ifr2_m15.md) | preço M15 | **F4 — FECHADA** | CONTRA (2 trials WIN, IC 97,5%; CONTRA no WDO) | 2 (WIN) + 1 (WDO) | v2.61, v2.63, v2.82 |
| [`orb_m15.md`](orb_m15.md) | preço M15 | **F4 — FECHADA** | CONTRA no combinado 2015-26 (WIN); INCONCLUSIVO no WDO | 1 (WIN) + 1 (WDO) | v2.64, v2.65, v2.82 |
| [`123_m15.md`](123_m15.md) — puro | preço M15 | **F4 — INCONCLUSIVO; F5 como PORTADOR** (7a fechado 21/09) | p1 0,5285 IC [0,515; 0,542], n=5.444: real, pequeno; não replica no WDO | 1 (WIN) + 1 (WDO) | v2.67, v2.82 |
| [`123_gate_volume_alto.md`](123_gate_volume_alto.md) — ficha 9 | preço + volume de candle | **F4 — FECHADA** | hipótese FALSA no sentido declarado; o complemento gerou a ficha abaixo | 1 (WIN) | v2.85 |
| [`123_volume_baixo.md`](123_volume_baixo.md) — ficha 12 | preço + volume de candle | **F4 INCONCLUSIVO no WDO; é o GATE do 123 no forward** | WDO 0,534 IC [0,516; 0,552]; atravessa a quebra de 2020 nos dois instrumentos | 1 (WDO) | v2.86, v2.89 |
| [`gap_abertura.md`](gap_abertura.md) — ficha 10 | preço M15 (noite) | **F4 — congelada; resultado só no catálogo** | "inconclusivo, por-ano sem padrão" — tabela n/p1/IC não está no repositório | 1 (WIN, a confirmar) | v2.94 |
| [`vespera.md`](vespera.md) — ficha 11 | preço M15 (dia anterior) | **F3 — FECHADA sem p1** | estimador não serve em M15 (v0: 78% por tempo; v1: 54-74% ambígua) | 0 | v2.92, v2.93 |
| [`microprice.md`](microprice.md) — fast-track | topo do livro (tiny_book) | **DESCARTADO como taker**; passiva pendente de modelo de fila | sinal real e estável (~+1,2 pt em 1–5 s, 10/10 dias), ~8× menor que o break-even taker | 0 (fast-track) | v3.63, v3.64 |
| [`ignicao.md`](ignicao.md) — fast-track | tape (WIN) | **F5 — forward em dry_run** a partir de 28/09 | estudo FAVORÁVEL: p_alvo 0,702 IC [0,560; 0,813], 47 decididos em 44 pregões (escolha cega + replicação) | forward em curso | v3.66–v3.68 |

## Convenções compartilhadas pelas fichas de preço (M15)

Valem para IFR2, ORB, 123 e derivadas, gap e véspera, salvo onde a ficha
diz o contrário (`EAS_DE_PRECO.md` §2):

- Barra M15, WINFUT, indicadores contínuos entre pregões. Tick = 5 pts;
  meio-tick arredonda para cima.
- Regime: MME80 do fechamento — cláusula ou estrato conforme a ficha.
- Uma posição por vez por EA; sinal com posição aberta é ignorado
  (`ignorado_posicao`, contado, fora do p1).
- Última entrada: barra que fecha até 16:30; zeragem forçada 17:30.
  Operação zerada por tempo não conta no p1 (reportada à parte).
- ATR14 = SMA14 do TrueRange (variante que o Profit calcula).
- Custo: 11 pts ida e volta por contrato.
- Estimador binário: p1 = fração em que a barreira favorável (alvo) é
  tocada antes da desfavorável (stop); nula a custo zero = 0,50.
  Barra que toca as duas = AMBÍGUA (excluída, reportada).
- Critério: p1 ≥ 0,56 e IC acima de 0,50 = FAVORÁVEL; p1 ≤ 0,50 =
  CONTRA; entre = INCONCLUSIVO = fecha. IC95 de Wilson (97,5% no
  segundo trial de uma família na mesma amostra).
- Amostras por data: DEPURAÇÃO 2026-08-14+ (não interpretável); TESTE
  2023-25 (primário, uma rodada); REPLICAÇÃO 2026 até 13/08; HISTÓRICO
  out/2015-2022; veredito no COMBINADO quando a sequência foi declarada.
- Capital nunca restringe uma ficha (`EA_ARQUITETURA.md` 4.9): é
  reportado, o operador decide.
