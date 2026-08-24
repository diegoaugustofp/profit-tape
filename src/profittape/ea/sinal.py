"""
STUB — construcao de barra ao vivo e calculo do sinal em tempo real.

O QUE FALTA (trabalho real, nao implementado):
  1. Acumular trades ao vivo (via callback, igual ao record) em memoria ate'
     fechar uma barra de volume_barra contratos -- reaproveitar a LOGICA de
     bars.atribuir_barras, mas em modo streaming continuo (uma barra por
     vez, sem esperar arquivo fechado) em vez de batch sobre parquet.
  2. Ao fechar cada barra, calcular a MESMA formula de flow.calcular para o
     agente do SinalConfig -- reaproveitar flow.py diretamente, nao reescrever.
  3. Manter a janela rolante para o z-score (normalize.py usa rolling mean/
     std com shift(1) -- em streaming isso vira um buffer circular de
     tamanho janela_z, atualizado barra a barra).

DECISAO DE DESIGN que MUDA quando isso for implementado: volume_barra e
janela_z em EAConfig sao os valores que o research VALIDOU -- carregados do
mesmo config congelado, nunca recalculados ao vivo (sugerir_volume_barra
sobre dado do dia mudaria o threshold e invalidaria a comparacao com o
sinal testado).
"""

from __future__ import annotations


class ConstrutorDeSinalAoVivo:
    """Placeholder -- ver docstring do modulo. Nao instancie ainda."""

    def __init__(self, *_args, **_kwargs) -> None:
        raise NotImplementedError(
            "sinal.py e' esboco -- construcao de barra ao vivo ainda nao "
            "implementada. Ver docs/EA_ARQUITETURA.md."
        )
