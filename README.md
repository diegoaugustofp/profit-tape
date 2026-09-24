# profit-tape

Pipeline quant para o WIN (mini-índice) na B3, em três camadas que se
alimentam nessa ordem:

1. **Captura** — grava tape (negócios, com o agente agressor e o passivo)
   e offer book da B3 via ProfitDLL, em Parquet particionado. Roda todo
   pregão como serviço.
2. **Pesquisa** — features de fluxo sobre barras de volume, IC
   walk-forward com veredito deflacionado, e uma disciplina de
   pré-registro que decide o critério ANTES de olhar o resultado.
3. **Execução** — EAs que rodam dentro do record (dry_run ou ordens
   reais na conta demo), com reconciliação de posição, supervisor de
   risco e inclusão/remoção a quente.

Estado em uma linha (2026-09-24): captura em produção há dois meses; a
linha de EAs de preço em M15 rodou sete fichas e fechou seis; o 123 com
gate de volume baixo está em forward com ordens reais na conta demo
desde 22/09; o classificador da Fase 2 está em forward offline. O
estado de cada estratégia vive em [`docs/eas/`](docs/eas/README.md).

## O problema que ele resolve

**Histórico de negócios você consegue pedir. Book, não.** O offer book
do ProfitDLL é realtime puro — não existe "me dá o livro de ontem". Toda
feature que dependa de fila, microprice ou queue imbalance só pode ser
calculada sobre dado que você mesmo gravou. Isso inverte a ordem
natural de trabalho: o recorder precisa estar rodando meses antes da
estratégia existir. Por isso a captura é a primeira camada e a mais
protegida.

## Instalação

```bash
git clone https://github.com/diegoaugustofp/profit-tape && cd profit-tape
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -e ".[dev]"

cp .env.example .env                # credenciais da DLL (e de roteamento, para EA)
cp config/recorder.example.yaml config/recorder.yaml
```

Requisitos: Windows, Python 3.12+, Profit aberto e logado. A
**arquitetura do Python precisa bater com a da DLL** (64 com 64) —
`doctor` verifica.

## Os três fluxos de trabalho

A CLI tem ~70 comandos (`profit-tape --help`; todos, por categoria, em
[`docs/REFERENCIA_CLI.md`](docs/REFERENCIA_CLI.md)); estes são os que
estruturam cada fluxo. Detalhe de rotina em [`docs/OPERACAO.md`](docs/OPERACAO.md).

**Gravar (todo pregão)**

```bash
profit-tape doctor                  # DLL carrega, exports batem, credencial, disco
profit-tape record                  # grava até o horário configurado (ou como serviço NSSM)
profit-tape inspect data/raw        # o que foi gravado, por dia, pelos footers
profit-tape backfill                # histórico de TRADES dos ativos (book não tem)
profit-tape vigia                   # watchdog externo, via schtasks
```

**Pesquisar (sobre dado curado; categoria decide o custo)**

```bash
profit-tape curate                  # dedup + ordena raw -> curated. SEMPRE antes de features
profit-tape features WINFUT --volume-barra 120000 --agentes ...   # barras de volume + Tier 1 (zero trial)
profit-tape triagem ...             # tria uma feature ANTES de gastar trial
profit-tape research ...            # IC walk-forward, veredito deflacionado (CONSOME trial)
profit-tape quintis ...             # tradução econômica de um "segue" (zero trial)
profit-tape eas-preco --ficha 123   # funil de uma ficha de preço (M15, dump do gráfico)
profit-tape eas-preco-teste ...     # o teste da ficha congelada — uma rodada
```

Comandos de pesquisa são de duas categorias: os que **consomem trial**
(`research`, `eas-preco-teste`: cada rodada sobe o limiar deflacionado)
e os que **não consomem** (`features`, `quintis`, `mae-analise`,
`ea-replay-lote`, descrições). A skill `profit-tape-disciplina` e
`docs/RESEARCH_PLANO.md` dizem qual é qual.

**Executar (EA dentro do record)**

```bash
profit-tape ea-replay-lote ...      # replay do EA sobre todos os dias curados (F4)
profit-tape record --ea-dir data/eas_ativos --ea-modo-ticker exclusivo \
    --login-completo --ea-ticker-ordem WINV26 --capital-em-conta 20000   # F5: dry_run ou demo
profit-tape diario ...              # o que foi DECIDIDO, sinal a sinal (o Profit só sabe o que executou)
profit-tape e4-comparar ...         # ordem real na demo x gêmeo simulado = custo de execução
```

Um EA é um YAML em `config/` (`ea_123_volume_baixo.yaml`,
`ea_venda_rota_b.yaml`); a pasta `--ea-dir` permite incluir/remover EA
com o record rodando. Ordens reais só na conta demo, por trava no
código (`RUNBOOK_E4.md`).

## Estrutura

```
src/profittape/
├── profitdll/    ÚNICO ponto de contato com a DLL: bindings ctypes, callbacks, parser de data
├── domain/       eventos, enums, schemas Arrow
├── pipeline/     fila com contabilidade de descarte + writer thread
├── storage/      sink Parquet particionado, com footer verificado por releitura
├── recorder/     orquestração do record, backfill, encerramento ordenado
├── health/       métricas
├── infra/        energia (manter a máquina acordada durante o pregão)
├── tools/        inspect, curate, compact, quarentena, duplicatas, bench, ntsl-equivalência
├── features/     barras de volume (relógio de agressão), fluxo Tier 1, z-scores, labels
├── research/     49 módulos: IC, quintis, fichas de preço, Bollinger, DeepScalper, book, contrapartes
├── ea/           sinal, decisão, risco, execução, reconciliação, despachante multi-EA, diário
└── testing/      dublês que fazem parte do pacote (DLL falsa)

ntsl/             indicadores NTSL (absorção, Bollinger, preço M15) — cada um tem parser Python gêmeo
config/           recorder.yaml, ea_*.yaml, alertas
scripts/          instalação do serviço NSSM
tools/            valida_ancoras.py (âncoras dos índices dos docs)
sql/              schema TimescaleDB opcional
tests/            ~1.070 testes; rodam no Linux, sem DLL, com a DLL falsa
docs/             ver abaixo
```

## Disciplina

O projeto tem um pipeline fixo por onde toda estratégia passa — F0
hipótese → F1 features → F2 triagem → F3 pré-registro → F4 depuração
(replay) → F5 forward demo → F6 produção — e uma escada de
infraestrutura de execução (E0–E5) ortogonal a ele. As regras que mais
custaram para aprender: validar o **mecanismo** antes de calibrar
**números**; escrever o critério de decisão **antes** de rodar;
declarar amostra e sequência inteira, sem parada opcional; um trial por
família por amostra. Estão em `docs/EA_ARQUITETURA.md` §0 e nas skills
do Project (`profit-tape-disciplina`, `profit-tape-engenharia`).

## O aviso que importa

Este projeto assume **uma versão específica da interface do ProfitDLL**.
As assinaturas em `profitdll/bindings.py` seguem a documentação pública,
mas mudam entre versões — e um argumento a mais ou a menos em
`WINFUNCTYPE` corrompe a pilha, o que se manifesta como queda do
processo ou número absurdo em campo numérico, nunca como exceção Python
limpa. A tabela de códigos de erro da DLL foi corrigida em 2026-09-23
(`docs/OPERACAO.md`): diagnósticos antigos que citem "login inválido"
devem ser relidos.

**Confira `bindings.py` e `domain/enums.py` contra o manual da sua
versão antes de contar com uma gravação de pregão.** `doctor` valida os
exports; `inspect` sinaliza código de negócio fora da tabela conhecida.

## Testes

```bash
pytest                 # suíte completa (~3 min)
ruff check src tests
mypy src               # modo strict
make docs              # regenera a referência de CLI e valida as âncoras dos índices
```

A suíte roda no Linux, sem DLL e sem mercado aberto, via
`profittape/testing` (DLL falsa que imita login assíncrono, entrega de
outra thread e o formato de data da DLL). Os testes que mais importam
na captura: `test_encerramento_drena_a_fila` (nada se perde no
shutdown) e `test_tipos_de_negocio_preservados_ate_o_disco` (leilão e
RLP sobrevivem até o Parquet).

## Documentação

Ponto de entrada: [`docs/README.md`](docs/README.md) — índice de todos
os documentos, com status e a regra de onde registrar cada coisa. Os
que mais se abrem:

- [`docs/ESTADO_E_CAMINHOS.md`](docs/ESTADO_E_CAMINHOS.md) — onde o projeto está, em uma tela
- [`docs/eas/`](docs/eas/README.md) — uma ficha por estratégia: pré-registro, resultados, veredito
- [`docs/OPERACAO.md`](docs/OPERACAO.md) — rotina diária, incidentes, checklist pós-pregão
- [`docs/RESEARCH_PLANO.md`](docs/RESEARCH_PLANO.md) — decisões de pesquisa e método (use o índice por assunto)
- [`docs/EA_ARQUITETURA.md`](docs/EA_ARQUITETURA.md) — pipeline F0–F6, escada E0–E5, arquitetura do EA
- [`docs/HISTORICO_DE_SESSOES.md`](docs/HISTORICO_DE_SESSOES.md) — o que aconteceu em cada sessão
- [`docs/GLOSSARIO.md`](docs/GLOSSARIO.md) — o vocabulário do projeto (Rota B, trial, ficha, gate, F0–F6, E0–E5…)

## Como o código chega aqui

Claude trabalha num sandbox sem acesso à máquina do operador; toda
mudança é entregue como `git bundle` incremental com tag sequencial
`entregue-vX.YY`, aplicado com `git fetch <bundle> refs/tags/entregue-vX.YY
&& git merge entregue-vX.YY && git push origin HEAD:main --tags`. Sem o
`--tags` as tags que sustentam o esquema não sobem. Detalhe na skill
`profit-tape-engenharia`.
