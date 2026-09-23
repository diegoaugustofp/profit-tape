# Roteiro do E4 — ordem real na conta DEMO

Uma página para o dia. Consolida o que estava espalhado entre o E2b, a
reconciliação (EA_ARQUITETURA 4b) e os incidentes de setembro (OPERACAO).

## 0. O que é e o que não é

- **Ordens reais na conta DEMO** (corretora 32006, Simulador). A trava é
  do código, não do yaml: o record cria o executor com
  `usar_conta_real=False` e `apenas_simulador=True` fixos, e cada envio
  confere o nome da corretora. **Não há como tocar a conta real (1003, XP)
  neste modo.**
- **Objetivo: medir EXECUÇÃO** — slippage, latência, fills parciais,
  recusas — contra o mesmo EA simulado. Não é teste de estratégia: o
  forward da estratégia continua sendo o do 123.
- **Ressalva:** o fill do demo é simulado pela Nelogica sobre o mercado
  real. Aproxima a execução, não reproduz a fila real. O slippage medido
  aqui é uma primeira estimativa, não o número final.
- **O que está em jogo num problema:** uma operação mal medida, não
  capital. Ainda assim, trate como real: o código que roda aqui é o mesmo
  que um dia vai rodar na conta real.

## 1. Na noite anterior

1. Versão **≥ v3.30** aplicada (a v3.30 é a que impede um EA simulado de
   ocupar a vaga do real).
2. Na pasta `data\eas_ativos`:
   - `ea_123_volume_baixo_e4.yaml` (`dry_run: false`, nome `ea_123_vb_e4`);
   - **recomendado: manter também** `ea_123_volume_baixo.yaml` (simulado).
     Os dois recebem os MESMOS sinais; um preenche no nível ideal, o outro
     na corretora. **A diferença entre os dois diários, sinal a sinal, é o
     custo de execução** — a medição mais limpa possível. Desde a v3.30 o
     simulado não disputa vaga com o real.
   - o `z_agf_win` pode ficar: está em `dry_run` e não bloqueia o real.
3. Comando (uma linha):

```
profit-tape record -c C:\projetos\profit-tape\config\recorder.yaml --ea-dir C:\projetos\profit-tape\data\eas_ativos --ea-modo-ticker exclusivo --capital-em-conta 20000 --login-completo --ea-ticker-ordem WINV26 --log-file C:\projetos\profit-tape\logs\record_diario.jsonl
```

4. **Contrato:** `WINV26` vence em **14/10**. Na semana de 05/10, trocar
   para `--ea-ticker-ordem WINZ26` (é um evento do forward: registrar no
   histórico o dia da troca).

## 2. No arranque, antes das 09:00 — tem que aparecer

| log | o que conferir |
|---|---|
| `energia.mantendo_acordado` | a máquina não vai dormir (se vier `energia.pedido_recusado`, não ligue o E4) |
| `recorder.heartbeat` | `login_ok=True`, `corretora_pronta=True` |
| `ea.123.iniciado` do `ea_123_vb_e4` | `dry_run=False`, semente `valida=True`, perfil com 38 horários |
| `ea_registro.incluido` | o E4 aparece com `dry_run=False` |
| `ea.123.limpeza_na_subida` (v3.31) | `acao=limpo`: o EA real cancelou TODAS as ordens do `WINV26` na conta demo e não achou posição. `zerou_orfa` = havia posição sem dono e ele zerou — confira no Profit |

**Não deve aparecer:** `recorder.ea_ordens_reais_sem_pre_requisito`,
`recorder.ea_ticker_agregador_recusado`, `ea.123.sem_semente`. Se aparecer
qualquer um, o EA real não subiu — corrigir antes das 09:00 ou seguir o
dia só com o simulado.

## 3. Durante o pregão — a vida de uma operação

```
ea.123.armado            sinal na barra t; ordem de entrada (stop) enviada
  (aceite: New)          confira no Profit: ordem na conta Simulador
ea.123.fill              entrada executou
ea.123.posicionado       stop e alvo ENVIADOS (~1 s depois do fill)
ea.123.fill              stop ou alvo executou
ea.123.operacao_fechada  desfecho, slippage por ordem, latências
```

- A entrada vale só durante a barra t+1; sem fill, é cancelada
  (`nao_executou`).
- **Zeragem às 17:30:** cancela o que estiver pendente e zera a mercado.
- **A janela sensível:** entre o fill da entrada e o envio de stop e alvo
  (~1 s). Se a máquina ou a rede cair exatamente aí, a posição fica sem
  saída na corretora até o EA voltar.

## 4. Sinais de problema e o que fazer

| aparece | significa | faça |
|---|---|---|
| `ea.123.aviso ... CONFIRA NO PROFIT` | timeout de callback, cancelamento ou zeragem não confirmados | olhe a ordem e a posição no Profit; anote o horário |
| `ea.123.posicao_orfa` | posição que o ciclo não conhece | o ciclo zera a mercado; confira no Profit que zerou |
| `ea.123.posicao_inesperada` (v3.31) | na volta de uma queda a posição real não bate com a esperada — p.ex. INVERTIDA porque stop e alvo executaram os dois | o ciclo cancela tudo do ativo e zera; confira no Profit |
| `ea.123.reconectado` + `ea.123.reconciliado` | a conexão caiu e voltou | leia `acao` no `reconciliado`: re-armou saída, fechou como `reconciliado` ou zerou órfã |
| heartbeat parado, ou `sem_evento_ha_s` alto no pregão | máquina ou rede | abra o Profit: **posição sem stop → zere à mão** (seção 5) |
| `ea.123.atrasado` | EA mais de 5 s atrás do mercado | anote; se for constante, é assunto de desempenho |
| `ea.123.stop_protegido` (v3.32) | o stop disparou num salto além do limite e **não executou**; o EA cancelou as duas pernas e zerou a mercado | confira no Profit que zerou e anote o preço; no diário a operação vem com `stop_protegido` e desfecho `stop` |
| `POSICAO CONTRARIA -- zerando a mercado` (v3.32) | as duas pernas executaram; o EA zera na hora | confira no Profit |
| ordem recusada pela corretora | — | pare o E4 (critério da seção 7) |

**Stop e alvo NÃO são OCO na corretora** (observado pelo operador em
22/09 e confirmado no extrato: duas ordens `Normal`, independentes). A DLL
não oferece OCO nativo; quem cancela a perna que sobra é o EA. Consequência:
com o EA fora do ar, a perna que sobra pode **abrir uma posição nova** mais
tarde. Coberturas (v3.31):
- processo PAROU e voltou: a reconciliação cancela ordem a ordem, e trata
  a posição invertida (`posicao_inesperada`);
- processo MORREU: na subida, `limpeza_na_subida` cancela TODAS as ordens
  do ativo na conta e zera o que houver. Custo declarado: cancela também
  ordens manuais do ativo nessa conta.

### Teste do cancelamento total — FEITO em 23/09, PASSOU

`ea.cancel_todas_enviado retorno=0`, `acao=limpo`, `posicao_real=0`, e a
ordem manual apareceu **Cancelada** no Profit. A limitação da ordem órfã
de processo morto deixa de valer.

Dois aprendizados do teste, para quando precisar repetir:

- **Antes da abertura a chamada é recusada** (`NL_INVALID_ARGS`, com a
  posição também implausível). Desde a v3.38 o EA repete a cada 60 s até
  conseguir, então basta esperar o mercado abrir.
- **Não use o próprio E4 para o teste.** Ao ser recolocado na pasta no
  meio do pregão, o EA recomeça a montar barras e cai em
  `ea.dia_incompleto` — **não arma mais nenhum sinal naquele dia** (foi o
  que aconteceu em 23/09). Use um **yaml descartável**: copie o do E4 com
  outro `nome` e outro `registro_dir`, coloque na pasta, confira a
  limpeza no log, e tire depois. O E4 fica intocado.

## 5. Intervir à mão sem confundir o EA

1. **Sempre que possível, retirada graciosa:** tire o
   `ea_123_volume_baixo_e4.yaml` da pasta (`recorder.ea_removido_por_arquivo`).
   O EA cancela as próprias ordens (entrada, stop, alvo) e **envia** a
   zeragem a mercado. O record continua gravando.
   **Atenção (conferido no código):** em modo real o EA sai logo depois de
   ENVIAR a zeragem, sem esperar a execução. A zeragem executa na
   corretora do mesmo jeito, mas a linha `ea.123.operacao_fechada
   desfecho=zeragem` **pode não aparecer**, e essa operação pode ficar sem
   registro no diário. **Confira no Profit que a posição foi a zero** e
   anote o preço da zeragem no histórico.
2. **Se o EA não responde** (máquina travada, log parado): zere e cancele
   tudo no Profit, **depois** tire o yaml da pasta.
3. Antes de recolocar o yaml no mesmo dia: confira no Profit que **não há
   ordem viva nem posição** na conta Simulador.
4. Anote no `HISTORICO_DE_SESSOES.md`: horário, o que viu, o que fez.

## 6. Depois do fechamento

```
profit-tape diario data\forward\ea_123_vb_e4 --ea ea_123_vb_e4
profit-tape diario data\forward\ea_123_vb --ea ea_123_vb
```

- **EXECUCAO** do E4: slippage por papel (entrada, stop, alvo, zeragem) e
  latências de aceite e fill.
- Compare com o simulado **sinal a sinal** com o comparador (v3.33):

```
profit-tape e4-comparar --real data\forward\ea_123_vb_e4 --simulado data\forward\ea_123_vb --curated data\curated --dia 2026-09-22
```

  Ele mostra, por ordem: nível, fill real, fill simulado, **custo em
  pontos** (positivo = executou pior) e o **pior preço negociado no tape**
  nos 2 s seguintes ao cruzamento. O bloco final responde se a demo
  preenche no ideal: se as ordens com mercado pior forem as mesmas que
  executaram no nível, a demo não reproduz a fila — e o E4 em demo mede
  latência e robustez, **não slippage**.
- Confira o **extrato da conta Simulador no Profit**: operações, preços e
  quantidades batem com o diário do E4?
- Cure o dia (`--dia`) e registre no histórico: operações, slippage médio,
  intervenções.

## 7. Critérios declarados ANTES

**Pare o E4 e investigue** (não é fim do forward, é defeito a entender):
- posição sem stop por mais de 1 minuto;
- ordem recusada pela corretora;
- divergência entre o diário do E4 e o extrato do Profit.

**O que o E4 responde, ao fim de ~50 pregões:** se o slippage médio por
operação cabe no custo declarado na ficha (≤ 6 pts). Não se muda regra de
entrada, stop ou alvo no meio — o diário dimensiona, não escolhe.
