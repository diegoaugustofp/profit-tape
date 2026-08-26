"""
Construcao de barra ao vivo e calculo do sinal em tempo real.

Reproduz, trade a trade, EXATAMENTE as mesmas formulas do research
(bars.atribuir_barras, flow.calcular, normalize.zscore_rolante) -- streaming
em vez de batch sobre parquet. Isto e' deliberado: qualquer divergencia entre
o que foi VALIDADO e o que RODA e' o tipo de bug que so' aparece com dinheiro
real em jogo.

DECISAO DE DESIGN que nao muda: volume_barra e janela_z vem de EAConfig,
carregados do config CONGELADO que o research validou -- nunca recalculados
ao vivo (sugerir_volume_barra sobre dado do dia mudaria o threshold e
invalidaria a comparacao com o sinal testado).
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

# trade_type de agressao (compra/venda a mercado) -- mesmos codigos de
# features/bars.py _AGRESSAO. Repetido aqui (nao importado) de proposito: o
# modulo ea/ nao deve depender de features/ em tempo de execucao — captura e
# trading sao processos separados por design (ver __init__.py).
_AGRESSAO = (2, 3)


@dataclass
class BarraFechada:
    """Uma barra completa, pronta para decisao.decidir()."""
    bar_id: int
    ts_open_ns: int
    ts_close_ns: int
    open: float
    high: float
    low: float
    close: float
    vol_agr: int
    agf: dict[int, float]      # agente_id -> z-score do agf, SO' p/ agentes rastreados


@dataclass
class _AcumuladorBarra:
    """Estado da barra EM FORMACAO — reseta a cada fechamento."""
    ts_open_ns: int | None = None
    open: float | None = None
    high: float = float("-inf")
    low: float = float("inf")
    close: float | None = None
    vol_agr: int = 0
    comprado_por_agente: dict[int, int] = field(default_factory=dict)
    vendido_por_agente: dict[int, int] = field(default_factory=dict)

    def registrar(self, ts_ns: int, price: float, quantidade: int,
                 trade_type: int, agente_comprador: int, agente_vendedor: int) -> None:
        if self.ts_open_ns is None:
            self.ts_open_ns = ts_ns
            self.open = price
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        if trade_type in _AGRESSAO:
            self.vol_agr += quantidade
            self.comprado_por_agente[agente_comprador] = (
                self.comprado_por_agente.get(agente_comprador, 0) + quantidade
            )
            self.vendido_por_agente[agente_vendedor] = (
                self.vendido_por_agente.get(agente_vendedor, 0) + quantidade
            )


class ConstrutorDeSinalAoVivo:
    """
    Uma instancia por SIMBOLO. Alimentada trade a trade via processar_trade();
    devolve uma BarraFechada (com os z-scores ja calculados) toda vez que uma
    barra de volume_barra contratos se completa, ou None caso contrario.

    agentes_rastreados: os agent_id que aparecem em EAConfig.sinais — so'
    esses tem z-score de agf calculado (equivalente a flow.calcular+normalize
    do research, mas so' para os agentes que o EA realmente usa, nao o
    top-N inteiro).
    """

    def __init__(self, volume_barra: int, janela_z: int,
                agentes_rastreados: list[int]) -> None:
        if volume_barra <= 0:
            raise ValueError("volume_barra precisa ser positivo — vem do "
                             "config CONGELADO do research, nunca recalculado")
        self.volume_barra = volume_barra
        self.janela_z = janela_z
        self.agentes_rastreados = list(agentes_rastreados)

        # BUG REAL corrigido (2026-08-26, pego pelo teste de equivalencia):
        # bars.atribuir_barras usa bar_local = cum_prev // volume_barra, onde
        # cum_prev e' a soma cumulativa GLOBAL do dia (nunca resetada por
        # barra) — o "excesso" de uma barra (fechar com 82 em vez de 80, por
        # exemplo) CARREGA para a proxima, que precisa de so' 78 para
        # completar, nao 80 de novo. A primeira versao deste modulo zerava
        # o contador a cada fechamento, perdendo o carregamento — o erro
        # se acumulava barra a barra ate' desalinhar tudo (batch e streaming
        # discordavam ja' na barra 3 de um teste com apenas 3000 trades).
        self._cum_total = 0            # NUNCA resetado — e' o cum_prev do batch
        self._bar_local_atual = 0
        self._acumulador = _AcumuladorBarra()
        # Buffer circular por agente — mesma janela que normalize.zscore_rolante
        # usaria em batch. maxlen descarta o mais antigo sozinho.
        self._historico_agf: dict[int, deque[float]] = {
            aid: deque(maxlen=janela_z) for aid in agentes_rastreados
        }
        self._min_periods = max(2, janela_z // 2)   # espelha normalize.py

    def processar_trade(self, ts_ns: int, price: float, quantidade: int,
                        trade_type: int, agente_comprador: int,
                        agente_vendedor: int) -> BarraFechada | None:
        """
        Chamar para CADA trade recebido do callback, na ordem em que chegam
        (mesma pre-condicao de bars.atribuir_barras: ts_ns crescente).

        bar_local deste trade e' determinado por cum_total ANTES dele (mesmo
        "cum_prev" do batch) — se isso mudou em relacao a' barra que estava
        sendo acumulada, a barra ANTERIOR esta completa e e' devolvida ANTES
        deste trade ser processado na barra nova.
        """
        bar_local_deste_trade = self._cum_total // self.volume_barra

        fechada = None
        if bar_local_deste_trade != self._bar_local_atual:
            fechada = self._fechar()
            self._bar_local_atual = bar_local_deste_trade
            self._acumulador = _AcumuladorBarra()

        self._acumulador.registrar(ts_ns, price, quantidade, trade_type,
                                   agente_comprador, agente_vendedor)
        if trade_type in _AGRESSAO:
            self._cum_total += quantidade

        return fechada

    def _fechar(self) -> BarraFechada:
        acc = self._acumulador
        agf: dict[int, float] = {}
        for aid in self.agentes_rastreados:
            comprado = acc.comprado_por_agente.get(aid, 0)
            vendido = acc.vendido_por_agente.get(aid, 0)
            bruto = (comprado - vendido) / acc.vol_agr if acc.vol_agr else 0.0

            hist = self._historico_agf[aid]
            if len(hist) >= self._min_periods:
                media = sum(hist) / len(hist)
                var = sum((x - media) ** 2 for x in hist) / (len(hist) - 1)
                desvio = math.sqrt(var)
                agf[aid] = (bruto - media) / desvio if desvio > 0 else float("nan")
            else:
                agf[aid] = float("nan")   # mesmo min_periods de normalize.py
            hist.append(bruto)            # SO' apos calcular o z — anti-lookahead

        barra = BarraFechada(
            bar_id=self._bar_local_atual,
            ts_open_ns=acc.ts_open_ns or 0,
            ts_close_ns=acc.ts_open_ns or 0,
            open=acc.open or 0.0, high=acc.high, low=acc.low,
            close=acc.close or 0.0, vol_agr=acc.vol_agr, agf=agf,
        )
        return barra
