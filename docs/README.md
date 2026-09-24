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

Cada estratégia terá uma ficha própria em `docs/eas/` (em construção, revisão
de documentação de 2026-09-24). Até lá, o documento de origem de cada uma é:

| arquivo | assunto | status | revisado |
|---|---|---|---|
| [`EA_ARQUITETURA.md`](EA_ARQUITETURA.md) | pipeline F0–F6, escada de infraestrutura E0–E5, tabela "onde cada EA está", decisões de arquitetura do EA | vivo | 2026-09-23 |
| [`EAS_DE_PRECO.md`](EAS_DE_PRECO.md) | linha de EAs de preço em M15: fichas IFR2, ORB, 123, 123+gate de volume, gap, véspera | vivo | 2026-09-16 |
| [`BOLLINGER_SCALP.md`](BOLLINGER_SCALP.md) | scalp de Bollinger 15 s: ficha, replay, três variantes; veredito INCONCLUSIVO após revogação do CONTRA (§12) | fechado (suspensa) | 2026-09-24 |
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
| decisão de sinal/estratégia, pré-registro, resultado de trial | `RESEARCH_PLANO.md` (ou, para uma estratégia com ficha própria, na ficha em `docs/eas/`) |
| decisão de arquitetura/infra do EA, mudança na escada E0–E5, mudança de fase F0–F6 | `EA_ARQUITETURA.md` — e a linha da tabela §1 |
| incidente operacional, achado sobre a DLL, mudança na rotina | `OPERACAO.md` |
| dado capturado com defeito em algum período/stream | `INTEGRIDADE_DOS_DADOS.md` |
| período de trial escolhido | `PERIODOS_DECLARADOS.json` — ANTES de olhar resultado |
| mudança em definição de feature | `FEATURES.md`, versionando a coluna (`v2`), nunca sobrescrevendo |
| fim de qualquer sessão que tocou código | entrada nova no fim de `HISTORICO_DE_SESSOES.md` |
| documento novo em `docs/` | linha nova neste índice, com cabeçalho padrão no documento |

## Cabeçalho padrão

Todo documento em `docs/` começa com o H1 e, logo abaixo, uma citação de
uma a três linhas:

```
> **Status:** vivo | fechado | superado por `X.md` | referência — **Revisado:** AAAA-MM-DD — **Assunto:** uma frase.
```

`Revisado` é a data da última revisão de *conteúdo*, não de qualquer
edição. Ao marcar um documento como `superado`, diga por qual.

## Divergências conhecidas (a corrigir na etapa de fichas)

- `EA_ARQUITETURA.md` §1 lista o scalp de Bollinger (retorno e rompimento)
  como **F4 — REPROVADO**; `BOLLINGER_SCALP.md` §12 (2026-09-23) revogou o
  CONTRA para **INCONCLUSIVO** (clustering de 2,56 sinais por janela alarga
  os IC). Vale o documento de origem.
- `EA_ARQUITETURA.md` §1 (tabela "revisado 2026-09-13") ainda lista o 7a como
  próximo passo do 123; a tabela da escada no mesmo documento (§2) e
  `ESTADO_E_CAMINHOS.md` §1 registram o 7a FECHADO em 2026-09-21. Vale o
  registro mais recente.
- `README.md` da raiz descreve só o recorder (2026-08-21). Reescrita
  prevista na mesma revisão de documentação.
