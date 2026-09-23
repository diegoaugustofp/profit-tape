"""
Topo do livro AO VIVO -- o que o EA consulta no instante da decisão.

POR QUE ISTO EXISTE
-------------------
O `tiny_book` (melhor bid e melhor ask, com quantidade) é capturado
desde sempre -- cerca de 1 milhão de eventos por pregão -- e nunca foi
usado ao vivo. Este módulo é a ponte: mantém o último estado conhecido
de cada lado, por símbolo, e responde em O(1).

O valor para uma estratégia de ROMPIMENTO é direto: o desequilíbrio
bid/ask mede a **resistência no caminho**. Romper para cima com o ask
minguado é diferente de romper contra uma oferta grande -- e isso o EA
não tem como derivar dos trades, por mais que os processe.

CONCORRÊNCIA
------------
`atualizar` roda no HOT PATH (callback da DLL, com o feed parado
esperando); `ler` roda na thread do EA. Por isso:

  - o estado é uma TUPLA IMUTÁVEL trocada inteira (copy-on-write), não
    um dict mutado no lugar. Assim `ler` nunca precisa de lock e nunca
    vê um estado meio-atualizado (bid novo com ask velho);
  - `atualizar` não aloca, não loga e não levanta;
  - não há trava alguma no caminho de leitura.

É o mesmo padrão do `DespachanteDeEAs`, pela mesma razão: o que roda
dentro do callback não pode esperar por nada.

O QUE ESTE MÓDULO NÃO FAZ
-------------------------
Não guarda histórico, não agrega por barra e não decide nada. É estado
instantâneo. Agregação por balde de 15s é problema de quem consome --
o módulo de pesquisa (`research/regime_rlp_book.py`) faz isso sobre
parquet, para medir; aqui é o valor de AGORA, para decidir.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from ..domain.events import TinyBook

log = structlog.get_logger(__name__)

LADO_BID, LADO_ASK = 0, 1


@dataclass(frozen=True)
class TopoDoLivro:
    """Estado instantâneo de um símbolo. `None` em preço/quantidade
    significa que aquele lado ainda não chegou nesta sessão -- é
    diferente de zero, que seria 'lado vazio no livro'."""

    symbol: str
    preco_bid: float | None = None
    qtd_bid: int | None = None
    preco_ask: float | None = None
    qtd_ask: int | None = None
    ts_recv_ns: int = 0

    @property
    def completo(self) -> bool:
        return self.qtd_bid is not None and self.qtd_ask is not None

    @property
    def desequilibrio(self) -> float | None:
        """
        (bid - ask)/(bid + ask), em [-1, +1].

        +1 = só há bid (livro de venda vazio): rompimento para CIMA sem
        resistência à frente. -1 = o oposto.

        `None` quando falta um lado ou quando a soma é zero -- nesses
        casos não existe desequilíbrio, e devolver 0,0 seria inventar
        'equilibrado', que é afirmação diferente de 'não sei'.
        """
        if self.qtd_bid is None or self.qtd_ask is None:
            return None
        soma = self.qtd_bid + self.qtd_ask
        if soma <= 0:
            return None
        return (self.qtd_bid - self.qtd_ask) / soma

    def resistencia_a_favor(self, lado: int) -> bool | None:
        """
        A resistência À FRENTE está fina para um rompimento em `lado`
        (+1 compra, -1 venda)?

        Compra rompe para cima: o obstáculo é o ASK, então queremos
        desequilíbrio > 0 (bid dominando, ask minguado).
        Venda rompe para baixo: o obstáculo é o BID, então < 0.

        É ASSIMÉTRICO de propósito -- "à frente" muda de lado conforme a
        direção do rompimento (ficha 10.1).
        """
        d = self.desequilibrio
        if d is None:
            return None
        return d > 0 if lado > 0 else d < 0


class EstadoDoLivro:
    """Um por processo. Alimentado por `on_tiny_extra`."""

    def __init__(self) -> None:
        # Tupla de pares (symbol, TopoDoLivro): `ler` percorre sem lock.
        # Um dict seria mais rápido, mas mutá-lo no lugar exporia leitura
        # parcial ao EA. Com poucos símbolos a varredura é irrelevante.
        self._estado: tuple[tuple[str, TopoDoLivro], ...] = ()
        self.atualizacoes = 0

    def atualizar(self, tb: TinyBook) -> None:
        """HOT PATH. Sem lock, sem log, sem alocação além da tupla."""
        atual = self.ler(tb.symbol) or TopoDoLivro(symbol=tb.symbol)
        if tb.side == LADO_BID:
            novo = TopoDoLivro(tb.symbol, tb.price, tb.quantidade,
                              atual.preco_ask, atual.qtd_ask, tb.ts_recv_ns)
        elif tb.side == LADO_ASK:
            novo = TopoDoLivro(tb.symbol, atual.preco_bid, atual.qtd_bid,
                              tb.price, tb.quantidade, tb.ts_recv_ns)
        else:
            return          # lado desconhecido: ignora, não inventa
        self._estado = tuple(
            (s, novo if s == tb.symbol else v) for s, v in self._estado
        ) if any(s == tb.symbol for s, _ in self._estado) else (
            *self._estado, (tb.symbol, novo))
        self.atualizacoes += 1

    def ler(self, symbol: str) -> TopoDoLivro | None:
        for s, v in self._estado:
            if s == symbol:
                return v
        return None

    def resumo(self) -> dict[str, object]:
        return {
            "simbolos": len(self._estado),
            "atualizacoes": self.atualizacoes,
            "estado": {
                s: {"bid": v.qtd_bid, "ask": v.qtd_ask,
                    "deseq": None if v.desequilibrio is None
                    else round(v.desequilibrio, 3)}
                for s, v in self._estado
            },
        }
