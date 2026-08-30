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
3. Tire o conteudo do console para um `.txt` (lixo em volta e' tolerado).
4. Compare:

```powershell
profit-tape ntsl-equivalencia `
  --log logs\console_20260827.txt `
  --features data\features_tempo\sym=WINFUT\tf=5m\features.parquet `
  --segundos 300
```

## Onde o log e' gravado: em lugar nenhum do disco

**O NTSL nao tem escrita em arquivo.** Nao existe `WriteFile`,
`SaveToFile` nem equivalente no manual; a unica funcionalidade chamada
"exportar" e' a do CODIGO-FONTE da estrategia, nao de dados.

`ConsoleLog` escreve numa JANELA da interface — o terminal de console de
depuracao quando o codigo roda como indicador, ou a janela de Detalhes
da Automacao quando roda como automacao. De la o conteudo precisa ser
tirado a mao.

NAO VERIFICADO: como exatamente se extrai conteudo dessa janela
(copiar-e-colar? opcao de salvar?). O manual nao descreve, e nao tenho
como testar. Se a extracao pela janela de indicador for ruim, rodar o
mesmo codigo como AUTOMACAO joga os logs em Detalhes da Automacao, que
talvez extraia melhor — a verificar na pratica.

### O volume e' pequeno, e isso resolve o problema

    5m : 113 linhas por pregao
    1m : 565 linhas por pregao

Copiar a mao e' viavel. E `LogSomenteSinal=1` reduz a poucas linhas.

### A comparacao nao precisa do pregao inteiro

O que a equivalencia responde e' se as duas implementacoes calculam o
MESMO numero. Uma divergencia sistematica de OHLC por RLP aparece em 20
barras tao bem quanto em 113. Para o primeiro teste, um punhado de
linhas basta — e coincide com o teste de janela curta que ja deve ser
feito primeiro de qualquer forma.

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


## Verificado em 2026-08-30, com um dump real de 2.001 barras

O primeiro `ConsoleLog` (19 pregões de jul/ago 2025) resolveu tudo o que
estava em aberto sobre o indicador em si.

### O que passou

- **Zero duplicatas** em 2.001 linhas, 113 barras por pregão. O guard
  `CurrentBar <= BarCount - 3` funcionou: uma linha por barra, sem spam.
  Era o risco que não dava para verificar de fora.
- **Aritmética interna** com erro máximo de 1e-8 (arredondamento de
  impressão): `imbalance`, `desloc_norm` e `absorcao_dir` conferidos.
- **O z do NTSL reproduz `normalize.py` com erro máximo de 2,4e-8** em
  1.950 células. Janela 50, `shift(1)` anti-lookahead e divisor `(n-1)`
  idênticos nas duas implementações. Era a dúvida real do desenho.
- Desvio do z: 1,023 (NTSL) contra 1,027 (Python). `|z| >= 1,75`: 5,64%
  contra 6,30%. Séries diferentes, mesma distribuição.

### CORRIGIDO: o histórico de agressão é profundo

Estava registrado aqui como "não verificado se `AgressionVolBuy/Sell`
populam barras antigas". O dump responde: valores válidos em
**16/07/2025**, mais de treze meses antes. Não é só tempo real.

### `WINFUT` no gráfico é a série contínua AJUSTADA

Os preços vêm com oito casas (`157.722,86300000`) e fora da grade de 5
pontos. Medido a partir dos próprios dados: o passo mínimo entre preços
distintos é **5,789 = 5 x 1,1578**, e todos os preços caem nessa grade
com desvio de 1e-4. Fator de rolagem **k = 1,1578** no trecho de
julho/2025.

Isso NÃO afeta a fórmula: `desloc_norm` é uma razão (o k cancela no
numerador e no denominador, e um ajuste aditivo também cancela) e
`imbalance` é volume. E não é argumento apenas — é o que a distribuição
já mostrou acima.

O que muda: **nível de preço não é comparável** entre gráfico e tape. O
OHLC entra na tabela do comparador como `diagnostico`, nunca como
critério de equivalência. E k salta a cada rolagem.

CrossOrder não interfere no cálculo: pelo manual ele faz a estratégia
rodar sobre a série histórica e rotear ordens para outro ativo de
negociação (afeta `AskSize`, `BidSize`, `Lote`).

### O que falta: sobreposição de datas

O dump cobre 16/07 a 11/08 de **2025**; o parquet cobre 24/07 a 27/08 de
**2026**. Zero sobreposição — a equivalência contra o tape não pôde ser
feita. O operador confirmou que consegue estender o período do gráfico.

### Diagnóstico novo no log: a armadilha do `SoAgressores`

O log passa a trazer `QuantityVol(False, False)` e
`QuantityVol(False, True)` lado a lado.

**Se as duas colunas forem idênticas em todas as barras**, ou o WIN não
tem RLP nem leilão (implausível) ou o opcional "Plugin Tape Reading" não
está assinado e o parâmetro está sendo ignorado em silêncio, exatamente
como o manual descreve. É o único jeito de detectar essa falha de fora.

Se forem diferentes, a razão entre elas dá a fração de RLP+leilão da
barra, comparável direto com `rlp_frac` do parquet.
