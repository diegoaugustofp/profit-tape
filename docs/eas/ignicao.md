# EA de ignição do WIN — fast-track

> **Status:** F5 — forward em **dry_run** ligado a partir de 2026-09-28 — **Criado:** 2026-09-25 (v3.68) — **Código:** `ea/config_ignicao.py`, `ea/sinal_ignicao.py`, `ea/service_ignicao.py`, `config/ea_ignicao.yaml` — **Estudo:** `research/ignicao.py` (v3.66–v3.67)

## Mecanismo em uma frase

Um movimento de 500 pts em 60 s no WIN é quase sempre um choque de
informação (dado americano, abertura da B3 ou de NY, Fed) que o mercado
leva dezenas de minutos para precificar; entrando **depois** de detectado,
o preço toca +530 antes de −530 mais vezes do que o contrário.

## Regras (o suficiente para reimplementar)

- **Evento:** a cada negócio do WINFUT, referência = último negócio com
  `ts ≤ t − 60 s` (relógio da bolsa). |preço − referência| ≥ 500 pts, com
  `t` em [09:16, 17:00) BRT e fora do refratário de 1.800 s → ignição na
  direção do movimento.
- **Entrada:** a mercado, 1 contrato, no processamento da ignição.
- **Saída**, a cada negócio, a partir do preço de **detecção**: tempo
  (> 3.600 s, estrito) → alvo (+530) → stop (−530) → 18:00 zera.
- **Ignição com posição aberta:** `ignorada_posicionado`, não conta.
- **Limite:** 4 operações por dia. Negócio com ts mais antigo que o último
  processado (edição da B3) é descartado.
- **Só registro, não decide:** âncora de agenda (09:30, 10:00, 10:30, 15:00
  + 5 min) e deslizamento/atraso de cada entrada e saída.

## Origem dos números (escolha CEGA)

`profit-tape ignicao --so-taxa` sobre 10 pregões (10–23/09), com a regra
declarada ANTES (HISTORICO 2026-09-25): limiar = menor com ≤ 2 eventos/dia
→ **500**; barreira = 0,5 × amplitude mediana de 60 min (1.058) → **530**.
Nenhum número foi escolhido olhando p_alvo.

## Resultados do estudo (antes do forward)

| amostra | pregões | decididos | alvo | p_alvo | IC95 |
|---|---|---|---|---|---|
| 1ª medição (10–24/09) | 11 | 19 | 14 | 0,737 | 0,512–0,882 |
| replicação (24/07–09/09, não vista) | 33 | 28 | 19 | 0,679 | 0,493–0,821 |
| **combinado** | **44** | **47** | **33** | **0,702** | **0,560–0,813** |

Critério declarado antes da replicação: IC combinado acima de 0,537
(empate com 30 pts de deslizamento) → **favorável**. Aguenta até ~55 pts
de deslizamento por entrada. Achados descritivos, **não** filtros: filtro
do WDO não separa em 500 pts (17/21 confirmam); 51% das ignições nos 5
min após uma âncora de agenda; 10:30 com 10/11 alvos (n pequeno, visto
depois).

## Ficha do forward (congelada em v3.68 — não se edita)

    HIPOTESE   Depois de uma ignicao de 500 pts em 60 s, o WIN toca +530 antes
               de -530 (a partir do preco de deteccao) em mais de 65% das vezes.
    EVENTO     As regras acima, exatamente; config_sha do ea_ignicao.yaml e tag
               entregue-v3.68 carimbados em cada operacao.
    TAXA       1,07 decididos/pregao (47 em 44 pregoes, estudo); 0,9 em jul-ago,
               1,7 em set: a taxa oscila com a volatilidade (limiar fixo em pts).
    EFEITO     p_alvo 0,65 contra empate 0,537. Efeito real menor (0,60) NAO e'
               distinguivel neste horizonte e sai inconclusivo -- aceito.
    HORIZONTE  ~68 decididos -> ~64 pregoes (~3 meses) a 1,07/pregao.
    CRITERIO   empate_real = (530 + 4 + desliz_entrada_medio + desliz_saida_medio)
               / 1060, com o deslizamento MEDIDO pelo fill no livro ao vivo.
               FAVORAVEL: limite inferior do IC95 de p_alvo > empate_real.
               CONTRA: limite superior < empate_real. INCONCLUSIVO: o resto.
               Operacoes de fill=tape entram no p_alvo, NAO na media do desliz.
    PARADA     Veredito so' com >= 68 decididos OU 6 meses, o que vier antes.
               Olhadas antes disso: SO' defeito (dado, codigo, log). Sequencia
               ruim NAO autoriza parar nem mexer (e' dry_run: sem dinheiro).
               Mudou numero, regra ou saida -> contagem nova (carimbo).

## Antes de ligar (skill forward, seção 3)

1. `profit-tape ea-ignicao-replay config/ea_ignicao.yaml --raw <raiz>` nos
   44 pregões do estudo: EA e estudo lado a lado; "eventos SÓ NO EA" tem de
   ser **0**. Diferenças só no estudo = `ignorada_posicionado`.
2. Rodar o 1º pregão ao vivo e olhar cada ignição no gráfico.
3. Record com `--ea-livro-ao-vivo`: sem ele, `fill=tape` e o deslizamento
   sai zero **por construção**, não medido.

## Histórico M1 — fast-track (declarado 2026-09-25, antes de qualquer número)

**Decisão do operador:** seguir o fast-track do projeto. Sem guarda de
amostra, sem contagem de trials, sem IC deflacionado; mais de uma rodada é
permitida. Ficam as salvaguardas de engenharia: parâmetros fixados antes,
conta à mão, ambíguo reportado. A **consistência por ano** faz o papel da
amostra cega. (Uma divisão em quatro amostras, pela convenção de
`eas_preco_teste.py`, foi proposta e recusada por ser o rigor que o
fast-track corta.)

- **Dado:** `data/winfut_m1_historico.csv`, 27/09/2021 em diante, série
  AJUSTADA multiplicativamente (fator 1,715 → 1,000); validado contra o
  tape (rótulo = início do minuto; `volume_ticks` = negócios do tape).
- **A** = mediana das amplitudes de 60 min (blocos a partir de 09:15) dos
  20 pregões anteriores.
- **Evento:** fechamento(t) − fechamento(t−1), candles consecutivos,
  |mov| ≥ **0,4726 × A** (proporção do tape: 500 / 1.058); decisão no fim do
  candle t em [09:16, 17:00); refratário 30 min.
- **Barreira** 0,5 × A a partir do fechamento de t, até 60 min; os dois
  lados no mesmo candle = ambíguo (fora do p_alvo).
- **Empate:** (B + C) / 2B, C = (9 + 30) pts reais × fator do dia.
- **Critério:** IC95 comum do total acima do empate médio **e** p_alvo > 0,5
  na maioria dos anos → favorável; IC95 superior abaixo do empate → contra;
  resto → inconclusivo.
- **Conferência de tradução:** eventos M1 de 2026 × CSVs de eventos do tape
  (`--comparar-tape`). É outro evento (candle fixo × janela corrida de 60 s);
  a conferência mede o quanto eles coincidem.

Comando: `profit-tape ignicao-m1` (v3.74).

## Resultados do forward

Nenhum ainda.

## Próximo passo

Forward em dry_run. Depois, conta demo (E4) para medir o deslizamento
real com ordem enviada. Variantes de saída (fixa, parcial + trailing,
por tempo) só com ficha própria, declarada antes de olhar.
