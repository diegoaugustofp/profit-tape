"""
Prioridade BAIXA para comandos de pesquisa/ferramentas que rodam NA MESMA
maquina do `record` (2026-10-01, v4.10).

Contexto (docs/OPERACAO.md, ACHADO 2026-10-01): as 14:22 BRT a entrega de
trades da DLL parou ~9,5 min e voltou em rajada (atraso medido 634 s) com o
processo vivo, `login_ok` e `corretora_pronta` verdadeiros. A causa esta' EM
ABERTO (a hipotese do gerador de niveis foi enfraquecida pelas datas dos
arquivos). Isto NAO e' a correcao desse incidente: e' higiene barata -- um
comando de pesquisa nao deve disputar CPU/disco com o record. Nada foi
perdido (volume M5 do tape = Profit), mas as EAs ficaram cegas 10 min.

O `record` NUNCA chama isto: so' os comandos de pesquisa. Teste estrutural
garante as duas coisas (tests/test_prioridade.py).

Windows: PROCESS_MODE_BACKGROUND_BEGIN baixa prioridade de CPU, de I/O e de
memoria do PROPRIO processo de uma vez; se falhar, BELOW_NORMAL. Os prototipos
da API sao declarados (HANDLE e' ponteiro: sem `argtypes`, o pseudo-handle -1
de GetCurrentProcess seria passado como int de 32 bits e a chamada falharia
em x64). POSIX: nice +10.
"""

from __future__ import annotations

import os
import sys

import structlog

log = structlog.get_logger(__name__)

_BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
_PROCESS_MODE_BACKGROUND_BEGIN = 0x00100000
_APLICADA: str | None = None


def baixa_prioridade() -> str:
    """Baixa a prioridade do processo atual. Idempotente. Devolve o modo
    aplicado: 'windows_background', 'windows_below_normal', 'nice' ou
    'indisponivel' (nunca levanta: falhar em baixar prioridade nao pode
    impedir o comando de rodar)."""
    global _APLICADA
    if _APLICADA is not None:
        return _APLICADA
    modo = "indisponivel"
    try:
        if sys.platform == "win32":
            import ctypes

            k32 = ctypes.windll.kernel32
            k32.GetCurrentProcess.restype = ctypes.c_void_p
            k32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            k32.SetPriorityClass.restype = ctypes.c_int
            h = k32.GetCurrentProcess()
            if k32.SetPriorityClass(h, _PROCESS_MODE_BACKGROUND_BEGIN):
                modo = "windows_background"
            elif k32.SetPriorityClass(h, _BELOW_NORMAL_PRIORITY_CLASS):
                modo = "windows_below_normal"
        elif hasattr(os, "nice"):
            os.nice(10)
            modo = "nice"
    except Exception as exc:
        log.warning("prioridade.falhou", erro=repr(exc))
    _APLICADA = modo
    log.info("prioridade.baixa", modo=modo, nota="comando de pesquisa; o record nao e' afetado")
    return modo
