"""Interface de linha de comando."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd

import structlog
import typer

from . import __version__
from .config import Credenciais, RecorderConfig
from .logging_setup import configurar

log = structlog.get_logger(__name__)
app = typer.Typer(add_completion=False, help="Gravador de tape e book da B3 (ProfitDLL).")


@app.command()
def record(
    config: Path = typer.Option(Path("config/recorder.yaml"), "--config", "-c"),
    log_level: str = typer.Option("INFO", "--log-level"),
    log_file: Path | None = typer.Option(None, "--log-file"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Valida config e sai."),
    ea_config: Path | None = typer.Option(
        None, "--ea-config",
        help="OPCIONAL (2026-08-27, decisao de arquitetura de longo "
             "prazo): roda o EA DENTRO deste processo, mesma conexao -- "
             "licenca Nelogica so' permite UMA chave de ativacao. Sempre "
             "dry_run=True nesta fase -- so' loga decisoes, nunca envia "
             "ordem. Sem este parametro, comportamento identico a sempre."),
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
        if ea_config:
            typer.echo(f"  EA integrado: --ea-config {ea_config}")
        raise typer.Exit(0)

    cred.validar()
    from .recorder.service import RecorderService

    raise typer.Exit(RecorderService(cfg, cred, ea_config_path=ea_config).run())


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
    desde: str | None = typer.Option(
        None, "--desde", help="YYYY-MM-DD -- so' valida dt= a partir desta "
        "data (inclusive). Sem isso, varre TODO o historico (comportamento "
        "de sempre) -- pedido real: revarrer tudo a cada backup incremental "
        "fica inviavel com semanas/meses acumulados."),
    ate: str | None = typer.Option(
        None, "--ate", help="YYYY-MM-DD -- so' valida dt= ate esta data "
        "(inclusive). Combina com --desde para um intervalo."),
    dia: str | None = typer.Option(
        None, "--dia", help="YYYY-MM-DD -- atalho para --desde X --ate X "
        "(valida so' um dia). Nao combina com --desde/--ate."),
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
    if dia and (desde or ate):
        raise SystemExit("--dia nao combina com --desde/--ate -- use um ou outro.")
    if dia:
        desde = ate = dia

    configurar(log_level, log_file)
    from .tools.quarentena import varrer

    varrer(raiz, remover, profundo, desde=desde, ate=ate)


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
def ea_replay(
    config: Path = typer.Option(Path("config/ea.yaml"), "-c", "--config"),
    dia: str = typer.Option(..., "--dia", help="YYYY-MM-DD"),
    raiz_raw: Path = typer.Option(Path("data/raw"), "--raiz-raw"),
    log_file: Path | None = typer.Option(None, "--log-file"),
    log_level: str = typer.Option("INFO", "--log-level"),
) -> None:
    """
    Forward-test SEM conexao propria: reler os trades que o `record` JA'
    CAPTUROU (parquet), alimentar o MESMO nucleo do EA (sinal, decisao,
    risco), e reportar as decisoes que teriam sido tomadas.

    Existe por um motivo real de licenciamento (2026-08-27): a chave de
    ativacao so' permite UMA sessao por vez -- rodar `ea` como processo
    separado com conexao propria, ao mesmo tempo que o `record`, nao
    funciona (a segunda conexao recebe NL_INTERNAL_ERROR). O replay reusa
    a mesma logica sem precisar de conexao nenhuma, portanto sem conflito.
    """
    configurar(log_level, log_file)
    from .ea.config import EAConfig
    from .ea.service import EAService

    if not config.exists():
        raise SystemExit(f"nao achei {config} -- crie a partir de "
                         f"config/ea.exemplo.yaml")
    ea_cfg = EAConfig.from_yaml(config)
    caminho = raiz_raw / "trade" / f"dt={dia}" / f"sym={ea_cfg.symbol}"
    if not caminho.exists():
        raise SystemExit(f"nao achei {caminho} -- o record capturou esse dia?")

    typer.echo(f"EA replay: {ea_cfg.symbol} dia={dia} dry_run={ea_cfg.dry_run} "
               f"sinais={[s.feature for s in ea_cfg.sinais]}")
    svc = EAService(ea_cfg)
    svc.rodar_replay(caminho)
    typer.echo(f"trades={svc.stats.trades} barras={svc.stats.barras} "
               f"decisoes={svc.stats.decisoes} "
               f"pnl_dia_pontos={round(svc.gestor.pnl_dia_pontos, 1)} "
               f"perdas_seguidas={svc.gestor.perdas_consecutivas} "
               f"bloqueado={svc.gestor.bloqueado}")


@app.command()
def ea_replay_lote(
    config: Path = typer.Option(Path("config/ea.yaml"), "-c", "--config"),
    raiz_raw: Path = typer.Option(Path("data/raw"), "--raiz-raw"),
    ignorar_circuit_breaker: bool = typer.Option(
        False, "--ignorar-circuit-breaker",
        help="SO' PARA ANALISE: nao interrompe apos 3 perdas seguidas, "
             "para ver o comportamento do dia inteiro. NUNCA usar isso "
             "como configuracao de producao -- e' flag explicita de "
             "diagnostico, nao vem do ea.yaml."),
    comparar_circuit_breaker: bool = typer.Option(
        False, "--comparar-circuit-breaker",
        help="Para todo dia em que o circuit breaker disparar de "
             "verdade, roda TAMBEM sem ele (mesmo dado ja' carregado, "
             "SEM reler o parquet duas vezes) e mostra os dois "
             "resultados lado a lado. Responde 'o freio ajudou ou "
             "atrapalhou NESTE dia' sem precisar rodar o comando duas "
             "vezes manualmente. Nao combina com --ignorar-circuit-breaker."),
    saida: Path = typer.Option(Path("data/research"), "--saida"),
    log_file: Path | None = typer.Option(
        None, "--log-file",
        help="Grava o log DETALHADO (cada barra/decisao de TODOS os "
             "dias) neste arquivo -- sem isso, so' o resumo final vai "
             "para data/research/*.md; o detalhe por decisao se perde."),
    log_level: str = typer.Option("WARNING", "--log-level",
                                  help="WARNING p/ nao afogar o console "
                                       "com o log de cada barra de cada dia. "
                                       "Vale so' para a TELA -- o --log-file "
                                       "sempre grava tudo em INFO."),
) -> None:
    """
    Roda ea-replay em TODOS os dias ja' capturados (uma instancia NOVA de
    EAService por dia -- circuit breaker e posicao reiniciam a cada dia,
    igual rodaria em producao de verdade), agrega o resultado.

    Existe para responder a pergunta certa: um dia isolado tem amostra
    pequena demais para julgar (o proprio quintil do research tinha so'
    ~43% de acerto -- 3 perdas seguidas logo no primeiro dia testado tem
    probabilidade nada desprezivel so' por variancia). O lote da' a
    distribuicao completa por OPERACAO (nao so' o total por dia) -- e'
    isso que decide se a assimetria ganho/perda bate com a expectativa
    matematica validada no research, ou se alguma coisa diverge.
    """
    import statistics as stats

    if comparar_circuit_breaker and ignorar_circuit_breaker:
        raise SystemExit("--comparar-circuit-breaker nao combina com "
                         "--ignorar-circuit-breaker -- sao dois modos "
                         "de diagnostico diferentes, use um ou outro.")

    from .ea.config import EAConfig
    from .ea.service import EAService, carregar_trades_do_dia

    configurar(log_level, log_file, nivel_arquivo="INFO")
    ea_cfg = EAConfig.from_yaml(config)
    raiz_symbol = raiz_raw / "trade"
    dias = sorted(p.name.removeprefix("dt=") for p in raiz_symbol.glob("dt=*")
                 if (p / f"sym={ea_cfg.symbol}").exists())
    if not dias:
        raise SystemExit(f"nenhum dia encontrado em {raiz_symbol} para "
                         f"symbol={ea_cfg.symbol}")

    typer.echo(f"EA replay em lote: {ea_cfg.symbol}, {len(dias)} dia(s), "
               f"ignorar_circuit_breaker={ignorar_circuit_breaker}")

    por_dia: list[dict[str, Any]] = []
    todas_operacoes: list[float] = []
    todas_operacoes_com_lado: list[tuple[int, float]] = []
    # "sem freio" completo (2026-08-27, pergunta real do operador: "por
    # lado" nao deveria ter com/sem freio tambem?). Para dias em que o
    # freio NUNCA disparou, com/sem freio sao IDENTICOS por construcao
    # (o freio so' age depois de bloqueado=True) -- reusa o mesmo dado do
    # svc principal, sem rodar de novo. So' dias que dispararam o freio
    # precisam do segundo passe (svc_sem_freio) para saber o que teria
    # acontecido nas operacoes que o freio impediu.
    todas_operacoes_sem_freio: list[float] = []
    todas_operacoes_com_lado_sem_freio: list[tuple[int, float]] = []
    t0_lote = time.monotonic()
    for i, dia in enumerate(dias, 1):
        # Visibilidade de progresso (2026-08-27, pedido real do operador):
        # rodando dezenas de dias sem nenhum marcador claro de "dia X
        # terminou, comecando dia Y", nao da' pra saber, olhando so' a
        # tela ou so' o log, quantos ja passaram e quantos faltam --
        # sobretudo se o operador nao estiver olhando o terminal no
        # momento exato. log.info() (vai pro --log-file, sempre em INFO
        # desde a v0.73) E typer.echo() (tela, sempre visivel) juntos --
        # funciona tanto acompanhando ao vivo quanto via Get-Content -Wait
        # depois. Boa pratica a repetir em qualquer processo longo futuro.
        log.info("ea.replay_lote_dia_iniciando", dia=dia, numero=i, de=len(dias))
        typer.echo(f"\n[{i}/{len(dias)}] {dia} — iniciando...")

        caminho = raiz_symbol / f"dt={dia}" / f"sym={ea_cfg.symbol}"
        trades = carregar_trades_do_dia(caminho)

        svc = EAService(ea_cfg, ignorar_circuit_breaker=ignorar_circuit_breaker)
        svc.processar_trades_carregados(trades)

        pnl_sem_freio = None
        svc_sem_freio = None
        if comparar_circuit_breaker and svc.gestor.bloqueado:
            # Mesmo dado JA' CARREGADO, sem reler o parquet -- a leitura
            # e' a parte cara (~80s), este segundo passe e' barato (~10s).
            svc_sem_freio = EAService(ea_cfg, ignorar_circuit_breaker=True)
            svc_sem_freio.processar_trades_carregados(trades)
            pnl_sem_freio = round(svc_sem_freio.gestor.pnl_dia_pontos, 1)
            delta = round(pnl_sem_freio - svc.gestor.pnl_dia_pontos, 1)
            typer.echo(f"    [circuit breaker disparou] com freio: "
                      f"{svc.gestor.pnl_dia_pontos:+.1f} pts  |  "
                      f"sem freio: {pnl_sem_freio:+.1f} pts  |  "
                      f"delta: {delta:+.1f} pts")

        por_dia.append({
            "dia": dia, "trades": svc.stats.trades, "barras": svc.stats.barras,
            "decisoes": dict(svc.stats.decisoes),
            "pnl_dia": round(svc.gestor.pnl_dia_pontos, 1),
            "n_operacoes": len(svc.gestor.historico_pnl),
            "perdas_seguidas_final": svc.gestor.perdas_consecutivas,
            "bloqueado": svc.gestor.bloqueado,
            "pnl_sem_freio": pnl_sem_freio,
        })
        todas_operacoes.extend(svc.gestor.historico_pnl)
        todas_operacoes_com_lado.extend(svc.gestor.historico_operacoes)
        if comparar_circuit_breaker:
            # svc_sem_freio existe so' quando o freio disparou neste dia;
            # senao, com/sem freio sao identicos -- reusa svc mesmo.
            fonte = svc_sem_freio if svc_sem_freio is not None else svc
            todas_operacoes_sem_freio.extend(fonte.gestor.historico_pnl)
            todas_operacoes_com_lado_sem_freio.extend(fonte.gestor.historico_operacoes)

        decorrido_s = time.monotonic() - t0_lote
        media_por_dia_s = decorrido_s / i
        eta_s = media_por_dia_s * (len(dias) - i)
        log.info("ea.replay_lote_dia_concluido", dia=dia, numero=i, de=len(dias),
                 pnl_dia=por_dia[-1]["pnl_dia"], operacoes=por_dia[-1]["n_operacoes"],
                 bloqueado=por_dia[-1]["bloqueado"],
                 decorrido_s=round(decorrido_s, 1), eta_s=round(eta_s, 1))
        typer.echo(f"[{i}/{len(dias)}] {dia} concluido: "
                   f"pnl={por_dia[-1]['pnl_dia']:+.1f} pts  "
                   f"operacoes={por_dia[-1]['n_operacoes']}  "
                   f"bloqueado={por_dia[-1]['bloqueado']}  "
                   f"(decorrido={decorrido_s / 60:.1f}min  "
                   f"restante~={eta_s / 60:.1f}min)")

    ganhos = [p for p in todas_operacoes if p > 0]
    perdas = [p for p in todas_operacoes if p <= 0]
    pnl_total = sum(todas_operacoes)
    dias_bloqueados = sum(1 for d in por_dia if d["bloqueado"])

    typer.echo("\n" + "=" * 62)
    typer.echo("RESUMO DO LOTE")
    typer.echo("=" * 62)
    typer.echo(f"  dias                 : {len(dias)}")
    typer.echo(f"  operacoes totais     : {len(todas_operacoes)}")
    typer.echo(f"  pnl total (pts)      : {pnl_total:+.1f}")
    typer.echo(f"  pnl medio/operacao   : {pnl_total / len(todas_operacoes):+.2f}"
               if todas_operacoes else "  pnl medio/operacao   : n/a")
    typer.echo(f"  taxa de acerto       : {len(ganhos) / len(todas_operacoes):.1%}"
               if todas_operacoes else "  taxa de acerto       : n/a")
    if ganhos:
        typer.echo(f"  ganho medio          : {stats.mean(ganhos):+.1f}")
    else:
        typer.echo("  ganho medio          : n/a")
    if perdas:
        typer.echo(f"  perda media          : {stats.mean(perdas):+.1f}")
    else:
        typer.echo("  perda media          : n/a")
    typer.echo(f"  MAIOR ganho          : {max(todas_operacoes):+.1f}" if todas_operacoes else "")
    typer.echo(f"  MAIOR perda          : {min(todas_operacoes):+.1f}" if todas_operacoes else "")
    if ganhos and perdas:
        razao = abs(stats.mean(ganhos) / stats.mean(perdas))
        rotulo = "FAVORAVEL" if razao > 1 else "DESFAVORAVEL — oposto da expectativa buscada"
        typer.echo(f"  razao ganho/perda medio: {razao:.2f}  ({rotulo})")
    typer.echo(f"  dias com circuit breaker disparado: {dias_bloqueados}/{len(dias)}")

    # Curva de patrimonio / drawdown (2026-08-27, pergunta real do
    # operador: "qual o tamanho de conta necessario para essa
    # estrategia?"). Reusa todas_operacoes na ordem CRONOLOGICA real (nao
    # agrupada por lado) -- e' a experiencia de saldo de quem realmente
    # operou dia apos dia. Fora de escopo aqui, registrado como pendencia
    # separada: zeragem por consumo de GARANTIA (precisa da tabela de
    # margem real da B3/XP) -- isto so' mede ruina por P&L.
    curva = None
    if todas_operacoes:
        from .research.curva_patrimonio import calcular_curva_patrimonio
        curva = calcular_curva_patrimonio(
            todas_operacoes, capital_inicial=ea_cfg.risco.capital,
            valor_ponto_reais=ea_cfg.risco.valor_ponto_reais)
        typer.echo("\n  curva de patrimonio (capital inicial "
                   f"R${ea_cfg.risco.capital:.2f}, so' ruina por P&L -- "
                   "NAO cobre zeragem por garantia):")
        typer.echo(f"    saldo final          : R${curva.saldo_final:,.2f}  "
                   f"({curva.retorno_total_pct:+.1%})")
        typer.echo(f"    drawdown maximo      : R${curva.drawdown_maximo_reais:,.2f}  "
                   f"({curva.drawdown_maximo_pct:.1%} do pico de R${curva.saldo_no_pico:,.2f})")
        typer.echo(f"    capital minimo sugerido (1.5x o dd): "
                   f"R${curva.capital_minimo_sugerido:,.2f}")
        typer.echo(f"    calmar ratio (retorno/dd): {curva.calmar_ratio:.2f}")
        if curva.ficou_negativo_ou_zero:
            typer.echo("    ATENCAO: com este capital inicial, o saldo "
                      "chegou a zero ou negativo em algum ponto da amostra.")

    # Quebra por lado (2026-08-27, mesma pergunta que mae.py ja' respondia
    # de forma independente: as perdas do EA simulado estao concentradas
    # no lado de compra -- ja' sem edge segundo o MAE -- ou distribuidas
    # nos dois? So' o dado REAL do proprio EA replay confirma ou nao.
    op_compra = [pnl for lado, pnl in todas_operacoes_com_lado if lado == 1]
    op_venda = [pnl for lado, pnl in todas_operacoes_com_lado if lado == -1]
    typer.echo("\n  por lado (pnl LIQUIDO, ja' descontado o custo):")
    if op_compra:
        typer.echo(f"    compra: n={len(op_compra)}  "
                   f"pnl_liquido_medio={stats.mean(op_compra):+.1f}  "
                   f"pnl_liquido_total={sum(op_compra):+.1f}")
    else:
        typer.echo("    compra: n=0")
    if op_venda:
        typer.echo(f"    venda : n={len(op_venda)}  "
                   f"pnl_liquido_medio={stats.mean(op_venda):+.1f}  "
                   f"pnl_liquido_total={sum(op_venda):+.1f}")
    else:
        typer.echo("    venda : n=0")

    op_compra_sf = op_venda_sf = None
    if comparar_circuit_breaker:
        # Pergunta real do operador (2026-08-27): "por lado" tambem
        # deveria comparar com/sem freio? Sim -- se o freio bloqueia
        # desproporcionalmente um lado (ex.: apos uma sequencia de perdas
        # de compra, o freio tambem impede vendas que teriam edge), a
        # tabela SO' com freio subestima o potencial real daquele lado.
        op_compra_sf = [pnl for lado, pnl in todas_operacoes_com_lado_sem_freio if lado == 1]
        op_venda_sf = [pnl for lado, pnl in todas_operacoes_com_lado_sem_freio if lado == -1]
        typer.echo("\n  por lado SEM o circuit breaker (para comparacao):")
        if op_compra_sf:
            typer.echo(f"    compra: n={len(op_compra_sf)}  "
                       f"pnl_liquido_medio={stats.mean(op_compra_sf):+.1f}  "
                       f"pnl_liquido_total={sum(op_compra_sf):+.1f}")
        else:
            typer.echo("    compra: n=0")
        if op_venda_sf:
            typer.echo(f"    venda : n={len(op_venda_sf)}  "
                       f"pnl_liquido_medio={stats.mean(op_venda_sf):+.1f}  "
                       f"pnl_liquido_total={sum(op_venda_sf):+.1f}")
        else:
            typer.echo("    venda : n=0")

    saida.mkdir(parents=True, exist_ok=True)
    from datetime import UTC, datetime
    arq = saida / f"ea_replay_lote_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.md"
    linhas = [
        "# EA replay em lote\n",
        f"- symbol: {ea_cfg.symbol}",
        f"- dias: {len(dias)} ({dias[0]} a {dias[-1]})",
        f"- ignorar_circuit_breaker: {ignorar_circuit_breaker}",
        f"- operacoes totais: {len(todas_operacoes)}",
        f"- pnl total: {pnl_total:+.1f} pts",
        f"- taxa de acerto: {len(ganhos) / len(todas_operacoes):.1%}" if todas_operacoes else "",
        f"- ganho medio: {stats.mean(ganhos):+.1f}" if ganhos else "",
        f"- perda media: {stats.mean(perdas):+.1f}" if perdas else "",
        f"- MAIOR ganho: {max(todas_operacoes):+.1f}" if todas_operacoes else "",
        f"- MAIOR perda: {min(todas_operacoes):+.1f}" if todas_operacoes else "",
        f"- dias com circuit breaker disparado: {dias_bloqueados}/{len(dias)}",
    ]
    if curva is not None:
        linhas.append("\n## Curva de patrimonio / drawdown\n")
        linhas.append(
            "So' ruina por P&L (saldo cair a zero ou perto) -- NAO cobre "
            "zeragem por consumo de GARANTIA da B3/XP (exigiria a tabela "
            "de margem real, fora de escopo aqui). Registrado como "
            "pendencia separada em docs/EA_ARQUITETURA.md.\n"
        )
        linhas.append(f"- capital inicial: R${ea_cfg.risco.capital:,.2f}")
        linhas.append(f"- saldo final: R${curva.saldo_final:,.2f} "
                      f"({curva.retorno_total_pct:+.1%})")
        linhas.append(f"- drawdown maximo: R${curva.drawdown_maximo_reais:,.2f} "
                      f"({curva.drawdown_maximo_pct:.1%} do pico de "
                      f"R${curva.saldo_no_pico:,.2f})")
        linhas.append(f"- capital minimo sugerido (1.5x o drawdown maximo): "
                      f"R${curva.capital_minimo_sugerido:,.2f}")
        linhas.append(f"- calmar ratio (retorno total / drawdown maximo): "
                      f"{curva.calmar_ratio:.2f}")
        if curva.ficou_negativo_ou_zero:
            linhas.append("- **ATENCAO**: com este capital inicial, o saldo "
                          "chegou a zero ou negativo em algum ponto da amostra.")
    linhas.append("\n## Por dia\n")
    linhas.extend([
        (
            "| dia | pnl (com freio) | pnl (sem freio) | delta | operacoes | "
            "perdas seguidas (final) | bloqueado |"
            if comparar_circuit_breaker else
            "| dia | pnl | operacoes | perdas seguidas (final) | bloqueado |"
        ),
        ("|---|---|---|---|---|---|---|" if comparar_circuit_breaker else "|---|---|---|---|---|"),
    ])
    for d in por_dia:
        if comparar_circuit_breaker:
            if d["pnl_sem_freio"] is not None:
                delta = d["pnl_sem_freio"] - d["pnl_dia"]
                linhas.append(f"| {d['dia']} | {d['pnl_dia']:+.1f} | "
                              f"{d['pnl_sem_freio']:+.1f} | {delta:+.1f} | "
                              f"{d['n_operacoes']} | {d['perdas_seguidas_final']} | "
                              f"{d['bloqueado']} |")
            else:
                linhas.append(f"| {d['dia']} | {d['pnl_dia']:+.1f} | - | - | "
                              f"{d['n_operacoes']} | {d['perdas_seguidas_final']} | "
                              f"{d['bloqueado']} |")
        else:
            linhas.append(f"| {d['dia']} | {d['pnl_dia']:+.1f} | {d['n_operacoes']} | "
                          f"{d['perdas_seguidas_final']} | {d['bloqueado']} |")
    if comparar_circuit_breaker:
        linhas.append(
            "\nATENCAO NA LEITURA: cada linha acima e' UM dia -- nao decida "
            "sobre a calibracao do circuit breaker (max_perdas_consecutivas) "
            "com poucos dias de amostra. O freio protege contra o PIOR "
            "caso, nao maximiza o resultado esperado de um dia especifico; "
            "'o freio atrapalhou este dia' nao significa que a regra esteja "
            "mal calibrada -- so' rodadas futuras, com MUITOS dias em que o "
            "freio disparou, respondem isso de verdade."
        )
    linhas.append("\n## Por lado (pnl LIQUIDO, ja' descontado o custo)\n")
    linhas.append("Mesma pergunta que mae.py ja' respondia de forma independente: "
                  "as perdas estao concentradas no lado de compra (sem edge segundo "
                  "o MAE), ou distribuidas nos dois? Dado REAL do proprio EA "
                  "replay, nao mais inferencia.\n")
    linhas.append("| lado | n | pnl liquido medio | pnl liquido total |")
    linhas.append("|---|---|---|---|")
    linhas.append(f"| compra | {len(op_compra)} | "
                  f"{stats.mean(op_compra):+.1f} | {sum(op_compra):+.1f} |"
                  if op_compra else "| compra | 0 | - | - |")
    linhas.append(f"| venda | {len(op_venda)} | "
                  f"{stats.mean(op_venda):+.1f} | {sum(op_venda):+.1f} |"
                  if op_venda else "| venda | 0 | - | - |")
    if comparar_circuit_breaker:
        linhas.append("\n## Por lado SEM o circuit breaker (para comparacao)\n")
        linhas.append(
            "Se o freio bloqueia desproporcionalmente um lado (ex.: apos "
            "uma sequencia de perdas de compra, tambem impede vendas que "
            "teriam edge), a tabela COM freio acima subestima o potencial "
            "real daquele lado. Esta tabela usa, para os dias em que o "
            "freio disparou, as operacoes que teriam acontecido sem ele; "
            "nos demais dias e' identica a tabela acima (o freio nunca "
            "chegou a agir).\n"
        )
        linhas.append("| lado | n | pnl liquido medio | pnl liquido total |")
        linhas.append("|---|---|---|---|")
        linhas.append(f"| compra | {len(op_compra_sf)} | "
                      f"{stats.mean(op_compra_sf):+.1f} | {sum(op_compra_sf):+.1f} |"
                      if op_compra_sf else "| compra | 0 | - | - |")
        linhas.append(f"| venda | {len(op_venda_sf)} | "
                      f"{stats.mean(op_venda_sf):+.1f} | {sum(op_venda_sf):+.1f} |"
                      if op_venda_sf else "| venda | 0 | - | - |")
    linhas.append("\n## Todas as operacoes (pnl liquido, pontos)\n")
    linhas.append(", ".join(f"{p:+.1f}" for p in todas_operacoes))
    arq.write_text("\n".join(linhas), encoding="utf-8")
    typer.echo(f"\nrelatorio: {arq}")


@app.command()
def mae_analise(
    symbol: str = typer.Option("WINFUT", "--symbol"),
    features: Path = typer.Option(Path("data/features"), "--features"),
    feature: str = typer.Option(..., "--feature", help="ex.: z_agf_3"),
    horizonte: int = typer.Option(..., "--horizonte", help="mesmo h do sinal, ex.: 3"),
    threshold_entrada: float = typer.Option(..., "--threshold-entrada"),
    direcao: str = typer.Option("contrarian", "--direcao"),
    stop_catastrofico_pontos: float = typer.Option(
        500.0, "--stop-catastrofico-pontos",
        help="Deve bater com RiscoConfig.stop_catastrofico_pontos do "
             "ea.yaml (derivado de capital x risco_max_pct / valor_ponto)."),
    saida: Path = typer.Option(Path("data/research"), "--saida"),
    treino_min: int = typer.Option(
        3, "--treino-min",
        help="Mesma semantica de walk-forward do `research`/`quintis`: dias "
             "minimos de treino antes do primeiro bloco de teste. A analise "
             "roda SO' sobre o pool out-of-sample (uniao dos blocos de "
             "teste) -- nunca sobre a amostra inteira, para nao misturar "
             "dia que 'treinou' com dia de avaliacao real."),
    teste_dias: int = typer.Option(2, "--teste-dias"),
) -> None:
    """
    MAE (Maximum Adverse Excursion) por operacao -- responde se o stop
    catastrofico e' so' seguro de cauda (raramente tocado) ou ja esta
    mordendo de verdade dentro da janela real de holding do sinal.

    NAO consome trial: engenharia de risco sobre sinal JA' validado, mesmo
    espirito de `quintis`, nao uma hipotese estatistica nova.
    """
    from .research.mae import analisar_mae

    arquivo = features / f"sym={symbol.upper()}" / "features.parquet"
    if not arquivo.exists():
        raise SystemExit(f"nao achei {arquivo} — rode `profit-tape features` antes")

    r = analisar_mae(arquivo, feature, horizonte, threshold_entrada, direcao,
                     stop_catastrofico_pontos, saida,
                     treino_min=treino_min, teste_dias=teste_dias)
    typer.echo("=" * 62)
    typer.echo(f"MAE — {feature}@h{horizonte}  stop={stop_catastrofico_pontos:.0f}pts  "
               f"n={r['n_triggers']}")
    typer.echo("=" * 62)
    typer.echo(f"  MAE_close   media={r['mae_close_media']:.1f}  "
               f"mediana={r['mae_close_mediana']:.1f}  p90={r['mae_close_p90']:.1f}  "
               f"p99={r['mae_close_p99']:.1f}  max={r['mae_close_max']:.1f}")
    typer.echo(f"  MAE_intrabar (teorico) p90={r['mae_intrabar_p90']:.1f}  "
               f"p99={r['mae_intrabar_p99']:.1f}  max={r['mae_intrabar_max']:.1f}")
    typer.echo(f"  MFE_close (p/ Rota B) media={r['mfe_close_media']:.1f}  "
               f"mediana={r['mfe_close_mediana']:.1f}  p10={r['mfe_close_p10']:.1f}  "
               f"p90={r['mfe_close_p90']:.1f}")
    typer.echo(f"  teria batido o stop: {r['n_teria_batido_stop']}/{r['n_triggers']} "
               f"({r['pct_teria_batido_stop']:.1%})")
    typer.echo(f"  pnl medio SEM stop : {r['pnl_medio_sem_stop']:+.1f} pts")
    typer.echo(f"  pnl medio COM stop hipotetico: "
               f"{r['pnl_medio_com_stop_hipotetico']:+.1f} pts")
    typer.echo("\n  por lado:")
    typer.echo(f"    compra: n={r['stats_compra']['n']}  "
               f"pnl_bruto_medio={r['stats_compra']['pnl_bruto_medio']:+.1f}  "
               f"mae_mediana={r['stats_compra']['mae_close_mediana']:.1f}  "
               f"mfe_mediana={r['stats_compra']['mfe_close_mediana']:.1f}")
    typer.echo(f"    venda : n={r['stats_venda']['n']}  "
               f"pnl_bruto_medio={r['stats_venda']['pnl_bruto_medio']:+.1f}  "
               f"mae_mediana={r['stats_venda']['mae_close_mediana']:.1f}  "
               f"mfe_mediana={r['stats_venda']['mfe_close_mediana']:.1f}")
    typer.echo(f"\nrelatorio: {r['relatorio']}")


@app.command()
def triagem_inprogress(
    raiz_raw: Path = typer.Argument(..., help="Raiz do dado (ex.: data/raw)."),
    destino_quarentena: Path = typer.Option(
        Path("_inprogress_orfaos"), "--destino-quarentena",
        help="Pasta FORA de raiz_raw onde os arquivos sem footer sao "
             "movidos (nunca apagados). Estrutura relativa preservada."),
    idade_min_min: float = typer.Option(
        15.0, "--idade-min-min",
        help="So' mexe em .inprogress mais VELHO que isto (minutos). Um "
             "arquivo mais recente pode ter escritor vivo -- nunca tocado."),
    mover: bool = typer.Option(
        False, "--mover",
        help="Sem isso, so' LISTA o que faria (dry-run). Com isso, "
             "promove (footer valido) ou quarentena (sem footer) de verdade."),
    log_level: str = typer.Option("INFO", "--log-level"),
    log_file: Path | None = typer.Option(None, "--log-file"),
) -> None:
    """
    Triagem de .parquet.inprogress orfaos apos travamento de maquina
    (2026-08-27) -- um travamento derruba TODOS os writers abertos no
    instante, um por stream/simbolo, simultaneamente. Automatiza achar,
    verificar footer, e mover (nunca apagar) o que nao tem recuperacao --
    ou promover (rename) o que teve a sorte de ja ter o footer escrito
    antes do crash.

    Dry-run por padrao -- roda sem --mover primeiro para conferir a lista.
    """
    configurar(log_level, log_file)
    from .tools.triagem_inprogress import gerar_resumo_para_integridade, triagem

    r = triagem(raiz_raw, destino_quarentena, idade_min_min=idade_min_min, mover=mover)

    typer.echo(f"pulados (recentes, intocados): {len(r.pulados_recentes)}")
    typer.echo(f"recuperados (tinham footer)   : {len(r.recuperados)}")
    typer.echo(f"quarentenados (sem footer)    : {len(r.quarentenados)}")
    if not mover and (r.recuperados or r.quarentenados):
        typer.echo("\nDRY-RUN -- nada foi movido. Rode de novo com --mover para aplicar.")
    if r.quarentenados:
        typer.echo("\n" + gerar_resumo_para_integridade(r, raiz_raw))
        typer.echo("\nCopie o bloco acima para docs/INTEGRIDADE_DOS_DADOS.md.")


def _tabela_var_es_fmt(tabela: pd.DataFrame) -> str:
    """
    Formatacao POR COLUNA (2026-08-27, bug real achado pelo operador): um
    float_format UNICO (.2f) aplicado a todas as colunas fazia
    nivel_confianca=0.995 arredondar para "0.99" -- colidindo visualmente
    com o nivel 0.99 de verdade (0.995 em binario e' ligeiramente menor
    que 0.995 exato, ".2f" arredonda pra baixo). Mesma familia de bug ja'
    corrigida em quintis.py (v0.58) -- nao repetida aqui por descuido,
    corrigida agora. nivel_confianca em PERCENTUAL (99.0% vs 99.5% —
    inequivoco), pontos com 2 casas fixas (nunca colidem entre si nessa
    faixa de magnitude).
    """
    formatadores = {"nivel_confianca": lambda v: f"{v:.1%}"}
    for col in tabela.columns:
        if col != "nivel_confianca" and tabela[col].dtype.kind == "f":
            formatadores[col] = lambda v: f"{v:.2f}"
    return tabela.to_string(index=False, formatters=formatadores)


@app.command()
def custo_acoes(
    preco: float = typer.Option(..., "--preco", help="Preco atual da acao (R$)."),
    financeiro: float = typer.Option(
        ..., "--financeiro",
        help="Financeiro que voce pretende expor (mesmo criterio de "
             "risco entre ativos diferentes, ex.: R$10000)."),
    xlsx: Path = typer.Option(
        Path("docs/referencias/custos_acoes_xp.xlsx"), "--xlsx",
        help="Planilha real de custos da XP."),
) -> None:
    """
    Custo de day trade de UMA acao, calculado a partir da planilha real
    da XP -- devolve o numero pronto para `--custo-pontos` do comando
    `quintis`. NUNCA reuse o custo calculado para um ativo em outro
    ativo de preco muito diferente (achado real: custo por acao nao e'
    constante entre ativos, mesmo com o mesmo financeiro exposto).
    """
    from .research.custo_acoes import carregar_parametros_xp, custo_giro_dia_trade

    if not xlsx.exists():
        raise SystemExit(f"planilha nao encontrada em {xlsx}")
    parametros = carregar_parametros_xp(xlsx)
    quantidade = financeiro / preco
    r = custo_giro_dia_trade(preco, quantidade, parametros)

    typer.echo(f"preco={preco:.2f}  financeiro={financeiro:,.2f}  "
               f"quantidade implicita={quantidade:,.0f} acoes")
    typer.echo(f"custo do giro (abre+fecha): R${r['custo_giro_total_reais']:.2f}")
    typer.echo(f"custo por acao (--custo-pontos): {r['custo_por_acao_reais']:.5f}")
    typer.echo(f"custo como % do financeiro: {r['custo_pct_financeiro']:.4%}")


@app.command()
def risco_realizado(
    symbol: str = typer.Option("WINFUT", "--symbol"),
    features: Path = typer.Option(Path("data/features"), "--features"),
    limiar_pontos: float = typer.Option(
        ..., "--limiar-pontos",
        help="O limiar JA' ESCOLHIDO a avaliar (ex.: 500, o stop "
             "catastrofico do ea.yaml). Responde: que nivel de confianca "
             "empirico este limiar representa?"),
    niveis_confianca: str = typer.Option(
        "0.90,0.95,0.99,0.995", "--niveis-confianca",
        help="Lista separada por virgula, ex.: 0.90,0.95,0.99"),
    por_horario: bool = typer.Option(
        False, "--por-horario",
        help="Tambem segmenta por faixa de horario (abertura/meio/"
             "fechamento) -- sazonalidade intradiaria pode enviesar o "
             "VaR agregado sem isso."),
) -> None:
    """
    VaR e Expected Shortfall REALIZADOS sobre o retorno de barra do
    instrumento -- aplica o insight central de "Realized Quantiles"
    (2026-08-27, ver research/risco_realizado.py para a fundamentacao
    completa) para calibrar um limiar de risco (ex.: o stop catastrofico)
    contra o comportamento EMPIRICO de cauda do proprio instrumento, nao
    so' contra uma regra de capital.

    NAO consome trial: engenharia/descricao sobre o instrumento,
    incondicional a qualquer sinal -- mesmo espirito de mae-analise.
    """
    from .research.risco_realizado import (
        nivel_implicado_por_limiar,
        var_es_por_faixa_horario,
        var_es_realizado,
    )

    arquivo = features / f"sym={symbol.upper()}" / "features.parquet"
    if not arquivo.exists():
        raise SystemExit(f"nao achei {arquivo} — rode `profit-tape features` antes")

    import pandas as pd
    df = pd.read_parquet(arquivo)
    retornos_abs = df["close"].diff().abs().dropna()
    niveis = tuple(float(x) for x in niveis_confianca.split(","))

    typer.echo("=" * 62)
    typer.echo(f"RISCO REALIZADO — {symbol}  n_barras={len(retornos_abs)}")
    typer.echo("=" * 62)

    tabela = var_es_realizado(retornos_abs, niveis)
    typer.echo("\nVaR/ES agregado (todas as barras, sem segmentar por horario):")
    typer.echo(_tabela_var_es_fmt(tabela))

    inv = nivel_implicado_por_limiar(retornos_abs, limiar_pontos)
    typer.echo(f"\nO limiar de {limiar_pontos:.0f} pts representa:")
    typer.echo(f"  nivel de confianca implicado: {inv['nivel_confianca_implicado']:.2%}")
    typer.echo(f"  fracao de barras que excedem : {inv['pct_barras_que_excedem']:.2%} "
               f"({inv['n_barras_que_excedem']} barras)")
    typer.echo(f"  ES no limiar (tamanho medio quando excede): "
               f"{inv['es_no_limiar_pontos']:.1f} pts")

    if por_horario:
        typer.echo("\nPor faixa de horario:")
        tabela_h = var_es_por_faixa_horario(df, "ts_close", "close", niveis_confianca=niveis)
        typer.echo(_tabela_var_es_fmt(tabela_h))


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
