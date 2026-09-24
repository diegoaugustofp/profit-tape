# Ficha — z_agf_3 (venda apenas + Rota B)

> **Status:** vivo — **Revisado:** 2026-09-24 — **Assunto:** EA de fluxo sobre a agressão do agente 3, lado de venda, saída por tempo (3 barras de volume) com stop/alvo da Rota B; roda em dry_run dentro do record; F5 montado.

## Identidade

| | |
|---|---|
| Linha | fluxo (tape), barras de volume |
| Instrumento | WINFUT |
| Config | `config/ea_venda_rota_b.yaml` (`dry_run: true`; o E4 liga `dry_run=false` via `--ea-ticker-ordem`) |
| Código | `ea/sinal.py`, `ea/decisao.py`, `ea/risco.py`, `ea/service.py`; features em `features/` |
| NTSL | nenhum (o indicador `absorcao_dir` é outra hipótese, já reprovada) |
| Nome no registro de EAs | `z_agf_3` |

## Fase e estado

**F5 — forward demo MONTADO (v2.47), sem sinal real ter virado ordem.**
Roda em dry_run dentro do record desde agosto; decisões logadas.
Pré-requisito 5 da escada (decisões logadas x previsão do research)
declarado satisfeito pelo operador em 2026-09-11. O E4 que começou em
22/09 é o do **123**, não deste EA (decisão 5.4 de `EAS_DE_PRECO.md`:
o 123 é o portador da estrutura multi-EA).

## Mecanismo em uma frase

Quando o agente 3 (varejo, XP) agride comprando muito acima do seu
normal recente, o mercado corrige o excesso nas barras seguintes —
vende-se contra o fluxo de varejo e sai-se três barras depois.

## Regras (o suficiente para reimplementar)

- Barra de volume de 120.000 (relógio de agressão, `FEATURES.md`).
- `z_agf_3` = z-score, janela de 50 barras, de `agf_3` = (comprado −
  vendido pelo agente 3) / volume de agressão da barra.
- Sinal: `z_agf_3 ≥ 1,4`, direção contrária ao fluxo (`contrarian`).
- **Lado permitido: só venda** (`lado_permitido: venda`). A abertura de
  compra é suprimida; ZERAR nunca é suprimido.
- Saída por tempo: 3 barras (`horizonte: 3`) — Rota A, a que foi validada.
- Rota B sobreposta: `stop_rota_b_pontos: 100`, `alvo_pontos: 120`
  (checados no **fechamento** da barra, não tick a tick — ver
  "Divergência a resolver").
- Risco: 1 contrato, capital R$5.000, 2% → stop catastrófico 500 pts;
  circuit breaker de 3 perdas consecutivas.
- Custo estimado: 11 pts ida e volta.

## Pré-registros (na ordem em que aconteceram)

### Sinal — IC e quintis (2026-08-23 a 26)

Não há ficha de seis linhas: o sinal foi validado no regime anterior ao
das fichas, pelo IC (t = −3,95, consistência 10/10 folds) e pela tabela
de quintis com custo real. Spread líquido Q5−Q1: **h=3 +18,14 pts**,
h=10 +52,55; h=1 morre no custo. Decisão: qualquer EA sobre `z_agf_3`
usa h=3 ou h=10, nunca h=1. (`RESEARCH_PLANO.md`, "Segunda rodada de
quintis".)

### Restrição de direção — venda apenas (2026-08-27, `entregue-v0.85`)

Motivação: MAE (300 triggers) e replay (163 ops) mostraram compra
negativa e venda positiva. Critério congelado antes: favorável se P&L
total da variante venda > baseline **e** razão ganho/perda ≥ baseline.

| | baseline (ambos) | venda apenas |
|---|---|---|
| operações | 163 | 142 |
| P&L total | −533 | **+3.228** |
| acerto | 47,2% | 52,8% |
| razão ganho/perda | 1,080 | 1,128 |

**FAVORÁVEL** pelo critério. Leitura registrada antes e mantida: não é
evidência nova — é engenharia sobre a mesma amostra que revelou a
assimetria (não consome trial).

### Rota B — par congelado (2026-08-27; overlay em `risco.py` na `entregue-v0.96`)

Princípio pré-registrado: stop = mediana do MAE_close da venda, alvo =
mediana do MFE_close, arredondados antes de olhar resultado econômico.
n = 336 triggers: MAE 95 → **stop 100**; MFE **120**. Payoff 1,2:1,
aceito conscientemente pelo operador (caminho 1 dos três registrados).

### "Existe reversão condicional?" — pré-registro 3 (2026-08-30d → 30i)

Separou stop como limite de perda (a) de stop como detector de reversão
(b); testou só (b) com grade de X fixada. 25 pregões, 178 sinais de
venda, limiar deflacionado 1,96: |t| máximo 0,76, todos os IC contendo
zero. **CONTRA: o stop não detecta reversão.** Só se justificaria como
(a), com custo em expectativa a medir em pré-registro separado.

### Drawdown — decomposição (2026-08-31)

A premissa "Calmar 0,23" era artefato de dado dobrado. Sobre `curated`:
99 ops, +6.356 pts, drawdown máximo 1.556 pts (R$311, 6,2%), Calmar
4,08. **"Stop como controle de drawdown" encerrado como pergunta.**
Achado colateral: o stop catastrófico de 500 pts deixou passar −590,
−615, −565 porque checa `excursao_contra` só no close da barra —
"Rota B redesign: checagem contínua" ficou como sessão de desenho
pendente.

## Veredito

Sinal com borda validada (IC + quintis), lado de venda, saída por
tempo. Forward demo montado, execução real ainda não medida.

## Divergência a resolver (registrada 2026-09-24, não decidida)

O YAML em uso ainda carrega `alvo_pontos: 120` e `stop_rota_b_pontos:
100`, enquanto a pesquisa fechou que (i) o alvo foi "descartado como
conceito para z_agf_3" (2026-08-29, `HISTORICO_DE_SESSOES.md`), (ii) o
stop não detecta reversão (30/08) e (iii) drawdown não é problema
(31/08). Não há registro de o YAML ter sido revisto depois. Decidir se
o EA em forward roda Rota A pura (como validado) ou Rota B (como está)
é decisão do operador — o que não pode é o forward medir uma coisa e a
ficha descrever outra.

## Próximo passo

1. Operador decide a divergência acima; se mudar o YAML, carimbo novo.
2. E5.6: segundo EA com ordens reais em modo exclusivo com o 123 —
   este é o candidato desenhado (`EAS_DE_PRECO.md` 8.1c).
3. Rota B com checagem contínua (tick a tick) é sessão de desenho, não
   patch — pendente desde 31/08.

## Onde está a discussão longa

- `RESEARCH_PLANO.md`: quintis (2026-08-26); "Restrição de direção"
  (08-27); "Rota B: par CONGELADO" e "DECISÃO: par empírico aceito"
  (08-27); "PRÉ-REGISTRO 3 DA ROTA B" e "RESULTADO DA ROTA B: CONTRA"
  (08-30); "DECOMPOSIÇÃO RODOU" (08-31).
- `EA_ARQUITETURA.md` §1 e "Rota A escolhida pelo operador".
