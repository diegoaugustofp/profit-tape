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
import threading
import time
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
    ) -> None:
        self.eventos_por_ativo = eventos_por_ativo
        self.intervalo_s = intervalo_s
        self.atraso_login_s = atraso_login_s
        self.rng = random.Random(seed)
        self._cb: dict[str, object] = {}
        self._subscritos: list[tuple[str, str, str]] = []
        self._threads: list[threading.Thread] = []
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
        Emite historico pelo callback proprio, como a DLL real: a chamada
        retorna imediatamente e os eventos chegam depois, de outra thread.
        E' esse formato assincrono que o quiesce do backfill precisa tratar.
        """
        t = threading.Thread(
            target=self._emitir_historico, args=(ticker, bolsa, ini), daemon=True
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
            tt = self.rng.choices([2, 3, 1, 4, 32], weights=[45, 45, 4, 3, 3])[0]
            qtd = self.rng.choice([100, 200, 300, 1000])
            self._cb["hist"](
                ativo, data, i + 1, preco, preco * qtd, qtd,
                self.rng.randint(1, 400), self.rng.randint(1, 400), tt,
            )
            if self.intervalo_s:
                time.sleep(self.intervalo_s)

    def DLLFinalize(self):
        self._parar.set()
        for t in self._threads:
            t.join(timeout=5)
        self.finalizado = True
        return 0

    # -- geracao -------------------------------------------------------
    def _iniciar(self, ticker: str, bolsa: str, tipo: str) -> None:
        self._subscritos.append((ticker, bolsa, tipo))
        t = threading.Thread(target=self._emitir, args=(ticker, bolsa, tipo), daemon=True)
        t.start()
        self._threads.append(t)

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
                # Mistura proposital de tipos: continuo, leilao e RLP. O
                # pipeline precisa preservar essa distincao ate o disco.
                tt = self.rng.choices([2, 3, 1, 4, 32], weights=[45, 45, 4, 3, 3])[0]
                qtd = self.rng.choice([100, 200, 300, 1000, 5000])
                self._cb["trade"](
                    ativo, data, i + 1, preco, preco * qtd, qtd,
                    self.rng.randint(1, 400), self.rng.randint(1, 400), tt, b"\x00",
                )
            elif tipo == "offer":
                self._cb["offer"](
                    ativo, self.rng.choice([0, 1, 2]), self.rng.randint(0, 9),
                    self.rng.choice([0, 1]), self.rng.choice([100, 500, 1000]),
                    self.rng.randint(1, 400), 10_000_000 + i, preco,
                    b"\x01", b"\x01", b"\x01", b"\x01", b"\x01", data, None, None,
                )
            else:
                self._cb["price"](
                    ativo, self.rng.choice([0, 1, 2]), self.rng.randint(0, 9),
                    self.rng.choice([0, 1]), self.rng.choice([100, 500, 1000]),
                    self.rng.randint(1, 20), preco, None, None,
                )

            if self.intervalo_s:
                time.sleep(self.intervalo_s)
