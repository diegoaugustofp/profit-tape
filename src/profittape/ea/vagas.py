"""
E5.4c — VagasPorTicker: dois EAs no mesmo ticker, so' um posicionado.

O PROBLEMA QUE ISTO RESOLVE
----------------------------
A regra de "1 EA por ticker" (caminho B, EA_ARQUITETURA 4.2) existe por
causa do NETTING: sem subconta, EA A comprado 1 e EA B vendido 1 viram
posicao liquida ZERO na B3 -- indistinguivel de "ninguem tem nada", e a
reconciliacao (E3) nao sabe de quem e' o que.

Mas o netting so' acontece se os DOIS estiverem posicionados ao mesmo
tempo. Se garantirmos que no maximo UM EA tem posicao naquele ticker a
cada instante, nao existe posicao oposta para netar -- e dois EAs podem
dividir o mesmo ativo. E' o modo `exclusivo`.

REGRAS (decididas pelo operador, 2026-09-13)
---------------------------------------------
- **Quem sinalizou primeiro ganha a vaga.** Sem prioridade declarada,
  sem hierarquia entre EAs.
- **Quem perde, DESCARTA o sinal.** Nao fica em espera: quando a vaga
  abrisse, o sinal ja' estaria velho e a entrada sairia em preco que ja'
  correu. Perdeu a vez, segue a vida.
- A vaga e' liberada quando o EA que a tomou zera a posicao.

CUSTO ESTATISTICO, QUE PRECISA ESTAR NA CARA
---------------------------------------------
Isto CONTAMINA a medicao de cada EA. Se o EA B perde metade dos sinais
porque o A estava posicionado, o desempenho medido do B nao e' mais o
da estrategia B -- e' o da estrategia B CONDICIONADA ao que a A fazia.
Para COMPARAR duas estrategias honestamente, tickers separados continuam
sendo melhor. Para OPERAR as duas no mesmo ativo, este modo e' o
caminho certo.

Por isso `sinais_descartados` e' contado por EA e vai para o log: quem
ler o resultado de um EA em modo exclusivo precisa ver quantas vezes
ele ficou de fora.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

import structlog

log = structlog.get_logger(__name__)


@dataclass
class VagasPorTicker:
    """
    Uma instancia por processo, compartilhada por todos os EAService.

    Thread-safe de verdade (lock, nao tupla imutavel como o despachante):
    aqui ha' LEITURA-E-ESCRITA atomica ("pega se estiver livre"), que e'
    exatamente o caso que um snapshot sem lock nao resolve. Cada bridge
    roda na SUA thread, entao dois EAs podem tentar a mesma vaga no mesmo
    instante.

    O lock e' segurado por microssegundos (um dict lookup + atribuicao) e
    NAO no hot path do callback da DLL -- isto roda na thread do bridge,
    depois da barra fechar.
    """

    _dono: dict[str, str] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    descartes: dict[str, int] = field(default_factory=dict)
    simulados: dict[str, int] = field(default_factory=dict)

    def tentar_ocupar(self, ticker: str, ea: str, simulado: bool = False) -> bool:
        """
        True se a vaga era livre (ou ja' era deste EA) e agora e' dele.
        False se outro EA esta' posicionado -- o chamador DESCARTA o
        sinal.

        Reentrante de proposito: o mesmo EA pedindo de novo recebe True,
        para nao quebrar se houver um caminho que peca duas vezes.

        `simulado=True` (EA em dry_run, 2026-09-21): **EA simulado NAO toma
        nem respeita vaga.** A vaga existe para impedir DUAS POSICOES REAIS no
        mesmo ticker; um EA em dry_run nao tem posicao real a proteger. Antes,
        um simulado ocupando a vaga podia BLOQUEAR um sinal REAL (e o
        contrario: em 18/09 o 123 simulado tirou 8 sinais do z_agf_win) --
        com o E4 isso contaminaria a medicao do forward. Agora cada EA
        simulado mede como se estivesse sozinho, e so' os reais disputam.
        """
        if simulado:
            self.simulados[ea] = self.simulados.get(ea, 0) + 1
            return True
        with self._lock:
            atual = self._dono.get(ticker)
            if atual is None or atual == ea:
                self._dono[ticker] = ea
                return True
        self.descartes[ea] = self.descartes.get(ea, 0) + 1
        log.info("ea.vaga_ocupada_por_outro", ticker=ticker, pediu=ea, dono=atual,
                 descartes_deste_ea=self.descartes[ea],
                 nota="sinal DESCARTADO (modo exclusivo: quem sinaliza "
                      "primeiro fica com a vaga ate' zerar)")
        return False

    def liberar(self, ticker: str, ea: str) -> None:
        """Libera se (e so' se) a vaga for deste EA. Liberar a vaga de
        outro seria um bug grave -- por isso a checagem, mesmo que o
        chamador 'saiba' que e' dele."""
        with self._lock:
            if self._dono.get(ticker) == ea:
                del self._dono[ticker]
                liberou = True
            else:
                liberou = False
        if liberou:
            log.info("ea.vaga_liberada", ticker=ticker, ea=ea)

    def dono(self, ticker: str) -> str | None:
        with self._lock:
            return self._dono.get(ticker)

    def resumo(self) -> dict[str, object]:
        with self._lock:
            ocupadas = dict(self._dono)
        return {"ocupadas": ocupadas, "descartes_por_ea": dict(self.descartes)}
