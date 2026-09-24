# Ficha — IFR2 M15 (retorno à média em extremo)

> **Status:** fechado — **Revisado:** 2026-09-24 — **Assunto:** RSI(2) em extremo como exaustão imediata, WIN M15; CONTRA em dois trials no WIN (IC 97,5% no segundo) e CONTRA no WDO. Família fechada sobre 2015-2026.

## Identidade

| | |
|---|---|
| Linha | preço M15 (`EAS_DE_PRECO.md`) |
| Instrumentos | WINFUT (2 trials), WDO (1 trial) |
| Código | `research/eas_preco.py` (`--ficha ifr2`), `research/eas_preco_teste.py` |
| Config de EA | nenhuma — nunca chegou a EA |
| Hashes de ficha | trial 1 `449b012649c4`; trial 2 `a0ee1342c69e`; WDO `5aaa0f6ac7fc` |

## Fase e estado

**F4 — REPROVADA. Família FECHADA** sobre 2015-2026 nos dois futuros
(2026-09-14 no WIN, 09-15 no WDO). Sem trial 3: qualquer variante (RSI
≤ 5, saída por RSI 50, outro timeframe) é família nova, em amostra que
estes testes não tocaram.

## Mecanismo em uma frase

No WIN em M15, RSI(2) em extremo é exaustão imediata: entrando a mercado
na barra seguinte, a primeira excursão de K × ATR14 vai a favor mais de
50% das vezes.

## Regras

Convenções de `docs/eas/README.md`, mais:

- COMPRA: RSI2(t) ≤ 10 (Wilder); VENDA: RSI2(t) ≥ 90. Um sinal por
  excursão (t−1 fora do extremo). t fecha entre 09:15 e 16:30; t+1 no
  mesmo pregão.
- Entrada = open(t+1), a mercado. D = K × ATR14(t) ao tick; alvo =
  entrada + D, stop = entrada − D (espelho na venda).
- Regime MME80 = **estrato reportado**, não cláusula.
- Resolução: primeira barra ≥ t+1 do dia em que alvo ou stop cabem em
  [low, high]; os dois = AMBÍGUA; dia acaba sem tocar = POR TEMPO.

## Pré-registro congelado — trial 1, K = 0,5 (2026-09-13, `entregue-v2.61`)

    TAXA       3,51 (2026) e 3,54 (2023-25) sinais/pregão.
    EFEITO     p1 ≥ 0,56 contra ≤ 0,50; ±3 pp → n = 1.070.
    CUSTO MAX  D × (2p1 − 1); D mediano 175-245 → p1 de empate 0,52-0,53.
    AMOSTRAS   TESTE 2023-25 (749 pregões, uma rodada); REPLICAÇÃO 2026
               até 13/08; DEPURAÇÃO 14/08+.
    CRITERIO   p1 ≥ 0,56 FAVORÁVEL; ≤ 0,50 CONTRA; entre INCONCLUSIVO. IC95.
    PARADA     depuração → teste → replicação. Número mudado = hash novo.

Porta de volume declarada (não implementada): `absorcao` na barra de
sinal como gate — hipótese nova.

## Trial 2 — K = 1 (declarado 2026-09-14 antes de rodar, `entregue-v2.63`)

Só K mudou (0,5 → 1,0). Preço de reutilizar 2023-25: **IC 97,5%**
(Bonferroni) e FAVORÁVEL exige limite inferior > 0,50. Declarado: sem
trial 3 qualquer que fosse o resultado.

## Resultados

| trial | amostra | resolvidas | ambíguas | p1 | IC | P&L bruto/op | veredito |
|---|---|---|---|---|---|---|---|
| 1 (K=0,5) | TESTE 2023-25 | 2.452 | 7,4% | **0,492** | 95%: [0,472; 0,512] | −4,8 | **CONTRA** |
| 1 | REPLICAÇÃO 2026 | 492 | 7,7% | 0,482 | [0,438; 0,526] | −6,9 | contra (reportada) |
| 2 (K=1) | TESTE 2023-25 | 2.478 | 0,9% | **0,486** | 97,5%: [0,464; 0,509] | −9,5 | **CONTRA** |
| 2 | REPLICAÇÃO 2026 | 491 | 0,4% | 0,479 | [0,429; 0,529] | −13 | contra (reportada) |
| WDO (trial 1 da família no WDO) | combinado 2015-26 | 8.612 | — | 0,492 | 95%: [0,482; 0,503] | −0,3 | **CONTRA** |

Nenhum estrato (a favor/contra MME80, compra/venda) com IC fora de 0,50
em nenhum trial.

## Veredito

**CONTRA, nulo a custo zero.** O teto do IC nem paga o custo (D 175 ×
0,024 = 4 pts brutos contra 11). Aprendizado da categoria: reversão à
média pública em M15 está arbitrada.

## Próximo passo

Nenhum. Lápide.

## Onde está a discussão longa

`EAS_DE_PRECO.md` §3 (3.0 a 3.5) e §8.1c (WDO); catálogo de hipóteses
mortas em `RESEARCH_PLANO.md` ("COMO GERAR E REFINAR HIPOTESE", item 4).
