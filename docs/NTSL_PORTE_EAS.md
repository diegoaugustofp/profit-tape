# Porte dos EAs para NTSL (contingência da queda do ProfitDLL)

> **Status:** vivo — **Revisado:** 2026-10-07 — **Assunto:** `vwapvp_continuacao`, `ignicao`, `ea_123_vb` (E4) e `z_agf_win` (Rota A, v4.34) reescritos como estratégias de execução do Profit enquanto o ProfitDLL da Nelogica está fora; MECANISMO NOVO, carimbo e contagem próprios; NÃO COMPILADO ainda.

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
4. Gráficos: `vwapvp_continuacao` WINFUT **M5**; `ea_123_vb` WINFUT **M15**; `ignicao` WINFUT em **5 segundos com `BarrasJanela` 12** (é o que opera ao vivo desde 07/10; em 1 s seria 60). O `BarrasJanela` padrão do arquivo é 60: **um replay/backtest sem o input ajustado roda outra regra** (janela de 5 min e refratário de 150 min num gráfico de 5 s; aconteceu em 07/10). Desde a v4.42 o console imprime `NTSI|PARAMS|...` no primeiro candle; confira-o em todo replay.
5. Ligar **antes** da abertura da janela (vwapvp 11:00; ignição 09:16; 123 09:30). Contadores e bloqueios recomeçam em zero se ligar no meio do dia.
6. **Nunca junto com o `record` no mesmo ticker e conta.** O Python tem "vaga do ticker"; o NTSL não o conhece. Quando o DLL voltar: desligar as automações NTSL ANTES de subir o `record`.
7. Market Replay: `GuardaRelogio = 0` (o relógio do PC é o de hoje, não o do replay).
8. **Uma CARTEIRA por automação** (resolvido por informação do Diego em 2026-10-07: o Profit oferece o recurso de carteira; uma carteira por automação executa sem interferir
   nas outras e admite posições simultâneas e contrárias). Sem isso, duas automações na MESMA conta e no mesmo ativo somariam a posição líquida e a lógica de estado (que assume
   que a posição é dela) quebraria. Vale para o simulador; **não testado em conta real** (não é o caminho pré-registrado). A isolação entre carteiras foi observada em 07/10
   só indiretamente (o ignição operou sozinho; os outros dois não operaram).
9. `z_agf_win`: gráfico de **120.000 lotes** (período por quantidade de lotes), não de tempo; ao vivo apenas (o `BalanceAgent` não roda em backtest). **ESTACIONADO em 2026-10-07**: o Profit não tem gráfico de 120.000; o máximo por quantidade é 10.000 (informação do Diego). Não é refutação da hipótese, só inviabilidade de teste no Profit; a equivalência de barra (10.000 ≠ 120.000) não foi medida. Arquivo e testes ficam como estão (`ModoConferir = 1`, nenhuma ordem).

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

**REGRA DO RELÓGIO E DA JANELA NO BACKTEST (2026-10-07; medida em vwapvp, vale para 123 e z_agf_win):** no backtest `CurrentTime` é o relógio do PC, não o do candle. Com `GuardaRelogio = 1` o resultado depende da hora em que se roda (só entre 18:30 e 23:59 todas as barras "terminaram"; às 00:13 deu ZERO operações, `Fechou = 0`).
Backtest: `GuardaRelogio = 0` e datas inicial/final EXPLÍCITAS (a janela padrão anda com a data: 30/09–06/10 virou 01/10–07/10 e a operação de 30/09 sumiu; as outras 5 saíram idênticas). Ao vivo: `GuardaRelogio = 1`. Conferir sempre `Fechou = 1` no `NTSV`/`NT123`/`NTZA` do backtest.

## Regra das passadas do backtest e alarme `ALVO_CRUZADO` (2026-10-07, v4.38)

**Medido (6/10, console do vwapvp e do ignicao, primeira x segunda execução):** o editor de estratégia do Profit roda o backtest em VÁRIAS passadas (o console repete o histórico inteiro).
Na primeira execução do vwapvp foram 3 passadas (1.864, 1.835, 1.835 linhas); na segunda, 2 (1.835, 1.835). No ignicao: 4 passadas (3.469, 1.935, 362, 362) contra 2 (362, 362).

    [Certo] Candles iguais: nas 1.829 barras comuns à passada 0 e à 1 do vwapvp, High, Low, Close, z, SD e VWAP
            não diferem (0 divergências). A hipótese "dado incompleto" NÃO explica a diferença.
    [Certo] Passada 0 do vwapvp: `Pend = 1`, o preço cruzou o alvo (30/09 15:00, High 188.760 contra alvo 188.750)
            e a posição seguiu aberta; as 4 saídas foram por tempo (`Evento 3`, 12 barras). Por isso só 4 entradas
            (a posição ainda estava aberta nos sinais de 01/10 12:15 e 02/10 16:55). PnlDia −251 nessa passada, +414 nas finais.
    [Certo] Passadas finais (as duas últimas, idênticas entre si e à segunda execução): 6 operações no vwapvp, todas
            saindo por alvo (5) ou stop (1) exatamente no nível; 7 no ignicao (alvo 4, stop 3).
    [Certo] Ignicao, passadas iniciais: saídas por tempo com `BarsPos` até 721 e 533 avisos do Profit
            ("...ToCoverStop enviado com stop abaixo da abertura do candle. Em automação essa ordem pode ter
            comportamento diferente"). Esses avisos NÃO existem na segunda execução.
    [Chutando] causa: nas passadas iniciais o simulador não executa as ordens ToCover (intrabarra ainda não
            carregado?). Não provado.

**REGRA (vale para todo backtest NTSL):** só conta como depuração a lista de operações das DUAS ÚLTIMAS passadas do console, que têm de ser idênticas entre si, e o relatório depois de "atualizar".
Primeira execução, ou execução com avisos de ToCover, NÃO vale. Diego já tinha visto isso como "4 operações, depois 6".

**Alarme (v4.38, só diagnóstico, comportamento idêntico à v4.35/v4.37; novo input `AlarmeCruzado(1)`):**
`NTSI|ALVO_CRUZADO|Date|Time|Bar|LadoPos|AlvoPx|StopPx|High|Low|BarsPos` (ignicao) e `NTSV|ALVO_CRUZADO|...` (vwapvp, mesmos campos).
Dispara quando há posição, `BarsPos >= 1` (candle posterior ao de entrada, cuja faixa não inclui o pré-fill) e o High/Low do candle cruzou alvo ou stop: a ordem ToCover deveria ter executado.
Não depende de `LastBarOnChart` (aparece no backtest). **Ao vivo, uma linha destas é DEFEITO DE EXECUÇÃO: PARADA imediata, o dia não conta.**
Conferido sobre o console do vwapvp (condição reaplicada em Python às linhas `NTSVD`): passada 0 da primeira execução = 24 disparos; passadas finais e segunda execução = 0. No ignicao não dá para conferir (o `NTSD` não traz High/Low).

**Carimbos novos (comportamento inalterado; a contagem do ignicao ainda NÃO começou, começa em 07/10):**
`ignicao.ntsl` sha256 `0da080ab35cb…` (substitui `30248ebe0439…`), `vwapvp_continuacao.ntsl` sha256 `6891f8a2db47…`. Gráfico: ignicao 5 s com `BarrasJanela` 12; vwapvp M5.

**NÃO coberto:** o alarme só enxerga cruzamento em candle posterior; uma falha do ToCover no próprio candle de entrada não aparece. Se o Profit rodar passadas iniciais ao vivo, não sei. `ea_123_vb` e `z_agf_win` não receberam o alarme (123 sem backtest validado; z_agf em `ModoConferir`, sem ordens).

## Backtest do `ea_123_vb`: 0 operações (2026-10-07, v4.39)

Backtest WINFUT M15, 30/09–06/10, `GuardaRelogio = 0`: **0 operações**. O console tem só a linha do último candle (`LastBarOnChart`), 06/10 18:15:
`GateN = 0`, `Med = 0`, `Motivo = 2` (fora da janela), `Fechou = 1`.

    [Certo]     o relógio não é o problema (Fechou = 1) e o log não diz por que nenhum dia armou.
    [Certo]     existe candle com label 18:15 em 06/10. O código supõe `BarrasPorDia = 37`
                (09:00..18:00) e o 1º candle do dia às 09:00; com 09:00..18:15 são 38.
    [Provável]  `BarrasPorDia` errado desalinha o perfil de volume (a conferência do label de hora falha),
                o gate fica INDEFINIDO (`GateN < 20`, Motivo 6) e nada arma, em silêncio. É o caso que
                a conferência do 1º pregão já previa (item 3). `GateN = 0` num candle fora da janela
                também pode ser só aquele candle; falta ver as barras da janela.
    [Chutando]  0 operações em 5 pregões é raro se a regra gera ~1 sinal/dia depois do gate (li as
                fichas de relance, não conferi a taxa).

**Medida (v4.39, só diagnóstico, comportamento idêntico, novo input `LogDiag(1)`; sem `LastBarOnChart`):**
`NT123|DIA|Date|BarrasDoDia|UltimaHora` (uma linha por pregão; dia cheio esperado: 38 e 1815 se o pregão for 09:00–18:15)
`NT123D|Bar|Date|Time|Fechou|PadC|PadV|Regime|D|LadoCand|VolT|Med|GateN|GateOk|Motivo|Evento|Close|Mme`
(toda barra da janela com padrão 123 ou evento). Ler: `Motivo 6` = gate indefinido (alinhamento); `5` = gate reprovou; `3` regime; `4` D < mínimo; `1` armou.
Se `BarrasDoDia` ≠ 37, trocar `BarrasPorDia` é mudança de parâmetro com pré-registro próprio (mecanismo de alinhamento do perfil, não calibração de número).
Carimbo novo: `ea_123_vb.ntsl` sha256 `172244413fd5…` (nunca contou).

## 123: `BarrasPorDia` medido e ORFA confirmado (2026-10-07, v4.40)

**Barras por pregão (M15 WINFUT, console completo 2015–06/10/2026, 2.718 pregões, `NT123|DIA`):** 36 (último 17:45) no horário de verão americano; 37 (18:00) em 2015–2020 no inverno; **38 (18:15) em todo o período desde 15/02/2024** (e no inverno desde 2020).
Pregões curtos isolados desde 2024: Quarta de Cinzas (22 barras, abre às 13:00), 21/08/2025 (35), 31/07/2026 (24). `BarrasPorDia = 37` NUNCA batia: o gate ficava indefinido em 100% das barras (`GateN = 0`, `Med = 0`, 113 padrões 24/09–06/10 bloqueados em `Motivo 6` ou `3`). [Certo] Essa foi a causa dos zero trades.
**Default agora 38** (alinhamento com o que o Profit entrega, medida, não calibração). Falha fechada: pregão curto ⇒ gate indefinido nos 20 pregões seguintes (1 a 3 eventos por ano ≈ 20–60 pregões), nunca sinal errado. A janela 30/09–06/10 tem 45 pregões de 38 barras desde 03/08, então o gate vale.

**Com 38 (`GuardaRelogio = 0`, `CalcDataInicio = 1260924`, 24/09–06/10):** `GateN = 20` e `Med > 0` nas 123 barras com padrão; 23 armadas (`Motivo 1`), 38 reprovadas pelo gate (`Motivo 5`), 52 por regime (`Motivo 3`), 10 por `Evento 9` (ORFA).
**[Certo] ORFA no 123:** as 10 linhas `Evento 9` vêm em 5 pares (a barra de arme e a seguinte: 30/09 10:45/11:00, 11:45/12:00, 13:00/13:15, 15:30/15:45 e 06/10 14:00/14:15). A premissa registrada na v4.36 ("o STOP enche em t+1 com estado gravado em t") era FALSA: o Profit reprocessa o candle de arme depois do fill e o estado gravado não está em `[1]`, o mesmo mecanismo do ignicao/vwapvp. Cada ORFA fechava a posição na hora.

**Conserto (v4.40, mesmo padrão da v4.35/v4.36):** o sinal é calculado ANTES do bloco de posição (puro, sem ordens); com posição e estado ausente, se o sinal se reproduz, o estado é reconstruído SEM nova ordem (`Evento 11`); senão ORFA como antes. `Motivo 7` = com posição.
Risco declarado: uma posição órfã de outra origem pode ser "reconstruída" com o candidato de uma barra que por acaso tenha sinal (o `Evento 11` aparece no log e no `NT123D`).
**NÃO coberto:** nunca compilado nem rodado depois do conserto; não sei se o preenchimento do STOP no simulador é o do mercado; o backtest antigo (5 pares ORFA) não conta, nem o novo.
Carimbo novo: `ea_123_vb.ntsl` sha256 `a33f82b505f0…` (nunca contou). Formato `NT123D`/`NT123|DIA` da v4.39 inalterado; `Evento 11` = reconstruído.

## 123: backtest depois do conserto e alarme `ALVO_CRUZADO` (2026-10-07, v4.41)

**Backtest 123 M15, 30/09–06/10, `BarrasPorDia` 38, `GuardaRelogio` 0, duas últimas passadas idênticas (v4.40):** zero `NT123|ORFA|`, cinco `Evento 11` (as mesmas 5 barras que antes davam ORFA), `GateN = 20`.
CSV de operações cruzado com o `NT123D` (`D` = distância entrada–stop; alvo e stop a ±`D` da entrada): 5 operações, todas de compra, todas encheram na barra seguinte à de arme e saíram EXATAMENTE em alvo ou stop:

    30/09 10:45  D 765  +765 alvo | 30/09 11:45  D 705  −705 stop | 30/09 13:00  D 950  +950 alvo
    30/09 15:30  D 355  −355 stop | 06/10 14:00  D 505  +505 alvo         total +1.160 pts (R$ 232)

[Certo] o conserto e o ToCover funcionam no 123 no backtest. [Certo] n = 5, depuração, NÃO conta. [Provável] o simulador enche alvo/stop no nível, sem deslizamento: otimista; o stop-limite com folga 50 nunca foi testado contra gap.

**Alarme (v4.41, só diagnóstico, input `AlarmeCruzado(1)`):** `NT123|ALVO_CRUZADO|Date|Time|Bar|LadoPos|AlvoPx|StopPx|High|Low|BarrasDesdeArme`.
Dispara com posição, sem `Evento 11`, níveis > 0 e `CurrentBar >= ArmBar + 2` (o fill é em t+1 do arme; a faixa do candle do fill inclui o pré-fill) quando o High/Low cruzou alvo ou stop. Mesma regra dos outros: **ao vivo, uma linha destas é DEFEITO DE EXECUÇÃO: PARADA imediata, o dia não conta.** Não confirmado contra console (o `NT123D` não traz High/Low); a condição segue o ignicao/vwapvp, onde foi reaplicada ao `NTSVD` (24 disparos na passada inicial, 0 nas finais).
Carimbo novo: `ea_123_vb.ntsl` sha256 `b768ec42c477…` (nunca contou). Contagem do 123 NTSL: só simulador ao vivo, a partir da data em que o Diego ligar com este carimbo.

## 07/10 no simulador: níveis velhos no ignição, replay ≠ ao vivo (2026-10-07, v4.42)

**Primeiro pregão em simulador (carteira por automação).** Só o ignição operou. `vwapvp` e `ea_123_vb` ligados, sem ordem. Os três arquivos conferidos contra o repositório (v4.41): o hash de quem roda no Windows sai com fim de linha CRLF e difere do carimbo; com LF bate. **O carimbo vale sobre o arquivo com LF** (hash CRLF equivalente: vwapvp `1594D08D0712` = `6891f8a2db47`; ignicao `890DCB0DD5DF` = `0da080ab35cb`; 123 `A64003163831` = `b768ec42c477`).

**Ignição ao vivo, 4 operações** (relatório de operações + log de ordens; todas as entradas nos múltiplos de 5 s ⇒ gráfico de 5 s; espaço entre detecções 31:30, 30:05, 42:55 ⇒ refratário de 30 min ⇒ `BarrasJanela` 12):

    09:31:10–10:02:36  C  +620 alvo   níveis 206.715 / 205.655   ok
    10:02:40–10:02:40  C    −5         níveis 206.715 / 205.655   DEFEITO (iguais aos do trade 1)
    10:32:45–11:09:12  V  +495 alvo   níveis 205.640 / 206.700   ok
    11:15:40–11:38:45  C  −510 stop   níveis 206.265 / 205.205   ok     (total +600 pts, R$ 120)

**Defeito (níveis velhos).** A compra de 10:02:40 enviou o ToCover com o alvo 206.715 do trade 1, abaixo do preço de entrada (206.770): a limitada de venda ficou executável e saiu a 206.765, 0,13 s depois. [Provável] Mecanismo: o candle anterior foi avaliado com o trade 1 aberto e gravou seus níveis; o reprocessamento do candle de entrada lê `[1]`, que não está zerado; a reconstrução (v4.35/36/40) só roda com níveis zerados e não rodou. Bate com todos os números do log de ordens; **não** confirmado por console (não existe ao vivo). A mesma estrutura existe no vwapvp e no 123 (só acontece com entrada no candle seguinte à saída anterior; não verifiquei se ocorreu nos backtests).

### Pré-registro v4.42 (escrito antes de codificar; autorizado pelo Diego em 2026-10-07)

    MOTIVO     Trade 2 do ignição em 07/10 (acima).
    REGRA      Com posição e DailyResult(False) diferente do registrado no candle anterior
               (|Δ| > 0,001; vale ganho e perda), os níveis lidos de [1] são descartados
               antes do bloco de posição; a reconstrução (Evento 11) ou o ORFA assumem. Só se
               aplica com HasPosition; o fluxo sem posição não muda.
    OBSERVAVEL Coluna final `Descarte` em NTSD / NTSVD / NT123D (só aparece em backtest/replay).
    PARAMS     Linha `NTSI|PARAMS|` / `NTSV|PARAMS|` / `NT123|PARAMS|` no primeiro candle
               (diagnóstico; BarrasJanela, SegBarra, RefratBarras etc.).
    CRITERIO   Ao vivo, nenhuma entrada com ToCover em níveis diferentes dos do próprio sinal
               (conferido no log de ordens: alvo do lado certo do preço de entrada, ±D/±530).
    LIMITE     Trade fechado com resultado exatamente 0 não dispara o descarte [Chutando: raro].
    CARIMBOS   Mudam os três arquivos. Nada foi contado ainda, então a contagem recomeça sem custo.
    DIA INVALIDO (acréscimo, escrito DEPOIS de ver o dado de 07/10; efeito numérico no ignição:
               −5 pts): qualquer entrada cujo ToCover não corresponda ao próprio sinal.

**Dia 07/10 do ignição não conta** (execução com níveis errados). Os outros 3 trades ficam como amostra de depuração.

### Replay do ignição ≠ ao vivo: parâmetro, não "modo de execução"

O console do replay (NTSD, 05–07/10) mostra `Refrat = 1800` na armada. O código define `Refrat = RefratarioSeg / (60 / BarrasJanela)`; 1800 ⇒ `BarrasJanela = 60`. As barras andam de 5 em 5 s (ex.: 76 barras em 7 min), então o replay rodou com janela de **5 min** (ref = fechamento 60 barras atrás) e refratário de **150 min**, enquanto o ao vivo usava 12. Detecções do replay em 07/10: 09:24 (alvo em 09:31) e 12:24; ao vivo: 09:31:10, 10:02:40, 10:32:45, 11:15:40; **zero coincidência**. Os consoles de 05–06/10 desse arquivo também têm `Refrat = 1800`. Conclusão: este replay não serve de comparação com o ao vivo. Refazer com `BarrasJanela = 12`, gráfico de 5 s, mesmo período, e comparar a lista de detecções com as 4 do ao vivo (horário ±5 s, lado, nível); se coincidirem, o caminho histórico do ignição reproduz o ao vivo; se não, é caminho de dados.

### 123 e vwapvp: o replay armou, o ao vivo não

Replay de 07/10: vwapvp armou às 12:25 com `z = −2,0198` (limiar 2,0; margem 1%) e fechou com −546 pts líquidos (custo de 11 incluso; [Provável] no stop 205.280); 123 armou às 12:30 com volume 452.302 contra mediana 472.268 (razão 0,958) e bateu o alvo (+790 pts, R$ 158), mais uma armada às 15:45 (razão 0,927) sem fill. Ao vivo: nenhuma ordem.
Marginalidade medida nos mesmos consoles (replay, 01–07/10): no vwapvp 19 de 50 armadas (38%) têm \|z\| < 2,10 e 11 (22%) < 2,05; no 123, 4 de 5 armadas têm volume ≥ 90% da mediana. [Provável] Sinais assim mudam com diferença pequena no volume do candle formado em tempo real contra o histórico consolidado. [Chutando] Também possível: `Fechou = 0` (relógio, Motivo 8) ou `GateN < 20` (histórico carregado, Motivo 6). **Sem console ao vivo não há como separar as hipóteses.** Dia ao vivo do vwapvp e do 123 em 07/10: zero operações, **sem evidência de que avaliaram as barras certas**.

Testar o caminho ao vivo: o Market Replay do Profit (replay de mercado) alimenta os candles negócio a negócio, como ao vivo, com `GuardaRelogio = 0`. NÃO SEI se o console da automação aparece nesse modo; é a primeira coisa a verificar.

## 07/10: o buraco das 12:12 e a caixa desmarcada (2026-10-08, v4.43)

**Fonte:** `LogDesktop_2026_10_07.log` do Profit (pasta `Roaming\Nelogica\Profit\Logs`), lido em 08/10. O console da automação AO VIVO existe: aparece no log de eventos da própria automação (tela) e no `LogDesktop` como `Event=Evento Personalizado (ConsoleLog)`. **A afirmação anterior "o Profit não guarda o console ao vivo" (item 14 de "O que NÃO sei") estava errada.**

**Por que o vwapvp e o 123 não armaram às 12:25 e 12:30 [Certo]:** às 12:12:39 o notebook foi para a bateria (falta de energia, informada pelo Diego; o modem desligou); às 12:12:42 os pings falharam; às 12:12:46 todas as automações receberam "Servidor desconectado". A reconexão só ocorreu às 19:45:53 (a rede não voltou sozinha). Os dois sinais do replay (12:25 e 12:30) caem dentro dessa janela. **Não houve divergência de lógica.** A hipótese de "volume em tempo real contra consolidado" (seção acima) deixa de ser necessária para explicar o dia.

**Antes das 12:12, o 123 ao vivo [Certo]:** padrão presente nos candles 11:15 e 11:45, ambos reprovados pelo gate (volume final 1,13× e 1,10× a mediana). Nenhum sinal armável perdido antes da queda.

**Defeito operacional achado [Certo]:** o 123 (RobotID 7) e o vwapvp ligado na carteira antiga (RobotID 2) rodaram a cada 5–10 s dentro do candle (caixa "executar apenas no fechamento do candle ou com atualização de posição" DESMARCADA). Dos 13 candles de 15 min avaliados até 12:12, só 2 tiveram `Fechou = 1` (10:45:00.060 e 11:00:00.024): o fechamento só é visto se um tick chegar nos milissegundos entre o fim do candle e a criação do próximo. Nessa configuração o arme ao vivo funciona por sorte (2 de 13 = 15%), mesmo com rede. Toda a contagem ao vivo exige a caixa MARCADA.

**Dois vwapvp ligados [Certo]:** RobotID 2 (corretora 1003, conta 3813830, carteira 10030009, a antiga do WINV26; gerou todo o console NTSV do dia) e RobotID 5 (carteira nova 320060032, mesma conta do 123 e do ignição). O RobotID 5 fez só 40 loops, nos fechamentos de candle (caixa marcada) e **não imprimiu nenhuma linha de console**. [Provável] No modo de fechamento o loop avalia o candle anterior (`CurrentIndex/Count = 104631/104633`, contra `100637/100638` no modo desmarcado), logo `LastBarOnChart` é falso e `LogAtivo` fica mudo. [Chutando] A conta 3813830 é outra conta/corretora; o Diego deve confirmar o que ela é e desligar o RobotID 2.

### Pré-registro v4.43 (escrito antes de codificar; autorizado pelo Diego em 2026-10-08)

**Motivação:** (1) no modo "só no fechamento" o console ao vivo some, e sem ele "não operou" não tem causa observável; (2) no modo desmarcado o código roda errado e ninguém é avisado.
**Mudança (SÓ log; nenhuma ordem, nenhum estado, nenhum parâmetro novo de comportamento), em `ea_123_vb` e `vwapvp_continuacao`; a ignição NÃO muda (já avalia por tick/5 s por desenho):**
1. `NT123|HB|...` / `NTSV|HB|...` (batimento de fechamento): uma linha por candle, na primeira avaliação com `bCompleta` e `CurrentTime` até 3 min depois do fim da barra, só com `GuardaRelogio = 1` e `LogDiag = 1`, **sem `LastBarOnChart`**. Campos: Data, Hora, CurrentTime, LastBar (1/0), e o estado do sinal (padrão, regime, motivo, gate, z). Prova de que o candle foi avaliado COMPLETO e, via `LastBar`, em que modo.
2. `NT123|AVISO_MODO|...` / `NTSV|AVISO_MODO|...`: uma linha por candle quando `GuardaRelogio = 1`, `LastBarOnChart` e a barra está incompleta (só ocorre com a caixa desmarcada).
**Critério de decisão (sem calibração):** favorável = no pregão seguinte, com a caixa marcada, aparece 1 linha `HB` por candle avaliado e nenhum `AVISO_MODO`; contra/inconclusivo = nenhuma linha `HB` com a caixa marcada ⇒ o fechamento é avaliado fora da janela de 3 min ou o loop não executa o código; nesse caso a janela é o primeiro suspeito e NÃO se muda lógica de arme antes de ver o dado. Risco conhecido: ao ligar a automação o histórico é reprocessado; a janela de 3 min limita o HB a no máximo 1 candle por dia de histórico, só se ligar logo após um fechamento. Retrocompatibilidade: com `GuardaRelogio = 0` (backtest/replay) nenhuma linha nova.

### Checklist de ligar (consolidado em 08/10)

1. Caixa "executar apenas no fechamento do candle ou com atualização de posição" MARCADA nas 3 (a do 123 e a do vwapvp antigo estavam desmarcadas).
2. UM vwapvp ligado (carteira 320060032); desligar o RobotID 2 (conta 3813830) depois de confirmar o que é.
3. Gráfico/contrato: as automações estão em `WINV26`; em 14/10 (rolagem) trocar para `WINZ26` e conferir o `GateN` do 123 e o roteamento (cross-order).
4. Energia: nobreak para notebook, modem e roteador; reconexão automática do Wi-Fi/Ethernet; avisar quando o Profit mostrar "Servidor desconectado". Ao voltar a conexão, conferir se as automações continuam habilitadas.
5. Carimbo no lado do Profit: o texto é colado e compilado no editor do Profit, o byte a byte pode mudar. Compilar a v4.43 uma vez, ler o `SourceCodeMD5` no cabeçalho do dump (`LogStratDump_*.stdmp`) de cada automação e registrá-lo ao lado do sha256 do arquivo do repositório.

### Ferramenta `tools/analisa_log_profit.py`

Lê o `LogDesktop_AAAA_MM_DD.log` e resume, por automação (RobotID): linhas de console por hora, fração de `Fechou = 1`, quedas de conexão ("Servidor desconectado" até "Servidor conectado") e lacunas sem console. Feito em cima do caso de 07/10 (queda 12:12:46–19:45:53; 2 de 13 fechamentos).

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
13. ~~Uma automação por conta~~ — resolvido para o simulador pelo recurso de carteira (item 8 de "Como ligar"); não testado em conta real.
14. ~~O Profit não guarda o console ao vivo~~ — ERRADO (corrigido em 08/10): o console aparece no log de eventos da automação e no `LogDesktop`. Mas no modo "só no fechamento" o `LastBarOnChart` fica falso e o `NTSV|`/`NT123|` some (v4.43 acrescenta o batimento `HB`).
15. ~~Caminho de dados ao vivo ≠ histórico~~ — explicado em 08/10 para 07/10: os sinais de 12:25 e 12:30 caíram numa queda de conexão (12:12:46–19:45:53). A pergunta de fundo (o candle em tempo real tem o mesmo volume do consolidado?) segue sem medida; só um dia ao vivo com conexão contínua responde.

## Quando o DLL voltar

- `profit-tape backfill` recupera os negócios dos dias sem captura (janela de 30 dias do Profit); **o book ao vivo desses dias não volta**.
- Desligar as automações NTSL (as quatro) antes de subir o `record` com `--ea-dir config/`.
- `z_agf_win`: fazer a conferência do item 4 acima com o tape recuperado.
- A contagem NTSL e a do Python ficam em carimbos separados; o relatório do forward não mistura.

## Relação com as fichas

Nenhum número das fichas mudou. `config/*.yaml` intactos (o `config_sha` do Python não muda). O porte não altera o EA Python: `sinal_*`, `ciclo_123`, `gate_fluxo` e `perfil_volume` são a **especificação** e continuam sendo o que roda quando o DLL voltar.
