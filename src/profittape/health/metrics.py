"""
Metricas de captura.

Nao e' enfeite. Numa gravacao que roda sozinha por horas, a unica forma de
saber se o dado presta e' instrumentar enquanto ele passa. Descobrir buraco
tres meses depois, na hora do backtest, e' descobrir tarde.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Snapshot:
    uptime_s: float
    eventos_por_stream: dict[str, int]
    eventos_por_simbolo: dict[str, int]
    linhas_escritas: int
    descartados: int
    taxa_descarte: float
    fila_atual: int
    fila_pico: int
    arquivos_abertos: int
    ultimo_evento_ha_s: float
    escrita_s_total: float


@dataclass
class Metrics:
    inicio: float = field(default_factory=time.monotonic)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _por_stream: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _por_simbolo: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _linhas: int = 0
    _escrita_s: float = 0.0
    _arquivos: int = 0
    _ultimo_evento: float = field(default_factory=time.monotonic)

    def registrar_lote(self, por_stream: dict[str, int]) -> None:
        """
        Chamado pelo WRITER a cada lote processado — custo zero no callback.

        Bug historico: existia um registrar_evento por evento que NINGUEM
        chamava; sem_evento_ha_s subia linearmente com o feed vivo (observado:
        844s "sem evento" com 769k linhas escritas) e por_stream saia vazio.
        Um detector de feed morto que mente e' pior que nenhum — no dia do
        feed morrer de verdade, ninguem acredita nele.
        """
        with self._lock:
            for stream, n in por_stream.items():
                self._por_stream[stream] += n
            if por_stream:
                self._ultimo_evento = time.monotonic()

    def registrar_escrita(self, linhas: int, segundos: float, arquivos_abertos: int) -> None:
        with self._lock:
            self._linhas += linhas
            self._escrita_s += segundos
            self._arquivos = arquivos_abertos

    def snapshot(
        self, fila_atual: int, fila_pico: int, descartados: int, recebidos: int
    ) -> Snapshot:
        with self._lock:
            return Snapshot(
                uptime_s=time.monotonic() - self.inicio,
                eventos_por_stream=dict(self._por_stream),
                eventos_por_simbolo=dict(self._por_simbolo),
                linhas_escritas=self._linhas,
                descartados=descartados,
                taxa_descarte=descartados / recebidos if recebidos else 0.0,
                fila_atual=fila_atual,
                fila_pico=fila_pico,
                arquivos_abertos=self._arquivos,
                ultimo_evento_ha_s=time.monotonic() - self._ultimo_evento,
                escrita_s_total=self._escrita_s,
            )
