"""
E5.4 — DespachanteDeEAs: um alvo fixo para o callback, N bridges por
dentro.

POR QUE ISTO PRECISA EXISTIR (obstaculo tecnico real)
------------------------------------------------------
`ProfitClient.connect()` captura `on_trade_extra` numa VARIAVEL LOCAL
antes de registrar o callback na DLL:

    on_trade_extra = self._on_trade_extra      # <- fecha sobre o valor
    @b.TNewTradeCallback
    def _trade(...):
        if on_trade_extra is not None: on_trade_extra(evento)

Ou seja: trocar `client._on_trade_extra` DEPOIS de conectado nao tem
efeito nenhum -- o callback ja' fechou sobre o valor antigo. Por isso o
multi-EA nao pode ser "trocar o atributo quando incluir um EA". Tem que
ser um alvo ESTAVEL, registrado uma vez, que consulta uma lista mutavel
a cada trade. E' este modulo.

POR QUE O RECORD NUNCA PARA (decisao do operador, 2026-09-11)
--------------------------------------------------------------
    "Se o record iniciou uma estrategia eu nao inicio uma nova sem
    reiniciar o record. Isso gera perda de dados."

Captura perdida e' o unico ativo do projeto que nao da' para refazer
depois. Entao EAs entram e saem em tempo de execucao, e a captura tem
prioridade absoluta -- mesma filosofia que ja' governa `on_trade_extra`
(excecao do EA e' contida para nao matar o processo) e a fila do
`EABridge` (descarta e conta, nunca bloqueia o hot path).

REGRAS DE CONCORRENCIA
----------------------
`publicar()` roda no HOT PATH (callback da DLL, feed parado esperando).
Portanto:
  - o lock e' segurado SO' para copiar a referencia da tupla, nunca
    durante o `publicar` de cada bridge (senao uma inclusao lenta
    seguraria o feed);
  - a lista e' uma TUPLA IMUTAVEL trocada inteira (copy-on-write), nao
    uma list mutada no lugar -- assim `publicar` itera sobre um
    snapshot consistente sem lock nenhum;
  - `publicar` NUNCA levanta: um EA com bug nao derruba os outros nem a
    captura.
"""

from __future__ import annotations

import threading

import structlog

from ..domain.events import Trade
from .bridge import EABridge

log = structlog.get_logger(__name__)


class DespachanteDeEAs:
    """
    Alvo unico de `on_trade_extra`. Registrado UMA vez na conexao e nunca
    trocado; os EAs entram e saem por dentro.

    Com zero bridges (o caso de partida, quando o record sobe sem EA
    nenhum), `publicar` e' praticamente gratuito -- um `if` sobre uma
    tupla vazia.
    """

    def __init__(self) -> None:
        # Tupla, nao list: `publicar` le sem lock (copy-on-write). Mutar
        # uma list no lugar exigiria lock na LEITURA, no hot path.
        self._bridges: tuple[EABridge, ...] = ()
        self._lock = threading.Lock()
        self._publicados = 0
        self._erros = 0

    # ------------------------------------------------------------------
    # hot path
    # ------------------------------------------------------------------
    def publicar(self, trade: Trade) -> None:
        """
        HOT PATH. Sem lock, sem alocacao, sem log em caminho normal.
        Cada bridge ja' filtra por simbolo e descarta se sua fila encher
        -- aqui so' repassamos.
        """
        bridges = self._bridges          # leitura atomica da referencia
        if not bridges:
            return
        self._publicados += 1
        for bridge in bridges:
            try:
                bridge.publicar(trade)
            except Exception:
                # Um bridge quebrado nao pode impedir os OUTROS de
                # receberem o trade, nem propagar para o callback da DLL.
                self._erros += 1
                log.exception("ea_despachante.erro_publicando",
                             symbol=getattr(bridge, "_simbolo", "?"))

    # ------------------------------------------------------------------
    # mutacao (thread principal do record, nunca do callback)
    # ------------------------------------------------------------------
    def incluir(self, bridge: EABridge) -> None:
        """Adiciona e INICIA o bridge. A troca da tupla e' a ultima coisa
        que acontece -- assim o bridge ja' esta' com a thread rodando
        quando o primeiro trade chegar nele."""
        bridge.iniciar()
        with self._lock:
            self._bridges = (*self._bridges, bridge)
        log.info("ea_despachante.incluido", symbol=bridge._simbolo,
                 total=len(self._bridges))

    def remover(self, bridge: EABridge, timeout_s: float = 5.0) -> bool:
        """
        Tira da tupla PRIMEIRO (para parar de receber trade novo), depois
        para a thread. Devolve False se o bridge nao estava na lista.

        `bridge.parar()` chama `encerrar_dia()`, que zera posicao aberta
        -- por isso a ordem importa: se parassemos antes de remover, um
        trade poderia entrar na fila de um bridge ja' encerrado.
        """
        with self._lock:
            restantes = tuple(b for b in self._bridges if b is not bridge)
            if len(restantes) == len(self._bridges):
                return False
            self._bridges = restantes
        bridge.parar(timeout_s=timeout_s)
        log.info("ea_despachante.removido", symbol=bridge._simbolo,
                 total=len(self._bridges))
        return True

    def parar_todos(self, timeout_s: float = 5.0) -> None:
        """Encerramento do record. Esvazia a tupla antes de parar, pelo
        mesmo motivo de `remover`."""
        with self._lock:
            bridges, self._bridges = self._bridges, ()
        for bridge in bridges:
            try:
                bridge.parar(timeout_s=timeout_s)
            except Exception:
                # Um bridge que falha ao encerrar nao pode impedir os
                # outros de encerrarem (nem o record de terminar).
                log.exception("ea_despachante.erro_ao_parar",
                             symbol=getattr(bridge, "_simbolo", "?"))
        log.info("ea_despachante.parou_todos", quantos=len(bridges))

    # ------------------------------------------------------------------
    @property
    def bridges(self) -> tuple[EABridge, ...]:
        return self._bridges

    def __len__(self) -> int:
        return len(self._bridges)

    def resumo(self) -> dict[str, object]:
        return {
            "eas": len(self._bridges),
            "simbolos": [b._simbolo for b in self._bridges],
            "publicados": self._publicados,
            "erros": self._erros,
        }
