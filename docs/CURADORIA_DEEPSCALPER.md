# Curadoria de referencias — DeepScalper e RL intradiario (fechada 2026-09-07)

Registro do que foi lido, o que ficou e o que foi descartado, com o
motivo. Existe para **nao voltar** em material ja' avaliado. Antes de
propor uma fonte nova sobre RL/fluxo/scalping, confira aqui.

O pre-registro derivado desta curadoria esta em
`docs/RESEARCH_PLANO.md` → "PRE-REGISTRO: DeepScalper — Fase 0 (desenho)
(2026-09-07)".

## Regra de triagem que emergiu

Blog de plataforma, site de afiliado de corretora e guia "para
iniciantes" **nao renderam nada em 6 de 6 casos**. Filtro inicial: se a
fonte nao tem uma formula, um limiar, um dado ou um teste, nao abre.

---

## APROVEITADO

### DeepScalper — Sun et al., CIKM 2022 (arXiv 2201.09058)
**Arquitetura de referencia, evidencia fraca.** Quatro pecas: dueling
Q-network com action branching (preco x quantidade), hindsight bonus no
reward (peso `w` sobre o retorno de segurar `h` barras adiante),
micro-encoder LSTM sobre book de 5 niveis + estado privado, tarefa
auxiliar de prever volatilidade. Na ablacao do paper a peca que mais
rende e' o hindsight bonus.

Problemas de rigor (todos pesam):
- Teste de 4 meses (jan-abr/2020, crash da COVID) nos indices; regime
  unico. Momentum deu -27%, reversao +8% no mesmo periodo.
- Grid search em `h`, `w`, `eta` e tamanhos de rede, com curvas de
  sensibilidade plotadas em retorno do periodo de TESTE. Sem validacao.
- TR 12,74 +- 4,65 com 5 seeds; "p < 0,01 por Wilcoxon" e' impossivel
  com 5 pares (minimo 0,0625) — devem ter agregado dias, nao dito.
- Tabela de ablacao nao bate com a tabela principal (6,97% vs 4,79%).
- Execucao idealizada: ordem limitada sem modelo de fill/fila, custo
  2,3e-5, alavancagem fixa 5x, uma decisao por minuto.
- "Generalizacao" TF02→T02 sao vencimentos adjacentes do mesmo contrato.
- Sem codigo publico (ver TradeMaster abaixo).

### DeepLOB — Zhang, Zohren, Roberts 2019 (arXiv 1808.03668; github zcakhaa)
Referencia para prever movimento a partir do book (CNN por nivel +
LSTM). Codigo publico. Uso: baseline supervisionado na Fase 2 e
alternativa ao micro-encoder.

### iRDPG — Liu et al., AAAI 2020 ("Adaptive Quantitative Trading: An Imitative DRL Approach")
Mesmo problema (futuros IF/IC, minuto). Ideia transferivel: imitacao de
regra classica (Dual Thrust) para reduzir a fome de dado do RL.
**Correcao de link**: no caderno estava apontando para 2011.09607, que
e' o FinRL.

### EarnHFT — Qin et al., AAAI 2024 (github TradeMaster-NTU/EarnHFT)
Duas ideias: "Q-teacher" por programacao dinamica com preco futuro
(acelera treino com pouco dado) e execucao *order-taker* sobre o book
(atravessa niveis, paga spread) — e' o modelo de fill conservador da
Fase 1. Ressalva: dado de cripto, book fino.

## REFERENCIA PARCIAL

### TradeMaster (github TradeMaster-NTU/TradeMaster, commit 1747cc1, 2025-06-04)
Codigo inspecionado em 2026-09-07. **O "DeepScalper" do TradeMaster e'
DeepScalper so' no nome.** O que existe sob esse nome
(`configs/_base_/agents/algorithmic_trading/deepscalper.py` →
`AlgorithmicTradingDQN` + `QNet`):

| Componente do paper              | No TradeMaster                              |
|----------------------------------|---------------------------------------------|
| Dueling + action branching       | NAO. DQN simples, MLP 64→32, 3 acoes         |
| Micro-encoder LSTM sobre book    | NAO. Sem LOB. OHLCV+11 ind. x 5 barras, sem normalizar |
| Hindsight bonus                  | SIM (`future_weights=0.2`, `forward_num_day=5`), indexacao confusa |
| Auxiliar de volatilidade         | NAO. Env calcula e devolve em `info`; agente ignora |
| Replay priorizado                | NAO. Uniforme                               |
| Custo no reward                  | NAO. So' desconta do caixa; girar e' gratis para o agente |
| Dado                             | DIARIO (BTC, FX). Nao intradiario           |

Consequencia: **nao existe implementacao publica do DeepScalper
completo.** BDQ, micro-encoder e auxiliar tem de ser escritos do zero.
Qualquer resultado de terceiros "com DeepScalper via TradeMaster" e'
resultado de DQN simples.

O que vale no repo: modulo `high_frequency_trading` (HFT_DDQN, precursor
do EarnHFT) — book de 5 niveis, execucao atravessando niveis, mascara de
acoes pela profundidade, professor por DP na loss. Ressalvas: posicao em
`[0, max]` (**long-only**, invalida para WIN sem reescrita) e cripto em
segundos. Engenharia: registry estilo mmcv, Python 3.9, `gym` antigo,
um seed por padrao. Nao e' base para construir; e' codigo para ler.

## ESTACIONADO (ideia boa, contexto errado)

- **FinPILOT** (arXiv 2605.12653, mai/2026): previsor XGBoost como
  modelo de mundo para ajustar a politica na inferencia. Portfolio
  diario (DJ30). So' numa fase muito posterior.
- **FinRL** (arXiv 2011.09607): ferramental para acoes diarias. O
  TradeMaster cobre o mesmo papel mais perto do nosso caso.

## DESCARTADO — nao reabrir

| Fonte | Motivo |
|---|---|
| OrderflowHQ — absorcao/desequilibrio/divergencia de delta | Blog de marketing (Vtrender). Sem formula, limiar, dado ou teste. So' vocabulario: "iniciativa vs responsiva". `imbalance` do post **ja' existe** em `docs/FEATURES.md`. Unica candidata nova: divergencia preco x delta acumulado — se algum dia for proposta, passa pela triagem de redundancia (7.2) antes de qualquer trial. |
| OrderflowHQ — compradores/vendedores agressivos | Redundante com o anterior. |
| OrderflowHQ — melhores mercados para fluxo | ES/NQ/CL/GC para quem escolhe mercado. Irrelevante. |
| DayTrading.com — PDF "Scalping Trading" | PDF sem texto extraivel; e' a impressao da pagina /scalping de um site de afiliado de corretoras (operado por "Boleyn SEO Limited"). Guia de iniciante, forex, sem conteudo tecnico. |
| World Bank DataBank | Indicadores macro ANUAIS por pais. E' a fonte da citacao "90 trilhoes" da introducao do DeepScalper. Nada intradiario. Contexto macro real (IPCA, Copom, payroll) viria de calendario economico com timestamp, nao daqui. |
| howtotrade.com — scalping de 1 minuto | Triple EMA + estocastico, site de afiliado. Sem evidencia. |
| Nelogica — Setup 9.1 (Larry Williams) | Regra trivial de MME9. Baselines melhores ja' existem (momentum/reversao do proprio paper). |
| arXiv 2602.17098 — DRL vs MVO (Sood et al., fev/2026) | Alocacao de portfolio diaria, PPO long-only. Nada intradiario. |
| Peaks2Tails — "Can deep learning enhance your quant strategy" | Blog de marketing, sem conteudo tecnico. |

## Referencias que NAO entraram e valeriam se o tema for fluxo quantificado

Nao avaliadas nesta curadoria; anotadas para quando houver pergunta que
precise delas (e so' entao):
- Easley, Lopez de Prado, O'Hara — VPIN / fluxo toxico.
- Cont, Kukanov, Stoikov (2014) — order flow imbalance e impacto.
- Bouchaud, Bonart, Donier, Gould — *Trades, Quotes and Prices*.
