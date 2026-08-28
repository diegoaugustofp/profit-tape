"""
Orquestracao: liga cliente, bus, writer e monitoramento; encerra com ordem.

ORDEM DE ENCERRAMENTO IMPORTA
-----------------------------
    1. parar de receber (DLLFinalize)
    2. sinalizar fim ao bus
    3. esperar o writer drenar o que ficou
    4. fechar os arquivos Parquet (footer!)

Inverter 1 e 3 perde os eventos em transito. Pular 4 deixa arquivo sem footer,
ilegivel. Por isso o `finally` aninhado e o join sem timeout curto.
"""

from __future__ import annotations

import contextlib
import signal
import threading
import time
from datetime import datetime
from pathlib import Path

import structlog

from ..alertas import ConfigAlertas, enviar
from ..config import Credenciais, RecorderConfig
from ..health.metrics import Metrics
from ..pipeline.bus import EventBus, nivel_ocupacao
from ..pipeline.writer import WriterThread
from ..profitdll.client import ProfitClient
from ..storage.parquet_sink import ParquetSink

log = structlog.get_logger(__name__)


class RecorderService:
    def __init__(
        self,
        cfg: RecorderConfig,
        cred: Credenciais,
        dll_injetada: object | None = None,
        ea_config_path: Path | None = None,
    ) -> None:
        self.cfg = cfg
        self.cred = cred
        self.metrics = Metrics()
        # Alertas sao OPCIONAIS: sem config/alertas.yaml, self.alertas fica
        # None e enviar() vira no-op silencioso — o record roda igual, so'
        # sem notificacao remota.
        self.alertas = ConfigAlertas.carregar(Path("config/alertas.yaml"))
        self.bus = EventBus(maxsize=cfg.pipeline.fila_maxsize)
        self.sink = ParquetSink(
            raiz=cfg.storage.raiz,
            max_rows_per_file=cfg.storage.max_rows_per_file,
            compressao=cfg.storage.compressao,
            nivel_compressao=cfg.storage.nivel_compressao,
        )
        self.writer = WriterThread(
            bus=self.bus,
            sink=self.sink,
            metrics=self.metrics,
            batch_max=cfg.pipeline.batch_max,
            poll_timeout=cfg.pipeline.poll_timeout_s,
            idle_close_s=cfg.storage.idle_close_s,
            limiar_lote_lento_s=cfg.pipeline.limiar_lote_lento_s,
        )
        # EA integrado (2026-08-27, decisao de arquitetura de longo prazo):
        # OPCIONAL, None por padrao -- todo caller existente (producao ha'
        # semanas) tem ZERO mudanca de comportamento sem passar
        # ea_config_path explicitamente. Falha CEDO (config invalida) e'
        # aceitavel aqui, ANTES de qualquer captura comecar -- diferente de
        # uma falha DURANTE a sessao, que a EABridge protege via try/except
        # (ver bridge.py). Sempre dry_run=True nesta fase -- SendOrder real
        # usando a MESMA conexao do record e' decisao futura separada.
        self.ea_bridge: EABridge | None = None
        if ea_config_path is not None:
            from ..ea.bridge import EABridge
            from ..ea.config import EAConfig
            from ..ea.service import EAService

            ea_cfg = EAConfig.from_yaml(ea_config_path)
            if not ea_cfg.dry_run:
                raise SystemExit(
                    "ea_config_path com dry_run=False -- o record so' "
                    "suporta o EA em dry_run nesta fase (SendOrder real "
                    "usando a mesma conexao e' decisao futura separada, "
                    "ver EA_ARQUITETURA.md)."
                )
            self.ea_bridge = EABridge(EAService(ea_cfg))
            log.info("recorder.ea_integrado", symbol=ea_cfg.symbol,
                     sinais=[s.feature for s in ea_cfg.sinais])

        self.client = ProfitClient(
            dll_path=cred.dll_path,
            activation_key=cred.activation_key,
            user=cred.user,
            password=cred.password,
            bus=self.bus,
            tz_offset_horas=cfg.runtime.tz_offset_horas,
            on_state=self._on_state,
            on_trade_extra=self.ea_bridge.publicar if self.ea_bridge else None,
            dll=dll_injetada,
        )
        self._parar = threading.Event()

    # ------------------------------------------------------------------
    def _on_state(self, tipo: int, valor: int) -> None:
        log.info("profitdll.estado", tipo=tipo, valor=valor)

    def _instalar_sinais(self) -> None:
        def handler(signum: int, _frame: object) -> None:
            if self._parar.is_set():
                # Segundo Ctrl+C durante o encerramento: sem esta resposta, o
                # silencio induz a acreditar que o primeiro nao registrou (e a
                # apertar de novo, ou matar o processo — que ai sim perde a
                # cauda). O handler customizado ja' impede que o sinal vire
                # KeyboardInterrupt, entao aqui e' so' comunicacao.
                log.warning("recorder.ENCERRAMENTO_JA_EM_ANDAMENTO",
                            nota="aguarde — fila sendo drenada e arquivos "
                                 "sendo fechados; nao e' preciso pressionar de novo")
                return
            log.info("recorder.sinal_recebido", sinal=signum)
            self._parar.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            # Falha quando nao estamos na thread principal (caso dos testes) ou
            # quando a plataforma nao expoe o sinal. Nenhum dos dois e' erro.
            with contextlib.suppress(ValueError, OSError):
                signal.signal(sig, handler)

    # ------------------------------------------------------------------
    def run(self) -> int:
        self._instalar_sinais()
        self.writer.start()
        if self.ea_bridge is not None:
            self.ea_bridge.iniciar()
        try:
            self.client.connect()
            self._subscrever()
            enviar(
                f"✅ record iniciado — {len(self.cfg.ativos)} ativo(s) "
                f"({', '.join(a.ticker for a in self.cfg.ativos)})",
                self.alertas,
            )
            self._loop_monitoramento()
        except Exception as exc:
            log.exception("recorder.erro")
            enviar(f"🔴 record CAIU com erro: {type(exc).__name__}: {exc}", self.alertas)
            return 1
        finally:
            self._encerrar()
        return 0

    def _subscrever(self) -> None:
        for a in self.cfg.ativos:
            if a.trades:
                self.client.subscribe_trades(a.ticker, a.bolsa)
            if a.offer_book:
                self.client.subscribe_offer_book(a.ticker, a.bolsa)
            if a.price_book:
                self.client.subscribe_price_book(a.ticker, a.bolsa)
            log.info(
                "recorder.subscrito",
                ticker=a.ticker,
                trades=a.trades,
                offer_book=a.offer_book,
                price_book=a.price_book,
            )

    # ------------------------------------------------------------------
    def _loop_monitoramento(self) -> None:
        hb = self.cfg.runtime.heartbeat_s
        limite_descarte = self.cfg.runtime.alerta_taxa_descarte
        proximo = time.monotonic()

        while not self._parar.is_set():
            time.sleep(0.5)
            if self._hora_de_encerrar():
                log.info("recorder.encerramento_agendado", horario=self.cfg.runtime.encerrar_em)
                break
            if not self.writer.is_alive():
                log.error("recorder.writer_morreu")
                break
            if time.monotonic() < proximo:
                continue
            proximo = time.monotonic() + hb

            st = self.bus.stats()
            snap = self.metrics.snapshot(
                st.profundidade_atual, st.profundidade_maxima,
                st.total_descartado, st.total_recebido,
            )
            vazao = (int(snap.linhas_escritas / snap.escrita_s_total)
                     if snap.escrita_s_total > 0 else 0)
            log.info(
                "recorder.heartbeat",
                uptime_min=round(snap.uptime_s / 60, 1),
                linhas=snap.linhas_escritas,
                fila=snap.fila_atual,
                fila_pico=snap.fila_pico,
                descartados=snap.descartados,
                arquivos=snap.arquivos_abertos,
                sem_evento_ha_s=round(snap.ultimo_evento_ha_s, 1),
                # Vazao de escrita do writer (linhas/s de tempo GASTO
                # escrevendo). Se cair abaixo da taxa de chegada, a fila sobe
                # — este numero e' o preditor do descarte, nao o descarte.
                escrita_linhas_s=vazao,
            )
            nivel = nivel_ocupacao(st.profundidade_atual, self.bus.maxsize)
            if nivel == "atencao":
                log.warning("recorder.fila_subindo",
                            ocupacao=f"{st.profundidade_atual / self.bus.maxsize:.0%}",
                            causa_tipica="disco lento segurando o writer",
                            mitigacao="ver OPERACAO.md secao 'Disco lento'")
            elif nivel == "critico":
                log.error("recorder.fila_critica",
                          ocupacao=f"{st.profundidade_atual / self.bus.maxsize:.0%}",
                          aviso="descarte iminente se a tendencia continuar")
                enviar(
                    f"🟠 fila CRITICA ({st.profundidade_atual / self.bus.maxsize:.0%}) "
                    f"— descarte iminente. Ver OPERACAO.md 'Disco lento'.",
                    self.alertas,
                )
            if st.taxa_descarte > limite_descarte:
                log.error(
                    "recorder.descarte_acima_do_limite",
                    taxa=round(st.taxa_descarte, 6),
                    descartados=st.total_descartado,
                    acao="aumente fila_maxsize, reduza ativos com offer_book, "
                         "ou mova data/raw para disco mais rapido",
                )

    def _hora_de_encerrar(self) -> bool:
        alvo = self.cfg.runtime.encerrar_em
        if not alvo:
            return False
        agora = datetime.now().strftime("%H:%M")
        return agora >= alvo

    # ------------------------------------------------------------------
    def _encerrar(self) -> None:
        log.info("recorder.encerrando")
        self.client.disconnect()      # 1: para de entrar evento novo
        if self.ea_bridge is not None:
            # ANTES do bus.close() -- protegido internamente (try/except em
            # torno de encerrar_dia(), ver bridge.py); um erro aqui nunca
            # pode impedir o restante do encerramento do record (footer,
            # verificacao, alerta), que e' sempre prioridade.
            self.ea_bridge.parar()
        self.bus.close()              # 2: sentinela
        self.writer.join(timeout=120) # 3: drena o que sobrou
        if self.writer.is_alive():
            log.error("recorder.writer_nao_encerrou", acao="forcando parada")
            self.writer.parar()
            self.writer.join(timeout=30)

        st = self.bus.stats()
        snap = self.metrics.snapshot(
            st.profundidade_atual, st.profundidade_maxima,
            st.total_descartado, st.total_recebido,
        )
        log.info(
            "recorder.resumo",
            eventos_recebidos=st.total_recebido,
            linhas_escritas=snap.linhas_escritas,
            descartados=st.total_descartado,
            taxa_descarte=round(st.taxa_descarte, 8),
            fila_pico=st.profundidade_maxima,
            por_stream=snap.eventos_por_stream,
            full_book_descartados=self.client.full_book_descartados,
            arquivos_verificados=self.writer.sink.arquivos_verificados,
            falhas_verificacao=len(self.writer.sink.falhas_verificacao),
            raiz=str(Path(self.cfg.storage.raiz).resolve()),
        )
        if self.writer.sink.falhas_verificacao:
            log.error("recorder.ARQUIVOS_NAO_CONFIAVEIS",
                      arquivos=self.writer.sink.falhas_verificacao,
                      acao="permanecem .inprogress; investigue o volume antes "
                           "de confiar em qualquer dado desta sessao")
            enviar(
                f"🔴 {len(self.writer.sink.falhas_verificacao)} arquivo(s) NAO "
                f"verificado(s) (footer nao confirmado) — investigue o disco "
                f"antes de confiar no dado de hoje.",
                self.alertas,
            )
        if st.total_descartado:
            log.error(
                "recorder.DADO_PERDIDO",
                eventos=st.total_descartado,
                aviso="as particoes deste dia tem buraco. Registre isso antes de "
                      "usar o dado em backtest.",
            )

        # Alerta de encerramento SEMPRE dispara (graceful ou nao) — e' o que
        # confirma remotamente que o dia foi capturado, sem precisar abrir o
        # notebook a noite. status separado do alerta de erro do run(): aqui
        # e' sempre o ultimo aviso da sessao, com os numeros que importam.
        status = "⚠️ com PROBLEMAS" if (self.writer.sink.falhas_verificacao
                                       or st.total_descartado) else "✅ OK"
        enviar(
            f"{status} record encerrado — {snap.linhas_escritas:,} linhas, "
            f"{st.total_descartado} descartado(s), fila_pico={st.profundidade_maxima}, "
            f"{self.writer.sink.arquivos_verificados} arquivo(s) verificado(s).",
            self.alertas,
        )
