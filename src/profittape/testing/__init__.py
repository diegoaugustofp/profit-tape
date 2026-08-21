"""
Dubles de teste que fazem parte do PACOTE, nao da suite.

A FakeProfitDLL comecou em tests/ e migrou para ca' quando o `bench` — um
comando de producao — passou a depender dela e quebrou fora da raiz do repo
(entrypoint instalado nao tem tests/ no path). Regra que fica: codigo que um
comando da CLI importa pertence ao pacote, mesmo que tambem sirva a testes.
"""

from .fake_dll import FakeProfitDLL

__all__ = ["FakeProfitDLL"]
