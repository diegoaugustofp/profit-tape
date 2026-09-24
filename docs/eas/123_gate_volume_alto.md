# Ficha — 123 com GATE de volume ALTO (ficha 9)

> **Status:** fechado — **Revisado:** 2026-09-24 — **Assunto:** o 123 mais uma cláusula de volume de candle acima da mediana do horário; hipótese FALSA no sentido declarado — o complemento (volume baixo) é que separou, e virou a ficha `123_volume_baixo.md`.

## Identidade

| | |
|---|---|
| Linha | preço M15 + volume de candle (`vol_total`, `QuantityVol` do gráfico) |
| Instrumento | WINFUT |
| Código | `research/eas_preco*.py` (`--ficha 123gate`) |
| Hash de ficha | `a9abff26ba21` |
| Família | "123gate", trial 1 — família NOVA, não variante do 123 |

## Fase e estado

**F4 — FECHADA (2026-09-15).** O gate como declarado é nulo. O WIN
2015-2026 está QUEIMADO para a família 123 no que toca a volume:
escolher o estrato bom depois de ver é o erro que a disciplina existe
para evitar — mesmo com IC 97,5% [0,532; 0,572] e dez anos consistentes
no complemento.

## Mecanismo em uma frase

Um 123 cuja barra t fecha com volume acima do normal daquele horário
carrega mais continuação do que um com volume abaixo.

## Regras

Tudo da ficha `123_m15.md`, **e**: vol_total(t) ≥ mediana de vol_total
no mesmo hhmm nos 20 pregões ANTERIORES (dia de t fora; sem 20 pregões
de perfil, gate indefinido → sinal fora, contado). Posição aberta ignora
sinal dentro do conjunto com gate.

## Pré-registro congelado (2026-09-15, `entregue-v2.85`)

    TAXA       41-47% dos sinais 123 passam; 1,2-1,6 sinais/pregão.
    EFEITO     p1 ≥ 0,56 contra 0,50 no conjunto COM gate. Combinado
               2015-26: ~3.100 resolvidas, ±1,8 pp.
    CONTRASTE  O COMPLEMENTO (volume abaixo) reportado com o mesmo
               estimador e por ano: gate 0,56 e complemento 0,50 é o que
               vale; gate 0,54 e complemento 0,52 é o 123 de novo.
    ESTRATO    (acrescentado no funil, antes do teste) p1 do gate e do
               complemento DENTRO de cada quartil de D — porque o gate
               seleciona padrões MAIORES (D 825 vs 485). Separa dentro
               dos quartis = volume; só entre = tamanho.
    SEQUÊNCIA  como o 123: veredito no combinado; inconclusivo = fecha.
               Sem trial 2. Um gate, um número, declarado.

## Resultados (2026-09-15)

| conjunto | resolvidas | p1 | IC95 | P&L bruto/op | por-ano |
|---|---|---|---|---|---|
| gate (volume ACIMA) — primário | 2.581 | 0,506 | [0,487; 0,525] | −7 | sem padrão |
| complemento (volume ABAIXO) — reportado | 3.366 | **0,552** | **[0,535; 0,569]** | **+39** | dez de onze anos entre 0,52 e 0,59 |

Por quartil de D — gate / complemento: Q1 0,526 / **0,575**; Q2 0,538 /
**0,564**; Q3 0,495 / **0,525**; Q4 0,494 / 0,498. Volume separa dentro
dos quartis (3-5 pp), no sentido contrário ao declarado; tamanho também
importa (Q1 > Q4 dos dois lados).

## Veredito

**Hipótese FALSA no sentido declarado — fecha.** O achado do
complemento gerou uma hipótese nova, testada em amostra que este teste
não tocou (WDO + forward): ficha `123_volume_baixo.md`. Mecanismo dito
depois de ver (por isso não vale como evidência): recuo sem convicção
continua; recuo com briga vira qualquer coisa.

## Próximo passo

Nenhum nesta ficha.

## Onde está a discussão longa

`EAS_DE_PRECO.md` §9 (9.0 a 9.2).
