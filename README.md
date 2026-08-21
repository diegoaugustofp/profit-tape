# profit-tape

Gravador de tape e offer book da B3 via ProfitDLL, com saida em Parquet
particionado. Construido para alimentar pesquisa de fluxo de ordens: OFI,
queue imbalance, absorcao, fluxo por corretora.

## O problema que ele resolve

**Historico de negocios voce consegue pedir. Book, nao.** O offer book do
ProfitDLL e' realtime puro — nao existe "me da o livro de ontem". Toda feature
que dependa de fila, microprice ou queue imbalance so pode ser calculada sobre
dado que voce mesmo gravou. Isso inverte a ordem natural de trabalho: o
recorder precisa estar rodando meses antes da estrategia existir.

## Instalacao

```bash
git clone <repo> && cd profit-tape
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -e ".[dev]"

cp .env.example .env                # preencha as credenciais
cp config/recorder.example.yaml config/recorder.yaml
```

Requisitos: Windows, Python 3.11+, Profit aberto e logado. A **arquitetura do
Python precisa bater com a da DLL** (64 com 64) — `doctor` verifica.

## Uso

```bash
profit-tape doctor                  # diagnostico completo antes de confiar
profit-tape record --dry-run        # valida config
profit-tape bench                   # folga do pipeline nesta maquina
profit-tape record                  # grava
profit-tape inspect data/raw        # audita o que foi gravado
```

## Estrutura

```
src/profittape/
├── profitdll/          # UNICO ponto de contato com a DLL
│   ├── bindings.py     #   <-- assinaturas ctypes; corrija AQUI se a versao mudar
│   ├── client.py       #   callbacks (caminho quente)
│   ├── timeparse.py    #   parser de data ~10x mais rapido que strptime
│   └── types.py        #   structs
├── domain/             # eventos, enums, schemas Arrow
├── pipeline/           # fila com contabilidade de descarte + writer thread
├── storage/            # sink Parquet particionado
├── recorder/           # orquestracao e encerramento ordenado
├── health/             # metricas
└── tools/              # inspect, bench
```

## O aviso que importa

Este projeto assume **uma versao especifica da interface do ProfitDLL**. As
assinaturas em `bindings.py` seguem a documentacao publica, mas mudam entre
versoes — e um argumento a mais ou a menos em `WINFUNCTYPE` corrompe a pilha, o
que se manifesta como queda do processo ou numero absurdo em campo numerico,
nunca como excecao Python limpa.

**Confira `bindings.py` e `domain/enums.py` contra o manual da sua versao antes
de contar com uma gravacao de pregao.** `doctor` valida os exports; `inspect`
sinaliza codigo de negocio fora da tabela conhecida.

## Testes

A suite roda no Linux, sem DLL e sem mercado aberto, via `tests/fakes/fake_dll.py`.
Ela imita login assincrono, entrega de outra thread e o formato de data da DLL.

```bash
pytest
```

Os testes que mais importam: `test_encerramento_drena_a_fila` (nada se perde no
shutdown) e `test_tipos_de_negocio_preservados_ate_o_disco` (leilao e RLP
sobrevivem ate o Parquet, para poderem ser excluidos depois).

## Documentacao

- [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md) — decisoes de projeto e tabela de sintomas
- [`docs/OPERACAO.md`](docs/OPERACAO.md) — rotina diaria e checklist pos-pregao
- [`sql/001_raw_market_data.sql`](sql/001_raw_market_data.sql) — schema TimescaleDB opcional
