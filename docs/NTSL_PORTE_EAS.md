# Porte dos EAs para NTSL (contingência da queda do ProfitDLL)

> **Status:** vivo — **Revisado:** 2026-10-06 — **Assunto:** `vwapvp_continuacao`, `ignicao`, `ea_123_vb` (E4) e `z_agf_win` (Rota A, v4.34) reescritos como estratégias de execução do Profit enquanto o ProfitDLL da Nelogica está fora; MECANISMO NOVO, carimbo e contagem próprios; NÃO COMPILADO ainda.

Arquivos: `ntsl/vwapvp_continuacao.ntsl`, `ntsl/ignicao.ntsl`, `ntsl/ea_123_vb.ntsl`, `ntsl/z_agf_win.ntsl` (v4.34).
Guarda estática: `tests/test_ntsl_execucao.py` (só pega os defeitos de sintaxe/idioma que a skill de engenharia §3.1 já custou; **não prova que compila nem que opera**).

## Por que existe

Desde 04/10/2026 o ProfitDLL está fora (`profitdll.estado tipo=0 valor=200`, LOGIN_UNKNOWN_ERR) e o `record` não sobe: sem captura de tape/book e sem os EAs
Python, que moram dentro do `record`. O Profit em si funciona. Os três primeiros EAs foram portados na v4.33. **Correção (v4.34):** a v4.33 dizia que `z_agf_win` e
`microprice` "não existem em NTSL" (agente por corretora, book por negócio). **Isso estava errado**: o NTSL tem `VolumeAgent`/`AvgAgent`/`BalanceAgent` (Ultra ou Automação 2,
manual NTSL 20.18, 20.25, 20.157) e funções de book. Eu afirmei sem ter aberto o manual; o Diego apontou. O `z_agf_win` foi portado na v4.34 (Rota A). O `microprice`
**continua sem porte, por outro motivo**: a ficha o descartou como taker em 2026-09-25 (`docs/eas/microprice.md`); ter o book disponível não reabre isso.

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

### Acréscimo v4.34 — `z_agf_win` (pré-registrado antes de qualquer log NTZA)

    HIPOTESE   O porte executa a regra escrita da ficha z_agf_3 na ROTA A (a
               validada: venda apenas, z >= 1,4 contrarian, saída por TEMPO em 3
               barras, stop catastrófico 500 pts, circuit breaker de 3 perdas).
               Não é a Rota B que o YAML do Python carrega (100/120): o operador
               escolheu a A em 2026-10-06, o que também resolve, para o NTSL, a
               "Divergência a resolver" da ficha. O YAML do Python NÃO mudou.
    CARIMBO    ntsl/z_agf_win.ntsl + sha256. Contagem PRÓPRIA, nunca soma com
               o forward Python (dry_run) nem com os outros três .ntsl.
    ETAPAS     1) ModoConferir = 1 (default): nenhuma ordem; o log NTZA registra
                  Bal, VolAg, Volume, QuantityVol, agf, z e a decisão que tomaria.
               2) Conferência (abaixo) passa -> ModoConferir = 0 em SIMULADOR.
               Pular a etapa 1 invalida a contagem.
    EQUIVALENCIA  Só se declara quando, no mesmo pregão, as barras e o z do log
               NTZA concordarem com os do Python recalculado do tape recuperado
               (`profit-tape features`, mesma config). Hoje: NADA provado. A
               aritmética da janela (soma/soma de quadrados recursivas) está
               provada contra `zscore_rolante` em teste; a FONTE (BalanceAgent) não.
    CRITERIO   Conferência, fixada AGORA (o operador pode mudá-la por escrito antes do
               1º pregão de conferência; depois de ver dado, não): (i) Fechou = 1
               em toda barra de fechamento; (ii) nº de barras do pregão no Profit
               dentro de ±5% do nº do Python (com ~40 barras/dia, ±2 barras);
               (iii) nas barras pareadas por horário de fechamento, correlação
               >= 0,90 entre `Agf` (NTSL) e `agf_3` (Python) e mesmo lado em
               >= 90% das barras com |z| >= 1,4 em qualquer dos dois. Qualquer
               item fora: o porte NÃO conta como equivalente e `ModoConferir = 0`
               só roda como mecanismo novo, sem relação com a ficha. Os números
               0,90/90%/5% são escolhas minhas, sem base empírica nesta amostra;
               o que importa é estarem escritos antes do dado.
    PARADA     Defeito de execução (ordem duplicada, posição sem estado/ORFA
               repetido, ordem fora do Simulador) desliga na hora.

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
8. **Uma automação por ativo e por conta.** As quatro estratégias operam WINFUT. Duas automações na MESMA conta e no mesmo ativo somam a posição líquida: uma vê
   `HasPosition` por causa da outra e a lógica de estado (que assume que a posição é dela) quebra. **NÃO SEI** se o Profit oferece subcontas/contas simuladas separadas
   para isso. Até saber, ligue UMA automação por vez, ou cada uma numa conta simulada distinta. Isto também vale para as três da v4.33 (não constava lá).
9. `z_agf_win`: gráfico de **120.000 lotes** (período por quantidade de lotes), não de tempo; ao vivo apenas (o `BalanceAgent` não roda em backtest).

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

**`NTZA` (z_agf_win, uma linha por avaliação do último candle; as completas têm `Fechou = 1`):**
`NTZA|Date|Time|CurrentTime|Fechou|Close|Qtd|Volume|Bal|VolAg|Agf|Ok|Media|Dp|Cnt|Z|Motivo|Evento|Modo|Hold|LadoPos|EntradaPx|StopPx|Pos|Perdas|PnlDiaPts|Bloq|DeltaRes`
Motivo: 0 sem sinal · 1 ARMOU · 2 fora do horário · 3 lado não permitido · 4 bloqueado · 5 com posição · 7 saiu nesta barra. Evento: 1 entrada · 2 stop (fechamento) · 3 saída por tempo (no modo conferência é a saída VIRTUAL) · 4 zeragem · 9 órfã · 11 estado reconstruído.
`Qtd` = QuantityVol do candle; `Volume` = financeiro; `Bal`/`VolAg` = BalanceAgent/VolumeAgent do agente 3 no candle; `Cnt` = barras válidas na janela ANTES desta barra.

O que olhar, nesta ordem:

1. **`Fechou = 1` em toda linha de fechamento** (vwapvp e 123). Se aparecer `Fechou = 0` num fechamento de verdade, o relógio do PC está atrás do da bolsa e o guarda está descartando sinais: ligar `GuardaRelogio = 0` e avisar.
2. **Cada ordem aparece no Profit como foi desenhada**: 123 = uma STOP de entrada que some sozinha no fim de t+1; depois stop-limite + limitada. vwapvp/ignição = mercado e depois OCO.
3. **123: `GateN = 20` e `Med` bate com o Python** (`PerfilVolumeHorario.mediana` para o mesmo dia/horário, calculado do parquet). Se `GateN < 20` em dia normal, `BarrasPorDia` está errado (o aviso `NT123|AVISO` no 1º candle diz o que o Profit mede).
4. **`DeltaRes` (vwapvp)**: o resultado fechado que o simulador reporta, em R$. Dividir por 0,20 e comparar com Close de entrada/saída: diz se o simulador já desconta taxas (se descontar, `DescontarCusto = 0`).
5. **Se aparecer `ORFA`**: a posição existia sem níveis guardados (estado perdido no reprocessamento ou automação religada com posição). A estratégia fecha a mercado por segurança. Anotar quando.

### Conferência do `z_agf_win` (etapa 1, `ModoConferir = 1`)

1. `Qtd` das linhas `Fechou = 1` deve ficar perto de 120.000 (se for sempre maior, o excesso não é carregado como no Python; se `Fechou = 0` no fechamento, a barra do
   Profit não chega a `VolBarra`: o RLP/leilão está fora do QuantityVol dele, ou o gráfico não é de 120.000 lotes).
2. `Bal` ≠ 0 e `VolAg` > 0 nas barras: se vierem zerados, o `BalanceAgent` não está devolvendo dado (licença, conta ou agente) e **nada abaixo vale**.
3. `Cnt` crescendo de 0 até 50 ao longo do dia (ou já começando alto se o histórico do dia anterior veio): diz se a janela atravessa o dia.
4. Depois que o DLL voltar: `profit-tape backfill` do pregão, recalcular as barras e `agf_3`/`z_agf_3` com a MESMA config e parear com o log (por horário de fechamento).
   Medir: nº de barras do dia, correlação do `Agf` (NTSL) com o `agf_3` (Python) e concordância do lado do z nas barras com |z| ≥ 1,4, contra os limiares do pré-registro acima.
5. Só então `ModoConferir = 0`, em conta SIMULADOR, sozinha (item 8 de "Como ligar").

## Achado do 1º backtest do `ignicao` (2026-10-06, v4.35)

Diego rodou o `ignicao` em backtest (30/09–06/10) nos gráficos de 5 s (`BarrasJanela` 12) e 15 s; no de 1 s não saiu relatório.

    EVIDENCIA   console: NTSI|ORFA| em TODA entrada (14 linhas = 7 trades x 2, 5 s).
                CSV 5 s: 7 operações, TODAS com tempo = 1 barra (5 s), ganho médio
                +15 a +50 pts, perda -140/-185 pts; o desenho é alvo/stop 530 ou 60 min.
                15 s: 24 operações em 5 pregões (teto 4/dia = 20): contador diário
                não acumulou.
    DEFEITO     estado (níveis, contador) não está em `[1]` no primeiro candle avaliado
                com posição; o ramo ORFA fecha a posição na hora. Defeito de EXECUÇÃO:
                pela PARADA do pré-registro, a contagem NTSL do ignicao não começou.
                Os números desse backtest são amostra de DEPURAÇÃO (skill disciplina
                §7.1): não interpretáveis, não contam.
    CONSERTO    detecção calculada antes do bloco de posição; se há posição, o estado
                falta, o sinal se reproduz nesta barra e é a 1ª barra com posição: o
                estado é reconstruído (sem nova ordem, contador +1, evento 11).
                Cobre o reprocessamento do MESMO candle. NÃO cobre a perda de estado
                numa barra posterior (continua ORFA). O log `NTSD` mede qual caso é.
    1 s         sem relatório: NÃO SEI. Indício (fraco): as 7 entradas do 5 s só
                aparecem em 05 e 06/10, o que sugere pouco histórico de segundos no
                backtest. Ver o texto da tela no 1 s antes de concluir.
    MEDIDO      (2º backtest, 5 s, v4.35) NTSD: em TODAS as 7 entradas, `Evento 10` (Pos 0) e
                `Evento 11` (Pos 1, LadoAnt 0) no MESMO `Bar`: o Profit reprocessa o MESMO
                candle depois do fill. Zero ORFA; durações 9–177 barras = o CSV, uma a uma;
                saídas nos níveis (4 alvos, 3 stops), máx. 4 ordens/dia. Resultado bruto
                +R$ 44 (+220 pts), deslizamento médio da entrada contra o nível de detecção
                +44 pts (fill do simulador, NÃO conta para a ficha). Amostra de DEPURAÇÃO.
    CONTAGEM    carimbo `ignicao.ntsl` sha256 `30248ebe0439…`; só vale em simulador AO VIVO,
                a partir do próximo pregão. Backtest nunca conta. As 7 entradas de 05–06/10
                (13:57, 15:08, 16:30, 09:20, 10:11, 10:45, 11:56) ficam como lista de
                conferência contra o `ea-ignicao-replay` do Python, quando o tape voltar.
    v4.36       `vwapvp_continuacao` entra a MERCADO no fechamento da barra do sinal, como o
                ignicao: mesma exposição, mesmo conserto (sinal calculado antes do bloco de
                posição + reconstrução, evento 11). `ea_123_vb` NÃO foi alterado: a entrada é
                ordem STOP que enche em t+1 e o estado foi gravado em t, então o reprocessamento
                lê o estado em [1]. É PREMISSA, não medida: se o 1º backtest do 123 mostrar
                `NT123|ORFA|`, ela caiu. `z_agf_win` (entrada a mercado) já reconstrói a barra
                de entrada, mas não tem o NTSD.

## Achados do backtest do `vwapvp_continuacao` e limite de licença (2026-10-06, v4.37)

**Licença:** o pacote de automação do Diego NÃO permite gráfico de 1 s. Isso explica o 1 s sem relatório [Certo, informado pelo operador]. O `ignicao` roda em **5 s com `BarrasJanela` 12** (a janela de 60 s é a mesma, a referência
fica até 5 s mais grossa); o carimbo da contagem inclui "gráfico de 5 s".

**vwapvp (M5, 30/09–06/10, v4.36):** 4 operações, TODAS com duração exata de 1 h (o tempo máximo de 12 barras), nenhuma por alvo ou stop; bruto −535, +405, +1.585, −240 pts (+1.215 pts, R$ 243): uma operação
responde por 130% do total, n = 4. Zero ORFA: o conserto do estado funcionou.

    SUSPEITA    [Provável] as ordens ToCover (alvo/stop) não estão atuando. Operação 4: venda em 206.055
                às 11:20 de 06/10; o próprio log do ignicao mostra o WIN em 205.145 às 11:56, 910 pts a
                favor; o alvo é 0,5 SD (SD da sessão chegou a 1.028 pts só no fim do dia, então < ~500 pts
                às 11:20) e mesmo assim saiu por tempo, em 206.295 (−240). Operação 3: +1.585 pts em 1 h
                sem tocar o alvo.
    CAUSA       [Chutando] não sei. Nas 7 operações do ignicao as mesmas ordens ToCover funcionaram. A
                diferença é de gráfico (M5 de tempo, não 5 s) ou de nível; falta medir.
    MEDIDA      v4.37: log `NTSVD` no vwapvp (sem LastBarOnChart): High/Low da barra, níveis guardados e
                `HasPendingOrders` depois de enviar os ToCover.

**`NTSVD`:** `NTSVD|Bar|Date|Time|High|Low|Close|Pos|LadoPos|AlvoPx|StopPx|BarsPos|Ops|Motivo|Evento|Pend|Z|SD|VWAP`.
Ler: se `High`/`Low` cruzaram `AlvoPx`/`StopPx` e a posição continuou, o ToCover não atuou; `Pend = 0` com `Pos = 1` = as ordens nem existiam depois do envio.

**`NTSD` (diagnóstico, uma linha por avaliação com posição, sinal ou evento; sem `LastBarOnChart`):**
`NTSD|Bar|Date|Time|Close|Pos|LadoAnt|LadoPos|Ops|BarsPos|Refrat|Lado|Status|Evento|AlvoPx|StopPx`
Como ler: duas linhas com o MESMO `Bar` = reprocessamento do mesmo candle. `Pos = 1` com `LadoAnt = 0` e `Evento = 11` = o conserto agiu. `Evento = 9` = perda de estado fora do caso coberto.

## O que NÃO sei (nenhum item testado; é o que eu verificaria primeiro)

[Chutando] ≈ 8 itens, por ordem de risco:

1. **Compila?** Escrevi contra o manual e os `.ntsl` que já rodam. Nenhum compilador à mão. O primeiro erro de compilação é esperado.
2. **Em que candle o reprocessamento pós-fill roda.** [CONFIRMADO em 06/10 (NTSD, ignicao): é o MESMO candle, reprocessado depois do fill.] O manual (11.11) diz "reprocessa o mesmo candle para as ordens Cover"; assumi que é o candle em formação (t+1), com os níveis lidos de `[1]`. Se for o candle t, o estado do sinal se perde e a estratégia cai no ramo `ORFA` e fecha a posição que acabou de abrir.
3. **Reavaliação no meio do candle sem posição.** Se uma cover fechar a posição no meio de um candle, o código roda de novo com a barra PARCIAL. O guarda de relógio (`CurrentTime >= fim da barra`) cobre vwapvp e 123; na ignição o refratário de 30 min cobre.
4. **OCO re-editada a cada barra.** Em 1 s isso pode virar enxurrada (`ModoSaidaOCO = 0` é a saída).
5. **`DailyResult(False)` e taxas**: o `DescontarCusto` pode estar contando o custo em dobro ou não contando.
6. **Ligar a automação no meio do dia**: o histórico é reprocessado; se o Profit simular ordens nos candles passados, os contadores nascem sujos.
7. **Ordem no `WINFUT`**: ver "Rolagem do WIN".
8. **Limite automático do stop** quando omitido: o manual diz 30 ticks para futuros BMF; passei `SlackStopPts` explícito (150 no vwapvp/ignição, 50 no 123 como no Python).
9. **`BalanceAgent` é o mesmo número que o `agf` do Python?** O Python soma contratos do agente 3 (comprador − vendedor) nos negócios de agressão, sobre o volume de agressão.
   O NTSL só oferece saldo FINANCEIRO por agente. Não sei se o saldo inclui RLP/leilão, nem como ele trata o preço dentro do candle. O z não depende da escala constante, mas depende do resto.
10. **Barra de 120.000 lotes**: o que o Profit conta e como carrega o excesso. Diferença aqui desloca todas as barras e invalida a comparação com o Python.
11. **Histórico do `BalanceAgent`**: o manual diz "no máximo até o dia anterior". Não sei se isso significa candles do dia anterior ao carregar o gráfico ou só o saldo agregado.
12. **`BalanceAgent`/`VolumeAgent` com `AgenteId` vindo de `input`**: o manual diz que funções de indicador só aceitam constantes nos parâmetros. Input é constante em tempo de execução, mas
    não conferi que o compilador aceite. Se recusar: trocar `AgenteId` por `3` literal.
13. **Uma automação por conta** (item 8 de "Como ligar").

## Quando o DLL voltar

- `profit-tape backfill` recupera os negócios dos dias sem captura (janela de 30 dias do Profit); **o book ao vivo desses dias não volta**.
- Desligar as automações NTSL (as quatro) antes de subir o `record` com `--ea-dir config/`.
- `z_agf_win`: fazer a conferência do item 4 acima com o tape recuperado.
- A contagem NTSL e a do Python ficam em carimbos separados; o relatório do forward não mistura.

## Relação com as fichas

Nenhum número das fichas mudou. `config/*.yaml` intactos (o `config_sha` do Python não muda). O porte não altera o EA Python: `sinal_*`, `ciclo_123`, `gate_fluxo` e `perfil_volume` são a **especificação** e continuam sendo o que roda quando o DLL voltar.
