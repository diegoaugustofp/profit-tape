"""
Codigos do ProfitDLL.

ATENCAO: estes valores mudam entre versoes da DLL. Confira contra o manual da
SUA versao antes de confiar em qualquer analise que dependa deles. O script
`scripts/verify_capture.py` imprime a distribuicao empirica de cada codigo
observado — se aparecer valor fora deste enum, a sua versao difere e a tabela
precisa ser corrigida aqui.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum


class TradeType(IntEnum):
    """Classificacao do negocio no tape."""

    DESCONHECIDO = 0
    CROSS = 1
    AGRESSOR_COMPRADOR = 2
    AGRESSOR_VENDEDOR = 3
    LEILAO = 4
    SURVEILLANCE = 5
    EXPIT = 6
    EXERCICIO_OPCAO = 7
    BALCAO = 8
    RLP = 32

    @property
    def is_agressao_continua(self) -> bool:
        """
        True apenas para negocio de mercado continuo com agressor identificado.

        Leilao, balcao, exercicio e RLP NAO sao agressao no sentido de
        microestrutura: leilao e' batimento por preco unico e RLP e' contraparte
        de varejo. Incluir esses no order flow imbalance contamina o sinal — por
        isso a distincao mora aqui, e nao espalhada pelo codigo de feature.
        """
        return self in (TradeType.AGRESSOR_COMPRADOR, TradeType.AGRESSOR_VENDEDOR)

    @property
    def signo(self) -> int:
        """+1 agressao compradora, -1 vendedora, 0 nao aplicavel."""
        if self is TradeType.AGRESSOR_COMPRADOR:
            return 1
        if self is TradeType.AGRESSOR_VENDEDOR:
            return -1
        return 0


class BookAction(IntEnum):
    """Acao aplicada ao livro no callback de offer book."""

    ADD = 0
    EDIT = 1
    DELETE = 2
    DELETE_FROM = 3
    FULL_BOOK = 4


class BookSide(IntEnum):
    BID = 0
    ASK = 1


class ConnState(IntEnum):
    """Tipo de estado reportado pelo StateCallback."""

    LOGIN = 0
    ROTEAMENTO = 1
    MARKET_DATA = 2
    ATIVACAO = 3


class Stream(StrEnum):
    """Fluxos gravaveis. O valor vira nome de diretorio na particao."""

    TRADE = "trade"
    BOOK_OFFER = "book_offer"
    BOOK_PRICE = "book_price"
    TINY_BOOK = "tiny_book"
