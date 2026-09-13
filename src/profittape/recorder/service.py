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
from typing import TYPE_CHECKING

import structlog

from ..alertas import ConfigAlertas, enviar
from ..config import Credenciais, RecorderConfig
from ..ea.config import EAConfig
from ..ea.despachante import DespachanteDeEAs
from ..ea.livro import LivroDePosicoes
from ..ea.registro import RegistroDeEAs
from ..ea.supervisor import SupervisorDeRisco
from ..health.metrics import Metrics
from ..pipeline.bus import EventBus, nivel_ocupacao
from ..pipeline.writer import WriterThread
from ..profitdll.client import ProfitClient
from ..storage.parquet_sink import ParquetSink

if TYPE_CHECKING:
    from ..ea.config import EAConfig
    from ..ea.ordem_teste import OrdemDeTeste
    from ..ea.reconciliacao import ReconciliadorPosicao

log = structlog.get_logger(__name__)


class RecorderService:
    # Intervalo da varredura de `--ea-dir` (E5.4b). 5 s e' folgado: incluir
    # um EA nao e' operacao de urgencia, e varrer disco a cada 0,5 s (o
    # passo do laco) seria desperdicio.
    _EA_DIR_INTERVALO_S = 5.0

    def __init__(
        self,
        cfg: RecorderConfig,
        cred: Credenciais,
        dll_injetada: object | None = None,
        ea_config_path: Path | None = None,
        ordem_teste_em: str | None = None,
        ordem_teste_ticker: str = "WINFUT",
        reconciliar_em: str | None = None,
        reconciliar_ticker: str = "WINFUT",
        reconciliar_esperado: int = 0,
        ea_ticker_ordem: str | None = None,
        ea_dir: Path | str | None = None,
        capital_em_conta: float = 0.0,
        ea_modo_ticker: str = "unico",
    ) -> None:
        self.cfg = cfg
        self.cred = cred
        # E2 dentro do record (2026-09-11): uma ordem de teste na conta de
        # simulacao, no horario dado, ticada pela thread principal. Exige
        # login_completo. Construida DEPOIS do client (precisa dele).
        self._ordem_teste_em = ordem_teste_em
        self.ordem_teste: OrdemDeTeste | None = None
        # E3 dentro do record (2026-09-11): reconciliacao de posicao no
        # horario dado -- consulta a corretora e zera se divergir do
        # esperado. Mesmo padrao do E2: ticada pela thread principal,
        # construida depois do client.
        self._reconciliar_em = reconciliar_em
        self.reconciliador: ReconciliadorPosicao | None = None
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
        # (ver bridge.py).
        #
        # E4 (2026-09-11): dry_run=False agora e' suportado, mas SO' em
        # demo (apenas_simulador=True, hardcoded -- nao e' opcao) e SO'
        # com o contrato ESPECIFICO (`ea_ticker_ordem`, nunca
        # `ea_cfg.symbol`, que e' "WINFUT" -- o agregador que a DLL
        # aceita para dado mas rejeita no envio de ordem, medido no E2).
        # E5.4b (2026-09-13): o despachante e' o alvo FIXO de
        # `on_trade_extra` -- registrado UMA vez na construcao do client e
        # nunca trocado. Os EAs entram e saem DELE em tempo de execucao,
        # sem reiniciar o record (decisao do operador: reiniciar perde
        # captura, o unico ativo que nao da' para refazer).
        #
        # Isto substitui o esquema anterior de duas fases: antes, ligar o
        # EA com ordens reais exigia trocar `client._on_trade_extra` DEPOIS
        # de construir o client -- o que so' funcionava porque `connect()`
        # ainda nao tinha rodado. Com o despachante, nao ha' mais troca de
        # atributo: o alvo e' estavel desde o inicio.
        # True depois que `run()` comeca -- muda o tratamento de erro de
        # EA: na construcao da' para morrer (nada capturado ainda), em
        # execucao NUNCA (derrubaria a captura). Definido ANTES de
        # qualquer inclusao de EA, que ja' o consulta.
        self._em_execucao = False
        self.despachante = DespachanteDeEAs()
        self.supervisor = SupervisorDeRisco(capital_em_conta=capital_em_conta)
        self.livro = LivroDePosicoes()
        self.registro = RegistroDeEAs(self.despachante, supervisor=self.supervisor,
                                      livro=self.livro, modo_ticker=ea_modo_ticker)
        if ea_modo_ticker == "exclusivo":
            log.warning("recorder.ea_modo_exclusivo",
                       nota="varios EAs podem dividir um ticker; so' UM fica "
                            "posicionado por vez (quem sinaliza primeiro; quem "
                            "perde DESCARTA o sinal). Isso CONTAMINA a medicao "
                            "de cada EA -- ver `sinais_sem_vaga` no heartbeat.")
        self._ea_dir = Path(ea_dir) if ea_dir else None
        self._ea_ticker_ordem = ea_ticker_ordem
        self._ea_config_path = ea_config_path
        self._proxima_varredura = 0.0
        if ea_config_path is not None:
            # Validacao CEDO (antes de qualquer captura comecar): config
            # invalida derruba o processo aqui, nao no meio do pregao.
            ea_cfg = EAConfig.from_yaml(ea_config_path)
            self._exigir_pre_requisitos_de_ordem_real(ea_cfg, ea_config_path)

        self.client = ProfitClient(
            dll_path=cred.dll_path,
            activation_key=cred.activation_key,
            user=cred.user,
            password=cred.password,
            bus=self.bus,
            tz_offset_horas=cfg.runtime.tz_offset_horas,
            on_state=self._on_state,
            on_trade_extra=self.despachante.publicar,
            dll=dll_injetada,
            login_completo=cfg.runtime.login_completo,
        )
        if cfg.runtime.login_completo:
            log.warning(
                "recorder.login_completo",
                nota="conexao sobe com DLLInitializeLogin (roteamento). "
                "E1 da trilha de execucao -- confira o heartbeat: "
                "corretora_pronta=True e contas>=1 devem aparecer.",
            )
        if self._ea_config_path is not None:
            # EA inicial entra pelo MESMO caminho de um EA incluido a
            # quente (`_incluir_ea`), com as mesmas travas. Antes do E5.4b
            # havia dois caminhos diferentes; um so' significa que o que
            # vale no pregao vale no startup.
            self._incluir_ea(self._ea_config_path)

        if ordem_teste_em is not None:
            if not cfg.runtime.login_completo:
                raise SystemExit(
                    "--ordem-teste-em exige login completo (--login-completo "
                    "ou runtime.login_completo: true): sem sessao de "
                    "roteamento nao ha' onde enviar."
                )
            from ..ea.config import RoteamentoConfig
            from ..ea.ordem_teste import OrdemDeTeste, TickerAgregadorInvalido

            try:
                self.ordem_teste = OrdemDeTeste(
                    self.client,
                    RoteamentoConfig(),
                    horario_hhmm=ordem_teste_em,
                    ticker=ordem_teste_ticker,
                )
            except TickerAgregadorInvalido as exc:
                # Falha AQUI, no startup, antes de qualquer conexao -- nao
                # 10 minutos depois, no pregao, com "Ordem invalida" vindo
                # da B3 (e' o que aconteceu em 2026-09-11 com WINFUT).
                raise SystemExit(
                    f"{exc}\n--ordem-teste-ticker recebeu {ordem_teste_ticker!r}."
                ) from exc
            log.warning(
                "recorder.ordem_teste_agendada",
                horario=ordem_teste_em,
                ticker=ordem_teste_ticker,
                nota="E2: 1 contrato a mercado na conta de SIMULACAO "
                "(trava pela DLL) e zeragem em seguida.",
            )
        if reconciliar_em is not None:
            if not cfg.runtime.login_completo:
                raise SystemExit(
                    "--reconciliar-em exige login completo (--login-completo "
                    "ou runtime.login_completo: true): sem sessao de "
                    "roteamento nao ha' onde consultar posicao."
                )
            from ..ea.config import RoteamentoConfig
            from ..ea.ordem_teste import TickerAgregadorInvalido
            from ..ea.reconciliacao import ReconciliadorPosicao

            try:
                self.reconciliador = ReconciliadorPosicao(
                    self.client,
                    RoteamentoConfig(),
                    horario_hhmm=reconciliar_em,
                    ticker=reconciliar_ticker,
                    esperado=reconciliar_esperado,
                )
            except TickerAgregadorInvalido as exc:
                raise SystemExit(
                    f"{exc}\n--reconciliar-ticker recebeu {reconciliar_ticker!r}."
                ) from exc
            log.warning(
                "recorder.reconciliacao_agendada",
                horario=reconciliar_em,
                ticker=reconciliar_ticker,
                esperado=reconciliar_esperado,
                nota="E3: consulta a posicao na corretora (GetPositionV2, "
                "NAO VERIFICADO contra a DLL real -- ver profitdll/types.py) "
                "e ZERA A MERCADO se divergir do esperado (trava: so' "
                "Simulador).",
            )
        self._parar = threading.Event()

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # EAs a quente (E5.4b) -- tudo roda na THREAD PRINCIPAL (construcao ou
    # laco de monitoramento), nunca de dentro de um callback da DLL.
    # ------------------------------------------------------------------
    def _exigir_pre_requisitos_de_ordem_real(self, ea_cfg: EAConfig,
                                            origem: Path) -> None:
        """Falha ALTO e cedo se o EA pede ordem real sem o necessario.
        Chamado na construcao (EA inicial) e antes de incluir a quente."""
        if ea_cfg.dry_run:
            return
        if not self._ea_ticker_ordem:
            raise SystemExit(
                f"{origem}: dry_run=False exige --ea-ticker-ordem (o contrato "
                "ESPECIFICO em vigor, ex.: WINV26 -- nunca o symbol da config, "
                "que e' o agregador 'WINFUT'). E4: forward em demo com ordens "
                "reais."
            )
        if not self.cfg.runtime.login_completo:
            raise SystemExit(
                f"{origem}: dry_run=False exige login completo "
                "(--login-completo ou runtime.login_completo: true): sem "
                "sessao de roteamento nao ha' onde enviar."
            )

    def _incluir_ea(self, caminho: Path) -> bool:
        """
        Le o yaml, valida e inclui. Devolve True se entrou.

        NUNCA levanta por culpa do EA: um yaml invalido, um ticker
        repetido ou um erro de montagem sao LOGADOS e a captura segue --
        e' o principio do E5.4b (o record nao para por causa de EA). A
        unica excecao e' `SystemExit` de pre-requisito de ordem real, e
        so' na construcao (onde ainda nao ha' captura a perder).
        """
        from ..ea.config import EAConfig, RoteamentoConfig
        from ..ea.execucao import ExecutorDeOrdens
        from ..ea.ordem_teste import TickerAgregadorInvalido
        from ..ea.registro import InclusaoRecusada

        try:
            ea_cfg = EAConfig.from_yaml(caminho)
        except Exception as exc:
            log.error("recorder.ea_yaml_invalido", origem=str(caminho), erro=repr(exc))
            return False

        executor = None
        if not ea_cfg.dry_run:
            if self._em_execucao:
                # A quente: nao da' para matar o processo -- so' recusa.
                if not self._ea_ticker_ordem or not self.cfg.runtime.login_completo:
                    log.error("recorder.ea_ordens_reais_sem_pre_requisito",
                             origem=str(caminho),
                             tem_ticker=bool(self._ea_ticker_ordem),
                             login_completo=self.cfg.runtime.login_completo,
                             nota="EA com dry_run=False precisa de "
                                  "--ea-ticker-ordem e login completo; nao incluido")
                    return False
            else:
                self._exigir_pre_requisitos_de_ordem_real(ea_cfg, caminho)
            assert self._ea_ticker_ordem is not None  # validado logo acima
            try:
                executor = ExecutorDeOrdens(
                    self.client, RoteamentoConfig(), self._ea_ticker_ordem, "F",
                    ea_cfg.tamanho_posicao,
                    usar_conta_real=False,   # HARDCODED -- E4/E5 nunca e' real
                    apenas_simulador=True,   # HARDCODED -- exigir_simulador sempre
                )
            except TickerAgregadorInvalido as exc:
                # Na CONSTRUCAO isto e' fatal: o operador pediu ordem real
                # com um ticker que a DLL nunca aceitaria ("Ordem invalida"
                # no meio do pregao, medido no E2). Melhor nao subir.
                # A QUENTE seria inaceitavel matar o processo -- ai' so'
                # recusa o EA e a captura segue.
                if not self._em_execucao:
                    raise SystemExit(
                        f"{exc}\n--ea-ticker-ordem recebeu {self._ea_ticker_ordem!r} "
                        f"(exigido por {caminho}, que tem dry_run=False)."
                    ) from exc
                log.error("recorder.ea_ticker_agregador_recusado",
                         origem=str(caminho), ticker=self._ea_ticker_ordem,
                         erro=str(exc))
                return False
            except Exception as exc:
                log.error("recorder.ea_executor_recusado", origem=str(caminho),
                         erro=repr(exc))
                return False

        try:
            registrado = self.registro.incluir(ea_cfg, origem=caminho, executor=executor)
        except InclusaoRecusada as exc:
            log.error("recorder.ea_inclusao_recusada", origem=str(caminho),
                     motivo=str(exc))
            return False
        except Exception as exc:
            log.exception("recorder.ea_inclusao_falhou", origem=str(caminho),
                         erro=repr(exc))
            return False
        log.warning("recorder.ea_incluido", nome=registrado.nome,
                   symbol=registrado.symbol, dry_run=ea_cfg.dry_run,
                   origem=str(caminho), a_quente=self._em_execucao,
                   total=len(self.registro.nomes))
        return True

    def _varrer_ea_dir(self) -> None:
        """
        Chamado pelo laco de monitoramento. YAML novo -> inclui; YAML que
        sumiu -> remove (graciosamente: o EA zera posicao antes de sair).

        Erro de I/O na pasta e' logado e ignorado -- uma pasta em rede
        indisponivel nao pode derrubar a captura.
        """
        assert self._ea_dir is not None
        try:
            arquivos = {p.resolve() for p in self._ea_dir.glob("*.yaml")}
        except OSError as exc:
            log.warning("recorder.ea_dir_ilegivel", dir=str(self._ea_dir), erro=repr(exc))
            return

        registrados = {r.origem: r for r in
                      (self.registro._registrados[n] for n in self.registro.nomes)
                      if r.origem is not None}
        for novo in sorted(arquivos - set(registrados)):
            self._incluir_ea(novo)
        for sumiu in sorted(set(registrados) - arquivos):
            nome = registrados[sumiu].nome
            log.warning("recorder.ea_removido_por_arquivo", nome=nome,
                       origem=str(sumiu),
                       nota="yaml removido da pasta -- retirada graciosa "
                            "(zera posicao antes de sair)")
            self.registro.remover(nome)

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
                log.warning(
                    "recorder.ENCERRAMENTO_JA_EM_ANDAMENTO",
                    nota="aguarde — fila sendo drenada e arquivos "
                    "sendo fechados; nao e' preciso pressionar de novo",
                )
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
        self._em_execucao = True
        self.writer.start()
        # Os bridges ja' foram iniciados por `registro.incluir` (o
        # despachante inicia cada um ao incluir) -- nada a fazer aqui.
        if self._ea_dir is not None:
            log.warning("recorder.ea_dir_vigiada", dir=str(self._ea_dir),
                       intervalo_s=self._EA_DIR_INTERVALO_S,
                       nota="E5.4b: yaml novo nessa pasta inclui um EA; yaml "
                            "removido retira (graciosamente). Record NAO para.")
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
        contas_logadas: list[tuple[int, str]] = []

        while not self._parar.is_set():
            time.sleep(0.5)
            if self.ordem_teste is not None and not self.ordem_teste.concluida:
                self.ordem_teste.tick()  # thread principal, nunca callback
            if self.reconciliador is not None and not self.reconciliador.concluida:
                self.reconciliador.tick()  # thread principal, nunca callback
            if self._ea_dir is not None and time.monotonic() >= self._proxima_varredura:
                # Varredura da pasta de EAs: thread principal, nunca
                # callback. Protegida por dentro (`_varrer_ea_dir` engole
                # erro de I/O) -- uma pasta em rede fora do ar nao pode
                # derrubar a captura.
                self._proxima_varredura = time.monotonic() + self._EA_DIR_INTERVALO_S
                self._varrer_ea_dir()
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
                st.profundidade_atual,
                st.profundidade_maxima,
                st.total_descartado,
                st.total_recebido,
            )
            vazao = (
                int(snap.linhas_escritas / snap.escrita_s_total) if snap.escrita_s_total > 0 else 0
            )
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
                # E1: so' informativo no MarketLogin (sempre False/0). No
                # login completo, roteamento_conectado=True e contas>0 sao a
                # prova de que a sessao de roteamento subiu junto com a
                # captura -- e' o que o teste A do E1 le.
                login_ok=self.client.conectado_login,
                corretora_pronta=self.client.corretora_pronta,
                contas=len(self.client.contas_vistas),
                contas_callbacks=self.client.contadores_roteamento["conta"],
            )
            # v2.08: os pares (corretora, conta) UMA vez, quando a lista
            # mudar -- da thread principal, nunca do callback. E' o que
            # decide o "14 contas" do teste A: duplicata ou entrada real.
            contas_agora = list(self.client.contas_vistas)
            if contas_agora != contas_logadas:
                log.info(
                    "profitdll.contas",
                    pares=[f"{c}:{a}" for c, a in contas_agora],
                    unicas=len(contas_agora),
                    callbacks=self.client.contadores_roteamento["conta"],
                )
                contas_logadas = contas_agora
            nivel = nivel_ocupacao(st.profundidade_atual, self.bus.maxsize)
            if nivel == "atencao":
                log.warning(
                    "recorder.fila_subindo",
                    ocupacao=f"{st.profundidade_atual / self.bus.maxsize:.0%}",
                    causa_tipica="disco lento segurando o writer",
                    mitigacao="ver OPERACAO.md secao 'Disco lento'",
                )
            elif nivel == "critico":
                log.error(
                    "recorder.fila_critica",
                    ocupacao=f"{st.profundidade_atual / self.bus.maxsize:.0%}",
                    aviso="descarte iminente se a tendencia continuar",
                )
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
        self.client.disconnect()  # 1: para de entrar evento novo
        # ANTES do bus.close() -- protegido internamente (try/except em
        # torno de encerrar_dia(), ver bridge.py e despachante.py); um erro
        # aqui nunca pode impedir o restante do encerramento do record
        # (footer, verificacao, alerta), que e' sempre prioridade.
        self.despachante.parar_todos()
        self.bus.close()  # 2: sentinela
        self.writer.join(timeout=120)  # 3: drena o que sobrou
        if self.writer.is_alive():
            log.error("recorder.writer_nao_encerrou", acao="forcando parada")
            self.writer.parar()
            self.writer.join(timeout=30)

        st = self.bus.stats()
        snap = self.metrics.snapshot(
            st.profundidade_atual,
            st.profundidade_maxima,
            st.total_descartado,
            st.total_recebido,
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
            log.error(
                "recorder.ARQUIVOS_NAO_CONFIAVEIS",
                arquivos=self.writer.sink.falhas_verificacao,
                acao="permanecem .inprogress; investigue o volume antes "
                "de confiar em qualquer dado desta sessao",
            )
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
        status = (
            "⚠️ com PROBLEMAS"
            if (self.writer.sink.falhas_verificacao or st.total_descartado)
            else "✅ OK"
        )
        enviar(
            f"{status} record encerrado — {snap.linhas_escritas:,} linhas, "
            f"{st.total_descartado} descartado(s), fila_pico={st.profundidade_maxima}, "
            f"{self.writer.sink.arquivos_verificados} arquivo(s) verificado(s).",
            self.alertas,
        )
