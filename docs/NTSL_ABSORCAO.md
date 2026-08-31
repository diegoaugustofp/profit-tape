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


## O buffer do console enche de trás para frente (2026-08-30)

Medido: o console retém cerca de **2.000 linhas**. A carga de histórico
processa as barras em ordem **cronológica**, então o buffer enche a
partir da barra **mais antiga** e para.

Consequência contraintuitiva: **quanto mais histórico o gráfico tem,
mais cedo o log termina.** Três tentativas seguidas produziram dumps
cada vez mais antigos — 16/07 a 11/08 de 2025, depois 07/03 a 02/04 de
2025, depois 10/03/2025 a 30/06/2026. O gráfico tinha agosto de 2026 o
tempo todo; as vagas é que acabavam antes.

Reduzir o log por barra não resolve — o buffer conta linhas, e mesmo com
`LogSomenteSinal=1` (6,2 barras/pregão) as 2.001 vagas cobriram 325
pregões e travaram em 30/06/2026.

Limitar o período pelos parâmetros do Profit também não: **"tick a tick
= 1 semana" é limite de backtest/automação, e o indicador não o
respeita** — ele roda sobre tudo que o gráfico carregou.

### Por que a janela de data resolve sem custo

`LogDataInicio` / `LogDataFim` suprimem apenas o `ConsoleLog`. O
indicador continua **calculando** sobre todo o histórico, então a janela
de 50 barras e o aquecimento do z-score ficam intactos.

Reduzir o período do gráfico teria o mesmo efeito no buffer, mas custaria
o aquecimento: as primeiras 50 barras da janela sairiam com `z = 0` e as
seguintes com estatística de amostra curta. Filtrar no log não custa
nada disso.

    LogDataInicio = 1260701   (01/07/2026)
    LogSomenteSinal = 0       (amostra NAO selecionada — ver abaixo)

### Por que desligar `LogSomenteSinal` na equivalência

Logando só as barras coloridas, a amostra fica **selecionada pelo z do
NTSL**. Se as duas implementações divergirem, só se enxerga as barras
onde o NTSL achou extremo — e fica-se cego para o caso oposto, onde o
Python acha extremo e o NTSL não. Para comparar duas implementações, a
amostra tem que ser independente do resultado de qualquer uma delas.

## Diagnóstico do `SoAgressores`: RESOLVIDO (2026-08-30)

Sobre 2.001 barras reais:

    vol_total == vol_so_agressores em 0,00% das barras (0 de 2.001)
    mediana vol_total          171.058
    mediana vol_so_agressores  124.086
    mediana agrC + agrV        124.086

**O opcional Plugin Tape Reading está ativo** — o `SoAgressores` é
obedecido, não ignorado em silêncio. A armadilha do manual existe, mas
não é o caso aqui.

E `AgressionVolBuy + AgressionVolSell` é **exatamente**
`QuantityVol(False, True)`: razão mediana 1,0000, com p05 e p95 também
em 1,0000. Duas APIs diferentes, mesmo número, barra a barra.

### Fração de RLP + leilão: 26%

    mediana 0,2603   p95 0,3434   max 0,7125

É a divergência prevista por escrito antes de qualquer medição: o OHLC
do gráfico inclui esses 26%, o do profit-tape não. Quando a equivalência
rodar, `desloc_norm` vai divergir por isso — agora com a magnitude
conhecida de antemão, em vez de virar surpresa.


## EQUIVALÊNCIA MEDIDA (2026-08-30) — 80 barras de 24/07/2026

    campo         n  iguais  frac   dif_mediana   dif_max    papel
    open         80       0  0,000    3608,008    3650,972   diagnostico
    high         80       0  0,000    3611,021    3646,279   diagnostico
    low          80       0  0,000    3606,408    3628,752   diagnostico
    close        80       0  0,000    3607,792    3628,957   diagnostico
    imbalance    80      80  1,000       0,000       0,000   equivalencia
    desloc_norm  80      33  0,413       0,013892    0,181818 equivalencia
    absorcao_dir 80      33  0,413       0,013892    0,181818 equivalencia
    z            55       0  0,000       0,146120    0,518564 equivalencia

### `imbalance`: exato

80 de 80 dentro de 1e-6, diferença **máxima** 0,000000. O volume de
agressão do gráfico (`AgressionVolBuy/Sell`) e o do tape capturado via
ProfitDLL produzem o mesmo número barra a barra. Era a maior incógnita
do desenho.

### `desloc_norm`: diverge, e a divergência é inteiramente atribuída

O erro de `absorcao_dir` é IDÊNTICO ao de `desloc_norm` — mesma mediana
(0,013892), mesmo máximo, as mesmas 33 barras iguais. Como
`absorcao_dir = imbalance − desloc_norm` e `imbalance` é exato, toda a
divergência vem do OHLC. **Não sobrou resíduo inexplicado.**

Previsto por escrito antes da medição: o OHLC do gráfico inclui RLP e
leilão (28% do volume no dia), o do profit-tape não.

Que 41% das barras batam EXATAMENTE é coerente com o mecanismo: RLP
imprime dentro do spread e frequentemente não define extremo novo.

### OHLC: confirma a escala

Diferença mediana de 3.608 pontos contra `176.000 × (1,02048 − 1) ≈
3.604`. O k medido pela grade de preço e o k implícito na diferença
batem.

### `z`: NÃO era comparável neste dia

24/07/2026 é o **primeiro dia do parquet**. O z do NTSL usa a janela do
gráfico (18 pregões de julho para trás); o do Python usa a janela do
parquet, que ali não tem passado. 25 das 80 células saíram `NaN` e as 55
restantes usavam janelas de **conteúdo diferente**.

A divergência de 0,146 não diz nada sobre a implementação — foi erro de
desenho do teste, escolher o dia da sobreposição sem notar que era a
borda da amostra. A ferramenta passa a detectar e avisar.

Para comparar `z` de verdade: sobreposição a partir de **28/07/2026**,
onde o parquet já tem 50 barras de passado.

### O que a ferramenta ganhou

- `--janela-z` e aviso automático quando as barras casadas caem nas
  primeiras `janela_z` barras do parquet.
- **Atribuição da causa**: correlação entre o erro por barra e a fração
  de RLP daquela barra, mais o erro mediano por quartil de RLP. Verifica
  o mecanismo em vez de constatar o sintoma — se o erro não crescer com
  o RLP, a previsão acertou por sorte e há outra coisa acontecendo.
- Mensagem útil para arquivo inexistente (o caso real tinha cedilha no
  nome e produzia 40 linhas de traceback).


## A ATRIBUIÇÃO FALHOU, e estava errada (2026-08-30)

Rodada a atribuição sobre as 80 barras de 24/07/2026:

    correlacao |erro| vs fracao de RLP : -0,1219
    RLP mediano por quartil  : [0,2437  0,2753  0,2864  0,3058]
    erro mediano por quartil : [0,01788 0,01790 0,01300 0,00000]

Correlação **negativa**, e o quartil de **maior** RLP com erro **zero**.
O oposto da previsão.

A explicação registrada — "o erro vem do RLP no OHLC, logo cresce com a
fração de RLP" — está **refutada** pelo próprio diagnóstico construído
para testá-la. Sem ele, o resultado anterior (divergência presente, do
tamanho esperado) teria sido lido como confirmação.

### A causa real está na aritmética, não no volume

O erro máximo medido é **exatamente 2/11**. Não é arredondamento — é a
assinatura de uma razão entre inteiros pequenos.

Com preço na grade de 5 pontos, `(close − open)` e `(high − low)` são
múltiplos inteiros do tick, então `desloc_norm` é razão de inteiros
pequenos. O que muda a razão é um print de RLP ou leilão **tocar um
extremo** — não o volume que ele carrega:

- barra com 35% de RLP, todo impresso dentro da faixa → erro **zero**;
- barra com 20% de RLP onde um único print fez máxima nova → erro.

E a sensibilidade cai com a amplitude: um tick a mais em 35 muda pouco,
em 11 muda muito. Como amplitude cresce com volume, e RLP cresce com
volume, a correlação com a fração de RLP sai **negativa** — foi
exatamente o observado.

### A atribuição foi trocada

Agora separa as barras em que os **extremos coincidem** (depois de
dividir pelo k estimado) das em que não coincidem, e mede o erro em cada
grupo. Se a causa for o extremo, o grupo "extremos iguais" tem erro ~0.
Reporta também a correlação com a amplitude — negativa confirma
quantização.

O teste correspondente constrói metade das barras com a máxima esticada
de um tick e **volume de RLP idêntico nos dois grupos**: se a explicação
antiga ainda valesse, ela não separaria nada.

Erro meu na primeira tentativa da nova versão: estimei o tick como a
menor amplitude da amostra e classifiquei tudo como igual. Trocado por
tolerância relativa, que não depende de estimar o tick.


## A SEGUNDA EXPLICAÇÃO TAMBÉM FOI REFUTADA (2026-08-30)

    k estimado                     : 1,020499
    barras com extremos IGUAIS     : 79 de 80
    erro mediano (extremos iguais) : 0,013699
    erro mediano (extremos difs)   : 0,018768
    correlacao |erro| vs amplitude : -0,4113

**79 das 80 barras têm os extremos idênticos** — `(high − low)` bate nos
dois lados — e o erro mediano nesse grupo é 0,0137, praticamente o erro
geral. A explicação "um print de RLP toca um extremo" está refutada.

Duas hipóteses derrubadas em sequência pelo mesmo diagnóstico. A
primeira (volume de RLP) reproduzia o sintoma; a segunda (extremo)
também. Nenhuma das duas era a causa.

### Se o denominador bate, a diferença está no numerador

`open` e `close` são o **primeiro e o último negócio** da barra. Um
print de RLP dentro da faixa não mexe em máxima nem mínima — mas muda a
abertura ou o fechamento se calhar de ser o primeiro ou o último. Com
~28% do volume em RLP, isso acontece com frequência.

Bate com tudo o que foi medido: amplitude igual em 79/80, erro ∝
1/amplitude (correlação −0,41), erro como razão de inteiros (máximo
exatamente 2/11) e 41% de barras exatas — aquelas em que nem o primeiro
nem o último negócio foi RLP.

### O diagnóstico agora decompõe, em vez de correlacionar

    desloc_norm = (close - open) / (high - low)

Separa as barras em quatro grupos — só o numerador difere, só o
denominador, os dois, nenhum — e reporta o erro mediano de cada um, mais
a diferença mediana de numerador e denominador em ticks. Não há para
onde a causa fugir.

Erro meu na primeira tentativa: estimei o tick pelo gcd das
**amplitudes**, e num caso em que todas valiam o mesmo o "tick" saiu
igual à amplitude. Trocado para o gcd das diferenças entre **preços
distintos**, que é onde a grade de fato aparece, com a classificação por
tolerância relativa para não depender dele.


## DECOMPOSIÇÃO CONCLUSIVA (2026-08-30) — é o numerador

    desloc_norm = (close - open) / (high - low)
    k estimado 1,020499 | tick estimado 5,0

    so' o NUMERADOR (close-open) difere : 46 de 80
    so' o DENOMINADOR (high-low) difere :  0
    os dois diferem                     :  1
    nenhum difere                       : 33   (erro mediano 0,0)

    diferenca mediana do numerador   : 1,0 tick
    diferenca mediana do denominador : 1,0 tick

Partição perfeita: 33 + 46 + 1 = 80, e os 33 "nada difere" são exatamente
as 33 barras iguais da linha `desloc_norm`. O denominador diverge em
**1 de 80**.

`(high − low)` é o mesmo nos dois lados. O que muda é `(close − open)`,
por **exatamente um tick**. Isso é `open` e/ou `close` — o primeiro e o
último negócio da barra.

### Sequência de três explicações, duas refutadas

1. "cresce com o volume de RLP" → correlação −0,12, quartil de maior RLP
   com erro zero. **Refutada.**
2. "um print de RLP toca um extremo" → 79/80 com extremos idênticos e o
   erro continuava. **Refutada.**
3. "o primeiro ou o último negócio da barra difere" → compatível com
   tudo: denominador intacto, numerador exatamente 1 tick, erro ∝
   1/amplitude, erro máximo 2/11, 41% de barras exatas.

As duas primeiras reproduziam o **sintoma** — divergência presente, do
tamanho esperado, ausente quando `imbalance` é exato. Nenhuma era a
causa. Sem um diagnóstico que testasse a explicação, qualquer uma teria
sido dada como confirmada.

### Falta separar `open` de `close`

O diagnóstico agora reporta as duas pontas em separado. É o que distingue
as duas causas ainda possíveis:

- **taxas parecidas nas duas pontas** → é o tipo do negócio (RLP), que
  um lado inclui e o outro não;
- **só o fechamento diverge** → é fronteira de barra, que afeta
  preferencialmente o último negócio, e aí o problema é de qual negócio
  cai em qual balde, não de preço.

### Erro de processo registrado

Uma edição por substituição de texto reportou sucesso **sem alterar
nada**: um `ruff --fix` anterior tinha removido as aspas de
`"pd.Series[bool]"`, então a âncora procurada não existia mais. A falha
só apareceu porque o teste novo quebrou com `KeyError`. É a terceira
falha silenciosa desta sessão — junto com o contador de buracos que
devolvia zero por construção e o validador de âncoras que achava zero
links.


## EQUIVALÊNCIA FECHADA (2026-08-30)

    so' open  : 21   |  so' close : 21   |  os dois : 6
    dif mediana open : 1,0 tick  |  close : 1,0 tick

Simetria perfeita entre as duas pontas. Isso resolve a última
bifurcação: **é o tipo do negócio, não a fronteira de barra.** Fronteira
afetaria preferencialmente o fechamento — é o último negócio que corre
risco de cair no balde seguinte, e a abertura não teria por que sofrer
igual.

### A explicação fecha em três frentes independentes

**Taxa.** As pontas divergem em 27/80 = 33,8% das barras, contra 27,9%
de RLP+leilão por *volume*. A taxa por negócio ser MAIOR que a por
volume significa que os negócios de RLP são menores que a média — que é
exatamente o esperado de internalização de varejo.

**Independência.** Com p = 0,3375 nas duas pontas, o esperado para
"ambas divergem" é 9,1 e o observado é 6; para "ao menos uma", 44,9
contra 48. Compatível.

**Magnitude.** Um tick exato nas duas pontas, e o denominador intacto em
79 de 80 — RLP imprime dentro da faixa e raramente define extremo.

### Conclusão

O indicador NTSL e o pipeline Python calculam **a mesma fórmula**. As
diferenças são todas conhecidas, medidas e explicadas:

| campo | resultado |
|---|---|
| `imbalance` | **exato**, 80/80, diferença máxima 0,000000 |
| `desloc_norm` | diverge em 47/80, sempre por 1 tick em `open`/`close` |
| `absorcao_dir` | herda exatamente o erro de `desloc_norm` |
| OHLC | escala k = 1,020499 (série contínua ajustada) |

**Causa única**: o OHLC do gráfico usa o primeiro e o último negócio de
*qualquer* tipo; o do profit-tape usa só agressão. Quando o primeiro ou
o último negócio da barra é RLP ou leilão, `open` ou `close` difere por
um tick.

Impacto prático no z: `Δz ≈ 0,0139 / 0,38 ≈ 0,037`, cerca de 3,7% de um
desvio. Perto do limiar de 1,75 isso pode trocar a cor de uma fração
pequena das barras.

### O que ficou de fora

O `z` não foi comparado — a sobreposição caiu no primeiro dia do
parquet, onde as janelas têm conteúdo diferente por construção. Para
fechar: `LogDataInicio = 1260728`.


## ROLAGEM DENTRO DA AMOSTRA invalidou a atribuição (2026-08-30)

Rodada sobre **2.001 barras** (28/07 a 21/08/2026, 19 pregões, todos
longe da borda do parquet):

    imbalance    2001/2001 iguais, diferenca maxima 0,000000
    desloc_norm  1045/2001 (52%), mediana 0,000000, max 1,103876
    z            mediana 0,031623, max 3,025623

`imbalance` exato sobre 19 pregões — a conclusão de 24/07 se sustenta em
amostra 25 vezes maior. E o `z` com mediana 0,0316 confirma a propagação
prevista (≈0,037).

### O diagnóstico de pontas deu 682 ticks — e a causa era minha

29% dos `open` batiam **exatamente**, o que é impossível se todos os
preços estivessem escalados pelo mesmo k. Medido por pregão:

    28/07 a 11/08 : k = 1,020480
    12/08 a 21/08 : k = 1,000000

**Houve rolagem de contrato dentro da amostra.** A série contínua passou
a apontar para o contrato corrente, que não precisa de ajuste.

Um k global vira média dos dois regimes. Dividir por k errado desloca
`open` e `close` em ~2%, que num numerador típico vale **~1 tick** —
indistinguível do efeito que se queria medir. A "diferença mediana de
1,0 tick" e os "682 ticks" do diagnóstico de pontas eram os dois
artefatos do meu k.

Isso significa que a atribuição de 24/07 — feita num único pregão, onde
k é constante por construção — continua válida; mas o número de 1 tick
que ela produziu **não** pode ser extrapolado para a janela inteira sem
o k por pregão.

### Corrigido

`k` passa a ser estimado **por pregão** (mediana da razão entre
fechamentos; dentro de um pregão não há rolagem). O comando avisa
quando detecta mais de um fator e lista os valores por dia.

Teste de regressão com dado idêntico nos dois lados e dois fatores k
diferentes: com k por pregão o erro tem que ser exatamente zero.


## Restricoes do Profit, consolidadas (2026-08-30)

Reunidas aqui porque estavam espalhadas por varias secoes e esquecer
delas custou tres dumps inuteis num unico dia.

| restricao | consequencia pratica |
|---|---|
| console retem ~2.000 linhas | limita o dump por rodada |
| buffer enche de TRAS PARA FRENTE | mais historico no grafico = log termina mais CEDO |
| "tick a tick = 1 semana" | e' de BACKTEST/AUTOMACAO; o indicador ignora |
| backtest so' aceita estrategia automatizada | codigo precisa ter funcao do modulo backtest |
| `WINFUT` = serie continua AJUSTADA | `k` muda nas rolagens; nivel nao e' comparavel |
| `SoAgressores` sem Plugin Tape Reading | vira `False` em SILENCIO (confirmado ativo aqui) |
| `VolumeAtPrice` | historico curto |
| livro | sem historico na automacao |

**A saida para o buffer** e' `LogDataInicio`/`LogDataFim`, que suprimem
apenas o `ConsoleLog`. O indicador continua CALCULANDO sobre todo o
historico, entao a janela de 50 barras e o aquecimento do z-score ficam
intactos — reduzir o periodo do grafico teria o mesmo efeito no buffer
mas custaria o aquecimento.

**Custo de extrair historico longo**: ~2.000 linhas por dump, janela de
data ajustada a mao. Para 300 pregoes com log completo (113
barras/pregao) seriam ~17 dumps. Viavel, mas entra na conta antes de
prometer amostra grande.

### O backtest do Profit nao substitui o pipeline

So' aceita estrategias automatizadas — o codigo precisa conter funcoes
do modulo backtest para ser classificado como tal, e por isso o
`absorcao_dir.ntsl` (so' `Plot`/`PaintBar`/`ConsoleLog`) aparece como
indicador.

Mas a limitacao que importa nao e' essa: o backtest do Profit nao tem
validacao cruzada purgada, limiar deflacionado, portao de honestidade
nem contador de trials. Ver `RESEARCH_PLANO.md`, secao "POLITICA DO
HISTORICO DO GRAFICO".


## AS QUATRO CORES: a subtracao escondia duas leituras opostas (2026-08-31)

### O caso que revelou

Barra real de 31/08, 09:03-09:05, reconstruida do tape (169.920
negocios):

    imbalance    +0,0486   agressao praticamente empatada
                           (185.742 compra x 168.510 venda)
    desloc_norm  +0,9509   quase marubozu de ALTA, +326 ticks
    absorcao_dir -0,9023   -> pintava AQUA

A leitura do operador foi a oposta da que a cor sugeria: "os compradores
agrediram e levaram o preco embora". **Os numeros deram razao a ele.**
Nao houve vendedor agredindo nada — o preco subiu porque o livro estava
fino.

### O defeito conceitual

`absorcao_dir = imbalance - desloc_norm` e' uma SUBTRACAO, e um valor
extremo pode vir de dois lugares OPOSTOS:

| caso | o que acontece | leitura |
|---|---|---|
| **A** | agressao forte num sentido, preco no outro | esforco que FALHOU — absorcao |
| **B** | preco anda muito SEM agressao dominante | AUSENCIA de resistencia — livro fino |

Os dois pintavam a mesma cor.

E ha' um agravante de escala: `imbalance` raramente sai de +-0,3
enquanto `desloc_norm` vai ate +-1. **Quem domina a subtracao quase
sempre e' o `desloc_norm`** — ou seja, boa parte do que o indicador
pintava era deslocamento normalizado com o sinal trocado, e nao
absorcao. Coerente com o CONTRA nas 12 celulas.

### A separacao

    clRed     A - comprador agrediu e NAO levou     (vendedor passivo)
    clAqua    A - vendedor agrediu e NAO levou      (comprador passivo)
    clFucsia  B - preco CAIU sem esforco vendedor   (livro fino)
    clYellow  B - preco SUBIU sem esforco comprador (livro fino)

O discriminante e' `z_imbalance` na MESMA janela, com o MESMO
anti-lookahead. Tem que ser o z e nao o valor cru, senao a diferenca de
escala classificaria quase tudo como B.

`LimiarImb` (default 1,00) **NAO E' VALIDADO**, igual ao `Limiar`. Serve
para separar duas leituras, nao para gerar sinal.

O log ganhou o campo `z_imbalance` ao final — ordem CONGELADA, o parser
mudou junto.

### O termo que falta, e agora esta medido

Absorcao, na leitura de tape, e' ESFORCO GRANDE com RESULTADO PEQUENO. O
esforco precisa de um termo ILIMITADO, porque `imbalance` nunca passa
de 1:

    esforco = vol_agr / amplitude_em_ticks

Na barra de 31/08: 354.252 contratos em 326 ticks = **1.087 contratos
por tick**. Barra que anda muito com volume normal tem esforco BAIXO;
barra que anda pouco com volume enorme tem esforco ALTO.

Comando novo, categoria `features` (zero trial):

    profit-tape absorcao-diagnostico WINFUT --tf 5m

Ele mede a distribuicao do esforco e a separacao A/B sobre os pregoes
capturados. **Nao testa predicao** — e' o insumo empirico para um
pre-registro futuro, que continua exigindo ser escrito e congelado
antes.


## AGRESSAO ZERADA: a falha silenciosa aconteceu de verdade (2026-08-31)

Dump de WINFUT 5m, 24/07 a 19/08/2026, 2.001 barras:

    QuantityVol(False, False)  mediana  108.534   funciona
    QuantityVol(False, True)   mediana   78.115   funciona, e DIFERE
    AgressionVolBuy            maximo         0   ZERO
    AgressionVolSell           maximo         0   ZERO

    absorcao_dir == -desloc_norm em 2001 de 2001 barras

**O dado de agressao EXISTIA.** `QuantityVol(False, True)` separou
agressor de nao-agressor (78.115 contra 108.534), o que so' e' possivel
com o Plugin Tape Reading ativo. Uma API entregou o dado e a outra
devolveu zero na MESMA barra.

Nao e' licenca, nao e' simbolo, nao e' timeframe: o periodo 24/07-19/08
**se sobrepoe a dois dumps que funcionaram no mesmo dia** (01/07-24/07 e
28/07-21/08, ambos com agressao valida).

Hipotese que resta: `QuantityVol` vem do volume consolidado da barra,
que acompanha o historico do grafico, enquanto `AgressionVolBuy/Sell`
dependem do dado tick a tick que o Profit baixa SOB DEMANDA. Grafico
recriado ou recarregado ainda nao tem esse dado, e as funcoes devolvem
zero em vez de esperar. **Testavel**: deixar o grafico aberto no periodo
e gerar o dump de novo.

### Por que isso e' grave

Com `imbalance = 0`:

    absorcao_dir = 0 - desloc_norm = -desloc_norm

O indicador passa a medir **deslocamento normalizado com o sinal
trocado**. As cores continuam pintando, o log continua saindo, os
numeros continuam plausiveis. Era o risco levantado na primeira sessao
como "aviso nao decorativo" — e ele se materializou.

### Guarda no parser

`carregar_log` agora RECUSA log com agressao zerada e volume presente,
explicando a causa e o que fazer.

A checagem compara as DUAS fontes de proposito: agressao zero COM volume
zero e' barra sem negocio (normal, tem teste proprio) e nao dispara.
Agressao zero COM volume presente e' contradicao. Uma guarda que grita a
toa acaba desligada.
