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

## Backfill: fatos empiricos da conta em uso (medidos em 2026-08-21)

- `fim` e' EXCLUSIVO: pedir 19..20 entrega so o dia 19 (09:00 as 18:31 BRT
  do WIN, sessao completa). Para N dias, peca ate o dia seguinte ao ultimo.
- Vazao observada do servidor de historico: ~27-37 mil eventos/s.
- Volume de referencia: 1 pregao de WINFUT ~= 5,0M negocios; WDOFUT ~500k;
  PETR4/VALE3/ITUB4 ~40-47k cada. Dimensione --timeout por ai
  (ex.: 60 pregoes de WIN ~= 300M eventos ~= 2h30-3h de download).
- O servidor respondeu de madrugada; a recusa NL base+46 logo apos conectar
  se resolve com o settle padrao de 5s.
- ERRATA (2026-08-21): uma versao anterior desta doc afirmava "~11% de
  trade_id repetidos no feed". FALSO — era bug do inspect contando ids
  globalmente quando eles sao sequenciais POR SIMBOLO. O feed de historico
  nao apresentou duplicata alguma. O curate segue obrigatorio (dedup real
  pode ocorrer em reconnect no realtime), mas o numero era artefato.
- A maquina NAO pode suspender durante captura: um cochilo do Windows
  congelou quiesce, progresso e timeout no meio de um run (deteccao de
  drift agora avisa, mas nao conserta). Desative a suspensao no plano de
  energia enquanto grava.

## Offer book: V1 x V2 (incidente 2026-08-21)

Os slots de callback do DLLInitializeMarketLogin sao os tipos V1 (nQtd em
Integer 32 bits). Registrar callbacks V2 neles produziu dois sintomas
diferentes e nenhum crash: o offer book ficou MUDO (subscribe aceito, zero
eventos em 14 min de pregao) e o price book "funcionou" lendo Int64 de um slot
de 32 bits — quantidade com bits altos potencialmente sujos.

Correcao: slots do init tipados como V1; o offer book order-by-order e'
registrado via SetOfferBookCallbackV2 apos o init (o setter sobrepoe o slot do
init, por manual). O doctor passou a checar a presenca do setter.

DADO A DESCARTAR: o book_price gravado ANTES desta correcao (sessao de
2026-08-21, ~14 min) pode ter quantidades corrompidas nos bits altos. Nao usar
em analise; a particao pode ser removida.

## bHasDate ignorada: causa DOMINANTE do timestamp "1990" (incidente 2026-08-21, parte 3)

CORRECAO DE REGISTRO: a "parte 2" abaixo atribuiu o timestamp implausivel ao
atFullBook. Isso estava CERTO mas INCOMPLETO — o atFullBook explica ~100
pacotes por sessao; a sessao real tinha 2.181.338 linhas implausiveis (97% do
total). A causa dominante e' outra, e maior: o manual documenta bHasDate ("1
byte para especificar se existe data") no TOfferBookCallbackV2, e o codigo
IGNORAVA essa flag, parseando pwcDate incondicionalmente. A maioria dos
deltas de book (atAdd/atEdit/atDelete) NAO carrega data por evento — quando
bHasDate=False, pwcDate aponta para conteudo obsoleto (nao nulo!) de um
evento anterior, que parece uma data valida e parseia "com sucesso" para o
timestamp errado.

Correcao: has_date persistido no schema (BookDelta.has_date); ts_ns so' e'
parseado quando a flag confirma presenca de data, senao ts_ns=0 por design
(nao por falha). O `inspect` foi atualizado para NAO alarmar nesse caso —
"sem data por evento: N (X%) — normal para deltas de book; use ts_recv_ns" —
e so' aponta TIMESTAMP INVALIDO de verdade quando ts_ns=0 SEM has_date=False
correspondente (parse realmente falhando).

ESTADO ESPERADO DAQUI PRA FRENTE: e' NORMAL que a maioria das linhas de
book_offer tenha has_date=False e ts_ns=0. Use ts_recv_ns para ordenacao
temporal de deltas de book; ts_ns so' e' confiavel quando has_date=True.

## atFullBook: campos escalares descartados (incidente 2026-08-21, parte 2)

O manual documenta, para TOfferBookCallbackV2 e TPriceBookCallbackV2: os
arrays pArraySell/pArrayBuy "sao validos em atFullBook" (nAction=4). A
contrapartida — nao dita explicitamente mas confirmada pelo incidente — e' que
os campos escalares (preco, data, etc.) NAO sao o payload real nesse caso.
Publica-los como um delta normal grava lixo: uma sessao real produziu uma
linha com timestamp "1990-01-01", memoria obsoleta lida como se fosse data
valida — e essa diferenca de tempo, ao ser usada no calculo de latencia,
tambem derrubava o `inspect` (estouro do cast seguro int64->float64).

Correcao: eventos com action=atFullBook sao descartados na origem (client.py)
e contados em `full_book_descartados` (aparece no resumo do record). O
`inspect` tambem ganhou defesa em profundidade: filtra timestamp implausivel
(nao so ts_ns==0) antes de calcular latencia, e reporta a contagem em vez de
deixar contaminar a mediana silenciosamente.

DADO A DESCARTAR: as capturas de book_offer/book_price ANTES desta correcao
(sessoes de 2026-08-21) contem linhas atFullBook com campos escalares
invalidos misturadas aos deltas validos. Nao usar em analise sem filtrar; o
mais simples e' re-capturar.

PENDENCIA (Tier 2, nao bloqueia Tier 1): o payload real do atFullBook — o
livro completo no momento da subscricao — nao e' decodificado. O formato e'
registro de tamanho VARIAVEL (campo de data e' string com tamanho prefixado),
documentado no manual nas secoes de TOfferBookCallbackV2/TPriceBookCallbackV2
("Cabecalho"/"Array"/"Rodape"). Sem isso, o recorder captura corretamente os
DELTAS a partir da subscricao mas nao o estado inicial do livro — para
bootstrapar o book seria preciso ou parsear esse payload ou reconstruir so a
partir dos deltas full-book incrementais em diante (perdendo o snapshot
inicial). Fica para quando o Tier 2 comecar a reconstrucao de livro.

## LIMITE CONFIRMADO: GetHistoryTrades so' cobre 30 dias corridos (2026-08-21)

O manual documenta `NL_HISTORY_PERIOD_LIMIT` (0x8000002E, base+46 — o mesmo
codigo "desconhecido" investigado em incidentes anteriores desta doc):
"Periodo de historico solicitado excede o limite permitido (data inicial com
mais de 30 dias)". Confirmado empiricamente: dias com mais de ~30 dias
corridos antes de hoje sao recusados na hora (a "recusa" de conexao dos
primeiros incidentes tambem era isto, nao instabilidade do servidor).

IMPLICACAO ESTRATEGICA: um backfill de ~60 pregoes via GetHistoryTrades e'
estruturalmente IMPOSSIVEL nesta conta/versao. O maximo obtenivel de uma vez
e' ~20 pregoes (30 dias corridos ~= 20-22 dias uteis). O plano original de
"backfill grande + pesquisa" precisa virar "backfill do maximo permitido +
GRAVACAO AO VIVO DIARIA acumulando dali em diante" — sem atalho.

ACAO RECOMENDADA:
1. Backfill --por-dia com --inicio de ~28-29 dias atras (margem de seguranca
   contra diferenca de fuso/corte exato do servidor) ate ontem. Produz o
   maximo de historico imediato disponivel.
2. Rodar `record` TODO pregao dali em diante (Agendador de Tarefas, ver secao
   acima) — e' a UNICA forma de acumular alem dos 30 dias, um dia de cada vez.
   O dataset de pesquisa cresce ~1 pregao/dia; CPCV/DSR com amostra robusta
   e' questao de semanas, nao de uma noite.
3. Se precisar de historico mais profundo AGORA, a saida e' fora do
   ProfitDLL: fontes pagas ja mapeadas (Databento, Economatica) ou B3
   COTAHIST (publico, mas so' EOD — nao serve para tick/fluxo).

NOTA A PARTE (nao aplica ao GetHistoryTrades usado aqui): o manual documenta
uma API de series MAIS NOVA (GetSerie, com a_pSerieID/a_pQuoteStart) com
limites de 1-Trade DIFERENTES por ativo — WIN=8 dias, WDO=30, DOL/IND=180,
outros=365. Essa API nao esta implementada neste projeto; se um dia for
adotada, WIN especificamente teria janela AINDA MENOR (8 dias), nao maior.
Nao e' uma saida para o limite de 30 dias do WIN.

## Disco lento (latencia de escrita no volume de dados)

SINTOMA: `writer.lote_lento` com poucos segundos para POUCAS linhas indica
latencia de criacao de arquivo (nao vazao) — suspeitos classicos: antivirus
escaneando cada parquet novo, HDD saindo de spin-down, USB com suspensao
seletiva. `lote_lento` com MUITAS linhas indica vazao baixa de verdade.

O QUE PROTEGE A CAPTURA: a fila (pipeline.fila_maxsize) absorve o descompasso.
Descarte so' ocorre com fila 100% cheia — e agora ha' alerta ANTES:
`fila_subindo` a 10% de ocupacao, `fila_critica` a 50%. O heartbeat tambem
mostra `escrita_linhas_s` (vazao do writer): se ficar abaixo da taxa de
chegada, a fila sobe — e' o preditor do problema, nao o problema.

MEDIR ANTES DE MITIGAR:
    profit-tape bench --raiz G:\bench_tmp --duracao 20
O bench sem --raiz mede o temp do C:, que pode nao ser onde a captura grava.

MITIGACOES, em ordem de custo/beneficio:
1. Exclusao de antivirus na pasta de dados (G:\data) — resolve o caso mais
   comum de latencia de segundos na criacao de arquivo. Decisao de seguranca
   do operador.
2. Energia: desativar spin-down do HDD e suspensao seletiva de USB no plano
   de energia enquanto captura.
3. fila_maxsize maior no recorder.yaml (ex.: 2_000_000 ~ centenas de MB de
   RAM) — mais colchao para rajadas; nao conserta vazao cronica, so' absorve.
4. batch_max maior (ex.: 100_000) — menos operacoes de escrita, maiores;
   ajuda quando o custo dominante e' por-operacao (latencia), nao por-byte.
5. SPOOL: gravar no volume rapido (C:) e mover ao fim da sessao:
       storage.raiz: data/raw          (local, rapido)
       robocopy C:\projetos\profit-tape\data\raw G:\data\raw /E /MOVE
   Viabilidade: ~20 pregoes de trades ~= poucos GB; sessao diaria de book
   ~= 1-2 GB — cabem com folga nos ~25 GB do C: antes do move noturno.

O que NAO ajuda: reduzir nivel_compressao (zstd e' custo de CPU, nao de
latencia de disco); aumentar poll_timeout (so' atrasa a deteccao).

## INCIDENTE CRITICO: 96 arquivos sem footer no G: USB (2026-08-21)

SINTOMA: apos backfill que reportou backfill_dia.ok com conservacao exata, o
inspect marcou 96 de 100 arquivos como corrompidos. Diagnostico por bytes:
arquivos comecam com PAR1 (magic inicial) mas terminam em 00 00 00 00 em vez
de PAR1 (magic final). Ou seja: os DADOS (row groups, ~135 MB/arquivo) estao
gravados, mas o FOOTER (indice no fim, alguns KB) nunca chegou ao disco.

CAUSA RAIZ: writer.close() escreve o footer, mas em disco USB externo com
spin-down o footer fica no cache de escrita do Windows. O rename-on-close
seguinte "tem sucesso" — renomeia um arquivo cujo footer ainda esta em RAM. O
rename e' atomico para o NOME, nao para o CONTEUDO. Quando o disco dorme ou
desconecta antes do flush, o footer se perde. Confirmado: o fluxo close+rename
produz footer perfeito em disco local; o problema e' especifico do USB.

CORRECAO: fsync do arquivo ANTES do rename (parquet_sink._close_one), forcando
o footer ao disco fisico. rename-on-close so' garante atomicidade se o conteudo
ja' estiver duravel.

RECUPERACAO DOS 96 ARQUIVOS EXISTENTES: os row groups estao fisicamente no
disco, mas sem o footer o pyarrow nao os le. Reconstruir o footer exige
reparsear os page headers Thrift arquivo a arquivo — possivel, mas trabalhoso e
sem garantia. Como TODOS os pregoes afetados (24/07 a 19/08) ainda estao dentro
da janela de 30 dias do GetHistoryTrades, a rota recomendada e' RECAPTURAR com
o writer corrigido, nao reconstruir. Recuperacao forense so' se justificaria
para dado fora da janela e insubstituivel.

LICAO PARA O RECORD DIARIO: sem o fsync, o record agendado sofreria o mesmo em
TODO pregao gravado no G:, e a perda so' apareceria semanas depois. O fsync
torna cada arquivo duravel no momento em que fecha.

## Fosseis sem footer da era do fsync quebrado (2026-08-22)

Os part-0000 gravados antes do fsync corrigido (v0.27) ficaram sem footer. A
recaptura com v0.27+ NAO os sobrescreve — a numeracao de part e' descoberta no
disco e incrementa (part-0001, part-0002) para nunca sobrescrever dado bom.
Resultado: dias recapturados ficaram com o part-0000 fossil ao lado do
part-0001 novo. curate/inspect leem o bom e reportam o fossil como corrompido.

NAO E' bug de captura multi-dia (a captura de multiplos dias funciona). E' lixo
acumulado. Limpeza segura:
    profit-tape quarentena G:\data\raw            # dry-run, so' lista
    profit-tape quarentena G:\data\raw --remover  # apaga os sem-footer
A ferramenta avisa quais dias ficam SO' com fossil (precisam recaptura) antes
de apagar. Depois de limpar, recapture os dias sinalizados.

## Instabilidade da origem no historico (2026-08-22)

Alguns dias DENTRO da janela de 30 dias vieram sem_entrega mesmo apos o retry,
com o servidor oscilando de estado (conexao tipo=2 valor 0->1->2->4) durante os
pedidos. Nao e' o limite de 30 dias nem bug local — e' instabilidade da origem
naquela sessao (os MESMOS dias baixaram em rodadas anteriores). O retry de 3
tentativas ajuda mas nao cobre instabilidade prolongada. Resposta correta: como
o backfill --por-dia e' retomavel (pula dias ja capturados), basta RE-RODAR o
mesmo comando mais tarde — de madrugada o servidor de historico costuma estar
mais estavel (fato observado desde as primeiras sessoes).

## Backfill pulava dia inteiro ao ampliar a lista de ativos (2026-08-23)

SINTOMA: baixou WINFUT completo, ampliou o yaml para WDOFUT+acoes e rodou o
mesmo backfill — reportou os dias como 'ja capturados' sem NUNCA pedir
WDOFUT/acoes ao servidor.

CAUSA: _dia_ja_capturado checava so' 'existe QUALQUER .parquet nesse dt=',
nao 'existe .parquet de CADA ticker configurado'. Um dia com so' WINFUT ja
marcava o dia inteiro como feito para qualquer combinacao de ativos.

CORRECAO: a checagem agora exige .parquet de TODOS os tickers configurados
para o dia contar como capturado. E o pedido por dia so' solicita os tickers
que AINDA FALTAM naquele dia especifico — nao re-baixa um simbolo ja presente
so' porque outro do mesmo dia esta pendente.

Efeito pratico: ao ampliar `cfg.ativos` no yaml e re-rodar o MESMO comando de
backfill, ele agora completa os simbolos que faltam em cada dia ja iniciado,
em vez de pular o dia inteiro.

## Alertas via Telegram (2026-08-24)

Opcional — sem config/alertas.yaml, tudo roda normalmente sem notificar.

### Configurar
1. Fale com @BotFather no Telegram, `/newbot`, copie o token.
2. Mande qualquer mensagem para o bot recem-criado.
3. Abra `https://api.telegram.org/bot<TOKEN>/getUpdates` e leia `chat.id`.
4. Copie `config/alertas.example.yaml` para `config/alertas.yaml` (gitignored)
   e preencha os dois campos.

### O que dispara alerta (hooks DENTRO do record, tempo real)
- inicio do pregao (confirmacao de que subiu e subscreveu)
- fim do pregao (resumo: linhas, descartes, fila_pico, arquivos verificados)
- erro fatal (`recorder.erro`, processo caindo com excecao)
- fila CRITICA (nao "atencao" — esse so' loga, para nao gerar ruido)
- arquivos NAO verificados (footer nao confirmado — o tipo de incidente que
  custou um dia inteiro de recaptura nesta semana)

### O que o vigia cobre (processo EXTERNO, watchdog)
Os hooks acima so' alertam se o record chegou a RODAR. Se ele nunca iniciar
(schtasks ausente, notebook desligado, DLL rejeitando login), ninguem alerta
sobre si mesmo — por isso o vigia existe como processo separado:

```
profit-tape vigia
```

Agende via schtasks proprio, a cada 5 minutos, das 09:00 as 18:35:
```powershell
schtasks /Create /TN "profit-tape-vigia" /SC MINUTE /MO 5 `
  /ST 09:00 /ET 18:40 `
  /TR "C:\projetos\profit-tape\.venv\Scripts\profit-tape.exe vigia" `
  /RL LIMITED /F
```
Cooldown por tipo de alerta evita spam (30min para "nao iniciou", 15min para
"travado", etc — ver vigia.py). Estado em logs/vigia_estado.json (gitignored).

## Log em arquivo agora e' JSON de verdade (2026-08-24)

Bug corrigido: --log-file gravava o MESMO texto formatado do console, nunca
JSON, apesar do nome .jsonl. Console continua legivel/colorido; arquivo agora
e' JSON valido, uma linha por evento — o vigia (e qualquer ferramenta futura)
depende disso para parsear o log programaticamente.
