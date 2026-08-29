# Histórico de sessões — profit-tape

Log cronológico, uma entrada por sessão de trabalho. Cada entrada resume
o que foi feito, organizado por assunto, com ponteiro para as
tags/versões entregues e os documentos de referência tocados.

**Este arquivo é sobre "o que aconteceu quando"** — para o estado ATUAL
de um assunto específico (não o histórico de como se chegou lá),
consulte o documento de assunto correspondente:
- `docs/RESEARCH_PLANO.md` — pesquisa, sinais, decisões de estratégia
- `docs/EA_ARQUITETURA.md` — arquitetura do EA, decisões de integração
- `docs/OPERACAO.md` — rotinas operacionais, infraestrutura
- `docs/BOAS_PRATICAS_PROGRESSO.md` — convenção de progresso/logs

## Como adicionar uma entrada nova (para sessões futuras)

Ao final de cada sessão, adicione uma entrada abaixo (mais recente no
topo), seguindo o modelo: data, resumo por assunto, tags entregues,
pendências que ficaram em aberto. Não repita detalhe que já está nos
documentos de assunto — só resuma e aponte.

---

## Sessão 2026-08-27 a 2026-08-28 (sessão longa, ~um dia inteiro)

Sessão excepcionalmente longa e densa — do planejamento matinal até
correção de CI de madrugada do dia seguinte. Versões entregues:
`entregue-v0.73` até `entregue-v1.02` (aprox. 30 incrementos).

### Infraestrutura
- NSSM configurado e validado em produção (teste de resiliência real
  passou). `schtasks` trocado para chamar `nssm start`.
- Travamento de máquina tratado: ferramenta `triagem-inprogress`
  criada para automatizar a limpeza pós-incidente (promove arquivo com
  footer válido, quarentena o resto).
- `quarentena` ganhou filtro de data (`--dia`/`--desde`/`--ate`).
- Bug real de isolamento de teste corrigido (`cache_logger_on_first_use`
  vazava configuração global do `structlog` entre testes).
- **CI corrigido em 3 causas distintas, sequenciais**: (1) `pandas-stubs`
  faltando revelou 162 erros reais de tipo, corrigidos um a um; (2)
  `mypy` não conseguia nem parsear o stub do `numpy` (sintaxe Python
  3.12+, `python_version` do projeto desatualizado); (3) o interpretador
  Python 3.11 do próprio CI não sabe interpretar essa sintaxe,
  independente de configuração — matriz do `ci.yml` atualizada para
  3.12/3.13. Um teste intermitente (`sleep` fixo em teste de thread)
  também corrigido.
- **Lacuna de versionamento descoberta e corrigida**: `git push origin
  HEAD:main` nunca enviava as tags `entregue-vX.YY` — só a branch.
  Corrigido para sempre incluir `--tags`.

### EA — arquitetura
- Bug crítico de performance resolvido: `ea-replay` travava horas em
  `pyarrow.dataset().to_table()` — trocado por leitura arquivo-a-arquivo.
- Decisão de arquitetura fechada: EA roda **dentro** do processo do
  `record` (licença Nelogica permite só uma chave de ativação).
  Implementado e testado ponta a ponta (`EABridge` + `record --ea-config`).
- `lado_permitido` (restrição de direção) implementado, pré-registrado,
  testado: veredito **favorável** para venda-apenas (mesmo período, não
  out-of-sample nova).
- Curva de patrimônio/drawdown implementada e conectada ao
  `ea-replay-lote`.
- **Rota B (alvo/stop fixo) implementada, depois questionada com razão
  pelo operador**: o mecanismo de checagem só no fechamento de barra
  (não contínuo, tick a tick) não tem lógica de stop/alvo de verdade —
  identificado como o tipo de erro que a regra "valide o mecanismo antes
  de calibrar número" (skill `profit-tape-disciplina`) existe para
  evitar. **Ficou pendente**: desenhar do zero uma Rota B com checagem
  contínua (por trade, não por barra) antes de qualquer nova tentativa.
- `pydantic` das configs do EA (`SinalConfig`/`RiscoConfig`/`EAConfig`)
  ganhou `extra="forbid"` — fecha uma classe de falha silenciosa real
  (campo desconhecido no YAML era ignorado sem erro).

### Pesquisa
- MAE/MFE implementados, com correção de bug real (pool out-of-sample).
- Assimetria compra/venda confirmada por 3 métodos independentes
  convergindo na mesma direção.
- `risco-realizado` (VaR/ES) implementado — conexão de design real com
  a escolha de barras por volume (tempo intrínseco, mesma linhagem
  teórica do "volume clock" que já sustentava o projeto). Achado:
  sazonalidade intradiária afeta calibração de risco, não só o IC.
- `z_agf_8` (fluxo UBS) **fechado** nos dois fronts (ações: morto pelo
  custo, confirmado duas vezes; WINFUT: não passou no IC já testado em
  2026-08-23) — sem gastar trial novo.
- Correção de custo de ações real: planilha da XP decodificada, custo
  tem componente fixo + proporcional ao financeiro.
- Disciplina formalizada: `features` sem custo (roda sempre);
  `research` com custo real (só com dias novos suficientes acumulados).

### Documentação e disciplina
- `docs/BOAS_PRATICAS_PROGRESSO.md` criado (visibilidade de progresso
  em processos longos).
- Política de retenção disco local vs backup documentada (lacuna
  identificada, convenção fixa ainda não decidida).
- Dois *skills* criados: `profit-tape-disciplina` (metodologia —
  pré-registro, validar mecanismo antes de calibrar número, amostra
  pequena) e `profit-tape-engenharia` (versionamento, desenvolvimento,
  logs — inclui o procedimento de bootstrap de sessão nova a partir do
  GitHub).

### Pendências que ficaram em aberto
- Forward-test em DEMO com pregão real (infraestrutura pronta, nunca
  testada em condição real).
- Rota B: redesenhar com checagem contínua antes de tentar de novo.
- Zeragem por consumo de garantia (fora de escopo da curva de
  patrimônio atual).
- Segmentação de IC por horário (feita para risco, não para o IC do
  sinal em si).
- Robustez em regime de mercado diferente.
- `research` aguardando mais dias (decisão do operador).

---

## Sessões anteriores (antes de 2026-08-27)

Não recompiladas em detalhe aqui — o contexto desta sessão longa
começou com um resumo compactado de conversas anteriores (catalogadas
em `journal.txt`, junto aos transcripts brutos, fora deste
repositório). Se precisar de detalhe de uma sessão anterior a
2026-08-27, comece pelos documentos de assunto (`RESEARCH_PLANO.md`,
`EA_ARQUITETURA.md`) — eles têm entradas datadas desde 2026-08-23.
