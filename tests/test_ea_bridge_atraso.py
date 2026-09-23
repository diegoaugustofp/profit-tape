"""Atraso do EA em relacao ao mercado, medido na saida da fila (17/09).

Por que existe: foi atraso de processamento que fragmentou a barra do EA
de preco. No EA de FLUXO o efeito e' pior e nunca foi medido -- a barra de
VOLUME fecha por contagem de contratos, entao atraso/perda muda ONDE a
barra fecha, ou seja, o proprio evento. Sem medir, qualquer arquitetura
de fila seria chute.
"""

from __future__ import annotations

import time
from typing import Any

from profittape.ea.bridge import EABridge


class _ServicoFalso:
    def __init__(self, symbol: str = "WINFUT") -> None:
        class _Cfg:
            pass
        self.config = _Cfg()
        self.config.symbol = symbol  # type: ignore[attr-defined]
        self.vistos: list[Any] = []

    def processar_trade_bruto(self, t: Any) -> None:
        self.vistos.append(t)

    def encerrar_dia(self) -> None:
        pass

    def _hb(self) -> dict[str, Any]:
        return {"trades": len(self.vistos)}


class _Trade:
    def __init__(self, ts_ns: int) -> None:
        self.ts_ns = ts_ns
        self.is_edit = False
        self.symbol = "WINFUT"
        self.price = 140000.0
        self.quantidade = 1
        self.trade_type = 2
        self.agente_comprador = 0
        self.agente_vendedor = 0
        self.trade_id = 1


def test_atraso_e_medido_e_reportado() -> None:
    b = EABridge(_ServicoFalso())  # type: ignore[arg-type]
    agora = time.time()
    b._medir_atraso(_Trade(int((agora - 120) * 1e9)))    # 2 min atras
    b._medir_atraso(_Trade(int((agora - 60) * 1e9)))     # 1 min atras
    a = b.atraso()
    assert a["trades_medidos"] == 2
    assert 118 < a["atraso_max_s"] < 122
    assert 88 < a["atraso_medio_s"] < 92


def test_relogio_do_feed_a_frente_e_ignorado() -> None:
    b = EABridge(_ServicoFalso())  # type: ignore[arg-type]
    b._medir_atraso(_Trade(int((time.time() + 60) * 1e9)))
    assert b.atraso()["trades_medidos"] == 0 and b.atraso()["atraso_max_s"] == 0.0


def test_trade_sem_ts_nao_conta() -> None:
    b = EABridge(_ServicoFalso())  # type: ignore[arg-type]
    b._medir_atraso(_Trade(0))
    assert b.atraso()["trades_medidos"] == 0


def test_alerta_sai_uma_vez_por_minuto() -> None:
    b = EABridge(_ServicoFalso())  # type: ignore[arg-type]
    b._medir_atraso(_Trade(int((time.time() - 30) * 1e9)))
    b._alertar_atraso()
    primeiro = b._ultimo_alerta_atraso
    assert primeiro > 0
    b._alertar_atraso()                                  # nao repete
    assert b._ultimo_alerta_atraso == primeiro


def test_sem_atraso_nao_alerta() -> None:
    b = EABridge(_ServicoFalso())  # type: ignore[arg-type]
    b._medir_atraso(_Trade(int((time.time() - 1) * 1e9)))
    b._alertar_atraso()
    assert b._ultimo_alerta_atraso == 0.0


def test_maximo_do_dia_diz_de_QUE_negocio_veio() -> None:
    """22/09: o resumo trouxe `atraso_max_dia_s=5575` com o WINFUT rodando a
    2-5 s o dia inteiro, e nao houve como investigar. Minhas duas hipoteses
    (print de leilao; negocio de outro ticker) foram derrubadas pelo dado.
    Agora o maximo carrega o negocio que o produziu."""
    b = EABridge(_ServicoFalso())  # type: ignore[arg-type]
    agora = time.time()
    b._medir_atraso(_Trade(int((agora - 3) * 1e9)))
    velho = _Trade(int((agora - 5575) * 1e9))
    velho.trade_id = 987654
    velho.trade_type = 4
    b._medir_atraso(velho)
    b._medir_atraso(_Trade(int((agora - 1) * 1e9)))
    assert 5574 < b._atraso_max_dia_s < 5576
    info = b._atraso_max_dia_info
    assert info["trade_id"] == 987654 and info["trade_type"] == 4
    assert info["symbol"] == "WINFUT" and info["ts_evento"] < info["ts_medido"]


def test_maximo_do_dia_sobrevive_ao_reset_da_janela_com_a_procedencia() -> None:
    b = EABridge(_ServicoFalso())  # type: ignore[arg-type]
    b._medir_atraso(_Trade(int((time.time() - 42) * 1e9)))
    b._ultimo_periodico = 0.0
    b._alertar_atraso()                       # zera a JANELA
    assert b.atraso()["trades_medidos"] == 0
    assert 41 < b._atraso_max_dia_s < 43 and b._atraso_max_dia_info["trade_id"] == 1


def test_negocio_EDITADO_nao_entra_na_metrica() -> None:
    """A B3 corrige negocios e a DLL entrega a correcao com o TIMESTAMP
    ORIGINAL: em 22 e 23/09 isso virou 'atraso' de 5.575 s e 509 s em UM
    negocio, com os milhares da mesma janela em 2 s. Correcao nao atrasa
    sinal -- o EA ja' processou o original."""
    b = EABridge(_ServicoFalso())  # type: ignore[arg-type]
    normal = _Trade(int((time.time() - 2) * 1e9))
    b._medir_atraso(normal)
    edicao = _Trade(int((time.time() - 509) * 1e9))
    edicao.is_edit = True
    b._medir_atraso(edicao)
    assert b._edicoes_ignoradas == 1
    assert b._atraso_max_dia_s < 5              # a edicao NAO virou maximo
    assert b.atraso()["trades_medidos"] == 1


def test_procedencia_do_maximo_marca_se_era_edicao() -> None:
    b = EABridge(_ServicoFalso())  # type: ignore[arg-type]
    b._medir_atraso(_Trade(int((time.time() - 7) * 1e9)))
    assert b._atraso_max_dia_info["is_edit"] is False
