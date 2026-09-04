# Onde estamos e para onde dá para ir — 2026-09-04

## 1. O estado da hipótese de absorção

Testada duas vezes, com amostra suficiente na segunda.

    lado AQUA (absorcao apos ALTA)     n=251   +6,6 pts   t 0,361
      -> RESPOSTA CLARA: nao antecipa queda. Sem desculpa de poder.

    lado FUCSIA (absorcao apos QUEDA)  n=216  -36,3 pts   t -1,996
      -> marginal (folga 0,036), e confundido com momentum

**A hipótese como formulada não sobreviveu.** O lado aqua tem resposta
negativa firme. O lado fúcsia tem um sinal marginal que aponta para o
lado **contrário** ao esperado, e que o controle sugere não ser
absorção.

**Não há amostra cega restante** no gráfico para 2025 e 2026. Sobram 2024
e anteriores, que seriam nova declaração com multiplicidade acumulada.

## 2. O achado mais forte da sessão não foi a absorção

    CONTROLE contexto sem evento   n=10.305   media -4,55   t -2,296

São barras com movimento prévio e **sem absorção nenhuma**. Retorno
negativo na direção contrária ao movimento significa que **o preço
continuou** no sentido dele.

Isso é momentum, e o poder é de outra ordem:

    EMD do desenho 3 (absorcao)      0,34 unidades
    EMD deste grupo                  0,016 unidades

**O problema de poder que dominou a sessão inteira simplesmente não
existe aqui** — n de 10.305 em vez de 216.

**Ressalva grande**: isto foi encontrado OLHANDO o dado, num grupo que
existia como diagnóstico. Como hipótese, precisa de declaração própria e
amostra que não seja 2025 nem 2026.

## 3. O que ficou estabelecido sobre o problema

- **Absorção não é rara**: 2,7 barras por pregão, 2,4% das barras.
- **Absorção e movimento andam juntos**: 3,7x acima do acaso.
- **O contexto não seleciona eventos menos ruidosos.** O desvio é
  constante de `K=0` a `K=3`. Ele reduz quantidade, não ruído.
- **O alvo de 1.000 está além do p90 da excursão favorável.** O preço
  tipicamente anda menos de 1x o risco a favor.
- **Média de retorno em pontos é instrumento fraco** para amostras desta
  ordem: exige 105+ eventos por lado só para detectar 0,25 amplitude de
  barra.

## 4. Caminhos, com o custo de cada um

### A. Fechar a absorção e registrar

Custo zero. O lado aqua tem resposta; o fúcsia fica registrado como
marginal e confundido. Honesto, e libera atenção.

### B. Momentum como hipótese NOVA

O achado do controle, formalizado e pré-registrado do zero.

**A favor**: poder de sobra (EMD 0,016), mecanismo simples e testável,
usa infraestrutura que já existe.
**Contra**: foi encontrado olhando dado, então precisa de amostra virgem
— 2024 ou anterior. E momentum em índice futuro é fenômeno muito
estudado; a chance de haver algo não explorado é menor que numa leitura
de tape.

### C. Acumular tape adiante (`record`)

**A favor**: é a única fonte de dado **genuinamente novo**, sem
multiplicidade acumulada. E abre perguntas que só o tape responde —
preenchimento exato, book, agressão por lado.
**Contra**: lento. ~21 pregões por mês.

### D. Trocar o instrumento de medição

Média de retorno em pontos é fraca. Alternativas: taxa de acerto
(classificação), rotulagem por barreiras triplas, ou critério sobre a
forma da distribuição.

**A favor**: ataca a causa estrutural, não um sintoma. Serve para
qualquer hipótese futura.
**Contra**: é trabalho de infraestrutura, não de descoberta. E não
garante que exista sinal.

### E. Exaustão

Nunca testada. É processo de **sequência** (base de 2-5 candles, acima de
20 vira indecisão), escala diferente da barra única.

**A favor**: é hipótese do operador, vinda da leitura de tela, e nunca
tocada. Ortogonal a tudo que foi testado.
**Contra**: precisa de formalização do zero, e a experiência desta sessão
diz que a formalização é onde os erros moram.

### F. Stop como controle de drawdown

Pré-registro pendente de sessões anteriores. A Rota B deixou explícito
que "stop não detecta reversão" — mas controlar drawdown é outra
pergunta.

**A favor**: pergunta de gestão, não de sinal. Não depende de haver edge.
**Contra**: só faz sentido quando houver estratégia para proteger.

## 5. O que eu faria, e por quê

**A + C em paralelo.** Fechar a absorção honestamente, e deixar o
`record` acumulando — é a única fonte de dado sem multiplicidade
herdada.

**E depois E (exaustão)**, porque é a única hipótese que ainda vem da
leitura de tela do operador e nunca foi tocada. A absorção nasceu assim e
o processo funcionou: a formalização estava errada duas vezes, foi
corrigida por inspeção visual, e a resposta veio limpa.

**B (momentum) é tentador e eu desconfiaria dele.** O poder é atraente
justamente porque `n` é enorme, e `n` enorme torna significativo qualquer
viés residual de medição. Um efeito de −4,5 pontos por operação também
não sobrevive a custo.

**D vale quando houver hipótese que precise dele** — construir
instrumento sem pergunta é o erro que a sessão já cometeu com o desenho
2.
