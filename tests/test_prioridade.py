"""Prioridade baixa dos comandos de pesquisa (v4.10) e a garantia de que o
`record` nunca a aplica."""

from __future__ import annotations

import inspect
import os
import sys

import pytest

from profittape import prioridade


@pytest.fixture(autouse=True)
def _zera_idempotencia(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prioridade, "_APLICADA", None)


class _Fn:
    """Funcao fake da kernel32: registra chamadas e aceita argtypes/restype."""

    def __init__(self, retornos: list[int]) -> None:
        self.retornos = list(retornos)
        self.calls: list[tuple[object, ...]] = []
        self.argtypes = None
        self.restype = None

    def __call__(self, *a: object) -> int:
        self.calls.append(a)
        return self.retornos.pop(0) if self.retornos else 0


class _Kernel32:
    def __init__(self, set_priority: list[int]) -> None:
        self.GetCurrentProcess = _Fn([-1])      # pseudo-handle
        self.SetPriorityClass = _Fn(set_priority)


class _Windll:
    def __init__(self, k32: _Kernel32) -> None:
        self.kernel32 = k32


def test_posix_usa_nice_10(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas: list[int] = []
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(os, "nice", lambda n: chamadas.append(n) or n, raising=False)
    assert prioridade.baixa_prioridade() == "nice"
    assert chamadas == [10]


def test_windows_tenta_background_e_so_cai_para_below_normal_se_falhar(
        monkeypatch: pytest.MonkeyPatch) -> None:
    import ctypes

    k32 = _Kernel32([1])                    # background aceito de primeira
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "windll", _Windll(k32), raising=False)
    assert prioridade.baixa_prioridade() == "windows_background"
    assert [c[1] for c in k32.SetPriorityClass.calls] == [0x00100000]
    # HANDLE e' ponteiro: prototipo declarado (sem isso x64 falha com o pseudo-handle -1)
    assert k32.SetPriorityClass.argtypes is not None and k32.GetCurrentProcess.restype is not None

    monkeypatch.setattr(prioridade, "_APLICADA", None)
    k32b = _Kernel32([0, 1])                # background recusado, below_normal aceito
    monkeypatch.setattr(ctypes, "windll", _Windll(k32b), raising=False)
    assert prioridade.baixa_prioridade() == "windows_below_normal"
    assert [c[1] for c in k32b.SetPriorityClass.calls] == [0x00100000, 0x00004000]

    monkeypatch.setattr(prioridade, "_APLICADA", None)
    k32c = _Kernel32([0, 0])                # as duas recusadas: nao levanta
    monkeypatch.setattr(ctypes, "windll", _Windll(k32c), raising=False)
    assert prioridade.baixa_prioridade() == "indisponivel"


def test_idempotente_e_nunca_levanta(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas: list[int] = []
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(os, "nice", lambda n: chamadas.append(n) or n, raising=False)
    assert prioridade.baixa_prioridade() == "nice"
    assert prioridade.baixa_prioridade() == "nice"
    assert chamadas == [10]                  # a 2a chamada nao baixa de novo

    monkeypatch.setattr(prioridade, "_APLICADA", None)

    def estoura(_n: int) -> int:
        raise PermissionError("sem permissao")
    monkeypatch.setattr(os, "nice", estoura, raising=False)
    assert prioridade.baixa_prioridade() == "indisponivel"


COMANDOS_DE_PESQUISA = {
    "vwapvp-conferir", "vwapvp-ntsl-equivalencia", "vwapvp-ntsl-setupb", "ea-vwapvp-taxa",
    "ea-vwapvp-sonda", "ea-vwapvp-regra", "ea-vwapvp-servico-replay", "ea-vwapvp-replay",
}


def _fontes() -> dict[str, str]:
    from profittape.cli import app

    out = {}
    for c in app.registered_commands:
        nome = c.name or c.callback.__name__.replace("_", "-")
        out[nome] = inspect.getsource(c.callback)
    return out


def test_todo_comando_de_pesquisa_baixa_a_prioridade() -> None:
    fontes = _fontes()
    faltando = COMANDOS_DE_PESQUISA - set(fontes)
    assert not faltando, f"comandos que sumiram do CLI: {faltando}"
    sem = [n for n in COMANDOS_DE_PESQUISA if "baixa_prioridade()" not in fontes[n]]
    assert not sem, f"comandos de pesquisa sem baixa_prioridade(): {sem}"


def test_o_record_nunca_baixa_a_propria_prioridade() -> None:
    fontes = _fontes()
    assert "record" in fontes
    assert "baixa_prioridade" not in fontes["record"]
    import profittape.recorder.service as svc
    assert "baixa_prioridade" not in inspect.getsource(svc)
