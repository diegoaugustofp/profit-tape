"""
research/: avaliacao de features com metodo travado ANTES do resultado.

Decisoes registradas em docs/RESEARCH_PLANO.md (2026-08-22):
walk-forward por dias inteiros; retornos intra-dia (nunca cruzam pregao) —
o que torna o purging ESTRUTURAL: nenhuma janela de retorno atravessa a
fronteira treino/teste; DSR com contador de trials PERSISTIDO em disco;
veredito por limiar deflacionado, nunca por p-valor cru.
"""
