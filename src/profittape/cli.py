"""Interface de linha de comando."""

from __future__ import annotations

from pathlib import Path

import typer

from . import __version__
from .config import Credenciais, RecorderConfig
from .logging_setup import configurar

app = typer.Typer(add_completion=False, help="Gravador de tape e book da B3 (ProfitDLL).")


@app.command()
def record(
    config: Path = typer.Option(Path("config/recorder.yaml"), "--config", "-c"),
    log_level: str = typer.Option("INFO", "--log-level"),
    log_file: Path | None = typer.Option(None, "--log-file"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Valida config e sai."),
) -> None:
    """Grava tape e book ate o horario configurado ou ate Ctrl+C."""
    configurar(log_level, log_file)
    cfg = RecorderConfig.from_yaml(config)
    cred = Credenciais()

    if dry_run:
        typer.echo(f"Config valida: {len(cfg.ativos)} ativos, raiz={cfg.storage.raiz}")
        for a in cfg.ativos:
            flags = [n for n, v in
                     (("trades", a.trades), ("offer", a.offer_book), ("price", a.price_book)) if v]
            typer.echo(f"  {a.ticker:<10} {a.bolsa}  {'+'.join(flags)}")
        raise typer.Exit(0)

    cred.validar()
    from .recorder.service import RecorderService

    raise typer.Exit(RecorderService(cfg, cred).run())


@app.command()
def doctor(
    config: Path = typer.Option(Path("config/recorder.yaml"), "--config", "-c"),
) -> None:
    """
    Diagnostico antes de gravar: DLL carrega, exports batem, credencial existe,
    disco tem espaco. Rode isso ANTES de contar com uma gravacao de pregao.
    """
    configurar("INFO")
    import shutil
    import sys

    ok = True
    typer.echo(f"profit-tape {__version__}")
    typer.echo(f"Python      {sys.version.split()[0]} ({64 if sys.maxsize > 2**32 else 32} bits)")
    typer.echo(f"Plataforma  {sys.platform}")

    cred = Credenciais()
    for campo in ("activation_key", "user", "password"):
        preenchido = bool(getattr(cred, campo))
        typer.echo(f"  credencial {campo:<16} {'ok' if preenchido else 'AUSENTE'}")
        ok &= preenchido

    typer.echo(f"  dll_path    {cred.dll_path}")
    if sys.platform == "win32":
        from .profitdll.bindings import check_exports, load_dll

        try:
            dll = load_dll(cred.dll_path)
            ausentes = check_exports(dll)
            if ausentes:
                typer.echo(f"  EXPORTS AUSENTES: {ausentes}")
                typer.echo("  -> ajuste src/profittape/profitdll/bindings.py")
                ok = False
            else:
                typer.echo("  exports      ok")
            if hasattr(dll, "SetOfferBookCallbackV2"):
                typer.echo("  offer book   V2 disponivel (order-by-order)")
            else:
                typer.echo("  offer book   SEM SetOfferBookCallbackV2 — o offer book")
                typer.echo("               pode nao entregar NADA nesta versao (visto em")
                typer.echo("               producao). Estrategias de fila ficam bloqueadas.")
        except Exception as exc:
            typer.echo(f"  DLL          FALHOU: {exc}")
            ok = False
    else:
        typer.echo("  DLL          pulado (nao-Windows)")

    if config.exists():
        cfg = RecorderConfig.from_yaml(config)
        raiz = Path(cfg.storage.raiz)
        raiz.mkdir(parents=True, exist_ok=True)
        livre_gb = shutil.disk_usage(raiz).free / 1e9
        typer.echo(f"  config       ok ({len(cfg.ativos)} ativos)")
        typer.echo(f"  disco livre  {livre_gb:.1f} GB em {raiz.resolve()}")
        n_book = len(cfg.tickers_book)
        if n_book and livre_gb < 20:
            typer.echo("  AVISO: offer_book em varios ativos consome dezenas de GB por mes.")
    else:
        typer.echo(f"  config       AUSENTE em {config}")
        ok = False

    typer.echo("\nPRONTO PARA GRAVAR" if ok else "\nPENDENCIAS ACIMA")
    raise typer.Exit(0 if ok else 1)


@app.command()
def inspect(
    caminho: Path = typer.Argument(..., help="Diretorio ou arquivo Parquet."),
    stream: str = typer.Option("trade", "--stream"),
) -> None:
    """Resumo do que foi gravado: contagem, cobertura temporal, tipos de negocio."""
    from .tools.inspect import resumir

    resumir(caminho, stream)


@app.command()
def duplicatas(
    caminho: Path = typer.Argument(..., help="Raiz dos dados (ex.: G:\\data\\raw)."),
    symbol: str = typer.Argument(..., help="Ativo a diagnosticar (ex.: WINFUT)."),
    dia: str | None = typer.Option(None, "--dia", help="Restringe a um dt=YYYY-MM-DD."),
    amostras: int = typer.Option(10, "--amostras", help="Quantos pares mostrar lado a lado."),
) -> None:
    """
    Diagnostica trade_id repetido: edicao de negocio (campos diferem) x
    reentrega benigna (campos identicos). Decide se e' preciso o callback V2.
    """
    from .tools.duplicatas import diagnosticar

    diagnosticar(caminho, symbol.upper(), dia, amostras)


@app.command()
def backfill(
    inicio: str = typer.Option(..., "--inicio", help="YYYY-MM-DD"),
    fim: str = typer.Option(..., "--fim",
                            help="YYYY-MM-DD. EXCLUSIVO (observado em producao): "
                                 "para incluir o dia X, informe X+1."),
    config: Path = typer.Option(Path("config/recorder.yaml"), "--config", "-c"),
    quiesce: float = typer.Option(15.0, "--quiesce", help="Segundos sem evento novo = fim."),
    timeout: float = typer.Option(3600.0, "--timeout"),
    settle: float = typer.Option(5.0, "--settle",
                                 help="Respiro apos conectar; historico pode nao estar pronto."),
    tentativas: int = typer.Option(3, "--tentativas"),
    intervalo: float = typer.Option(15.0, "--intervalo", help="Segundos entre tentativas."),
    ticker: list[str] = typer.Option(
        [], "--ticker",
        help="Sobrepoe os ativos do config. Formato TICKER ou TICKER:BOLSA. Repetivel.",
    ),
    por_dia: bool = typer.Option(
        False, "--por-dia",
        help="Um request por pregao, RETOMAVEL (pula dt= ja capturados). "
             "Use para intervalos longos; aqui --fim e' INCLUSIVO.",
    ),
    timeout_dia: float = typer.Option(900.0, "--timeout-dia",
                                      help="Timeout por pregao no modo --por-dia."),
    tentativas_vazio: int = typer.Option(
        3, "--tentativas-vazio",
        help="Modo --por-dia: quantas vezes repetir um dia que voltou vazio "
             "estando DENTRO da janela de 30 dias (servidor ocupado do dia "
             "anterior devolve vazio; repetir costuma resolver).",
    ),
    pausa_retry_vazio: float = typer.Option(
        20.0, "--pausa-retry-vazio",
        help="Segundos de pausa entre tentativas de um dia vazio.",
    ),
    log_level: str = typer.Option("INFO", "--log-level"),
    log_file: Path | None = typer.Option(
        None, "--log-file",
        help="Grava o log em arquivo alem do console — permite acompanhar com "
             "Get-Content -Wait sem tocar na janela do processo (QuickEdit "
             "pausa processo que escreve no console selecionado).",
    ),
) -> None:
    """
    Puxa o historico de TRADES dos ativos do config. Book nao tem historico.

    Funciona fora do pregao se o servidor da corretora responder — vale tentar;
    se recusar, rode em horario comercial. A profundidade entregue e' empirica:
    confira com `inspect` depois.
    """
    configurar(log_level, log_file)
    cfg = RecorderConfig.from_yaml(config)
    if ticker:
        from .config import AtivoConfig

        novos = []
        for t in ticker:
            nome, _, bolsa = t.partition(":")
            novos.append(AtivoConfig(ticker=nome.upper(), bolsa=bolsa.upper() or "B"))
        cfg = cfg.model_copy(update={"ativos": novos})
    cred = Credenciais()
    cred.validar()
    if por_dia:
        from .recorder.backfill import executar_por_dia

        raise typer.Exit(executar_por_dia(cfg, cred, inicio, fim,
                                          quiesce_s=quiesce, timeout_dia_s=timeout_dia,
                                          settle_s=settle,
                                          tentativas_vazio=tentativas_vazio,
                                          pausa_retry_vazio=pausa_retry_vazio))
    from .recorder.backfill import executar

    raise typer.Exit(executar(cfg, cred, inicio, fim, quiesce_s=quiesce, timeout_s=timeout,
                              settle_s=settle, tentativas=tentativas,
                              intervalo_retry_s=intervalo))


@app.command()
def quarentena(
    raiz: Path = typer.Argument(..., help="Raiz dos dados (ex.: G:\\data\\raw)."),
    remover: bool = typer.Option(
        False, "--remover",
        help="Apaga os arquivos sem footer. Sem esta flag, apenas LISTA (dry-run).",
    ),
    profundo: bool = typer.Option(
        False, "--profundo",
        help="Tambem descomprime cada arquivo para pegar corrupcao INTERNA "
             "(ZSTD failed) que o footer intacto esconde. Mais lento, mas pega "
             "o que derruba o curate.",
    ),
    log_level: str = typer.Option("INFO", "--log-level"),
    log_file: Path | None = typer.Option(
        None, "--log-file",
        help="Grava o log em arquivo alem do console — util pra acompanhar "
             "com Get-Content -Wait numa varredura longa (--profundo em "
             "milhares de arquivos pode levar horas).",
    ),
) -> None:
    """
    Acha (e opcionalmente remove) arquivos .parquet corrompidos — fosseis sem
    footer da era do fsync quebrado, ou (com --profundo) row groups internamente
    corrompidos que passam pelo footer. Dry-run por padrao: nunca apaga sem
    --remover.

    Loga progresso a cada 5s/100 arquivos (quarentena.progresso) — sem isso,
    --profundo em milhares de arquivos fica em silencio por horas,
    indistinguivel de travado.
    """
    configurar(log_level, log_file)
    from .tools.quarentena import varrer

    varrer(raiz, remover, profundo)


@app.command()
def curate(
    raw: Path = typer.Option(Path("data/raw"), "--raw"),
    curated: Path = typer.Option(Path("data/curated"), "--curated"),
    log_level: str = typer.Option("INFO", "--log-level"),
    log_file: Path | None = typer.Option(
        None, "--log-file",
        help="Grava o log em arquivo alem do console — util pra acompanhar "
             "com Get-Content -Wait numa curadoria longa (muitos dias/simbolos).",
    ),
) -> None:
    """
    Deduplica e ordena raw -> curated. Rode SEMPRE antes de calcular features.

    Idempotente: reprocessar sobrescreve a mesma saida. Loga progresso por dia
    (curate.processando / curate.dia_ok) — uma curadoria de 20+ dias fica
    muda por minutos sem isso, indistinguivel de travada.
    """
    configurar(log_level, log_file)
    from .tools.curate import curar_trades, imprimir_relatorio

    imprimir_relatorio(curar_trades(raw, curated))


@app.command()
def features(
    symbol: str = typer.Argument(
        ..., help="Ex.: WINFUT — ou lista separada por virgula (WINFUT,WDOFUT,"
                   "PETR4) ou 'todos' para processar cada sym= presente no "
                   "curated. QoL para nao repetir o comando 9x manualmente."),
    curated: Path = typer.Option(Path("data/curated"), "--curated"),
    saida: Path = typer.Option(Path("data/features"), "--saida"),
    volume_barra: int | None = typer.Option(None, "--volume-barra",
                                            help="Fixo; omita para sugerir pela mediana."),
    barras_por_dia: int = typer.Option(100, "--barras-por-dia"),
    top_agentes: int = typer.Option(10, "--top-agentes"),
    janela_z: int = typer.Option(50, "--janela-z"),
    label_k: float = typer.Option(2.0, "--label-k"),
    label_h: int = typer.Option(10, "--label-h"),
    perfis: Path | None = typer.Option(
        Path("data/ref/agentes.csv"), "--perfis",
        help="CSV classificado (agents); adiciona fluxo_nacional se existir "
             "e tiver algum agente rotulado NACIONAL. Passe vazio para omitir.",
    ),
) -> None:
    """
    Gera barras de volume (relogio de agressao) com features de fluxo Tier 1,
    z-scores anti-lookahead e labels triple-barrier. Uma linha por barra.
    """
    configurar("WARNING")
    from .features.pipeline import gerar

    if symbol.strip().lower() == "todos":
        simbolos = sorted({
            p.name.split("=", 1)[1]
            for p in (curated / "trade").glob("dt=*/sym=*")
        })
        if not simbolos:
            raise SystemExit(f"nenhum symbol encontrado em {curated / 'trade'}")
    else:
        simbolos = [s.strip().upper() for s in symbol.split(",") if s.strip()]

    falhas = []
    for i, sym in enumerate(simbolos, 1):
        typer.echo(f"\n[{i}/{len(simbolos)}] {sym}")
        try:
            r = gerar(curated, saida, sym, volume_barra, barras_por_dia,
                      top_agentes, janela_z, label_k, label_h, perfis)
        except SystemExit as exc:
            # Simbolo com pouco dado (ex.: MGLU3 com 200 trades/dia nao
            # forma barra alguma) nao pode derrubar o lote inteiro — os
            # outros 8 simbolos continuam valendo a pena.
            typer.echo(f"  PULADO: {exc}")
            falhas.append(sym)
            continue
        typer.echo(f"  barras={r['barras']} volume_barra={r['volume_barra']} "
                   f"tick={r['tick_inferido']} arquivo={r['arquivo']}")
    if falhas:
        typer.echo(f"\n{len(falhas)} simbolo(s) pulado(s) (dado insuficiente): "
                   f"{falhas}")


@app.command()
def agents(
    dados: Path = typer.Option(
        Path("data/curated"), "--dados",
        help="Arvore Parquet de onde extrair os codigos de agente observados.",
    ),
    saida: Path = typer.Option(Path("data/ref/agentes.csv"), "--saida"),
) -> None:
    """
    Resolve codigos de corretora em nomes via GetAgentNameById e grava um CSV
    de referencia (agent_id, nome) para join nas analises de fluxo.

    Conecta na DLL; funciona fora do pregao. Codigo sem nome vira linha com
    nome vazio — ainda util para o join nao perder linhas.
    """
    configurar("INFO")
    import csv

    import pyarrow.compute as pc
    import pyarrow.dataset as ds

    from .pipeline.bus import EventBus
    from .profitdll.client import ProfitClient

    origem = dados / "trade" if (dados / "trade").exists() else dados
    tabela = ds.dataset(origem, format="parquet", partitioning="hive",
                        exclude_invalid_files=True).to_table()
    ids = sorted(
        set(pc.unique(tabela["agente_comprador"]).to_pylist())
        | set(pc.unique(tabela["agente_vendedor"]).to_pylist())
    )
    typer.echo(f"{len(ids)} codigos de agente observados em {origem}")

    cred = Credenciais()
    cred.validar()
    client = ProfitClient(
        dll_path=cred.dll_path, activation_key=cred.activation_key,
        user=cred.user, password=cred.password, bus=EventBus(maxsize=16),
    )
    client.connect()
    try:
        linhas = [
            (i, client.agent_name(i, curto=True) or "",
             client.agent_name(i) or "")
            for i in ids
        ]
    finally:
        client.disconnect()

    saida.parent.mkdir(parents=True, exist_ok=True)
    with saida.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        # Coluna 'perfil' vem VAZIA de proposito: e' curadoria manual do
        # operador (nacional/estrangeiro, varejo/institucional, ou o que a
        # pesquisa decidir), congelada ANTES do IC para nao virar p-hacking.
        w.writerow(["agent_id", "short_name", "nome", "perfil"])
        w.writerows((i, curto, longo, "") for i, curto, longo in linhas)

    sem_nome = sum(1 for _, curto, longo in linhas if not curto and not longo)
    typer.echo(f"gravado: {saida}  ({len(linhas)} agentes, {sem_nome} sem nome)")
    typer.echo("  coluna 'perfil' vazia — preencha manualmente antes do research")
    for i, curto, longo in linhas[:10]:
        typer.echo(f"  {i:>6}  {curto or '(sem short)':<12} {longo}")


@app.command()
def research(
    features: Path = typer.Option(Path("data/features"), "--features"),
    symbol: str = typer.Option("WINFUT", "--symbol"),
    saida: Path = typer.Option(Path("data/research"), "--saida"),
    treino_min: int = typer.Option(3, "--treino-min", help="Dias minimos de treino."),
    teste_dias: int = typer.Option(2, "--teste-dias", help="Dias por bloco de teste."),
) -> None:
    """
    IC walk-forward das features com veredito deflacionado por trials
    acumulados. Metodo pre-registrado em docs/RESEARCH_PLANO.md.
    """
    from .research.pipeline import rodar

    arquivo = features / f"sym={symbol.upper()}" / "features.parquet"
    if not arquivo.exists():
        raise SystemExit(f"nao achei {arquivo} — rode `profit-tape features` antes")
    r = rodar(arquivo, saida, treino_min=treino_min, teste_dias=teste_dias)
    typer.echo("=" * 62)
    typer.echo("RESEARCH — IC walk-forward")
    typer.echo("=" * 62)
    for k in ("dias", "folds", "features", "trials_rodada", "trials_acumulados",
              "limiar_deflacionado", "segue", "descarta", "inconclusivo"):
        typer.echo(f"  {k:20}: {r[k]}")
    typer.echo(f"  relatorio           : {r['relatorio']}")


@app.command()
def perfil_validar(
    curated: Path = typer.Option(Path("data/curated"), "--curated"),
    symbol: str = typer.Option("WINFUT", "--symbol"),
    agentes_csv: Path = typer.Option(Path("data/ref/agentes.csv"), "--agentes"),
    referencia: Path = typer.Option(
        Path("data/ref/fluxo_participantes_b3_oficial.csv"), "--referencia"),
) -> None:
    """
    Valida a classificacao de corretoras contra a serie oficial da B3 —
    ANTES de gastar trials de IC em features de perfil (pre-registrado).
    """
    from .research.perfil import carregar_perfis, fluxo_diario_por_perfil, validar

    perfis = carregar_perfis(agentes_csv)
    classificados = sum(1 for v in perfis.values() if v)
    typer.echo(f"{len(perfis)} agentes no CSV, {classificados} classificados")
    fluxo = fluxo_diario_por_perfil(curated, symbol.upper(), perfis)
    r = validar(fluxo, referencia)
    typer.echo("=" * 62)
    typer.echo(f"VALIDACAO DE PERFIL x SERIE OFICIAL ({r['dias_em_comum']} dias)")
    typer.echo("=" * 62)
    typer.echo(r["tabela"].to_string(index=False,
               float_format=lambda v: f"{v:.3f}"))
    typer.echo("-" * 62)
    typer.echo("Ressalva pre-registrada: oficial = mercado a vista; nosso = WIN.")
    typer.echo("Proxy contra proxy — pearson >= 0.4 valida a DIRECAO.")


@app.command()
def quintis(
    pares: str = typer.Argument(
        ..., help='Pares "feature:h" separados por virgula, ex.: '
                   '"z_agf_3:3,z_agf_4090:1" (os vereditos \'segue\' do research).'),
    custo_pontos: float = typer.Option(
        5.0, "--custo-pontos",
        help="Custo de ida-e-volta em PONTOS de indice (spread+corretagem+"
             "slippage). AJUSTE para o custo real do seu book — o default "
             "e' um placeholder, nao uma estimativa real."),
    features: Path = typer.Option(Path("data/features"), "--features"),
    symbol: str = typer.Option("WINFUT", "--symbol"),
    saida: Path = typer.Option(Path("data/research"), "--saida"),
    treino_min: int = typer.Option(3, "--treino-min"),
    teste_dias: int = typer.Option(2, "--teste-dias"),
) -> None:
    """
    Tabela de quintis: traducao economica dos vereditos 'segue' do IC — sinal
    estatisticamente real pode ser economicamente morto pelo custo de
    transacao. NAO gasta trial (leitura sobre feature ja' avaliada).
    """
    from .research.quintis import avaliar_pares

    lista = []
    for item in pares.split(","):
        feat, h = item.strip().split(":")
        lista.append((feat.strip(), int(h)))

    arquivo = features / f"sym={symbol.upper()}" / "features.parquet"
    if not arquivo.exists():
        raise SystemExit(f"nao achei {arquivo} — rode `profit-tape features` antes")
    r = avaliar_pares(arquivo, lista, saida, custo_pontos,
                      treino_min=treino_min, teste_dias=teste_dias)
    from .research.quintis import _fmt
    typer.echo("=" * 62)
    typer.echo(f"QUINTIS — custo assumido {_fmt(custo_pontos)} pts, "
               f"{r['dias_out_of_sample']} dias out-of-sample")
    typer.echo("=" * 62)
    for (feat, h), tabela in r["tabelas"].items():
        typer.echo(f"\n{feat} @ h={h}")
        typer.echo(tabela.to_string(index=False, float_format=lambda v: _fmt(v)))
        for teste in r["diferencas"].get((feat, h), []):
            marca = "DIFEREM" if teste["diferem_5pct"] else "indistinguivel"
            typer.echo(
                f"  Q{teste['quintil_a']} vs Q{teste['quintil_b']}: "
                f"diff={_fmt(teste['diferenca'])}pts t={teste['t_welch']:.2f} "
                f"p={teste['p_valor']:.3f} [{marca}]"
            )
    typer.echo(f"\nrelatorio: {r['relatorio']}")


@app.command()
def alertas_testar(
    alertas: Path = typer.Option(Path("config/alertas.yaml"), "--alertas"),
) -> None:
    """
    Manda uma mensagem de teste ao Telegram configurado — confirma
    bot_token/chat_id ANTES de depender disso durante o pregao.
    """
    from .alertas import ConfigAlertas, enviar

    cfg = ConfigAlertas.carregar(alertas)
    if cfg is None:
        typer.echo(f"SEM CONFIG: {alertas} nao existe ou esta incompleto "
                   f"(precisa de telegram.bot_token e telegram.chat_id).")
        raise typer.Exit(1)

    ok = enviar("🧪 teste do profit-tape — se voce recebeu isso, "
               "bot_token e chat_id estao corretos.", cfg)
    if ok:
        typer.echo("Enviado. Confira o Telegram.")
    else:
        typer.echo("FALHOU ao enviar — o motivo apareceu na linha acima "
                   "(alertas.envio_falhou). Confira bot_token, chat_id, e se "
                   "a rede alcanca api.telegram.org.")
        raise typer.Exit(1)


@app.command()
def vigia(
    log_file: Path = typer.Option(Path("logs/record_diario.jsonl"), "--log-file"),
    alertas: Path = typer.Option(Path("config/alertas.yaml"), "--alertas"),
    estado: Path = typer.Option(Path("logs/vigia_estado.json"), "--estado"),
    abertura: str = typer.Option(
        "09:05", "--abertura",
        help="Apos este horario local, exige que o record ja tenha iniciado."),
    fechamento: str = typer.Option(
        "18:35", "--fechamento",
        help="Apos este horario, o vigia nao verifica mais (pregao encerrado)."),
    limite_parado_min: float = typer.Option(6.0, "--limite-parado-min"),
) -> None:
    """
    Watchdog EXTERNO ao record — roda via schtasks proprio a cada poucos
    minutos. Cobre o que o record nao pode alertar sobre si mesmo: nunca ter
    iniciado, ou ter travado sem chegar a emitir o alerta de erro.
    """
    from .vigia import checar

    veredito = checar(log_file, alertas, estado, abertura, fechamento, limite_parado_min)
    typer.echo(f"vigia: {veredito}")


@app.command()
def ea(
    config: Path = typer.Option(Path("config/ea.yaml"), "-c", "--config"),
    encerrar_em: str = typer.Option(
        "17:30", "--encerrar-em",
        help="HH:MM local para zerar e parar. Default 17:30: folga de "
             "seguranca sobre a zeragem automatica da XP, que ocorre 15min "
             "antes do fechamento do BMF (18:00, ou 17:45 em dia de "
             "vencimento de serie) -- ver docs/EA_ARQUITETURA.md."),
    bolsa: str = typer.Option("F", "--bolsa"),
    heartbeat_s: int = typer.Option(30, "--heartbeat-s"),
    log_file: Path | None = typer.Option(None, "--log-file"),
    log_level: str = typer.Option("INFO", "--log-level"),
) -> None:
    """
    FORWARD-TEST do EA (dry_run por default no config): conecta com login
    completo, assina o simbolo, constroi barras ao vivo e LOGA cada decisao
    que o EA teria tomado. NENHUMA ordem e' enviada enquanto dry_run=True
    no yaml -- e dry_run=False continua bloqueado por design ate' gestao
    de risco existir (ver docs/EA_ARQUITETURA.md).

    Encerra sozinho em --encerrar-em (default 18:20, ANTES do fechamento
    do pregao -- o EA nunca carrega posicao overnight por design).
    """
    configurar(log_level, log_file)
    from .config import Credenciais
    from .ea.config import EAConfig
    from .ea.service import EAService

    if not config.exists():
        raise SystemExit(f"nao achei {config} -- crie a partir de "
                         f"config/ea.exemplo.yaml")
    ea_cfg = EAConfig.from_yaml(config)
    if not ea_cfg.dry_run:
        raise SystemExit(
            "dry_run=False no yaml, mas o comando `ea` do CLI so' roda "
            "forward-test por enquanto -- gestao de risco ainda nao existe "
            "(pre-requisito 5 em docs/EA_ARQUITETURA.md). Deliberado."
        )

    cred = Credenciais()
    cred.validar()

    typer.echo(f"EA forward-test: {ea_cfg.symbol} dry_run={ea_cfg.dry_run} "
               f"sinais={[s.feature for s in ea_cfg.sinais]}")
    svc = EAService(ea_cfg)
    svc.rodar(cred, bolsa=bolsa, encerrar_em=encerrar_em,
              heartbeat_s=heartbeat_s)


@app.command()
def ea_contas(
    timeout: float = typer.Option(15.0, "--timeout"),
    log_level: str = typer.Option("INFO", "--log-level"),
) -> None:
    """
    DIAGNOSTICO (nao operacional): conecta com login completo e lista as
    contas de roteamento (GetAccount) -- demo e real. Use o resultado para
    preencher ROTEAMENTO_ID_ACCOUNT_DEMO/REAL no .env.

    READ-ONLY: nao envia ordem, nao modifica nada. Rode de preferencia FORA
    do horario de pregao, com o record PARADO -- ver docs/EA_ARQUITETURA.md.
    """
    configurar(log_level)
    from .config import Credenciais
    from .ea.contas import listar_contas

    cred = Credenciais()
    cred.validar()

    typer.echo("Conectando (login completo)...")
    contas = listar_contas(cred, timeout_s=timeout)

    if not contas:
        typer.echo("Nenhuma conta retornada. Confira se GetAccount() e' "
                   "suportado nesta versao da DLL, ou aumente --timeout.")
        raise typer.Exit(1)

    typer.echo(f"\n{len(contas)} conta(s) encontrada(s):")
    typer.echo("-" * 70)
    for c in contas:
        typer.echo(f"  corretora_id={c.corretora_id:<6} corretora={c.corretora_nome}")
        typer.echo(f"  account_id={c.account_id!r:<12} titular={c.titular}")
        typer.echo("-" * 70)

    if len(contas) == 1:
        typer.echo(
            "\nSo' uma conta -- normal se a chave de ativacao ainda so' "
            "tem permissao para o SIMULADOR (nao para a conta real). "
            "Preencha por enquanto so':"
        )
        typer.echo(f"  ROTEAMENTO_ID_ACCOUNT_DEMO={contas[0].account_id}")
        typer.echo(f"  ROTEAMENTO_ID_CORRETORA={contas[0].corretora_id}")
        typer.echo(
            "ROTEAMENTO_ID_ACCOUNT_REAL fica VAZIO ate' a XP habilitar a "
            "conta real para esta chave -- nunca invente um valor aqui."
        )
    else:
        typer.echo("\nAnote qual account_id e' DEMO e qual e' REAL, e preencha:")
        typer.echo("  ROTEAMENTO_ID_ACCOUNT_DEMO=<...>")
        typer.echo("  ROTEAMENTO_ID_ACCOUNT_REAL=<...>")
        typer.echo("  ROTEAMENTO_ID_CORRETORA=<corretora_id acima>")
    typer.echo("no seu .env (nunca no yaml versionado).")


@app.command()
def bench(
    ativos: int = typer.Option(5, "--ativos"),
    duracao: float = typer.Option(15.0, "--duracao", help="Segundos de simulacao."),
    intervalo: float = typer.Option(
        0.0004, "--intervalo",
        help="Pausa entre eventos por produtor. 0 satura o GIL e nao representa mercado.",
    ),
    raiz: Path | None = typer.Option(
        None, "--raiz",
        help="Volume onde MEDIR a escrita (ex.: G:\\bench). Sem isto, mede o "
             "temp do C: — que pode nao ser onde a captura grava.",
    ),
) -> None:
    """Mede a folga do pipeline NESTA maquina, com a DLL falsa."""
    configurar("WARNING")
    from .tools.bench import rodar

    rodar(eventos_por_ativo=10_000_000, n_ativos=ativos, duracao_s=duracao,
          intervalo_s=intervalo, raiz=raiz)


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    # Sem isto, `python -m profittape.cli ...` importa o modulo (define os
    # comandos) mas NUNCA invoca o app -- o processo simplesmente termina
    # em silencio, sem erro, sem saida, parecendo que "nao fez nada" (bug
    # real, 2026-08-25: o operador precisou do fallback `python -m
    # profittape` -- sem o '.cli' -- que ja funcionava via __main__.py).
    main()
