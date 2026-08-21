"""
Cliente ProfitDLL: ciclo de vida, callbacks e subscricoes.

A regra que governa este arquivo inteiro: NENHUM callback faz trabalho alem de
montar a tupla e empurrar no bus. Sem I/O, sem log, sem lock disputado, sem
alocacao grande. O feed fica parado enquanto o callback roda.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import structlog

from ..domain.enums import ConnState, Stream
from ..domain.events import BookDelta, PriceLevel, TinyBook, Trade
from ..pipeline.bus import EventBus
from . import bindings as b
from .errors import LoginFailed, check
from .timeparse import parse_ts_ns

log = structlog.get_logger(__name__)


class ProfitClient:
    """
    Envolve a DLL. Uma instancia por processo — a DLL e' global e nao aceita
    duas inicializacoes.
    """

    def __init__(
        self,
        dll_path: str | Path,
        activation_key: str,
        user: str,
        password: str,
        bus: EventBus,
        tz_offset_horas: int = -3,
        on_state: Callable[[int, int], None] | None = None,
        dll: Any | None = None,
    ) -> None:
        self.dll_path = dll_path
        self._key = activation_key
        self._user = user
        self._password = password
        self.bus = bus
        self.tz = tz_offset_horas
        self._on_state = on_state
        self._dll = dll  # injetavel: permite FakeProfitDLL em teste

        self.conectado_market = False
        self.conectado_login = False
        self._inicializado = False

        # Referencias fortes aos callbacks. Sem isto o GC do Python coleta o
        # objeto enquanto a DLL ainda guarda o ponteiro, e o proximo evento
        # executa memoria liberada. E' a causa numero um de crash aleatorio
        # em integracao ctypes.
        self._cb: dict[str, Any] = {}

        # Contador diagnostico de pacotes atFullBook descartados (ver
        # _corpo_offer/_corpo_price). Incremento simples: perder uma unidade
        # por corrida rara entre threads e' aceitavel para um contador de
        # diagnostico — nao e' dado, e' metrica.
        self.full_book_descartados = {"offer": 0, "price": 0}

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    def connect(self, timeout_s: float = 30.0) -> None:
        if self._dll is None:
            self._dll = b.load_dll(self.dll_path)

        ausentes = b.check_exports(self._dll)
        if ausentes:
            raise LoginFailed(
                f"A DLL nao expoe {ausentes}. Versao incompativel com "
                f"src/profittape/profitdll/bindings.py — ajuste as assinaturas la."
            )

        self._montar_callbacks()
        codigo = self._dll.DLLInitializeMarketLogin(
            self._key, self._user, self._password,
            self._cb["state"],
            self._cb["trade"],
            self._cb["daily"],
            self._cb["price_book"],
            self._cb["offer_book"],
            self._cb["history"],
            self._cb["progress"],
            self._cb["tiny"],
        )
        if codigo < 0:
            raise LoginFailed(f"DLLInitializeMarketLogin devolveu {codigo}")
        self._inicializado = True

        # O offer book order-by-order (com agente e offer_id confiaveis em
        # Int64) so chega pelo setter V2 — o slot V1 do init ficou MUDO em
        # producao (subscribe OK, zero eventos). Registrar aqui, apos o init,
        # conforme o manual: o setter sobrepoe a callback do init.
        set_v2 = getattr(self._dll, "SetOfferBookCallbackV2", None)
        if callable(set_v2):
            ret = set_v2(self._cb["offer_book_v2"])
            log.info("profitdll.offer_book_v2_registrado", retorno=int(ret))
            self.offer_book_v2 = True
        else:
            self.offer_book_v2 = False
            log.warning(
                "profitdll.sem_offer_book_v2",
                aviso="esta versao da DLL nao expoe SetOfferBookCallbackV2; "
                      "o offer book dependera do slot V1 do init, que em "
                      "producao pode nao entregar nada",
            )

        # O login e' assincrono: a chamada acima retorna antes da conexao
        # existir. Subscrever antes do market data estar pronto falha em
        # silencio — o ticker simplesmente nunca entrega evento.
        limite = time.monotonic() + timeout_s
        while time.monotonic() < limite:
            if self.conectado_market:
                log.info("profitdll.conectado")
                return
            time.sleep(0.2)
        raise LoginFailed(
            f"Market data nao conectou em {timeout_s}s. Verifique credencial, "
            f"chave de ativacao e se o Profit esta aberto e logado."
        )

    def disconnect(self) -> None:
        if self._inicializado and self._dll is not None:
            try:
                self._dll.DLLFinalize()
            except Exception:
                log.exception("profitdll.finalize_falhou")
            self._inicializado = False

    def __enter__(self) -> ProfitClient:
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.disconnect()

    # ------------------------------------------------------------------
    # Subscricoes
    # ------------------------------------------------------------------
    def subscribe_trades(self, ticker: str, bolsa: str = "B") -> None:
        check(self._dll.SubscribeTicker(ticker, bolsa), f"SubscribeTicker {ticker}")

    def subscribe_offer_book(self, ticker: str, bolsa: str = "B") -> None:
        check(self._dll.SubscribeOfferBook(ticker, bolsa), f"SubscribeOfferBook {ticker}")

    def subscribe_price_book(self, ticker: str, bolsa: str = "B") -> None:
        check(self._dll.SubscribePriceBook(ticker, bolsa), f"SubscribePriceBook {ticker}")

    def request_history(self, ticker: str, inicio: str, fim: str, bolsa: str = "B") -> None:
        """
        Historico de negocios. Datas em "DD/MM/YYYY".

        Lembrete: historico existe para TRADES. Book e' realtime puro — nao ha
        como pedir livro de ontem. Toda feature de fila depende de gravacao
        propria, e por isso o recorder precisa comecar a rodar cedo.
        """
        check(
            self._dll.GetHistoryTrades(ticker, bolsa, inicio, fim),
            f"GetHistoryTrades {ticker}",
        )

    def agent_name(self, agent_id: int) -> str | None:
        """
        Nome da corretora pelo codigo, via GetAgentNameById (grafia varia).

        Devolve None se a DLL nao expuser o export ou nao conhecer o codigo —
        quem chama decide se isso e' erro (para o CSV de referencia, nao e':
        codigo sem nome vira linha com nome vazio, ainda util para o join).
        """
        for nome in ("GetAgentNameByID", "GetAgentNameById"):
            fn = getattr(self._dll, nome, None)
            if fn is not None:
                resultado = fn(int(agent_id))
                return resultado or None
        return None

    # ------------------------------------------------------------------
    # Callbacks — caminho quente
    # ------------------------------------------------------------------
    def _montar_callbacks(self) -> None:
        bus = self.bus          # ligacao local: evita lookup de atributo no hot path
        tz = self.tz
        publish = bus.publish

        @b.TStateCallback
        def _state(tipo: int, valor: int) -> None:
            if tipo == ConnState.MARKET_DATA:
                self.conectado_market = valor in (2, 3, 4)
            elif tipo == ConnState.LOGIN:
                self.conectado_login = valor == 0
            if self._on_state is not None:
                self._on_state(tipo, valor)

        @b.TNewTradeCallback
        def _trade(ativo, data, numero, preco, vol, qtd, comp, vend, tipo, edit) -> None:
            publish(
                Stream.TRADE,
                Trade(
                    ts_ns=parse_ts_ns(data, tz),
                    ts_recv_ns=time.time_ns(),
                    symbol=ativo.ticker or "",
                    exchange=ativo.bolsa or "",
                    trade_id=int(numero),
                    price=float(preco),
                    volume_financeiro=float(vol),
                    quantidade=int(qtd),
                    agente_comprador=int(comp),
                    agente_vendedor=int(vend),
                    trade_type=int(tipo),
                    is_edit=edit != b"\x00",
                ),
            )

        FULL_BOOK = 4   # BookAction.FULL_BOOK — ver domain/enums.py

        def _corpo_offer(ativo, action, position, side, qtd, agente, offer_id,
                         preco, has_price, has_qtd, has_date, data) -> None:
            if action == FULL_BOOK:
                # Manual (TOfferBookCallbackV2): "pArraySell, pArrayBuy: Lista
                # com as ofertas de compra/venda; (Validos em atFullBook)".
                # A contrapartida: os campos ESCALARES (preco, data, etc.) nao
                # sao o payload real aqui — o book completo vem empacotado nos
                # arrays, que este binding ainda nao decodifica (formato de
                # registro variavel por causa da data em string; ver
                # docs/ARQUITETURA.md). Publicar os escalares como se fossem
                # um delta normal grava LIXO: foi assim que uma sessao real
                # produziu uma linha com timestamp "1990-01-01" — memoria nao
                # inicializada/obsoleta lida como se fosse data valida.
                # Ate o parser de array existir, descartamos e contamos.
                self.full_book_descartados["offer"] += 1
                return
            # bHasDate ("1 byte para especificar se existe data", manual):
            # a maioria dos deltas de book NAO carrega data por evento — so'
            # parseamos pwcDate quando a flag confirma que ha' conteudo valido
            # ali. Achado real: nao checar isso fez ~97% dos deltas de uma
            # sessao saírem com ts_ns=1990-01-01 — memoria obsoleta de um
            # ponteiro que a DLL nao preencheu para este evento, lida como se
            # fosse uma data de verdade. ts_recv_ns continua confiavel sempre.
            tem_data = has_date != b"\x00"
            publish(
                Stream.BOOK_OFFER,
                BookDelta(
                    ts_ns=parse_ts_ns(data, tz) if tem_data else 0,
                    ts_recv_ns=time.time_ns(),
                    symbol=ativo.ticker or "",
                    exchange=ativo.bolsa or "",
                    action=int(action),
                    side=int(side),
                    position=int(position),
                    offer_id=int(offer_id),
                    price=float(preco),
                    quantidade=int(qtd),
                    agente=int(agente),
                    has_price=has_price != b"\x00",
                    has_qtd=has_qtd != b"\x00",
                    has_date=tem_data,
                ),
            )

        # Mesmo corpo, DOIS envelopes de tipo: o V1 (nQtd Integer) vive no
        # slot do init — se alguma versao da DLL alimentar por la, capturamos
        # em vez de perder — e o V2 (nQtd Int64) e' registrado via
        # SetOfferBookCallbackV2 no connect(). O manual garante que o setter
        # SOBREPOE o do init: nunca os dois ativos, sem duplicata.
        @b.TOfferBookCallbackV1
        def _offer_v1(ativo, action, position, side, qtd, agente, offer_id,
                      preco, has_price, has_qtd, has_date, has_id, has_agent,
                      data, arr_sell, arr_buy) -> None:
            _corpo_offer(ativo, action, position, side, qtd, agente, offer_id,
                         preco, has_price, has_qtd, has_date, data)

        @b.TOfferBookCallbackV2
        def _offer_v2(ativo, action, position, side, qtd, agente, offer_id,
                      preco, has_price, has_qtd, has_date, has_id, has_agent,
                      data, arr_sell, arr_buy) -> None:
            _corpo_offer(ativo, action, position, side, qtd, agente, offer_id,
                         preco, has_price, has_qtd, has_date, data)

        @b.TPriceBookCallbackV1
        def _price(ativo, action, position, side, qtd, n_ofertas, preco,
                   arr_sell, arr_buy) -> None:
            if action == FULL_BOOK:
                # Mesma ressalva do manual para TPriceBookCallbackV2: os
                # arrays so sao validos em atFullBook, e os campos escalares
                # (incluindo dPrice) nao sao garantidos fora de atAdd. Mesmo
                # descarte do offer book, mesmo motivo.
                self.full_book_descartados["price"] += 1
                return
            agora = time.time_ns()
            publish(
                Stream.BOOK_PRICE,
                PriceLevel(
                    ts_ns=agora,   # price book nao carrega timestamp proprio
                    ts_recv_ns=agora,
                    symbol=ativo.ticker or "",
                    exchange=ativo.bolsa or "",
                    action=int(action),
                    side=int(side),
                    position=int(position),
                    price=float(preco),
                    quantidade=int(qtd),
                    n_ofertas=int(n_ofertas),
                ),
            )

        @b.TTinyBookCallback
        def _tiny(ativo, preco, qtd, side) -> None:
            publish(
                Stream.TINY_BOOK,
                TinyBook(
                    ts_recv_ns=time.time_ns(),
                    symbol=ativo.ticker or "",
                    exchange=ativo.bolsa or "",
                    side=int(side),
                    price=float(preco),
                    quantidade=int(qtd),
                ),
            )

        @b.THistoryTradeCallback
        def _history(ativo, data, numero, preco, vol, qtd, comp, vend, tipo) -> None:
            publish(
                Stream.TRADE,
                Trade(
                    ts_ns=parse_ts_ns(data, tz),
                    ts_recv_ns=time.time_ns(),
                    symbol=ativo.ticker or "",
                    exchange=ativo.bolsa or "",
                    trade_id=int(numero),
                    price=float(preco),
                    volume_financeiro=float(vol),
                    quantidade=int(qtd),
                    agente_comprador=int(comp),
                    agente_vendedor=int(vend),
                    trade_type=int(tipo),
                    is_edit=False,
                ),
            )

        @b.TNewDailyCallback
        def _daily(*_: object) -> None:
            return  # candle diario nao interessa ao recorder de fluxo

        @b.TProgressCallback
        def _progress(ativo, pct) -> None:
            return

        self._cb = {
            "state": _state, "trade": _trade, "daily": _daily,
            "price_book": _price, "offer_book": _offer_v1,
            "offer_book_v2": _offer_v2,
            "history": _history, "progress": _progress, "tiny": _tiny,
        }
