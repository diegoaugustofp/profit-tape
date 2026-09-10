"""
Versao do arquivo da ProfitDLL, pelos metadados do PE (Windows).

A DLL nao exporta funcao de versao. O que existe e' o VERSIONINFO do
arquivo, o mesmo que o Explorer mostra em Propriedades > Detalhes. Aqui
via `version.dll` (GetFileVersionInfoW / VerQueryValueW), ctypes puro,
sem pywin32.

Por que importa: a versao da DLL e' parte do carimbo de qualquer
resultado. O changelog da 4.0.0.42 (2026-09-11) corrige "atraso na
entrega das callbacks de ordem" -- a latencia que o E2 mede. Um numero
de latencia sem a versao da DLL ao lado nao diz nada.

Fora do Windows devolve None (o sandbox de desenvolvimento e' Linux).
"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path


def versao_arquivo(caminho: str | Path) -> str | None:
    if sys.platform != "win32":
        return None
    p = str(caminho)
    if not Path(p).exists():
        return None
    try:
        ver = ctypes.windll.version
        tam = ver.GetFileVersionInfoSizeW(p, None)
        if not tam:
            return None
        buf = ctypes.create_string_buffer(tam)
        if not ver.GetFileVersionInfoW(p, 0, tam, buf):
            return None
        ptr = ctypes.c_void_p()
        n = ctypes.c_uint()
        if not ver.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(n)):
            return None
        # VS_FIXEDFILEINFO: dwFileVersionMS em offset 8, dwFileVersionLS em 12
        ffi = (ctypes.c_uint32 * (n.value // 4)).from_address(ptr.value or 0)
        ms, ls = ffi[2], ffi[3]
        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
    except Exception:
        return None
