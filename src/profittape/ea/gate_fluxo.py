"""
A PORTA DE VOLUME do EA de preco (passo 5 do F5, EAS_DE_PRECO.md 5.4 e 6).

Interface, nao conteudo. `GateDeFluxo.permite(candidato, barra_t)` fica
entre "o sinal de preco armou" e "manda a ordem". `SemFiltro` e' o
default e o unico conteudo hoje: deixa passar tudo.

Por que e' um GATE e nao um termo do sinal: o sinal de preco continua
identico ao que os 10 anos testaram; o gate so' escolhe quais dos
mesmos candidatos viram ordem. Quando uma feature de fluxo passar pela
disciplina (ficha propria, amostra que os testes nao tocaram -- a que o
passo 6 grava), ela vira uma implementacao daqui e um bloco preenchido
em `filtro_fluxo:` no YAML. Carimbo novo, contagem nova.
"""

from __future__ import annotations

from typing import Any, Protocol

from .sinal import BarraFechada
from .sinal_123 import Candidato123


class GateDeFluxo(Protocol):
    def permite(self, candidato: Candidato123, barra_t: BarraFechada) -> bool: ...


class SemFiltro:
    """Default. Nenhum conteudo."""

    def permite(self, candidato: Candidato123, barra_t: BarraFechada) -> bool:
        return True


def construir_gate(cfg: dict[str, Any] | None) -> GateDeFluxo:
    """`filtro_fluxo: null` -> SemFiltro. Qualquer outra coisa e' recusada
    ate' existir uma ficha que a autorize (extra=forbid na config)."""
    if cfg is None:
        return SemFiltro()
    raise ValueError(f"filtro_fluxo={cfg!r}: nenhum gate de fluxo tem ficha congelada; "
                     "so' `null` e' aceito (EAS_DE_PRECO.md 6)")
