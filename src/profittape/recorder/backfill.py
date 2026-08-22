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

import signal
import time
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path

import structlog

from ..config import Credenciais, RecorderConfig
from ..health.metrics import Metrics
from ..pipeline.bus import EventBus, nivel_ocupacao
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


def _dias_uteis(inicio_iso: str, fim_iso: str) -> list[str]:
    """Dias uteis (seg-sex) no intervalo INCLUSIVO. Feriado da B3 nao e'
    conhecido aqui — dia sem entrega e' tratado como feriado no loop."""
    d = datetime.strptime(inicio_iso, "%Y-%m-%d").date()
    fim = datetime.strptime(fim_iso, "%Y-%m-%d").date()
    dias = []
    while d <= fim:
        if d.weekday() < 5:
            dias.append(d.isoformat())
        d += timedelta(days=1)
    return dias


def _dia_ja_capturado(raiz: Path, dia: str) -> bool:
    pasta = Path(raiz) / "trade" / f"dt={dia}"
    return pasta.exists() and any(pasta.rglob("*.parquet"))


def _aguardar_quiesce(bus, base: int, quiesce_s: float, timeout_s: float) -> tuple[int, bool]:
    """Espera o total (relativo a `base`) estabilizar. Devolve (eventos, completou)."""
    t0 = time.monotonic()
    anterior = -1
    estavel_desde = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        time.sleep(1.0)
        atual = bus.stats().total_recebido - base
        if atual != anterior:
            anterior = atual
            estavel_desde = time.monotonic()
        elif time.monotonic() - estavel_desde >= quiesce_s:
            return max(anterior, 0), True
    return max(anterior, 0), False


def executar_por_dia(
    cfg: RecorderConfig,
    cred: Credenciais,
    inicio_iso: str,
    fim_iso: str,
    quiesce_s: float = 10.0,
    timeout_dia_s: float = 900.0,
    settle_s: float = 5.0,
    tentativas_vazio: int = 3,
    pausa_retry_vazio: float = 20.0,
    dll_injetada: object | None = None,
) -> int:
    """
    Backfill longo, um pregao por request, RETOMAVEL.

    Por que existe: a unica entrega multi... o unico comportamento OBSERVADO
    do servidor foi [d, d+1) -> exatamente o dia d. Um request de 60 dias e'
    hipotese nao testada; 60 requests de 1 dia e' comportamento provado. E a
    retomada por particao significa que queda de conexao na madrugada custa
    re-rodar o comando, nao a noite.

    Dia sem entrega apos o quiesce e' registrado como provavel feriado e o
    loop segue — a B3 tem ~10 por ano e nao vale manter tabela.
    """
    dias = [d for d in _dias_uteis(inicio_iso, fim_iso)]
    pulados = [d for d in dias if _dia_ja_capturado(cfg.storage.raiz, d)]
    pendentes = [d for d in dias if d not in pulados]
    import shutil as _sh
    raiz_resolvida = Path(cfg.storage.raiz).resolve()
    try:
        livre_gb = _sh.disk_usage(raiz_resolvida.anchor or ".").free / 1e9
    except OSError:
        livre_gb = -1.0
    log.info("backfill_dia.destino", raiz=str(raiz_resolvida),
             livre_gb=round(livre_gb, 1))
    log.info("backfill_dia.plano", dias_uteis=len(dias),
             ja_capturados=len(pulados), pendentes=len(pendentes))

    # Confirmado no manual (NL_HISTORY_PERIOD_LIMIT, base+46): GetHistoryTrades
    # so' aceita 'data inicial' dentro dos ultimos 30 dias corridos a partir de
    # HOJE — nao dias uteis, corridos. Avisa de antemao em vez de deixar o
    # usuario descobrir olhando dezenas de recusas passarem no log.
    limite_30d = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    fora_da_janela = [d for d in pendentes if d < limite_30d]
    if fora_da_janela:
        log.warning(
            "backfill_dia.fora_da_janela_de_30_dias",
            dias_inatingiveis=len(fora_da_janela),
            mais_antigo=fora_da_janela[0], limite=limite_30d,
            aviso="GetHistoryTrades so' entrega 'data inicial' dentro dos "
                  "ultimos 30 dias corridos (limite documentado no manual, "
                  "nao restricao de conta). Esses dias serao tentados mas "
                  "vao recusar rapido (NL_HISTORY_PERIOD_LIMIT). Para "
                  "historico mais antigo, so' resta gravacao ao vivo diaria "
                  "acumulando — ver docs/OPERACAO.md.",
        )
    if not pendentes:
        log.info("backfill_dia.nada_a_fazer")
        return 0

    metrics = Metrics()
    bus = EventBus(maxsize=cfg.pipeline.fila_maxsize)
    sink = ParquetSink(
        raiz=cfg.storage.raiz, max_rows_per_file=cfg.storage.max_rows_per_file,
        compressao=cfg.storage.compressao, nivel_compressao=cfg.storage.nivel_compressao,
    )
    writer = WriterThread(bus=bus, sink=sink, metrics=metrics,
                          batch_max=cfg.pipeline.batch_max,
                          poll_timeout=cfg.pipeline.poll_timeout_s,
                          limiar_lote_lento_s=cfg.pipeline.limiar_lote_lento_s)
    client = ProfitClient(
        dll_path=cred.dll_path, activation_key=cred.activation_key,
        user=cred.user, password=cred.password, bus=bus,
        tz_offset_horas=cfg.runtime.tz_offset_horas,
        on_state=lambda t, v: log.info("backfill_dia.estado", tipo=t, valor=v),
        dll=dll_injetada,
    )

    writer.start()
    feriados: list[str] = []
    incompletos: list[str] = []
    capturados = 0
    interrompido = False
    dia_em_andamento: str | None = None
    try:
        client.connect()
        if settle_s > 0:
            time.sleep(settle_s)
        for idx, dia in enumerate(pendentes, 1):
            dia_em_andamento = dia
            d = datetime.strptime(dia, "%Y-%m-%d")
            ini = d.strftime("%d/%m/%Y")
            fim = (d + timedelta(days=1)).strftime("%d/%m/%Y")
            log.info("backfill_dia.solicitando", dia=dia, progresso=f"{idx}/{len(pendentes)}")

            # Padrao descoberto em producao (log de 2026-08-21): TODO dia
            # pedido logo apos um dia de milhoes de eventos voltava vazio com
            # timing exato de quiesce (16s) — nao era feriado (30/07, 05/08
            # sao uteis), era o servidor de historico ainda ocupado despejando
            # /resetando do dia anterior. A resposta e' esperar e repetir:
            # dentro da janela de 30 dias, um dia vazio e' quase sempre isso.
            eventos, ok, recusado = 0, False, False
            max_tentativas = tentativas_vazio if dia >= limite_30d else 1
            for tentativa in range(1, max_tentativas + 1):
                base = bus.stats().total_recebido
                recusas = 0
                for a in cfg.ativos:
                    try:
                        client.request_history(a.ticker, ini, fim, a.bolsa)
                    except SubscriptionFailed as exc:
                        recusas += 1
                        log.error("backfill_dia.recusado", dia=dia,
                                  ticker=a.ticker, detalhe=str(exc))
                if recusas == len(cfg.ativos):
                    recusado = True
                    break
                eventos, ok = _aguardar_quiesce(bus, base, quiesce_s, timeout_dia_s)
                if eventos > 0:
                    break
                if tentativa < max_tentativas:
                    log.info(
                        "backfill_dia.vazio_retry",
                        dia=dia, tentativa=f"{tentativa}/{max_tentativas}",
                        aguardando_s=pausa_retry_vazio,
                        nota="dia dentro da janela veio vazio; provavel servidor "
                             "ainda ocupado do dia anterior — aguardando e repetindo",
                    )
                    time.sleep(pausa_retry_vazio)

            if recusado:
                incompletos.append(dia)
                continue
            if eventos == 0:
                feriados.append(dia)
                nota = (
                    "provavel LIMITE DE 30 DIAS do GetHistoryTrades, nao feriado"
                    if dia < limite_30d else
                    # Fato: pedido ACEITO, zero eventos ate o quiesce. Nao
                    # chutamos a causa — incidente real: 'provavel feriado'
                    # em quarta e quinta uteis consecutivas era warmup do
                    # servidor de historico logo apos a conexao, nao feriado.
                    "aceito mas nada chegou — candidatos: feriado, warmup do "
                    "servidor pos-conexao, ou borda da janela de 30 dias"
                )
                log.info("backfill_dia.sem_entrega", dia=dia, nota=nota,
                         reacao="dia NAO e' marcado como capturado; o mesmo "
                                "comando re-tenta sozinho no proximo run")
            elif not ok:
                incompletos.append(dia)
                log.error("backfill_dia.timeout", dia=dia, eventos=eventos,
                          aviso="dia possivelmente parcial — sera re-pedido no "
                                "proximo run se a particao for removida")
            elif dia < limite_30d:
                # Silencio dentro da janela historicamente inatingivel:
                # mais provavel ser o teto de 30 dias que feriado. O evento
                # 'sem_entrega' abaixo ja registra isso; nao promover a
                # 'capturado' evita falso positivo de particao completa.
                pass
            else:
                capturados += 1
                log.info("backfill_dia.ok", dia=dia, eventos=eventos)
    except KeyboardInterrupt:
        # BaseException, nao Exception: sem este bloco, o resumo final nunca
        # imprimia apos Ctrl+C. E o incidente real teve uma SEGUNDA camada,
        # diagnosticada pelo proprio usuario: sem feedback imediato de que o
        # primeiro Ctrl+C registrou, a reacao natural e' apertar DE NOVO — e
        # o segundo interrompe o finally no meio, matando a drenagem da fila
        # e o fechamento dos arquivos. Por isso, duas medidas aqui:
        #   1. logar NA HORA que o encerramento comecou (feedback);
        #   2. ignorar SIGINT dali em diante (blindagem): depois que a
        #      limpeza inicia, um segundo Ctrl+C so' pode causar dano.
        interrompido = True
        with suppress(ValueError, OSError):   # fora da main thread / plataforma
            signal.signal(signal.SIGINT, signal.SIG_IGN)
        log.warning(
            "backfill_dia.ENCERRAMENTO_INICIADO",
            dia_em_andamento=dia_em_andamento,
            nota="Ctrl+C recebido. Drenando fila e fechando arquivos — pode "
                 "levar ate' alguns minutos com fila cheia. Ctrl+C adicional "
                 "sera IGNORADO de proposito: interromper o fechamento e' a "
                 "unica forma de perder dado nesta fase. Aguarde o resumo.",
        )
    except Exception:
        log.exception("backfill_dia.erro")
        return 1
    finally:
        log.info("backfill_dia.encerrando",
                 nota="desconectando DLL, drenando fila, fechando arquivos")
        client.disconnect()
        bus.close()
        writer.join(timeout=600)
        log.info("backfill_dia.arquivos_fechados")

    st = bus.stats()
    log.info("backfill_dia.resumo",
             capturados=capturados, ja_existiam=len(pulados),
             sem_entrega=feriados, incompletos=incompletos,
             eventos=st.total_recebido, descartados=st.total_descartado)
    if incompletos:
        log.error("backfill_dia.ATENCAO_incompletos", dias=incompletos,
                  acao="remova as particoes desses dias e re-rode para completar")
    if interrompido:
        restantes = len(pendentes) - capturados - len(feriados) - len(incompletos)
        log.warning(
            "backfill_dia.parcial",
            capturados_nesta_rodada=capturados, dia_interrompido=dia_em_andamento,
            estimativa_restante=max(restantes, 0),
            dica="rode o MESMO comando de novo — dias ja capturados sao "
                 "pulados automaticamente (retomavel por particao)",
        )
        return 130   # convencao POSIX para SIGINT
    return 0 if not incompletos else 3


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
        limiar_lote_lento_s=cfg.pipeline.limiar_lote_lento_s,
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
                fila_agora = bus.stats().profundidade_atual
                log.info(
                    "backfill.progresso",
                    eventos=atual,
                    eventos_por_s=int(atual / decorrido) if decorrido else 0,
                    decorrido_min=round(decorrido / 60, 1),
                    fila=fila_agora,
                )
                nivel = nivel_ocupacao(fila_agora, bus.maxsize)
                if nivel is not None:
                    log.warning("backfill.fila_ocupada",
                                nivel=nivel,
                                ocupacao=f"{fila_agora / bus.maxsize:.0%}",
                                causa_tipica="writer atras da chegada — "
                                             "tipicamente disco lento")
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
