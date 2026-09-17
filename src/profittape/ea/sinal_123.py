"""
Sinal do 123 ao vivo (passo 3 do F5, EAS_DE_PRECO.md 5.4) sobre a barra de
TEMPO: no fechamento de cada barra M15, decide se ARMA um candidato --
lado, entrada (stop de rompimento), stop e alvo -- valido SO' durante a
barra seguinte. Quem manda a ordem, cancela no fim de t+1 e cuida da
posicao e' o ciclo de ordens (passo 4); quem filtra por fluxo e' o gate
(passo 5). Este modulo so' aplica a formula.

A FORMULA E' A DO RESEARCH, IMPORTADA: `eas_preco.avaliar_123`. O teste
de equivalencia roda `marcar_123` (vetorizada, a dos 10 anos) e este
modulo sobre as mesmas barras e exige os mesmos candidatos.

REGRAS QUE SO' EXISTEM AO VIVO (decididas 2026-09-15)
------------------------------------------------------
- DIA INCOMPLETO: se a primeira barra vista no dia nao e' a 09:00 (o
  processo subiu tarde), a MME80 fica fora pelos closes que faltaram
  (15 pts medidos em 11/09, decaindo em ~11 pregoes). O dia nao arma
  sinal; a MME continua sendo atualizada para chegar convergida no dia
  seguinte. `ea.dia_incompleto` no log, com a hora da primeira barra.
- BARRA PARCIAL: alimenta a MME (close certo) mas nao entra na janela
  de 3 barras (geometria errada); a janela recomeca depois dela.
- REGIME: `close(t) > MME80(t)` com a MME JA' atualizada pelo close de t
  -- e' o que o Profit plota na propria barra e o que o research usou.
- Nada de posicao aqui: "posicao aberta ignora sinal" e' do ciclo.
"""

from __future__ import annotations

import datetime as dt
from collections import deque
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from ..research.eas_preco import avaliar_123
from .semente import IndicadorMME
from .sinal import BarraFechada

log = structlog.get_logger(__name__)
_TZ = ZoneInfo("America/Sao_Paulo")
_NS = 1_000_000_000
HHMM_ABERTURA = 900


@dataclass(frozen=True)
class Candidato123:
    lado: str                  # compra | venda
    entrada: float             # nivel da ordem STOP de entrada
    stop: float                # nivel do stop de protecao
    alvo: float                # nivel da limitada de alvo
    D_pts: float
    barra_sinal_id: int        # bar_id de t
    hhmm_sinal: int            # label da barra t
    valido_ate_ns: int         # fim de t+1: nao executou, cancela
    mme80: float
    regime_ok: bool
    # insumo do gate / registro do sinal (passo 6): fluxo da barra t
    vol_agr_compra_t: int
    vol_agr_venda_t: int
    n_trades_t: int
    vol_total_t: int = 0
    volume_confiavel_t: bool = True
    maior_lacuna_t_s: float = 0.0
    # As TRES barras do padrao (t-2, t-1, t), cada uma com hhmm e OHLC.
    # Sem isto, conferir um sinal no grafico exige adivinhar a janela --
    # em 17/09 a ambiguidade do `hhmm` (que e' a barra t, a ULTIMA) custou
    # meia hora de conferencia e quase mascarou um defeito real.
    janela: tuple[dict[str, Any], ...] = ()

    def resumo(self) -> dict[str, Any]:
        return {"lado": self.lado, "entrada": self.entrada, "stop": self.stop,
                "alvo": self.alvo, "D_pts": self.D_pts, "hhmm": self.hhmm_sinal,
                "bar_id": self.barra_sinal_id, "mme80": round(self.mme80, 2),
                "vol_total_t": self.vol_total_t, "volume_confiavel_t": self.volume_confiavel_t,
                "maior_lacuna_t_s": self.maior_lacuna_t_s, "janela": list(self.janela)}


class SinalPreco123:
    def __init__(self, mme: IndicadorMME, periodo_s: int = 900) -> None:
        self.mme = mme
        self.periodo_ns = periodo_s * _NS
        self._janela: deque[BarraFechada] = deque(maxlen=3)
        self._dia_atual: dt.date | None = None
        self.dia_completo = False
        self.candidatos_armados = 0
        self.barras_vistas = 0

    @staticmethod
    def _local(ts_ns: int) -> dt.datetime:
        return dt.datetime.fromtimestamp(ts_ns / _NS, tz=_TZ)

    def barra_fechada(self, b: BarraFechada) -> Candidato123 | None:
        """Chamar para CADA barra fechada (parcial ou nao), na ordem."""
        self.barras_vistas += 1
        t = self._local(b.ts_open_ns)
        hhmm = t.hour * 100 + t.minute
        if t.date() != self._dia_atual:
            self._dia_atual = t.date()
            self._janela.clear()
            self.dia_completo = (hhmm == HHMM_ABERTURA and not b.parcial)
            if not self.dia_completo:
                log.warning("ea.dia_incompleto", dia=t.date().isoformat(),
                            primeira_barra=hhmm, parcial=b.parcial,
                            nota="MME segue atualizando; nenhum sinal hoje")
        mme = self.mme.atualizar(b.close)          # sempre: close da parcial e' certo
        if b.parcial:
            self._janela.clear()
            return None
        self._janela.append(b)
        if not self.dia_completo or len(self._janela) < 3:
            return None
        b2, b1, b0 = self._janela
        janela = tuple({"hhmm": (lambda t: t.hour * 100 + t.minute)(self._local(b.ts_open_ns)),
                        "open": b.open, "high": b.high, "low": b.low, "close": b.close,
                        "vol_total": b.vol_total, "n_trades": b.n_trades}
                       for b in (b2, b1, b0))
        r = avaliar_123(b2.high, b2.low, b1.high, b1.low, b0.high, b0.low, b0.close, mme, hhmm)
        if r is None:
            return None
        self.candidatos_armados += 1
        c = Candidato123(
            lado=r["lado"], entrada=r["entrada"], stop=r["stop"], alvo=r["alvo"],
            D_pts=r["D_pts"], barra_sinal_id=b0.bar_id, hhmm_sinal=hhmm,
            valido_ate_ns=b0.ts_close_ns + self.periodo_ns, mme80=mme,
            regime_ok=bool(r["regime_ok"]),
            vol_agr_compra_t=b0.vol_agr_compra, vol_agr_venda_t=b0.vol_agr_venda,
            n_trades_t=b0.n_trades, vol_total_t=b0.vol_total,
            volume_confiavel_t=b0.volume_confiavel, maior_lacuna_t_s=b0.maior_lacuna_s,
            janela=janela,
        )
        log.info("ea.sinal_123.armado", **c.resumo())
        return c
