# Features Tier 1 — definicoes travadas

Mudanca em qualquer definicao abaixo invalida comparacao com resultados
anteriores. Se mudar, versione (v2 no nome da coluna) em vez de sobrescrever.

## Barras
Volume bars com relogio de AGRESSAO: somente AGGRESSOR_BUYER/SELLER avancam o
relogio. RLP (25% do WIN) e leilao sao atribuidos a barra corrente mas nao a
fecham — se fechassem, a barra encolheria no pico de varejo sem informacao
nova de microestrutura. O negocio que cruza o threshold pertence a barra que
completa. Barra nao atravessa dia; a parcial do fim do pregao e' descartada.
Threshold sugerido = mediana do volume de agressao diario / barras_por_dia
(mediana: um vencimento nao dita o tamanho da barra dos dias normais).

## Features (por barra; nada olha para frente)
- `imbalance` = (vol_buy − vol_sell) / vol_agr, em [−1, 1]
- `tick_imbalance` = (n_buy − n_sell) / (n_buy + n_sell)
- `absorcao` = vol_agr / max(range_em_ticks, 1) — volume alto andando pouco
  preco. Tick inferido do dado (menor variacao positiva; mediana entre dias).
- `rlp_frac` = vol_rlp / (vol_rlp + vol_agr) — proxy direto de varejo,
  possivel gracas ao codigo 13 validado.
- `agf_{id}` = (comprado − vendido pelo agente) / vol_agr, top-N agentes por
  volume de agressao. SO agressao: em RLP a ponta provedora e' o
  internalizador e misturaria fenomenos.
- OHLC/vwap usam SO agressao (print de leilao/RLP fora do high/low).

## Normalizacao
z-score rolante em BARRAS com shift(1): a barra t e' avaliada contra o passado
ESTRITO. normalize.py e' o unico modulo com janela rolante — auditoria de
lookahead tem um endereco so.

## Labels
Triple-Barrier: barreiras em close·exp(±k·sigma), sigma = desvio rolante dos
retornos de barra com shift(1); vertical em h barras. Toque ambiguo (high e
low da mesma barra futura cruzam ambas) = label 0 com `label_ambigua=True` —
escolher um lado injetaria vies indetectavel. `ret_h` permite re-rotular.

## Uso
    profit-tape features WINFUT
    # data/features/sym=WINFUT/features.parquet — uma linha por barra
