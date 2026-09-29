"""
VWAP DE SESSAO incremental com bandas de desvio (F1 do EA `vwap_vp`,
docs/eas/vwap_vp.md, 2026-09-29).

O que e'
--------
`vwap = sum(p*v) / sum(v)` desde o primeiro negocio registrado; a banda
`k` e' `vwap +- k * sd`, com `sd = sqrt(sum(v*(p-vwap)^2) / sum(v))` --
desvio PONDERADO PELO VOLUME, populacional (divide por sum(v), nao por
n-1). E' a definicao que os graficos plotam ("VWAP bands"); confira a
mao em `tests/test_vwap_sessao.py` antes de mudar.

O(1) por negocio: guarda tres somas. Serve ao hot path do EA (um
`registrar` por trade) e ao replay.

POR QUE HA' UM PRECO DE REFERENCIA
----------------------------------
Com precos ~140.000 e volume de milhoes, `sum(v*p^2)` chega a 1e16 e a
variancia (~1e5) sai da subtracao de dois numeros de 1e10: perde-se
~6 casas. Guardando `p - p0` (p0 = primeiro preco) as somas ficam
pequenas e a variancia nao muda (invariante a translacao). O `vwap`
soma `p0` de volta na saida.

QUAIS NEGOCIOS ENTRAM e' decisao de quem chama (D3 da ficha: todos --
agressao, RLP e leilao -- para bater com o que o Profit plota). Esta
classe nao filtra tipo; instancie duas para comparar conjuntos.
"""

from __future__ import annotations

import math
from typing import Any


class VWAPSessao:
    __slots__ = ("_p0", "_sv", "_sv_d", "_sv_d2", "n")

    def __init__(self) -> None:
        self._p0: float | None = None
        self._sv = 0.0         # sum(v)
        self._sv_d = 0.0       # sum(v * (p - p0))
        self._sv_d2 = 0.0      # sum(v * (p - p0)^2)
        self.n = 0
        self.reiniciar()

    # ------------------------------------------------------------ entrada
    def registrar(self, price: float, quantidade: int | float) -> None:
        if quantidade <= 0:
            return                      # edicao/cancelamento nao entra
        if self._p0 is None:
            self._p0 = float(price)
        d = float(price) - self._p0
        v = float(quantidade)
        self._sv += v
        self._sv_d += v * d
        self._sv_d2 += v * d * d
        self.n += 1

    def reiniciar(self) -> None:
        self._p0 = None
        self._sv = self._sv_d = self._sv_d2 = 0.0
        self.n = 0

    # -------------------------------------------------------------- saida
    @property
    def volume(self) -> float:
        return self._sv

    @property
    def vwap(self) -> float | None:
        if self._p0 is None or self._sv <= 0:
            return None
        return self._p0 + self._sv_d / self._sv

    @property
    def variancia(self) -> float | None:
        """sum(v*(p-vwap)^2)/sum(v) = E[d^2] - E[d]^2 com d = p - p0."""
        if self._p0 is None or self._sv <= 0:
            return None
        m = self._sv_d / self._sv
        var = self._sv_d2 / self._sv - m * m
        return var if var > 0 else 0.0     # ruido de ponto flutuante nunca vira negativo

    @property
    def desvio(self) -> float | None:
        var = self.variancia
        return None if var is None else math.sqrt(var)

    def banda(self, k: float) -> tuple[float, float] | None:
        """(inferior, superior) = vwap -+ k*sd. None antes do primeiro negocio."""
        vw, sd = self.vwap, self.desvio
        if vw is None or sd is None:
            return None
        return (vw - k * sd, vw + k * sd)

    def resumo(self, bandas: tuple[float, ...] = (1.0, 2.0)) -> dict[str, Any]:
        out: dict[str, Any] = {"n": self.n, "volume": self.volume,
                               "vwap": self.vwap, "sd": self.desvio}
        for k in bandas:
            b = self.banda(k)
            out[f"inf_{k:g}sd"], out[f"sup_{k:g}sd"] = (None, None) if b is None else b
        return out
