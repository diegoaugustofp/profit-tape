"""
Eventos de mercado.

Por que NamedTuple e nao dataclass: estes objetos sao construidos DENTRO do
callback da DLL, no caminho mais quente do sistema. NamedTuple e' implementado
em C, aloca uma tupla simples e nao executa `__init__` escrito em Python. Um
dataclass comum custa varias vezes mais por instancia. Em rajada de abertura
essa diferenca decide se o callback devolve o controle a tempo.

Todos os campos sao primitivos. Nada de parsing pesado aqui — conversao de
tipo e' trabalho do writer, que roda em outra thread.
"""

from __future__ import annotations

from typing import NamedTuple


class Trade(NamedTuple):
    """Um negocio do tape."""

    ts_ns: int          # timestamp do evento, epoch em nanossegundos (UTC)
    ts_recv_ns: int     # quando NOS recebemos — a diferenca e' a latencia do feed
    symbol: str
    exchange: str
    trade_id: int
    price: float
    volume_financeiro: float
    quantidade: int
    agente_comprador: int
    agente_vendedor: int
    trade_type: int
    is_edit: bool


class BookDelta(NamedTuple):
    """
    Uma operacao no offer book (order-by-order).

    Guardamos o DELTA, nao o snapshot. Reconstruir o livro a partir do delta e'
    responsabilidade de quem le, offline. Gravar snapshot a cada evento
    multiplicaria o volume em disco por duas ordens de grandeza sem adicionar
    informacao nenhuma.
    """

    ts_ns: int
    ts_recv_ns: int
    symbol: str
    exchange: str
    action: int         # BookAction
    side: int           # BookSide
    position: int       # posicao na fila (0 = topo)
    offer_id: int
    price: float
    quantidade: int
    agente: int
    has_price: bool
    has_qtd: bool


class PriceLevel(NamedTuple):
    """Nivel agregado do price book (soma das ofertas naquele preco)."""

    ts_ns: int
    ts_recv_ns: int
    symbol: str
    exchange: str
    action: int
    side: int
    position: int
    price: float
    quantidade: int
    n_ofertas: int


class TinyBook(NamedTuple):
    """Melhor bid/ask. Barato e suficiente para muita coisa."""

    ts_recv_ns: int
    symbol: str
    exchange: str
    side: int
    price: float
    quantidade: int
