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
