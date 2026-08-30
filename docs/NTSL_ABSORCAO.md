# Indicador NTSL `absorcao_dir` — visualizacao exploratoria

Fonte: `ntsl/absorcao_dir.ntsl`. Comparador: `profit-tape ntsl-equivalencia`.

## O que este indicador NAO e'

Nao e' sinal. A hipotese que ele desenha foi REPROVADA no IC em
2026-08-30 — `CONTRA` nas 12 celulas, ver `RESEARCH_PLANO.md`. O
`Limiar` de 2,0 foi escolhido para ser VISIVEL, nao por ter edge. Uma
barra vermelha significa "esta barra esta na cauda da distribuicao
recente desta conta", e nada alem disso.

O uso legitimo e' GERAR HIPOTESE: olhar as barras que a leitura visual
identifica como absorcao e ver o que a formula deixou de fora. O que
NAO vale e' ajustar `Limiar` na tela ate "ficar bom" — isso e' overfit
visual, e nao deixa de ser porque foi feito com o olho em vez de com um
otimizador. Se algo aparecer, vira pre-registro novo, testado em amostra
NOVA.

## Parametros

| parametro | default | nota |
|---|---|---|
| `Limiar` | 2,0 | **nao validado** |
| `Janela` | 50 | 5m: 50 / **1m: 250** (os dois = 250 min) |
| `MostrarLadoOposto` | 1 | pinta o lado negativo de `clAqua` |
| `LogAtivo` | 1 | emite `ConsoleLog` |
| `LogSomenteSinal` | 0 | 1 = loga so' barras coloridas |

**Trocar o timeframe exige trocar `Janela` junto.** Deixar 50 num
grafico de 1m normaliza contra 50 minutos em vez de 250, e ai o que
aparece na tela nao e' o que foi medido em Python.

## Por que o log so' sai com dois candles de atraso

O manual e' explicito: *"o mesmo candle pode ser processado diversas
vezes... cada trade pode gerar uma notificacao de reprocessamento"*, e a
cada tick sao reavaliados *"o ultimo e o penultimo candle"*.

O WINFUT tem ~42.000 negocios por barra de 5m. Logar a barra em formacao
produziria dezenas de milhares de linhas por barra. Por isso o guard e'
`CurrentBar <= BarCount - 3`: a barra so' e' logada quando ja saiu da
janela de reavaliacao. Em replay, cada barra sai uma vez, com dois
candles de atraso. Na carga do historico, o grafico inteiro sai de uma
vez.

O manual tambem avisa que candles PASSADOS podem ser reprocessados. Se
isso acontecer havera linhas repetidas — o comparador deduplica por
data+hora e REPORTA quantas viu, em vez de esconder.

## PRIMEIRO TESTE: janela curta, nao um pregao inteiro

Antes de replayar um dia completo, rode com poucas barras e confira que
sai **exatamente uma linha por barra**. Se sair mais, o motor esta
reavaliando mais do que o manual descreve e o guard precisa mudar antes
de qualquer coisa. Descobrir isso com o console travado no meio de um
replay de 8 horas e' pior.

## Equivalencia: duas divergencias sao ESPERADAS

Previstas por escrito antes de qualquer medicao:

1. **OHLC.** O do grafico inclui TODOS os negocios; o do profit-tape usa
   so' agressao (RLP e leilao fora). Um RLP que imprima nova maxima muda
   `desloc_norm` aqui e nao muda la.
2. **Volume de agressao.** Nao esta documentado se `AgressionVolBuy` e
   `AgressionVolSell` excluem RLP.

Por isso o comparador nao devolve "bate / nao bate": devolve a
distribuicao da diferenca campo a campo.

    divergencia SO em desloc_norm  -> causa (1), OHLC
    divergencia tambem em imbalance -> causa (2), volume de agressao
    NENHUMA barra casa             -> fuso; tente --hora-bolsa

## Rotina

1. Abra o grafico no timeframe desejado, com `Janela` coerente.
2. Rode o replay do dia.
3. Exporte o console inteiro para um `.txt` (lixo em volta e' tolerado).
4. Compare:

```powershell
profit-tape ntsl-equivalencia `
  --log logs\console_20260827.txt `
  --features data\features_tempo\sym=WINFUT\tf=5m\features.parquet `
  --segundos 300
```

## Falha silenciosa a vigiar

Sem licenca Pro/Ultra/Scalper, `AgressionVolBuy`/`Sell` nao calculam e
NAO ha erro — os valores vem zerados. Com `vol_agr = 0` o `imbalance`
cai na guarda e vira 0, e `absorcao_dir` fica sendo `-desloc_norm`. O
indicador continua plotando e pintando barras, so' que medindo outra
coisa.

O log e' o que revela: `agr_compra` e `agr_venda` zerados em todas as
barras. E' a mesma classe de falha do `SoAgressores`, que o manual diz
ser silenciosamente tratado como `False` sem o opcional Plugin Tape
Reading — e da mesma familia do bug de pydantic que motivou o
`extra="forbid"` nas configs do EA.
