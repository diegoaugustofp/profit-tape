# Referencia da CLI `profit-tape`

> **Status:** vivo (GERADO) — **Revisado:** pela ultima execucao de `tools/gera_referencia_cli.py` — **Assunto:** todos os comandos de `src/profittape/cli.py`, agrupados por categoria, com a nota de trial e o documento de referencia. NAO EDITE A MAO: rode o script.

74 comandos. Categoria e documento vem do dicionario no script; nome e descricao vem do docstring do proprio comando (`profit-tape <cmd> --help` mostra as opcoes).

A distincao que mais importa: comandos que **consomem trial** sobem o limiar deflacionado a cada rodada e so' devem rodar com dado NOVO suficiente; os que nao consomem podem rodar quando quiser (skill `profit-tape-disciplina`, 2).

## Captura (todo pregao)

*nao consome trial.*

| comando | o que faz | referencia |
|---|---|---|
| `agents` | Resolve codigos de corretora em nomes via GetAgentNameById e grava um CSV de referencia (agent_id, nome) para join nas analises de fluxo. | RESEARCH_PLANO.md |
| `backfill` | Puxa o historico de TRADES dos ativos do config. | OPERACAO.md |
| `bench` | Mede a folga do pipeline NESTA maquina, com a DLL falsa. | ARQUITETURA.md |
| `doctor` | Diagnostico antes de gravar: DLL carrega, exports batem, credencial existe, disco tem espaco. | README.md |
| `inspect` | Resumo do que foi gravado. | OPERACAO.md |
| `record` | Grava tape e book ate o horario configurado ou ate Ctrl+C. | OPERACAO.md |

## Dado: curadoria, integridade, historico

*nao consome trial.*

| comando | o que faz | referencia |
|---|---|---|
| `compact` | Reescreve o raw de dias FECHADOS consolidando row groups minusculos. | REVISAO_STORAGE.md |
| `curate` | Deduplica e ordena raw -> curated. | RESEARCH_PLANO.md (DECOMPOSICAO RODOU, 2026-08-31) |
| `duplicatas` | Diagnostica trade_id repetido: edicao de negocio (campos diferem) x reentrega benigna (campos identicos). | INTEGRIDADE_DOS_DADOS.md |
| `quarentena` | Acha (e opcionalmente remove) arquivos .parquet corrompidos — fosseis sem footer da era do fsync quebrado, ou (com --profundo) row groups internamente corrompidos que passam pelo footer. | OPERACAO.md |
| `triagem-inprogress` | Triagem de .parquet.inprogress orfaos apos travamento de maquina (2026-08-27) -- um travamento derruba TODOS os writers abertos no instante, um por stream/simbolo, simultaneamente. | OPERACAO.md |

## Features e triagem (categoria features)

*nao consome trial.*

| comando | o que faz | referencia |
|---|---|---|
| `curva-poder` | EMD em funcao do limiar de contexto K. | DESENHO_2_absorcao_com_risco.md |
| `desenho2-emd` | Simula a gestao do DESENHO 2 e mede o EMD, antes de congelar. | DESENHO_2_absorcao_com_risco.md |
| `features` | Gera barras de volume (relogio de agressao) com features de fluxo Tier 1, z-scores anti-lookahead e labels triple-barrier. | FEATURES.md |
| `features-tempo` | Features em BARRA DE TEMPO para o pre-registro da absorcao direcional. | RESEARCH_PLANO.md |
| `fluxo-vs-grafico` | O GRAFICO SUBSTITUI O TAPE? | RESEARCH_PLANO.md (O grafico substitui o tape?) |
| `ntsl-equivalencia` | Confronta o indicador NTSL com as features calculadas em Python. | NTSL_ABSORCAO.md |
| `perfil-validar` | Valida a classificacao de corretoras contra a serie oficial da B3 — ANTES de gastar trials de IC em features de perfil (pre-registrado). | RESEARCH_PLANO.md |
| `perfil-volume-horario` | Perfil de volume de AGRESSAO por faixa horaria (mediana entre pregoes). | eas/123_volume_baixo.md |
| `regime-funil` | REGIME: funil de RLP e topo do livro (tiny_book) sobre os sinais. | BOLLINGER_SCALP.md |
| `triagem` | Tria uma feature candidata ANTES de gastar trial. | skill profit-tape-disciplina 7.2 |
| `triagem-absorcao` | TRIAGEM (7.2) da absorcao de grafico, ANTES de qualquer ficha: `absorcao = volume / range` tem o range no denominador. | RESEARCH_PLANO.md (TRIAGEM 7.2 da absorcao) |

## Pesquisa que CONSOME trial

*cada rodada sobe o limiar deflacionado.*

| comando | o que faz | referencia |
|---|---|---|
| `absorcao-barra` | ABSORCAO DE BARRA — pre-registro congelado em 2026-08-31. | RESEARCH_PLANO.md (pre-registro 2026-08-31) |
| `absorcao-grafico` | Roda o pre-registro da absorcao sobre dados do GRAFICO. | RESEARCH_PLANO.md |
| `portao-absorcao` | PORTAO DE HONESTIDADE do pre-registro de 2026-08-29e — bloqueante. | RESEARCH_PLANO.md (portao 2026-08-29e) |
| `remanescente-apos-toque` | PRE-REGISTRO 2 (2026-08-29b): no instante em que eu sairia a -X, qual a expectativa de CONTINUAR ate' o fim da janela? | eas/z_agf_3.md |
| `research` | IC walk-forward das features com veredito deflacionado por trials acumulados. | RESEARCH_PLANO.md (topo) |
| `reversao-condicional` | Testa a hipotese (b) do PRE-REGISTRO congelado em 2026-08-29: o movimento contra a posicao é EVIDENCIA de que o edge expirou, ou so' ruido normal que metade das operacoes atravessa antes de pagar? | eas/z_agf_3.md |
| `rota-b-remanescente` | ROTA B — expectativa remanescente a partir do toque, com F exato. | eas/z_agf_3.md |

## Traducao economica e entendimento de sinal ja' validado

*nao consome trial.*

| comando | o que faz | referencia |
|---|---|---|
| `absorcao-diagnostico` | Distribuicao do ESFORCO (vol_agr/tick) e separacao A/B da absorcao. | RESEARCH_PLANO.md |
| `absorcao-inspecionar` | Por que ESTA barra marcou (ou nao marcou)? | NTSL_ABSORCAO.md |
| `custo-acoes` | Custo de day trade de UMA acao, calculado a partir da planilha real da XP -- devolve o numero pronto para `--custo-pontos` do comando `quintis`. | EAS_DE_PRECO.md 8.2 |
| `decompor-efeito` | FASE DE ENTENDIMENTO: onde o efeito esta', nao se ele existe. | RESEARCH_PLANO.md |
| `decomposicao-drawdown` | PRE-VOO da pergunta de drawdown (2026-08-30): de onde vem o drawdown maximo -- poucas operacoes grandes, uma sequencia, ou um dia ruim? | eas/z_agf_3.md |
| `mae-analise` | MAE (Maximum Adverse Excursion) por operacao -- responde se o stop catastrofico e' so' seguro de cauda (raramente tocado) ou ja esta mordendo de verdade dentro da janela real de holding do sinal. | eas/z_agf_3.md |
| `quintis` | Tabela de quintis: traducao economica dos vereditos 'segue' do IC — sinal estatisticamente real pode ser economicamente morto pelo custo de transacao. | RESEARCH_PLANO.md (quintis) |
| `risco-realizado` | VaR e Expected Shortfall REALIZADOS sobre o retorno de barra do instrumento -- aplica o insight central de "Realized Quantiles" (2026-08-27, ver research/risco_realizado.py para a fundamentacao completa) para calibrar... | RESEARCH_PLANO.md |

## EAs de PRECO (M15): fichas, funis, testes

*`eas-preco-teste` consome trial; funis e combinar, nao.*

| comando | o que faz | referencia |
|---|---|---|
| `eas-preco` | EAs de PRECO (M15): equivalencia Python x Profit + funil da ficha (`--ficha ifr2`, fechada em 2026-09-14, ou `--ficha orb`). | EAS_DE_PRECO.md; eas/*.md |
| `eas-preco-combinar` | Placar COMBINADO das amostras (teste + replicacao + historico_2015_22) de uma ficha, com o por-ano reportado. | EAS_DE_PRECO.md |
| `eas-preco-teste` | IFR2 M15: o TESTE da ficha congelada (docs/EAS_DE_PRECO.md 3.2). | EAS_DE_PRECO.md; eas/*.md |

## Scalp de Bollinger (15 s)

*replay e funis nao consomem; o veredito e' pela ficha.*

| comando | o que faz | referencia |
|---|---|---|
| `bollinger-contexto` | Scalp de Bollinger: FUNIL do estocastico de CONTEXTO (6 min). | BOLLINGER_SCALP.md 8 |
| `bollinger-direcao` | Scalp de Bollinger: conteudo direcional do sinal (5.6), SEM regra de saida. | BOLLINGER_SCALP.md 5.6 |
| `bollinger-replay` | Scalp de Bollinger: replay das tres pernas pelo TAPE (depuracao). | BOLLINGER_SCALP.md 5 |
| `bollinger-scalp` | Scalp de Bollinger (15s): equivalencia Python x Profit + funil da regra. | eas/bollinger_scalp.md |
| `diagnostico-multitf` | Armadilhas do modelo de DOIS TIMEFRAMES (features, zero trial). | BOLLINGER_SCALP.md 11-12 |
| `valida-ohlc-6min` | Fecha a lacuna 11.4: o OHLC de 6 min do PROFIT contra a NOSSA agregacao das barras de 15s. | BOLLINGER_SCALP.md 14-15 |

## DeepScalper (Fases 0-2)

*score de forward: uma ficha, um trial em curso.*

| comando | o que faz | referencia |
|---|---|---|
| `fase2-preparar` | Fase 2 DeepScalper, passo "antes de ligar" (RESEARCH_PLANO, FICHA FORWARD). | eas/deepscalper_fase2.md |
| `fase2-score` | Forward da Fase 2: escora o(s) pregao(oes) com o modelo CONGELADO, grava uma linha por evento em forward_eventos.csv com carimbo (tag + sha256 do modelo) e imprime o placar. | eas/deepscalper_fase2.md |
| `inventario-deepscalper` | Fase 0 do pre-registro DeepScalper (RESEARCH_PLANO.md, 2026-09-07): barras/pregao (TAXA), barras/hora (define `h`), spread em ticks, pregoes com book integro (portao de 160 da Fase 3). | eas/deepscalper_fase2.md |
| `simulador-conferir` | Fase 1 do pre-registro DeepScalper, conferencia 3: o simulador de replay (features.parquet) reproduz o P&L do ea-replay-lote (trades ao vivo) para a regra que o EA ja' roda? | eas/deepscalper_fase2.md |

## Descricoes por contraparte / anomalia medida (passo 1)

*nao consome trial.*

| comando | o que faz | referencia |
|---|---|---|
| `book-recomposicao` | RECOMPOSICAO NO LIVRO, passo 1 (v2): oferta que SAI do livro e cujo lugar e' reposto pelo MESMO agente, no mesmo preco e tamanho, em segundos. | RESEARCH_PLANO.md (RECOMPOSICAO NO LIVRO) |
| `defasagem` | DESCRICAO da defasagem WIN x CESTA (passo 1): quem chega primeiro? | RESEARCH_PLANO.md (DEFASAGEM) |
| `fechamento` | DESCRICAO do AJUSTE/FECHAMENTO (passo 1): o fluxo obrigatorio do fim do pregao (ajuste = margem; zeragem de day trade) deixa marca numa janela estreita? | RESEARCH_PLANO.md (AJUSTE/FECHAMENTO) |
| `iceberg` | ICEBERG / LOTE REPETIDO, passo 1 (v2): negocios de mesma quantidade, no mesmo preco, COM O MESMO AGENTE PASSIVO, em sequencia -- existem alem do acaso? | RESEARCH_PLANO.md (ICEBERG) |
| `ignicao` | IGNICOES do WIN: grandes movimentos DETECTADOS (nao previstos) e o que acontece depois, separado pela confirmacao do WDO no sentido oposto. | research/ignicao.py (docstring); HISTORICO 2026-09-25 |
| `leadlag` | LEAD-LAG em milissegundos (default: WDO lidera o WIN, sentido oposto). | research/leadlag.py (docstring); HISTORICO 2026-09-25 |
| `m1-valida` | VALIDA o historico M1 exportado, sem testar hipotese: inventario, fator do ajuste multiplicativo por dia (pela granularidade) e, nos dias com tape, conferencia de preco, fator e horario (deslocamento -1/0/+1 min) por... | research/m1_historico.py (docstring); HISTORICO 2026-09-25 |
| `opcoes-vencimento` | OPCAO SOBRE ACAO, passo 1: a semana do vencimento e' diferente, e o volume do papel se concentra perto dos STRIKES? | RESEARCH_PLANO.md (Opcao sobre acao) |
| `rolagem` | DESCRICAO da rolagem (passo 1 de "anomalia medida"): a contraparte OBRIGADA (quem precisa rolar ou fechar no vencimento) deixa marca? | RESEARCH_PLANO.md (ROLAGEM) |
| `rolagem-par` | ROLAGEM pelo PAR CASADO: o mesmo agente vendendo num contrato e comprando no outro, em segundos. | RESEARCH_PLANO.md (RECLASSIFICACAO rolagem) |

## EA: forward, replay, execucao, diagnostico

*nao consome trial.*

| comando | o que faz | referencia |
|---|---|---|
| `barra-tempo-conferir` | Passo 1 do F5 do 123: barras M15 que o EA constroi do TAPE (trade a trade) contra as barras do GRAFICO do Profit (dump), barra a barra. | EAS_DE_PRECO.md 5.4 |
| `diario` | Relatorio do DIARIO de sinais: uma linha por sinal, inclusive os que NAO viraram ordem. | EA_ARQUITETURA.md 6 |
| `e4-comparar` | Compara o E4 (ordem real na demo) com o gemeo SIMULADO, ordem a ordem, e responde se o simulador preenche no IDEAL -- o que decide se o E4 em demo consegue medir slippage. | RUNBOOK_E4.md |
| `ea` | FORWARD-TEST do EA (dry_run por default no config): conecta com login completo, assina o simbolo, constroi barras ao vivo e LOGA cada decisao que o EA teria tomado. | EA_ARQUITETURA.md |
| `ea-123-replay` | REPLAY do EA 123 sobre um dia curado: semente, perfil de volume, gate, sinal, ciclo em dry_run e DIARIO, com barras reais e sem esperar pregao. | eas/123_m15.md |
| `ea-contas` | DIAGNOSTICO (nao operacional): conecta com login completo e lista as contas de roteamento (GetAccount) -- demo e real. | EA_ARQUITETURA.md 2 (E1) |
| `ea-ignicao-replay` | Replay do EA de ignicao sobre o tape gravado, LADO A LADO com o estudo (`research/ignicao.py`) nos mesmos dias e parametros: conferencia dos dois lados antes de ligar o forward. | eas/ignicao.md |
| `ea-micro-replay` | REPLAY do EA de microprice sobre o tiny_book GRAVADO: mesmo nucleo do vivo, relogio = ts_recv_ns, dry_run forcado. | eas/microprice.md |
| `ea-ordem-teste` | E2 da trilha de execucao (2026-09-10): primeira ordem de teste real. | EA_ARQUITETURA.md 2 (E2) |
| `ea-replay` | Forward-test SEM conexao propria: reler os trades que o `record` JA' CAPTUROU (parquet), alimentar o MESMO nucleo do EA (sinal, decisao, risco), e reportar as decisoes que teriam sido tomadas. | EA_ARQUITETURA.md |
| `ea-replay-lote` | Roda ea-replay em TODOS os dias ja' capturados (uma instancia NOVA de EAService por dia -- circuit breaker e posicao reiniciam a cada dia, igual rodaria em producao de verdade), agrega o resultado. | EA_ARQUITETURA.md; BOAS_PRATICAS_PROGRESSO.md |
| `semente-conferir` | Passo 2 do F5 do 123: semente da MME80 (parquet do grafico + ponte pelo tape) e a recursao ao longo do dia, comparada barra a barra com o mme80_ntsl do grafico no mesmo dia. | EAS_DE_PRECO.md 5.4 |

## Infraestrutura e operacao

*nao consome trial.*

| comando | o que faz | referencia |
|---|---|---|
| `alertas-testar` | Manda uma mensagem de teste ao Telegram configurado — confirma bot_token/chat_id ANTES de depender disso durante o pregao. | OPERACAO.md |
| `vigia` | Watchdog EXTERNO ao record — roda via schtasks proprio a cada poucos minutos. | OPERACAO.md |
