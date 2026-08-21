# Operacao

## Antes do primeiro pregao

```bash
profit-tape doctor            # DLL, exports, credencial, disco
profit-tape record --dry-run  # valida o YAML
profit-tape bench             # folga do pipeline NESTA maquina
```

`doctor` e' o unico que detecta incompatibilidade de versao da DLL antes de
voce perder um pregao inteiro.

## Rodando

```bash
profit-tape record -c config/recorder.yaml --log-file logs/recorder.jsonl
```

Encerra sozinho no horario de `runtime.encerrar_em`, ou com Ctrl+C. Nos dois
casos o encerramento e' ordenado: para de receber, drena a fila, fecha os
arquivos. Matar o processo com `kill -9` pula o fechamento e deixa o ultimo
arquivo de cada particao sem footer.

## Agendamento no Windows

Agendador de Tarefas, gatilho diario as 09:45 (antes do leilao de abertura):

```
Programa : C:\caminho\.venv\Scripts\profit-tape.exe
Argumentos: record -c C:\caminho\config\recorder.yaml --log-file C:\caminho\logs\rec.jsonl
Iniciar em: C:\caminho
```

O Profit precisa estar aberto e logado.

## Depois do pregao — obrigatorio, nao opcional

```bash
profit-tape inspect data/raw --stream trade
```

Confira, nesta ordem:

1. **`taxa_descarte` no log de resumo.** Qualquer valor acima de zero significa
   buraco. Anote em algum lugar que sobreviva — a particao parece intacta.
2. **`TIMESTAMP INVALIDO`.** Se aparecer, o formato de data da sua DLL difere
   e `timeparse.py` precisa de ajuste. O dado do dia esta comprometido.
3. **`CODIGO DESCONHECIDO`** em tipo de negocio. Sua versao usa codigos fora da
   tabela em `domain/enums.py` — corrija antes de calcular qualquer coisa.
4. **`trade_id` repetido.** Normal em reconnect. Deduplique por
   `(symbol, trade_id)` mantendo a ultima versao.
5. **Latencia p50.** Salto subito sugere problema de rede ou maquina saturada.

## Lendo o dado

```python
import duckdb

con = duckdb.connect()
df = con.execute("""
    SELECT ts_ns, price, quantidade, trade_type, agente_comprador, agente_vendedor
    FROM read_parquet('data/raw/trade/**/*.parquet', hive_partitioning=true)
    WHERE dt = '2026-08-21' AND sym = 'WINFUT'
      AND trade_type IN (2, 3)      -- so agressao continua
    ORDER BY ts_ns
""").df()
```

O filtro por `trade_type` nao e' detalhe. Leilao, RLP e balcao no meio do
calculo de OFI produzem um numero que parece razoavel e nao mede nada.

## Comportamento sob queda de conexao (aprendido em producao)

Se a internet cair durante uma chamada da DLL, a chamada pode BLOQUEAR por
muitos minutos (observado: 21) e nao ha como interromper com seguranca — nem
Ctrl+C acorda a thread presa dentro da DLL ate a chamada retornar. O log
`backfill.solicitando` imediatamente antes de cada chamada diz onde parou;
`backfill.estado_conexao` registra a queda quando o callback de estado dispara.
Se precisar abortar de verdade, feche o processo pelo gerenciador de tarefas —
o raw do dia continua legivel porque os arquivos rotacionam por ociosidade.

A recusa NL base+46 apareceu em dois contextos: logo apos conectar (historico
ainda nao pronto) e apos queda de conexao. O backfill trata os dois com
`--settle` (respiro pos-conexao, padrao 5s) e `--tentativas`/`--intervalo`
(retry por ticker). Se todos os tickers recusarem apos os retries em condicao
de rede boa e horario comercial, ai sim procure o 46o codigo NL_ no manual.
