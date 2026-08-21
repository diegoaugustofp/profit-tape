# Arquitetura

```
   ProfitDLL (thread da DLL)                Thread do writer
  ┌──────────────────────────┐            ┌───────────────────────┐
  │ callback                 │            │ drain(lote)           │
  │   monta NamedTuple       │  EventBus  │ agrupa por particao   │
  │   publish() ────────────────────────▶ │ transpoe p/ colunas   │
  │   return                 │  (fila     │ escreve RecordBatch   │
  │                          │  limitada) │ rotaciona arquivos    │
  └──────────────────────────┘            └───────────┬───────────┘
        ▲                                             ▼
        │                                   data/raw/{stream}/
   feed PARADO enquanto                       dt=.../sym=.../
   o callback roda                              part-NNNN.parquet
```

## As tres decisoes que sustentam tudo

**1. O callback nao faz nada alem de empilhar.**
Enquanto codigo Python roda dentro do callback, a DLL nao entrega o proximo
evento. I/O ali dentro enfileira do lado da DLL e, quando o buffer dela estoura,
o dado se perde antes de chegar a voce — sem aviso, sem excecao.

**2. Perda conhecida vale mais que perda silenciosa.**
Fila cheia descarta e CONTABILIZA. Um buraco nao registrado invalida toda
analise feita em cima daquela particao, e voce descobre meses depois, quando
um backtest der um numero bom demais.

**3. Grava-se o delta cru, nao o derivado.**
Nada de normalizar tipo de negocio, agregar book ou calcular feature na
captura. Leilao e RLP precisam chegar ao disco justamente para poderem ser
excluidos DEPOIS, de forma explicita. Dado descartado na captura nao volta.

## Onde procurar quando algo der errado

| Sintoma | Arquivo | O que verificar |
|---|---|---|
| Processo cai sem excecao | `profitdll/bindings.py` | Assinatura de callback com argumento a mais/menos corrompe a pilha |
| Ticker nunca entrega evento | `profitdll/client.py` | Subscricao antes do market data conectar falha em silencio |
| `taxa_descarte` > 0 | `pipeline/bus.py` | Fila pequena, disco lento, ou book demais subscrito |
| Timestamp zerado no Parquet | `profitdll/timeparse.py` | Formato de data da sua versao difere |
| Arquivo Parquet ilegivel | `storage/parquet_sink.py` | Footer nao escrito — processo morreu sem `close()` |
| `CODIGO DESCONHECIDO` no inspect | `domain/enums.py` | Tabela de `TradeType` desatualizada para a sua DLL |

## Custo em disco (medido)

~80 bytes por evento com zstd-3, contando trades e offer book misturados.
Projecao: **~4 GB por 50 milhoes de eventos**. Um WINFUT com offer book
sozinho gera na casa de milhoes de eventos por pregao — dimensione o disco
por mes, nao por dia.

## Vazao (medida)

- Caminho de escrita isolado: **~125 mil linhas/s** (transposicao + Arrow + Parquet).
- Pipeline completo a 15 mil ev/s sustentados: **fila pico de ~1.000 de 500.000**.

O gargalo pratico nao e' disco nem Parquet — e' disputa de GIL entre as threads
de callback e o writer. Reforca a regra 1.
