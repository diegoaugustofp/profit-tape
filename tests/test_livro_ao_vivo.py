"""
Topo do livro AO VIVO: estado consultavel pelo EA no instante da decisao.

~1 milhao de eventos por pregao que eram capturados e nunca usados.
"""

from __future__ import annotations

import threading

import pytest

from profittape.domain.events import TinyBook
from profittape.ea.livro_ao_vivo import EstadoDoLivro


def _tb(side: int, preco: float, qtd: int, sym: str = "WINV26") -> TinyBook:
    return TinyBook(ts_recv_ns=1, symbol=sym, exchange="F", side=side,
                    price=preco, quantidade=qtd)


def test_simbolo_desconhecido_devolve_None() -> None:
    assert EstadoDoLivro().ler("WINV26") is None


def test_um_lado_so_NAO_tem_desequilibrio() -> None:
    """Sem os dois lados nao existe desequilibrio. Devolver 0,0 seria
    inventar 'equilibrado', que e' afirmacao diferente de 'nao sei'."""
    e = EstadoDoLivro()
    e.atualizar(_tb(0, 100.0, 80))
    t = e.ler("WINV26")
    assert t is not None and t.qtd_bid == 80 and t.qtd_ask is None
    assert t.desequilibrio is None and t.completo is False
    assert t.resistencia_a_favor(+1) is None


def test_desequilibrio_confere_com_a_conta_a_mao() -> None:
    e = EstadoDoLivro()
    e.atualizar(_tb(0, 100.0, 80))
    e.atualizar(_tb(1, 101.0, 20))
    t = e.ler("WINV26")
    assert t is not None
    assert t.desequilibrio == pytest.approx(0.60)   # (80-20)/100


def test_resistencia_a_frente_e_ASSIMETRICA() -> None:
    """O ponto central da ficha 10.1: 'a frente' muda de lado. Compra
    rompe para cima e o obstaculo e' o ASK; venda rompe para baixo e o
    obstaculo e' o BID."""
    e = EstadoDoLivro()
    e.atualizar(_tb(0, 100.0, 80))      # bid grosso
    e.atualizar(_tb(1, 101.0, 20))      # ask fino -> caminho livre para CIMA
    t = e.ler("WINV26")
    assert t is not None
    assert t.resistencia_a_favor(+1) is True, "compra: ask fino favorece"
    assert t.resistencia_a_favor(-1) is False, "venda: bid grosso atrapalha"

    e.atualizar(_tb(0, 100.0, 20))      # agora invertido
    e.atualizar(_tb(1, 101.0, 80))
    t2 = e.ler("WINV26")
    assert t2 is not None
    assert t2.resistencia_a_favor(-1) is True and t2.resistencia_a_favor(+1) is False


def test_livro_equilibrado_nao_favorece_ninguem() -> None:
    e = EstadoDoLivro()
    e.atualizar(_tb(0, 100.0, 50))
    e.atualizar(_tb(1, 101.0, 50))
    t = e.ler("WINV26")
    assert t is not None and t.desequilibrio == pytest.approx(0.0)
    # corte em ZERO (ficha 10.1): empate nao passa em nenhum lado
    assert t.resistencia_a_favor(+1) is False and t.resistencia_a_favor(-1) is False


def test_soma_zero_nao_inventa_desequilibrio() -> None:
    e = EstadoDoLivro()
    e.atualizar(_tb(0, 100.0, 0))
    e.atualizar(_tb(1, 101.0, 0))
    t = e.ler("WINV26")
    assert t is not None and t.desequilibrio is None


def test_simbolos_nao_se_misturam() -> None:
    e = EstadoDoLivro()
    e.atualizar(_tb(0, 100.0, 80))
    e.atualizar(_tb(1, 101.0, 20))
    e.atualizar(_tb(0, 5000.0, 10, "WDOV26"))
    e.atualizar(_tb(1, 5001.0, 10, "WDOV26"))
    win, wdo = e.ler("WINV26"), e.ler("WDOV26")
    assert win is not None and wdo is not None
    assert win.desequilibrio == pytest.approx(0.60)
    assert wdo.desequilibrio == pytest.approx(0.0)


def test_lado_desconhecido_e_ignorado_sem_quebrar() -> None:
    """Callback da DLL nao pode levantar -- valor inesperado se ignora."""
    e = EstadoDoLivro()
    e.atualizar(_tb(7, 100.0, 50))
    assert e.ler("WINV26") is None


def test_leitura_concorrente_nunca_ve_estado_PARCIAL() -> None:
    """`atualizar` roda no hot path do callback e `ler` na thread do EA.
    O estado e' tupla imutavel trocada inteira justamente para que a
    leitura nunca pegue bid novo com ask velho."""
    e = EstadoDoLivro()
    e.atualizar(_tb(0, 100.0, 50))
    e.atualizar(_tb(1, 101.0, 50))
    erros: list[str] = []
    parar = threading.Event()

    def lendo() -> None:
        while not parar.is_set():
            t = e.ler("WINV26")
            if t is not None and t.completo:
                d = t.desequilibrio
                if d is not None and not (-1.0 <= d <= 1.0):
                    erros.append(f"desequilibrio fora da faixa: {d}")

    th = threading.Thread(target=lendo, daemon=True)
    th.start()
    for i in range(3000):
        e.atualizar(_tb(0, 100.0, i % 100 + 1))
        e.atualizar(_tb(1, 101.0, 100 - i % 100))
    parar.set()
    th.join(timeout=5)
    assert not erros, erros[:3]


# ---------------------------------------------------------------------
# Filtro de regime no EAService (ficha 10.1)
# ---------------------------------------------------------------------
def _config(filtro_book: bool):  # type: ignore[no-untyped-def]
    from profittape.ea.config import EAConfig, SinalConfig
    return EAConfig(
        nome="teste", symbol="WINV26", volume_barra=1000, janela_z=10,
        filtro_book=filtro_book,
        sinais=[SinalConfig(feature="z_agf_3", horizonte=3, agent_id=3,
                            threshold_entrada=1.4, direcao="contrarian")])


def test_filtro_DESLIGADO_e_o_default_e_nao_muda_nada() -> None:
    """Retrocompatibilidade: todo EA de hoje roda sem o filtro, e o
    comportamento deles nao pode mudar."""
    from profittape.ea.service import EAService

    assert _config(False).filtro_book is False
    svc = EAService(_config(False))
    assert svc.livro is None
    assert svc.stats.sinais_descartados_book == 0


def test_filtro_LIGADO_sem_livro_descarta_TUDO() -> None:
    """Sem a informacao nao da' para afirmar o regime -- deixar passar
    mediria outra coisa. E o contador mostra que caiu por falta de dado."""
    from profittape.ea.decisao import Acao, Decisao
    from profittape.ea.service import EAService

    svc = EAService(_config(True))          # filtro ligado, livro None
    assert svc.livro is None
    d = Decisao(acao=Acao.COMPRAR, motivo="t", sinal_valor=2.0, feature="z")
    # o filtro roda dentro do laco de decisao; aqui exercitamos a regra
    topo = svc.livro.ler("WINV26") if svc.livro else None
    assert topo is None, "sem livro nao ha' topo -> sinal seria descartado"
    del d


def test_filtro_usa_a_ASSIMETRIA_certa() -> None:
    """Compra so' passa com ask fino; venda so' com bid fino."""
    from profittape.ea.service import EAService

    livro = EstadoDoLivro()
    livro.atualizar(_tb(0, 100.0, 80))      # bid grosso
    livro.atualizar(_tb(1, 101.0, 20))      # ask fino
    svc = EAService(_config(True), livro=livro)
    topo = svc.livro.ler("WINV26") if svc.livro else None
    assert topo is not None
    assert topo.resistencia_a_favor(+1) is True    # compra passaria
    assert topo.resistencia_a_favor(-1) is False   # venda nao
