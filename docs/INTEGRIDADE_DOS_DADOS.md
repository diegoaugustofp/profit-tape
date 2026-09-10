# Integridade dos dados — registro de problemas conhecidos por periodo/stream

Livro de bordo dos incidentes que afetaram QUALIDADE do dado (nao so'
disponibilidade). Consulte isto antes de tirar conclusao de research sobre
periodo ou stream aqui listado. Ordem cronologica reversa (mais recente
primeiro).

---

## book_offer — capturas ANTERIORES a 2026-08-26 (correcao v0.55)

**O que aconteceu**: deltas de offer book sem bHasDate (a MAIORIA dos
deltas, comportamento normal do protocolo — nao e' excecao) tinham
ts_ns=0. O writer confundia isso com timestamp valido (epoch =
1970-01-01) em vez de cair no fallback de ts_recv_ns. Uma fatia
desconhecida — provavelmente grande — de TODO book_offer capturado antes
desta correcao foi parar na particao fossil dt=1970-01-01 (ou dt=1990-01-01
numa manifestacao anterior do mesmo bug de raiz) em vez do dia real.

**Correcao**: pipeline/writer.py, v0.55 (2026-08-26). Detalhe completo em
docs/OPERACAO.md.

**Impacto pratico**:
- Qualquer dia de book_offer capturado ANTES de 2026-08-26 pode estar
  FALTANDO uma fracao significativa de eventos (os que foram para a
  particao fossil e depois apagados em limpezas).
- NAO HA' COMO DISTINGUIR, olhando so' o book_offer de um dia especifico
  anterior a essa data, se ele esta completo ou nao — o sintoma e'
  silencioso (menos eventos que o esperado, sem erro).
- trade e price_book NUNCA foram afetados por este bug especifico.
- tiny_book nao e' afetado (nao usa ts_ns para particionar).

**Se algo parecer estranho em research/features sobre book_offer de dias
anteriores a 2026-08-26**: primeiro suspeite disto antes de qualquer outra
hipotese. Pregao com contagem de eventos de book anormalmente baixa,
gaps de fila de ofertas, ou desequilibrio suspeito entre compra/venda no
book podem ser consequencia direta deste bug, nao um fenomeno de mercado.

**Recomendacao**: tratar todo book_offer anterior a 2026-08-26 como
NAO-CONFIAVEL para pesquisa que dependa de completude do stream (OFI,
queue imbalance). trade do mesmo periodo continua confiavel.


## Dados perdidos por travamento de maquina — 18 arquivo(s) sem footer

- **book_offer**, dt=2026-09-08: sym=BOVA11, sym=ITUB4, sym=PETR4, sym=VALE3, sym=WDOFUT, sym=WINFUT
- **book_price**, dt=2026-09-08: sym=WINFUT
- **tiny_book**, dt=2026-09-08: sym=BBAS3, sym=BOVA11, sym=ITUB4, sym=MGLU3, sym=PETR4, sym=VALE3, sym=WDOFUT, sym=WEGE3, sym=WINFUT
- **trade**, dt=2026-09-08: sym=WDOFUT, sym=WINFUT
## Lacuna por queda de rede real durante o teste B do E1 (2026-09-09, ~83 s)

Durante o teste B (record de produção com `login_completo: true`), a
internet caiu duas vezes ao longo do pregão. A primeira ficou registrada
com precisão no log:

- **15:23:42 -> 15:25:05** (~83 s): `linhas` do heartbeat CONGELADO no
  mesmo valor pelos dois heartbeats intermediarios, `sem_evento_ha_s`
  subindo 19,2 -> 49,2 -> 79,3. Roteamento (`tipo=1`) E mercado (`tipo=2`)
  oscilando juntos ate' a DLL reconectar sozinha.
- `descartados=0` durante toda a janela -- **nao contradiz a lacuna**:
  esse contador so' mede descarte por fila cheia (`queue.Full`), nunca
  dado que nunca chegou por a conexao ter caido. As duas coisas sao
  independentes; aqui a fila nunca encheu porque nao havia nada chegando.
- Nenhum negocio de nenhum dos 9 ativos foi capturado nesses ~83 s. Nao
  ha' como recuperar -- nunca chegou a DLL, entao nunca esteve em
  nenhum buffer nosso.
- Houve uma SEGUNDA queda no mesmo pregao, mencionada pelo operador mas
  sem log detalhado anexado aqui.

**Se algo parecer estranho em research sobre 09/09 perto de 15:23-15:25**:
suspeitar desta lacuna antes de qualquer hipotese de mercado. Volume ou
contagem de trades anormalmente baixa nesse minuto e meio e' esperado,
nao sinal.

**O lado bom, registrado no EA_ARQUITETURA.md (E1)**: a reconexao foi
inteiramente gerenciada pela DLL (nosso codigo nunca rechama
`DLLInitializeLogin`); `corretora_pronta` seguiu o estado real durante
toda a queda (caiu para False, voltou True sozinho quando a DLL avisou),
validando ao vivo a regra de checar `corretora_pronta` no MOMENTO do
envio de ordem, nao uma vez so' no inicio.


## BUG REAL: row groups minusculos por cadencia de escrita (2026-08-21 a 2026-09-10)

`EventBus.drain()` usava `get_nowait()` (espera ZERO) para todo item apos
o primeiro, contradizendo o proprio docstring ("Lote grande e' o que
torna a escrita eficiente"). Contra um produtor de CADENCIA REGULAR (nao
rajada instantanea) -- o padrao real de um ativo de alta frequencia --
o consumidor "vencia a corrida" quase sempre: acordava no primeiro item,
checava `get_nowait()`, achava vazio porque o proximo ainda nao tinha
chegado, devolvia lote de 1.

**Efeito, medido em producao (WINFUT, dt=2026-09-08)**: 34.525 row groups
para 519.764 linhas -- media de 15 linhas por row group. Cada row group
carrega seu proprio metadado/dicionario/estatisticas; ter milhares deles
para entregar poucas linhas cada e' overhead estrutural, nao volume de
dado. Leitura desse UM simbolo: 4h48min (90 KB/s efetivo) onde deveria
levar segundos.

**NAO e' bug de um dia so'.** A causa e' estrutural na cadencia de
escrita, presente desde o primeiro commit do projeto (2026-08-21).
Qualquer dia de producao com WINFUT tem o mesmo padrao. Antivirus,
disco, tarefa agendada, sessoes de teste do E1 -- todos investigados e
descartados nesta sessao antes de chegar na causa real.

**Diagnostico**: `pq.ParquetFile(caminho).metadata.num_row_groups` e'
instantaneo (le so' o rodape) e detecta isto sem ler o arquivo inteiro.
Um arquivo saudavel deveria ter poucas centenas a poucos milhares de
linhas por row group, nao dezenas.

**Correcao**: `bus.py` -- apos o primeiro item, `drain()` agora usa
`get(timeout=restante)` (o tempo QUE SOBRA do orcamento original), nao
mais `get_nowait()`. Uma fila continuamente ocupada agora acumula pelo
orcamento de tempo inteiro antes de devolver; uma fila quieta continua
devolvendo perto do timeout, sem espera extra.

**Nao afeta a latencia do EA**: `on_trade_extra` (o callback do
EABridge) roda direto no callback da DLL, ANTES do `bus.publish()` --
nunca passou pelo `drain()`. Confirmado no codigo antes de fechar esta
correcao.

**Efeito esperado em producao, a partir do proximo dia gravado com esta
versao**: arquivos de WINFUT/WDOFUT (e qualquer ativo de alta frequencia)
com muito menos row groups, leitura ordens de grandeza mais rapida.
Dados JA' gravados (todo dia ate' 2026-09-10) continuam com o padrao
antigo -- esta correcao muda a escrita dai pra frente, nao reescreve o
que ja existe.
