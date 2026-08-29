# Instrucoes do Project (Claude.ai) -- profit-tape

Este e' o texto colocado no campo de instrucoes personalizadas do
Project do Claude.ai onde as sessoes deste projeto acontecem. Mantido
aqui tambem, versionado, para nao depender so' da UI do Claude.ai.

Se o texto no Project ficar desatualizado em relacao a este arquivo,
atualize os dois juntos.

---

# Instrucoes do Projeto — profit-tape

profit-tape e' o pipeline quant do Diego: captura de tape/book da B3
via ProfitDLL, pesquisa estatistica com disciplina anti-overfitting,
e um EA de execucao para WIN futures. Sessoes sao longas e tecnicas
— codigo Python real, testes, git.

## Ao comecar QUALQUER sessao nova

O sandbox de Claude comeca sempre vazio, mesmo dentro deste Project —
nunca assuma que o codigo ja' esta la'. Primeiro passo, sempre:

    git clone https://github.com/diegoaugustofp/profit-tape
    cd profit-tape
    git tag              # confirma quais tags entregue-vX.YY existem
    git log --oneline -5

Se a tag mais recente parecer desatualizada frente ao que a conversa
sugere, pergunte ao Diego antes de continuar — nao assuma.

## Skills a consultar sempre que a tarefa envolver codigo ou decisao de pesquisa/estrategia

- `profit-tape-disciplina` — quando pre-registrar antes de codificar,
  como validar que um MECANISMO faz sentido antes de calibrar NUMEROS
  para ele, disciplina de amostra pequena, retrocompatibilidade.
- `profit-tape-engenharia` — como versionar/entregar codigo (tag +
  bundle incremental, ja' que Claude roda isolado sem acesso a maquina
  do Diego), ordem de verificacao antes de considerar algo pronto,
  convencao de logs.

## Se as skills nao carregarem por algum motivo, o minimo indispensavel:

1. Nunca mude comportamento do EA sem pre-registrar por escrito
   (motivacao, criterio de decisao) ANTES de codificar.
2. Antes de calibrar um numero/limiar, confirme que o MECANISMO em si
   faz sentido — nao gaste tempo depurando implementacao de algo cujo
   desenho de base esta errado.
3. Toda entrega de codigo vira um `git bundle` incremental (tag
   `entregue-vX.YY`, sequencial, com `--tags` no push) — sem isso, a
   mudanca nao existe para o Diego.
4. Rode a suite completa + `ruff check` + `mypy src` antes de
   considerar qualquer mudanca pronta.

## Documentos vivos (dentro do repositorio, sempre atualizados)

- `docs/HISTORICO_DE_SESSOES.md` — o que aconteceu em cada sessao.
- `docs/RESEARCH_PLANO.md`, `docs/EA_ARQUITETURA.md`,
  `docs/OPERACAO.md` — estado atual por assunto (cada um tem indice
  agrupado por tema no topo).
