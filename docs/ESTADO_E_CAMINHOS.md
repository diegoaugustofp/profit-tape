# Onde estamos e para onde dá para ir — 2026-09-15 (noite)

> Substitui a versão de 2026-09-14. A anterior fechava com "a linha de
> preço resolveu-se em dois dias"; esta fecha com a linha inteira
> percorrida em dois instrumentos, um efeito real encontrado, e o EA
> pronto para levá-lo ao forward.

## 1. O que existe hoje, em uma tela

| linha | o que é | estado |
|---|---|---|
| **Fluxo** (tape) | a aposta original: absorção, agressão, `z_agf` sobre barras de volume | absorção fechada como formulada; Rota B em forward montado, **nunca disparou ordem real**; DeepScalper fase 2 até n=50; **tape acumulando desde 24/07** |
| **Preço** (M15) | nasceu 13/09 para ter EA validável hoje | **percorrida**: 3 setups × 2 futuros + 2 fichas de volume. Um efeito real e pequeno encontrado (123 em volume baixo) |
| **Execução** | escada E0–E5 + F5 do 123 | E0–E3, **E2b** e **E5.5** fechados; F5 do 123 com código completo (7 passos + gate); falta pregão |

## 2. O que a linha de preço concluiu

**Nulo, em dez anos, nos dois futuros:** IFR2 (2 trials no WIN, 1 no WDO),
ORB (WIN e WDO). Categoria arbitrada — é a conclusão mais sólida da linha.

**Pequeno e real:** 123 no WIN, p1 = 0,5285 [0,515; 0,542] em 5.444, onze
de doze anos acima de 0,50. Não replicou no WDO (0,514, IC toca 0,50).

**O achado da sessão — 123 em volume BAIXO.** A ficha 9 testou o oposto
(volume alto) e deu nulo; o complemento, que era estrato reportado, deu
0,552 [0,535; 0,569] no WIN e **separou dentro dos quartis de D** (não é
só tamanho). Como a hipótese foi gerada ali, o WIN ficou queimado; a
ficha 12 foi declarada e testada no **WDO**, onde nenhum teste de volume
tinha tocado: **0,534 [0,516; 0,552]** em 2.863, contraste 0,5005, onze
de doze anos, mesma forma por quartil, P&L com IC inteiro acima de zero.

Gerado num instrumento, confirmado no outro, com direção, magnitude e
forma iguais. **Pelo critério (0,56) é inconclusivo** — e o critério não
muda: 0,53–0,55 é pequeno demais para ser um EA por si. É suficiente
para ser o **gate do 123 no forward**, que era o caminho declarado no dia 1
e agora tem evidência atrás em vez de uma porta vazia.

**O que mais ficou provado nesta sessão:** o `QuantityVol` do gráfico é a
soma das quantidades do tape (28/08 e 11/09, depois do backfill: 35/35
idênticos) — o gate ao vivo usa `vol_total` direto; e um dia com queda de
conexão vira um dia perfeito com um comando de `backfill`.

## 3. O que falta — em ordem

### A. O forward do 123 (o único caminho com decisão tomada)

Código completo. Dois EAs prontos, o operador escolhe:
`config/ea_123.yaml` (sem gate) e `config/ea_123_volume_baixo.yaml`
(ficha 12, `ea_123_vb`) — recomendação: o com gate.

| # | falta | quem |
|---|---|---|
| 7a | **um pregão em dry_run**: ligar antes das 09:00, conferir 2–3 candidatos no gráfico, `perfil_volume` no arranque, JSONL no fim | operador |
| — | conferir `SendCancelOrders` ao vivo (usada na reconciliação; declarada, não testada) | operador |
| 7b | **E4**: `dry_run: false` + `--login-completo --ea-ticker-ordem`; E5.6 fecha junto | operador |
| — | o forward em si: slippage ≤ 6 pts, n = 100, ~50 pregões | calendário |

**Pré-requisito de infra (decidido 15/09):** cabo em vez de Wi-Fi e
nobreak na máquina e no roteador, antes do E4 real. Pesquisa se cura com
backfill (30 dias); execução não. VPS só com dinheiro real — muda a
latência, que é justamente o que o forward mede.

**Rotina diária que passa a valer:** `backfill` do dia anterior + cura,
no mesmo Agendador que sobe o record. Mantém parquet, perfil de volume e
semente sempre completos, e faz `gate_indefinidos` significar mercado,
não infra.

### B. Fichas declaradas, na ordem, sem data

1. **Gap de abertura** (`EAS_DE_PRECO.md` 10) — informação da noite.
2. **Máx/mín da véspera** (11) — estrutura diária.
3. **Ações** (8.2) — lista fechada (PETR4, VALE3, ITUB4, BBDC4, BBAS3),
   M15, os dois lados (day trade não precisa de aluguel), zeragem antes
   do leilão (16:45), custo em % — e a expectativa mais baixa das três,
   depois do que os futuros mostraram. Quatro das cinco já têm tape;
   bolsa "B" exige refazer a E2.

### C. Andando sozinho / backlog

- Tape acumula; DeepScalper espera n = 50; Rota B espera o primeiro sinal.
- `RequestSerieHistory` de barras (substitui o parquet da semente e
  resolve o dia incompleto).
- Momentum como hipótese nova; `FEATURES.md` e a doc do fluxo atrasadas.
- **Queimado:** 2015–2026 do WIN para IFR2, ORB, 123 e 123gate; do WDO
  para IFR2, ORB, 123 e 123gate_baixo. Variante dessas famílias precisa
  de amostra que nenhum desses testes tocou.

## 4. O que eu faria, e por quê

Um pregão em dry_run com o `ea_123_vb`, olhando barras e ordens — é o
único passo que ainda pode revelar defeito de fórmula sem custar
amostra. Depois cabo e nobreak, depois E4.

E uma lembrança do que o forward é: um teste de **execução** e um
gerador de amostra, com um efeito pequeno e real por baixo. Ele não vai
confirmar 0,53 (n exigiria anos). Se o slippage ficar ≤ 6 pts, o 123 com
gate vira candidato a F6; se não, o efeito existe e não paga a execução —
e isso também é uma resposta.
