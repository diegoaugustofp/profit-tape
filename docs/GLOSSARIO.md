# Glossário do profit-tape

> **Status:** vivo — **Revisado:** 2026-09-24 — **Assunto:** os termos que o projeto usa com sentido próprio, uma linha cada, com ponteiro para onde o termo é definido; não repete definições longas, aponta.

Termos em ordem alfabética. Quando um termo tem dois sentidos no
projeto, as duas entradas estão marcadas com ⚠ e explicam qual é qual.
Convenção de ponteiro: `DOC §n` = seção de `docs/DOC.md`; `eas/x` =
ficha em `docs/eas/`.

## A

- **absorção** — feature Tier 1: `vol_agr / max(range_em_ticks, 1)` — volume alto andando pouco preço. Não-direcional. Triada por regime: até 2019 é volume disfarçado, de 2020 é range disfarçado (`RESEARCH_PLANO`, "a absorcao MUDA DE IDENTIDADE"). `FEATURES.md`.
- **absorcao_dir** — indicador NTSL de absorção direcional, exploratório; a hipótese que desenha foi CONTRA nas 12 células em 2026-08-30. Não é sinal. `NTSL_ABSORCAO.md`.
- **agf_{id}** — (comprado − vendido pelo agente `id`) / volume de agressão da barra, só agressão; top-N agentes por volume. `z_agf_3` é o do agente 3 (XP, varejo). `FEATURES.md`; `eas/z_agf_3`.
- **agente** — corretora (código `agent_id` da DLL), comprador ou vendedor de cada negócio. Resolvido para nome por `profit-tape agents`. Nunca é o cliente final.
- **ambígua (operação)** — barra em que alvo e stop cabem no mesmo [low, high]; o OHLC não ordena. Excluída do p1, reportada. `eas/README`.
- **amostra de depuração** — pregões a partir de 2026-08-14 (fichas de preço) usados para olhar barras uma a uma e corrigir FÓRMULA; nunca para ajustar NÚMERO nem para interpretar. `eas/README`; skill `profit-tape-disciplina`.
- **anomalia medida** — método de gerar hipótese a partir de uma descrição (categoria features, zero trial) onde o mercado é estranho, com contraparte nomeada antes da ficha. `RESEARCH_PLANO`, "COMO GERAR E REFINAR HIPOTESE".
- **ATR14** — SMA14 do TrueRange, a variante que o Profit calcula (Wilder erra até 73 pts). `EAS_DE_PRECO §2`.

## B

- **backfill** — `profit-tape backfill`: puxa o histórico de TRADES pela DLL. Book não tem backfill. Cura a pesquisa, não a execução. `OPERACAO.md`.
- **barra de tempo** — barra M15 que o EA constrói do tape, alinhada em hh:00/15/30/45; fecha pelo primeiro trade que cruza a fronteira ou pelo relógio. `ea/barra_tempo.py`; `EAS_DE_PRECO §5.4`.
- **barra de volume** — barra que fecha quando o volume de AGRESSÃO acumulado cruza o threshold (120.000 no WIN); RLP e leilão entram na barra mas não a fecham. Não atravessa dia. `FEATURES.md`.
- **book_offer / book_price / tiny_book** — os três streams de livro gravados (deltas do offer book por ordem; book por preço; topo do livro). `tiny_book` é ~1 M eventos/pregão e é o usado como feature no Bollinger. `domain/enums.py`; `INTEGRIDADE_DOS_DADOS.md`.
- **borda (bruta / líquida)** — P&L médio por operação em pontos, antes / depois do custo de 11 pts. Custo é condição comercial, não propriedade da estratégia. `eas/bollinger_scalp`.
- **bundle** — `git bundle` incremental (`tag_anterior..tag_nova`) que é a ÚNICA forma de o código sair do sandbox de Claude para a máquina do operador. Skill `profit-tape-engenharia` §1.

## C

- **carimbo** — tag `entregue-vX.YY` + hash (sha256 dos parâmetros da ficha, do modelo `.pkl`, do YAML do EA) gravado em cada observação de teste ou forward. Resultados com carimbo diferente nunca se somam. `eas/*`.
- **catálogo de hipóteses mortas** — tabela hipótese / morreu por / aprendizado sobre a CATEGORIA. `RESEARCH_PLANO`, "COMO GERAR E REFINAR HIPOTESE", item 4.
- **categoria features / consome trial** — ver **trial**.
- **circuit breaker** — bloqueio do EA após 3 perdas consecutivas no dia. É risco, nunca veredito: não autoriza parar um teste. `ea/risco.py`.
- **cláusula vs estrato** — cláusula filtra o evento (muda a hipótese); estrato só fatia o resultado para reporte, sem veredito próprio. Escolher o estrato bom depois de ver é p-hacking. Skill `profit-tape-disciplina` §7.4; `eas/README`.
- **clustering / deff** — sinais que chegam em rajadas na mesma janela de contexto não são independentes; `deff` (2,56 no Bollinger) alarga os IC. `BOLLINGER_SCALP §11-12`.
- **combinado** — placar de teste + replicação + histórico de uma ficha, onde o veredito final é dado quando a sequência inteira foi declarada. `eas-preco-combinar`.
- **conta demo / real** — corretora 32006 (Simulador Nelogica) / 1003 (XP). O E4 só toca a demo, por trava no código. `RUNBOOK_E4 §0`; `.env.example`.
- **contraparte** — quem está do outro lado e por que é obrigado a estar (rolagem, hedge de opção, ajuste). Obrigatória antes de escrever hipótese desde 2026-09-16. `RESEARCH_PLANO`, "COMO GERAR E REFINAR HIPOTESE".
- **curated / raw** — `raw` é o que o record gravou (pode ter reentrega dobrada); `curated` é raw deduplicado e ordenado. Features, replay e EA leem curated. `profit-tape curate`.
- **custo máximo suportado** — borda bruta por contrato: o custo ida-e-volta máximo que a estratégia paga. Alerta no EA, não critério. `eas/bollinger_scalp`.

## D

- **D** — distância entrada→stop (e alvo, simétrico) de uma ficha de preço, em pontos ao tick. Varia por ficha: K × ATR14 (IFR2), A (ORB), geométrico (123), |entrada − close_v| (gap). `eas/*`.
- **deflacionado (limiar / IC)** — limiar do IC que sobe com os trials acumulados (DSR); no teste de fichas, IC 97,5% no 2º trial de uma família na mesma amostra (Bonferroni), 98,3% no 3º. `RESEARCH_PLANO` (research); `eas/ifr2_m15`, `eas/bollinger_scalp`.
- **despachante (de EAs)** — `DespachanteDeEAs` + `RegistroDeEAs`: roteia trades a vários EAs dentro de um record, inclui/remove por arquivo (`--ea-dir`). `EA_ARQUITETURA §2` (E5.4).
- **diário (de sinais)** — JSONL com uma linha por SINAL, inclusive os que não viraram ordem (desfecho: executou / rejeitado_gate / gate_indefinido / sem_vaga / posicao_aberta …). O Profit só sabe o que executou. `ea/diario.py`; `EA_ARQUITETURA §6`.
- **dry_run** — EA decide e loga, não manda ordem. `simulado=True`: não toma nem respeita vaga. `RUNBOOK_E4`.
- **duplicatas / reentrega** — o mesmo trade_id entregue duas vezes com campos idênticos (benigno; curate resolve) vs. campos diferentes (edição de negócio). `profit-tape duplicatas`.

## E

- **E0–E5 (escada)** — infraestrutura de EXECUÇÃO: E0 exports de ordem; E1 login completo; E2 ordem real na demo; E2b stop/limitada/cancel/OCO; E3 reconciliação de posição; E4 forward em demo medindo slippage; E5 multi-EA a quente (E5.0–E5.6). Ortogonal a F0–F6. `EA_ARQUITETURA §2`.
- **EA** — expert advisor: a estratégia em execução (YAML em `config/` + núcleo em `ea/`). Roda DENTRO do record porque uma chave de ativação = uma conexão.
- **EMD** — efeito mínimo detectável: 1,96 × desvio / √n, calculado só da variância e do n, antes de ver a média. Se exige efeito implausível, o desenho é abandonado sem que isso seja p-hacking. `RESEARCH_PLANO`; `DESENHO_2`.
- **entregue-vX.YY** — tag sequencial de cada entrega de código. Ver **bundle**.
- **estrato** — ver **cláusula vs estrato**.
- **exclusivo (modo ticker)** — `--ea-modo-ticker exclusivo`: dois EAs no mesmo ticker, só um posicionado por vez (vaga). `EA_ARQUITETURA §2` (E5.4c).

## F

- **F0–F6 (pipeline)** ⚠ — as sete fases de QUALQUER estratégia: F0 hipótese, F1 features, F2 triagem, F3 pré-registro, F4 depuração (replay), F5 forward demo, F6 produção. F4 mede BORDA, F5 mede EXECUÇÃO. Não confundir com **Fase 0/1/2 do DeepScalper**. `EA_ARQUITETURA §0`.
- **Fase 0 / 1 / 2 (DeepScalper)** ⚠ — etapas do pré-registro específico do DeepScalper: Fase 0 inventário, Fase 1 simulador de replay, Fase 2 classificador supervisionado (em forward), Fase 3 RL (não autorizada). São etapas dentro de uma estratégia, não fases do pipeline. `eas/deepscalper_fase2`.
- **família** — conjunto de fichas que testam a mesma ideia sobre a mesma amostra; a família consome trials, e o 2º trial na mesma amostra paga IC deflacionado. Mudar K, limiar, janela ou amostra = família nova. `eas/README`.
- **features (categoria)** — ver **trial**.
- **ficha** — o pré-registro de uma estratégia: hipótese, evento, taxa, efeito, horizonte, critério, parada (a "ficha de seis linhas" do regime forward). Congelada = não se edita; versões empilham. Uma por estratégia em `docs/eas/`.
- **fluxo_nacional** — `agf` somando TODOS os agentes classificados NACIONAL. Única feature de perfil que validou. `RESEARCH_PLANO`, "fluxo_nacional implementado".
- **footer (verificado)** — o `.parquet` só recebe esse nome depois de fsync + releitura dos magic bytes do disco (INV1); antes é `.inprogress`. `REVISAO_STORAGE.md`.
- **forward** — teste sobre pregões que ainda não existiam quando a regra foi congelada. Em demo com ordens reais (F5/E4), ou offline (score diário da Fase 2). Skill `profit-tape-disciplina-forward`.
- **funil** — contagem de quantos eventos cada cláusula de uma ficha deixa passar, medido ANTES de congelar (categoria features). `eas-preco --ficha`.

## G

- **gate / porta de volume** — cláusula de fluxo sobre um sinal de preço, declarada no dia 1 da linha de preço como "interface, não conteúdo". Hoje: `GateVolumeBaixo` (volume da barra t abaixo da mediana do horário). `eas/123_volume_baixo`; `EAS_DE_PRECO §6`.
- **gate indefinido** — barra sem `volume_confiavel` ou sem perfil de 20 pregões: sinal fora, contado. `eas/123_volume_baixo`.

## H

- **h (horizonte)** — número de barras da saída por tempo (Rota A) ou da janela do label (triple barrier). `z_agf_3` usa h=3. `eas/z_agf_3`.
- **hash_ficha** — ver **carimbo**.
- **histórico (amostra)** — out/2015 a dez/2022 no dump do gráfico, para as fichas de preço. Dá n, não homogeneidade: **o WIN quebrou em 2020**. `RESEARCH_PLANO`, "RESULTADO DA TRIAGEM…2020".

## I

- **IC (walk-forward)** ⚠ — `profit-tape research`: coeficiente de informação da feature vs retorno futuro, por fold, com veredito deflacionado por trials. `RESEARCH_PLANO` (topo).
- **IC95 (de Wilson)** ⚠ — intervalo de confiança de p1 nas fichas. Contexto desambigua: "passa no IC" é o walk-forward; "IC [0,515; 0,542]" é Wilson.
- **ignorado_posicao** — sinal que chegou com posição aberta; contado, fora do p1. `eas/README`.
- **imbalance / tick_imbalance** — (vol_buy − vol_sell)/vol_agr e a versão por número de negócios. Direcionais. `FEATURES.md`.
- **inprogress** — arquivo Parquet ainda sem footer verificado. Órfão após travamento → `triagem-inprogress`. `OPERACAO.md`.
- **inconclusivo** — veredito entre FAVORÁVEL e CONTRA. Nas fichas de preço, inconclusivo = fecha (não vira "mais dado com a mesma regra"). "Não achamos borda" ≠ "provamos que não há". `eas/bollinger_scalp`.

## L

- **livro (de posições)** — `LivroDePosicoes` por (EA, subconta, ticker). `EA_ARQUITETURA §2` (E5.1).
- **login completo** — `--login-completo`: conexão com roteamento de ordens, além de market data. `EA_ARQUITETURA §2` (E1).

## M

- **M15** — barra de 15 minutos do gráfico do Profit, timeframe da linha de EAs de preço.
- **MAE / MFE** — excursão máxima adversa / favorável de uma operação (no close da barra: `_close`). Origem do par stop 100 / alvo 120 da Rota B. `eas/z_agf_3`.
- **mecanismo antes de número** — regra 0 da disciplina: validar que o desenho faz sentido em uma frase antes de calibrar qualquer limiar. Skill `profit-tape-disciplina`.
- **MME80** — média móvel exponencial de 80 fechamentos em M15; define o regime das fichas de preço. Ver **regime**.

## N

- **NSSM** — supervisor de serviço Windows que reinicia o record se ele cair no meio do pregão. `NSSM_SERVICO.md`.
- **NTSL** — linguagem de indicadores do Profit. Cada `.ntsl` do projeto tem parser Python gêmeo, e mudança de semântica sai nos dois lados na mesma entrega. Skill `profit-tape-engenharia` §3.1-3.2.
- **nula (a custo zero)** — p1 = 0,50 com barreiras simétricas; na Fase 2, fração de eventos com alguma barreira tocada / 2 (0,337). Custo não entra na nula. `eas/README`; `eas/deepscalper_fase2`.

## O

- **OCO** — one-cancels-other: stop + alvo, um executou → cancela o outro. É do EA; a DLL não tem. `eas/123_m15`.
- **operação por tempo** — zerada às 17:30 sem tocar alvo nem stop. Fora do p1; P&L na zeragem reportado. `eas/README`.

## P

- **p1** — fração das operações resolvidas em que a barreira favorável é tocada antes da desfavorável. O estimador binário das fichas. `eas/README`.
- **perfil (de corretora / de volume)** ⚠ — perfil de corretora: classificação NACIONAL/ESTRANGEIRO/etc. de agentes (`perfil-validar`); perfil de volume horário: mediana de volume por hhmm nos 20 pregões anteriores (`PerfilVolumeHorario`, gate do 123).
- **poder** — probabilidade de detectar o efeito declarado com o n disponível; checado antes de interpretar (n ≥ 60 no Bollinger) e antes de pré-registrar (triagem de poder). Skill `profit-tape-disciplina`.
- **ponte pelo tape** — completar a semente (MME80, perfil) com as barras do dia corrente construídas do tape até o instante atual. `ea/semente.py`.
- **portador** — papel do 123 no forward: não aposta de P&L, mas o primeiro sinal real a atravessar a estrutura multi-EA e o gerador da amostra do gate. `eas/123_m15`.
- **pré-registro** — escrever motivação, mudança e critério de decisão ANTES de rodar. Ver **ficha**. Skill `profit-tape-disciplina` §1.

## Q

- **quarentena** — `raw/_quarentena/` e `profit-tape quarentena`: arquivos Parquet corrompidos (footer ausente ou row group ilegível) e resíduo de dia anterior, separados do dado bom. `OPERACAO.md`.
- **queimado (dado / pregão)** — amostra já usada por um teste da família; não pode ser reutilizada sem IC deflacionado e nunca para o estrato escolhido depois. `eas/123_gate_volume_alto`.
- **quintis** — tradução econômica de um "segue" do IC: retorno por quintil da feature, com custo real; sinal estatisticamente real pode morrer aqui (`z_agf_3` h=1). `RESEARCH_PLANO`, "Segunda rodada de quintis".

## R

- **reconciliação** — `ReconciliadorPosicao`: posição do EA vs posição na corretora; diverge → zera. `EA_ARQUITETURA §2` (E3).
- **regime** ⚠ — (1) nas fichas de preço: `close` vs MME80 (a favor / contra), como cláusula ou estrato; (2) na triagem de features: a quebra estrutural de 2020 (variância de log-volume caiu de 1,24 para ~0,3), `por_regime` no combinar. `EAS_DE_PRECO §2`; `RESEARCH_PLANO`, "…o WIN quebrou em 2020".
- **replicação (amostra)** — 2026 até 13/08 nas fichas de preço; reportada depois do teste primário, sem veto sobre ele. `eas/README`.
- **RLP** — retail liquidity provider: negócio internalizado (código 13), ~25% do WIN; entra na barra sem fechá-la; `rlp_frac` é proxy de varejo. `FEATURES.md`.
- **rolagem** — troca do contrato vencendo pelo seguinte (WINV26 → WINZ26 na semana de 05/10). Como hipótese, reclassificada: a assinatura é o par casado entre contratos, não a série contínua. `RESEARCH_PLANO`, "RECLASSIFICACAO: rolagem".
- **Rota A / Rota B** — Rota A: saída por tempo (h barras) + stop catastrófico largo — a que foi validada. Rota B: overlay de stop/alvo fixos (100/120) checados no close da barra; pesquisa fechou que o stop não detecta reversão. `eas/z_agf_3`; `EA_ARQUITETURA`, "Rota A escolhida".

## S

- **semente** — estado inicial de um indicador contínuo (MME80, perfil de volume) carregado do parquet do gráfico antes do pregão; `semente_valida` no diário. `ea/semente.py`; `semente-conferir`.
- **7a / 7b** — passos do desenho de F5 do 123: 7a pregão inteiro em dry_run ao vivo (fechado 21/09); 7b E4 com ordens reais (iniciado 22/09). `EAS_DE_PRECO §5.4`; `EA_ARQUITETURA §2`.
- **simulado (EA)** — ver **dry_run**.
- **skill** — instruções que vivem no Project do Claude.ai, fora do repositório: `profit-tape-disciplina`, `profit-tape-disciplina-forward`, `profit-tape-engenharia`. `INSTRUCOES_DO_PROJETO_CLAUDE.md`.
- **slippage** — fill real − nível teórico, entrada e saída somados. A medida do E4; critério ≤ 6 pts. `eas/123_m15`.
- **stop catastrófico** — 500 pts (2% de R$5.000 a R$0,20/pt): seguro de cauda da Rota A, quase nunca tocado — mas checado só no close da barra (deixou passar −615). `eas/z_agf_3`.
- **supervisor (de risco)** — `SupervisorDeRisco`: calcula e avisa sobre o risco agregado dos EAs; informativo, nunca trava. Capital nunca restringe uma ficha (decisão 4.9). `EA_ARQUITETURA §2` (E5.0).

## T

- **tape** — a sequência de negócios com agente agressor e passivo. O que o projeto tem e quase ninguém tem. Escasso (desde 2026-07-24), e por isso a linha de preço existe em paralelo.
- **teste (amostra)** — 2023-25 nas fichas de preço: primário, UMA rodada; `eas-preco-teste --amostra teste` recusa a segunda. `eas/README`.
- **Tier 1 (features)** — as definições travadas em `FEATURES.md`: imbalance, tick_imbalance, absorção, rlp_frac, agf_{id}, fluxo_nacional, OHLC/vwap de agressão.
- **trial** — uma rodada de teste de hipótese que sobe o limiar deflacionado. Comandos **consomem trial** (`research`, `eas-preco-teste`) ou **não consomem** (categoria `features`: `features`, `quintis`, `mae-analise`, `ea-replay-lote`, descrições, funis, releituras de estrato já reportado). Skill `profit-tape-disciplina` §2.
- **triagem** — antes de pré-registrar: redundância com features existentes, poder (dá para decidir em < 6 meses?), e por regime quando a feature é razão. `profit-tape triagem`, `triagem-absorcao`.
- **triple barrier / label** — desfecho de uma barra em h barras: +1 se toca k·σ para cima antes, −1 se para baixo, 0 se o vertical vence; empate resolvido pelo tape. `features/labels.py`; `eas/deepscalper_fase2`.

## V

- **vaga** — no modo exclusivo, o direito de estar posicionado no ticker; `sinais_sem_vaga` no diário. EA simulado não toma vaga. `EA_ARQUITETURA §2` (E5.4c).
- **vigia** — watchdog externo ao record, via schtasks; alerta o que o record não pode alertar sobre si. `profit-tape vigia`.
- **volume_confiavel** — barra sem parcial nem lacuna de feed > 5 s; barra não confiável = gate indefinido e fora do perfil. `eas/123_volume_baixo`.

## W

- **WINFUT / WINV26** — `WINFUT` é o ticker agregador (serve para DADO); ordem só no contrato específico (`WINV26`, depois `WINZ26`). A DLL não faz cross-order no envio. `EA_ARQUITETURA §2`, "Lições da escada".
- **WDO** — mini-dólar; instrumento de replicação das fichas de preço (nenhuma sobreviveu lá, exceto o 123 em volume baixo, que separa). `EAS_DE_PRECO §8`.

## Z

- **z_\*** — z-score por dia (janela de 50 barras, aquecimento de 25) de uma feature; convenção compartilhada por research e EA. Qualquer coluna `z_*` entra no `research`. `FEATURES.md`.
- **zeragem 17:30** — fechamento forçado de qualquer posição. Operação assim é "por tempo". `eas/README`.
