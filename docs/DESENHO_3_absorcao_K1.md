# DESENHO 3 — absorção com hipótese menos restritiva (K = 1)

**RASCUNHO PARA VALIDAÇÃO. Não congelado.** Nenhum retorno de 2025 foi
consultado. Tudo abaixo saiu de variância e contagem, nas amostras de
depuração (parquet, maio, 2026).

---

## 1. O que muda em relação ao desenho 1

**Só o `K`.** Estimador, evento, horizonte, critério e métrica são
idênticos — para que a diferença entre os dois testes seja atribuível a
uma coisa só.

    DESENHO 1   K = 3   ->  732 pts de movimento prévio
    DESENHO 3   K = 1   ->  244 pts

## 2. Por que muda — e a parte que precisa ser dita

O trial de 2026 fechou `CONTRA` na baixa e `INCONCLUSIVO` na alta, mas o
motivo real não era o resultado:

    absorção sozinha (3 condições)   326 eventos  ->  EMD 0,25 unidades
    + contexto |mov6| >= 3            62 eventos  ->  EMD 0,55

**A restrição da hipótese, e não o estimador, era o gargalo.** Absorção
acontece 2,7 vezes por pregão; absorção *após movimento forte* acontece
0,5.

**A parte incômoda, registrada de propósito:** a necessidade de mexer no
`K` veio de ver que `K = 3` não tinha poder. Isso é informação derivada
de dado, ainda que de variância e não de média. O que **não** veio de
dado foi o valor escolhido — ver a seção 4.

## 3. A hipótese fica MAIS FRACA, e isso é o custo

    DESENHO 1   "absorção após movimento FORTE antecipa reversão"
    DESENHO 3   "absorção após movimento antecipa reversão"

Não é a mesma afirmação. O desenho 3 afirma menos, e um resultado
favorável nele **não** valida a versão forte.

## 4. O `K = 1` foi escolhido por mecanismo, não pela tabela

Justificativa do operador, antes de qualquer número de EMD:

> "K = 1 é quase metade do meu stop máximo. Sem medir nada, acho razoável
> entrar numa posição a partir de um sinal que já andou a metade do meu
> stop."

E ela fica mais forte com um número já medido:

    K = 1 exige movimento prévio de   244 pts
    stop mediano medido (desenho 2)   255 pts

A regra vira **"só entro se o preço já andou, antes, o equivalente ao
risco que vou assumir"** — movimento prévio e risco na mesma escala.

**`K = 0` foi recusado por mecanismo, não por número.** Com `|mov6|`
perto de zero o preço praticamente não andou, e `sign(mov6)` vira
sorteio: 56 dos 326 eventos teriam menos de 122 pontos de deslocamento
prévio. Direção tirada de ruído adiciona variância em vez de informar.

O operador optou por **não olhar o gráfico** antes de decidir, e a razão
está certa: a justificativa do stop não depende de quais barras ele viu.

## 5. EMD DECLARADO ANTES DE RODAR

Exigência da regra 4 do critério de abandono:

    K = 1, medido em 2026 (depuração):
      eventos          216
      menor lado        96
      desvio         369,9 pts
      EMD pior lado   0,34 unidades = 83 pontos líquidos em 10 minutos

Contra 0,55 do desenho 1 e 0,25 que `K = 0` daria.

**Ressalva que precisa acompanhar:** 0,34 continua acima do limiar de
0,25 que eu mesmo estipulei — e esse limiar é julgamento, não medição.
Se 83 pontos líquidos em 10 minutos for implausível para absorção, este
desenho também não responde, e isso deve ser dito **agora**, não depois.

## 6. Um achado que muda a leitura do contexto

    desvio por K:  K=0 → 371   K=1 → 370   K=2 → 375   K=3 → 339

**O desvio é constante.** Todo o ganho de EMD vem de `n`, nada de
variância. O contexto **não** seleciona eventos menos ruidosos — só
menos eventos.

Isso não o torna inútil: ele pode selecionar eventos de **efeito** maior,
e isso é imensurável sem olhar a média. Mas significa que a expectativa
de que o contexto "melhora a qualidade do sinal" não tem suporte na
variância.

## 7. Definição — idêntica ao desenho 1, exceto `K`

    |desloc_norm| <= 0,25      resultado nulo
    z_amplitude   >= 0,50      alcance
    z_vol_agr     >= 0,50      esforço
    |mov6|        >= 1,00      contexto            <- ÚNICA MUDANÇA
    lado = -sign(mov6)         contrário ao movimento

    retorno = (close[t+2] - close[t]) * lado, BRUTO

Barra de 5 min. Janelas de 50 (z) e 6 (contexto), com purga de pregão no
contexto e blocos contíguos. `so_agressao = True`.

Uma amostra contra zero, **por lado separado**, purga estrutural de dia.
Significância exige `|t| >= limiar deflacionado` para 2 comparações **e**
IC95 de bootstrap por pregão excluindo zero. `n` mínimo 30 por lado.

Controles pré-registrados, como diagnóstico: contexto sem evento, e
evento sem contexto.

## 8. Portão

`CONTRA` sobre ruído puro, mesma geometria. Bloqueante.

## 9. Critério de decisão e regra de parada

Idênticos ao desenho 1. **Veredito por lado reportado junto do global** —
o global pode afirmar mais do que um lado sustenta quando as amostras são
desiguais, e isso já aconteceu em 2026.

Proibido re-rodar com `K`, cortes, janela ou horizonte diferentes depois
de ver o resultado.

## 10. Amostra e contabilidade

**Teste: 2025** (02/01 a 30/12, já declarado, ~250 pregões). É o último
período cego.

Projeção com a taxa de `K = 1`: 216 eventos em 119 pregões = 1,8/pregão →
**~450 eventos em 2025**, uns 200 no menor lado. Folgado.

**Contabilidade honesta da multiplicidade:**

    trial 1  desenho 1, K = 3, testado em 2026     -> CONTRA / INCONCLUSIVO
    trial 2  desenho 3, K = 1, a testar em 2025

São **duas variantes da mesma hipótese**, e a segunda nasceu depois de a
primeira falhar. Ainda que a mudança tenha justificativa de mecanismo, a
multiplicidade existe e fica registrada.

O desenho 2 **não** entra na conta: foi reprovado na depuração, sem
consumir amostra de teste.

**Se o desenho 3 sair INCONCLUSIVO ou CONTRA, não há terceira variante
disponível** — 2025 é o último período cego. Uma quarta tentativa exigiria
dado novo, e a essa altura a contagem de tentativas passaria a pesar mais
que qualquer resultado.

---

## PARA VOCÊ DECIDIR ANTES DE CONGELAR

1. **83 pontos líquidos em 10 minutos é plausível para absorção?** Se
   não, este desenho também não responde, e é melhor saber agora.
2. **Vale gastar 2025 nisto?** É o último período cego, e o desenho 3
   afirma menos que o desenho 1.
