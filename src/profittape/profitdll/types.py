"""
Estruturas ctypes espelhando os tipos do ProfitDLL.

Delphi usa PWideChar (UTF-16) em toda a interface, por isso c_wchar_p em todo
lugar. Trocar por c_char_p devolve lixo silenciosamente — nao ha excecao, so
dado errado.
"""

from __future__ import annotations

from ctypes import Structure, c_int, c_wchar_p


class TAssetIDRec(Structure):
    """Identificador de ativo passado por valor em todos os callbacks."""

    _fields_ = (
        ("ticker", c_wchar_p),
        ("bolsa", c_wchar_p),
        ("feed", c_int),
    )

    def as_tuple(self) -> tuple[str, str]:
        """(symbol, exchange), ja normalizado contra ponteiro nulo."""
        return (self.ticker or "", self.bolsa or "")
