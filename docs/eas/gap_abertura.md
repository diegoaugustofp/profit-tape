# Ficha — GAP de abertura (ficha 10, fechamento de gap)

> **Status:** fechado (a confirmar) — **Revisado:** 2026-09-24 — **Assunto:** entrar contra o gap na abertura de 09:15 com alvo no fechamento da véspera; congelada em 2026-09-16; o catálogo de hipóteses mortas registra "inconclusivo, por-ano sem padrão", mas a tabela n/p1/IC do teste não está no repositório.

## Identidade

| | |
|---|---|
| Linha | preço M15 — informação da NOITE, entrada a mercado |
| Instrumento | WINFUT |
| Código | `research/eas_preco*.py` (`--ficha gap`; `resolver_gap`; `alternativas_de_piso` no funil) |
| Família | "gap", trial 1 |

## Fase e estado

**F4 — congelada em 2026-09-16 (`entregue-v2.94`).** O catálogo de
hipóteses mortas (`RESEARCH_PLANO.md`, item 4 de "COMO GERAR E REFINAR
HIPOTESE", adicionado na v2.99) registra: *"inconclusivo, por-ano sem
padrão — informação da noite também já está no preço"*. **Lacuna:** não
há em nenhum documento a tabela de resultado (amostras, resolvidas, p1,
IC, P&L, hash do carimbo) que os outros fechamentos têm. A preencher
pelo operador a partir de `resultado_gap_*.json` / combinado — ou, se o
teste não rodou, corrigir o catálogo.

## Mecanismo em uma frase

Uma abertura com gap relevante tende a reavaliar o gap durante o dia:
entrando contra o gap às 09:15, o fechamento da véspera é alcançado
antes de um stop simétrico mais de 50% das vezes.

## Regras

Convenções de `docs/eas/README.md`, mais:

- Véspera contígua; close_v e atr_v = close e ATR14 da ÚLTIMA barra da
  véspera. gap = open(09:00) − close_v; |gap| ≥ 0,5 × atr_v.
- A barra 09:00 não pode ter fechado o gap (low ≤ close_v ≤ high →
  fora, contado).
- Lado pelo SINAL do gap: para cima → VENDA; para baixo → COMPRA.
- Entrada a MERCADO na abertura de 09:15; se já estiver além de
  close_v, fora. Alvo = close_v. **D = |entrada − close_v|** ao tick
  (recalculado da entrada); stop simétrico; D ≥ 4 ticks.
- Uma operação por pregão; resolve até a zeragem. Regime = estrato.
- Registradas, não testadas: versão "com confirmação" (barra 09:00 já
  andou na direção do fechamento) — outra ficha.

## Pré-registro congelado (2026-09-16, `entregue-v2.94`)

Funil nos três dumps do WIN:

| | 2015-22 | 2023-25 | 2026 |
|---|---|---|---|
| \|gap\| ≥ 0,5 × ATR14 | 85,2% | 83,8% | 87,3% |
| barra 09:00 fechou o gap (corta) | 14,2% | 28,6% | 34,1% |
| sinal por pregão | 0,71 | 0,55 | 0,53 |
| D p50 (pts) | 960 | 655 | 1.328 |
| ambígua / por tempo | 1,1% / 14,5% | 2,2% / 11,4% | 0% / 17,4% |

Combinado ~1.490 resolvidas, ±2,5 pp. Ressalva do operador (ATR das
barras finais encolhe) MEDIDA: ATR das 16:30 é 5-9% maior e a cláusula
quase não muda (84% vs 81%) → **piso mantido em 0,5 × ATR14 da última
barra**. Sequência: depuração → teste → replicação → histórico →
combinado; veredito no combinado; inconclusivo = fecha. Expectativa
dita antes: prior baixo.

## Resultados

**Não registrados no repositório** (ver "Fase e estado").

## Veredito

Pelo catálogo: **INCONCLUSIVO → fecha.** Aprendizado da categoria: a
informação da noite também já está no preço. Pendente confirmar com a
tabela.

## Próximo passo

Preencher a seção "Resultados" com a tabela do carimbo, ou corrigir o
catálogo. Sem trial 2 em qualquer caso.

## Onde está a discussão longa

`EAS_DE_PRECO.md` §10 (10.0, 10.1); `HISTORICO_DE_SESSOES.md` 2026-09-16
(v2.93/v2.94); catálogo em `RESEARCH_PLANO.md`.
