"""
Nucleo PURO do EA de ignicao: detecta no tape e decide a saida pela
barreira. Sem I/O, sem relogio de parede, sem livro -- o servico cuida
disso. A semantica e' a de `research/ignicao.py`, e o teste de
equivalencia compara os DOIS LADOS no mesmo tape (skill forward, 3).

DETECCAO: a cada negocio, referencia = ULTIMO negocio com ts <= t - janela
(o proprio negocio nunca e' referencia). |preco - referencia| >= limiar,
com t em [inicio + janela, fim) BRT e fora do refratario -> ignicao.

SAIDA (posicao aberta), a cada negocio, NESTA ORDEM:
  1. tempo:  t - t_deteccao > tempo_max   (estrito: a barreira ainda vale
             no instante exato, como no estudo, que inclui ts == t + h)
  2. alvo:   (preco - p_deteccao) * lado >= alvo
  3. stop:   (preco - p_deteccao) * lado <= -stop
  4. fim do dia: hora >= zerar_ate
A barreira e' medida a partir do preco de DETECCAO (o do estudo); o P&L,
a partir dos fills. A diferenca entre os dois e' o deslizamento.

DIFERENCAS CONHECIDAS PARA O ESTUDO (documentadas, nao corrigidas):
- Ignicao com posicao aberta e' `ignorada_posicionado` (1 contrato). O
  estudo contava eventos sobrepostos (refratario 30 min < barreira 60).
- Negocio mais antigo que o ultimo processado e' descartado
  (`fora_de_ordem`): edicoes da B3 chegam com o timestamp ORIGINAL (ver
  bridge._medir_atraso). O estudo deduplicava por trade_id ficando com a
  edicao, na posicao do tempo original.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Any

from .config_ignicao import EAIgnicaoConfig
from .sinal_microprice import _OFFSET_BRT_S

_NS = 1_000_000_000
_DIA_NS = 86_400 * _NS


def ns_do_dia_brt(ts_ns: int) -> int:
    return (ts_ns + _OFFSET_BRT_S * _NS) % _DIA_NS


def _hhmm_ns(hhmm: int) -> int:
    return ((hhmm // 100) * 3600 + (hhmm % 100) * 60) * _NS


def ancora_de(ts_ns: int, ancoras_hhmm: list[int], janela_min: int) -> str | None:
    """'HH:MM' se o negocio cai nos `janela_min` minutos depois de uma ancora
    (minuto truncado, como na tabela do estudo)."""
    minuto = ns_do_dia_brt(ts_ns) // (60 * _NS)
    for a in ancoras_hhmm:
        am = (a // 100) * 60 + a % 100
        if am <= minuto < am + janela_min:
            return f"{a // 100:02d}:{a % 100:02d}"
    return None


@dataclass(frozen=True)
class IgnicaoDetectada:
    ts_ns: int
    direcao: int            # +1 alta, -1 queda
    mov_pts: float          # com sinal
    preco: float            # preco do negocio de deteccao
    referencia: float
    ancora: str | None


@dataclass(frozen=True)
class Entrada:
    ignicao: IgnicaoDetectada


@dataclass(frozen=True)
class Saida:
    motivo: str             # alvo / stop / tempo / fim_do_dia
    preco_tape: float       # negocio que disparou
    ts_ns: int


@dataclass
class PosicaoIgnicao:
    ignicao: IgnicaoDetectada
    preco_fill: float
    ts_entrada_ns: int

    @property
    def lado(self) -> int:
        return self.ignicao.direcao


@dataclass
class StatsIgnicao:
    detectadas: int = 0
    ignoradas: Counter[str] = field(default_factory=Counter)
    fora_de_ordem: int = 0
    operacoes: int = 0
    saidas: Counter[str] = field(default_factory=Counter)
    pnl_bruto: float = 0.0
    pnl_liquido: float = 0.0
    desliz_entrada_soma: float = 0.0
    desliz_saida_soma: float = 0.0
    por_ancora: Counter[str] = field(default_factory=Counter)


class DetectorIgnicao:
    def __init__(self, cfg: EAIgnicaoConfig) -> None:
        self.cfg = cfg
        self._jan = int(cfg.janela_s * _NS)
        self._ini = _hhmm_ns(cfg.inicio_hhmm) + self._jan
        self._fim = _hhmm_ns(cfg.fim_hhmm)
        self._hist: deque[tuple[int, float]] = deque()
        self._ultimo_ts = 0
        self._livre_desde = 0
        self.fora_de_ordem = 0

    def novo_trade(self, ts: int, preco: float) -> IgnicaoDetectada | None:
        if ts < self._ultimo_ts:
            self.fora_de_ordem += 1
            return None
        self._ultimo_ts = ts
        h = self._hist
        h.append((ts, preco))
        limite = ts - self._jan
        while len(h) >= 2 and h[1][0] <= limite:
            h.popleft()
        if h[0][0] > limite:                  # ainda sem uma janela de historia
            return None
        ref = h[0][1]
        mov = preco - ref
        if abs(mov) < self.cfg.limiar_pts - 1e-9:
            return None
        nd = ns_do_dia_brt(ts)
        if not (self._ini <= nd < self._fim) or ts < self._livre_desde:
            return None
        self._livre_desde = ts + int(self.cfg.refratario_s * _NS)
        return IgnicaoDetectada(ts, 1 if mov > 0 else -1, mov, preco, ref,
                                ancora_de(ts, self.cfg.ancoras_hhmm,
                                          self.cfg.ancora_janela_min))


class DecisorIgnicao:
    def __init__(self, cfg: EAIgnicaoConfig) -> None:
        self.cfg = cfg
        self.detector = DetectorIgnicao(cfg)
        self.posicao: PosicaoIgnicao | None = None
        self.stats = StatsIgnicao()
        self._zerar_ns = _hhmm_ns(cfg.zerar_ate_hhmm)

    # -------------------------------------------------------------- saida
    def checar_saida(self, ts: int, preco: float | None) -> Saida | None:
        """`preco` None = checagem so' de tempo (tick sem negocio)."""
        p = self.posicao
        if p is None:
            return None
        ign = p.ignicao
        if ts - ign.ts_ns > self.cfg.tempo_max_s * _NS:
            return Saida("tempo", preco if preco is not None else ign.preco, ts)
        if preco is not None:
            fav = (preco - ign.preco) * p.lado
            if fav >= self.cfg.alvo_pts - 1e-9:
                return Saida("alvo", preco, ts)
            if fav <= -self.cfg.stop_pts + 1e-9:
                return Saida("stop", preco, ts)
        if ns_do_dia_brt(ts) >= self._zerar_ns:
            return Saida("fim_do_dia", preco if preco is not None else ign.preco, ts)
        return None

    # ------------------------------------------------------------ negocio
    def novo_trade(self, ts: int, preco: float) -> list[Entrada | Saida]:
        """Saida primeiro, depois deteccao (um negocio pode fechar uma
        posicao e disparar a proxima, como no estudo, que conta os dois)."""
        acoes: list[Entrada | Saida] = []
        antes = self.detector.fora_de_ordem
        ign = self.detector.novo_trade(ts, preco)
        if self.detector.fora_de_ordem > antes:
            self.stats.fora_de_ordem += 1
            return acoes
        s = self.checar_saida(ts, preco)
        if s is not None:
            acoes.append(s)
        if ign is not None:
            self.stats.detectadas += 1
            posicionado = self.posicao is not None and s is None
            if posicionado:
                self.stats.ignoradas["posicionado"] += 1
            elif self.stats.operacoes >= self.cfg.max_operacoes_dia:
                self.stats.ignoradas["limite_dia"] += 1
            else:
                acoes.append(Entrada(ign))
        return acoes

    # ------------------------------------------------------- contabilidade
    def abrir(self, ign: IgnicaoDetectada, preco_fill: float, ts: int) -> None:
        self.posicao = PosicaoIgnicao(ign, preco_fill, ts)
        self.stats.operacoes += 1
        self.stats.desliz_entrada_soma += (preco_fill - ign.preco) * ign.direcao

    def fechar(self, preco_fill: float, ts: int, motivo: str,
               preco_tape: float) -> dict[str, Any]:
        p = self.posicao
        assert p is not None
        bruto = (preco_fill - p.preco_fill) * p.lado
        liquido = bruto - self.cfg.custo_pontos_estimado
        desliz_saida = (preco_tape - preco_fill) * p.lado      # >0 = pior que o tape
        s = self.stats
        s.saidas[motivo] += 1
        s.pnl_bruto += bruto
        s.pnl_liquido += liquido
        s.desliz_saida_soma += desliz_saida
        s.por_ancora[f"{p.ignicao.ancora or 'fora'}:{motivo}"] += 1
        self.posicao = None
        return {"lado": p.lado, "motivo": motivo, "ancora": p.ignicao.ancora,
                "ts_deteccao": p.ignicao.ts_ns,
                "preco_deteccao": p.ignicao.preco, "entrada": p.preco_fill,
                "saida": preco_fill, "saida_tape": preco_tape,
                "desliz_entrada": (p.preco_fill - p.ignicao.preco) * p.lado,
                "desliz_saida": desliz_saida,
                "pnl_bruto": bruto, "pnl_liquido": liquido,
                "duracao_s": round((ts - p.ts_entrada_ns) / _NS, 1)}

    def resumo(self) -> dict[str, Any]:
        s = self.stats
        n = sum(s.saidas.values())
        return {"detectadas": s.detectadas, "operacoes": s.operacoes,
                "ignoradas": dict(s.ignoradas), "fora_de_ordem": s.fora_de_ordem,
                "saidas": dict(s.saidas), "posicionado": self.posicao is not None,
                "pnl_bruto_pts": round(s.pnl_bruto, 1),
                "pnl_liquido_pts": round(s.pnl_liquido, 1),
                "desliz_entrada_medio": round(s.desliz_entrada_soma / s.operacoes, 1)
                if s.operacoes else None,
                "desliz_saida_medio": round(s.desliz_saida_soma / n, 1) if n else None,
                "por_ancora": dict(s.por_ancora)}
