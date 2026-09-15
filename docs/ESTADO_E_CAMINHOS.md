# Onde estamos e para onde dá para ir — 2026-09-14

> Substitui a versão de 2026-09-04. O que ela dizia (absorção não
> sobreviveu como formulada; momentum como hipótese nova; acumular tape)
> continua verdadeiro e está registrado no `RESEARCH_PLANO.md`. Este
> documento é o estado DEPOIS de duas semanas em que a infraestrutura
> fechou e uma linha inteira de pesquisa nasceu, correu e se resolveu.

## 1. O que existe hoje, em uma tela

**Duas linhas de pesquisa**, uma infraestrutura.

| linha | o que é | estado |
|---|---|---|
| **Fluxo** (tape) | a aposta original: absorção, agressão, `z_agf` sobre barras de volume | absorção fechada como formulada; `z_agf_3` + Rota B em forward demo montado, **nunca disparou ordem real**; DeepScalper fase 2 em forward, placar fechado até n=50; **tape acumulando desde 24/07** (o recurso escasso) |
| **Preço** (M15) | nasceu em 13/09 para ter EA validável HOJE, com 10 anos de candle | três candidatos, três respostas em dois dias: IFR2 **nulo** (2 trials), ORB **nulo** (10 anos), **123 real e pequeno** (p1 0,5285, IC exclui 0,50, +6 pts líquidos/op) — vai a F5 como portador |

**Infraestrutura (escada E0–E5):** E0–E3 fechados; **E2b fechado hoje**
(stop, limitada, cancelamento, OCO pelo EA — tudo na demo, de primeira);
E4 montado, nunca viu sinal real; **E5.5 validado ao vivo hoje** (2 EAs,
5 h, 47,6 M linhas, inclusão a quente, `descartados=0`); E5.6 pendente
(2 EAs com ordens reais).

## 2. O que a linha de preço ensinou (e por que valeu)

1. **O pipeline reprova em uma noite o que o forward levaria anos.** Do
   funil ao veredito, sobre 923 → 2.685 pregões, sem gastar um dia de
   calendário. É a ferramenta que fica para qualquer hipótese futura.
2. **O que existe de graça em preço no WIN M15 já foi arbitrado.** IFR2 e
   ORB, os dois setups públicos mais conhecidos, são nulos a custo zero
   em dez anos. Não negativos — nulos.
3. **O 123 é diferente**: IC exclui 0,50 em 5.444 operações, onze anos de
   doze acima de 0,50, compra e venda iguais. Mas +6 pts líquidos por
   operação, com o IC do P&L tocando zero. É uma borda que existe e não
   paga a execução sozinha — o caso exato para o qual a porta de volume
   foi declarada no dia 1.
4. **Três erros meus, corrigidos e registrados:** verificador com bug de
   aquecimento (dizia NÃO BATE com mediana 0,0); capital usado para
   encolher D duas vezes, contra a decisão 4.9; e a expectativa
   "provavelmente nulo" para o 123. Os três estão no `EAS_DE_PRECO.md`.

## 3. O que falta — em ordem

### A. Levar o 123 a F5 (o caminho decidido)

Ficha de forward em `EAS_DE_PRECO.md` 5.4. O forward **não** re‑verifica
o p1 (seis anos a 2 op/dia); mede **execução** — slippage ≤ 6 pts em
n = 100, ~50 pregões — e grava, por sinal, as features de fluxo da barra
do gatilho: a amostra da porta de volume, F1 do gate.

Passos, cada um uma entrega:

| # | passo | estado |
|---|---|---|
| 1 | barra de TEMPO no EA (`ConstrutorDeBarraDeTempo`, M15 alinhado à bolsa) | **FECHADO (v2.74)**: 69/69 barras identicas ao grafico no dado real; dobra no fim de sessao e barra parcial viraram regra |
| 2 | semente da MME80 (parquet do gráfico + ponte pelo tape; sem semente não arma) | **FECHADO (v2.75)**: 28/08 dif 0,0 em 38 barras; 11/09 −15 pts decaindo (3 closes sem tape) → regra do dia incompleto |
| 3 | `SinalPreco123` sobre a barra de tempo, fórmula importada do research | **FECHADO (v2.76)**: equivalência EA × research testada |
| 3b | E2b — stop / limitada / cancel / OCO na demo | **FECHADO 14/09** |
| 4 | ciclo de ordens do 123 (stop de entrada → cancela no fim de t+1; fill → stop + limitada; um executa → cancela o outro), slippage e latência por ordem | **FECHADO (v2.77)** |
| 4b | reconciliação de ORDENS ao reconectar (cancela todas, confere posição, re‑arma ou zera) | **entregue (v2.78)**; `SendCancelOrders` a conferir ao vivo |
| 5 | `GateDeFluxo` / `SemFiltro`, `filtro_fluxo: null` | **entregue (v2.78)** |
| 6 | registro do sinal com features de fluxo (F1 do gate) | **entregue (v2.78)**: JSONL carimbado por operação |
| 7 | `ea_123.yaml` na esteira exclusiva; um pregão em dry_run com barras olhadas; depois E4 real | **código entregue (v2.78)**; falta o pregão em dry_run (7a) e o E4 (7b) |

Depois do passo 7 o 123 é o **primeiro EA com sinal real** a atravessar a
escada, e E5.6 fecha junto (dois EAs com ordens reais: 123 no WIN, Rota B
ou `venda_apenas` no outro ticker).

### B. O que continua andando sozinho

- **Tape acumula** todo pregão (`record`). É o insumo da porta de volume
  e da linha de fluxo. Nada a fazer além de manter o `record` de pé.
- **DeepScalper fase 2**: `fase2-score` nos dias pendentes até n = 50.
- **z_agf_3 / Rota B**: espera um sinal real disparar no forward.

### B2. Outros instrumentos (declarado 15/09, `EAS_DE_PRECO.md` 8)

- **WDO**: funis feitos nos três dumps (15/09); **três fichas congeladas**
  (`EAS_DE_PRECO.md` 8.1b), sequência declarada. Falta rodar os 15
  comandos de teste com `--instrumento wdo`.
- **Ações**: lista fechada (PETR4, VALE3, ITUB4, BBDC4, BBAS3),
  registrada, não agora — sem tape, bolsa "B" exige refazer a E2.

### C. O que fica no backlog, declarado, sem ação

- Porta de volume do 123 (ficha própria quando o forward tiver n de
  sinais gravados; a observação do operador nas por tempo do ORB está
  registrada em 4.5).
- `RequestSerieHistory` de barras (substitui o parquet da semente).
- Momentum como hipótese nova (desde 04/09, sem amostra virgem de fluxo).
- 2015–2022 e 2023–2026 estão QUEIMADOS para as famílias IFR2, ORB e 123.
  Qualquer variante delas precisa de amostra nova.

## 4. O que eu faria, e por quê

Seguir a ordem A, sem pular o passo 1 para "chegar logo" no 4. A barra
de tempo é o único pedaço que o EA de fluxo não tem, e é onde um defeito
de alinhamento (fronteira de 15 min no horário da bolsa, barra sem
trade) custaria semanas de forward. Um passo por entrega, cada um com o
seu teste, é o que permitiu os 815 verdes de hoje.

E lembrar o que o forward do 123 é: um teste de execução e um gerador de
amostra, com um sinal pequeno e real por baixo. Se o slippage ficar ≤ 6
pts, o 123 puro vira candidato a F6 com o gate; se não, ele só vive com
o gate — e o gate só nasce da amostra que ele mesmo vai gravar. Os dois
caminhos passam pelo mesmo lugar.
