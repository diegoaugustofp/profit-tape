# Onde estamos e para onde dá para ir — 2026-09-21

> Substitui a versão de 2026-09-16. Sessão de 16 a 21/09: v2.98 → v3.27,
> 902 → 957 testes. O EA 123 rodou ao vivo pela primeira vez, o dry_run
> encontrou defeitos que o replay não pegava, e a pesquisa ganhou método
> novo (contraparte antes do padrão) e uma linha inteira de book.

## 1. O que existe hoje, em uma tela

| linha | estado |
|---|---|
| **EA 123 + gate volume baixo** | **7a FECHADO em 21/09**: pregão ao vivo limpo (37 barras, 6 candidatos, gate barrou 3), volumes das barras na escala certa (316 mil a 1,25 M) e sinal conferido no gráfico. Antes do E4 falta só infra |
| **Pesquisa de preço (M15)** | fechada; o único efeito vivo (123 volume baixo) atravessa a quebra de 2020 |
| **Pesquisa por contraparte** | rolagem, fechamento e defasagem descritos; opção sobre ação em captura |
| **Book (livro de ofertas)** | reconstrução validada; hipótese de nível defendido = **teste sem poder**; linha **estacionada** até o E4 |
| **Captura** | 9 ativos + 14 séries de opção; book agora gravado **sem duplicata**; record mantém a máquina acordada |

## 2. O que a sessão estabeleceu

**Sobre o mercado**
- **O WIN quebrou em 2020** e não voltou: a variância de log-volume caiu de
  1,24 para ~0,3. Histórico longo dá n, não homogeneidade.
- **O 123 em volume baixo sobrevive à quebra** nos dois instrumentos (WIN
  0,563 → 0,546; WDO 0,552 → 0,526; contraste abaixo em todos). Hipótese
  mais forte; veredito (inconclusivo pelo 0,56) inalterado.
- **Fluxo obrigatório de calendário e de horário não deixa marca no WIN**
  (rolagem na série contínua, ajuste/fechamento) — e o fim do pregão é o
  momento mais magro do dia; quem concentra é a abertura.
- **O WIN lidera a cesta** em 15 s (5 de 5 dias), sem valor operacional.
- **Book:** 16% das saídas de oferta são varredura por agressão; existem
  ~1,6 mil cadeias/dia de consumo seguido de reposição acima do embaralhado,
  mas as cadeias mais longas são de recotação — o comprimento não separa
  formador de nível defendido.

**Sobre o próprio sistema (defeitos achados e corrigidos)**
- EA armava sobre **fragmentos de barra** ao vivo (EA atrás da fila +
  relógio de parede). Agora quem fecha barra é o trade. Teste: 10.800 → 23.
- **Atraso real** do EA com fluxo: 0,03–6 s de média, 8 s de máximo — não
  bloqueia o E4 do 123.
- **Modern Standby** congelou o record 26 min em 18/09. O record agora pede
  ao Windows para não dormir.
- A **cura destruiu um pregão** (resíduo de 1 linha sobrescreveu 5,97 M).
  Agora recusa sobrescrever com menos da metade.
- O **offer book era gravado em dobro** (V1 e V2 disparando). Corrigido na
  captura; o histórico é desfeito na leitura.
- Nosso tape = aba **"negócios"** do Times & Trades (cada casamento); o
  Profit em "ordem original" agrega ~4×. Volume bate (fora RLP).

## 3. O que falta — em ordem

### A. Caminho crítico (decide dezembro) — prazo: fim de setembro

| # | falta | quem |
|---|---|---|
| 1 | Aplicar até a v3.27 com o record parado | operador |
| 2 | Próximo pregão (1º com a v3.28): `energia.mantendo_acordado` no arranque; as linhas `recorder.evento_de_dia_anterior` (mandar: dizem o que a DLL entrega); **37 barras** sem `dia_incompleto` (a das 18:15 fica aberta — é o certo); no `recorder.resumo`, `offer_book_chamadas` (`v1_suprimidas` ≈ `v2`) e `eventos_de_dia_anterior`; nenhuma pasta de ontem em `raw/trade/` | operador |
| 3 | ~~18/09~~ **FEITO**: o backfill preencheu o buraco (34–58 mil negócios por 10 min em 16:10–16:50, como os vizinhos) | — |
| 4 | Nobreak do ROTEADOR (a bateria do notebook segura a máquina, não a rede) e cabo. Em demo não bloqueiam o E4; bloqueiam a conta real | operador |
| 5 | **E4 COMEÇOU em 22/09** (1ª operação: venda 186.700, slippage 0, stop e alvo 1 s depois do fill — conferido no extrato do Profit). Próximo: **testar o cancelamento total** (procedimento no RUNBOOK_E4). Plano original: **E4 — pode começar amanhã (22/09) se o arranque passar** (ver `docs/RUNBOOK_E4.md`, seção 2: `energia.mantendo_acordado`, `ea.123.iniciado` do E4 com `dry_run=False` e semente válida, heartbeat com `corretora_pronta`). É conta **DEMO** — a trava é fixa no código —, então um problema custa uma operação mal medida, não capital. Rodar o E4 **junto com o 123 simulado**: mesmos sinais, a diferença entre os dois diários é o custo de execução. `--ea-ticker-ordem WINV26`, trocar para `WINZ26` na semana de 05/10 | operador |
| 6 | ~50 pregões de forward; slippage ≤ 6 pts | calendário |

### B. Pequenos, no código — FEITOS na v3.28
- Diário: o gate agora julga também os sinais bloqueados por posição, e o
  relatório mostra o custo do gate sobre TODOS os sinais.
- Record: o resíduo do dia anterior vai para `raw/_quarentena/` e é logado
  por inteiro (`recorder.evento_de_dia_anterior`) — **o log do próximo
  arranque é que vai dizer O QUE a DLL entrega na assinatura**.
- Book: inserções fora de ordem contadas por hora.

### C. Pesquisa — estacionada até o E4 começar
- **Opções de PETR4**: outubro capturado o mês inteiro (vence 16/10); OI
  colado no spot → **um nulo em outubro pesa contra**. Falta escrever a
  descrição do passo 1 (setembro já tem 18/09 capturado).
- **Book, próximo teste — o LADO**: formador cota os dois lados; defensor,
  um. Para cada cadeia de consumo, o mesmo agente tinha oferta do lado
  oposto? Depois: capturar o `atFullBook` (engenharia na captura).
- **Rolagem refeita** (par casado entre contratos): WIN vence 14/10 →
  assinar `WINV26` e `WINZ26` antes de ~07/10. **WDO vence no 1º dia útil
  do mês → a virada é nesta semana**; se quiser a amostra mais rápida,
  assinar `WDOV26` e `WDOX26` já.
- **Agente** (saldo acumulado e a sua virada) — depois do book.

## 4. Onde cada hipótese está (a taxonomia de fechamento)

| hipótese | estado |
|---|---|
| IFR2, ORB | **refutada** |
| véspera, rolagem v1 (série contínua) | **teste sem poder** |
| iceberg no tape | **dado insuficiente** (tape só tem execução; agente = corretora) |
| nível defendido no book | **teste sem poder** (controle não separa formador) |
| opção sobre índice | descartada com razão medida |
| opção sobre ação | **em captura** |
| 123 volume baixo | **viva**, no forward |

## 5. As duas perguntas de dezembro

1. **Existe EA que opere com retorno?** Um candidato com efeito pequeno,
   real e que atravessou uma mudança estrutural. O forward mede se a
   execução cabe dentro dele.
2. **A estrutura (ProfitDLL) é a certa?** Esta sessão respondeu parte: a
   DLL deu o que o gráfico não dá (agente por negócio, ordem de chegada
   entre ativos, livro reconstruível evento a evento) — e cobrou caro em
   engenharia (book duplicado, standby, fila). O forward responde o resto.
