"""
E5.4c — dois EAs no mesmo ticker, so' um posicionado (modo exclusivo).

Regras decididas pelo operador (2026-09-13): quem sinaliza PRIMEIRO fica
com a vaga; quem perde DESCARTA o sinal (nao fica em espera); a vaga sai
quando o dono zera.
"""

from __future__ import annotations

import threading

import pytest

from profittape.ea.config import EAConfig, SinalConfig
from profittape.ea.despachante import DespachanteDeEAs
from profittape.ea.registro import InclusaoRecusada, RegistroDeEAs
from profittape.ea.vagas import VagasPorTicker


def _cfg(symbol: str = "WINV26", nome: str | None = None) -> EAConfig:
    return EAConfig(
        nome=nome, symbol=symbol, volume_barra=1000, janela_z=10,
        sinais=[SinalConfig(feature="z_agf_3", horizonte=3, agent_id=3,
                            threshold_entrada=1.4, direcao="contrarian")],
    )


# ---------------------------------------------------------------- vagas
def test_primeiro_a_sinalizar_fica_com_a_vaga() -> None:
    v = VagasPorTicker()
    assert v.tentar_ocupar("WINV26", "A") is True
    assert v.tentar_ocupar("WINV26", "B") is False, "B tem que perder a vaga"
    assert v.dono("WINV26") == "A"


def test_quem_perde_a_vaga_e_contado() -> None:
    """O numero importa para LER o resultado: um EA que perdeu metade dos
    sinais nao teve o desempenho da estrategia dele."""
    v = VagasPorTicker()
    v.tentar_ocupar("WINV26", "A")
    v.tentar_ocupar("WINV26", "B")
    v.tentar_ocupar("WINV26", "B")
    assert v.descartes == {"B": 2}


def test_mesmo_EA_pedindo_de_novo_e_reentrante() -> None:
    v = VagasPorTicker()
    v.tentar_ocupar("WINV26", "A")
    assert v.tentar_ocupar("WINV26", "A") is True
    assert v.descartes == {}, "pedir a propria vaga nao e' descarte"


def test_tickers_diferentes_nao_disputam() -> None:
    v = VagasPorTicker()
    assert v.tentar_ocupar("WINV26", "A") is True
    assert v.tentar_ocupar("WDOV26", "B") is True


def test_EA_nao_consegue_liberar_vaga_de_outro() -> None:
    """Liberar a vaga alheia seria bug grave: o dono real continuaria
    posicionado e outro EA entraria em cima."""
    v = VagasPorTicker()
    v.tentar_ocupar("WINV26", "A")
    v.liberar("WINV26", "B")
    assert v.dono("WINV26") == "A"


def test_liberar_devolve_a_vaga() -> None:
    v = VagasPorTicker()
    v.tentar_ocupar("WINV26", "A")
    v.liberar("WINV26", "A")
    assert v.dono("WINV26") is None
    assert v.tentar_ocupar("WINV26", "B") is True


def test_disputa_concorrente_so_um_ganha() -> None:
    """Cada bridge roda na sua thread -- dois EAs podem pedir a vaga no
    mesmo instante. So' um pode ganhar."""
    v = VagasPorTicker()
    ganhadores: list[str] = []
    barreira = threading.Barrier(20)

    def tenta(nome: str) -> None:
        barreira.wait()
        if v.tentar_ocupar("WINV26", nome):
            ganhadores.append(nome)

    threads = [threading.Thread(target=tenta, args=(f"EA{i}",)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    assert len(ganhadores) == 1, f"so' um podia ganhar, ganharam {ganhadores}"


# -------------------------------------------------------------- registro
def test_modo_unico_recusa_segundo_EA_no_ticker() -> None:
    reg = RegistroDeEAs(DespachanteDeEAs())            # default: unico
    reg.incluir(_cfg("WINV26", "a"))
    with pytest.raises(InclusaoRecusada, match="ja' e' operado"):
        reg.incluir(_cfg("WINV26", "b"))


def test_modo_exclusivo_aceita_varios_no_mesmo_ticker() -> None:
    reg = RegistroDeEAs(DespachanteDeEAs(), modo_ticker="exclusivo")
    a = reg.incluir(_cfg("WINV26", "a"))
    b = reg.incluir(_cfg("WINV26", "b"))
    assert reg.nomes == ["a", "b"]
    assert a.bridge.ea_service.vagas is b.bridge.ea_service.vagas, (
        "os EAs precisam DIVIDIR o mesmo controlador de vagas, senao "
        "cada um acharia que a vaga esta' livre")
    assert (a.bridge.ea_service.nome, b.bridge.ea_service.nome) == ("a", "b")


def test_modo_exclusivo_ainda_recusa_nome_duplicado() -> None:
    reg = RegistroDeEAs(DespachanteDeEAs(), modo_ticker="exclusivo")
    reg.incluir(_cfg("WINV26", "mesmo"))
    with pytest.raises(InclusaoRecusada, match="ja' existe um EA"):
        reg.incluir(_cfg("WDOV26", "mesmo"))


def test_modo_invalido_falha_alto() -> None:
    with pytest.raises(ValueError, match="modo_ticker"):
        RegistroDeEAs(DespachanteDeEAs(), modo_ticker="qualquercoisa")


def test_modo_unico_nao_cria_vagas() -> None:
    """Sem disputa, o controlador nem precisa existir -- e sua ausencia
    e' o que mantem o caminho normal identico ao de antes."""
    assert RegistroDeEAs(DespachanteDeEAs()).vagas is None
