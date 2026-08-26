"""
Orquestracao do EA — a peca que liga sinal.py + decisao.py + execucao.py.

FLUXO: conecta com login COMPLETO (DLLInitializeLogin — mesma conexao
serve market data e roteamento), assina os trades do simbolo, alimenta um
ConstrutorDeSinalAoVivo trade a trade; cada BarraFechada passa por
decisao.decidir() para cada sinal configurado; a Decisao vai para
execucao.executar() — que em dry_run=True (default) SO' LOGA.

POSICAO SIMULADA (decisao de escopo do v1, deliberada): a posicao usada
por decidir() e' atualizada a partir das PROPRIAS decisoes (COMPRAR ->
+tamanho, VENDER -> -tamanho, ZERAR -> 0), nao lida da corretora. Isso e'
exatamente o que o forward-test em dry_run precisa (as decisoes logadas
refletem o que o EA TERIA feito). Rastreamento REAL de posicao (via
OrderChangeCallback / GetPosition, com reconciliacao) e' territorio da
gestao de risco — pre-requisito antes de dry_run=False, nao detalhe.

ENCERRAMENTO: em encerrar_em (HH:MM local), se a posicao simulada nao for
zero, emite um ZERAR forcado (mesmo caminho de execucao) e para. O EA
NUNCA carrega posicao overnight por design (day trade, custo de carrego
mata o sinal — ver RESEARCH_PLANO.md, secao de custos).
"""

from __future__ import annotations

import queue
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import structlog

from ..config import Credenciais
from .config import EAConfig, RoteamentoConfig
from .decisao import Acao, Decisao, decidir
from .execucao import ExecutorDeOrdens, executar
from .sinal import BarraFechada, ConstrutorDeSinalAoVivo

log = structlog.get_logger(__name__)


@dataclass
class _TradeBruto:
    ts_ns: int
    price: float
    quantidade: int
    trade_type: int
    agente_comprador: int
    agente_vendedor: int


@dataclass
class EstatisticasEA:
    trades: int = 0
    barras: int = 0
    decisoes: dict[str, int] = field(default_factory=dict)
    posicao_simulada: int = 0


class EAService:
    """
    Uma instancia por simbolo (igual ConstrutorDeSinalAoVivo). Testavel sem
    DLL: processar_trade_bruto() e' o nucleo, alimentavel diretamente.
    """

    def __init__(self, config: EAConfig, roteamento: RoteamentoConfig | None = None,
                executor: ExecutorDeOrdens | None = None) -> None:
        if not config.dry_run and executor is None:
            raise RuntimeError(
                "dry_run=False exige um ExecutorDeOrdens construido "
                "explicitamente (ver execucao.py, camadas de protecao)."
            )
        self.config = config
        self.executor = executor
        agentes = [s.agent_id for s in config.sinais]
        self.construtor = ConstrutorDeSinalAoVivo(
            config.volume_barra, config.janela_z, agentes)
        self.stats = EstatisticasEA()

    # ------------------------------------------------------------ nucleo
    def processar_trade_bruto(self, t: _TradeBruto) -> list[Decisao]:
        """
        Nucleo puro: um trade entra; se fechar barra, decide para cada
        sinal configurado e executa. Devolve as decisoes tomadas (para
        teste e diagnostico) — em dry_run elas ja' foram logadas.
        """
        self.stats.trades += 1
        barra = self.construtor.processar_trade(
            t.ts_ns, t.price, t.quantidade, t.trade_type,
            t.agente_comprador, t.agente_vendedor)
        if barra is None:
            return []
        return self._decidir_barra(barra)

    def _decidir_barra(self, barra: BarraFechada) -> list[Decisao]:
        self.stats.barras += 1
        decisoes: list[Decisao] = []
        for sinal_cfg in self.config.sinais:
            valor = barra.agf.get(sinal_cfg.agent_id)
            if valor is None or valor != valor:   # NaN (aquecimento da janela)
                continue
            d = decidir(sinal_cfg, valor_atual=valor,
                        posicao_atual=self.stats.posicao_simulada)
            decisoes.append(d)
            self._executar_e_simular(d)
        if decisoes:
            log.info("ea.barra_fechada", bar_id=barra.bar_id,
                     close=barra.close, vol_agr=barra.vol_agr,
                     posicao=self.stats.posicao_simulada)
        return decisoes

    def _executar_e_simular(self, d: Decisao) -> None:
        self.stats.decisoes[d.acao.value] = self.stats.decisoes.get(d.acao.value, 0) + 1
        executar(d, dry_run=self.config.dry_run, executor=self.executor)
        # Simulacao de posicao a partir da PROPRIA decisao (ver docstring).
        if d.acao == Acao.COMPRAR:
            self.stats.posicao_simulada += self.config.tamanho_posicao
        elif d.acao == Acao.VENDER:
            self.stats.posicao_simulada -= self.config.tamanho_posicao
        elif d.acao == Acao.ZERAR:
            self.stats.posicao_simulada = 0

    def encerrar_dia(self) -> Decisao | None:
        """ZERAR forcado se houver posicao simulada aberta (fim de pregao)."""
        if self.stats.posicao_simulada == 0:
            return None
        d = Decisao(acao=Acao.ZERAR, motivo="encerramento do dia (posicao aberta)",
                    sinal_valor=0.0, feature="_encerramento")
        self._executar_e_simular(d)
        log.info("ea.encerramento_dia", posicao_zerada=True)
        return d

    # ------------------------------------------------- conexao e loop real
    def rodar(self, cred: Credenciais, bolsa: str = "F",
              encerrar_em: str | None = None, tz_offset_horas: int = -3,
              heartbeat_s: int = 30, dll_injetada: object | None = None) -> None:
        """
        Loop real contra a DLL. Conecta (login completo), assina o simbolo,
        consome trades ate' encerrar_em (ou Ctrl+C). Espelha o padrao do
        contas.py (callbacks todos declarados, referencias seguradas).
        """
        from ..profitdll import bindings as b
        from ..profitdll.errors import check
        from ..profitdll.timeparse import parse_ts_ns

        fila: queue.Queue[_TradeBruto] = queue.Queue(maxsize=100_000)
        estado = {"conectado": False, "erro": None}

        dll = dll_injetada if dll_injetada is not None else b.load_dll(cred.dll_path)

        def _on_state(tipo: int, valor: int) -> None:
            log.info("ea.estado", tipo=tipo, valor=valor)
            if tipo == 0 and valor == 0:
                estado["conectado"] = True
            elif valor < 0:
                estado["erro"] = f"tipo={tipo} valor={valor}"

        def _on_trade(ativo, data, numero, preco, vol, qtd, comp, vend,
                      tipo, edit) -> None:
            try:   # noqa: SIM105 — explicito de proposito: callback da DLL,
                # perder 1 trade e' melhor que qualquer risco de travar aqui
                fila.put_nowait(_TradeBruto(
                    ts_ns=parse_ts_ns(data, tz_offset_horas),
                    price=float(preco), quantidade=int(qtd),
                    trade_type=int(tipo),
                    agente_comprador=int(comp), agente_vendedor=int(vend)))
            except queue.Full:   # pragma: no cover — melhor perder 1 trade que travar a DLL
                pass

        cb_state = b.TStateCallback(_on_state)
        cb_trade = b.TNewTradeCallback(_on_trade)
        cb_history = b.THistoryCallback(lambda *a: None)
        cb_order_change = b.TOrderChangeCallback(lambda *a: None)
        cb_account = b.TAccountCallback(lambda *a: None)
        cb_new_daily = b.TNewDailyCallback(lambda *a: None)
        cb_price_book = b.TPriceBookCallbackV1(lambda *a: None)
        cb_offer_book = b.TOfferBookCallbackV1(lambda *a: None)
        cb_history_trade = b.THistoryTradeCallback(lambda *a: None)
        cb_progress = b.TProgressCallback(lambda *a: None)
        cb_tiny_book = b.TTinyBookCallback(lambda *a: None)

        ret = dll.DLLInitializeLogin(
            cred.activation_key, cred.user, cred.password,
            cb_state, cb_history, cb_order_change, cb_account,
            cb_trade, cb_new_daily, cb_price_book, cb_offer_book,
            cb_history_trade, cb_progress, cb_tiny_book)
        if ret != 0:
            raise SystemExit(f"DLLInitializeLogin devolveu {ret} — confira "
                             f"credenciais/horario (servico de roteamento tem "
                             f"janela de disponibilidade propria).")

        t0 = time.monotonic()
        while not estado["conectado"]:
            if estado["erro"]:
                raise SystemExit(f"estado de erro: {estado['erro']}")
            if time.monotonic() - t0 > 30:
                raise SystemExit("nao conectou em 30s")
            time.sleep(0.2)

        check(dll.SubscribeTicker(self.config.symbol, bolsa),
              f"SubscribeTicker {self.config.symbol}")
        log.info("ea.iniciado", symbol=self.config.symbol,
                 dry_run=self.config.dry_run,
                 volume_barra=self.config.volume_barra,
                 sinais=[s.feature for s in self.config.sinais])

        ultimo_hb = time.monotonic()
        try:
            while True:
                try:
                    t = fila.get(timeout=0.5)
                    self.processar_trade_bruto(t)
                except queue.Empty:
                    pass
                agora = time.monotonic()
                if agora - ultimo_hb >= heartbeat_s:
                    log.info("ea.heartbeat", **self._hb())
                    ultimo_hb = agora
                if encerrar_em and self._hora_de_encerrar(encerrar_em, tz_offset_horas):
                    log.info("ea.encerramento_agendado", alvo=encerrar_em)
                    break
        except KeyboardInterrupt:
            log.info("ea.interrompido_pelo_usuario")
        finally:
            self.encerrar_dia()
            dll.DLLFinalize()
            log.info("ea.finalizado", **self._hb())

    def _hb(self) -> dict:
        return {"trades": self.stats.trades, "barras": self.stats.barras,
                "decisoes": dict(self.stats.decisoes),
                "posicao": self.stats.posicao_simulada}

    @staticmethod
    def _hora_de_encerrar(alvo_hhmm: str, tz_offset_horas: int) -> bool:
        tz = timezone(timedelta(hours=tz_offset_horas))
        agora = datetime.now(tz)
        h, m = alvo_hhmm.split(":")
        alvo = agora.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
        return agora >= alvo
