# Ficha — 123 em volume BAIXO (ficha 12) — o gate do 123 no forward

> **Status:** vivo — **Revisado:** 2026-09-24 — **Assunto:** 123 cuja barra de sinal fecha com volume abaixo da mediana do horário; gerada pelo complemento da ficha 9, replicada no WDO (0,534, IC exclui 0,50) e atravessa a quebra de 2020 nos dois instrumentos; INCONCLUSIVA pelo critério de 0,56, mas é o gate do 123 no E4 desde 22/09.

## Identidade

| | |
|---|---|
| Linha | preço M15 + volume de candle |
| Instrumentos | WDO (teste); WIN (forward — o WIN histórico não pode testá-la: `eas-preco-teste` recusa `--instrumento win`) |
| Configs | `config/ea_123_volume_baixo.yaml` (`ea_123_vb`, simulado); `config/ea_123_volume_baixo_e4.yaml` (`ea_123_vb_e4`, `dry_run: false`, conta DEMO) |
| Código | `ea/gate_fluxo.py` (`GateVolumeBaixo`), `ea/perfil_volume.py` (`PerfilVolumeHorario`), `ea/diario.py`; `research/eas_preco*.py` (`--ficha 123gate_baixo`) |
| Hash de ficha | WDO `d744e7d4ad26` |
| Família | "123gate_baixo", trial 1 |

## Fase e estado

**F4 no WDO: INCONCLUSIVO pelo critério, efeito real. F5 no WIN: É O
GATE DO 123 NO E4** — 7a fechado 2026-09-21 (gate barrou 3 de 6
candidatos ao vivo), E4 com ordens reais desde 2026-09-22 (ver
`123_m15.md` e `RUNBOOK_E4.md`).

## Mecanismo em uma frase

Um 123 que se forma em volume baixo continua mais do que um em volume
alto — recuo sem convicção continua; recuo com briga vira qualquer
coisa (mecanismo dito depois do dado da ficha 9, por isso testado em
amostra nova).

## Regras

Tudo da ficha `123_m15.md`, **e**: vol_total(t) < mediana de vol_total
no mesmo hhmm nos 20 pregões anteriores. No EA:

- `filtro_fluxo: {tipo: volume_baixo, janela_pregoes: 20}`.
- Perfil semeado pelo parquet + ponte pelo tape (como a MME80).
- Barra com `volume_confiavel` falso (parcial ou lacuna > 5 s) = gate
  INDEFINIDO (sinal fora, contado) e não entra no perfil.
- Diário JSONL por sinal com desfecho (executou / rejeitado_gate /
  gate_indefinido / sem_vaga / posicao_aberta …), volume e mediana do
  gate, `volume_confiavel`, `maior_lacuna_s`, infra do momento.

Conferência tape × gráfico do volume feita antes de ligar (v2.89):
28/08 idêntico (37/37); 11/09 cinco barras abaixo, todas com lacuna
de 38-211 s — buraco de feed, não fórmula.

## Pré-registro declarado (2026-09-15, `entregue-v2.86`)

    HIPOTESE   p1 ≥ 0,56 no conjunto de volume baixo; contraste (volume
               acima) fica abaixo.
    ONDE       (a) WDO, dez anos, onde nenhum teste de volume tocou e o
               123 puro deu 0,514 — replicação em OUTRO instrumento;
               (b) FORWARD no WIN: gate do EA, medido daqui para frente.
    CRITERIO   No WDO: como sempre, com contraste e por-quartil
               reportados. Não separar = "interessante, não replicado".
    AMOSTRAS   WDO: depuração → teste → replicação → histórico → combinado.

## Resultados

**WDO (2026-09-15):**

| | resolvidas | p1 | IC95 | P&L bruto/op (pts WDO) |
|---|---|---|---|---|
| primário: volume ABAIXO | 2.863 | **0,534** | **[0,516; 0,552]** | **+0,8 [0,1; 1,4]** |
| contraste: volume ACIMA | 1.950 | 0,5005 | [0,478; 0,523] | −0,5 |

Onze de doze anos acima de 0,50. Por quartil de D, o MESMO desenho do
WIN. P&L com IC inteiro acima de zero — o primeiro da linha.

**Releitura por regime (2026-09-16, zero trial, critério escrito antes):**

| | até 2019 | de 2020 |
|---|---|---|
| WIN volume baixo | 0,563 [0,535; 0,590] n=1.269 | 0,546 [0,524; 0,567] n=2.097 |
| WIN volume alto | 0,507 | 0,506 |
| WDO volume baixo | 0,552 [0,520; 0,584] n=913 | 0,526 [0,503; 0,548] n=1.950 |
| WDO volume alto | 0,528 | 0,486 |

Quatro medições independentes entre 0,526 e 0,563, contraste abaixo em
todas: a hipótese fica MAIS FORTE; o veredito não muda. Observações sem
ação: queda de ~2 pp do regime antigo para o novo nos dois (direção de
arbitragem lenta); 2026 no WIN invertido com n=104.

**Forward WIN (E4):** em curso desde 22/09; slippage é a medida (ficha
de forward em `123_m15.md`).

## Veredito

**INCONCLUSIVO pelo critério de 0,56 (que não se mexe).** Efeito real e
pequeno, 0,53-0,55, em dois instrumentos por dez anos, através de uma
quebra estrutural. Pequeno para EA próprio; suficiente para ser o gate
do 123 — o caminho declarado no dia 1.

## Próximo passo

O do E4 (`RUNBOOK_E4.md`): cancelamento total, ~50 pregões, slippage
≤ 6 pts em n = 100. Não trocar limiar (mediana) nem janela (20) — cada
um é família nova sobre amostra queimada.

## Onde está a discussão longa

`EAS_DE_PRECO.md` §12 (12.0 a 12.3) e §9.2 (origem); `EA_ARQUITETURA.md`
§6 (diário); `RUNBOOK_E4.md`; `ESTADO_E_CAMINHOS.md`.
