"""Incidente de 18/09: Modern Standby congelou o record por 26 min, e a
metrica de atraso confundiu silencio com atraso. Os tres testes cobrem as
tres correcoes."""

from __future__ import annotations

import sys
import time
from typing import Any

import pytest

from profittape.ea.bridge import EABridge
from profittape.infra import energia


def test_manter_acordado_pede_as_tres_flags_no_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas: list[int] = []

    class _K32:
        def SetThreadExecutionState(self, flags: int) -> int:
            chamadas.append(flags)
            return 0x80000000

    class _Windll:
        kernel32 = _K32()

    import ctypes
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "windll", _Windll(), raising=False)
    assert energia.manter_acordado() is True
    f = chamadas[0]
    # DISPLAY_REQUIRED e' o que segura o Modern Standby (disparado pela tela)
    assert f & energia.ES_CONTINUOUS and f & energia.ES_SYSTEM_REQUIRED
    assert f & energia.ES_DISPLAY_REQUIRED
    energia.liberar()
    assert chamadas[-1] == energia.ES_CONTINUOUS


def test_fora_do_windows_e_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    assert energia.manter_acordado() is False


class _Servico:
    def __init__(self) -> None:
        class _C:
            symbol = "WINFUT"
        self.config = _C()

    def processar_trade_bruto(self, t: Any) -> None:
        pass

    def encerrar_dia(self) -> None:
        pass

    def _hb(self) -> dict[str, Any]:
        return {}


class _T:
    def __init__(self, ts_ns: int) -> None:
        self.ts_ns = ts_ns


def test_resumo_do_dia_nao_some_com_o_reset_da_janela() -> None:
    """18/09: a linha periodica zerava os contadores, e o `finalizado` do
    fim do dia (mercado fechado) mostrava atraso 0 e medidos 0."""
    b = EABridge(_Servico())  # type: ignore[arg-type]
    b._medir_atraso(_T(int((time.time() - 8) * 1e9)))
    b._ultimo_periodico = 0.0             # forca a janela a fechar
    b._alertar_atraso()                   # loga e ZERA a janela
    assert b.atraso()["trades_medidos"] == 0          # janela zerada...
    assert b._atraso_max_dia_s > 7 and b._atraso_n_dia == 1   # ...o dia nao


def test_atraso_do_servico_e_a_idade_do_trade_nao_o_silencio(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """Silencio (nenhum trade chegando) NAO e' atraso. O atraso e' a idade
    do trade no instante em que ele e' processado."""
    from profittape.ea import service_123 as sv
    s = sv.EA123Service.__new__(sv.EA123Service)
    s.ao_vivo = True
    s.trades = 0
    s._ultimo_ts_ns = 0
    s._atraso_ultimo_s = 0.0

    class _C:
        def processar_trade(self, *a: Any) -> None:
            return None

    class _Ciclo:
        def on_trade(self, *a: Any) -> None:
            pass

    s.construtor = _C()
    s.ciclo = _Ciclo()
    agora = [1_000_000.0]
    monkeypatch.setattr(sv.time, "time", lambda: agora[0])
    s.processar_trade_bruto(sv._TradeBruto(int((agora[0] - 0.5) * 1e9), 1.0, 1, 2))
    assert s._atraso_ultimo_s == pytest.approx(0.5, abs=1e-3)
    agora[0] += 300.0                      # 5 min de SILENCIO, nenhum trade
    assert s._atraso_ultimo_s == pytest.approx(0.5, abs=1e-3)   # nao cresceu
