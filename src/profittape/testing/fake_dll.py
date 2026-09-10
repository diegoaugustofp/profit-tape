"""
ProfitDLL falsa.

Por que existe: sem isto, todo o pipeline so pode ser exercitado num Windows
com terminal logado e mercado aberto — ou seja, poucas horas por dia, com
efeito colateral, e sem repetibilidade. A DLL falsa gera rajada sintetica com
o mesmo formato de dado e permite testar fila, writer, particao e encerramento
em CI, no Linux, em segundos.

Ela imita tres comportamentos que sao os que costumam quebrar em producao:
  * login ASSINCRONO — conexao so vira depois de alguns callbacks de estado;
  * eventos vindos de OUTRA thread, como na DLL real;
  * timestamp em horario local de Brasilia no formato da DLL.
"""

from __future__ import annotations

import random
import sys
import threading
import time
import traceback
from collections.abc import Callable
from datetime import datetime, timedelta

from profittape.profitdll.types import TAssetIDRec


def _ativo(ticker: str, bolsa: str) -> TAssetIDRec:
    """
    A struct REAL, nao um substituto.

    Tentador seria usar um objeto qualquer com .ticker e .bolsa. Nao funciona:
    os callbacks sao objetos ctypes de verdade e validam o tipo do argumento na
    chamada. Usar a struct de producao tambem e' mais fiel — o teste exercita a
    mesma marshalling que roda no Windows.
    """
    return TAssetIDRec(ticker, bolsa, 0)


class FakeProfitDLL:
    def __init__(
        self,
        eventos_por_ativo: int = 1_000,
        intervalo_s: float = 0.0,
        atraso_login_s: float = 0.05,
        seed: int = 42,
        com_offer_v2: bool = True,
        com_login_completo: bool = True,
        contas: tuple[tuple[int, str, str], ...] = ((32006, "SIMULADOR", "DEMO-1"),),
        preenche_ordens: bool = True,
        preco_fill: float = 140000.0,
        atraso_fill_s: float = 0.02,
    ) -> None:
        # E2 (2026-09-11): a fake responde a cada Send* com dois
        # OrderChangeCallback (aceita, depois executada), em thread, como a
        # DLL real. preenche_ordens=False simula ordem aceita e nunca
        # executada (caminho de timeout). ordens_enviadas guarda os
        # argumentos de cada Send* -- a trava e' testada por AUSENCIA de
        # entrada aqui.
        self.preenche_ordens = preenche_ordens
        self.preco_fill = preco_fill
        self.atraso_fill_s = atraso_fill_s
        self.ordens_enviadas: list[tuple[str, tuple[object, ...]]] = []
        self.com_offer_v2 = com_offer_v2
        # E1: com_login_completo=False remove o export DLLInitializeLogin
        # (simula DLL so-market-data) -- o client precisa falhar CEDO e
        # com mensagem clara, nao com AttributeError. `contas` sao as que
        # o AccountCallback vai anunciar apos o login completo, como a DLL
        # real faz (corretora, nome, account_id).
        self.com_login_completo = com_login_completo
        self.contas = contas
        self.modo_init: str | None = None
        self.eventos_por_ativo = eventos_por_ativo
        self.intervalo_s = intervalo_s
        self.atraso_login_s = atraso_login_s
        self.rng = random.Random(seed)
        self._cb: dict[str, Callable[..., object]] = {}
        self._subscritos: list[tuple[str, str, str]] = []
        self._threads: list[threading.Thread] = []
        self.erros: list[BaseException] = []
        self._hist_chamadas: dict[str, int] = {}
        self._ultima_data_offer = "01/01/1970 00:00:00.000"   # buffer "obsoleto" inicial
        self._parar = threading.Event()
        self.finalizado = False

    # -- superficie que o ProfitClient consome ---------------------------
    def DLLInitializeMarketLogin(
        self, key, user, password, state, trade, daily, price, offer, hist, prog, tiny
    ):
        self.modo_init = "market"
        self._cb = {
            "state": state, "trade": trade, "daily": daily, "price": price,
            "offer": offer, "hist": hist, "prog": prog, "tiny": tiny,
        }
        t = threading.Thread(target=self._login_assincrono, daemon=True)
        t.start()
        self._threads.append(t)
        return 0

    def _login_assincrono(self) -> None:
        time.sleep(self.atraso_login_s)
        self._cb["state"](0, 0)   # login ok
        if self.modo_init == "login":
            # Sequencia REAL observada no teste A de 08/09: a corretora
            # (tipo=1) passa por 1,2,4 e chega em 5 (BROKER_CONNECTED)
            # -- e chegou DEPOIS do market data no log real, entao aqui
            # tambem vem depois, para o client nao poder contar com a
            # ordem. As contas NAO sao anunciadas aqui: so' apos
            # GetAccount() (versao v2.06 do fake anunciava no login e
            # escondeu exatamente esse bug do client).
            self._cb["state"](1, 1)
            self._cb["state"](1, 2)
        time.sleep(self.atraso_login_s)
        self._cb["state"](2, 4)   # market data conectado
        if self.modo_init == "login":
            time.sleep(self.atraso_login_s)
            self._cb["state"](1, 4)
            self._cb["state"](1, 5)   # corretora pronta -- so' agora GetAccount() vale
        self.roteamento_pronto = self.modo_init == "login"

    def GetAccount(self) -> int:
        """Como a DLL real: dispara AccountCallback uma vez por conta, e
        so' se a corretora estiver conectada. Antes disso, nao devolve
        nada (o ea/contas.py aprendeu isso em 26/08)."""
        self.get_account_chamadas = getattr(self, "get_account_chamadas", 0) + 1
        if self.modo_init != "login" or not getattr(self, "roteamento_pronto", False):
            return -1
        for corretora, nome, account_id in self.contas:
            self._cb["account"](corretora, nome, account_id, "TITULAR")
        return 0

    # ---- E2 (2026-09-10): envio de ordem, minimo pra testar ea-ordem-teste
    # sem DLL real. So' devolve um ID crescente > 0 -- verificar CONTEUDO de
    # status/preenchimento e' assunto de quando o callback de ordem for
    # usado alem de contar (ver ea/execucao.py, "conteudo e' assunto do E2").
    def _ordem(self, nome: str, args: tuple[object, ...], lado: int) -> int:
        self._prox_ordem = getattr(self, "_prox_ordem", 1000) + 1
        oid = self._prox_ordem
        self.ordens_enviadas.append((nome, args))
        cb = self._cb.get("ordem_mudanca")
        if cb is not None:
            conta, corretora = str(args[0]), int(str(args[1]))
            ticker = str(args[3] if nome != "SendZeroPositionAtMarket" else args[2])

            def _emitir() -> None:
                time.sleep(self.atraso_fill_s / 2)
                cb(_ativo(ticker, "F"), corretora, 1, 0, 1, lado, 0.0, 0.0, 0.0,
                   oid, "Market", conta, "TITULAR", f"CL{oid}", "Accepted",
                   "01/01/2026 10:00:00", "")
                if self.preenche_ordens:
                    time.sleep(self.atraso_fill_s / 2)
                    cb(_ativo(ticker, "F"), corretora, 1, 1, 0, lado, self.preco_fill,
                       0.0, self.preco_fill, oid, "Market", conta, "TITULAR",
                       f"CL{oid}", "Filled", "01/01/2026 10:00:00", "")

            t = threading.Thread(target=_emitir, daemon=True)
            t.start()
            self._threads.append(t)
        return oid

    def SendMarketBuyOrder(self, *args: object) -> int:
        return self._ordem("SendMarketBuyOrder", args, 1)

    def SendMarketSellOrder(self, *args: object) -> int:
        return self._ordem("SendMarketSellOrder", args, 2)

    def SendZeroPositionAtMarket(self, *args: object) -> int:
        return self._ordem("SendZeroPositionAtMarket", args, 2)

    def __getattribute__(self, nome: str) -> object:
        # Simula a AUSENCIA do export: hasattr(dll, "DLLInitializeLogin")
        # precisa devolver False quando com_login_completo=False. Tem que
        # ser __getattribute__ (nao __getattr__): o metodo EXISTE na
        # classe, entao __getattr__ nunca seria consultado para ele.
        if nome == "DLLInitializeLogin" and not object.__getattribute__(self, "com_login_completo"):
            raise AttributeError(nome)
        return object.__getattribute__(self, nome)

    def DLLInitializeLogin(
        self, key, user, password, state, hist_ordem, ordem_mudanca, account,
        trade, daily, price, offer, hist, prog, tiny,
    ):
        """
        Mesma ordem de argumentos do manual/bindings: state, historico de
        ORDENS, mudanca de ordem, conta, e depois os slots de mercado.
        Guarda os tres extras com nomes distintos dos de mercado -- o teste
        do E1 confere que o client passou cada callback no slot certo.
        """
        if not self.com_login_completo:
            raise AttributeError("DLLInitializeLogin")
        self.modo_init = "login"
        self._cb = {
            "state": state, "hist_ordem": hist_ordem,
            "ordem_mudanca": ordem_mudanca, "account": account,
            "trade": trade, "daily": daily, "price": price,
            "offer": offer, "hist": hist, "prog": prog, "tiny": tiny,
        }
        t = threading.Thread(target=self._login_assincrono, daemon=True)
        t.start()
        self._threads.append(t)
        return 0

    def SubscribeTicker(self, ticker, bolsa):
        self._iniciar(ticker, bolsa, "trade")
        return 0

    def SetOfferBookCallbackV2(self, cb):
        """Como a DLL real: o offer book V2 so flui apos este registro."""
        if self.com_offer_v2:
            self._cb["offer_v2"] = cb
            return 0
        return -1

    def SubscribeOfferBook(self, ticker, bolsa):
        self._iniciar(ticker, bolsa, "offer")
        return 0

    def SubscribePriceBook(self, ticker, bolsa):
        self._iniciar(ticker, bolsa, "price")
        return 0

    def UnsubscribeTicker(self, ticker, bolsa):
        return 0

    def UnsubscribeOfferBook(self, ticker, bolsa):
        return 0

    def UnsubscribePriceBook(self, ticker, bolsa):
        return 0

    def GetHistoryTrades(self, ticker, bolsa, ini, fim):
        """
        Ticker comecando com "FAILHIST" e' recusado com codigo NL, imitando a
        recusa sincrona observada em producao (ex: continuo de futuro sem
        historico). Permite testar que um recusado nao derruba os demais.
        """
        if ticker.startswith("FAILHIST"):
            return -2147483602
        if ticker.startswith("FLAKYHIST"):
            # Imita o padrao real de "servidor de historico ainda nao pronto":
            # recusa a primeira chamada e aceita a partir da segunda.
            n = self._hist_chamadas.get(ticker, 0) + 1
            self._hist_chamadas[ticker] = n
            if n == 1:
                return -2147483602
        return self._get_history_ok(ticker, bolsa, ini, fim)

    def _get_history_ok(self, ticker, bolsa, ini, fim):
        """
        Emite historico pelo callback proprio, como a DLL real: a chamada
        retorna imediatamente e os eventos chegam depois, de outra thread.
        E' esse formato assincrono que o quiesce do backfill precisa tratar.
        """
        t = threading.Thread(
            target=self._com_diagnostico,
            args=(self._emitir_historico, ticker, bolsa, ini),
            daemon=True,
        )
        t.start()
        self._threads.append(t)
        return 0

    def _emitir_historico(self, ticker: str, bolsa: str, ini: str) -> None:
        ativo = _ativo(ticker, bolsa)
        preco = 30.0 + self.rng.random() * 10
        # Como a DLL 4.0.0.41 (medido 2026-09-10): SO' DATA e' aceito e vira
        # janela vazia -- progresso 0 -> 100 na hora, zero negocios. Com
        # hora, baixa (progresso ate' 99) e depois entrega.
        prog = self._cb.get("prog")
        if " " not in ini.strip():
            if prog is not None:
                prog(ativo, 0)
                prog(ativo, 100)
            return
        base = datetime.strptime(ini.split(" ")[0], "%d/%m/%Y").replace(hour=10)
        time.sleep(0.05)  # a DLL real tambem demora a comecar a entregar
        if prog is not None:
            prog(ativo, 99)
        for i in range(self.eventos_por_ativo):
            if self._parar.is_set():
                return
            momento = base + timedelta(milliseconds=i * 250)
            data = momento.strftime("%d/%m/%Y %H:%M:%S.") + f"{momento.microsecond // 1000:03d}"
            preco += (self.rng.random() - 0.5) * 0.05
            tt = self.rng.choices([2, 3, 13, 4, 1, 32],
                                  weights=[36, 36, 24, 2, 1, 1])[0]
            qtd = self.rng.choice([100, 200, 300, 1000])
            self._cb["hist"](
                ativo, data, i + 1, preco, preco * qtd, qtd,
                self.rng.randint(1, 400), self.rng.randint(1, 400), tt,
            )
            if self.intervalo_s:
                time.sleep(self.intervalo_s)
        # A DLL real: progresso 100 no fim do download; os ultimos negocios
        # ainda podem chegar logo depois. Aqui vem depois de tudo.
        if prog is not None:
            prog(ativo, 100)

    def GetAgentNameByID(self, agent_id):
        # Nomes deterministas para teste; codigo 999 simula "desconhecido".
        if agent_id == 999:
            return ""
        return f"CORRETORA {agent_id}"

    def DLLFinalize(self):
        self._parar.set()
        for t in self._threads:
            t.join(timeout=5)
        self.finalizado = True
        return 0

    # -- geracao -------------------------------------------------------
    def _iniciar(self, ticker: str, bolsa: str, tipo: str) -> None:
        self._subscritos.append((ticker, bolsa, tipo))
        t = threading.Thread(
            target=self._com_diagnostico, args=(self._emitir, ticker, bolsa, tipo),
            daemon=True,
        )
        t.start()
        self._threads.append(t)

    def _com_diagnostico(self, alvo, *args) -> None:
        """
        Torna VISIVEL qualquer excecao de thread emissora.

        Excecao em thread daemon vai para stderr via threading.excepthook e o
        pytest a esconde em warnings — o sintoma vira "zero eventos" sem causa
        aparente. Imprimir em STDOUT garante que ela apareca na secao
        'Captured stdout call' de qualquer teste que falhe. A excecao e'
        registrada em `self.erros` para os testes poderem afirmar sobre ela.
        """
        try:
            alvo(*args)
        except BaseException as exc:
            self.erros.append(exc)
            print(f"\n{'!' * 70}\nFAKE DLL: thread emissora morreu: {exc!r}")
            traceback.print_exc(file=sys.stdout)
            print("!" * 70)

    def _emitir(self, ticker: str, bolsa: str, tipo: str) -> None:
        ativo = _ativo(ticker, bolsa)
        preco = 30.0 + self.rng.random() * 10
        t0 = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)

        for i in range(self.eventos_por_ativo):
            if self._parar.is_set():
                return
            momento = t0 + timedelta(milliseconds=i * 37)
            data = momento.strftime("%d/%m/%Y %H:%M:%S.") + f"{momento.microsecond // 1000:03d}"
            preco += (self.rng.random() - 0.5) * 0.05

            if tipo == "trade":
                # Mistura proposital calcada no pregao real medido: agressao
                # dominante, ~25% de RLP (13), leilao, cross e um UNKNOWN (32)
                # raro. O pipeline preserva a distincao ate o disco.
                tt = self.rng.choices([2, 3, 13, 4, 1, 32],
                                      weights=[36, 36, 24, 2, 1, 1])[0]
                qtd = self.rng.choice([100, 200, 300, 1000, 5000])
                self._cb["trade"](
                    ativo, data, i + 1, preco, preco * qtd, qtd,
                    self.rng.randint(1, 400), self.rng.randint(1, 400), tt, b"\x00",
                )
            elif tipo == "offer":
                # Fidelidade ao incidente real: o slot "offer" do init NUNCA e'
                # alimentado. So o callback registrado via SetOfferBookCallbackV2
                # recebe — sem o registro, silencio total, como em producao.
                destino = self._cb.get("offer_v2")
                if destino is None:
                    continue
                # Fidelidade ao SEGUNDO achado real: a maioria dos deltas NAO
                # carrega data por evento (bHasDate=False), e quando isso
                # acontece o ponteiro de data aponta para conteudo OBSOLETO
                # (nao nulo!) — nesse caso mandamos uma data-lixo plausivel
                # (de um evento anterior) para provar que o cliente ignora
                # pwcDate quando has_date=False, em vez de confiar nela.
                tem_data = self.rng.random() < 0.05    # ~5%: so' o snapshot inicial
                data_enviada = data if tem_data else self._ultima_data_offer
                self._ultima_data_offer = data
                destino(
                    ativo, self.rng.choice([0, 1, 2]), self.rng.randint(0, 9),
                    self.rng.choice([0, 1]), self.rng.choice([100, 500, 1000]),
                    self.rng.randint(1, 400), 10_000_000 + i, preco,
                    b"\x01", b"\x01",
                    b"\x01" if tem_data else b"\x00",
                    b"\x01", b"\x01", data_enviada, None, None,
                )
            else:
                self._cb["price"](
                    ativo, self.rng.choice([0, 1, 2]), self.rng.randint(0, 9),
                    self.rng.choice([0, 1]), self.rng.choice([100, 500, 1000]),
                    self.rng.randint(1, 20), preco, None, None,
                )

            if self.intervalo_s:
                time.sleep(self.intervalo_s)
