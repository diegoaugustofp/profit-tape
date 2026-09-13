"""
E5.4 — RegistroDeEAs: quem entra, quem sai, e a trava do caminho B.

A trava central: 1 EA por TICKER. E' o que substitui a subconta
(EA_ARQUITETURA 4.2) -- dois EAs no mesmo ativo voltariam a netar e a
reconciliacao nao saberia de quem e' a divergencia.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from profittape.ea.config import EAConfig, SinalConfig
from profittape.ea.despachante import DespachanteDeEAs
from profittape.ea.livro import LivroDePosicoes
from profittape.ea.registro import InclusaoRecusada, RegistroDeEAs
from profittape.ea.supervisor import SupervisorDeRisco


def _cfg(symbol: str = "WINV26", nome: str | None = None) -> EAConfig:
    return EAConfig(
        nome=nome, symbol=symbol, volume_barra=1000, janela_z=10,
        sinais=[SinalConfig(feature="z_agf_3", horizonte=3, agent_id=3,
                            threshold_entrada=1.4, direcao="contrarian")],
    )


def _registro(**kw: object) -> RegistroDeEAs:
    return RegistroDeEAs(DespachanteDeEAs(), **kw)  # type: ignore[arg-type]


def test_inclui_e_liga_no_despachante() -> None:
    d = DespachanteDeEAs()
    reg = RegistroDeEAs(d)
    r = reg.incluir(_cfg("WINV26", "z_agf_win"))
    assert r.nome == "z_agf_win" and r.symbol == "WINV26"
    assert len(d) == 1 and reg.nomes == ["z_agf_win"]


def test_TRAVA_dois_EAs_no_mesmo_ticker_e_recusada() -> None:
    """O coracao do caminho B. Sem subconta, dois EAs no mesmo ativo
    netam -- a inclusao TEM que ser recusada, nao so' alertada."""
    reg = _registro()
    reg.incluir(_cfg("WINV26", "primeiro"))
    with pytest.raises(InclusaoRecusada, match="ja' e' operado"):
        reg.incluir(_cfg("WINV26", "segundo"))
    assert reg.nomes == ["primeiro"], "o segundo nao pode ter entrado"


def test_tickers_diferentes_convivem() -> None:
    reg = _registro()
    reg.incluir(_cfg("WINV26", "win"))
    reg.incluir(_cfg("WDOV26", "wdo"))
    assert reg.tickers_ocupados() == {"WINV26": "win", "WDOV26": "wdo"}


def test_nome_duplicado_e_recusado() -> None:
    reg = _registro()
    reg.incluir(_cfg("WINV26", "mesmo"))
    with pytest.raises(InclusaoRecusada, match="ja' existe um EA"):
        reg.incluir(_cfg("WDOV26", "mesmo"))


def test_validar_nao_tem_efeito_colateral() -> None:
    """Da' para checar se um EA entraria SEM inclui-lo -- util para CLI
    e dry-run."""
    reg = _registro()
    reg.incluir(_cfg("WINV26", "a"))
    with pytest.raises(InclusaoRecusada):
        reg.validar(_cfg("WINV26"), "b")
    assert reg.nomes == ["a"]
    reg.validar(_cfg("WDOV26"), "b")      # nao levanta, nao inclui
    assert reg.nomes == ["a"]


def test_remover_libera_o_ticker_para_outro_EA() -> None:
    reg = _registro()
    reg.incluir(_cfg("WINV26", "velho"))
    assert reg.remover("velho") is True
    assert reg.tickers_ocupados() == {}
    reg.incluir(_cfg("WINV26", "novo"))   # ticker livre de novo
    assert reg.nomes == ["novo"]


def test_remover_inexistente_devolve_false() -> None:
    assert _registro().remover("fantasma") is False


def test_nome_vem_do_cfg_ou_do_arquivo() -> None:
    reg = _registro()
    r1 = reg.incluir(_cfg("WINV26", "do_cfg"))
    assert r1.nome == "do_cfg"
    r2 = reg.incluir(_cfg("WDOV26"), origem=Path("/tmp/meu_ea.yaml"))
    assert r2.nome == "meu_ea", "sem `nome` no yaml, usa o nome do arquivo"
    r3 = reg.incluir(_cfg("DOLV26"), nome="explicito")
    assert r3.nome == "explicito", "argumento explicito vence"


def test_supervisor_soma_e_DESSOMA_ao_remover() -> None:
    """Defeito pego na conferencia a mao (2026-09-13): remover um EA
    deixava ele inflando o capital recomendado."""
    sup = SupervisorDeRisco(capital_em_conta=8000.0)
    reg = RegistroDeEAs(DespachanteDeEAs(), supervisor=sup)
    reg.incluir(_cfg("WINV26", "a"))
    reg.incluir(_cfg("WDOV26", "b"))
    assert sup.capital_recomendado_total == 10000.0
    reg.remover("a")
    assert sup.capital_recomendado_total == 5000.0
    assert sorted(sup.exigencias) == ["b"]


def test_livro_registra_e_fecha() -> None:
    livro = LivroDePosicoes()
    reg = RegistroDeEAs(DespachanteDeEAs(), livro=livro)
    reg.incluir(_cfg("WINV26", "a"))
    assert livro.esperado("a") == 0
    livro.registrar_abertura("a", 2, 100.0)
    reg.remover("a")
    assert livro.esperado("a") == 0, "remover tem que fechar a posicao no livro"


def test_caminho_B_nao_gera_alerta_de_subconta() -> None:
    """No caminho B ninguem tem subconta, e isso e' correto por desenho.
    Alertar ali seria ruido constante -- e ruido ensina a ignorar alerta."""
    sup = SupervisorDeRisco(capital_em_conta=99999.0)
    reg = RegistroDeEAs(DespachanteDeEAs(), supervisor=sup)
    reg.incluir(_cfg("WINV26", "a"))
    reg.incluir(_cfg("WDOV26", "b"))
    assert "ea_sem_subconta" not in [x.codigo for x in sup.avaliar()]
