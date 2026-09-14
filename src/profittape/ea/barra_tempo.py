"""
Barra de TEMPO para o EA de preco (passo 1 do F5 do 123, EAS_DE_PRECO.md 5.4).

O EA de fluxo fecha barra por VOLUME (ConstrutorDeSinalAoVivo). O 123
roda em M15: barras alinhadas ao relogio da bolsa, hh:00 / hh:15 /
hh:30 / hh:45, iguais as que o grafico do Profit plota e as que os
dumps de 10 anos usaram na ficha. A mesma `BarraFechada` sai daqui --
`agf` vazio (o 123 nao usa) e, novidade, o volume agredido POR LADO,
que e' o insumo da porta de volume (passo 6).

ALINHAMENTO
-----------
`ts_ns` e' epoch UTC (domain/events.py). A grade de 15 min coincide em
UTC e em Sao Paulo porque o fuso e' inteiro (-03:00): o inicio de uma
barra e' `ts_ns - ts_ns % periodo_ns`. Por isso este construtor exige
que o periodo DIVIDA uma hora -- 5, 15, 30, 60 min valem; 7 min nao
(a grade local e a UTC divergiriam). Periodo fora disso e' erro de
construcao, nao aviso.

FECHAMENTO
----------
Uma barra fecha de dois jeitos, os dois devolvendo a `BarraFechada`:

1. pelo TRADE: chega o primeiro trade cujo ts_ns cai numa barra
   posterior -- a barra em formacao fecha ANTES desse trade entrar na
   nova (mesma regra do construtor de volume);
2. pelo RELOGIO: `avancar_relogio(ts_ns)` com um instante alem da
   fronteira e nenhum trade novo -- a barra fecha com o que tem. E' o
   caminho do fim de sessao e de qualquer buraco sem negocio; o EA
   chama isto no tick de 0,5 s do record. Sem isso a ultima barra do
   dia nunca fecharia e o 123 nunca veria o fechamento das 17:45.

Buraco: se entre uma barra e a seguinte passar mais de um periodo sem
trade, NAO se inventa barra vazia -- o grafico do Profit tambem nao
plota barra sem negocio no WIN (medido: 37,5 barras/pregao nos dumps,
nunca 38 com buraco). `bar_id` e' o indice da fronteira (inicio //
periodo), entao o salto fica visivel em quem consome.

ORDEM DOS TRADES
----------------
Pre-condicao: ts_ns nao decrescente (a do callback e do parquet). Um
trade com ts_ns ANTERIOR ao inicio da barra em formacao e' um defeito
do feed; nao e' silenciado -- levanta, porque uma barra M15 com trade
de outra barra dentro e' exatamente o que faria o EA discordar do
grafico sem ninguem perceber.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.enums import TradeType
from .sinal import BarraFechada

_BUY = int(TradeType.AGGRESSOR_BUYER)
_SELL = int(TradeType.AGGRESSOR_SELLER)
_NS_POR_S = 1_000_000_000


class TradeForaDeOrdem(ValueError):
    """ts_ns anterior ao inicio da barra em formacao: defeito do feed."""


@dataclass
class _AcumuladorTempo:
    ts_open_ns: int
    ts_close_ns: int          # fronteira EXCLUSIVA: trades com ts >= isto sao da proxima
    open: float | None = None
    high: float = float("-inf")
    low: float = float("inf")
    close: float | None = None
    vol_agr: int = 0
    vol_agr_compra: int = 0
    vol_agr_venda: int = 0
    n_trades: int = 0
    ts_ultimo_ns: int = field(default=0)

    def registrar(self, ts_ns: int, price: float, quantidade: int, trade_type: int) -> None:
        if self.open is None:
            self.open = price
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.n_trades += 1
        self.ts_ultimo_ns = ts_ns
        if trade_type == _BUY:
            self.vol_agr += quantidade
            self.vol_agr_compra += quantidade
        elif trade_type == _SELL:
            self.vol_agr += quantidade
            self.vol_agr_venda += quantidade


class ConstrutorDeBarraDeTempo:
    """Uma instancia por SIMBOLO. `processar_trade` por trade; `avancar_relogio`
    no tick. Os dois devolvem BarraFechada ou None."""

    def __init__(self, periodo_s: int = 900) -> None:
        if periodo_s <= 0 or 3600 % periodo_s != 0:
            raise ValueError(
                f"periodo_s={periodo_s}: precisa dividir uma hora (5, 15, 30, 60 min), "
                "para a grade UTC coincidir com a da bolsa (fuso inteiro)")
        self.periodo_ns = periodo_s * _NS_POR_S
        self._acc: _AcumuladorTempo | None = None
        self.barras_fechadas = 0

    # ------------------------------------------------------------------
    def _inicio_de(self, ts_ns: int) -> int:
        return ts_ns - ts_ns % self.periodo_ns

    def _fechar(self) -> BarraFechada:
        acc = self._acc
        assert acc is not None and acc.open is not None and acc.close is not None
        self.barras_fechadas += 1
        barra = BarraFechada(
            bar_id=acc.ts_open_ns // self.periodo_ns,
            ts_open_ns=acc.ts_open_ns,
            ts_close_ns=acc.ts_close_ns,
            open=acc.open, high=acc.high, low=acc.low, close=acc.close,
            vol_agr=acc.vol_agr, agf={},
            vol_agr_compra=acc.vol_agr_compra, vol_agr_venda=acc.vol_agr_venda,
            n_trades=acc.n_trades,
        )
        self._acc = None
        return barra

    # ------------------------------------------------------------------
    def processar_trade(self, ts_ns: int, price: float, quantidade: int,
                        trade_type: int) -> BarraFechada | None:
        inicio = self._inicio_de(ts_ns)
        fechada = None
        if self._acc is not None:
            if ts_ns < self._acc.ts_open_ns:
                raise TradeForaDeOrdem(
                    f"trade ts={ts_ns} anterior ao inicio da barra em formacao "
                    f"({self._acc.ts_open_ns}): feed fora de ordem")
            if ts_ns >= self._acc.ts_close_ns:
                fechada = self._fechar()
        if self._acc is None:
            self._acc = _AcumuladorTempo(ts_open_ns=inicio, ts_close_ns=inicio + self.periodo_ns)
        self._acc.registrar(ts_ns, price, quantidade, trade_type)
        return fechada

    def avancar_relogio(self, agora_ns: int) -> BarraFechada | None:
        """Fecha a barra em formacao se o relogio ja' passou da fronteira dela
        e nenhum trade novo chegou para faze-lo. Nao abre barra nova."""
        if self._acc is not None and agora_ns >= self._acc.ts_close_ns:
            return self._fechar()
        return None

    @property
    def em_formacao(self) -> _AcumuladorTempo | None:
        return self._acc
