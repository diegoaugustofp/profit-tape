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

FIM DE SESSAO (medido em 28/08/2026, `barra-tempo-conferir`)
-----------------------------------------------------------
O grafico do Profit NAO abre barra nova a partir do fim da sessao: os
negocios de 18:30 em diante (fechamento, after) sao DOBRADOS na barra
18:15, que fica com o ultimo preco do dia como close. Sem esta regra o
EA fechava 38 barras identicas ao grafico e uma 39a que o grafico nao
tem, e a 18:15 do EA discordava no close. `fim_sessao_hhmm=1830`: trade
cuja barra comecaria a partir dai' entra na barra em formacao do mesmo
dia. Para o 123 isso nao muda sinal (ultima entrada 16:30) -- muda a
continuidade dos indicadores, que e' o que a ficha exige igual ao grafico.

PRIMEIRA BARRA (criterio final, 17/09: a ABERTURA DO CONTINUO)
--------------------------------------------------------------
O leilao de abertura pode prorrogar -- em 16/09 o primeiro negocio saiu
09:02:54. A barra 09:00 nao esta' incompleta por isso: o mercado nao
negociou, nao houve nada a perder. O tape marca leilao com
`trade_type=4` (AUCTION, enum confirmado contra o profitTypes oficial),
entao a ABERTURA DO CONTINUO e' observavel no proprio dado: o primeiro
trade que nao e' leilao. Criterio: a primeira barra e' PARCIAL se o
construtor comecou DEPOIS da abertura do continuo. Sem `inicio_ns`
(pesquisa/replay puro), cai no criterio antigo (primeiro trade > 60 s).

Historico do criterio: primeiro foi "1o trade veio tarde" (marcava a
09:00 de 16/09 como parcial e matava o dia); depois "construtor comecou
depois do inicio da BARRA" (marcava parcial quando o leilao prorrogava).

PRIMEIRA BARRA (versao anterior, mantida para replay sem inicio_ns)
-------------------------------------------------------------------
A primeira barra que o construtor fecha pode estar PARCIAL: o processo
pode ter subido no meio dela. O criterio certo e' o INICIO DO
CONSTRUTOR, nao a chegada do primeiro negocio: se `inicio_ns` <=
ts_open da barra, nada foi perdido e a barra e' COMPLETA, ainda que o
primeiro print tenha vindo 90 s depois (leilao de abertura, assinatura
demorando). Bug real de 16/09: EA de pe' desde 08:18, a barra 09:00
saiu `parcial` porque o 1o trade veio > 60 s depois -> `dia_incompleto`
-> nenhum sinal no dia inteiro, sem motivo.
Sem `inicio_ns` (replay, pesquisa) cai no criterio antigo: primeiro
trade mais de `tolerancia_parcial_s` depois do inicio da barra -- e' o
que conferiu 69/69 contra o grafico e continua valendo ali.
A parcial nao serve para GEOMETRIA (open/high/low); o close dela esta'
certo e alimenta a MME normalmente.

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
from datetime import datetime
from zoneinfo import ZoneInfo

from ..domain.enums import TradeType
from .sinal import BarraFechada

_TZ_BOLSA = ZoneInfo("America/Sao_Paulo")

_BUY = int(TradeType.AGGRESSOR_BUYER)
_SELL = int(TradeType.AGGRESSOR_SELLER)
_LEILAO = int(TradeType.AUCTION)
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
    vol_total: int = 0
    n_trades: int = 0
    ts_ultimo_ns: int = field(default=0)
    ts_primeiro_ns: int = field(default=0)
    maior_lacuna_ns: int = 0        # maior intervalo sem negocio dentro da barra
    ts_continuo_ns: int = 0         # 1o trade que NAO e' leilao (abertura do continuo)

    def registrar(self, ts_ns: int, price: float, quantidade: int, trade_type: int) -> None:
        if trade_type != _LEILAO and self.ts_continuo_ns == 0:
            self.ts_continuo_ns = ts_ns
        if self.open is None:
            self.open = price
            self.ts_primeiro_ns = ts_ns
        else:
            self.maior_lacuna_ns = max(self.maior_lacuna_ns, ts_ns - self.ts_ultimo_ns)
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.n_trades += 1
        self.vol_total += quantidade
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

    def __init__(self, periodo_s: int = 900, fim_sessao_hhmm: int | None = 1830,
                 tolerancia_parcial_s: int = 60, lacuna_maxima_s: int = 5,
                 inicio_ns: int | None = None) -> None:
        if periodo_s <= 0 or 3600 % periodo_s != 0:
            raise ValueError(
                f"periodo_s={periodo_s}: precisa dividir uma hora (5, 15, 30, 60 min), "
                "para a grade UTC coincidir com a da bolsa (fuso inteiro)")
        self.periodo_ns = periodo_s * _NS_POR_S
        self.fim_sessao_hhmm = fim_sessao_hhmm
        self.tolerancia_parcial_ns = tolerancia_parcial_s * _NS_POR_S
        # VOLUME CONFIAVEL (medido 11/09/2026): tape com buraco subconta volume
        # com OHLC identico -- e subcontar empurra o gate de volume para
        # "baixo". No WIN ha' negocio a cada segundo no pregao: lacuna > 5 s
        # dentro da barra marca volume_confiavel=False (o gate trata como
        # indefinido). Parcial tambem e' nao confiavel (faltou o comeco).
        self.lacuna_maxima_ns = lacuna_maxima_s * _NS_POR_S
        self.inicio_ns = inicio_ns          # ao vivo: quando o construtor subiu
        self._acc: _AcumuladorTempo | None = None
        self.barras_fechadas = 0

    @staticmethod
    def _local(ts_ns: int) -> datetime:
        return datetime.fromtimestamp(ts_ns / _NS_POR_S, tz=_TZ_BOLSA)

    def _e_parcial(self, acc: _AcumuladorTempo) -> bool:
        """Parcial = o construtor comecou DEPOIS da abertura do continuo
        (ou, sem `inicio_ns`, o 1o trade veio muito depois do inicio da
        barra). Leilao prorrogado NAO torna a barra parcial."""
        if self.inicio_ns is None:
            return acc.ts_primeiro_ns - acc.ts_open_ns > self.tolerancia_parcial_ns
        referencia = acc.ts_continuo_ns or acc.ts_primeiro_ns or acc.ts_open_ns
        return self.inicio_ns > max(referencia, acc.ts_open_ns)

    def _dobra_no_fim_de_sessao(self, ts_ns: int) -> bool:
        """True se um trade em ts_ns pertence a` barra em formacao por
        convencao de fim de sessao (mesmo dia local, hora >= fim)."""
        if self.fim_sessao_hhmm is None or self._acc is None:
            return False
        t = self._local(ts_ns)
        if t.hour * 100 + t.minute < self.fim_sessao_hhmm:
            return False
        return t.date() == self._local(self._acc.ts_open_ns).date()

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
            n_trades=acc.n_trades, vol_total=acc.vol_total,
            ts_primeiro_ns=acc.ts_primeiro_ns,
            parcial=(self.barras_fechadas == 1 and self._e_parcial(acc)),
            maior_lacuna_s=round(acc.maior_lacuna_ns / _NS_POR_S, 3),
        )
        barra.volume_confiavel = (not barra.parcial
                                  and acc.maior_lacuna_ns <= self.lacuna_maxima_ns)
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
                if self._dobra_no_fim_de_sessao(ts_ns):
                    self._acc.ts_close_ns = inicio + self.periodo_ns   # estende a barra
                else:
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
