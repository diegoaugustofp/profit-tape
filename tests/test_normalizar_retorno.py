"""
Codigo de erro de 32 bits lido por um restype de 64 bits.

BUG REAL, pregao de 2026-09-24: `SendCancelOrders` devolveu
NL_INVALID_ARGS (0x80000003). As funcoes de ordem sao declaradas com
`restype = c_int64` porque devolvem ID de ordem, que e' grande -- entao
o erro chegou como +2147483651 em vez de -2147483645, o teste
`if r < 0` NAO disparou, e o codigo registrou
`ea.cancel_todas_enviado` (sucesso) para uma chamada que FALHOU.

A v3.40 tinha acrescentado o detector certo (`if r < 0` com describe);
ele so' estava cego pelo sinal.
"""

from __future__ import annotations

import pytest

from profittape.profitdll.errors import describe, normalizar_retorno


def test_o_erro_EXATO_do_pregao_de_24_09() -> None:
    assert normalizar_retorno(2147483651) == -2147483645
    assert "NL_INVALID_ARGS" in describe(normalizar_retorno(2147483651))


def test_limites_da_faixa_de_erro() -> None:
    """Só 0x80000000..0xFFFFFFFF são códigos NL mal lidos."""
    assert normalizar_retorno(0x80000000) == -2147483648
    assert normalizar_retorno(0xFFFFFFFF) == -1
    # 0x7FFFFFFF é positivo legítimo e NÃO pode ser mexido
    assert normalizar_retorno(0x7FFFFFFF) == 0x7FFFFFFF


def test_IDs_de_ordem_REAIS_passam_intactos() -> None:
    """Os IDs medidos ao vivo no E2 e no E3. Se o normalizador mexesse
    neles, a confirmacao de fill pararia de casar."""
    for oid in (26091112112953, 26091117574093, 26091108132047):
        assert normalizar_retorno(oid) == oid


def test_sucesso_e_retornos_pequenos_nao_mudam() -> None:
    for v in (0, 1, 2, 1000):
        assert normalizar_retorno(v) == v


def test_negativo_ja_correto_nao_e_alterado() -> None:
    """Se algum caminho ja' devolver com sinal, normalizar de novo nao
    pode estragar (idempotencia sobre o valor final)."""
    assert normalizar_retorno(-2147483645) == -2147483645
    assert normalizar_retorno(normalizar_retorno(2147483651)) == -2147483645


@pytest.mark.parametrize("valor,esperado_negativo", [
    (2147483646, False),     # 0x7FFFFFFE: positivo legitimo
    (2147483648, True),      # 0x80000000: erro
    (2147483651, True),      # o de hoje
])
def test_fronteira(valor: int, esperado_negativo: bool) -> None:
    assert (normalizar_retorno(valor) < 0) is esperado_negativo
