# Plano do modulo research/ (decidido 2026-08-22, pre-implementacao)

Registro das decisoes de desenho ANTES de escrever codigo, para o research
nascer com metodo travado e nao com parametros escolhidos depois de ver
resultado (isso seria p-hacking — o proprio projeto ja rejeitou esse padrao).

## Decisoes aprovadas

1. ALVO: IC de Spearman de cada feature Tier 1 contra ret_h em barras de
   volume, horizontes h in {1, 3, 10} barras. Multi-horizonte para ver decay
   do sinal, nao um ponto isolado.

2. PURGING: gap entre treino e teste = holding maximo do triple-barrier;
   embargo de +1 barra. Minimo para nao vazar rotulo sobreposto (Lopez de
   Prado).

3. VALIDACAO: WALK-FORWARD, nao CPCV. Decisao explicita do operador
   (2026-08-22). Justificativa: com ~19 pregoes, CPCV (N=6, k=2 -> 15 combos)
   daria falsa sensacao de robustez que a amostra nao sustenta. Walk-forward
   e' honesto sobre o que 19 dias podem dizer. MIGRAR para CPCV quando o
   record diario acumular ~40+ pregoes.

4. DSR: cada feature x horizonte conta como trial. Contador PERSISTIDO em
   disco (nao mental), somando entre rodadas — o Deflated Sharpe precisa do
   numero real de tentativas historicas para nao mentir depois de meses.

5. SAIDA: relatorio markdown versionado por rodada — dado usado, parametros,
   trials acumulados, veredito por feature (segue / descarta / inconclusivo).

## Persistencia de corretora — desenho refinado (ideia do operador, 2026-08-22)

MUDANCA DE ENQUADRAMENTO: em vez de testar "o fluxo do agente N (numero cego)
preve retorno?", testar a hipotese ECONOMICA "fluxo de VAREJO preve retorno de
forma diferente de fluxo INSTITUCIONAL?". Isto e' a hipotese classica de
microestrutura smart money vs dumb money, e tem significado — nao e' garimpo
sobre codigos arbitrarios.

Intuicao a testar (nao a assumir):
  - Fluxo INSTITUCIONAL (ex.: Morgan Stanley, BTG institucional) tende a ser
    informado -> possivel CONTINUACAO de retorno.
  - Fluxo de VAREJO (ex.: XP, Clear, Rico, Modal) tende a ser ruidoso/contrario
    -> possivel REVERSAO.

Implementacao proposta:
  a. Tabela de classificacao agent_id -> perfil {VAREJO, INSTITUCIONAL, MISTO,
     DESCONHECIDO}. Construida a partir de data/ref/agentes.csv (nomes reais
     via GetAgentNameById) + curadoria manual do operador (ele conhece o
     mercado B3). Fica versionada em data/ref/perfil_corretora.csv.
  b. Features agregadas por perfil, nao so' por agente:
       - fluxo_liquido_varejo    = compra_varejo - venda_varejo  (por barra)
       - fluxo_liquido_inst      = compra_inst   - venda_inst
       - divergencia_perfil      = sinal(fluxo_inst) vs sinal(fluxo_varejo)
         (barras onde institucional e varejo estao em lados OPOSTOS — o setup
          classico: seguir o institucional contra o varejo)
  c. Testar IC dessas features de perfil contra ret_h, com o MESMO rigor
     (walk-forward, purging, DSR contando cada uma como trial).
  d. Teste de persistencia por perfil: autocorrelacao diaria do fluxo_liquido
     de cada perfil + IC defasado (o fluxo institucional de hoje preve o
     retorno de amanha melhor que o de varejo?).

CUIDADOS METODOLOGICOS registrados:
  - A classificacao VAREJO/INST e' uma HIPOTESE do operador, nao verdade
    revelada. Uma corretora pode ter mesa institucional E corretora de varejo
    sob o mesmo codigo (por isso o rotulo MISTO existe). Rotular errado
    enfraquece o teste — melhor MISTO/DESCONHECIDO honesto que forcar binario.
  - Classificar DEPOIS de ver qual classificacao da' IC melhor seria p-hacking.
    A tabela perfil_corretora.csv deve ser congelada ANTES de rodar o IC, com
    base em conhecimento de mercado, nao em resultado.
  - Cada variante de classificacao testada (ex.: "e se XP fosse MISTO?") conta
    como trial adicional no DSR. Nao ha almoco gratis em reclassificar ate'
    o sinal aparecer.
  - Volume real e' ~metade do bruto (reentregas idempotentes deduplicadas no
    curate, confirmado 2026-08-22). Features de fluxo devem rodar sobre o
    CURATED, nunca sobre o raw, senao o volume por perfil vem inflado 2x.

## Pre-requisitos antes de escrever research/
  - [x] 19 pregoes capturados com footer duravel (recaptura em andamento)
  - [ ] curate rodado -> dataset deduplicado
  - [ ] agents rodado -> agentes.csv com nomes reais
  - [ ] operador preenche perfil_corretora.csv (curadoria manual)
  - [ ] features rodado sobre curated

## REVISAO DA HIPOTESE DE PERFIL (2026-08-22, operador)

O operador puxou os SHORT NAMES (GetAgentShortNameById, mais util que o nome
juridico) dos agentes de maior volume:
    3    -> XP
    85   -> BTG
    1618 -> Ideal
    120  -> Genial
    8    -> UBS
    39   -> Agora

INSIGHT METODOLOGICO: o operador REJEITOU a classificacao varejo/institucional
simples ao ver os nomes — XP, BTG, Ideal, Genial atendem varejo E tem mesa
institucional/estrangeira sob o MESMO codigo de agente. Rotular XP como
"varejo" seria forcar os dados numa hipotese conveniente. Recuar disso e' a
decisao certa.

NOVA HIPOTESE (mais forte): NACIONAL vs ESTRANGEIRO, nao varejo/institucional.
Motivacao ancorada em evento REAL e datado: agosto/2026 registrou grande
saida de capital estrangeiro da B3. Se esse foi o fluxo dominante na janela de
dados, entao nacional/estrangeiro nao e' classificacao arbitraria — e' a
variavel que de fato movia o mercado nesses pregoes.

VANTAGENS desta hipotese sobre a anterior:
  1. Ancorada em evento macro real (saida de estrangeiro em agosto), nao
     numa taxonomia generica — menos sujeita a ser artefato estatistico.
  2. VERIFICAVEL contra dado externo independente: B3/CVM publicam saldo
     diario de investidor estrangeiro, e o Trade Hunter MCP (flow-foreign)
     traz fluxo estrangeiro/institucional/varejo consolidado. Isso permite
     VALIDAR a classificacao de corretora ANTES de testar previsao:
       - classificar corretoras por perfil nacional/estrangeiro
       - agregar fluxo liquido por perfil no dado tick-a-tick
       - checar se correlaciona com o saldo estrangeiro OFICIAL da B3 nos
         mesmos dias
       - se correlaciona -> classificacao validada; se nao -> esta errada,
         descoberto SEM gastar trial de p-hacking em previsao de retorno
  3. Alinha com a stack do operador (Trade Hunter flow-foreign ja' mapeado).

RISCO desta hipotese, registrado honestamente:
  - Classificar uma corretora como "estrangeira" ou "nacional" e' aproximado:
    a corretora e' o CANAL, nao o investidor final. XP pode rotear tanto
    pessoa fisica brasileira quanto fundo estrangeiro. O codigo de agente
    identifica a corretora, nao a origem do capital. Entao "fluxo via
    corretoras com forte presenca estrangeira" e' uma PROXY, nao a verdade.
    A validacao contra o saldo oficial da B3 (item 2 acima) e' o que mede
    quao boa e' essa proxy — se for ruim, a hipotese cai por dado, nao por
    opiniao.

ACAO: operador vai pesquisar a melhor forma de classificar (o proprio
reconheceu que precisa investigar mais). perfil_corretora.csv permanece
CONGELADO antes do IC, seja qual for o eixo escolhido. GetAgentShortNameById
agora exposto (client.agent_name(id, curto=True)); comando `agents` grava
short_name + nome + coluna 'perfil' vazia para curadoria manual.
