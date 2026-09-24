# Ficha — DeepScalper Fase 2 (classificador supervisionado)

> **Status:** vivo — **Revisado:** 2026-09-24 — **Assunto:** forward de um classificador congelado sobre as features de fluxo Tier 1; roda como score diário offline, não no EA; placar fechado até n=150.

## Identidade

| | |
|---|---|
| Linha | fluxo (tape), barras de volume |
| Instrumento | WINFUT |
| Config / artefatos | `docs/artefatos/fase2/modelo_fase2.pkl` (sha256 `5c5b0d7c74abad52…`), `docs/artefatos/fase2/ficha_fase2.json` (sha256 `63c392751f8de08d…`) — cópia única; dado de treino não reproduzível |
| Código | `research/fase2.py`; comandos `fase2-preparar`, `fase2-score` |
| Livro do forward | `data/research/fase2/forward_eventos.csv` (na máquina do operador) |
| Não toca | `ea.yaml`, `decidir()`, NTSL — zero mudança no EA |

## Fase e estado

**F3 → F4: forward LIGADO em 2026-09-11** (`--desde 2026-08-28`, primeiro
dia não visto pelo modelo). Placar fechado; abre em n=50 (sanidade) e
n=150 (veredito). **Checkpoint de sanidade feito em 2026-09-24** (v3.58,
livro reconstruído): n=75 em 18 pregões, acerto 0,293 (nula 0,337),
pts/op −52,5, 4,17 eventos/pregão. Sanidade OK (sem vazamento, sem
inversão, taxa dentro do teto). **Não é veredito.**

## Mecanismo em uma frase

Nas features de fluxo já calculadas (imbalance, absorção, rlp_frac,
agf dos dez maiores agentes, fluxo nacional) há informação sobre qual
barreira (alta/baixa, k·σ) o preço toca primeiro nas próximas 3 barras
que um limiar em `z_agf_3` sozinho não captura.

## Regras

- Features em z por dia, mesma convenção do EA; aquecimento de 25
  barras. `z_tick_imbalance` removida (ρ 0,982 com imbalance).
- Modelo: gradient boosting, max_depth 4, 200 iterações, lr 0,05,
  min_leaf 50, l2 1,0, seed 0. Treino 2026-07-24..08-20 (1.307 barras),
  validação 08-21..08-27 (306).
- Evento: barra fechada em que o modelo emite p ≥ **p\* = 0,633** para
  um lado; h = **3** barras cabem antes da última do dia; sem evento
  aberto. Barreira **k = 1,5 σ** (mediana ~274 pts). Empate intrabarra
  resolvido pelo tape.
- Resultado = 1 se a barreira do lado previsto bate primeiro; 0 se a
  oposta bate ou o vertical vence.
- `--agentes 3,8,39,85,88,92,114,120,1618,4090` obrigatório no score.

## Pré-registro congelado (2026-09-08, `entregue-v2.03`/`v2.04`)

    HIPOTESE   (acima)
    EVENTO     p* = 0,633, h = 3, k = 1,5
    TAXA       4,6 eventos/pregão (validação 08-21..27, 306 barras)
    EFEITO     +8 pp sobre a NULA 0,337 → acerto alvo 0,417; e ≥ +15 pts/op
    HORIZONTE  150 / 4,6 = 33 pregões (~1,6 mês). Teto 60 pregões.
    CRITERIO   FAVORAVEL: acerto ≥ 0,417 E pts/op ≥ +15, em n = 150.
               CONTRA: acerto ≤ 0,337 OU pts/op ≤ 0. Resto INCONCLUSIVO —
               e inconclusivo NÃO vira "mais 150"; volta à mesa.
    PARADA     Olha em n = 50 (sanidade) e n = 150 (veredito).

Reinicia a contagem: retreinar, mudar p\*, k, h, features, split.
Não reinicia: bug que desvia da ficha; dia re-escorado com dado
substituído (vai ao `forward_integridade.log`, v3.58).

Registros da preparação, sem decisão: k caiu no topo da grade
{0,25..1,5} e a grade não se estende; depuração na validação n=23 deu
0,304 (ruído, ±0,19); o critério binário é o que aperta.

## Resultados

| checkpoint | data | n | pregões | acerto | nula | pts/op | leitura |
|---|---|---|---|---|---|---|---|
| sanidade | 2026-09-24 | 75 (67 reais na 1ª contagem) | 18 | 0,293 | 0,337 | −52,5 | sanidade OK; **não é veredito** |

Integridade: 04, 08, 09, 10 e 15/09 tiveram barras regeradas depois de
escorados (backfill); livro reconstruído sobre o dado atual.

## Veredito

Pendente — em n = 150 (~início/meados de outubro no ritmo atual).

## Próximo passo

Ritual offline após 18:30: `curate` → `features WINFUT --volume-barra
120000 --agentes …` → `fase2-score WINFUT --dia …`. Não olhar o placar
antes de n=150. Só FAVORÁVEL autoriza a Fase 3 (RL), ainda sujeita ao
portão de 160 pregões de book.

## Onde está a discussão longa

- `RESEARCH_PLANO.md`: "PRE-REGISTRO: DeepScalper — Fase 0" (09-07);
  "inventario-deepscalper"; "Fase 1 — simulador"; "FICHA FORWARD: Fase 2
  — rascunho v0" e "CONGELADA" (09-08); checkpoint (09-24).
- `CURADORIA_DEEPSCALPER.md` — o que foi lido e descartado.
- `HISTORICO_DE_SESSOES.md`, sessões de 2026-09-08 e 2026-09-24.
