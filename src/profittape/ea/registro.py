"""
E5.4 — RegistroDeEAs: quem pode entrar, quem esta' dentro, quem sai.

A TRAVA CENTRAL DO CAMINHO B (docs/EA_ARQUITETURA 4.2)
-------------------------------------------------------
No caminho B, o que separa a execucao de dois EAs e' o TICKER: entre
ativos distintos nao existe netting na B3, entao a posicao de WIN e a
de WDO sao independentes por definicao -- sem precisar de subconta
(que, alem de bloqueada por licenca, e' produto de mesa proprietaria,
conceito errado para o nosso problema).

O preco disso e' uma restricao que PRECISA ser trava de codigo, nao
convencao: **dois EAs nao podem operar o mesmo ticker**. Se entrassem,
as posicoes voltariam a netar e a reconciliacao (E3) nao saberia de
quem e' a divergencia -- exatamente o problema que o caminho B existe
para evitar. Por isso `incluir()` RECUSA.

POR QUE RECUSAR E' BARATO AQUI
-------------------------------
Como a inclusao e' dinamica (o record ja' esta' rodando), recusar nao
derruba nada: o EA simplesmente nao entra, os outros seguem, a captura
nem percebe. Diferente de uma validacao na inicializacao, onde recusar
significaria nao subir o processo.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import structlog

from .bridge import EABridge
from .config import EAConfig
from .config_123 import EA123Config
from .despachante import DespachanteDeEAs
from .livro import LivroDePosicoes
from .livro_ao_vivo import EstadoDoLivro
from .service import EAService
from .supervisor import ExigenciaDeEA, SupervisorDeRisco, capital_recomendado_para
from .vagas import VagasPorTicker

log = structlog.get_logger(__name__)


class InclusaoRecusada(RuntimeError):
    """Motivo declarado para o EA nao ter entrado. Nunca derruba o
    record -- quem chama loga e segue."""


@dataclass
class EARegistrado:
    nome: str
    symbol: str
    origem: Path | None
    bridge: EABridge


class RegistroDeEAs:
    """
    Um por processo. Dono da lista de EAs vivos e das regras de entrada.

    Nao e' thread-safe por si: todas as mutacoes acontecem na thread
    principal do record (o laco de monitoramento), nunca de dentro de um
    callback -- mesma regra que ja' vale para `OrdemDeTeste` e
    `ReconciliadorPosicao`.
    """

    def __init__(self, despachante: DespachanteDeEAs,
                 supervisor: SupervisorDeRisco | None = None,
                 livro: LivroDePosicoes | None = None,
                 modo_ticker: str = "unico",
                 client: object | None = None,
                 livro_ao_vivo: EstadoDoLivro | None = None) -> None:
        """
        `modo_ticker` (E5.4c, decisao do operador 2026-09-13):

        - "unico" (default): 1 EA por ticker. Um segundo EA no mesmo
          ativo e' RECUSADO na inclusao. E' o caminho B puro -- e' o modo
          honesto para MEDIR uma estrategia, porque nenhum sinal se
          perde por disputa.
        - "exclusivo": varios EAs podem dividir o ticker, mas so' UM fica
          posicionado por vez (quem sinaliza primeiro; quem perde,
          descarta). Nao ha' netting porque nunca ha' duas posicoes
          simultaneas. CONTAMINA a medicao de cada EA -- ver vagas.py.
        """
        if modo_ticker not in ("unico", "exclusivo"):
            raise ValueError("modo_ticker deve ser 'unico' ou 'exclusivo'")
        self._client = client            # o 123 observa reconexao por ele
        self._despachante = despachante
        self._supervisor = supervisor
        self._livro = livro
        self.modo_ticker = modo_ticker
        # Topo do livro compartilhado por TODOS os EAs -- estado unico,
        # alimentado pelo callback da DLL (ver ea/livro_ao_vivo.py).
        self.livro_ao_vivo = livro_ao_vivo
        self.vagas = VagasPorTicker() if modo_ticker == "exclusivo" else None
        self._registrados: dict[str, EARegistrado] = {}

    # ------------------------------------------------------------------
    @property
    def nomes(self) -> list[str]:
        return sorted(self._registrados)

    def tickers_ocupados(self) -> dict[str, str]:
        """ticker -> nome do EA que o ocupa."""
        return {r.symbol: r.nome for r in self._registrados.values()}

    def por_origem(self, caminho: Path) -> EARegistrado | None:
        alvo = caminho.resolve()
        for r in self._registrados.values():
            if r.origem is not None and r.origem == alvo:
                return r
        return None

    # ------------------------------------------------------------------
    def validar(self, cfg: EAConfig | EA123Config, nome: str) -> None:
        """
        Levanta `InclusaoRecusada` se o EA nao puder entrar. Separado de
        `incluir` para dar para checar sem efeito colateral (teste, CLI,
        dry-run).
        """
        if nome in self._registrados:
            raise InclusaoRecusada(
                f"ja' existe um EA chamado {nome!r} -- nomes precisam ser "
                "unicos (o nome e' o que identifica a posicao no livro e "
                "nos logs)")
        dono = self.tickers_ocupados().get(cfg.symbol)
        if dono is not None and self.modo_ticker == "exclusivo":
            # Permitido: a exclusao mutua acontece na POSICAO (vagas.py),
            # nao na inclusao. Dois EAs coexistem no ticker; so' um opera
            # por vez.
            return
        if dono is not None:
            raise InclusaoRecusada(
                f"ticker {cfg.symbol!r} ja' e' operado pelo EA {dono!r}. No "
                "caminho B, o TICKER e' o que separa a execucao de dois EAs "
                "(sem subconta, posicoes no mesmo ativo NETAM e a "
                "reconciliacao nao sabe de quem e' a divergencia). Use um "
                "ativo diferente -- ver EA_ARQUITETURA 4.2.")

    def incluir(self, cfg: EAConfig | EA123Config, nome: str | None = None,
               origem: Path | None = None,
               executor: object | None = None) -> EARegistrado:
        """
        Valida, monta EAService + EABridge, inicia e liga no despachante.
        `nome` explicito vence; senao usa `cfg.nome`; senao o nome do
        arquivo de origem.
        """
        nome_final = nome or cfg.nome or (origem.stem if origem else cfg.symbol)
        self.validar(cfg, nome_final)

        servico: object
        if isinstance(cfg, EA123Config):
            from .service_123 import EA123Service
            servico = EA123Service(cfg, executor=executor, vagas=self.vagas,
                                   nome=nome_final, client=self._client)
        else:
            servico = EAService(cfg, executor=executor,  # type: ignore[arg-type]
                               vagas=self.vagas, nome=nome_final,
                               livro=self.livro_ao_vivo)
        bridge = EABridge(servico)  # type: ignore[arg-type]
        registrado = EARegistrado(nome=nome_final, symbol=cfg.symbol,
                                 origem=origem.resolve() if origem else None,
                                 bridge=bridge)
        # Despachante por ULTIMO: so' comeca a receber trade depois de
        # tudo montado e registrado.
        self._registrados[nome_final] = registrado
        if self._livro is not None:
            # subconta=None de proposito: no caminho B o ticker ja' e'
            # unico por EA, entao (None, ticker) ja' e' chave unica.
            # No modo exclusivo varios EAs dividem o ticker: a chave do
            # livro usa o NOME como discriminador, senao o segundo EA
            # colidiria com o primeiro em (subconta, ticker).
            self._livro.registrar_ea(nome_final, subconta=(
                nome_final if self.modo_ticker == "exclusivo" else ""),
                ticker=cfg.symbol)
        if self._supervisor is not None:
            self._supervisor.registrar(ExigenciaDeEA(
                nome=nome_final,
                # `stop_catastrofico_pontos` e' property derivada do capital
                # configurado; aqui fazemos o caminho inverso (dado o stop
                # que o EA usa de fato, qual capital o sustenta) para que a
                # soma de N EAs seja comparavel ao que o operador tem.
                capital_recomendado=(
                    cfg.capital_recomendado_informativo() if isinstance(cfg, EA123Config)
                    else capital_recomendado_para(
                        cfg.risco.stop_catastrofico_pontos,
                        cfg.tamanho_posicao, cfg.risco.valor_ponto_reais,
                        cfg.risco.risco_max_pct)),
                contratos=cfg.tamanho_posicao, ticker=cfg.symbol, subconta=None))
            self._supervisor.logar()
        self._despachante.incluir(bridge)
        log.warning("ea_registro.incluido", nome=nome_final, symbol=cfg.symbol,
                   dry_run=cfg.dry_run, origem=str(origem) if origem else None,
                   total=len(self._registrados),
                   nota="EA incluido COM O RECORD RODANDO (E5.4)")
        return registrado

    def remover(self, nome: str, timeout_s: float = 5.0) -> bool:
        """
        Retirada graciosa: `bridge.parar()` chama `encerrar_dia()`, que
        zera posicao aberta antes de sair. Um EA nao some com posicao
        viva -- isso criaria a posicao orfa que o `LivroDePosicoes` marca
        como "(ninguem)".
        """
        registrado = self._registrados.pop(nome, None)
        if registrado is None:
            return False
        self._despachante.remover(registrado.bridge, timeout_s=timeout_s)
        if self._livro is not None:
            self._livro.registrar_fechamento(nome)
        if self._supervisor is not None:
            # Sem isto o EA removido continuaria inflando o capital
            # recomendado (defeito pego na conferencia a mao, 2026-09-13).
            self._supervisor.remover(nome)
            self._supervisor.logar()
        log.warning("ea_registro.removido", nome=nome, symbol=registrado.symbol,
                   total=len(self._registrados),
                   nota="posicao zerada no encerramento do EA (retirada graciosa)")
        return True

    def resumo(self) -> dict[str, object]:
        return {
            "eas": len(self._registrados),
            "por_ticker": self.tickers_ocupados(),
        }
