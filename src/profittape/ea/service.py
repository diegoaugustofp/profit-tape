"""
Orquestracao do EA — a peca que liga sinal.py + decisao.py + execucao.py.

FLUXO: em dry_run=True (default), conecta com DLLInitializeMarketLogin
(o MESMO que o record usa todo dia) — nenhuma ordem e' enviada, entao
nao ha' motivo para exigir roteamento. Assina os trades do simbolo,
alimenta um ConstrutorDeSinalAoVivo trade a trade; cada BarraFechada
passa por decisao.decidir() para cada sinal configurado; a Decisao vai
para execucao.executar() — que em dry_run=True SO' LOGA.

Em dry_run=False, conecta com DLLInitializeLogin (login completo, com
roteamento) — e nesse caso o __init__ ja' exige um ExecutorDeOrdens
construido explicitamente.

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
from pathlib import Path

import structlog

from ..config import Credenciais
from ..domain.enums import AtivacaoResult, ConnState, MarketDataResult
from .config import EAConfig, RoteamentoConfig
from .decisao import Acao, Decisao, decidir
from .execucao import ExecutorDeOrdens, executar
from .risco import GestorDeRisco
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
                executor: ExecutorDeOrdens | None = None,
                ignorar_circuit_breaker: bool = False) -> None:
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
        self.gestor = GestorDeRisco(config.risco, config.custo_pontos_estimado,
                                    ignorar_circuit_breaker=ignorar_circuit_breaker)
        self._ultimo_close: float | None = None

    # ------------------------------------------------------------ nucleo
    def processar_trade_bruto(self, t: _TradeBruto) -> list[Decisao]:
        """
        Nucleo puro: um trade entra; se fechar barra, o RISCO decide primeiro
        (posicao aberta -> so' saida forcada ou manter; sinal ignorado); so'
        zerado e desbloqueado o sinal e' consultado para entrada. Devolve as
        decisoes tomadas (para teste e diagnostico).
        """
        self.stats.trades += 1
        barra = self.construtor.processar_trade(
            t.ts_ns, t.price, t.quantidade, t.trade_type,
            t.agente_comprador, t.agente_vendedor)
        if barra is None:
            return []
        self._ultimo_close = barra.close
        return self._decidir_barra(barra)

    def _decidir_barra(self, barra: BarraFechada) -> list[Decisao]:
        self.stats.barras += 1
        decisoes: list[Decisao] = []

        # 1. Com posicao aberta, SO' o risco manda (Rota A: sinal ignorado
        #    ate' a saida por tempo — fiel ao procedimento do research).
        if self.gestor.em_posicao():
            motivo = self.gestor.motivo_de_saida(barra.bar_id, barra.close)
            if motivo is not None:
                d = Decisao(Acao.ZERAR, motivo, 0.0, "_risco")
                decisoes.append(d)
                self._executar_e_simular(d)
                self.gestor.registrar_fechamento(barra.close)
            return decisoes

        # 2. Zerado: circuit breaker primeiro, sinal depois.
        if not self.gestor.pode_abrir():
            return decisoes
        for sinal_cfg in self.config.sinais:
            valor = barra.agf.get(sinal_cfg.agent_id)
            if valor is None or valor != valor:   # NaN (aquecimento da janela)
                continue
            d = decidir(sinal_cfg, valor_atual=valor,
                        posicao_atual=self.stats.posicao_simulada)
            if d.acao not in (Acao.COMPRAR, Acao.VENDER):
                continue
            decisoes.append(d)
            self._executar_e_simular(d)
            lado = +1 if d.acao == Acao.COMPRAR else -1
            self.gestor.registrar_abertura(lado, barra.close, barra.bar_id,
                                           sinal_cfg.horizonte)
            break   # UMA posicao por vez — o primeiro sinal que disparar leva
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
        """ZERAR forcado se houver posicao aberta (fim de pregao). Fecha
        tambem no gestor (P&L com o ultimo close conhecido) para o
        circuit breaker e o pnl_dia ficarem consistentes no log final."""
        if self.stats.posicao_simulada == 0 and not self.gestor.em_posicao():
            return None
        d = Decisao(acao=Acao.ZERAR, motivo="encerramento do dia (posicao aberta)",
                    sinal_valor=0.0, feature="_encerramento")
        self._executar_e_simular(d)
        if self.gestor.em_posicao() and self._ultimo_close is not None:
            self.gestor.registrar_fechamento(self._ultimo_close)
        log.info("ea.encerramento_dia", posicao_zerada=True,
                 pnl_dia_pontos=round(self.gestor.pnl_dia_pontos, 1))
        return d

    # ------------------------------------------------- conexao e loop real
    def rodar(self, cred: Credenciais, bolsa: str = "F",
              encerrar_em: str | None = None, tz_offset_horas: int = -3,
              heartbeat_s: int = 30, dll_injetada: object | None = None) -> None:
        """
        Loop real contra a DLL. Consome trades ate' encerrar_em (ou
        Ctrl+C). Espelha o padrao do contas.py (callbacks todos
        declarados, referencias seguradas).

        CONEXAO DEPENDE DE dry_run (2026-08-26, correcao de design real):
        em dry_run=True (default), NENHUMA ordem e' enviada -- so' dados de
        mercado sao necessarios, entao usa DLLInitializeMarketLogin (o
        MESMO que o record usa todo dia, sem excecao). DLLInitializeLogin
        (login completo, com roteamento) so' e' usado quando dry_run=False
        -- e nesse caso o __init__ ja' exige um ExecutorDeOrdens explicito.

        Motivo pratico: DLLInitializeLogin devolveu NL_INTERNAL_ERROR
        (-2147483647, codigo generico do fornecedor, ver manual) em DOIS
        testes manuais em horarios bem diferentes (madrugada e noite) --
        causa nao confirmada (possivelmente permissao de roteamento nao
        habilitada para a chave de ativacao; assinaturas dos callbacks
        conferidas contra o manual, batem exatamente). Isso NAO deveria
        bloquear o forward-test, que nao precisa de roteamento nenhum.
        """
        from ..profitdll import bindings as b
        from ..profitdll.errors import check
        from ..profitdll.timeparse import parse_ts_ns

        fila: queue.Queue[_TradeBruto] = queue.Queue(maxsize=100_000)
        estado = {"conectado": False, "erro": None}

        dll = dll_injetada if dll_injetada is not None else b.load_dll(cred.dll_path)

        def _on_state(tipo: int, valor: int) -> None:
            log.info("ea.estado", tipo=tipo, valor=valor)
            # BUG REAL corrigido (2026-08-26, mesmo achado de ea/contas.py):
            # "tipo==LOGIN e valor==0" e' so' o PRIMEIRO dos sinais de
            # conexao documentados no manual, nao "pronto". O sinal certo
            # para dado de mercado e' MARKET_DATA -- mesmo padrao que
            # client.py (record) ja' usa ha' semanas sem problema
            # (valor in 2,3,4 = WAITING/NOT_LOGGED/CONNECTED, tolerante).
            # "valor < 0" tambem nunca disparava -- todo codigo de erro
            # documentado e' NAO-NEGATIVO.
            if tipo == ConnState.MARKET_DATA and valor in (
                MarketDataResult.WAITING, MarketDataResult.NOT_LOGGED,
                MarketDataResult.CONNECTED,
            ):
                estado["conectado"] = True
            elif tipo == ConnState.ATIVACAO and valor == AtivacaoResult.INVALID:
                estado["erro"] = (
                    "ATIVACAO INVALIDADA (CONNECTION_ACTIVATE_INVALID) -- "
                    "sessao aceita e depois invalidada pelo servidor."
                )

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
        cb_new_daily = b.TNewDailyCallback(lambda *a: None)
        cb_price_book = b.TPriceBookCallbackV1(lambda *a: None)
        cb_offer_book = b.TOfferBookCallbackV1(lambda *a: None)
        cb_history_trade = b.THistoryTradeCallback(lambda *a: None)
        cb_progress = b.TProgressCallback(lambda *a: None)
        cb_tiny_book = b.TTinyBookCallback(lambda *a: None)

        if self.config.dry_run:
            ret = dll.DLLInitializeMarketLogin(
                cred.activation_key, cred.user, cred.password,
                cb_state, cb_trade, cb_new_daily, cb_price_book,
                cb_offer_book, cb_history_trade, cb_progress, cb_tiny_book)
            nome_init = "DLLInitializeMarketLogin"
        else:
            cb_history = b.THistoryCallback(lambda *a: None)
            cb_order_change = b.TOrderChangeCallback(lambda *a: None)
            cb_account = b.TAccountCallback(lambda *a: None)
            ret = dll.DLLInitializeLogin(
                cred.activation_key, cred.user, cred.password,
                cb_state, cb_history, cb_order_change, cb_account,
                cb_trade, cb_new_daily, cb_price_book, cb_offer_book,
                cb_history_trade, cb_progress, cb_tiny_book)
            nome_init = "DLLInitializeLogin"
        if ret != 0:
            raise SystemExit(f"{nome_init} devolveu {ret} — confira "
                             f"credenciais em .env, ou o log de "
                             f"docs/EA_ARQUITETURA.md para o historico "
                             f"deste erro especifico.")

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

    def rodar_replay(self, raiz_raw: Path) -> None:
        """
        FORWARD-TEST SEM CONEXAO PROPRIA (2026-08-27, resposta a um problema
        real de licenciamento): a chave de ativacao so' permite UMA sessao
        por vez -- duas conexoes MarketLogin simultaneas (record + ea)
        colidem exatamente como MarketLogin+LoginCompleto ja colidia
        (testado na pratica: a segunda tentativa recebe NL_INTERNAL_ERROR
        de forma identica, nao importa qual funcao de login). Rodar o EA
        como processo separado com conexao propria, ao mesmo tempo que o
        record, NAO FUNCIONA com uma unica chave de ativacao.

        Solucao para VALIDAR o EA sem esperar uma segunda chave ou
        redesenhar a arquitetura sob pressao: reler os trades que o
        record JA' CAPTUROU, direto do parquet, e alimentar o MESMO
        nucleo (processar_trade_bruto) que rodaria ao vivo. Nao e' tempo
        real -- roda DEPOIS que o record escreveu os arquivos -- mas usa
        exatamente a mesma logica de sinal/decisao/risco, sem nenhuma
        conexao com a DLL, portanto SEM CONFLITO possivel com o record.

        raiz_raw: caminho do stream trade dentro de data/raw (ex.:
        data/raw/trade/dt=2026-08-27/sym=WINFUT) -- le todos os
        part-*.parquet dali, ordena por ts_ns, alimenta em ordem.
        """
        import time as _time

        import pyarrow.dataset as ds

        arquivos = sorted(raiz_raw.glob("*.parquet"))
        if not arquivos:
            raise SystemExit(f"nenhum parquet em {raiz_raw}")

        # Projecao de colunas (2026-08-27): antes lia TODAS as colunas do
        # parquet (symbol, exchange, trade_id, volume_financeiro, is_edit,
        # ts_recv_ns...), desperdicando tempo/memoria com o que nunca e'
        # usado -- so' as 6 abaixo entram em _TradeBruto.
        colunas = ["ts_ns", "price", "quantidade", "trade_type",
                  "agente_comprador", "agente_vendedor"]
        tabela = ds.dataset(arquivos, format="parquet").to_table(columns=colunas)
        tabela = tabela.sort_by("ts_ns")
        log.info("ea.replay_iniciado", arquivo=str(raiz_raw), linhas=tabela.num_rows,
                 dry_run=self.config.dry_run,
                 sinais=[s.feature for s in self.config.sinais])

        cols = tabela.to_pydict()
        n = tabela.num_rows
        t0 = _time.monotonic()
        # Instrumentacao fina (2026-08-27, pedido real: um replay de dia
        # unico ficou rodando 3+ HORAS sem NENHUMA linha de progresso — o
        # checkpoint antigo (a cada 200k trades) so' apareceria depois de
        # boa parte do dia processado; se algo travar cedo, o operador fica
        # as cegas por horas antes do primeiro sinal. Agora reporta a cada
        # 10k trades, com THROUGHPUT real (trades/s) — um numero caindo
        # para perto de zero e' o sinal inequivoco de travamento real,
        # visivel em segundos, nao em horas.
        for i in range(n):
            self.processar_trade_bruto(_TradeBruto(
                ts_ns=cols["ts_ns"][i],
                price=cols["price"][i],
                quantidade=cols["quantidade"][i],
                trade_type=cols["trade_type"][i],
                agente_comprador=cols["agente_comprador"][i],
                agente_vendedor=cols["agente_vendedor"][i],
            ))
            if (i + 1) % 10_000 == 0:
                decorrido = _time.monotonic() - t0
                throughput = (i + 1) / decorrido if decorrido > 0 else 0.0
                log.info("ea.replay_progresso", linha=i + 1, de=n,
                        pct=round(100 * (i + 1) / n, 1),
                        trades_por_s=round(throughput, 0),
                        decorrido_s=round(decorrido, 1), **self._hb())

        self.encerrar_dia()
        log.info("ea.replay_concluido", **self._hb())

    def _hb(self) -> dict:
        return {"trades": self.stats.trades, "barras": self.stats.barras,
                "decisoes": dict(self.stats.decisoes),
                "posicao": self.stats.posicao_simulada,
                "pnl_dia_pontos": round(self.gestor.pnl_dia_pontos, 1),
                "perdas_seguidas": self.gestor.perdas_consecutivas,
                "bloqueado": self.gestor.bloqueado}

    @staticmethod
    def _hora_de_encerrar(alvo_hhmm: str, tz_offset_horas: int) -> bool:
        tz = timezone(timedelta(hours=tz_offset_horas))
        agora = datetime.now(tz)
        h, m = alvo_hhmm.split(":")
        alvo = agora.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
        return agora >= alvo
