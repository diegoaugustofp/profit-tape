"""
E5.1 — LivroDePosicoes: quem tem o que, em qual subconta.

POR QUE FICA SIMPLES (decisao do operador, 2026-09-11)
-------------------------------------------------------
Com cada EA em sua PROPRIA SUBCONTA, a posicao de um EA e' simplesmente
a posicao daquela subconta -- consultavel direto via GetPositionV2 com
`SubAccountID` preenchido. Nao precisa de rastreio paralelo, nem de
calcular "ordem liquida" para zerar um EA sem mexer no outro, nem de
adivinhar de quem e' uma divergencia.

Se os EAs dividissem a MESMA conta, nada disso valeria: comprar 1 num EA
e vender 1 no outro daria posicao liquida ZERO na B3, indistinguivel de
"nenhum dos dois tem posicao". Foi exatamente para evitar isso que o
operador escolheu subcontas.

O QUE ESTE MODULO FAZ
---------------------
Mantem o que o EA ACHA que tem (`registrar_abertura`/`registrar_fechamento`)
e compara com o que a corretora DIZ que ele tem (`reconciliar`), por
subconta. A comparacao por subconta e' o que permite dizer DE QUEM e' a
divergencia -- impossivel numa conta unica compartilhada.

Nao envia ordem, nao decide nada, nao chama DLL. Estrutura pura,
testavel sem nada -- mesma razao pela qual decisao.py foi o primeiro
modulo do EA a existir de verdade.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ChaveDePosicao:
    """Uma posicao e' identificada por ONDE ela mora (subconta + ticker),
    nao por quem a abriu -- e' assim que a corretora enxerga. `ea` viaja
    junto so' para atribuir responsabilidade nos alertas."""

    subconta: str
    ticker: str


@dataclass
class PosicaoDoEA:
    ea: str
    subconta: str
    ticker: str
    quantidade: int = 0          # com sinal: + comprada, - vendida
    preco_medio: float = 0.0

    @property
    def zerada(self) -> bool:
        return self.quantidade == 0


@dataclass(frozen=True)
class Divergencia:
    ea: str
    subconta: str
    ticker: str
    esperado: int
    encontrado: int

    @property
    def delta(self) -> int:
        """Quanto falta somar ao esperado para chegar no encontrado --
        e' a quantidade que uma correcao teria que executar."""
        return self.encontrado - self.esperado


@dataclass
class LivroDePosicoes:
    """Um por processo. Mapeia EA -> posicao que ele acredita ter."""

    posicoes: dict[str, PosicaoDoEA] = field(default_factory=dict)

    def registrar_ea(self, ea: str, subconta: str, ticker: str) -> None:
        """Idempotente: registrar de novo NAO zera uma posicao existente
        (evita perder estado se a montagem rodar duas vezes)."""
        if ea in self.posicoes:
            atual = self.posicoes[ea]
            if atual.subconta != subconta or atual.ticker != ticker:
                raise ValueError(
                    f"EA {ea!r} ja' registrado em ({atual.subconta}, "
                    f"{atual.ticker}); nao posso remapear para "
                    f"({subconta}, {ticker}) com posicao viva")
            return
        self.posicoes[ea] = PosicaoDoEA(ea=ea, subconta=subconta, ticker=ticker)

    def _exigir(self, ea: str) -> PosicaoDoEA:
        if ea not in self.posicoes:
            raise KeyError(f"EA {ea!r} nao registrado no livro")
        return self.posicoes[ea]

    def registrar_abertura(self, ea: str, quantidade: int, preco: float) -> None:
        """`quantidade` com sinal (+comprada, -vendida). Somar a uma
        posicao existente recalcula o preco medio PONDERADO; inverter o
        lado (de +2 para -1, por exemplo) e' tratado como a posicao nova,
        com o preco novo -- nao faz sentido media ponderada entre lados
        opostos."""
        if quantidade == 0:
            raise ValueError("quantidade nao pode ser zero numa abertura")
        p = self._exigir(ea)
        nova_qtd = p.quantidade + quantidade
        if p.quantidade == 0 or (p.quantidade > 0) != (quantidade > 0):
            # abertura do zero, ou virada de lado: preco novo manda
            p.preco_medio = preco if nova_qtd != 0 else 0.0
        else:
            # mesmo lado: media ponderada pelo tamanho
            total = abs(p.quantidade) + abs(quantidade)
            p.preco_medio = (p.preco_medio * abs(p.quantidade)
                            + preco * abs(quantidade)) / total
        p.quantidade = nova_qtd
        if p.quantidade == 0:
            p.preco_medio = 0.0

    def registrar_fechamento(self, ea: str) -> None:
        p = self._exigir(ea)
        p.quantidade = 0
        p.preco_medio = 0.0

    def esperado(self, ea: str) -> int:
        return self._exigir(ea).quantidade

    def por_subconta(self) -> dict[ChaveDePosicao, int]:
        """Soma por (subconta, ticker) -- e' isto que deve bater com o que
        `GetPositionV2` devolve para aquela subconta. Com um EA por
        subconta (o desenho), cada soma tem uma parcela so'."""
        agregado: dict[ChaveDePosicao, int] = {}
        for p in self.posicoes.values():
            chave = ChaveDePosicao(p.subconta, p.ticker)
            agregado[chave] = agregado.get(chave, 0) + p.quantidade
        return agregado

    def eas_em(self, subconta: str, ticker: str) -> list[str]:
        return sorted(p.ea for p in self.posicoes.values()
                     if p.subconta == subconta and p.ticker == ticker)

    def reconciliar(self, encontrado: dict[ChaveDePosicao, int]) -> list[Divergencia]:
        """
        `encontrado`: o que a corretora diz, por (subconta, ticker) --
        vem de `GetPositionV2` chamado uma vez por subconta.

        Devolve uma `Divergencia` por chave que nao bate. Se a chave tem
        UM EA (o desenho normal), a divergencia e' atribuida a ele. Se
        tem varios (subconta compartilhada -- o supervisor ja' alerta
        sobre isso), o campo `ea` vira a lista juntada, porque
        honestamente NAO da' para saber de quem e': e' a limitacao que
        as subcontas existem para evitar.

        Chaves presentes em `encontrado` mas nao no livro tambem viram
        divergencia (posicao que ninguem reclama -- tipicamente operacao
        manual, que o E3 ja' encontrou ao vivo em 2026-09-11).
        """
        divs: list[Divergencia] = []
        esperado_por_chave = self.por_subconta()
        todas = set(esperado_por_chave) | set(encontrado)
        for chave in sorted(todas, key=lambda c: (c.subconta, c.ticker)):
            esp = esperado_por_chave.get(chave, 0)
            enc = encontrado.get(chave, 0)
            if esp == enc:
                continue
            donos = self.eas_em(chave.subconta, chave.ticker)
            if not donos:
                nome = "(ninguem)"
            elif len(donos) == 1:
                nome = donos[0]
            else:
                nome = "+".join(donos)
            divs.append(Divergencia(ea=nome, subconta=chave.subconta,
                                   ticker=chave.ticker, esperado=esp, encontrado=enc))
        return divs

    def resumo(self) -> dict[str, object]:
        return {
            "eas": len(self.posicoes),
            "posicoes": {
                p.ea: {"subconta": p.subconta, "ticker": p.ticker,
                      "quantidade": p.quantidade,
                      "preco_medio": round(p.preco_medio, 2)}
                for p in sorted(self.posicoes.values(), key=lambda x: x.ea)
            },
        }
