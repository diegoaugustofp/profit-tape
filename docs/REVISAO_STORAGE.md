# Revisao do modulo de storage (2026-08-22, pedido do operador)

## Motivo

Tres incidentes de corrupcao/perda em sequencia, todos com a mesma anatomia:
o sistema fazia a coisa errada EM SILENCIO e so' contava no fim (ou nunca).

1. Footers nao-duraveis no G: USB (fsync ausente; depois fsync com O_RDONLY
   que falha no Windows) — 96 arquivos iliegiveis descobertos so' na auditoria.
2. Row groups internamente corrompidos (ZSTD) passando pelo filtro de footer.
3. Caminho relativo-a-unidade ('\data\raw') mandando capturas inteiras para o
   drive errado — G: numa rodada, C:\data\raw noutra — sem nenhum erro.

A licao transversal: em pipeline de dado irrecuperavel, silencio e' o modo de
falha mais caro. Toda promocao de confianca precisa ser VERIFICADA, e todo
destino precisa ser ANUNCIADO.

## Invariantes garantidos a partir da v0.34

INV1 — ".parquet" implica "footer verificado por releitura do disco".
  O rename .inprogress -> .parquet so' acontece apos fsync + releitura dos
  magic bytes finais DIRETO do disco. Falhou a verificacao: o arquivo fica
  .inprogress (estruturalmente nao-confiavel, visivel em qualquer listagem),
  sink.VERIFICACAO_FALHOU e' logado NA HORA, e a falha e' contada no resumo.
  No G:, isso teria gritado no primeiro arquivo, nao 96 depois.

INV2 — close()/close_idle() so' devolvem arquivos realmente promovidos.
  destino.exists() e' a verdade final. A API nao repete a mentira que o
  invariante 1 matou no disco.

INV3 — destino ambiguo e' recusado, nao avisado.
  storage.raiz relativo-a-unidade no Windows = ValueError fatal no load do
  config, com instrucao de correcao. raiz e' resolvida para absoluto NO LOAD
  (congelada contra mudancas de CWD).

INV4 — destino anunciado na primeira linha.
  record e backfill logam raiz resolvida + GB livres antes de qualquer outra
  coisa (recorder.destino / backfill_dia.destino).

INV5 — resumo sempre reporta a verificacao.
  arquivos_verificados e falhas_verificacao em todo resumo; backfill com
  falha de verificacao retorna exit code 4.

INV6 (pre-existente) — conservacao: eventos_recebidos == linhas_escritas +
  descartados_contados, em todo resumo.

## Ferramentas de auditoria independentes do pipeline

- `quarentena RAIZ`            : varre footers (rapido)
- `quarentena RAIZ --profundo` : descomprime tudo (pega ZSTD interno)
- `inspect` e `curate`         : leitura fragmento-a-fragmento; arquivo podre
                                 e' PULADO E NOMEADO, nunca derruba a auditoria

## O que NAO esta garantido (honestidade de escopo)

- Corrupcao por hardware APOS a verificacao (disco que apodrece dado ja'
  verificado, como o G: demonstrou fazer) e' detectavel apenas por re-auditoria
  (quarentena periodica), nao prevenivel por software. Disco assim nao serve
  para dado primario — no maximo backup verificado apos cada copia.
- A verificacao rele o footer, nao o arquivo inteiro; corrupcao interna no
  momento da escrita (nao do fechamento) e' pega pela quarentena --profundo,
  nao pelo fechamento. Verificacao integral no close custaria releitura total
  de cada arquivo (inviavel no hot path).
