"""
Decisor do EA VWAP + VP (continuacao a tarde). Estado do dia: posicao,
cooldown desde o ultimo sinal operado, limites. Nao executa nada; o
servico executa e chama `abrir` / `fechar`.

Dois pontos de decisao, como no simulador (`research/vwapvp_replay.py`,
`_simular_episodio`):

    avaliar_barra(b, vwap, sd)  -> COMPRAR / VENDER no fechamento da barra
    avaliar_preco(price, ts)    -> ZERAR por alvo, stop, tempo ou zeragem,
                                   a cada negocio

A diferenca declarada em relacao ao simulador: la' a entrada e' o close da
barra e alvo/stop sao conferidos em high/low da barra seguinte; aqui a
entrada e' o fill (dry_run: primeiro negocio apos o fechamento) e alvo/
stop sao conferidos negocio a negocio. O replay pelo servico
(`ea-vwapvp-servico-replay`) MEDE essa diferenca no mesmo dia.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from .config_vwapvp import EAVwapVpConfig
from .decisao import Acao
from .sinal import BarraFechada

_TZ = ZoneInfo("America/Sao_Paulo")
_NS = 1_000_000_000


def hhmm_de(ts_ns: int) -> int:
    t = dt.datetime.fromtimestamp(ts_ns / 1e9, tz=_TZ)
    return t.hour * 100 + t.minute


@dataclass
class PosicaoVwapVp:
    lado: int                 # +1 comprado, -1 vendido
    preco_entrada: float
    ts_entrada_ns: int
    alvo_px: float
    stop_px: float
    z_sinal: float
    sd_sinal: float
    dist_sinal: float
    hhmm_sinal: int


@dataclass(frozen=True)
class AvaliacaoVwapVp:
    acao: Acao
    motivo: str
    lado: int = 0
    z: float | None = None
    sd: float | None = None
    dist: float | None = None
    alvo_px: float | None = None
    stop_px: float | None = None
    hhmm_barra: int = 0       # abertura da barra de sinal (rotulo do Profit)


@dataclass
class EstatisticasVwapVp:
    operacoes: int = 0
    ganhos: int = 0
    pnl_bruto: float = 0.0
    pnl_liquido: float = 0.0
    perdas_seguidas: int = 0
    bloqueado: str | None = None
    saidas: Counter[str] = field(default_factory=Counter)
    filtros: Counter[str] = field(default_factory=Counter)
    sinais: int = 0            # barras que satisfizeram o evento (operadas ou nao)
    duracao_soma_s: float = 0.0


class DecisorVwapVp:
    def __init__(self, cfg: EAVwapVpConfig) -> None:
        self.cfg = cfg
        self.posicao: PosicaoVwapVp | None = None
        self.stats = EstatisticasVwapVp()
        self._ultimo_sinal_ns: int | None = None
        self._pendente: AvaliacaoVwapVp | None = None   # sinal aguardando o fill

    # ------------------------------------------------------------- sinal
    def avaliar_barra(self, b: BarraFechada, vwap: float | None,
                      sd: float | None) -> AvaliacaoVwapVp:
        """No fechamento da barra. Devolve COMPRAR/VENDER quando o evento vale
        e o dia permite; senao NADA com o motivo contado em `filtros`."""
        cfg, s = self.cfg, self.stats
        if vwap is None or sd is None or sd <= 0:
            return self._nada("sem_vwap")
        z = (b.close - vwap) / sd
        if abs(z) < cfg.z_banda:
            return self._nada("fora_da_banda", contar=False)
        s.sinais += 1
        hhmm = hhmm_de(b.ts_open_ns)
        if not (cfg.janela_inicio_hhmm <= hhmm < cfg.janela_fim_hhmm):
            return self._nada("fora_da_janela")
        lado = 1 if z > 0 else -1
        if cfg.lado_permitido == "compra" and lado < 0:
            return self._nada("lado_nao_permitido")
        if cfg.lado_permitido == "venda" and lado > 0:
            return self._nada("lado_nao_permitido")
        if s.bloqueado:
            return self._nada("bloqueado")
        if self.posicao is not None or self._pendente is not None:
            return self._nada("posicionado")
        if s.operacoes >= cfg.max_operacoes_dia:
            return self._nada("max_operacoes")
        if (self._ultimo_sinal_ns is not None
                and b.ts_close_ns - self._ultimo_sinal_ns < cfg.cooldown_s * _NS):
            return self._nada("cooldown")
        dist = abs(b.close - vwap)
        if dist <= 0:
            return self._nada("sem_distancia")
        alvo_px = b.close + lado * cfg.alvo_sd * sd
        stop_px = b.close - lado * cfg.stop_frac_dist * dist
        self._ultimo_sinal_ns = b.ts_close_ns
        av = AvaliacaoVwapVp(Acao.COMPRAR if lado > 0 else Acao.VENDER,
                             f"z={z:+.2f} >= {cfg.z_banda:g} na barra {hhmm:04d}",
                             lado=lado, z=z, sd=sd, dist=dist, alvo_px=alvo_px, stop_px=stop_px,
                             hhmm_barra=hhmm)
        self._pendente = av
        return av

    def _nada(self, motivo: str, contar: bool = True) -> AvaliacaoVwapVp:
        if contar:
            self.stats.filtros[motivo] += 1
        return AvaliacaoVwapVp(Acao.NADA, motivo)

    # ------------------------------------------------------------ posicao
    def abrir(self, preco_fill: float, ts_ns: int) -> PosicaoVwapVp:
        """Fill chegou. Alvo e stop sao os do SINAL (close da barra), nao do
        fill: e' o que o simulador fez, e manter os niveis fixos deixa a
        diferenca de fill visivel no P&L em vez de escondida nos niveis."""
        av = self._pendente
        assert av is not None and av.alvo_px is not None and av.stop_px is not None
        assert av.z is not None and av.sd is not None and av.dist is not None
        self.posicao = PosicaoVwapVp(av.lado, preco_fill, ts_ns, av.alvo_px, av.stop_px,
                                     av.z, av.sd, av.dist, av.hhmm_barra)
        self._pendente = None
        return self.posicao

    def cancelar_pendente(self) -> None:
        self._pendente = None

    def avaliar_preco(self, price: float, ts_ns: int) -> AvaliacaoVwapVp:
        """A cada negocio com posicao aberta: alvo, stop, tempo, zeragem."""
        p = self.posicao
        if p is None:
            return AvaliacaoVwapVp(Acao.NADA, "sem_posicao")
        if (p.lado > 0 and price <= p.stop_px) or (p.lado < 0 and price >= p.stop_px):
            return AvaliacaoVwapVp(Acao.ZERAR, "stop")
        if (p.lado > 0 and price >= p.alvo_px) or (p.lado < 0 and price <= p.alvo_px):
            return AvaliacaoVwapVp(Acao.ZERAR, "alvo")
        if ts_ns - p.ts_entrada_ns >= self.cfg.tempo_max_s * _NS:
            return AvaliacaoVwapVp(Acao.ZERAR, "tempo")
        if hhmm_de(ts_ns) >= self.cfg.zeragem_hhmm:
            return AvaliacaoVwapVp(Acao.ZERAR, "zeragem")
        return AvaliacaoVwapVp(Acao.NADA, "mantem")

    def fechar(self, preco: float, ts_ns: int, motivo: str) -> dict[str, float | int | str]:
        assert self.posicao is not None, "fechar sem posicao"
        cfg, p, s = self.cfg, self.posicao, self.stats
        bruto = (preco - p.preco_entrada) * p.lado
        liquido = bruto - cfg.custo_pontos_estimado
        dur_s = (ts_ns - p.ts_entrada_ns) / _NS
        s.operacoes += 1
        s.ganhos += liquido > 0
        s.pnl_bruto += bruto
        s.pnl_liquido += liquido
        s.duracao_soma_s += dur_s
        s.saidas[motivo] += 1
        s.perdas_seguidas = 0 if liquido > 0 else s.perdas_seguidas + 1
        if s.perdas_seguidas >= cfg.max_perdas_seguidas:
            s.bloqueado = f"{s.perdas_seguidas} perdas seguidas"
        elif s.pnl_liquido <= -cfg.perda_max_dia_pontos:
            s.bloqueado = f"perda do dia {s.pnl_liquido:.0f} pts"
        self.posicao = None
        return {"lado": p.lado, "entrada": p.preco_entrada, "saida": preco,
                "pnl_bruto": round(bruto, 1), "pnl_liquido": round(liquido, 1),
                "duracao_s": round(dur_s, 1), "motivo": motivo,
                "alvo_px": p.alvo_px, "stop_px": p.stop_px,
                "z_sinal": round(p.z_sinal, 3), "sd_sinal": round(p.sd_sinal, 1),
                "dist_sinal": round(p.dist_sinal, 1), "hhmm_sinal": p.hhmm_sinal}

    def resumo(self) -> dict[str, object]:
        s = self.stats
        return {"sinais": s.sinais, "operacoes": s.operacoes,
                "pct_ganho": round(100 * s.ganhos / s.operacoes, 1) if s.operacoes else None,
                "pnl_bruto_pts": round(s.pnl_bruto, 1),
                "pnl_liquido_pts": round(s.pnl_liquido, 1),
                "duracao_media_s": (round(s.duracao_soma_s / s.operacoes, 1)
                                    if s.operacoes else None),
                "saidas": dict(s.saidas), "bloqueado": s.bloqueado,
                "sinais_filtrados": dict(s.filtros),
                "posicionado": self.posicao is not None}
