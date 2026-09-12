"""
E5.1 — LivroDePosicoes: posicao por (EA, subconta, ticker).

O que estes testes protegem e' a razao de existir das subcontas
(EA_ARQUITETURA 4.2): com subcontas separadas, posicoes opostas de EAs
diferentes NAO se netam e a divergencia tem dono. Numa conta so', nada
disso seria verdade.
"""

from __future__ import annotations

import pytest

from profittape.ea.livro import ChaveDePosicao, LivroDePosicoes


def _livro_dois_eas() -> LivroDePosicoes:
    L = LivroDePosicoes()
    L.registrar_ea("A", "SUB-A", "WINV26")
    L.registrar_ea("B", "SUB-B", "WINV26")
    return L


def test_abertura_simples_e_preco_medio_ponderado() -> None:
    """Compra 1 a 100, depois +1 a 200 -> 2 contratos a 150 de media."""
    L = _livro_dois_eas()
    L.registrar_abertura("A", 1, 100.0)
    assert L.esperado("A") == 1 and L.posicoes["A"].preco_medio == 100.0
    L.registrar_abertura("A", 1, 200.0)
    assert L.esperado("A") == 2 and L.posicoes["A"].preco_medio == 150.0


def test_virada_de_lado_usa_o_preco_novo() -> None:
    """De +2 para -1 (vende 3): media ponderada entre lados opostos nao
    faz sentido -- a posicao resultante e' nova, com o preco novo."""
    L = _livro_dois_eas()
    L.registrar_abertura("A", 2, 150.0)
    L.registrar_abertura("A", -3, 300.0)
    assert L.esperado("A") == -1
    assert L.posicoes["A"].preco_medio == 300.0


def test_zerar_por_soma_limpa_o_preco_medio() -> None:
    L = _livro_dois_eas()
    L.registrar_abertura("A", 2, 150.0)
    L.registrar_abertura("A", -2, 180.0)
    assert L.esperado("A") == 0
    assert L.posicoes["A"].preco_medio == 0.0
    assert L.posicoes["A"].zerada


def test_subcontas_diferentes_NAO_netam() -> None:
    """O ponto central do desenho: A comprado 1, B vendido 1, em
    subcontas diferentes -> a corretora ve +1 numa e -1 na outra, nao
    zero. Numa conta unica isso viraria posicao liquida zero e seria
    indistinguivel de 'ninguem tem nada'."""
    L = _livro_dois_eas()
    L.registrar_abertura("A", 1, 100.0)
    L.registrar_abertura("B", -1, 100.0)
    agregado = L.por_subconta()
    assert agregado[ChaveDePosicao("SUB-A", "WINV26")] == 1
    assert agregado[ChaveDePosicao("SUB-B", "WINV26")] == -1
    assert len(agregado) == 2


def test_reconciliar_sem_divergencia() -> None:
    L = _livro_dois_eas()
    L.registrar_abertura("A", 2, 100.0)
    L.registrar_abertura("B", -1, 100.0)
    encontrado = {
        ChaveDePosicao("SUB-A", "WINV26"): 2,
        ChaveDePosicao("SUB-B", "WINV26"): -1,
    }
    assert L.reconciliar(encontrado) == []


def test_divergencia_tem_DONO_por_causa_da_subconta() -> None:
    """B acha que tem -1, a corretora diz 0 -> a divergencia e' do B,
    nominalmente. Isso e' o que a subconta compra."""
    L = _livro_dois_eas()
    L.registrar_abertura("A", 2, 100.0)
    L.registrar_abertura("B", -1, 100.0)
    encontrado = {
        ChaveDePosicao("SUB-A", "WINV26"): 2,
        ChaveDePosicao("SUB-B", "WINV26"): 0,
    }
    divs = L.reconciliar(encontrado)
    assert len(divs) == 1
    assert divs[0].ea == "B" and divs[0].esperado == -1 and divs[0].encontrado == 0
    assert divs[0].delta == 1     # precisa comprar 1 para chegar no encontrado


def test_posicao_orfa_aparece_como_de_ninguem() -> None:
    """Posicao numa subconta que nenhum EA reclama -- tipicamente
    operacao manual, o cenario que o E3 encontrou ao vivo em 2026-09-11."""
    L = _livro_dois_eas()
    encontrado = {ChaveDePosicao("PRINCIPAL", "WINV26"): 5}
    divs = L.reconciliar(encontrado)
    orfas = [d for d in divs if d.subconta == "PRINCIPAL"]
    assert len(orfas) == 1
    assert orfas[0].ea == "(ninguem)" and orfas[0].encontrado == 5


def test_subconta_compartilhada_nao_consegue_atribuir_dono() -> None:
    """Honestidade do modulo: se dois EAs dividem subconta, a divergencia
    NAO tem como ser atribuida -- e' a limitacao que as subcontas
    existem para evitar, e o supervisor ja' alerta sobre isso."""
    L = LivroDePosicoes()
    L.registrar_ea("A", "MESMA", "WINV26")
    L.registrar_ea("B", "MESMA", "WINV26")
    L.registrar_abertura("A", 1, 100.0)
    L.registrar_abertura("B", -1, 100.0)
    # os dois netam DENTRO da subconta compartilhada: esperado 0
    assert L.por_subconta()[ChaveDePosicao("MESMA", "WINV26")] == 0
    divs = L.reconciliar({ChaveDePosicao("MESMA", "WINV26"): 3})
    assert divs[0].ea == "A+B"     # nao da' para saber de quem


def test_registrar_ea_e_idempotente_mas_recusa_remapear() -> None:
    L = _livro_dois_eas()
    L.registrar_abertura("A", 1, 100.0)
    L.registrar_ea("A", "SUB-A", "WINV26")      # idempotente, nao zera
    assert L.esperado("A") == 1
    with pytest.raises(ValueError, match="nao posso remapear"):
        L.registrar_ea("A", "OUTRA-SUB", "WINV26")


def test_ea_nao_registrado_falha_alto() -> None:
    L = LivroDePosicoes()
    with pytest.raises(KeyError):
        L.registrar_abertura("fantasma", 1, 100.0)
    with pytest.raises(KeyError):
        L.esperado("fantasma")


def test_abertura_de_quantidade_zero_e_erro() -> None:
    L = _livro_dois_eas()
    with pytest.raises(ValueError):
        L.registrar_abertura("A", 0, 100.0)


def test_fechamento_zera() -> None:
    L = _livro_dois_eas()
    L.registrar_abertura("A", 3, 100.0)
    L.registrar_fechamento("A")
    assert L.esperado("A") == 0 and L.posicoes["A"].preco_medio == 0.0
