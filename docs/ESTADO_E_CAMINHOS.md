# Onde estamos e para onde dá para ir — 2026-09-16 (noite)

> Substitui a versão de 2026-09-15. Aquela fechava com a linha de preço
> percorrida em dois instrumentos; esta fecha com a linha inteira
> resolvida, um efeito replicado que atravessa uma quebra de regime, o
> diário de sinais pronto, e o método de gerar hipótese revisto.

## 1. O que existe hoje, em uma tela

| linha | estado |
|---|---|
| **Preço** (M15) | **percorrida e fechada.** 7 famílias × 2 futuros × 10 anos. Um efeito vivo: 123 em volume baixo |
| **Fluxo** (tape) | absorção fechada em duas formas; tape acumulando desde 24/07 (2 meses). É a aposta original, ainda sem resposta |
| **Execução** | E0–E3, E2b, E5.5 fechados. F5 do 123 com código completo (7 passos + gate + diário). Falta pregão |

## 2. O que sabemos, e com que confiança

**Nulo, em dez anos, nos dois futuros:** IFR2 (2 trials), ORB, gap de
abertura (inconclusivo sem padrão). Véspera fechou sem p1 — o estimador
binário não serve para entrada por rompimento com D pequeno.

**O efeito vivo — 123 em volume baixo.** Quatro medições independentes:

| | até 2019 | de 2020 |
|---|---|---|
| WIN | 0,563 [0,535; 0,590] | 0,546 [0,524; 0,567] |
| WDO | 0,552 [0,520; 0,584] | 0,526 [0,503; 0,548] |

Contraste (volume alto) abaixo em todas. Atravessa a quebra de
microestrutura de 2020. **Inconclusivo pelo critério de 0,56** — e o
critério não muda —, mas é a única hipótese com mecanismo plausível,
replicação em dois instrumentos e sobrevivência a uma mudança estrutural.

**Dois achados de método, que valem mais que qualquer ficha:**
1. **O WIN quebrou em 2020.** A variância de log‑volume caiu de 1,24
   para ~0,3 e não voltou. Histórico longo dá n, não homogeneidade.
2. **O gráfico proxia a absorção (decil 0,90) e o grosso do imbalance
   (R² 0,77), mas erra o extremo direcional (decil 0,43).** O que
   justifica a DLL é o extremo, os agentes, o book e a execução.

## 3. O que falta — em ordem

### A. Forward do 123 com gate (o que decide dezembro)

| # | falta | quem |
|---|---|---|
| 7a | **pregão em dry_run** com `ea_123_vb`, ligado antes das 09:00; no fim, `profit-tape diario data/forward/ea_123_vb --ea ea_123_vb` | operador |
| — | `SendCancelOrders` ao vivo (única peça da reconciliação nunca testada) | operador |
| — | cabo em vez de Wi‑Fi + nobreak (máquina e roteador) | operador |
| 7b | **E4** (`dry_run: false`); E5.6 fecha junto | operador |
| — | ~50 pregões: slippage ≤ 6 pts, n = 100 | calendário |

**Prazo:** o E4 precisa começar até o fim de setembro, ou o forward não
fecha dentro da janela de dezembro — e "não deu tempo" é pior desfecho
que "não tem borda".

### B. Enquanto o tape acumula (é de graça, não gasta pregão)

Os cinco pontos sobre geração de hipótese estão no `RESEARCH_PLANO.md` e
valem a partir da próxima ficha — com destaque para o campo
**CONTRAPARTE** obrigatório antes de HIPÓTESE, e para a triagem por
regime. O caminho mais valioso: **comportamento de agente** (quem
aparece antes de quê), que exige tape e é onde o dado é raro.

### C. Andando sozinho / backlog

- Tape acumula; **rotina nova:** backfill + cura do dia anterior toda
  manhã, no mesmo Agendador que sobe o record.
- DeepScalper espera n = 50; Rota B espera o primeiro sinal real.
- `RequestSerieHistory` de barras; `FEATURES.md` atrasado.
- **Queimado:** WIN 2015–2026 para IFR2, ORB, 123, 123gate, vespera e
  gap; WDO para IFR2, ORB, 123 e 123gate_baixo.

## 4. As duas perguntas de dezembro

1. **Existe EA que opere com retorno?** Hoje: um candidato com efeito
   pequeno e real. O forward diz se a execução cabe dentro dele.
2. **A estrutura (ProfitDLL) é a certa, ou NTSL faria o mesmo?** O
   forward responde isto também, medindo o que a DLL custa em slippage
   para fazer o que o NTSL faria barato. E a medição de 16/09 já disse o
   que sobra de exclusivo para ela: extremo direcional, agentes, book,
   execução automática.
