# Documentação do profit-tape — índice

> **Status:** vivo — **Revisado:** 2026-09-24 — **Assunto:** mapa de todos os
> documentos de `docs/`, com status e regra de onde registrar cada coisa.

Este é o ponto de entrada. Cada documento abaixo tem no topo um cabeçalho
padrão (`Status` / `Revisado` / `Assunto`); se o cabeçalho e esta tabela
discordarem, o cabeçalho do próprio documento vence e esta tabela deve ser
corrigida.

## Como ler um documento deste projeto

Os documentos de assunto (`RESEARCH_PLANO`, `EA_ARQUITETURA`, `OPERACAO`)
crescem por acúmulo: cada sessão empilha uma seção no fim, com data e
veredito da época. Regras de leitura:

1. **Estado atual fica no topo; histórico fica embaixo.** Quando os dois
   divergirem, o topo vence. O histórico serve para entender *por que*,
   não *o que vale hoje*.
2. **Use o índice por assunto** que existe no topo dos documentos longos.
   Não leia em ordem cronológica.
3. **Um veredito só vale no documento de origem da hipótese.** Tabelas-resumo
   em outros documentos (`EA_ARQUITETURA.md` §1, `ESTADO_E_CAMINHOS.md` §1)
   são cópias e podem estar atrasadas — ver "Divergências conhecidas" no
   fim deste índice.

## Significado dos status

| status | significa |
|---|---|
| **vivo** | reflete o estado atual; é atualizado quando o assunto muda |
| **fechado** | o trabalho que descreve terminou; conteúdo válido como registro, não muda mais |
| **superado** | substituído por outro documento (indicado); mantido só por rastreabilidade |
| **referência** | definições travadas ou material de consulta; muda raramente e com versionamento |

## Os documentos

### Estado do projeto (comece aqui)

| arquivo | assunto | status | revisado |
|---|---|---|---|
| [`ESTADO_E_CAMINHOS.md`](ESTADO_E_CAMINHOS.md) | onde o projeto está em uma tela, o que falta em ordem, taxonomia de fechamento das hipóteses | vivo | 2026-09-21 |
| [`HISTORICO_DE_SESSOES.md`](HISTORICO_DE_SESSOES.md) | uma entrada por sessão de trabalho, com as tags entregues — o eixo "quando" | vivo | 2026-09-24 |

### Método e disciplina

| arquivo | assunto | status | revisado |
|---|---|---|---|
| [`INSTRUCOES_DO_PROJETO_CLAUDE.md`](INSTRUCOES_DO_PROJETO_CLAUDE.md) | cópia versionada das instruções do Project no Claude.ai (bootstrap de sessão, skills, mínimo indispensável) | vivo | 2026-09-10 |
| [`BOAS_PRATICAS_PROGRESSO.md`](BOAS_PRATICAS_PROGRESSO.md) | regra de progresso visível `[i/N]` e `--log-file` em processos longos | vivo | 2026-08-27 |
| [`GLOSSARIO.md`](GLOSSARIO.md) | os termos com sentido próprio no projeto, uma linha cada, com ponteiro; marca as colisões (Fase, regime, IC, perfil) | vivo | 2026-09-24 |
| [`REFERENCIA_CLI.md`](REFERENCIA_CLI.md) | todos os comandos da CLI por categoria, com nota de trial e documento de referência — GERADO por `tools/gera_referencia_cli.py`, não editar à mão | vivo (gerado) | a cada `make docs` |
| skills `profit-tape-disciplina` e `profit-tape-engenharia` | pré-registro, mecanismo antes de número, tag + bundle, ordem de verificação — vivem fora do repositório, no Project | vivo | — |

### Pesquisa

| arquivo | assunto | status | revisado |
|---|---|---|---|
| [`RESEARCH_PLANO.md`](RESEARCH_PLANO.md) | decisões de sinal/estratégia, pré-registros, resultados de trial, método de geração de hipótese — o documento de origem da maioria das hipóteses | vivo | 2026-09-24 |
| [`FEATURES.md`](FEATURES.md) | definições travadas das features Tier 1 (barras de volume, imbalance, absorção, `agf_`) | referência | 2026-08-21 |
| [`PERIODOS_DECLARADOS.json`](PERIODOS_DECLARADOS.json) | períodos de trial declarados ANTES de consultar resultado, com commit da declaração | referência | 2026-09-03 |
| [`CURADORIA_DEEPSCALPER.md`](CURADORIA_DEEPSCALPER.md) | o que foi lido e descartado sobre RL intradiário/DeepScalper, com motivo — para não reler | fechado | 2026-09-08 |
| [`DESENHO_2_absorcao_com_risco.md`](DESENHO_2_absorcao_com_risco.md) | desenho 2 da absorção (com risco): abandonado antes do teste por EMD insuficiente | fechado | 2026-09-04 |
| [`DESENHO_3_absorcao_K1.md`](DESENHO_3_absorcao_K1.md) | desenho 3 da absorção (K=1), congelado; trial 2025 fechou INVERTIDO (`RESEARCH_PLANO.md`, 2026-09-04) | fechado | 2026-09-04 |
| [`NTSL_ABSORCAO.md`](NTSL_ABSORCAO.md) | indicador `absorcao_dir` no Profit — visualização exploratória, NÃO é sinal | vivo | 2026-09-02 |

### Estratégias e EAs

**O estado de cada estratégia vive na ficha dela em [`eas/`](eas/README.md)**
— uma por estratégia, vivas e mortas, com o pré-registro congelado, os
resultados por trial e o veredito. Os documentos abaixo guardam o
histórico e a discussão completa:

| arquivo | assunto | status | revisado |
|---|---|---|---|
| [`EA_ARQUITETURA.md`](EA_ARQUITETURA.md) | pipeline F0–F6, escada de infraestrutura E0–E5, decisões de arquitetura do EA; a tabela §1 aponta para as fichas | vivo | 2026-09-24 |
| [`eas/README.md`](eas/README.md) | índice das fichas: fase, veredito, trials consumidos, e as convenções comuns às fichas de preço | vivo | 2026-09-24 |
| [`eas/*.md`](eas/) | z_agf_3, deepscalper_fase2, bollinger_scalp, ifr2_m15, orb_m15, 123_m15, 123_gate_volume_alto, 123_volume_baixo, gap_abertura, vespera | vivo / fechado por ficha | 2026-09-24 |
| [`EAS_DE_PRECO.md`](EAS_DE_PRECO.md) | linha de EAs de preço em M15: histórico completo das fichas IFR2, ORB, 123, 123+gate de volume, gap, véspera | vivo (histórico) | 2026-09-24 |
| [`BOLLINGER_SCALP.md`](BOLLINGER_SCALP.md) | scalp de Bollinger 15 s: histórico completo (ficha, replay, três variantes, clustering) | fechado (suspensa) | 2026-09-24 |
| [`RUNBOOK_E4.md`](RUNBOOK_E4.md) | roteiro de um dia de E4: ordens reais na conta demo, o que conferir antes, durante e depois | vivo | 2026-09-23 |

### Operação e infraestrutura

| arquivo | assunto | status | revisado |
|---|---|---|---|
| [`OPERACAO.md`](OPERACAO.md) | rotina diária, incidentes, achados de DLL (tabela de erros corrigida 2026-09-23), checklist pós-pregão | vivo | 2026-09-23 |
| [`INTEGRIDADE_DOS_DADOS.md`](INTEGRIDADE_DOS_DADOS.md) | livro de bordo de problemas de QUALIDADE do dado por período/stream — consultar antes de concluir research sobre um período | vivo | 2026-09-24 |
| [`NSSM_SERVICO.md`](NSSM_SERVICO.md) | serviço supervisionado (NSSM) do record: desenho e validação em produção | fechado | 2026-08-27 |
| [`ARQUITETURA.md`](ARQUITETURA.md) | arquitetura do recorder (callback → fila → writer) e tabela de sintomas. Cobre só a captura; research e EA estão em `EA_ARQUITETURA.md` | vivo | 2026-08-21 |
| [`REVISAO_STORAGE.md`](REVISAO_STORAGE.md) | revisão do storage após três incidentes de corrupção; invariantes INV1–INV6 garantidos desde a v0.34 | fechado | 2026-08-22 |

### Consolidações de sessão (fotografias de um momento)

| arquivo | assunto | status | revisado |
|---|---|---|---|
| [`RESUMO_E_ROTEIRO_2026-08-27.md`](RESUMO_E_ROTEIRO_2026-08-27.md) | resumo, roteiro operacional e roadmap ao fim de 2026-08-27 | superado por `ESTADO_E_CAMINHOS.md` e `OPERACAO.md` | 2026-08-28 |

### Artefatos e referências (não são documentos)

| caminho | o que é |
|---|---|
| `artefatos/fase2/` | modelo congelado da Fase 2 do DeepScalper (`modelo_fase2.pkl`, sha256 na ficha) e `ficha_fase2.json`. Cópia única; o dado de treino não é reproduzível |
| `referencias/custos_acoes_xp.xlsx` | tabela de custos da corretora usada por `research/custo_acoes.py` |

## Onde registrar o quê

| aconteceu | registre em |
|---|---|
| pré-registro, resultado de trial, mudança de fase ou veredito de uma estratégia | a ficha em `docs/eas/` (estado) + o documento de origem (discussão longa: `EAS_DE_PRECO.md`, `BOLLINGER_SCALP.md`, `RESEARCH_PLANO.md`) |
| decisão de sinal/estratégia sem ficha ainda, método de pesquisa, triagem | `RESEARCH_PLANO.md` |
| decisão de arquitetura/infra do EA, mudança na escada E0–E5 | `EA_ARQUITETURA.md` |
| estratégia nova | ficha nova em `docs/eas/` + linha em `docs/eas/README.md` + linha na tabela §1 de `EA_ARQUITETURA.md` |
| incidente operacional, achado sobre a DLL, mudança na rotina | `OPERACAO.md` |
| dado capturado com defeito em algum período/stream | `INTEGRIDADE_DOS_DADOS.md` |
| período de trial escolhido | `PERIODOS_DECLARADOS.json` — ANTES de olhar resultado |
| mudança em definição de feature | `FEATURES.md`, versionando a coluna (`v2`), nunca sobrescrevendo |
| fim de qualquer sessão que tocou código | entrada nova no fim de `HISTORICO_DE_SESSOES.md` |
| documento novo em `docs/` | linha nova neste índice, com cabeçalho padrão no documento |
| comando novo na CLI | classificar em `tools/gera_referencia_cli.py` e rodar `make docs` (o teste `test_referencia_gerada_esta_em_dia` acusa se esquecer) |
| termo novo com sentido próprio | entrada em `GLOSSARIO.md` |

## Cabeçalho padrão

Todo documento em `docs/` começa com o H1 e, logo abaixo, uma citação de
uma a três linhas:

```
> **Status:** vivo | fechado | superado por `X.md` | referência — **Revisado:** AAAA-MM-DD — **Assunto:** uma frase.
```

`Revisado` é a data da última revisão de *conteúdo*, não de qualquer
edição. Ao marcar um documento como `superado`, diga por qual.

## Divergências e lacunas conhecidas

Resolvidas em 2026-09-24 pelas fichas: Bollinger REPROVADO vs INCONCLUSIVO
e o 7a do 123 na tabela §1 de `EA_ARQUITETURA.md` (a tabela agora aponta
para as fichas).

Abertas, registradas na ficha correspondente e aguardando o operador:

- **z_agf_3**: `config/ea_venda_rota_b.yaml` ainda carrega `alvo_pontos:
  120` e `stop_rota_b_pontos: 100`, enquanto a pesquisa fechou (29-31/08)
  que o alvo foi descartado como conceito, o stop não detecta reversão e
  drawdown não é problema. Sem registro de revisão do YAML depois. Ver
  `eas/z_agf_3.md`.
- **GAP de abertura**: o catálogo de hipóteses mortas registra
  "inconclusivo, por-ano sem padrão", mas não há tabela de resultado
  (n/p1/IC/hash) em nenhum documento. Ver `eas/gap_abertura.md`.
- (resolvida 2026-09-24) `README.md` da raiz reescrito.
