# Resumo da sessão, roteiro operacional e roadmap — 2026-08-27

Documento de consolidação, escrito ao fim de um dia excepcionalmente longo
de trabalho. Objetivo: dar uma visão de conjunto do que foi decidido e
construído, sem precisar reler a sessão inteira; e registrar a disciplina
operacional daqui para frente, para não depender de memória.

---

## 1. O que foi CONCLUÍDO hoje

### Infraestrutura
- **NSSM configurado e validado em produção**: teste de resiliência real
  passou (kill -9 do processo, reinício em segundos). `schtasks` trocado
  para chamar `nssm start` — resolve de vez as falhas de disparo
  automático desta semana. Modo de logon confirmado correto (pediu senha,
  não sessão interativa).
- **Travamento de máquina tratado e automatizado**: incidente real (todos
  os streams/ativos ficaram com `.inprogress` órfão simultaneamente) —
  criada ferramenta `triagem-inprogress` que acha, verifica footer, e
  promove ou quarentena automaticamente, para não repetir o processo
  manual da próxima vez.
- **`quarentena` com filtro de data** (`--dia`/`--desde`/`--ate`) — não
  precisa mais varrer o histórico completo a cada validação incremental.
- **Bug real de teste corrigido**: `cache_logger_on_first_use` causava
  vazamento de estado global do `structlog` entre testes, dependente de
  ordem de execução — fechado com fixture global + causa raiz.
- **Política de retenção disco local vs backup**: documentada (lacuna
  real identificada — sem regra fixa ainda, decisão de convenção
  permanece do operador).
- **Disciplina "quando rodar research"**: formalizada — `features` sem
  custo, `research` só com pelo menos `teste_dias` (2) dias novos
  acumulados desde a última rodada, idealmente uma semana.

### EA — arquitetura e mecânica
- **Bug crítico de performance resolvido**: `ea-replay` travava 3+ horas
  em `pyarrow.dataset().to_table()` combinando múltiplos fragmentos —
  substituído por leitura arquivo-a-arquivo + concatenação. Causa
  raiz nunca identificada dentro do `pyarrow` (não precisou ser — o
  contorno empírico resolveu, provado pelo próprio diagnóstico do
  operador).
- **Decisão de arquitetura de longo prazo FECHADA**: EA roda **dentro**
  do processo do `record`, mesma conexão — motivo comercial (licença
  Nelogica permite só UMA chave de ativação, validado com o time deles).
- **EA integrado: IMPLEMENTADO e testado ponta a ponta** — `EABridge`
  (fila própria, filtra por símbolo, nunca bloqueia a captura, erro
  contido) + `record --ea-config` (opcional, retrocompatível). Testado
  com `RecorderService` real (não só unitário): captura idêntica ao
  caso sem EA, EA processa os trades certos.
- **`lado_permitido` (restrição de direção)**: implementado, testado,
  pré-registrado e **rodado**: veredito **FAVORÁVEL** (pnl +3228 vs
  -533, razão ganho/perda 1,128 vs 1,08) — mas é confirmação de
  engenharia sobre o MESMO período que revelou a assimetria, não
  validação out-of-sample nova.
- **`--comparar-circuit-breaker`**: automatiza a comparação com/sem
  freio por dia e por lado — não decide sozinho, mas dá o dado para
  decidir com mais confiança no futuro.
- **Curva de patrimônio / drawdown máximo**: implementada, conectada ao
  `ea-replay-lote` — responde "que capital preciso alocar", mas
  deliberadamente **não cobre zeragem por consumo de garantia** (pendência
  separada).

### Pesquisa — achados substantivos
- **MAE/MFE**: implementados, com disciplina de pool out-of-sample
  (bug real corrigido no caminho). MAE mostrou o stop catastrófico
  funcionando como seguro de verdade (não corta caudas ganhadoras).
- **Assimetria compra/venda confirmada por 3 métodos independentes**
  convergindo na mesma direção: venda com edge real, compra sem edge.
- **`risco-realizado` (VaR/ES)**: primeiro passo aplicado da literatura
  de Realized Quantiles — conexão de design real com a escolha de barras
  por volume (tempo intrínseco) já feita no projeto. Achado concreto:
  o stop de 500pts cobre ~98,7% agregado, mas só **~90-95% na abertura**
  especificamente — sazonalidade intradiária afeta a calibração de
  risco, não só o IC.
- **`z_agf_8` (fluxo UBS) FECHADO**: morto nas ações (custo, confirmado
  duas vezes com custo corrigido) e não passou no IC do WINFUT (já
  testado em 2026-08-23, confirmado sem gastar trial novo).
- **Correção de custo de ações real**: planilha da XP decodificada —
  custo tem componente FIXO (corretagem) e PROPORCIONAL (taxas B3) ao
  financeiro. Custo por ação não é constante entre ativos de preços
  diferentes, mesmo mantendo risco equivalente.

---

## 2. O que ainda está PENDENTE

| Item | Status | Observação |
|---|---|---|
| Forward-test em DEMO, pregão real | **Não feito** | EA integrado só testado com `FakeProfitDLL` — próximo passo natural e prioritário |
| Conta real XP habilitada | Não feito | Depende da XP, fora do nosso controle |
| `SendOrder` real usando a mesma conexão | Não decidido | Reabre pergunta de licenciamento para ROTEAMENTO (diferente de sinal em dry_run) |
| Rota B (payoff fixo alvo/stop) | Preparação feita (MFE), overlay **não implementado** | Par stop/alvo exato ainda não congelado — próximo passo é rodar `mae-analise` por lado e congelar o número |
| Zeragem por consumo de garantia | **Fora de escopo, registrado** | Precisa da tabela de margem real B3/XP, não implementado |
| Segmentação de IC por horário (não só risco) | Parcial | Feito para `risco-realizado`; não feito para o IC do `research` em si |
| Robustez em regime de mercado diferente | Pendente antiga | Todo o histórico é do mesmo período (êxodo de capital estrangeiro) |
| `research` novo | Aguardando | Decisão do operador — esperar mais dias (mín. 2, meta: 1 semana) |
| Convenção fixa de retenção de disco | Pendente | Decisão do operador, não urgente |

---

## 3. Roteiro de disciplina operacional

### Diário (todo pregão)
1. **`record`** — captura ao vivo (com `--ea-config` quando o forward-test
   começar).
2. **`curate`** — assim que o pregão fechar / `record` encerrar. Nunca
   rodar com `.inprogress` na árvore (o próprio comando recusa).
3. **`triagem-inprogress`** — só se houve travamento/reinício no meio do
   dia (não é rotina, é resposta a incidente).
4. **Backup** (robocopy para o disco externo) + **`quarentena --dia`**
   (validação incremental, nunca o histórico completo).
5. **`features todos`** — sem custo, sempre que convier depois do
   `curate`.

### Semanal (ou quando ≥ `teste_dias` dias novos acumularem — meta: 1 semana)
1. **`research`** — só com dado novo suficiente para formar um bloco de
   teste genuinamente novo.
2. Revisão de pendências em aberto (esta lista).

### Sob demanda / por evento (não fixo, não obrigatório)
- `mae-analise`, `risco-realizado`, `ea-replay-lote` — rodar quando
  houver uma pergunta específica a responder, não como rotina fixa.
- Revisão da calibração do circuit breaker (`max_perdas_consecutivas`)
  — só depois de MUITOS eventos de disparo acumulados (hoje: 12 em 24
  dias — ainda cedo para decidir).
- Revisão da calibração do stop catastrófico — conforme mais dado
  acumular no `risco-realizado`, considerando a segmentação por horário.

---

## 4. Próximos passos — incluindo o que ainda não foi planejado

### Imediato (decorre direto do que já foi construído hoje)
1. **Forward-test em DEMO com pregão real** — a peça que faltava
   (integração EA+record) está pronta; falta só testar em condição real.
2. **Congelar o par stop/alvo da Rota B** — rodar `mae-analise` por lado
   (venda), pegar a mediana de MAE/MFE, arredondar, registrar o número
   exato antes de qualquer código novo em `risco.py`.

### Médio prazo (identificado, não iniciado)
3. **Cruzar `risco-realizado` com a tabela de margem real B3/XP** —
   fecha a lacuna de "zeragem por garantia" que hoje fica de fora da
   curva de patrimônio.
4. **Segmentar o IC do `research` por horário do pregão** — mesmo
   princípio já aplicado ao risco, ainda não aplicado à significância
   do sinal em si.

### Em aberto, ainda sem forma definida — "novo EA com outra estratégia"

Duas avenidas concretas já existem parcialmente, vale decidir entre elas
quando chegar a hora:

**a) Reaproveitar o motor já construído (`SinalConfig`/`decisao.py`/
`risco.py`) com um sinal diferente.** O framework do EA não é
específico do `z_agf_3` — qualquer feature já calculada
(`z_fluxo_nacional`, `z_absorcao`, `z_imbalance`, `z_tick_imbalance`,
outros `z_agf_N`) pode virar um novo `ea_*.yaml` sem escrever código
novo, desde que passe pelo mesmo funil (`research` → `quintis` →
significância) primeiro. Custo de implementação baixo — o gargalo é
achar um sinal que sobreviva ao funil, não a engenharia.

**b) SMC (Smart Money Concepts) — já existe código parcial, nunca
testado em forward real.** `SMC_Structure.mqh`, `SMC_POI.mqh`,
`SMC_Diario.mq5` (MQL5, rodando no MT5, não no Python/ProfitDLL) —
sistema de estrutura de preço (BOS/CHoCH/Order Blocks), calibrado mas
não forward-testado. Decisão em aberto: portar a lógica para o mesmo
framework Python (unificando com o motor de fluxo), ou manter os dois
sistemas separados (MQL5 para estrutura, Python para fluxo).

**c) Meta-labeling combinando estrutura (SMC) com fluxo (`agf`)** —
ideia registrada há tempo em `PREREG-FLUXO-EST2-F1` (7 campos ainda em
aberto, documento nunca congelado). Combina as avenidas (a) e (b): a
estrutura de preço definiria a direção, o fluxo decidiria executar ou
passar. Não iniciado.

### Visão de longo prazo (mencionada, não ativa)
- Multi-mercado: EUA (tastytrade/ActivTrades), cripto (Binance) — research
  pipeline citado como visão, zero desenvolvimento até agora.

---

*Este documento é um snapshot do estado em 2026-08-27. Não é
atualizado automaticamente — releia com ceticismo se muito tempo tiver
passado desde a data acima.*
