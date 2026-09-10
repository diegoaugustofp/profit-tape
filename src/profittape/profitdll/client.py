"""
Cliente ProfitDLL: ciclo de vida, callbacks e subscricoes.

A regra que governa este arquivo inteiro: NENHUM callback faz trabalho alem de
montar a tupla e empurrar no bus. Sem I/O, sem log, sem lock disputado, sem
alocacao grande. O feed fica parado enquanto o callback roda.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from ..domain.enums import ConnState, Stream
from ..domain.events import BookDelta, PriceLevel, TinyBook, Trade
from ..pipeline.bus import EventBus
from . import bindings as b
from .errors import LoginFailed, check
from .timeparse import parse_ts_ns
from .versao import versao_arquivo

log = structlog.get_logger(__name__)

# GetHistoryTrades exige "DD/MM/YYYY HH:mm:SS" com horas validas para o
# pregao. Medido em 2026-09-10 com a DLL 4.0.0.41: so' data ("31/08/2026")
# e' aceito com retorno 0 e progresso 0 -> 100 em 15 ms, ZERO negocios --
# a DLL le como janela de meia-noite a meia-noite. Com hora, o mesmo dia
# entregou milhoes de negocios. Foi o "backfill quebrado" de setembro.
# Fonte: artigo "Como requisitar trades historicos com a ProfitDLL"
# (ajuda.nelogica.com.br), que tambem fixa: maximo 10 dias por chamada,
# fim do download = progresso 100.
HORA_INICIO_PREGAO = "09:00:00"
HORA_FIM_PREGAO = "18:35:00"


def _com_hora(data: str, hora: str) -> str:
    """'DD/MM/YYYY' -> 'DD/MM/YYYY HH:mm:SS'; se ja' tem hora, nao mexe."""
    d = data.strip()
    return d if " " in d else f"{d} {hora}"


@dataclass(frozen=True)
class EventoOrdem:
    """Um OrderChangeCallback, ja' convertido para tipos Python. Montado no
    callback (so' conversao), lido pela thread principal."""

    t_mono: float
    profit_id: int
    corretora: int
    conta: str
    ticker: str
    qtd: int
    executada: int
    restante: int
    lado: int
    preco: float
    preco_medio: float
    status: str
    texto: str
    data: str


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
        on_trade_extra: Callable[[Trade], None] | None = None,
        dll: Any | None = None,
        login_completo: bool = False,
    ) -> None:
        self.dll_path = dll_path
        # E1 (2026-09-08): login COMPLETO (DLLInitializeLogin) em vez de
        # MarketLogin. Motivo: rotear ordem exige a sessao completa, e com
        # UMA chave de ativacao a conexao do record e' a unica que existe
        # -- entao e' o record que precisa subir com ela. False por
        # padrao: todo caller existente (producao ha semanas) tem ZERO
        # mudanca. Ver docs/EA_ARQUITETURA.md, "Trilha de execucao".
        self.login_completo = login_completo
        self._key = activation_key
        self._user = user
        self._password = password
        self.bus = bus
        self.tz = tz_offset_horas
        self._on_state = on_state
        # Hook opcional, ADITIVO (2026-08-27, decisao de arquitetura: EA
        # roda DENTRO do processo do record, mesma conexao -- licenciamento
        # da Nelogica so' permite UMA chave de ativacao, validado com o
        # time comercial deles). None por padrao -- callers existentes
        # (record de producao ha' semanas) tem ZERO mudanca de
        # comportamento. Chamado DEPOIS de publish() no hot path, nunca
        # antes -- a captura (bus.publish) e' sempre a prioridade; se este
        # hook falhar ou travar, NUNCA pode atrasar ou perder um evento de
        # captura. Exception aqui e' sempre engolida e logada, nunca
        # propaga de volta pra fronteira ctypes.
        self._on_trade_extra = on_trade_extra
        self._dll = dll  # injetavel: permite FakeProfitDLL em teste

        self.conectado_market = False
        self.conectado_login = False
        # E1 v2.07: o BUG que o ea/contas.py corrigiu em 26/08 e que eu
        # repeti na v2.06 -- "conectado_login" (tipo=LOGIN valor=0) e' o
        # PRIMEIRO dos quatro sinais, nao "tudo pronto". GetAccount() e
        # qualquer ordem dependem da CORRETORA conectada: tipo=ROTEAMENTO
        # valor=BROKER_CONNECTED(5). Visto no teste A de 08/09: o valor=5
        # chegou 0,35 s DEPOIS de connect() ter devolvido.
        self.roteamento_estado: int | None = None
        self.contas_pedidas = False
        self._inicializado = False

        # E1: diagnostico da sessao de roteamento. Preenchido SO' pelas
        # callbacks do login completo (mudas no MarketLogin). contas_vistas
        # e' a prova de que a sessao de roteamento subiu de verdade: a DLL
        # dispara AccountCallback uma vez por conta logo apos o login.
        self.contadores_roteamento = {"ordem_mudanca": 0, "ordem_historico": 0,
                                      "conta": 0}
        self.contas_vistas: list[tuple[int, str]] = []   # (corretora, account_id)
        # E2 (2026-09-11): o NOME da corretora, como a DLL o anuncia, por
        # id. E' a base da trava "so' Simulador": a decisao de que uma conta
        # e' de simulacao vem da DLL, nao do .env.
        self.nomes_corretoras: dict[int, str] = {}
        # E2: eventos do OrderChangeCallback, como tuplas cruas (sem I/O no
        # callback -- regra do arquivo). Quem consome e' a thread principal.
        self.ordens_eventos: deque[EventoOrdem] = deque(maxlen=10_000)
        # Historico: progresso por ticker e o sinal de "chegou a 100". Sao
        # a unica forma confiavel de saber que o download terminou (o
        # artigo da Nelogica): esperar o fluxo parar e' fragil -- a DLL
        # baixa primeiro (progresso sobe ate' 99 e fica) e entrega depois.
        self.progresso_historico: dict[str, int] = {}
        self.historico_100 = threading.Event()

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
        if self.login_completo:
            # Ordem dos argumentos e' a do MANUAL para DLLInitializeLogin
            # (e a mesma declarada em bindings._declare): state, historico
            # de ORDENS (THistoryCallback), mudanca de ordem, conta, e so'
            # entao os slots de mercado na mesma ordem do MarketLogin.
            # ATENCAO ao nome: self._cb["history"] e' THistoryTradeCallback
            # (historico de NEGOCIOS, slot de mercado), NAO o THistoryCallback
            # de ordens -- esse e' self._cb["ordem_historico"]. Trocar os
            # dois compila (ctypes nao confere) e corrompe a pilha.
            if not hasattr(self._dll, "DLLInitializeLogin"):
                raise LoginFailed(
                    "login_completo=True mas a DLL nao expoe DLLInitializeLogin "
                    "-- rode `profit-tape doctor` (secao EXECUCAO) e confira."
                )
            nome_init = "DLLInitializeLogin"
            codigo = self._dll.DLLInitializeLogin(
                self._key, self._user, self._password,
                self._cb["state"],
                self._cb["ordem_historico"],
                self._cb["ordem_mudanca"],
                self._cb["conta"],
                self._cb["trade"],
                self._cb["daily"],
                self._cb["price_book"],
                self._cb["offer_book"],
                self._cb["history"],
                self._cb["progress"],
                self._cb["tiny"],
            )
        else:
            nome_init = "DLLInitializeMarketLogin"
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
            raise LoginFailed(f"{nome_init} devolveu {codigo}")
        self._inicializado = True
        log.info("profitdll.inicializado", modo=nome_init,
                 dll_versao=versao_arquivo(self.dll_path))

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
        # A espera continua sendo por MARKET DATA (e' a captura que manda).
        # No login completo, o estado de LOGIN e' reportado junto, mas nao
        # bloqueia: se o roteamento nao subir, a captura nao pode ficar
        # refem disso -- o E2 confere conectado_login por conta propria.
        limite = time.monotonic() + timeout_s
        while time.monotonic() < limite:
            if self.conectado_market:
                log.info("profitdll.conectado",
                         login_completo=self.login_completo,
                         login_ok=self.conectado_login,
                         corretora=self.roteamento_estado,
                         contas=len(self.contas_vistas))
                if self.login_completo:
                    self._pedir_contas(timeout_s=5.0)
                return
            time.sleep(0.2)
        raise LoginFailed(
            f"Market data nao conectou em {timeout_s}s. Verifique credencial, "
            f"chave de ativacao e se o Profit esta aberto e logado."
        )

    @property
    def corretora_pronta(self) -> bool:
        """ROTEAMENTO em BROKER_CONNECTED(5). E' ISTO que GetAccount() e o
        envio de ordem exigem -- nao o login basico."""
        return self.roteamento_estado == 5

    def _pedir_contas(self, timeout_s: float) -> None:
        """
        Espera (limitado) a corretora ficar pronta e chama GetAccount() UMA
        vez. As contas chegam depois, pelo AccountCallback -- aparecem no
        heartbeat. Nunca bloqueia a captura: se a corretora nao ficar
        pronta no prazo, loga e segue; o E2 confere corretora_pronta antes
        de qualquer ordem. Chamado da thread principal, nunca de callback
        (reentrar na DLL de dentro de um callback e' comportamento
        indefinido).
        """
        assert self._dll is not None
        limite = time.monotonic() + timeout_s
        while time.monotonic() < limite and not self.corretora_pronta:
            time.sleep(0.1)
        if not self.corretora_pronta:
            log.warning("profitdll.corretora_nao_pronta",
                        estado=self.roteamento_estado, esperou_s=timeout_s,
                        nota="GetAccount() nao chamado; captura segue normal")
            return
        get_account = getattr(self._dll, "GetAccount", None)
        if get_account is None:
            log.warning("profitdll.sem_getaccount")
            return
        ret = get_account()
        self.contas_pedidas = True
        log.info("profitdll.contas_pedidas", retorno=int(ret))

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
        assert self._dll is not None, "connect() precisa ser chamado antes"
        check(self._dll.SubscribeTicker(ticker, bolsa), f"SubscribeTicker {ticker}")

    def subscribe_offer_book(self, ticker: str, bolsa: str = "B") -> None:
        assert self._dll is not None, "connect() precisa ser chamado antes"
        check(self._dll.SubscribeOfferBook(ticker, bolsa), f"SubscribeOfferBook {ticker}")

    def subscribe_price_book(self, ticker: str, bolsa: str = "B") -> None:
        assert self._dll is not None, "connect() precisa ser chamado antes"
        check(self._dll.SubscribePriceBook(ticker, bolsa), f"SubscribePriceBook {ticker}")

    def request_history(self, ticker: str, inicio: str, fim: str, bolsa: str = "B") -> None:
        """
        Historico de negocios. Datas em "DD/MM/YYYY" (recebem as horas do
        pregao aqui) ou ja' em "DD/MM/YYYY HH:mm:SS". Limpa `historico_100`
        antes de pedir: quem chama espera esse evento para saber que o
        download terminou, e so' depois espera o fim da entrega.

        Lembrete: historico existe para TRADES. Book e' realtime puro — nao ha
        como pedir livro de ontem. Toda feature de fila depende de gravacao
        propria, e por isso o recorder precisa comecar a rodar cedo.
        """
        assert self._dll is not None, "connect() precisa ser chamado antes"
        inicio = _com_hora(inicio, HORA_INICIO_PREGAO)
        fim = _com_hora(fim, HORA_FIM_PREGAO)
        self.historico_100.clear()
        self.progresso_historico.pop(ticker, None)
        check(
            self._dll.GetHistoryTrades(ticker, bolsa, inicio, fim),
            f"GetHistoryTrades {ticker}",
        )

    def agent_name(self, agent_id: int, curto: bool = False) -> str | None:
        """
        Nome da corretora pelo codigo. curto=True usa GetAgentShortNameById
        (ex.: 'XP', 'BTG', 'Ideal') em vez do nome juridico completo — muito
        mais util para classificacao de perfil, como o operador observou
        (2026-08-22). Cai no nome longo se o short name nao existir.

        Devolve None se a DLL nao expuser o export ou nao conhecer o codigo —
        quem chama decide se isso e' erro (para o CSV de referencia, nao e':
        codigo sem nome vira linha com nome vazio, ainda util para o join).
        """
        if curto:
            for nome in ("GetAgentShortNameByID", "GetAgentShortNameById"):
                fn = getattr(self._dll, nome, None)
                if fn is not None:
                    resultado = fn(int(agent_id))
                    if resultado:
                        return str(resultado)
            # sem short name: cai no longo abaixo
        for nome in ("GetAgentNameByID", "GetAgentNameById"):
            fn = getattr(self._dll, nome, None)
            if fn is not None:
                resultado = fn(int(agent_id))
                return str(resultado) if resultado else None
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
            elif tipo == ConnState.ROTEAMENTO:
                self.roteamento_estado = valor
            if self._on_state is not None:
                self._on_state(tipo, valor)

        on_trade_extra = self._on_trade_extra

        @b.TNewTradeCallback
        def _trade(ativo, data, numero, preco, vol, qtd, comp, vend, tipo, edit) -> None:
            evento = Trade(
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
            )
            publish(Stream.TRADE, evento)
            if on_trade_extra is not None:
                # A CAPTURA (linha acima) sempre vem primeiro e nunca espera
                # por isto. Qualquer excecao aqui e' silenciosamente
                # engolida -- propagar atravessaria a fronteira ctypes
                # (comportamento indefinido, tipicamente crash do processo
                # inteiro) so' porque o EA (secundario) teve um bug. Perder
                # o dado do EA para 1 trade e' aceitavel; perder a captura
                # do dia inteiro por causa do EA nao e'.
                try:
                    on_trade_extra(evento)
                except Exception:
                    log.exception("profitdll.on_trade_extra_falhou")

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

        progresso = self.progresso_historico
        hist_100 = self.historico_100

        @b.TProgressCallback
        def _progress(ativo, pct) -> None:
            # so' guarda o inteiro e seta o evento -- sem log, sem I/O
            progresso[str(getattr(ativo, "ticker", "") or "")] = int(pct)
            if int(pct) >= 100:
                hist_100.set()

        # ---- E1: callbacks da sessao de roteamento ------------------------
        # Mesma regra do arquivo: NADA alem de contar e guardar o minimo.
        # Sem log, sem I/O. O conteudo de ordem (status, preco medio,
        # quantidade) e' assunto do E2 -- aqui so' se prova que a sessao
        # sobe e as callbacks disparam.
        contadores = self.contadores_roteamento
        contas = self.contas_vistas
        nomes = self.nomes_corretoras
        eventos = self.ordens_eventos

        @b.TAccountCallback
        def _conta(corretora, nome_corretora, account_id, titular) -> None:
            # v2.08: DEDUPLICADO. No teste A de 08/09 o heartbeat mostrou
            # contas=14 para um login com DUAS contas -- e havia exatamente
            # 8 eventos ROTEAMENTO=5 no mesmo log. Hipotese: a DLL
            # re-anuncia as contas a cada notificacao de corretora. O
            # contador bruto fica em contadores["conta"] (invocacoes);
            # contas_vistas guarda so' pares unicos, em ordem de chegada.
            contadores["conta"] += 1
            par = (int(corretora), str(account_id or ""))
            if par not in contas:
                contas.append(par)
            nomes[int(corretora)] = str(nome_corretora or "")

        @b.TOrderChangeCallback
        def _ordem_mudanca(ativo, corretora, qtd, traded, leaves, side, preco,
                           stop, medio, profit_id, tipo, conta_id, titular,
                           cl_ord_id, status, data, texto) -> None:
            contadores["ordem_mudanca"] += 1
            # So' uma tupla de valores ja' convertidos. Nada de log aqui.
            eventos.append(EventoOrdem(
                t_mono=time.monotonic(), profit_id=int(profit_id),
                corretora=int(corretora), conta=str(conta_id or ""),
                ticker=str(getattr(ativo, "ticker", "") or ""),
                qtd=int(qtd), executada=int(traded), restante=int(leaves),
                lado=int(side), preco=float(preco), preco_medio=float(medio),
                status=str(status or ""), texto=str(texto or ""),
                data=str(data or "")))

        @b.THistoryCallback
        def _ordem_historico(*_: object) -> None:
            contadores["ordem_historico"] += 1

        self._cb = {
            "state": _state, "trade": _trade, "daily": _daily,
            "price_book": _price, "offer_book": _offer_v1,
            "offer_book_v2": _offer_v2,
            "history": _history, "progress": _progress, "tiny": _tiny,
            "conta": _conta, "ordem_mudanca": _ordem_mudanca,
            "ordem_historico": _ordem_historico,
        }
