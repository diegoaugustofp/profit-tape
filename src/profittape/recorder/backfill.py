"""
Backfill do historico de trades.

O QUE DA E O QUE NAO DA PARA PEDIR
----------------------------------
Trades: sim, via GetHistoryTrades. Book: nao — e' realtime puro, e nenhum
backfill traz o livro de ontem de volta.

LICOES DOS PRIMEIROS RUNS REAIS (2026-08-21)
--------------------------------------------
1. `conectado` no market data NAO significa historico pronto: houve recusa
   NL base+46 dois milissegundos depois do estado conectar. Por isso existe
   `settle_s` (respiro pos-conexao) e retry com intervalo.
2. O mesmo base+46 apareceu para TODOS os tickers apos queda de conexao.
   Um codigo, duas situacoes, uma leitura: "servidor de historico
   indisponivel". E' hipotese empirica, nao manual — mas retry e' a resposta
   certa para ela nos dois casos.
3. Uma chamada da DLL pode BLOQUEAR por muitos minutos se a conexao cair no
   meio (observado: 21 min). Nao ha como impor timeout a uma chamada ctypes
   bloqueante sem corromper o estado da DLL. O que se pode fazer — e este
   modulo faz — e' logar ANTES da chamada, para o travamento ter nome, e
   registrar toda mudanca de estado de conexao no meio do caminho.

COMO SABER QUE ACABOU
---------------------
A DLL nao emite "fim do historico" confiavel entre versoes. O criterio e'
quiesce: sem evento novo por `quiesce_s` segundos apos o primeiro lote,
consideramos completo. Conservador e a prova de versao.
"""

from __future__ import annotations

import time
from datetime import datetime

import structlog

from ..config import Credenciais, RecorderConfig
from ..health.metrics import Metrics
from ..pipeline.bus import EventBus
from ..pipeline.writer import WriterThread
from ..profitdll.client import ProfitClient
from ..profitdll.errors import SubscriptionFailed
from ..storage.parquet_sink import ParquetSink

log = structlog.get_logger(__name__)


def _iso_para_dll(iso: str) -> str:
    """'2026-08-20' -> '20/08/2026'. Falha cedo e com mensagem clara."""
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError as exc:
        raise ValueError(f"Data deve ser YYYY-MM-DD, veio {iso!r}") from exc


def executar(
    cfg: RecorderConfig,
    cred: Credenciais,
    inicio_iso: str,
    fim_iso: str,
    quiesce_s: float = 15.0,
    timeout_s: float = 3600.0,
    settle_s: float = 5.0,
    tentativas: int = 3,
    intervalo_retry_s: float = 15.0,
    dll_injetada: object | None = None,
) -> int:
    inicio = _iso_para_dll(inicio_iso)
    fim = _iso_para_dll(fim_iso)

    metrics = Metrics()
    bus = EventBus(maxsize=cfg.pipeline.fila_maxsize)
    sink = ParquetSink(
        raiz=cfg.storage.raiz,
        max_rows_per_file=cfg.storage.max_rows_per_file,
        compressao=cfg.storage.compressao,
        nivel_compressao=cfg.storage.nivel_compressao,
    )
    writer = WriterThread(
        bus=bus, sink=sink, metrics=metrics,
        batch_max=cfg.pipeline.batch_max,
        poll_timeout=cfg.pipeline.poll_timeout_s,
    )

    def _log_estado(tipo: int, valor: int) -> None:
        # A queda de conexao no meio do backfill foi invisivel no primeiro
        # incidente real. Nunca mais: todo estado vira linha de log.
        log.info("backfill.estado_conexao", tipo=tipo, valor=valor)

    client = ProfitClient(
        dll_path=cred.dll_path, activation_key=cred.activation_key,
        user=cred.user, password=cred.password, bus=bus,
        tz_offset_horas=cfg.runtime.tz_offset_horas,
        on_state=_log_estado, dll=dll_injetada,
    )

    writer.start()
    aceitos: list[str] = []
    recusas: dict[str, str] = {}
    try:
        client.connect()
        if settle_s > 0:
            # Market data conectado != historico pronto (visto em producao:
            # recusa 2ms apos o connect). Um respiro barato evita um round
            # inteiro de retry.
            log.info("backfill.settle", segundos=settle_s)
            time.sleep(settle_s)

        pendentes = list(cfg.ativos)
        for rodada in range(1, tentativas + 1):
            if rodada > 1:
                log.info("backfill.retry", rodada=rodada,
                         pendentes=[a.ticker for a in pendentes],
                         aguardando_s=intervalo_retry_s)
                time.sleep(intervalo_retry_s)
                if not client.conectado_market:
                    log.warning("backfill.sem_conexao_no_retry",
                                acao="aguardando reconectar")
                    limite = time.monotonic() + intervalo_retry_s
                    while time.monotonic() < limite and not client.conectado_market:
                        time.sleep(0.5)

            falharam: list = []
            for a in pendentes:
                # Log ANTES da chamada: se a DLL bloquear (observado: 21 min
                # apos queda de conexao), esta e' a linha que diz ONDE.
                log.info("backfill.solicitando", ticker=a.ticker,
                         inicio=inicio, fim=fim, rodada=rodada)
                try:
                    client.request_history(a.ticker, inicio, fim, a.bolsa)
                except SubscriptionFailed as exc:
                    recusas[a.ticker] = str(exc)
                    log.error("backfill.recusado", ticker=a.ticker,
                              rodada=rodada, detalhe=str(exc))
                    falharam.append(a)
                    continue
                aceitos.append(a.ticker)
                recusas.pop(a.ticker, None)
                log.info("backfill.aceito", ticker=a.ticker)
            pendentes = falharam
            if not pendentes:
                break

        if not aceitos:
            log.error(
                "backfill.todos_recusados",
                dica="mesmo codigo em todos os tickers tem padrao de servidor "
                     "de historico indisponivel — verifique a conexao e re-rode; "
                     "se persistir em horario comercial, o offset NL no manual "
                     "e' a pista decisiva",
            )
            return 2

        # Quiesce: espera o total parar de crescer. Mesma logica do download
        # assincrono do MT5 — a primeira resposta e' sempre parcial, e quem le
        # cedo demais subestima o que existe.
        t0 = time.monotonic()
        anterior = -1
        estavel_desde = time.monotonic()
        proximo_progresso = time.monotonic() + 15.0
        ancora_wall, ancora_mono = time.time(), time.monotonic()
        while time.monotonic() - t0 < timeout_s:
            time.sleep(1.0)
            # Suspensao da maquina distorce todo criterio baseado em relogio
            # (incidente real: timeout de 1h disparou 3h41 depois, sem nenhum
            # log no intervalo). Drift entre parede e monotonic denuncia.
            drift = (time.time() - ancora_wall) - (time.monotonic() - ancora_mono)
            if abs(drift) > 120:
                log.warning(
                    "backfill.suspensao_detectada",
                    drift_s=int(drift),
                    aviso="a maquina aparentemente dormiu; quiesce/timeout ficam "
                          "sem sentido neste run — confira o total contra um run "
                          "limpo e desative a suspensao para capturas",
                )
                ancora_wall, ancora_mono = time.time(), time.monotonic()
            atual = bus.stats().total_recebido
            if atual != anterior:
                anterior = atual
                estavel_desde = time.monotonic()
            elif atual > 0 and time.monotonic() - estavel_desde >= quiesce_s:
                log.info("backfill.quiesce", eventos=atual)
                break
            # Progresso periodico: download longo sem log parece travamento,
            # e a pessoa mata um processo saudavel. Licao de producao.
            if time.monotonic() >= proximo_progresso:
                proximo_progresso = time.monotonic() + 15.0
                decorrido = time.monotonic() - t0
                log.info(
                    "backfill.progresso",
                    eventos=atual,
                    eventos_por_s=int(atual / decorrido) if decorrido else 0,
                    decorrido_min=round(decorrido / 60, 1),
                    fila=bus.stats().profundidade_atual,
                )
        else:
            ainda_fluindo = time.monotonic() - estavel_desde < quiesce_s
            if ainda_fluindo:
                log.error(
                    "backfill.timeout_com_dado_fluindo",
                    eventos=anterior,
                    aviso="o corte foi ARBITRARIO: o servidor ainda entregava. "
                          "O que esta em disco e' parcial no meio de um dia — "
                          "re-rode com --timeout maior antes de usar este intervalo.",
                )
            else:
                log.warning("backfill.timeout", eventos=anterior,
                            aviso="pode estar incompleto — aumente --timeout")

        if anterior <= 0:
            log.error(
                "backfill.aceito_mas_vazio",
                aviso="o servidor aceitou o pedido e nao entregou nada — "
                      "intervalo sem pregao, ou conta sem historico provisionado",
            )
    except Exception:
        log.exception("backfill.erro")
        return 1
    finally:
        client.disconnect()
        bus.close()
        writer.join(timeout=300)

    st = bus.stats()
    log.info(
        "backfill.resumo",
        aceitos=sorted(set(aceitos)), recusados=sorted(recusas),
        eventos=st.total_recebido, descartados=st.total_descartado,
        raiz=str(cfg.storage.raiz),
        proximo_passo="profit-tape inspect para ver a profundidade REAL entregue, "
                      "e profit-tape curate antes de calcular qualquer feature",
    )
    return 0 if st.total_recebido > 0 else 2
