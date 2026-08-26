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
    """
    Classificacao do negocio no tape.

    Tabela VALIDADA contra a versao da DLL em uso (2026-08-21), com nomes
    identicos aos do manual para facilitar o cross-reference. Nota historica:
    a primeira versao desta tabela chutava RLP=32; o dado real (25% de um
    pregao de WIN em codigo 13, a fatia tipica do RLP em minicontratos)
    derrubou o chute e o manual confirmou RLP=13 e UNKNOWN=32.
    """

    CROSS_TRADE = 1
    AGGRESSOR_BUYER = 2
    AGGRESSOR_SELLER = 3
    AUCTION = 4
    SURVEILLANCE = 5
    EXPIT = 6
    OPTION_EXERCISE = 7
    OVER_THE_COUNTER = 8
    DERIVATIVE_TERM = 9
    INDEX = 10
    BTC = 11
    ON_BEHALF = 12
    RLP = 13
    BBT = 14
    RFQ = 15
    MPT = 16
    TAC = 17
    TAA = 18
    UNKNOWN = 32
    UPDATE = 33
    MID = 34
    OFF_EXCHANGE = 35

    @property
    def is_agressao_continua(self) -> bool:
        """
        True apenas para negocio de mercado continuo com agressor identificado.

        Leilao, balcao, exercicio e RLP NAO sao agressao no sentido de
        microestrutura: leilao e' batimento por preco unico e RLP e' varejo
        internalizado pelo provedor de liquidez. Incluir esses no order flow
        imbalance contamina o sinal — a distincao mora aqui, num lugar so.
        """
        return self in (TradeType.AGGRESSOR_BUYER, TradeType.AGGRESSOR_SELLER)

    @property
    def signo(self) -> int:
        """+1 agressao compradora, -1 vendedora, 0 nao aplicavel."""
        if self is TradeType.AGGRESSOR_BUYER:
            return 1
        if self is TradeType.AGGRESSOR_SELLER:
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


class LoginResult(IntEnum):
    """nResult quando ConnState.LOGIN — manual, secao TStateCallback."""

    CONNECTED = 0
    INVALID = 1
    INVALID_PASS = 2
    BLOCKED_PASS = 3
    EXPIRED_PASS = 4
    UNKNOWN_ERR = 200


class RoteamentoResult(IntEnum):
    """nResult quando ConnState.ROTEAMENTO — manual, secao TStateCallback.
    Distingue o SERVIDOR de roteamento (CONNECTED=2) da CORRETORA/conta
    especifica (BROKER_CONNECTED=5) -- GetAccount() depende do segundo,
    nao so' do primeiro (bug real pego em 2026-08-26: contas.py chamava
    GetAccount cedo demais, so' com o login basico, nunca com o broker
    de fato conectado)."""

    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2
    BROKER_DISCONNECTED = 3
    BROKER_CONNECTING = 4
    BROKER_CONNECTED = 5


class MarketDataResult(IntEnum):
    """nResult quando ConnState.MARKET_DATA."""

    DISCONNECTED = 0
    CONNECTING = 1
    WAITING = 2
    NOT_LOGGED = 3
    CONNECTED = 4
    PERFORMANCE_WARNING = 5
    PARTIAL_CONNECTED = 6


class AtivacaoResult(IntEnum):
    """nResult quando ConnState.ATIVACAO."""

    VALID = 0
    INVALID = 1


class Stream(StrEnum):
    """Fluxos gravaveis. O valor vira nome de diretorio na particao."""

    TRADE = "trade"
    BOOK_OFFER = "book_offer"
    BOOK_PRICE = "book_price"
    TINY_BOOK = "tiny_book"
