# Porte dos EAs para NTSL (contingência da queda do ProfitDLL)

> **Status:** vivo — **Revisado:** 2026-10-06 — **Assunto:** `vwapvp_continuacao`, `ignicao` e `ea_123_vb` (E4) reescritos como estratégias de execução do Profit enquanto o ProfitDLL da Nelogica está fora; MECANISMO NOVO, carimbo e contagem próprios; NÃO COMPILADO ainda.

Arquivos: `ntsl/vwapvp_continuacao.ntsl`, `ntsl/ignicao.ntsl`, `ntsl/ea_123_vb.ntsl`.
Guarda estática: `tests/test_ntsl_execucao.py` (só pega os defeitos de sintaxe/idioma que a skill de engenharia §3.1 já custou; **não prova que compila nem que opera**).

## Por que existe

Desde 04/10/2026 o ProfitDLL está fora (`profitdll.estado tipo=0 valor=200`, LOGIN_UNKNOWN_ERR) e o `record` não sobe: sem captura de tape/book e sem os EAs
Python, que moram dentro do `record`. O Profit em si funciona. Todos os EAs do `config/` foram portados, **menos `z_agf_win`** (usa `agent_id` por corretora e barra de
volume de 120.000: não existe em NTSL) e `microprice` (precisa do book por negócio).

## PRÉ-REGISTRO (escrito antes de qualquer sinal NTSL)

    HIPOTESE   O porte NTSL executa a MESMA regra escrita das fichas, com as diferenças
               declaradas abaixo. Não é validação de nenhuma ficha.
    EVENTO     Cada operação do simulador do Profit disparada por um dos três .ntsl.
    CONTAGEM   PRÓPRIA por arquivo. Carimbo = nome do arquivo + sha256 do .ntsl.
               Observação NTSL NUNCA soma com a do EA Python (skill forward, regra 2:
               porte = mecanismo novo, contagem nova, salvo equivalência provada).
    EQUIVALENCIA  Só se declara quando, num mesmo dia, o replay Python (`ea-vwapvp-replay`,
               `ea-ignicao-replay`, diário do 123) e o log NTSL concordarem em sinais e
               lados. Hoje: provada SÓ para a VWAP por barra do vwapvp (113/113 em 28/09,
               `vwapvp_conferir.ntsl`). O resto está por provar.
    CRITERIO   Os mesmos critérios de morte/continuação das fichas (vwapvp: DD > 7.000 pts
               ou 40 trades com média negativa; ignição e 123: slippage). Medidos NA
               CONTAGEM NTSL, que mede o simulador do Profit, não o book real.
    PARADA     Defeito de execução (ordem duplicada, posição sem proteção, ordem fora do
               Simulador) = desliga na hora, sem esperar n.

O que isto **não** é: não reabre nenhuma ficha, não troca número, não autoriza conta real.

## O que cada arquivo faz de diferente do Python

| Aspecto | Python (record) | NTSL |
|---|---|---|
| vwapvp: VWAP/SD | por negócio (5,5 M/dia) | por barra, preço típico × QuantityVol (aproximação já medida) |
| vwapvp: tempo | 1º negócio após 3.600 s | 12 barras M5 no fechamento |
| ignição: referência | último negócio de ≥ 60 s atrás | Close da barra de 60 s atrás (barra de 1 s) |
| ignição: nível | 1º negócio além do limiar | referência ± 500 (alvo/stop saem daí) |
| ignição: refratário/tempo | segundos de relógio | barras (segundo sem negócio não gera barra) |
| 123: MME80 | semente parquet + ponte do tape | `MediaExp(80, Close)` do gráfico (a do research) |
| 123: volume | tape + `volume_confiavel` | `QuantityVol` do candle (a do research); sem noção de "barra não confiável" |
| 123: perfil 20 pregões | fila por horário, pula dia faltante | deslocamento fixo de `BarrasPorDia`; dia com barra faltando ⇒ gate INDEFINIDO (nunca passa errado, pode perder sinal) |
| 123: proteção do stop-limite | zera 2 s após negócio além do limite | `ClosePosition` no fechamento da barra se o Close passou do limite |
| todos: fills | tape/book do record | simulador do Profit |
| todos: custo | 11 pts (vwapvp/123) / 4 (ignição) descontados | `DailyResult(False)/ValorPonto` (vwapvp desconta `CustoPts` se `DescontarCusto=1`) |
| todos: logs | `forward_eventos.csv`, diário JSONL | só `ConsoleLog` (linhas `NTSV`, `NTSI`, `NT123`) |
| todos: trava de conta | `apenas_simulador` fixo no código | **nenhuma**: é o nome da conta que o Diego escolhe ao ligar |

## Como ligar (os três)

1. Automação de estratégias → escolher o `.ntsl` → **conta SIMULADOR**.
2. Modo "Realizar envio de ordens no **fechamento do candle**" e **marcar** "executar apenas no fechamento do candle ou com atualização de posição". Desmarcada, o código roda várias vezes por candle (manual NTSL, 11.4) e o estado conta em dobro.
3. Quantidade por Ordem = 1 e Quantidade máxima da posição = 1.
4. Gráficos: `vwapvp_continuacao` WINFUT **M5**; `ea_123_vb` WINFUT **M15**; `ignicao` WINFUT em **1 segundo** (`BarrasJanela` 60; 5 s ⇒ 12).
5. Ligar **antes** da abertura da janela (vwapvp 11:00; ignição 09:16; 123 09:30). Contadores e bloqueios recomeçam em zero se ligar no meio do dia.
6. **Nunca junto com o `record` no mesmo ticker e conta.** O Python tem "vaga do ticker"; o NTSL não o conhece. Quando o DLL voltar: desligar as automações NTSL ANTES de subir o `record`.
7. Market Replay: `GuardaRelogio = 0` (o relógio do PC é o de hoje, não o do replay).

### Rolagem do WIN (14/10)

`--ea-ticker-ordem` do Python ia de `WINV26` para `WINZ26`. No NTSL, a ordem vai para o ativo do gráfico. No `WINFUT` o Profit resolve o contrato corrente. **Não sei se o Profit aceita automação com ordem no `WINFUT`**; se recusar, usar `WINV26` até 14/10 e `WINZ26` depois. Nesse caso o **gate do 123 fica distorcido** (o perfil de 20 pregões de volume do contrato novo é curto e fino): `GateN < 20` ⇒ gate indefinido ⇒ sem sinal; e se o gráfico tiver 20 pregões mas com volume fino, o gate passa demais. `UsarGate = 0` roda o 123 puro (`ea_123`), que é **outra** família.

## Conferência no 1º pregão (obrigatória antes de confiar em qualquer número)

Todos os `.ntsl` escrevem no console da automação (Detalhes da Automação; buffer ~2.000 linhas). Ordem dos campos **congelada** (mudar aqui ⇒ mudar o parser quando existir, skill §3.2).

**`NTSV` (vwapvp, uma linha por fechamento de M5):**
`NTSV|Date|Time|CurrentTime|Fechou|Close|VWAP|SD|Z|Motivo|Evento|LadoPos|AlvoPx|StopPx|Pos|BarsPos|Ops|Perdas|PnlDiaPts|Bloq|DeltaRes`
Motivo: 0 fora da banda · 1 ARMOU · 2 fora da janela · 3 lado · 4 bloqueado · 6 max ops · 7 cooldown · 8 sem distância · 9 barra incompleta. Evento: 1 entrada · 3 tempo · 4 zeragem · 9 órfã.

**`NTSI` (ignição; só eventos + linha de vida a cada `HeartbeatBarras`):**
`NTSI|Date|Time|Close|Ref|Lado|NivelDet|Status|Evento|LadoPos|AlvoPx|StopPx|BarsPos|Ops|Refrat|DailyRes`
Status: 1 ARMOU · 2 ignorada posicionado · 3 limite do dia. Evento: 1 alvo · 2 stop · 3 tempo · 4 zeragem · 5 ambíguo · 9 órfã · 10 entrada.

**`NT123` (uma linha por fechamento de M15):**
`NT123|Date|Time|CurrentTime|Fechou|O|H|L|C|Mme|PadC|PadV|Regime|D|LadoCand|Entrada|Stop|Alvo|VolT|Med|GateN|GateOk|Motivo|Evento|Pos|DailyRes`
Motivo: 0 sem padrão · 1 ARMOU · 2 fora da janela · 3 regime · 4 D < mínimo · 5 gate reprovou · 6 gate indefinido · 8 barra incompleta. Evento: 1 armou · 4 zeragem · 6 proteção do stop · 9 órfã.

O que olhar, nesta ordem:

1. **`Fechou = 1` em toda linha de fechamento** (vwapvp e 123). Se aparecer `Fechou = 0` num fechamento de verdade, o relógio do PC está atrás do da bolsa e o guarda está descartando sinais: ligar `GuardaRelogio = 0` e avisar.
2. **Cada ordem aparece no Profit como foi desenhada**: 123 = uma STOP de entrada que some sozinha no fim de t+1; depois stop-limite + limitada. vwapvp/ignição = mercado e depois OCO.
3. **123: `GateN = 20` e `Med` bate com o Python** (`PerfilVolumeHorario.mediana` para o mesmo dia/horário, calculado do parquet). Se `GateN < 20` em dia normal, `BarrasPorDia` está errado (o aviso `NT123|AVISO` no 1º candle diz o que o Profit mede).
4. **`DeltaRes` (vwapvp)**: o resultado fechado que o simulador reporta, em R$. Dividir por 0,20 e comparar com Close de entrada/saída: diz se o simulador já desconta taxas (se descontar, `DescontarCusto = 0`).
5. **Se aparecer `ORFA`**: a posição existia sem níveis guardados (estado perdido no reprocessamento ou automação religada com posição). A estratégia fecha a mercado por segurança. Anotar quando.

## O que NÃO sei (nenhum item testado; é o que eu verificaria primeiro)

[Chutando] ≈ 8 itens, por ordem de risco:

1. **Compila?** Escrevi contra o manual e os `.ntsl` que já rodam. Nenhum compilador à mão. O primeiro erro de compilação é esperado.
2. **Em que candle o reprocessamento pós-fill roda.** O manual (11.11) diz "reprocessa o mesmo candle para as ordens Cover"; assumi que é o candle em formação (t+1), com os níveis lidos de `[1]`. Se for o candle t, o estado do sinal se perde e a estratégia cai no ramo `ORFA` e fecha a posição que acabou de abrir.
3. **Reavaliação no meio do candle sem posição.** Se uma cover fechar a posição no meio de um candle, o código roda de novo com a barra PARCIAL. O guarda de relógio (`CurrentTime >= fim da barra`) cobre vwapvp e 123; na ignição o refratário de 30 min cobre.
4. **OCO re-editada a cada barra.** Em 1 s isso pode virar enxurrada (`ModoSaidaOCO = 0` é a saída).
5. **`DailyResult(False)` e taxas**: o `DescontarCusto` pode estar contando o custo em dobro ou não contando.
6. **Ligar a automação no meio do dia**: o histórico é reprocessado; se o Profit simular ordens nos candles passados, os contadores nascem sujos.
7. **Ordem no `WINFUT`**: ver "Rolagem do WIN".
8. **Limite automático do stop** quando omitido: o manual diz 30 ticks para futuros BMF; passei `SlackStopPts` explícito (150 no vwapvp/ignição, 50 no 123 como no Python).

## Quando o DLL voltar

- `profit-tape backfill` recupera os negócios dos dias sem captura (janela de 30 dias do Profit); **o book ao vivo desses dias não volta**.
- Desligar as três automações NTSL antes de subir o `record` com `--ea-dir config/`.
- A contagem NTSL e a do Python ficam em carimbos separados; o relatório do forward não mistura.

## Relação com as fichas

Nenhum número das fichas mudou. `config/*.yaml` intactos (o `config_sha` do Python não muda). O porte não altera o EA Python: `sinal_*`, `ciclo_123`, `gate_fluxo` e `perfil_volume` são a **especificação** e continuam sendo o que roda quando o DLL voltar.
