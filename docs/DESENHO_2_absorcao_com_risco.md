# DESENHO 2 — absorção com gestão de risco

**RASCUNHO PARA VALIDAÇÃO. Não congelado.** Nenhum retorno foi
consultado: tudo abaixo saiu de variância, amplitude e contagem, na
amostra de depuração (parquet + maio).

---

## 1. Por que o desenho 1 é abandonado

O pré-registro de 2026-08-31 mediu retorno bruto em horizonte fixo de 2
barras. O trial de 2026 fechou `CONTRA` na baixa e `INCONCLUSIVO` na
alta — mas o motivo real não era o resultado:

    desvio dos eventos individuais:  319 pts
    EMD = 1,96 x dp / raiz(n):       107 pts em 10 minutos
    amplitude média da barra 5m:     244 pts

O desenho só enxergava efeito de **0,44 amplitude de barra, líquido, em
duas barras**. Nenhum sinal razoável produz isso. Ele nunca teve como
responder.

Isso satisfaz o critério de abandono registrado em 2026-09-03: **o EMD
sai só da variância e do `n`**, sem usar a média observada. Valeria
igual se o resultado tivesse dado positivo.

E o retorno em horizonte fixo **não corresponde a nenhuma decisão que
alguém tomaria**. Um stop trunca a cauda de perda — e é a cauda que
produz o desvio de 319.

---

## 2. Entrada: idêntica ao desenho 1

Sem alteração nenhuma, para que a diferença entre os dois testes seja
**só a gestão**:

    |desloc_norm| <= 0,25      resultado nulo
    z_amplitude   >= 0,50      alcance
    z_vol_agr     >= 0,50      esforço
    |mov6|        >= 3,00      contexto (habilitador)
    lado = -sign(mov6)         contrário ao movimento

Barra de **5 minutos**. Janelas de 50 barras para os z, 6 para o
contexto, com purga de pregão no contexto e blocos contíguos.

---

## 3. Gestão de risco

### Stop

    referencia = extremo da janela [t-6, t], INCLUINDO a barra de sinal
                 aqua   (venda) -> a MAIOR máxima
                 fúcsia (compra) -> a MENOR mínima

    stop  = referencia + 20   (aqua)
          = referencia - 20   (fúcsia)

    distancia = |stop - close[t]|

    distancia < 150   ->  opera com 150
    distancia > 500   ->  NÃO OPERA
    150 <= d <= 500   ->  opera com a distância técnica

O afastamento de 20 pontos e o piso de 150 existem pela mesma razão que o
operador deu: **não tomar stop só pelo balanço**.

O teto de 500 é limite de risco, e nele a escolha foi **não operar** em
vez de truncar — truncar tiraria o stop do extremo, que é o oposto do
propósito.

### Alvo

**1.000 pontos fixos.** O R:R varia com a distância do stop, de
propósito: stop de 200 dá 5:1, stop de 500 dá 2:1.

### Saídas

    STOP    preço toca o nível
    ALVO    preço toca +1.000 no sentido do lado
    TEMPO   17:30, ao preço de fechamento da barra

A saída às 17:30 evita o leilão de fechamento e impede que a posição
vire swing trade. O pregão vai até 18:20 (barra 113); 17:30 é a barra
103.

### Horário limite de abertura

Não abrir a menos de **6 barras** do encerramento — última entrada às
**17:00** (barra 97).

Razão dada pelo operador, empírica e declarada como tal: com menos de 30
minutos e volume reduzido no fim do pregão, o alvo de 1.000 pontos é
improvável.

---

## 4. Por que isto é mensurável no gráfico

A Rota B precisava de tape porque media a expectativa **a partir do
toque**, e o preço de preenchimento só existe negócio a negócio. Aqui só
é preciso saber **se** tocou e **qual primeiro** — o preço de saída é o
nível.

A ambiguidade existe só quando a mesma barra toca stop **e** alvo, o que
exige percorrer 1.500 pontos. Medido:

    amplitude p50    203 pts
    amplitude p99    884 pts
    barras >= 1500   1 de 2.260   (0,04%)

Resolvido por **limite pessimista**: nas ambíguas, assume stop primeiro.
Uma barra em 2.260 não move veredito.

---

## 5. Estimador

    resultado = pontos ganhos ou perdidos na operação, BRUTO

Uma amostra contra zero, **por lado separado**, purga estrutural de dia.

Significância exige as duas evidências: `|t| >= limiar deflacionado` para
2 comparações **e** IC95 de bootstrap por pregão excluindo zero.

`n` mínimo 30 por lado. Abaixo disso: reportado, nunca interpretado.

---

## 6. Métricas obrigatórias — diagnóstico, nunca critério

Os defeitos abaixo são **conhecidos e aceitos** pelo operador. Cada um
tem métrica própria para poder ser avaliado depois **sem re-rodar**:

**"Em dias direcionais encerra cedo demais."**
→ retorno que a operação teria tido **sem alvo**, saindo só por
stop/tempo. A diferença é o custo do alvo fixo.

**"Pode chegar perto dos 1.000 e stopar, tendo tido R:R de 5x."**
→ **MFE** (máxima excursão favorável) de cada operação, em múltiplos do
risco inicial.

Também: taxa de acerto, distribuição da distância do stop, fração que
sai por stop, alvo e tempo, e quantos eventos foram descartados por
passar de 500.

**Mudar o alvo por causa da MFE observada seria calibrar depois de ver o
dado.** As métricas servem para desenhar o próximo pré-registro, não
este.

---

## 7. O que já foi medido, e o que falta

Na amostra de depuração (maio, 20 pregões, 10 eventos):

    extremo da janela É a própria barra de sinal:  7 de 10 (70%)
    distância do stop: p10=141  p50=223  p90=591
    abaixo de 150:  2  ->  operam com 150
    acima  de 500:  2  ->  descartados (20% da amostra)
    eventos a menos de 6 barras do fim: 0

Projeção para 2025 (~250 pregões), com a taxa de 0,5/pregão menos os 20%
descartados: **~40 eventos na baixa, ~45 na alta.** Passa dos 30 nos dois
lados, sem folga grande.

### FALTA, e é bloqueante antes de congelar

**O EMD deste desenho.** A regra 4 do critério de abandono exige
registrar o EMD do desenho novo **antes** de rodar. Se ele também for
implausível, este desenho não vale mais que o anterior.

Isso é medível na amostra de depuração — usa variância, não retorno
esperado. Mas com 8 operações em maio a estimativa seria fraca; o
parquet (25 pregões de tape) daria mais.

**Sem esse número, o desenho não deve ser congelado.**
