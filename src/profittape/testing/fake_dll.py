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
    ) -> None:
        self.com_offer_v2 = com_offer_v2
        self.eventos_por_ativo = eventos_por_ativo
        self.intervalo_s = intervalo_s
        self.atraso_login_s = atraso_login_s
        self.rng = random.Random(seed)
        self._cb: dict[str, object] = {}
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
        time.sleep(self.atraso_login_s)
        self._cb["state"](2, 4)   # market data conectado

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
        base = datetime.strptime(ini, "%d/%m/%Y").replace(hour=10)
        time.sleep(0.05)  # a DLL real tambem demora a comecar a entregar
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
