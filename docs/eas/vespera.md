# Ficha — rompimento da máxima/mínima da VÉSPERA (ficha 11)

> **Status:** fechado — **Revisado:** 2026-09-24 — **Assunto:** rompimento do nível do dia anterior com ordens STOP OCO; FECHADA sem nunca ter tido p1 — o estimador binário não serve em M15 (v0: 78% por tempo; v1: 54-74% ambígua). Aprendizado de método registrado.

## Identidade

| | |
|---|---|
| Linha | preço M15 — estrutura do dia anterior inteiro |
| Instrumento | WINFUT |
| Código | `research/eas_preco*.py` (`--ficha vespera`; `marcar_vespera`, `rodar_vespera`, `resolver_vespera`) |
| Família | "vespera", trial 1 (nunca consumido) |

## Fase e estado

**F3 — FECHADA sem p1 (2026-09-16, `entregue-v2.93`).** Não há v2:
escolher o terceiro desenho depois de dois diagnósticos é procurar o
que passa.

## Mecanismo em uma frase

O rompimento da máxima (ou mínima) do dia anterior, quando não
aconteceu já na abertura, continua por uma escala típica antes de
retroceder o mesmo tanto.

## Regras (v1, a última)

Convenções de `docs/eas/README.md`, mais:

- Véspera contígua; A_v = high_v − low_v ≥ 4 ticks.
- Ordens STOP OCO: compra em R_high_v + tick, venda em R_low_v − tick,
  válidas de 09:00 a 16:30. Uma operação por pregão; primeiro rompimento
  vence; os dois na mesma barra = ambíguo, fora.
- **Abertura já fora desarma o lado** (open(09:00) ≥ R_high_v + tick →
  aquele lado sai; sem isso viraria a ficha 10 disfarçada).
- v0: D = A_v (amplitude inteira da véspera). **v1: D = ATR14 da última
  barra fechada antes do gatilho** (nível da véspera, escala do dia).
- Regime = estrato, nunca cláusula (lição do ORB 7.4).
- Risco declarado antes: se "por tempo" passasse de 40%, a ficha voltava
  ao desenho ANTES de congelar.

## Funis (nunca houve congelamento)

| | v0 (D = A_v), 2015-22 / 2023-25 / 2026 | v1 (D = ATR14) |
|---|---|---|
| sinal por pregão | 0,63 / 0,70 / 0,68 | — |
| A_v p50 (pts) | 2.931 / 2.148 / 3.085 | (ATR14 ~465) |
| ambígua | 0% / 0% / 0% | **54-74%** |
| por tempo | **78,6% / 73,7% / 76,9%** | 0,8-1,5% |
| barras até resolver p50 | 28-30 | — |

v0 voltou ao desenho como estava escrito (por tempo > 40%): o alvo
ficava a uma amplitude diária inteira do rompimento. v1 resolveu o
tempo e criou ambiguidade: o stop a 1 ATR do nível fica DENTRO da barra
que rompe, e o OHLC não ordena. Lados opostos da mesma tensão.

## Veredito

**Fechada sem p1.** Conclusão: o rompimento do nível da véspera não é
testável em M15 com estimador binário simétrico — precisaria de tape
para ordenar a barra do gatilho, e isso é hipótese nova.

**Aprendizado de método (permanente):** quando a entrada é por
ROMPIMENTO, D precisa ser maior que a barra do gatilho, ou o OHLC não
resolve. O ORB tinha isso de graça (D = range inteiro, ambiguidade 0,3%).

## Próximo passo

Nenhum. Se um dia: mesma hipótese com ordenação pelo tape, ficha nova.

## Onde está a discussão longa

`EAS_DE_PRECO.md` §11 (11.0, 11.1); `HISTORICO_DE_SESSOES.md` 2026-09-16
(v2.92, v2.93); catálogo em `RESEARCH_PLANO.md`.
