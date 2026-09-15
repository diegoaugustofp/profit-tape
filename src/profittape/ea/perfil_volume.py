"""
Perfil de volume por horario para o gate de volume ao vivo (ficha 12,
EAS_DE_PRECO.md 12): mediana de `vol_total` no mesmo hhmm nos 20 pregoes
ANTERIORES -- a MESMA definicao de `research.eas_preco.perfil_volume_horario`
(o dia corrente nao entra; sem 20 pregoes, indefinido).

De onde vem, como a semente da MME80: o PARQUET do grafico (vol_total por
barra, 10 anos) da' os dias antes do fim do parquet; a PONTE pelo TAPE
(barras do `ConstrutorDeBarraDeTempo`) da' os dias entre o parquet e a
vespera. Ao vivo, cada barra fechada com `volume_confiavel` entra na fila
do seu horario e vale a partir do dia seguinte.

Regra de confianca (decidida 15/09 apos medir 11/09): barra com
`volume_confiavel=False` NAO entra no perfil (subcontaria a mediana) e
NAO passa pelo gate (gate indefinido: sinal fora, contado).
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict, deque
from pathlib import Path
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import structlog

from ..features.pipeline import _carregar_dia
from .barra_tempo import ConstrutorDeBarraDeTempo

log = structlog.get_logger(__name__)
_TZ = ZoneInfo("America/Sao_Paulo")
_NS = 1_000_000_000
JANELA_PREGOES = 20


class PerfilVolumeHorario:
    def __init__(self, janela_pregoes: int = JANELA_PREGOES) -> None:
        self.janela = janela_pregoes
        # janela + 1: o dia CORRENTE pode ja' estar na fila (entra ao fechar a
        # barra, vale amanha) sem expulsar o 20o dia anterior.
        self._fila: dict[int, deque[tuple[dt.date, float]]] = defaultdict(
            lambda: deque(maxlen=janela_pregoes + 1))
        self._hoje: dict[int, tuple[dt.date, float]] = {}   # barras de hoje: valem amanha
        self.dias_carregados: list[str] = []

    # ------------------------------------------------------------- carga
    def registrar(self, dia: dt.date, hhmm: int, vol_total: float, confiavel: bool = True) -> None:
        """Barra FECHADA. Se `dia` e' mais novo que o ultimo da fila daquele
        horario, entra; barras nao confiaveis nao entram."""
        if not confiavel:
            return
        fila = self._fila[hhmm]
        if fila and fila[-1][0] >= dia:
            return                                      # ja' tem este dia (ou mais novo)
        fila.append((dia, float(vol_total)))

    def mediana(self, hhmm: int, dia: dt.date) -> float | None:
        """Mediana dos `janela` pregoes ANTERIORES a `dia` naquele horario;
        None se nao houver `janela` dias completos antes de `dia`."""
        vals = [v for d, v in self._fila[hhmm] if d < dia]
        if len(vals) < self.janela:
            return None
        return float(median(vals[-self.janela:]))

    def resumo(self) -> dict[str, Any]:
        cheios = sum(1 for f in self._fila.values() if len(f) >= self.janela)
        return {"horarios": len(self._fila), "horarios_com_perfil": cheios,
                "janela": self.janela, "dias_carregados": self.dias_carregados[-3:]}


def _barras_do_tape(curated: Path, symbol: str, dia: dt.date,
                    periodo_s: int) -> list[tuple[int, float, bool]]:
    pasta = curated / "trade" / f"dt={dia.isoformat()}"
    if not (pasta / f"sym={symbol}").exists():
        return []
    t = _carregar_dia(pasta, symbol)
    if t.empty:
        return []
    c = ConstrutorDeBarraDeTempo(periodo_s)
    out: list[tuple[int, float, bool]] = []
    for ts_ns, price, qtd, tipo in t[["ts_ns", "price", "quantidade", "trade_type"]].itertuples(
            index=False):
        b = c.processar_trade(int(ts_ns), float(price), int(qtd), int(tipo))
        if b is not None:
            out.append((b.ts_open_ns, float(b.vol_total), b.volume_confiavel))
    fim = c.avancar_relogio(int(t["ts_ns"].to_numpy()[-1]) + periodo_s * _NS)
    if fim is not None:
        out.append((fim.ts_open_ns, float(fim.vol_total), fim.volume_confiavel))
    return out


def construir_perfil(parquet: Path, dia_alvo: dt.date, curated: Path | None = None,
                     symbol: str = "WINFUT", periodo_s: int = 900,
                     janela_pregoes: int = JANELA_PREGOES) -> PerfilVolumeHorario:
    """Perfil para operar em `dia_alvo`: parquet (dias < dia_alvo) + ponte pelo
    tape para os dias uteis depois do fim do parquet. Dias sem tape na
    ponte simplesmente nao entram (o perfil exige 20 dias por horario; um
    dia faltando so' atrasa, nao invalida -- diferente da MME80, que e'
    recursiva)."""
    p = PerfilVolumeHorario(janela_pregoes)
    if parquet.exists():
        h = pd.read_parquet(parquet, columns=["dia", "hhmm", "vol_total"])
        h["dia"] = pd.to_datetime(h["dia"].astype(str)).dt.date
        h = h[h["dia"] < dia_alvo].sort_values(["dia", "hhmm"])
        # so' os ultimos (janela + 5) dias de cada horario interessam
        for dia, hhmm, vol in h[["dia", "hhmm", "vol_total"]].itertuples(index=False):
            p.registrar(dia, int(hhmm), float(vol))
        dias = sorted(h["dia"].unique())
        p.dias_carregados = [d.isoformat() for d in dias[-3:]]
        ultimo = dias[-1] if dias else None
    else:
        ultimo = None
    if curated is not None:
        ini = (ultimo + dt.timedelta(days=1)) if ultimo else dia_alvo - dt.timedelta(days=45)
        d = ini
        while d < dia_alvo:
            if d.weekday() < 5:
                for ts_open, vol, ok in _barras_do_tape(curated, symbol, d, periodo_s):
                    t = pd.Timestamp(ts_open, unit="ns", tz="UTC").tz_convert(_TZ)
                    p.registrar(d, t.hour * 100 + t.minute, vol, ok)
                if _barras_do_tape(curated, symbol, d, periodo_s):
                    p.dias_carregados.append(d.isoformat())
            d += dt.timedelta(days=1)
    log.info("ea.perfil_volume", dia_alvo=dia_alvo.isoformat(), **p.resumo())
    return p
