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
) -> None:
    """
    Acha (e opcionalmente remove) arquivos .parquet sem footer — fosseis da era
    do fsync quebrado, que a recaptura deixou ao lado dos arquivos novos e bons.
    Dry-run por padrao: nunca apaga sem --remover.
    """
    from .tools.quarentena import varrer

    varrer(raiz, remover)


@app.command()
def curate(
    raw: Path = typer.Option(Path("data/raw"), "--raw"),
    curated: Path = typer.Option(Path("data/curated"), "--curated"),
) -> None:
    """
    Deduplica e ordena raw -> curated. Rode SEMPRE antes de calcular features.

    Idempotente: reprocessar sobrescreve a mesma saida.
    """
    configurar("WARNING")
    from .tools.curate import curar_trades, imprimir_relatorio

    imprimir_relatorio(curar_trades(raw, curated))


@app.command()
def features(
    symbol: str = typer.Argument(..., help="Ex.: WINFUT"),
    curated: Path = typer.Option(Path("data/curated"), "--curated"),
    saida: Path = typer.Option(Path("data/features"), "--saida"),
    volume_barra: int | None = typer.Option(None, "--volume-barra",
                                            help="Fixo; omita para sugerir pela mediana."),
    barras_por_dia: int = typer.Option(100, "--barras-por-dia"),
    top_agentes: int = typer.Option(10, "--top-agentes"),
    janela_z: int = typer.Option(50, "--janela-z"),
    label_k: float = typer.Option(2.0, "--label-k"),
    label_h: int = typer.Option(10, "--label-h"),
) -> None:
    """
    Gera barras de volume (relogio de agressao) com features de fluxo Tier 1,
    z-scores anti-lookahead e labels triple-barrier. Uma linha por barra.
    """
    configurar("WARNING")
    from .features.pipeline import gerar

    r = gerar(curated, saida, symbol.upper(), volume_barra, barras_por_dia,
              top_agentes, janela_z, label_k, label_h)
    typer.echo("=" * 60)
    typer.echo(f"FEATURES — {r['symbol']}")
    typer.echo("=" * 60)
    for chave in ("trades", "volume_barra", "tick_inferido", "barras",
                  "barras_parciais_descartadas", "agentes_top", "labels",
                  "ambiguas", "arquivo"):
        typer.echo(f"  {chave:<28}: {r[chave]}")


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
