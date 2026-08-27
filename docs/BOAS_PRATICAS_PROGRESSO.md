# Boas praticas: visibilidade de progresso em processos longos

Principio registrado pelo operador (2026-08-27): trabalhamos com volumes de
dado muito grandes (milhoes de trades por pregao, dezenas de dias
acumulados) e processos que rodam minutos a horas. Sem visibilidade clara
de progresso, um processo saudavel rodando devagar e' indistinguivel de um
processo travado -- o risco real e' perder horas de trabalho por nao saber
se algo esta evoluindo ou nao.

## Regra

**Todo comando que pode demorar mais que alguns segundos precisa emitir
progresso -- ANTES de terminar, nao so' um resumo no final.** Isso vale
tanto para quando o operador esta olhando a tela ao vivo quanto para
quando so' vai checar um `--log-file` depois.

## Como fazer certo (padrao ja usado no projeto)

1. **Contador explicito `[i/N]`** no inicio de cada unidade de trabalho
   (dia, simbolo, arquivo) -- nao so' "processando", mas "processando
   3 de 23". Sem o denominador, um numero sozinho nao diz nada sobre
   quanto falta.
2. **Emitir no INICIO e no FIM de cada unidade**, nao so' no fim -- um
   marcador de inicio prova que o processo esta vivo mesmo antes da
   primeira unidade terminar (util quando uma unidade demora muito mais
   que as outras).
3. **Duplo canal: tela (typer.echo) E log estruturado (log.info)** --
   quem esta olhando ao vivo ve na tela; quem so' vai conferir depois via
   `Get-Content -Wait arquivo.jsonl` precisa que a MESMA informacao esteja
   no arquivo. Emitir so' num dos dois canais deixa o outro cego.
4. **Estimativa de tempo restante (ETA)**, quando fizer sentido -- tempo
   decorrido / unidades feitas * unidades restantes. Simples de calcular,
   responde diretamente "quanto falta" sem o operador ter que adivinhar.
5. Para loops MUITO longos dentro de uma unica unidade (ex.: milhares de
   arquivos), relatar tambem a cada N itens OU a cada T segundos (o que
   vier primeiro) -- nao esperar a unidade inteira terminar para dizer
   algo (ver quarentena.progresso, curate.processando).

## Inventario (2026-08-27) -- quem ja segue, quem foi corrigido

| comando | tem progresso? | mecanismo |
|---|---|---|
| `record` | sim | `recorder.heartbeat` periodico (tambem usado pelo `vigia` para detectar travamento) |
| `curate` | sim | `curate.processando` com `progresso=i/N` por dia |
| `features todos` | sim | `[i/9] SYMBOL` por simbolo |
| `quarentena` | sim | `quarentena.progresso` a cada 100 arquivos ou 5s |
| `ea-replay-lote` | **corrigido 2026-08-27** | antes: so' uma linha de resumo apos cada dia, so' na tela, sem contador nem ETA. Agora: `[i/N] dia — iniciando` + `[i/N] dia concluido` (tela E log.info, com `decorrido`/`eta`) |
| `ea-replay` (dia unico) | parcial | tem `ea.replay_progresso` a cada 200k trades, mas roda tipicamente em ~30s -- progresso menos critico aqui |

## Checklist para qualquer comando novo que processe uma lista de itens

- [ ] Imprime o TOTAL antes de comecar (`N dia(s)`, `N arquivo(s)`)?
- [ ] Cada item processado aparece com contador `[i/N]`?
- [ ] Aparece tanto no inicio quanto no fim de cada item (nao so' no fim)?
- [ ] Vai tanto para a tela quanto para o `--log-file` (se o comando aceitar um)?
- [ ] Se um item sozinho pode demorar muito, tem progresso DENTRO dele tambem?
