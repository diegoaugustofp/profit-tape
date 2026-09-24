# Ficha — ORB M15 (rompimento do range de abertura)

> **Status:** fechado — **Revisado:** 2026-09-24 — **Assunto:** rompimento do range 09:00-09:30 com alvo/stop de uma amplitude; INCONCLUSIVO no teste, CONTRA no combinado de dez anos (WIN); INCONCLUSIVO no WDO. Capítulo fechado.

## Identidade

| | |
|---|---|
| Linha | preço M15 |
| Instrumentos | WINFUT, WDO |
| Código | `research/eas_preco.py` (`--ficha orb`), `eas_preco_teste.py`, `eas-preco-combinar` |
| Config de EA | nenhuma |
| Hash de ficha | WIN `7ae066bb3efb`; WDO `fad0bc2bf119` |

## Fase e estado

**F4 — REPROVADA (CONTRA no combinado). Capítulo fechado** (2026-09-14
WIN; 09-15 WDO). Sem trial 2.

## Mecanismo em uma frase

O range das duas primeiras barras M15 concentra a decisão do dia: o
primeiro rompimento dele continua por mais uma amplitude do range antes
de voltar a amplitude oposta.

## Regras

Convenções de `docs/eas/README.md`, mais:

- R_high/R_low = max/min das barras 09:00 e 09:15; A = R_high − R_low ≥
  20 pts.
- Das 09:30 até a barra 11:45 inclusive: ordens STOP OCO em R_high +
  tick (compra) e R_low − tick (venda). Primeira barra que toca um nível
  é o gatilho; toca os dois = gatilho ambíguo, pregão fora.
- Entrada = nível rompido. **D = A** ao tick; alvo = entrada + D, stop =
  entrada − D. Uma operação por pregão.
- Regime (close 09:15 vs MME80) = estrato.
- Resolução a partir da barra do gatilho inclusive; stop tocado nela =
  AMBÍGUA; 17:30 sem tocar = POR TEMPO.

## Pré-registro congelado (2026-09-14, `entregue-v2.64`)

    TAXA       0,964 (2023-25) / 0,977 (2026) sinais por pregão.
    EFEITO     ±3,9 pp no teste (636 resolvidas); enxerga 0,56 vs 0,50.
    POR TEMPO  11,6% / 23,5% (fora do p1; P&L na zeragem reportado).
    AMBIGUA    0,3% / 0%.
    AMOSTRAS   DEPURAÇÃO 14/08+ → TESTE 2023-25 → REPLICAÇÃO 2026.
    CRITERIO   como IFR2; estratos reportados sem veredito. IC95.

**Replicação 2 declarada antes de rodar (2026-09-14, `entregue-v2.65`):**
todo o histórico não tocado (out/2015-dez/2022) entra inteiro; veredito
FINAL no combinado teste + replicação + histórico (~2.400 resolvidas,
±2 pp); por-ano reportado como estrato. Sem terceira replicação.

## Resultados

| amostra | pregões | resolvidas | por tempo (zeragem) | p1 | IC95 | P&L bruto/op | veredito |
|---|---|---|---|---|---|---|---|
| TESTE 2023-25 | 749 | 636 | 84 (−47) | 0,524 | [0,485; 0,562] | +37 | INCONCLUSIVO |
| REPLICAÇÃO 2026 | 154 | 115 | 34 (−10) | 0,496 | [0,406; 0,586] | −9 | contra (reportada) |
| HISTÓRICO 2015-22 | 1.782 | 1.631 | 87 (+26) | 0,478 | [0,454; 0,503] | −29 | |
| **COMBINADO (WIN)** | 2.685 | **2.382** | 205 (−10) | **0,491** | **[0,471; 0,511]** | −10 | **CONTRA** |
| WDO combinado 2015-26 | — | 2.171 | — | 0,517 | [0,496; 0,538] | +0,7 | INCONCLUSIVO → fecha |

Por ano (WIN): nenhum com IC fora de 0,50. O estrato "contra a MME80"
brilhou no teste (0,557) e apagou na replicação (0,442) — caso de
manual, escrito antes que não decidia.

## Veredito

**CONTRA.** O 0,524 do teste era a borda superior de uma faixa de ruído
de dez anos. Nulo a custo zero, como o IFR2.

Backlog registrado, sem ação: nas operações por tempo o lado da entrada
era frequentemente o certo e o alvo ficava perto — é a porta de volume
(agressão no rompimento como gate), hipótese nova com ficha própria
quando o tape permitir.

## Próximo passo

Nenhum. Lápide.

## Onde está a discussão longa

`EAS_DE_PRECO.md` §4 (4.0 a 4.5) e §8.1c; catálogo em `RESEARCH_PLANO.md`.
