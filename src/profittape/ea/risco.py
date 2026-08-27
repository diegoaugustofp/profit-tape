"""
Gestao de risco — Rota A (fiel ao procedimento validado pelo research).

FRAMEWORK DO OPERADOR (2026-08-26), o que traduz para codigo aqui:
  - Circuit breaker: 3 perdas LIQUIDAS consecutivas -> bloqueia novas
    entradas ate' o proximo dia (o processo do EA e' diario; bloquear ate'
    o fim do processo E' bloquear ate' amanha).
  - Mao fixa: nenhum codigo de escalonamento existe neste modulo, de
    proposito -- tamanho vem fixo do config, ganho recente nao muda nada.
  - Stop catastrofico (derivado de capital x risco_max_pct): o SEGURO do
    capital, cenario de cauda apenas. NAO e' stop tatico.
  - Saida por TEMPO: a posicao fecha `horizonte` barras depois de abrir --
    exatamente o procedimento medido no research (+18.14 pts liquidos em
    z_agf_3 h=3 foi medido ASSIM, nao com alvo/payoff).

ROTA B (alvo/stop com payoff 2:1) fica como evolucao futura, registrada em
docs/EA_ARQUITETURA.md -- exige research proprio (MAE/MFE pre-registrado)
antes de substituir a saida por tempo, porque o sinal ganha por MAGNITUDE
com ~43% de acerto e um alvo fixo cortaria as caudas que pagam a conta.

Enquanto ha' posicao aberta, O SINAL E' IGNORADO (sem piramidar, sem sair
antes da hora) -- so' o risco manda. decidir() so' e' consultado zerado.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from .config import RiscoConfig

log = structlog.get_logger(__name__)


@dataclass
class PosicaoAberta:
    lado: int              # +1 comprado, -1 vendido
    preco_entrada: float
    bar_id_entrada: int
    horizonte: int         # do SinalConfig que abriu — governa a saida por tempo


class GestorDeRisco:
    """
    Uma instancia por simbolo, viva pelo dia inteiro do processo.
    O service consulta ANTES de abrir (pode_abrir) e A CADA barra com
    posicao (motivo_de_saida); registra abertura e fechamento aqui.
    """

    def __init__(self, config: RiscoConfig, custo_pontos: float,
                ignorar_circuit_breaker: bool = False) -> None:
        if config.capital <= 0 or config.risco_max_pct <= 0:
            raise ValueError("capital e risco_max_pct precisam ser positivos")
        self.config = config
        self.custo_pontos = custo_pontos
        self.posicao: PosicaoAberta | None = None
        self.perdas_consecutivas = 0
        self.bloqueado = False
        self.pnl_dia_pontos = 0.0
        self.operacoes_fechadas = 0
        # SO' PARA ANALISE (2026-08-27): permite ver o comportamento do dia
        # INTEIRO sem o circuit breaker interromper cedo -- nunca deve vir
        # de config/ea.yaml versionado, so' de ferramenta de diagnostico
        # (ea-replay-lote --ignorar-circuit-breaker). bloqueado continua
        # sendo CALCULADO normalmente (para saber quando teria disparado em
        # producao), so' nao interrompe pode_abrir().
        self.ignorar_circuit_breaker = ignorar_circuit_breaker
        # Historico de P&L LIQUIDO por operacao fechada -- para analise de
        # distribuicao (media, pior perda, melhor ganho), nao so' o total
        # do dia. Pedido real do operador: "-336 contra outras bem menores
        # e' o oposto do que a expectativa matematica busca" -- precisa da
        # distribuicao, nao so' da soma, para avaliar isso direito.
        self.historico_pnl: list[float] = []
        # Aditivo (2026-08-27, pedido real: separar resultado do EA
        # simulado por lado, mesma pergunta que o mae.py ja' respondia --
        # perdas concentradas no lado de compra, que o MAE ja mostrou sem
        # edge, ou distribuidas nos dois?). Nao muda historico_pnl (usado
        # em teste ja existente) -- so' adiciona o lado ao lado do pnl.
        self.historico_operacoes: list[tuple[int, float]] = []

    # ------------------------------------------------------------- estado
    def em_posicao(self) -> bool:
        return self.posicao is not None

    def pode_abrir(self) -> bool:
        """Circuit breaker: False depois de max_perdas_consecutivas perdas
        liquidas seguidas. Nao ha' desbloqueio no mesmo dia, de proposito.
        Em modo diagnostico (ignorar_circuit_breaker=True), 'bloqueado'
        continua sendo calculado normalmente mas nao impede nova entrada --
        so' para enxergar o comportamento do dia inteiro em analise."""
        if self.ignorar_circuit_breaker:
            return self.posicao is None
        return not self.bloqueado and self.posicao is None

    # ------------------------------------------------------------ eventos
    def registrar_abertura(self, lado: int, preco: float, bar_id: int,
                           horizonte: int) -> None:
        if self.posicao is not None:
            raise RuntimeError("abertura com posicao ja aberta — o service "
                               "nunca deveria permitir isso (sem piramide)")
        if self.bloqueado and not self.ignorar_circuit_breaker:
            raise RuntimeError("abertura com circuit breaker ativo — o "
                               "service deveria ter consultado pode_abrir()")
        if lado not in (+1, -1):
            raise ValueError("lado precisa ser +1 (compra) ou -1 (venda)")
        self.posicao = PosicaoAberta(lado, preco, bar_id, horizonte)
        log.info("risco.abertura", lado=lado, preco=preco, bar_id=bar_id,
                 horizonte=horizonte)

    def motivo_de_saida(self, bar_id_atual: int, preco_atual: float) -> str | None:
        """
        Consultado a cada barra fechada com posicao aberta. Devolve o motivo
        da saida FORCADA, ou None para manter. Ordem de prioridade: stop
        catastrofico primeiro (protecao de capital acima de fidelidade ao
        procedimento), tempo depois.
        """
        p = self.posicao
        if p is None:
            return None
        excursao_contra = (p.preco_entrada - preco_atual) * p.lado
        if excursao_contra >= self.config.stop_catastrofico_pontos:
            return (f"STOP CATASTROFICO: {excursao_contra:.0f} pts contra "
                    f"(limite {self.config.stop_catastrofico_pontos:.0f})")
        if bar_id_atual - p.bar_id_entrada >= p.horizonte:
            return f"saida por tempo: {p.horizonte} barra(s) desde a entrada"
        return None

    def registrar_fechamento(self, preco: float) -> float:
        """
        Fecha a posicao, devolve o P&L LIQUIDO em pontos (bruto - custo).
        Atualiza o circuit breaker: perda liquida incrementa a sequencia,
        ganho liquido ZERA a sequencia (a regra e' consecutivas).
        """
        p = self.posicao
        if p is None:
            raise RuntimeError("fechamento sem posicao aberta")
        pnl_liquido = (preco - p.preco_entrada) * p.lado - self.custo_pontos
        self.posicao = None
        self.operacoes_fechadas += 1
        self.pnl_dia_pontos += pnl_liquido
        self.historico_pnl.append(pnl_liquido)
        self.historico_operacoes.append((p.lado, pnl_liquido))

        if pnl_liquido < 0:
            self.perdas_consecutivas += 1
            if self.perdas_consecutivas >= self.config.max_perdas_consecutivas:
                self.bloqueado = True
                log.warning("risco.circuit_breaker",
                            perdas_consecutivas=self.perdas_consecutivas,
                            pnl_dia=round(self.pnl_dia_pontos, 1),
                            msg="3 perdas seguidas — sem novas entradas ate amanha")
        else:
            self.perdas_consecutivas = 0

        log.info("risco.fechamento", pnl_liquido=round(pnl_liquido, 1),
                 pnl_dia=round(self.pnl_dia_pontos, 1),
                 perdas_consecutivas=self.perdas_consecutivas,
                 bloqueado=self.bloqueado)
        return pnl_liquido
