# Inventário de dados

> **Status:** gerado — **NÃO é diário**: rode sob demanda (antes de formular uma hipótese, ou quando uma coleta terminar) com `profit-tape inventario-dados`. Confira a data abaixo antes de confiar.

- **Gerado em:** 03/10/2026 19:31 (LAPTOP-QQUN6HTM, profit-tape 4.29.dev0+g893c1aa43.d20261003)
- **Raízes varridas:** `raw` = `data\raw`; `curated` = `data\curated`; `backup` = `D:\backup_raw\data\raw`
- **Linhas de inventário:** 1.857 (camada x stream x ativo x dia)
- **Nível de varredura:** `leve` — padrão: abre rodapés só de curated/trade (poucos arquivos: um por dia e ativo). Listados 27.114 arquivos em 1.857 pastas (75,1 GB); rodapés abertos: 627.

**Vocabulário.** *tape* = negócios com agente agressor e passivo (stream `trade`; `docs/GLOSSARIO.md`). *Book* = `book_offer`, `book_price`, `tiny_book`. "Só trade" = o ativo tem `trade` e nenhum stream de book. **Origem do dia:** *ao vivo* (capturado no pregão), *importado* (histórico recuperado depois, por backfill: não tem latência de chegada real nem book) ou *misto*, pelo `ts_recv_ns` no rodapé do parquet.

## Coletas em andamento (declaradas x em disco)

| Coleta | Situação | Ativos | O que o disco mostra |
|---|---|---|---|
| **Rolagem do WDO pelo PAR CASADO entre contratos** | o marco passou ha' 2 dias: ha' dado para rodar | WDOV26, WDOX26 | `WDOV26`: 7 dias (22/09/2026 a 30/09/2026); `WDOX26`: 9 dias (22/09/2026 a 02/10/2026); **dias com os dois (o par): 7** (22/09/2026 a 30/09/2026) |
| **Rolagem do WIN pelo par casado (mesma hipotese, outro instrumento)** | ainda nao iniciada | WINV26, WINZ26 | `WINV26`: 21 dias (03/09/2026 a 02/10/2026); `WINZ26`: **sem dado**; **dias com os dois (o par): 0** |
| **Opcoes de PETR4 de outubro: pinning no vencimento mensal** | em curso desde 22/09; faltam 13 dias corridos para o fim | 14 séries | 14 de 14 séries com trade; 9 dias úteis esperados desde 22/09/2026; dias por série: 9 a 9 |

Hipótese, leitura declarada antes, limite e próximo passo de cada coleta: `docs/coletas.yaml`.

## Resumo por ativo

| Ativo | Família | Tipo | Trade: período | Dias | Linhas | Ao vivo / importado / misto / desconhecido | Livro (dias): ofertas / preço / topo | Camadas | Lacunas |
|---|---|---|---|---|---|---|---|---|---|
| `BBAS3` | acao | trade + só topo (tiny_book) | 24/07/2026 a 02/10/2026 | 49 | 1.629.854 | 15 / 29 / 5 / 0 | 0 / 0 / 24 | backup, curated, raw | 2 |
| `BOVA11` | acao | trade + book de ofertas | 24/07/2026 a 02/10/2026 | 49 | 2.031.822 | 15 / 29 / 5 / 0 | 24 / 0 / 24 | backup, curated, raw | 2 |
| `ITUB4` | acao | trade + book de ofertas | 24/07/2026 a 02/10/2026 | 49 | 1.729.936 | 15 / 29 / 5 / 0 | 24 / 0 / 24 | backup, curated, raw | 2 |
| `MGLU3` | acao | trade + só topo (tiny_book) | 24/07/2026 a 02/10/2026 | 49 | 781.594 | 15 / 29 / 5 / 0 | 0 / 0 / 24 | backup, curated, raw | 2 |
| `PETR4` | acao | trade + book de ofertas | 24/07/2026 a 02/10/2026 | 49 | 2.447.415 | 15 / 29 / 5 / 0 | 24 / 0 / 24 | backup, curated, raw | 2 |
| `VALE3` | acao | trade + book de ofertas | 24/07/2026 a 02/10/2026 | 49 | 1.670.925 | 15 / 29 / 5 / 0 | 24 / 0 / 24 | backup, curated, raw | 2 |
| `WEGE3` | acao | trade + só topo (tiny_book) | 24/07/2026 a 02/10/2026 | 49 | 975.176 | 15 / 29 / 5 / 0 | 0 / 0 / 24 | backup, curated, raw | 2 |
| `WDOV26` | futuro (contrato) | trade + só topo (tiny_book) | 22/09/2026 a 30/09/2026 | 7 | 3.319.261 | 7 / 0 / 0 / 0 | 0 / 0 / 7 | backup, curated | 0 |
| `WDOX26` | futuro (contrato) | trade + só topo (tiny_book) | 22/09/2026 a 02/10/2026 | 9 | 1.999.448 | 9 / 0 / 0 / 0 | 0 / 0 / 9 | backup, curated, raw | 0 |
| `WINV26` | futuro (contrato) | só trade | 03/09/2026 a 02/10/2026 | 21 | 124.316.712 | 0 / 21 / 0 / 0 | 0 / 0 / 0 | backup, curated, raw | 1 |
| `WDOFUT` | futuro (serie continua) | trade + book de ofertas | 24/07/2026 a 02/10/2026 | 49 | 21.355.005 | 16 / 29 / 4 / 0 | 24 / 0 / 24 | backup, curated, raw | 2 |
| `WINFUT` | futuro (serie continua) | trade + book de ofertas | 24/07/2026 a 02/10/2026 | 50 | 260.013.941 | 12 / 37 / 1 / 0 | 24 / 24 / 24 | backup, curated, raw | 1 |
| `PETRI19` | opcao PETR | trade + só topo (tiny_book) | 17/09/2026 a 18/09/2026 | 2 | 573 | 2 / 0 / 0 / 0 | 0 / 0 / 2 | backup, curated | 0 |
| `PETRI442` | opcao PETR | trade + só topo (tiny_book) | 17/09/2026 a 18/09/2026 | 2 | 142 | 2 / 0 / 0 / 0 | 0 / 0 / 2 | backup, curated | 0 |
| `PETRI447` | opcao PETR | trade + só topo (tiny_book) | 17/09/2026 a 18/09/2026 | 2 | 96 | 2 / 0 / 0 / 0 | 0 / 0 / 2 | backup, curated | 0 |
| `PETRI452` | opcao PETR | trade + só topo (tiny_book) | 17/09/2026 a 18/09/2026 | 2 | 87 | 2 / 0 / 0 / 0 | 0 / 0 / 2 | backup, curated | 0 |
| `PETRI457` | opcao PETR | trade + só topo (tiny_book) | 17/09/2026 a 18/09/2026 | 2 | 91 | 2 / 0 / 0 / 0 | 0 / 0 / 2 | backup, curated | 0 |
| `PETRI522` | opcao PETR | trade + só topo (tiny_book) | 17/09/2026 a 18/09/2026 | 2 | 488 | 2 / 0 / 0 / 0 | 0 / 0 / 2 | backup, curated | 0 |
| `PETRI527` | opcao PETR | trade + só topo (tiny_book) | 17/09/2026 a 18/09/2026 | 2 | 341 | 2 / 0 / 0 / 0 | 0 / 0 / 2 | backup, curated | 0 |
| `PETRI542` | opcao PETR | trade + só topo (tiny_book) | 17/09/2026 a 18/09/2026 | 2 | 78 | 2 / 0 / 0 / 0 | 0 / 0 / 2 | backup, curated | 0 |
| `PETRJ22` | opcao PETR | trade + só topo (tiny_book) | 22/09/2026 a 02/10/2026 | 9 | 2.311 | 9 / 0 / 0 / 0 | 0 / 0 / 9 | backup, curated, raw | 0 |
| `PETRJ470` | opcao PETR | trade + só topo (tiny_book) | 22/09/2026 a 02/10/2026 | 9 | 280 | 9 / 0 / 0 / 0 | 0 / 0 / 9 | backup, curated, raw | 0 |
| `PETRJ49` | opcao PETR | trade + só topo (tiny_book) | 22/09/2026 a 02/10/2026 | 9 | 2.247 | 9 / 0 / 0 / 0 | 0 / 0 / 9 | backup, curated, raw | 0 |
| `PETRJ493` | opcao PETR | trade + só topo (tiny_book) | 22/09/2026 a 02/10/2026 | 9 | 1.587 | 9 / 0 / 0 / 0 | 0 / 0 / 9 | backup, curated, raw | 0 |
| `PETRJ494` | opcao PETR | trade + só topo (tiny_book) | 22/09/2026 a 02/10/2026 | 9 | 2.000 | 9 / 0 / 0 / 0 | 0 / 0 / 9 | backup, curated, raw | 0 |
| `PETRJ500` | opcao PETR | trade + só topo (tiny_book) | 22/09/2026 a 02/10/2026 | 9 | 7.197 | 9 / 0 / 0 / 0 | 0 / 0 / 9 | backup, curated, raw | 0 |
| `PETRJ550` | opcao PETR | trade + só topo (tiny_book) | 22/09/2026 a 02/10/2026 | 9 | 11.521 | 9 / 0 / 0 / 0 | 0 / 0 / 9 | backup, curated, raw | 0 |
| `PETRU442` | opcao PETR | trade + só topo (tiny_book) | 17/09/2026 a 18/09/2026 | 2 | 7 | 2 / 0 / 0 / 0 | 0 / 0 / 2 | backup, curated | 0 |
| `PETRU447` | opcao PETR | trade + só topo (tiny_book) | 17/09/2026 a 17/09/2026 | 1 | 6 | 0 / 0 / 1 / 0 | 0 / 0 / 2 | backup, curated | 0 |
| `PETRU452` | opcao PETR | trade + só topo (tiny_book) | 17/09/2026 a 18/09/2026 | 2 | 20 | 2 / 0 / 0 / 0 | 0 / 0 / 2 | backup, curated | 0 |
| `PETRU457` | opcao PETR | trade + só topo (tiny_book) | 17/09/2026 a 17/09/2026 | 1 | 9 | 0 / 0 / 1 / 0 | 0 / 0 / 2 | backup, curated | 0 |
| `PETRV22` | opcao PETR | trade + só topo (tiny_book) | 22/09/2026 a 02/10/2026 | 9 | 1.207 | 9 / 0 / 0 / 0 | 0 / 0 / 9 | backup, curated, raw | 0 |
| `PETRV470` | opcao PETR | trade + só topo (tiny_book) | 22/09/2026 a 02/10/2026 | 9 | 762 | 9 / 0 / 0 / 0 | 0 / 0 / 9 | backup, curated, raw | 0 |
| `PETRV480` | opcao PETR | trade + só topo (tiny_book) | 22/09/2026 a 02/10/2026 | 9 | 3.025 | 9 / 0 / 0 / 0 | 0 / 0 / 9 | backup, curated, raw | 0 |
| `PETRV49` | opcao PETR | trade + só topo (tiny_book) | 22/09/2026 a 02/10/2026 | 9 | 6.332 | 9 / 0 / 0 / 0 | 0 / 0 / 9 | backup, curated, raw | 0 |
| `PETRV494` | opcao PETR | trade + só topo (tiny_book) | 22/09/2026 a 02/10/2026 | 9 | 2.840 | 9 / 0 / 0 / 0 | 0 / 0 / 9 | backup, curated, raw | 0 |
| `PETRV500` | opcao PETR | trade + só topo (tiny_book) | 22/09/2026 a 02/10/2026 | 9 | 3.719 | 9 / 0 / 0 / 0 | 0 / 0 / 9 | backup, curated, raw | 0 |
| `PETRV550` | opcao PETR | trade + só topo (tiny_book) | 22/09/2026 a 02/10/2026 | 9 | 191 | 9 / 0 / 0 / 0 | 0 / 0 / 9 | backup, curated, raw | 0 |

*Tipo*: **book de ofertas** = `book_offer` (profundidade, por ordem); **só topo** = só `tiny_book` (melhor compra e venda), que chega para todo ticker assinado. *Linhas* e *origem* (ao vivo/importado) só existem onde o rodapé foi lido: no nível padrão (`leve`) são os dias do `curated`; dia só no raw aparece como desconhecido (`--nivel trade`, com o record parado, lê o raw). *Linhas*: do `trade`, por dia, a maior entre as camadas. *Lacunas*: dias da semana sem dado entre o primeiro e o último dia; pode incluir feriado da B3.

## Por camada e stream

| Camada | Stream | Ativos | Dias (de-até) | Arquivos | MB | Linhas |
|---|---|---|---|---|---|---|
| backup | book_offer | 6 | 24/08/2026 a 02/10/2026 | 4.243 | 32.502,1 | — (rodapé não aberto) |
| backup | book_price | 1 | 24/08/2026 a 02/10/2026 | 615 | 7.305,6 | — (rodapé não aberto) |
| backup | tiny_book | 37 | 24/08/2026 a 02/10/2026 | 11.149 | 10.766,2 | — (rodapé não aberto) |
| backup | trade | 38 | 24/07/2026 a 02/10/2026 | 9.444 | 17.866,1 | — (rodapé não aberto) |
| curated | trade | 38 | 24/07/2026 a 02/10/2026 | 627 | 3.433,2 | 422.318.246 |
| raw | book_offer | 6 | 02/10/2026 a 02/10/2026 | 215 | 1.412,9 | — (rodapé não aberto) |
| raw | book_price | 1 | 02/10/2026 a 02/10/2026 | 39 | 422,8 | — (rodapé não aberto) |
| raw | tiny_book | 24 | 02/10/2026 a 02/10/2026 | 760 | 705,7 | — (rodapé não aberto) |
| raw | trade | 2 | 03/09/2026 a 02/10/2026 | 22 | 711,0 | — (rodapé não aberto) |

## Lacunas no trade (dias da semana sem dado entre o primeiro e o último)

- `BBAS3`: 2 dia(s): 02/09, 07/09
- `BOVA11`: 2 dia(s): 02/09, 07/09
- `ITUB4`: 2 dia(s): 02/09, 07/09
- `MGLU3`: 2 dia(s): 02/09, 07/09
- `PETR4`: 2 dia(s): 02/09, 07/09
- `VALE3`: 2 dia(s): 02/09, 07/09
- `WDOFUT`: 2 dia(s): 02/09, 07/09
- `WEGE3`: 2 dia(s): 02/09, 07/09
- `WINFUT`: 1 dia(s): 07/09
- `WINV26`: 1 dia(s): 07/09

## Dumps do console do Profit (histórico de preço e indicadores)

*Dump* = arquivo de texto com as linhas que um indicador NTSL escreve no console do Profit (`PRCBARRA|`, `ABSBARRA|`, `VWAPVP|`...) e que você copia à mão: **não é CSV nem parquet**. É a amostra longa de preço (ex.: out/2015 a dez/2022), sem agente. O NTSL não escreve o ticker na linha.

| Arquivo | Tipo | Resolução (estimada) | Linhas | Dias | Primeiro dia | Último dia | Por dia (mediana) | Ativo provável | Repetidas |
|---|---|---|---|---|---|---|---|---|---|
| `data/Calculo_Stop.txt` | absorcao M5 (barras) | 5 min | 339 | 3 | 24/08/2026 | 26/08/2026 | 113 | WIN (estimado pelo preco) | 0 |
| `data/absorcao_barra.txt` | absorcao M5 (barras) | 5 min | 2.260 | 20 | 04/05/2026 | 29/05/2026 | 113 | WIN (estimado pelo preco) | 0 |
| `data/absorcao_barra_2025.txt` | absorcao M5 (barras) | 5 min | 28.176 | 250 | 02/01/2025 | 30/12/2025 | 113 | WIN (estimado pelo preco) | 0 |
| `data/absorcao_barra_jan_a_abril_2026.txt` | absorcao M5 (barras) | 5 min | 9.105 | 81 | 02/01/2026 | 30/04/2026 | 113 | WIN (estimado pelo preco) | 0 |
| `data/absorcao_barra_jan_a_abril_jun_jul_2026.txt` | absorcao M5 (barras) | 5 min | 13.399 | 119 | 02/01/2026 | 23/07/2026 | 113 | WIN (estimado pelo preco) | 0 |
| `data/amostra_depuracao.txt` | preco M15 (barras) | 15 min | 5.796 | 154 | 02/01/2026 | 13/08/2026 | 38 | WIN (estimado pelo preco) | 0 |
| `data/dump2_preco_15m.txt` | preco M15 (barras) | 15 min | 28.083 | 749 | 02/01/2023 | 30/12/2025 | 38 | WIN (estimado pelo preco) | 0 |
| `data/dump_15_22.txt` | preco M15 (barras) | 15 min | 64.869 | 1782 | 01/10/2015 | 29/12/2022 | 36 | WIN (estimado pelo preco) | 0 |
| `data/dump_2015_19.txt` | preco M15 (barras) | 15 min | 37.590 | 1036 | 01/10/2015 | 30/12/2019 | 36 | WIN (estimado pelo preco) | 0 |
| `data/dump_2020.txt` | preco M15 (barras) | 15 min | 9.079 | 249 | 02/01/2020 | 30/12/2020 | 36 | WIN (estimado pelo preco) | 0 |
| `data/dump_2021_22.txt` | preco M15 (barras) | 15 min | 18.200 | 497 | 04/01/2021 | 29/12/2022 | 36 | WIN (estimado pelo preco) | 0 |
| `data/dump_20260901_20260904_9h_14h.txt` | bollinger scalp (barras) | 15 s | 3.160 | 4 | 01/09/2026 | 04/09/2026 | 1.191 | WIN (estimado pelo preco) | 0 |
| `data/dump_20260901_20260923_6m.txt` | bollinger scalp (barras) | 6 min | 1.518 | 16 | 01/09/2026 | 23/09/2026 | 95 | WIN (estimado pelo preco) | 0 |
| `data/dump_20260901_dia_completo.txt` | bollinger scalp (barras) | 15 s | 2.249 | 1 | 01/09/2026 | 01/09/2026 | 2.249 | WIN (estimado pelo preco) | 0 |
| `data/dump_dep.txt` | preco M15 (barras) | 15 min | 758 | 20 | 14/08/2026 | 11/09/2026 | 38 | WIN (estimado pelo preco) | 0 |
| `data/dump_preco_15m.txt` | preco M15 (barras) | 15 min | 6.580 | 174 | 02/01/2026 | 11/09/2026 | 38 | WIN (estimado pelo preco) | 0 |
| `data/vwapvp_ntsl_1.txt` | VWAP + VP M5 (barras) | 5 min | 113 | 1 | 28/09/2026 | 28/09/2026 | 113 | nao consta | n/d |
| `data/wdo_2015_22.txt` | preco M15 (barras) | 15 min | 62.409 | 1715 | 01/10/2015 | 29/12/2022 | 36 | WDO (pelo nome do arquivo) | 0 |
| `data/wdo_2023_25.txt` | preco M15 (barras) | 15 min | 28.085 | 749 | 02/01/2023 | 30/12/2025 | 38 | WDO (pelo nome do arquivo) | 0 |
| `data/wdo_2026.txt` | preco M15 (barras) | 15 min | 6.620 | 175 | 02/01/2026 | 14/09/2026 | 38 | WDO (pelo nome do arquivo) | 0 |
| `data/wdo_dep.txt` | preco M15 (barras) | 15 min | 798 | 21 | 14/08/2026 | 14/09/2026 | 38 | WDO (pelo nome do arquivo) | 0 |
| `data/wdo_rep.txt` | preco M15 (barras) | 15 min | 5.822 | 154 | 02/01/2026 | 13/08/2026 | 38 | WDO (pelo nome do arquivo) | 0 |
| `data/dumps_15s/dump20260901.txt` | bollinger scalp (barras) | 15 s | 2.249 | 1 | 01/09/2026 | 01/09/2026 | 2.249 | WIN (estimado pelo preco) | 0 |
| `data/dumps_15s/dump20260902.txt` | bollinger scalp (barras) | 15 s | 2.247 | 1 | 02/09/2026 | 02/09/2026 | 2.247 | WIN (estimado pelo preco) | 0 |
| `data/dumps_15s/dump20260903.txt` | bollinger scalp (barras) | 15 s | 2.249 | 1 | 03/09/2026 | 03/09/2026 | 2.249 | WIN (estimado pelo preco) | 0 |
| `data/dumps_15s/dump20260904.txt` | bollinger scalp (barras) | 15 s | 2.249 | 1 | 04/09/2026 | 04/09/2026 | 2.249 | WIN (estimado pelo preco) | 0 |
| `data/dumps_15s/dump20260908.txt` | bollinger scalp (barras) | 15 s | 2.248 | 1 | 08/09/2026 | 08/09/2026 | 2.248 | WIN (estimado pelo preco) | 0 |

### Dias únicos por tipo e ativo (sem contar a sobreposição)

| Tipo | Resolução | Ativo provável | Arquivos | Dias únicos | Período | Soma dos dias dos arquivos | Contados em duplicidade | Buracos (5+ dias úteis seguidos sem dado) |
|---|---|---|---|---|---|---|---|---|
| absorcao M5 (barras) | 5 min | WIN | 5 | **392** | 02/01/2025 a 26/08/2026 | 473 | **81** | 24/07/2026 a 21/08/2026 (21 dias) |
| bollinger scalp (barras) | 15 s | WIN | 7 | **5** | 01/09/2026 a 08/09/2026 | 10 | **5** | — |
| bollinger scalp (barras) | 6 min | WIN | 1 | **16** | 01/09/2026 a 23/09/2026 | 16 | 0 | — |
| preco M15 (barras) | 15 min | WDO | 5 | **2.639** | 01/10/2015 a 14/09/2026 | 2.814 | **175** | 31/05/2017 a 30/06/2017 (23 dias); 31/08/2017 a 28/09/2017 (21 dias); 31/03/2017 a 27/04/2017 (20 dias); 31/01/2017 a 23/02/2017 (18 dias) |
| preco M15 (barras) | 15 min | WIN | 8 | **2.705** | 01/10/2015 a 11/09/2026 | 4.661 | **1956** | 14/12/2016 a 30/12/2016 (13 dias) |
| VWAP + VP M5 (barras) | 5 min | não identificado | 1 | **1** | 28/09/2026 a 28/09/2026 | 1 | 0 | — |

### Sobreposição entre arquivos (mesmo tipo, ativo e resolução)

Somar as linhas destes arquivos conta de novo os dias em comum. **Mesmos dias não provam mesmas barras**: confira as barras por dia (resolução ou janela de horário podem diferir).

| Tipo | Ativo | Arquivo A (dias; barras/dia) | Arquivo B (dias; barras/dia) | Dias em comum | Relação |
|---|---|---|---|---|---|
| preco M15 (barras) · 15 min | WIN | `data/dump_15_22.txt` (1.782; 36) | `data/dump_2015_19.txt` (1.036; 36) | **1.036** (01/10/2015 a 30/12/2019) | B esta' dentro de A |
| preco M15 (barras) · 15 min | WIN | `data/dump_15_22.txt` (1.782; 36) | `data/dump_2021_22.txt` (497; 36) | **497** (04/01/2021 a 29/12/2022) | B esta' dentro de A |
| preco M15 (barras) · 15 min | WIN | `data/dump_15_22.txt` (1.782; 36) | `data/dump_2020.txt` (249; 36) | **249** (02/01/2020 a 30/12/2020) | B esta' dentro de A |
| preco M15 (barras) · 15 min | WIN | `data/amostra_depuracao.txt` (154; 38) | `data/dump_preco_15m.txt` (174; 38) | **154** (02/01/2026 a 13/08/2026) | A esta' dentro de B |
| preco M15 (barras) · 15 min | WDO | `data/wdo_2026.txt` (175; 38) | `data/wdo_rep.txt` (154; 38) | **154** (02/01/2026 a 13/08/2026) | B esta' dentro de A |
| absorcao M5 (barras) · 5 min | WIN | `data/absorcao_barra_jan_a_abril_2026.txt` (81; 113) | `data/absorcao_barra_jan_a_abril_jun_jul_2026.txt` (119; 113) | **81** (02/01/2026 a 30/04/2026) | A esta' dentro de B |
| preco M15 (barras) · 15 min | WDO | `data/wdo_2026.txt` (175; 38) | `data/wdo_dep.txt` (21; 38) | **21** (14/08/2026 a 14/09/2026) | B esta' dentro de A |
| preco M15 (barras) · 15 min | WIN | `data/dump_dep.txt` (20; 38) | `data/dump_preco_15m.txt` (174; 38) | **20** (14/08/2026 a 11/09/2026) | A esta' dentro de B |
| bollinger scalp (barras) · 15 s | WIN | `data/dump_20260901_20260904_9h_14h.txt` (4; 1.191) | `data/dump_20260901_dia_completo.txt` (1; 2.249) | **1** (01/09/2026 a 01/09/2026) | B esta' dentro de A |
| bollinger scalp (barras) · 15 s | WIN | `data/dump_20260901_20260904_9h_14h.txt` (4; 1.191) | `data/dumps_15s/dump20260901.txt` (1; 2.249) | **1** (01/09/2026 a 01/09/2026) | B esta' dentro de A |
| bollinger scalp (barras) · 15 s | WIN | `data/dump_20260901_20260904_9h_14h.txt` (4; 1.191) | `data/dumps_15s/dump20260902.txt` (1; 2.247) | **1** (02/09/2026 a 02/09/2026) | B esta' dentro de A |
| bollinger scalp (barras) · 15 s | WIN | `data/dump_20260901_20260904_9h_14h.txt` (4; 1.191) | `data/dumps_15s/dump20260903.txt` (1; 2.249) | **1** (03/09/2026 a 03/09/2026) | B esta' dentro de A |
| bollinger scalp (barras) · 15 s | WIN | `data/dump_20260901_20260904_9h_14h.txt` (4; 1.191) | `data/dumps_15s/dump20260904.txt` (1; 2.249) | **1** (04/09/2026 a 04/09/2026) | B esta' dentro de A |
| bollinger scalp (barras) · 15 s | WIN | `data/dump_20260901_dia_completo.txt` (1; 2.249) | `data/dumps_15s/dump20260901.txt` (1; 2.249) | **1** (01/09/2026 a 01/09/2026) | mesmos dias |

*Repetidas*: dentro do mesmo arquivo; a sobreposição ENTRE arquivos está nos blocos acima. Barras com a mesma identidade do parser da ficha (dia + `current_bar` em PRCBARRA e BBSBARRA; dia + hora em ABSBARRA) no mesmo arquivo: dumps sobrepostos inflam o n sem informação nova. `n/d` = o tipo não tem identidade de barra. *Resolução* é inferida do próprio arquivo (distância entre horas / barras por hora): arquivos de resoluções diferentes não são duplicatas, mesmo nos mesmos dias. *Ativo provável* é estimativa pelo nome do arquivo ou pela ordem de grandeza do preço (PRCBARRA, BBSBARRA e ABSBARRA); confirme.

