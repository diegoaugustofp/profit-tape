"""Interface de linha de comando."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd

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
    login_completo: bool = typer.Option(
        False, "--login-completo",
        help="E1 da trilha de execucao (2026-09-08): sobe a conexao com "
             "DLLInitializeLogin (sessao com roteamento) em vez de "
             "MarketLogin. Sobrescreve runtime.login_completo do yaml. Use "
             "num record de TESTE (pasta separada, fora do pregao) antes "
             "de ligar no yaml de producao -- ver docs/EA_ARQUITETURA.md."),
    sem_encerramento: bool = typer.Option(
        False, "--sem-encerramento",
        help="Ignora runtime.encerrar_em do yaml (roda ate' Ctrl+C). Para o "
             "teste A do E1 fora do pregao: o yaml de producao encerra as "
             "18:30, e o teste roda DEPOIS disso -- na v2.06 ele durou 4 s."),
    ordem_teste_em: str | None = typer.Option(
        None, "--ordem-teste-em",
        help="E2 dentro do record (2026-09-11): no horario HH:MM (local), "
             "envia 1 contrato WINFUT a mercado na conta de SIMULACAO -- "
             "trava conferida contra o que a DLL anunciou (nome da "
             "corretora contem 'Simul') -- confirma o callback de ordem e "
             "zera. Exige login completo. Roda na conexao de producao, no "
             "pregao, sem parar a captura."),
) -> None:
    """Grava tape e book ate o horario configurado ou ate Ctrl+C."""
    configurar(log_level, log_file)
    cfg = RecorderConfig.from_yaml(config)
    if login_completo:
        cfg.runtime.login_completo = True
    if sem_encerramento:
        cfg.runtime.encerrar_em = None
    cred = Credenciais()

    if dry_run:
        typer.echo(f"Config valida: {len(cfg.ativos)} ativos, raiz={cfg.storage.raiz}")
        for a in cfg.ativos:
            flags = [n for n, v in
                     (("trades", a.trades), ("offer", a.offer_book), ("price", a.price_book)) if v]
            typer.echo(f"  {a.ticker:<10} {a.bolsa}  {'+'.join(flags)}")
        if ea_config:
            typer.echo(f"  EA integrado: --ea-config {ea_config}")
        modo = "COMPLETO (roteamento)" if cfg.runtime.login_completo else "market data"
        typer.echo(f"  login: {modo}")
        if ordem_teste_em:
            typer.echo(f"  E2: ordem de teste (1 WINFUT, SIMULACAO) as {ordem_teste_em}")
        typer.echo(f"  encerramento: {cfg.runtime.encerrar_em or 'so Ctrl+C'}")
        raise typer.Exit(0)

    cred.validar()
    from .recorder.service import RecorderService

    raise typer.Exit(RecorderService(cfg, cred, ea_config_path=ea_config,
                                     ordem_teste_em=ordem_teste_em).run())


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

            # E0 (2026-09-08): inventario de execucao. INFORMATIVO -- nao
            # mexe em `ok`, porque o doctor gateia o RECORD, e o record
            # nao precisa de funcao de ordem. Puro hasattr, nao conecta.
            from .profitdll.bindings import inventario_exports_execucao
            inv = inventario_exports_execucao(dll)
            typer.echo("\n  EXECUCAO (E0) — exports de ordem/posicao nesta DLL:")
            for familia, r in inv["familias"].items():
                n_p, n_a = len(r["presentes"]), len(r["ausentes"])
                typer.echo(f"    {familia:<22} {n_p} presente(s), {n_a} ausente(s)")
                if r["ausentes"]:
                    typer.echo(f"      ausentes: {', '.join(r['ausentes'])}")
            leg = "COMPLETO" if inv["caminho_legado_completo"] else "INCOMPLETO"
            v2 = "COMPLETO" if inv["caminho_v2_completo"] else "INCOMPLETO"
            typer.echo(f"    caminho LEGADO (o que execucao.py usa hoje): {leg}")
            if inv["minimo_legado_ausente"]:
                typer.echo(f"      falta: {', '.join(inv['minimo_legado_ausente'])}")
            typer.echo(f"    caminho V2 (SendOrder/struct):               {v2}")
            if inv["minimo_v2_ausente"]:
                typer.echo(f"      falta: {', '.join(inv['minimo_v2_ausente'])}")
            if not inv["caminho_legado_completo"] and not inv["caminho_v2_completo"]:
                typer.echo("    -> NENHUM caminho completo: E1/E2 como desenhados")
                typer.echo("       nao sao possiveis nesta DLL. Registrar e redesenhar.")
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
    dia: str | None = typer.Option(
        None, "--dia", help="Auditoria completa de UM dt=YYYY-MM-DD apenas."),
    completo: bool = typer.Option(
        False, "--completo",
        help="Forca a auditoria completa da arvore inteira mesmo se for grande "
             "(carrega tudo em memoria; horas em HDD/USB)."),
    contagem: bool = typer.Option(
        False, "--contagem",
        help="So' a contagem por dia via metadados (segundos). E' o que "
             "responde 'e' a mesma populacao?'."),
) -> None:
    """
    Resumo do que foi gravado. SEMPRE comeca pela contagem por dia lida dos
    footers (segundos). A auditoria completa (que carrega o dado) so' roda
    para um --dia, para arvores pequenas, ou com --completo explicito --
    incidente real: 8h mudo tentando concatenar 25 pregoes em memoria.
    """
    from .tools.inspect import resumir

    resumir(caminho, stream, dia=dia, completo=completo, so_contagem=contagem)


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
    modo_leitura: str = typer.Option(
        "lote", "--modo-leitura",
        help="'lote' (default, paralelo) / 'sequencial' (lote sem threads -- "
             "tente se 'lote' parecer travado; leitura paralela de centenas "
             "de arquivos pode causar thrashing em HD mecanico ou volume de "
             "rede) / 'fragmento' (pula o lote inteiramente, volta ao loop "
             "antigo arquivo-a-arquivo -- mais lento mas e' o unico modo que "
             "ja terminou de verdade em producao; use se 'sequencial' "
             "tambem nao der sinal de vida)."),
    diagnostico: bool = typer.Option(
        False, "--diagnostico",
        help="Forca leitura fragmento-a-fragmento e loga progresso a cada 25 "
             "arquivos (curate.leitura_progresso) -- diz se a lentidao e' "
             "LINEAR (todo arquivo custando igual, suspeita de IO/antivirus) "
             "ou concentrada NUM arquivo (pulo brusco entre checkpoints). "
             "Use quando um dia estiver demorando horas sem log nenhum."),
    dia: str | None = typer.Option(
        None, "--dia", help="Restringe a UM dt=YYYY-MM-DD. Combinavel com --simbolo."),
    simbolo: str | None = typer.Option(
        None, "--simbolo",
        help="Restringe a UM simbolo (ex.: WINFUT). Combinavel com --dia. "
             "Util pra isolar um simbolo suspeito de lentidao sem esperar "
             "o dia inteiro chegar nele."),
) -> None:
    """
    Deduplica e ordena raw -> curated. Rode SEMPRE antes de calcular features.

    Idempotente: reprocessar sobrescreve a mesma saida. Loga progresso por
    (dia, simbolo) -- curate.processando / curate.particao_ok -- e por ETAPA
    dentro de cada particao (curate.leitura_ok / conversao_pandas_ok /
    dedup_ok, mais curate.leitura_progresso com --diagnostico) — o log so'
    ao fim ficaria mudo por horas se uma particao for grande, indistinguivel
    de travado.
    """
    configurar(log_level, log_file)
    from .tools.curate import curar_trades, imprimir_relatorio

    if modo_leitura not in ("lote", "sequencial", "fragmento"):
        raise typer.BadParameter(
            "--modo-leitura precisa ser 'lote', 'sequencial' ou 'fragmento'")
    imprimir_relatorio(curar_trades(raw, curated, modo_leitura=modo_leitura,
                                    diagnostico=diagnostico,
                                    dia_filtro=dia, simbolo_filtro=simbolo))


@app.command()
def compact(
    raw: Path = typer.Option(Path("data/raw"), "--raw"),
    log_level: str = typer.Option("INFO", "--log-level"),
    log_file: Path | None = typer.Option(
        None, "--log-file",
        help="Grava o log em arquivo alem do console (compact.particao_ok por "
             "particao, com row groups antes/depois)."),
    row_group_size: int = typer.Option(
        1_048_576, "--row-group-size",
        help="Linhas por row group DENTRO de cada arquivo novo. Grande e "
             "explicito de proposito -- e' o que desfaz os row groups de 15 "
             "linhas do backfill antigo."),
    max_rows_per_file: int = typer.Option(
        5_000_000, "--max-rows-per-file",
        help="Linhas por arquivo (mesmo limite do sink)."),
    modo_leitura: str = typer.Option(
        "lote", "--modo-leitura",
        help="'lote' (default, paralelo) / 'sequencial' (sem threads) / "
             "'fragmento' (arquivo a arquivo) -- mesma semantica do curate."),
    dia: str | None = typer.Option(
        None, "--dia", help="Restringe a UM dt=YYYY-MM-DD. Combinavel com --simbolo."),
    simbolo: str | None = typer.Option(
        None, "--simbolo", help="Restringe a UM simbolo. Combinavel com --dia."),
) -> None:
    """
    Reescreve o raw de dias FECHADOS consolidando row groups minusculos.

    Incidente 2026-09-10: backfill em micro-lotes deixou part-0000 do WINFUT
    com 519.764 linhas em 34.525 row groups, o que fazia o curate levar
    horas. O writer ja' foi corrigido; isto conserta o que ja' esta' no disco.
    NAO e' curadoria (nada de dedup/sort) -- so' reorganizacao fisica, e o
    dia corrente e particoes com .inprogress sao sempre pulados. Seguro
    reexecutar: particao ja' compacta e' reconhecida e pulada; compactacao
    interrompida e' concluida na rodada seguinte.
    """
    configurar(log_level, log_file)
    from .tools.compact import compactar_raw, imprimir_relatorio

    if modo_leitura not in ("lote", "sequencial", "fragmento"):
        raise typer.BadParameter(
            "--modo-leitura precisa ser 'lote', 'sequencial' ou 'fragmento'")
    if row_group_size > max_rows_per_file:
        raise typer.BadParameter("--row-group-size nao pode exceder --max-rows-per-file")
    imprimir_relatorio(compactar_raw(raw, row_group_size=row_group_size,
                                     max_rows_per_file=max_rows_per_file,
                                     modo_leitura=modo_leitura,
                                     dia_filtro=dia, simbolo_filtro=simbolo))


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
    agentes: str | None = typer.Option(
        None, "--agentes",
        help="Lista FIXA de agentes para agf_* (ex.: 3,8,39). Forward da Fase 2: "
             "o top-N muda com o historico; o modelo congelado precisa das mesmas colunas"),
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
            fixos = [int(a) for a in agentes.split(",")] if agentes else None
            r = gerar(curated, saida, sym, volume_barra, barras_por_dia,
                      top_agentes, janela_z, label_k, label_h, perfis,
                      agentes_fixos=fixos)
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
def features_tempo(
    symbol: str = typer.Argument("WINFUT", help="Ex.: WINFUT"),
    segundos: int = typer.Option(300, "--segundos",
                                 help="60 (1m) ou 300 (5m) — so' esses dois "
                                      "estao no pre-registro de 2026-08-29e."),
    curated: Path = typer.Option(Path("data/curated"), "--curated"),
    saida: Path = typer.Option(Path("data/features_tempo"), "--saida"),
    janela_minutos: int = typer.Option(
        250, "--janela-minutos",
        help="Janela do z-score em MINUTOS (nao em barras): casa a "
             "normalizacao entre 1m e 5m."),
    log_file: Path | None = typer.Option(None, "--log-file"),
    log_level: str = typer.Option("WARNING", "--log-level"),
) -> None:
    """
    Features em BARRA DE TEMPO para o pre-registro da absorcao direcional.

    Gera SO as tres colunas pre-registradas (absorcao_dir, desloc_norm,
    imbalance) — o conjunto completo faria o `research` cobrar 28 trials por
    timeframe em vez dos 6 pre-registrados. Saida separada de
    data/features/, que continua sendo barra de volume.
    """
    # nivel_arquivo="INFO": convencao do projeto -- console pode ficar
    # quieto, mas o arquivo grava INFO completo sempre. Sem isso o
    # --log-file herdaria o WARNING do console e sairia vazio.
    configurar(log_level, arquivo=log_file, nivel_arquivo="INFO")
    from .features.pipeline_tempo import gerar_tempo

    r = gerar_tempo(curated, saida, symbol.strip().upper(), segundos,
                    janela_minutos)
    typer.echo("=" * 62)
    typer.echo(f"FEATURES EM BARRA DE TEMPO — {r['symbol']} {r['tf']}")
    typer.echo("=" * 62)
    for k in ("dias", "trades", "barras", "barras_finais_descartadas",
              "buracos", "range_ticks_mediano", "tick_inferido",
              "janela_z_barras", "janela_z_minutos", "colunas_z", "arquivo"):
        typer.echo(f"  {k:26}: {r[k]}")


@app.command()
def portao_absorcao(
    trials: Path = typer.Option(Path("data/research/trials.json"), "--trials",
                                help="Para usar o MESMO limiar que o teste "
                                     "real vai enfrentar."),
    semeaduras: int = typer.Option(20, "--semeaduras",
                                   help="Tapes de ruido para o nulo empirico."),
    dias: int = typer.Option(25, "--dias"),
    saida: Path | None = typer.Option(None, "--saida",
                                      help="CSV opcional com as duas tabelas."),
    log_file: Path | None = typer.Option(None, "--log-file"),
    log_level: str = typer.Option("INFO", "--log-level"),
) -> None:
    """
    PORTAO DE HONESTIDADE do pre-registro de 2026-08-29e — bloqueante.

    Roda o mesmo caminho de medicao sobre TAPE SINTETICO sem edge nenhum
    (grade de tick + bounce bid/ask, lado agressor independente do passo do
    preco). Reprova o desenho se qualquer celula sair `segue` sobre ruido
    puro. Nao toca trials.json.
    """
    configurar(log_level, arquivo=log_file, nivel_arquivo="INFO")
    from .research.portao_absorcao import rodar_portao

    r = rodar_portao(trials_json=str(trials), n_semeaduras=semeaduras,
                     n_dias=dias)
    typer.echo("=" * 62)
    typer.echo("PORTAO DE HONESTIDADE — absorcao direcional (2026-08-29e)")
    typer.echo("=" * 62)
    typer.echo(f"  limiar_z usado      : {r['limiar_z']:.3f} "
               f"(trials {r['trials_base']} + {r['trials_extra']})")
    typer.echo(f"  vereditos           : {r['vereditos']}")
    typer.echo(f"  PASSOU              : {r['passou']}")
    typer.echo("\n--- rodada congelada ---")
    typer.echo(r["tabela"][["tf", "feature", "horizonte", "ic_medio", "t_stat",
                            "consistencia_sinal", "veredito"]].to_string(index=False))
    typer.echo(f"\n--- nulo empirico ({r['n_semeaduras']} tapes) ---")
    typer.echo(r["nulo_empirico"].round(5).to_string(index=False))
    if saida:
        saida.parent.mkdir(parents=True, exist_ok=True)
        r["nulo_empirico"].to_csv(saida, index=False)
        typer.echo(f"\n  nulo empirico gravado em {saida.resolve()}")
    if not r["passou"]:
        raise SystemExit("PORTAO REPROVOU — nao gaste trial (ver pre-registro)")


@app.command()
def ntsl_equivalencia(
    log: Path = typer.Option(..., "--log",
                             help="Dump do console do Profit com as linhas ABSDIR|."),
    features: Path = typer.Option(..., "--features",
                                  help="Parquet de data/features_tempo/."),
    segundos: int = typer.Option(300, "--segundos", help="60 ou 300."),
    hora_bolsa: bool = typer.Option(
        False, "--hora-bolsa",
        help="Usa TimeExchange no lugar de Time. Se NENHUMA barra casar "
             "com o default, o grafico esta em fuso diferente do da bolsa "
             "e e' esta a flag que resolve."),
    janela_z: int = typer.Option(
        50, "--janela-z",
        help="Janela do z-score, em barras. Usada para avisar quando as "
             "barras casadas caem no inicio do parquet, onde o z NAO e' "
             "comparavel por construcao."),
    tolerancia: float = typer.Option(1e-6, "--tolerancia"),
    log_level: str = typer.Option("INFO", "--log-level"),
) -> None:
    """
    Confronta o indicador NTSL com as features calculadas em Python.

    NAO devolve "bate / nao bate": devolve a distribuicao da diferenca
    campo a campo. Duas divergencias sao ESPERADAS e estao previstas por
    escrito — o OHLC do grafico inclui RLP e leilao, o do profit-tape nao;
    e nao esta documentado se AgressionVolBuy/Sell excluem RLP. Diferenca
    so' em desloc_norm aponta para a primeira; diferenca tambem em
    imbalance aponta para a segunda.
    """
    configurar(log_level)
    from .tools.ntsl_equivalencia import comparar

    r = comparar(log, features, segundos, usar_hora_bolsa=hora_bolsa,
                 janela_z=janela_z, tolerancia=tolerancia)
    typer.echo("=" * 62)
    typer.echo("EQUIVALENCIA NTSL <-> profit-tape")
    typer.echo("=" * 62)
    for k in ("linhas_com_prefixo", "malformadas", "duplicadas", "barras",
              "barras_python", "barras_casadas", "sem_par_no_python",
              "coluna_hora_usada", "tolerancia"):
        typer.echo(f"  {k:22}: {r[k]}")
    typer.echo("")
    if r["tabela"].empty:
        typer.echo("  nenhum campo comparavel — as barras casaram?")
    else:
        typer.echo(r["tabela"].round(6).to_string(index=False))
    borda = r["z_na_borda"]
    if borda.get("aviso"):
        typer.echo(f"\n  AVISO SOBRE O z: {borda['aviso']}")
    atrib = r["atribuicao_rlp"]
    if "barras_so_numerador_difere" in atrib:
        typer.echo("\n--- de onde vem a divergencia de desloc_norm ---")
        typer.echo("    desloc_norm = (close - open) / (high - low)")
        typer.echo(f"  tick estimado {atrib['tick_estimado']} | "
                   f"fatores k distintos: {atrib['k_distintos']}")
        if atrib["k_distintos"] > 1:
            typer.echo("    ATENCAO: houve ROLAGEM dentro da amostra. k por pregao:")
            for dia, kv in sorted(atrib["k_por_pregao"].items()):
                typer.echo(f"      {dia}: {kv}")
        typer.echo(f"  so' o NUMERADOR (close-open) difere : "
                   f"{atrib['barras_so_numerador_difere']} de {atrib['n']}")
        typer.echo(f"  so' o DENOMINADOR (high-low) difere : "
                   f"{atrib['barras_so_denominador_difere']}")
        typer.echo(f"  os dois diferem                     : "
                   f"{atrib['barras_ambos_diferem']}")
        typer.echo(f"  nenhum difere                       : "
                   f"{atrib['barras_nada_difere']}"
                   f"  (erro mediano {atrib['erro_mediano_nada_difere']})")
        typer.echo(f"  diferenca mediana do numerador   : "
                   f"{atrib['dif_numerador_mediana_ticks']} ticks")
        typer.echo(f"  diferenca mediana do denominador : "
                   f"{atrib['dif_denominador_mediana_ticks']} ticks")
        typer.echo("\n  qual ponta do numerador diverge (open e close sao o")
        typer.echo("  primeiro e o ultimo negocio da barra):")
        typer.echo(f"    so' open  : {atrib['barras_so_open']}"
                   f"   |  so' close : {atrib['barras_so_close']}"
                   f"   |  os dois : {atrib['barras_open_e_close']}")
        typer.echo(f"    dif mediana open  : "
                   f"{atrib['dif_open_mediana_ticks']} ticks  |  close : "
                   f"{atrib['dif_close_mediana_ticks']} ticks")
    elif atrib.get("situacao"):
        typer.echo(f"\n  atribuicao nao calculada: {atrib['situacao']}")
    if r["barras_casadas"] == 0:
        typer.echo("\n  NENHUMA barra casou. Tente --hora-bolsa, ou confira "
                   "se o --segundos bate com o timeframe do grafico.")


@app.command()
def rota_b_remanescente(
    symbol: str = typer.Argument("WINFUT"),
    features: Path = typer.Option(Path("data/features"), "--features"),
    curated: Path = typer.Option(Path("data/curated"), "--curated"),
    saida: Path = typer.Option(Path("data/research"), "--saida"),
    volume_barra: int | None = typer.Option(
        None, "--volume-barra",
        help="O MESMO usado ao gerar as features. Se omitido, e' lido do "
             "resumo.json ao lado do parquet ou, na falta dele, inferido "
             "de min(vol_agr). O portao monta barras de ruido com esta "
             "granularidade; errar aqui compara geometrias diferentes."),
    so_agressao: bool = typer.Option(
        True, "--so-agressao/--com-rlp",
        help="Quais negocios disparam o stop. Default True (RLP nao "
             "consome liquidez do livro). Rode os dois: se a conclusao "
             "mudar, e achado de microestrutura e tem que aparecer."),
    dias_ruido: int = typer.Option(100, "--dias-ruido"),
    log_file: Path | None = typer.Option(None, "--log-file"),
    log_level: str = typer.Option("INFO", "--log-level"),
) -> None:
    """
    ROTA B — expectativa remanescente a partir do toque, com F exato.

    Executa o pre-registro 3 congelado em 2026-08-30d, NA ORDEM:
    pre-voo (bloqueante), portao de honestidade (bloqueante), dado real.
    A ordem esta no codigo: se o portao nao devolver CONTRA sobre ruido,
    o comando aborta antes de olhar qualquer numero real.
    """
    configurar(log_level, arquivo=log_file, nivel_arquivo="INFO")
    from .research.remanescente_tape import rodar

    arquivo = features / f"sym={symbol.upper()}" / "features.parquet"
    if not arquivo.exists():
        raise SystemExit(f"nao achei {arquivo} — rode `profit-tape features`")

    r = rodar(arquivo, curated, symbol.strip().upper(), saida,
              volume_barra=volume_barra, so_agressao=so_agressao,
              n_dias_ruido=dias_ruido)

    typer.echo("=" * 66)
    typer.echo("ROTA B — remanescente a partir do toque (pre-registro 2026-08-30d)")
    typer.echo("=" * 66)
    typer.echo(f"\n  volume_barra: {r['volume_barra']}  "
               f"({r['volume_barra_origem']})")
    typer.echo("\n--- 1. CHECAGEM DE PRE-VOO (bloqueante) ---")
    for k, v in r["prevoo"].items():
        typer.echo(f"  {k:22}: {v}")
    typer.echo("\n--- 2. PORTAO SOBRE RUIDO (bloqueante) ---")
    typer.echo(f"  veredito: {r['portao']['veredito']}  |  passou: "
               f"{r['portao']['passou']}")
    typer.echo("\n--- 3. DADO REAL ---")
    typer.echo(f"  limiar deflacionado (7 comparacoes): "
               f"{r['limiar_deflacionado']}")
    typer.echo(f"  so_agressao: {r['so_agressao']}")
    typer.echo(r["tabela"][["x", "n", "n_suficiente", "media", "t",
                            "ic95_baixo", "ic95_alto", "overshoot_medio",
                            "sig"]].round(3).to_string(index=False))
    typer.echo(f"\n  VEREDITO: {r['veredito']}")
    typer.echo(f"  {r['motivo']}")


@app.command()
def absorcao_diagnostico(
    symbol: str = typer.Argument("WINFUT"),
    features: Path = typer.Option(Path("data/features_tempo"), "--features"),
    tf: str = typer.Option("5m", "--tf"),
    tick: float = typer.Option(5.0, "--tick"),
    limiar: float = typer.Option(1.75, "--limiar"),
    limiar_imb: float = typer.Option(1.0, "--limiar-imb"),
    log_level: str = typer.Option("INFO", "--log-level"),
) -> None:
    """
    Distribuicao do ESFORCO (vol_agr/tick) e separacao A/B da absorcao.

    Categoria `features`: descreve o dado, NAO testa hipotese, NAO
    consome trial. Nada aqui autoriza conclusao sobre retorno.

    A vira A quando a agressao empurrou para um lado e o preco foi para
    o outro (esforco que falhou). B e' preco andando SEM agressao
    dominante — livro fino, que e' quase o oposto de absorcao.
    """
    configurar(log_level)
    from .research.absorcao_diagnostico import rodar

    arquivo = (features / f"sym={symbol.upper()}" / f"tf={tf}"
               / "features.parquet")
    if not arquivo.exists():
        raise SystemExit(
            f"nao achei {arquivo} — rode `profit-tape features-tempo`")

    r = rodar(arquivo, tick=tick, limiar=limiar, limiar_imb=limiar_imb)
    typer.echo("=" * 70)
    typer.echo(f"DIAGNOSTICO DE ABSORCAO — {symbol.upper()} {tf}")
    typer.echo("=" * 70)
    typer.echo(f"  barras: {r['barras']}  |  amplitude zero (esforco "
               f"indefinido): {r['amplitude_zero']}")
    typer.echo("\n--- ESFORCO = vol_agr / amplitude_em_ticks ---")
    for k, v in r["esforco_geral"].items():
        typer.echo(f"  {k:>4}: {v:>12,.1f} contratos por tick")
    typer.echo("\n--- POR LEITURA (limiar "
               f"{limiar} / limiar_imb {limiar_imb}) ---")
    tabela = pd.DataFrame(r["por_leitura"])
    typer.echo(tabela.to_string(index=False))
    typer.echo("\n  A_* = agressao empurrou e o preco foi para o outro lado")
    typer.echo("  B_* = preco andou SEM agressao dominante (livro fino)")


@app.command()
def triagem(
    coluna: str = typer.Argument(..., help="Feature candidata a triar."),
    features: Path = typer.Option(
        Path("data/features_tempo/sym=WINFUT/tf=5m/features.parquet"),
        "--features"),
    contra: str | None = typer.Option(
        None, "--contra",
        help="Features existentes, separadas por virgula. Sem isto, "
             "compara com TODAS as numericas do parquet."),
    expr: str | None = typer.Option(
        None, "--expr",
        help="Expressao que DEFINE a candidata, quando ela ainda nao esta "
             "no parquet. Ex.: --expr \"vol_agr / ((high-low)/5)\". Sem "
             "isto, `coluna` e' lida do parquet."),
    numerador: str | None = typer.Option(
        None, "--numerador",
        help="Nome de coluna OU expressao."),
    denominador: str | None = typer.Option(
        None, "--denominador",
        help="Nome de coluna OU expressao. Se a candidata e' uma razao, "
             "declare as partes: razao entre quantidades que andam juntas "
             "e' quase constante por construcao."),
    log_level: str = typer.Option("INFO", "--log-level"),
) -> None:
    """
    Tria uma feature candidata ANTES de gastar trial.

    Olha so' a FORMA da variavel — redundancia, cauda, construcao — e
    NUNCA toca em retorno. Categoria `features`: zero trial.

    REPROVA e' bloqueante para pre-registro. PASSA nao autoriza nada:
    so' significa que nao da' para descartar olhando a forma.
    """
    configurar(log_level)
    from .features.triagem import triar_parquet

    if not features.exists():
        raise SystemExit(f"nao achei {features}")
    r = triar_parquet(features, coluna,
                      contra.split(",") if contra else None,
                      numerador, denominador, expr)

    typer.echo("=" * 64)
    typer.echo(f"TRIAGEM DE `{coluna}`  ->  {r['veredito']}")
    if r.get("expressao") and r["expressao"] != coluna:
        typer.echo(f"  definida como: {r['expressao']}")
    typer.echo("=" * 64)
    for m in r["motivos"]:
        typer.echo(f"  !! {m}")
    if not r["motivos"]:
        typer.echo("  nenhum defeito de forma detectado")
        typer.echo("  (PASSA nao autoriza nada — so' que nao da' para")
        typer.echo("   descartar olhando a forma)")

    typer.echo("\n--- REDUNDANCIA (|corr| >= 0,95 reprova) ---")
    typer.echo(pd.DataFrame(r["redundancia"]).head(8).to_string(index=False))

    c = r["cauda"]
    if "pct_acima_de_2_5_sd" in c:
        typer.echo("\n--- CAUDA ---")
        typer.echo(f"  {c['pct_acima_de_2_5_sd']}% acima de 2,5 desvios "
                   f"| normal: {c['pct_esperado_sob_normal']}% "
                   f"| razao: {c['razao_com_a_normal']}x")
        typer.echo(f"  faixa observada: [{c['min']}, {c['max']}]")

    if "correlacao_numerador_denominador" in r["razao"]:
        typer.echo("\n--- RAZAO ---")
        typer.echo(f"  corr(numerador, denominador) = "
                   f"{r['razao']['correlacao_numerador_denominador']:+.4f}")
        typer.echo(f"  {r['razao']['nota']}")


@app.command()
def absorcao_barra(
    features: Path = typer.Option(
        Path("data/features_tempo/sym=WINFUT/tf=5m/features.parquet"),
        "--features"),
    saida: Path = typer.Option(Path("data/research"), "--saida"),
    dias_ruido: int = typer.Option(900, "--dias-ruido"),
    log_level: str = typer.Option("INFO", "--log-level"),
) -> None:
    """
    ABSORCAO DE BARRA — pre-registro congelado em 2026-08-31.

    Ordem: portao sobre ruido (BLOQUEANTE), depois dado real. Se o
    portao nao devolver CONTRA, o comando aborta antes de olhar qualquer
    numero real.
    """
    configurar(log_level)
    from .research.absorcao_barra import rodar

    if not features.exists():
        raise SystemExit(
            f"nao achei {features} — rode `profit-tape features-tempo`")
    r = rodar(features, saida, n_dias_ruido=dias_ruido)

    typer.echo("=" * 72)
    typer.echo("ABSORCAO DE BARRA (pre-registro 2026-08-31)")
    typer.echo("=" * 72)
    typer.echo(f"  portao sobre ruido: {r['portao']['veredito']} "
               f"(passou: {r['portao']['passou']})")
    typer.echo(f"  barras: {r['barras']}  |  eventos: {r['eventos']}")
    typer.echo(f"  limiar deflacionado (2 comparacoes): "
               f"{r['limiar_deflacionado']}\n")
    typer.echo(r["tabela"][["grupo", "n", "n_suficiente", "media", "t",
                            "ic95_baixo", "ic95_alto", "sig"]]
               .round(3).to_string(index=False))
    typer.echo(f"\n  VEREDITO: {r['veredito']}")
    typer.echo(f"  {r['motivo']}")
    typer.echo("\n  CONTROLE = diagnostico, nao criterio: responde se a "
               "conjuncao acrescenta algo.")


@app.command()
def absorcao_grafico(
    log: Path = typer.Argument(..., help="Dump do console com linhas ABSBARRA|"),
    saida: Path = typer.Option(Path("data/research"), "--saida"),
    dias_ruido: int = typer.Option(900, "--dias-ruido"),
    log_level: str = typer.Option("INFO", "--log-level"),
) -> None:
    """
    Roda o pre-registro da absorcao sobre dados do GRAFICO.

    Amostra INDEPENDENTE, um tiro, consome trial. Recusa dump que se
    sobreponha a 24/07-27/08 (ja' no parquet): a independencia e' a
    unica razao de usar esta fonte.
    """
    configurar(log_level)
    from .research.absorcao_grafico import rodar

    r = rodar(log, saida, n_dias_ruido=dias_ruido)
    typer.echo("=" * 72)
    typer.echo("ABSORCAO DE BARRA — amostra do GRAFICO (independente)")
    typer.echo("=" * 72)
    d = r["log"]
    typer.echo(f"  {d['barras']} barras | {d['pregoes']} pregoes | "
               f"{d['inicio']} a {d['fim']}")
    typer.echo(f"  portao sobre ruido: {r['portao']}")
    typer.echo(f"  eventos: {r['eventos']}\n")
    typer.echo("--- CONFERENCIA Python vs .ntsl (divergencia = os dois nao")
    typer.echo("    sao a mesma coisa) ---")
    for campo, v in r["conferencia_ntsl"].items():
        if v.get("comparaveis"):
            typer.echo(f"  {campo:16} n={v['comparaveis']:5d} "
                       f"dif_mediana={v['dif_mediana']} "
                       f"dif_max={v['dif_max']}")
    typer.echo("")
    typer.echo(r["tabela"][["grupo", "n", "n_suficiente", "media", "t",
                            "ic95_baixo", "ic95_alto", "sig"]]
               .round(3).to_string(index=False))
    typer.echo(f"\n  VEREDITO: {r['veredito']}")
    typer.echo(f"  {r['motivo']}")


@app.command()
def bollinger_scalp(
    log: Path = typer.Argument(..., help="Dump do console com linhas BBSBARRA| (grafico de 15s)"),
    saida: Path = typer.Option(Path("data/research/bollinger_scalp"), "--saida"),
    tolerancia: float = typer.Option(
        0.5, "--tolerancia",
        help="Diferenca maxima Python x Profit para considerar a variante equivalente"),
    log_level: str = typer.Option("INFO", "--log-level"),
) -> None:
    """
    Scalp de Bollinger (15s): equivalencia Python x Profit + funil da regra.

    Categoria `features`, nao consome trial: nao olha retorno. Responde
    duas perguntas, medindo: (1) qual variante de cada indicador o Profit
    calcula (ddof, %K ou %D, ATR aritmetica ou Wilder); (2) quantos
    gatilhos cada clausula da regra deixa passar, por pregao.
    """
    configurar(log_level)
    from .research.bollinger_scalp import equivalencia, rodar

    r = rodar(log, saida)
    if tolerancia != 0.5:
        r["equivalencia"] = equivalencia(r["barras"], tolerancia)
    m = r["meta"]
    typer.echo("=" * 72)
    typer.echo("SCALP DE BOLLINGER — dump do grafico de 15s")
    typer.echo("=" * 72)
    typer.echo(f"  {m['barras']} barras | {m['pregoes']} pregoes | {m['blocos']} bloco(s) "
               f"contiguo(s) | {m['inicio']} a {m['fim']} | Time com segundos: "
               f"{m['time_com_segundos']}")
    typer.echo("\n--- EQUIVALENCIA Python x Profit (a variante que bate e' a que o")
    typer.echo("    operador ve no grafico; a que nao bate e' formula diferente) ---")
    for campo, v in r["equivalencia"].items():
        marca = "BATE" if v["bate"] else "NAO BATE"
        typer.echo(f"  {campo:12} melhor={v['melhor']!s:12} {marca}")
        for var, det in v["detalhe"].items():
            if det.get("comparaveis"):
                typer.echo(f"      {var:12} n={det['comparaveis']:5d} "
                           f"dif_max={det['dif_max']} dif_mediana={det['dif_mediana']}")
    if r["largura_banda"]:
        lb = r["largura_banda"]
        typer.echo(f"\n  Meia-largura da banda 0,38: p10={lb['meia_largura_p10_pts']} "
                   f"p50={lb['meia_largura_p50_pts']} p90={lb['meia_largura_p90_pts']} pts "
                   f"(p50 = {lb['meia_largura_p50_ticks']} ticks)")
    if r["atr"]:
        typer.echo(f"  ATR21: p50={r['atr']['atr21_p50_pts']} p90={r['atr']['atr21_p90_pts']} "
                   f"pts (stop da hipotese = 40 pts)")
    cob = r["cobertura"]
    typer.echo("\n--- COBERTURA POR PREGAO (o funil so' conta os inteiros) ---")
    typer.echo(cob.to_string(index=False))
    n_int = int(cob["inteiro"].sum())
    if n_int < len(cob):
        typer.echo(f"  AVISO: {len(cob) - n_int} pregao(oes) incompleto(s) fora do funil. "
                   "Regra pratica: um pregao por dump.")
    typer.echo(f"\n--- FUNIL DA REGRA (7.4) -- por_pregao = / {n_int} pregao(oes) inteiro(s) ---")
    typer.echo(r["funil"].to_string(index=False))
    dg = r["diagnostico"]
    typer.echo("\n--- DIAGNOSTICO (7.6: se uma clausula nunca dispara, e' o desenho) ---")
    for lado in ("compra", "venda"):
        v = dg.get(lado, {})
        if v.get("candidatos"):
            typer.echo(f"  {lado}: {v['candidatos']} candidatos (banda em t-2 e t-1). "
                       f"Est(t-1) quantis 5/25/50/75/95 = {v['est_t1_quantis_5_25_50_75_95']}")
            typer.echo(f"      Est(t-1) <20: {v['est_t1_abaixo_20']}  >80: {v['est_t1_acima_80']}"
                       f"  <50: {v['est_t1_abaixo_50']}  >50: {v['est_t1_acima_50']}"
                       f"  | Est(t-2) <20: {v['est_t2_abaixo_20']}  >80: {v['est_t2_acima_80']}")
    if "tr" in dg:
        t = dg["tr"]
        typer.echo(f"  TR da barra de 15s: p50={t['tr_p50_pts']} pts | barras com TR >= stop(40): "
                   f"{t['pct_barras_tr_ge_stop']}% | TR >= 80: {t['pct_barras_tr_ge_2x_stop']}%")
    typer.echo(f"\n  saida: {saida}")


@app.command()
def perfil_volume_horario(
    symbol: str = typer.Argument("WINFUT"),
    curated: Path = typer.Option(Path("data/curated"), "--curated"),
    minutos: int = typer.Option(30, "--minutos", help="Largura da faixa; divide 60"),
    saida: Path = typer.Option(Path("data/research/perfil_volume_horario"), "--saida"),
    log_level: str = typer.Option("WARNING", "--log-level"),
) -> None:
    """
    Perfil de volume de AGRESSAO por faixa horaria (mediana entre pregoes).

    Para a regra de horario do scalp de Bollinger (docs/BOLLINGER_SCALP.md).
    MEDE; nao escolhe o corte -- a regra e' declarada pelo operador em
    cima destes numeros, antes de qualquer replay. Categoria `features`.
    """
    configurar(log_level)
    from .research.perfil_volume_horario import perfil

    r = perfil(curated, symbol.strip().upper(), minutos)
    saida.mkdir(parents=True, exist_ok=True)
    r["por_dia"].to_parquet(saida / "por_dia.parquet", index=False)
    r["mediana"].to_csv(saida / "mediana.csv", index=False)
    typer.echo("=" * 72)
    typer.echo(f"PERFIL DE VOLUME POR FAIXA DE {minutos} MIN — {r['symbol']} — "
               f"mediana de {r['pregoes']} pregoes")
    typer.echo("=" * 72)
    m = r["mediana"].copy()
    m["pct_do_dia"] = (100 * m["pct_do_dia"]).round(1)
    m["pct_da_abertura"] = (100 * m["pct_da_abertura"]).round(0)
    m["por_barra_15s"] = m["por_barra_15s"].round(1)
    m["contratos"] = m["contratos"].round(0)
    m["negocios"] = m["negocios"].round(0)
    typer.echo(m.to_string(index=False))
    typer.echo("\n  por_barra_15s = negocios de agressao por barra de 15s (mediana)")
    typer.echo("  pct_da_abertura = contratos da faixa / primeira faixa completa")
    typer.echo(f"  saida: {saida}")


@app.command()
def inventario_deepscalper(
    symbol: str = typer.Argument("WINFUT"),
    curated: Path = typer.Option(Path("data/curated"), "--curated"),
    raw: Path = typer.Option(Path("data/raw"), "--raw",
                             help="Raiz do raw (book_offer/book_price/tiny_book nao sao curados)"),
    volume_barra: int = typer.Option(120_000, "--volume-barra",
                                     help="CONGELADO do EA (config/ea.yaml)"),
    data_book_confiavel: str = typer.Option(
        "2026-08-26", "--data-book-confiavel",
        help="Primeiro dia com book_offer confiavel (v0.55, INTEGRIDADE_DOS_DADOS.md)"),
    saida: Path = typer.Option(Path("data/research/inventario_deepscalper"), "--saida"),
    log_level: str = typer.Option("WARNING", "--log-level"),
) -> None:
    """
    Fase 0 do pre-registro DeepScalper (RESEARCH_PLANO.md, 2026-09-07):
    barras/pregao (TAXA), barras/hora (define `h`), spread em ticks,
    pregoes com book integro (portao de 160 da Fase 3). Categoria
    `features`: zero trial. MEDE; nao decide nada.
    """
    configurar(log_level)
    from .research.inventario_deepscalper import PORTAO_FASE_3, gravar, inventario

    r = inventario(curated, raw, symbol.strip().upper(), volume_barra,
                   data_book_confiavel)
    gravar(r, saida)
    s = r["resumo"]
    typer.echo("=" * 72)
    typer.echo(f"INVENTARIO DEEPSCALPER (Fase 0) — {s['symbol']} — "
               f"barra de {s['volume_barra']:,} contratos")
    typer.echo("=" * 72)
    typer.echo(f"  pregoes com trade curated        : {s['pregoes_trade']}")
    typer.echo(f"  pregoes com book INTEGRO         : {s['pregoes_book_integro']}"
               f"   (>= {s['data_book_confiavel']}, offer+price presentes)")
    typer.echo(f"  faltam para o portao da Fase 3   : {s['faltam_para_portao_fase3']}"
               f"   (portao = {PORTAO_FASE_3})")
    typer.echo(f"  barras por pregao (mediana)      : {s['barras_por_pregao_mediana']:.0f}"
               "   <- TAXA da ficha forward")
    typer.echo(f"  horas por pregao (mediana)       : {s['horas_por_pregao_mediana']:.2f}")
    typer.echo(f"  barras por hora (mediana)        : {s['barras_por_hora_mediana']:.2f}")
    typer.echo(f"  h (barras que cobrem 120 min)    : {s['h_120min']}")
    typer.echo(f"  tick (mediana)                   : {s['tick_mediana']:.1f}")
    typer.echo(f"  spread mediana / p90 (ticks)     : {s['spread_mediana_ticks']:.2f} / "
               f"{s['spread_p90_ticks']:.2f}   "
               f"em {s['pregoes_com_tiny_book']} pregoes com tiny_book")
    typer.echo(f"  fracao do tempo-evento em 1 tick : {s['spread_frac_1tick']:.2f}")
    typer.echo("\n  spread ponderado por EVENTO de tiny_book, nao por tempo; <= 0 excluido")
    typer.echo(f"  saida: {saida}  (por_dia.csv, por_dia.parquet, resumo.json)")


@app.command()
def simulador_conferir(
    features: Path = typer.Option(Path("data/features/sym=WINFUT/features.parquet"),
                                  "--features"),
    ea_config: Path = typer.Option(Path("config/ea.yaml"), "--ea-config"),
    operacoes_replay: Path = typer.Option(Path("data/research/operacoes_replay.parquet"),
                                          "--operacoes-replay",
                                          help="Saida do ea-replay-lote"),
    z_continuo: bool = typer.Option(
        False, "--z-continuo",
        help="NAO recalcular z por dia (o EA recalcula; so' para medir a diferenca)"),
    sem_circuit_breaker: bool = typer.Option(False, "--sem-circuit-breaker"),
    saida: Path = typer.Option(Path("data/research/simulador_conferencia"), "--saida"),
    log_level: str = typer.Option("WARNING", "--log-level"),
) -> None:
    """
    Fase 1 do pre-registro DeepScalper, conferencia 3: o simulador de
    replay (features.parquet) reproduz o P&L do ea-replay-lote (trades ao
    vivo) para a regra que o EA ja' roda? Mesmo GestorDeRisco, mesmo
    decidir(); o que pode divergir e' a barra ou o z. Nao decide nada.
    """
    import pandas as pd

    from .ea.config import EAConfig
    from .research.simulador import (
        Regras,
        Simulador,
        conferir_com_replay,
        politica_ea,
        preparar,
    )
    configurar(log_level)
    cfg = EAConfig.from_yaml(ea_config)
    barras = pd.read_parquet(features)
    cols_z = None if z_continuo else [f"agf_{s.agent_id}" for s in cfg.sinais]
    b = preparar(barras, z_por_dia=cols_z, janela_z=cfg.janela_z)
    sim = Simulador(b, Regras(custo_pontos=cfg.custo_pontos_estimado, risco=cfg.risco,
                              circuit_breaker=not sem_circuit_breaker))
    r = sim.rodar(politica_ea(cfg.sinais, cfg.janela_z))
    saida.mkdir(parents=True, exist_ok=True)
    r["operacoes"].to_parquet(saida / "operacoes_simulador.parquet", index=False)
    r["por_dia"].to_csv(saida / "por_dia_simulador.csv", index=False)
    typer.echo("=" * 72)
    typer.echo(f"SIMULADOR x EA-REPLAY — {cfg.symbol} — z {'continuo' if z_continuo else 'por dia'}"
               f" — circuit breaker {'OFF' if sem_circuit_breaker else 'ON'}")
    typer.echo("=" * 72)
    typer.echo(f"  simulador: {len(r['operacoes'])} operacoes, {r['pnl_total']:+.1f} pts "
               f"em {len(r['por_dia'])} pregoes")
    if not operacoes_replay.exists():
        typer.echo(f"  (sem {operacoes_replay}: rode ea-replay-lote antes para conferir)")
        return
    ea_ops = pd.read_parquet(operacoes_replay)
    c = conferir_com_replay(r["operacoes"], ea_ops)
    c["por_dia"].to_csv(saida / "conferencia_por_dia.csv", index=False)
    typer.echo(f"  ea-replay : {c['n_ea']} operacoes, {c['pnl_ea']:+.1f} pts")
    typer.echo(f"  casadas (dia, barra, lado): {c['casadas']}   so' sim: {c['so_sim']}   "
               f"so' EA: {c['so_ea']}")
    typer.echo(f"  casadas com |dif pnl| > 0.5 pt: {c['casadas_fora_da_tolerancia']}   "
               f"(max {c['max_dif_pnl_casadas']:.1f})")
    if c["so_sim"] or c["so_ea"]:
        typer.echo("\n  nao casadas (primeiras 40):")
        typer.echo(c["nao_casadas"].to_string(index=False))
    veredito = ("BATE" if c["so_sim"] == 0 and c["so_ea"] == 0
                and c["casadas_fora_da_tolerancia"] == 0 else "NAO BATE")
    typer.echo(f"\n  VEREDITO: {veredito}. Se NAO BATE, o simulador esta' errado ou a "
               "barra/z difere — nao a regra.")
    typer.echo(f"  saida: {saida}")


@app.command()
def fase2_preparar(
    symbol: str = typer.Argument("WINFUT"),
    features: Path = typer.Option(Path("data/features/sym=WINFUT/features.parquet"),
                                  "--features"),
    curated: Path | None = typer.Option(
        None, "--curated",
        help="Raiz do curated para desempatar toque ambiguo pelo TAPE (recomendado)"),
    h: int = typer.Option(3, "--h", help="CONGELADO na ficha: horizonte do sinal validado"),
    custo: float = typer.Option(11.0, "--custo",
                                help="custo_pontos_estimado do EA (spread dentro)"),
    janela_z: int = typer.Option(50, "--janela-z"),
    saida: Path = typer.Option(Path("data/research/fase2"), "--saida"),
    log_level: str = typer.Option("WARNING", "--log-level"),
) -> None:
    """
    Fase 2 DeepScalper, passo "antes de ligar" (RESEARCH_PLANO, FICHA
    FORWARD). Roda SO' em dado queimado: triagem de redundancia, escolha
    de k (regra fixa), treino com split temporal por dia, medicao de
    p*, nula e TAXA, retreino no total e congelamento (.pkl + sha256).
    Os numeros de validacao sao DEPURACAO, nao evidencia.
    """
    configurar(log_level)
    from .research.fase2 import preparar_fase2

    r = preparar_fase2(features, saida, symbol.strip().upper(), h=h, custo=custo,
                       janela_z=janela_z, curated=curated)
    f = r["ficha"]
    sep = "=" * 72
    typer.echo(sep)
    typer.echo(f"FASE 2 — PREPARAR ({f['symbol']}, h={f['h']}, custo={f['custo_pontos']})")
    typer.echo(sep)
    typer.echo("  triagem de redundancia (|rho| > 0,9):")
    typer.echo(f"    mantidas : {', '.join(f['features'])}")
    for c, m, rho in f["features_removidas_redundancia"]:
        typer.echo(f"    removida : {c}  (rho={rho:+.3f} com {m})")
    typer.echo("")
    typer.echo("  escolha de k (regra fixa: maior k com >= 60% resolvidas e barreira >= 2x custo):")
    tabela = r["escolha_k"].round(3).to_string(index=False)
    for linha in tabela.splitlines():
        typer.echo("    " + linha)
    typer.echo(f"    -> k = {f['k']}   ({f['k_motivo']})")
    tape = "SIM" if f["desempate_pelo_tape"] else "NAO (ambiguo conta 0)"
    typer.echo(f"    desempate pelo tape: {tape}")
    typer.echo("")
    typer.echo(f"  split temporal: treino {f['dias_treino'][0]}..{f['dias_treino'][1]} "
               f"(n={f['n_treino']})  validacao {f['dias_validacao'][0]}.."
               f"{f['dias_validacao'][1]} (n={f['n_validacao']})")
    typer.echo(f"  classes no treino: {f['classes_treino']}")
    typer.echo("")
    typer.echo("  [MEDIR] da ficha, preenchidos:")
    typer.echo(f"    p*                       : {f['MEDIDO_p_star']:.3f}")
    typer.echo(f"    nula (resolvidas/2)      : {f['MEDIDO_nula']:.3f}   "
               f"(resolvidas {f['MEDIDO_frac_resolvidas']:.3f})")
    typer.echo(f"    TAXA (eventos/pregao)    : {f['MEDIDO_taxa_eventos_por_pregao']:.2f}")
    hz = f["horizonte_pregoes_para_150"]
    if hz:
        typer.echo(f"    HORIZONTE p/ n=150       : {hz:.0f} pregoes")
    else:
        typer.echo("    HORIZONTE p/ n=150       : indefinido (taxa 0)")
    typer.echo("")
    typer.echo("  DEPURACAO (validacao queimada; NAO e' evidencia):")
    typer.echo(f"    eventos {f['DEPURACAO_n_eventos_validacao']}  acerto "
               f"{(f['DEPURACAO_acerto_validacao'] or 0):.3f}  pnl proxy/op "
               f"{(f['DEPURACAO_pnl_proxy_por_op'] or 0):+.1f}")
    typer.echo("")
    typer.echo(f"  modelo: {f['modelo_arquivo']}  sha256 {f['modelo_sha256'][:16]}...")
    typer.echo(f"  ficha : {saida / 'ficha_fase2.json'}  sha256 {f['ficha_sha256'][:16]}...")
    if hz and hz > 60:
        typer.echo("")
        typer.echo("  ATENCAO: horizonte > 60 pregoes. Pela ficha, NAO LIGA.")


@app.command()
def fase2_score(
    symbol: str = typer.Argument("WINFUT"),
    dia: str | None = typer.Option(None, "--dia", help="Um pregao (2026-09-09)"),
    desde: str | None = typer.Option(None, "--desde", help="Todos os pregoes >= esta data"),
    features: Path = typer.Option(Path("data/features/sym=WINFUT/features.parquet"),
                                  "--features"),
    curated: Path | None = typer.Option(Path("data/curated"), "--curated",
                                        help="Desempate pelo tape (mesma regra do preparar)"),
    pasta_fase2: Path = typer.Option(Path("data/research/fase2"), "--pasta-fase2",
                                     help="Onde estao ficha_fase2.json e modelo_fase2.pkl"),
    permitir_queimado: bool = typer.Option(
        False, "--permitir-queimado",
        help="So' para o checklist (olhar barras de um dia ja' visto). NAO grava no livro"),
    log_level: str = typer.Option("WARNING", "--log-level"),
) -> None:
    """
    Forward da Fase 2: escora o(s) pregao(oes) com o modelo CONGELADO,
    grava uma linha por evento em forward_eventos.csv com carimbo
    (tag + sha256 do modelo) e imprime o placar. Recusa dias ja'
    usados no treino/validacao (dado queimado) a menos que
    --permitir-queimado, e nesse caso NAO grava.
    """
    import json

    import pandas as pd

    from .research.fase2 import (
        carregar_modelo,
        carregar_trades_dos_dias,
        colunas_tier1,
        escorar,
        placar,
        registrar_forward,
    )
    from .research.simulador import preparar
    configurar(log_level)
    if (dia is None) == (desde is None):
        raise SystemExit("informe --dia OU --desde")
    with open(pasta_fase2 / "ficha_fase2.json", encoding="utf-8") as f:
        ficha = json.load(f)
    m = carregar_modelo(Path(ficha["modelo_arquivo"]) if Path(ficha["modelo_arquivo"]).exists()
                        else pasta_fase2 / "modelo_fase2.pkl")
    if m["sha256"] != ficha["modelo_sha256"]:
        raise SystemExit("modelo_fase2.pkl NAO bate com o sha256 da ficha — carimbo quebrado; "
                         "nao escoro com modelo diferente do congelado")
    barras = pd.read_parquet(features)
    b = preparar(barras, z_por_dia=colunas_tier1(barras), janela_z=int(ficha["janela_z"]))
    todos = sorted(b["dia"].unique())
    dias = [dia] if dia else [d for d in todos if d >= desde]
    ultimo_queimado = ficha["dias_validacao"][1]
    queimados = [d for d in dias if d <= ultimo_queimado]
    if queimados and not permitir_queimado:
        raise SystemExit(f"dias {queimados} sao dado queimado (<= {ultimo_queimado}). "
                         "Use --permitir-queimado so' para olhar barras; nao entra no livro.")
    faltando = [d for d in dias if d not in todos]
    if faltando:
        typer.echo(f"  (sem barras no features.parquet para {faltando}; "
                   "rode `profit-tape features` com --agentes da ficha)")
    dias = [d for d in dias if d in todos]
    if not dias:
        raise SystemExit("nenhum pregao para escorar")
    trades = carregar_trades_dos_dias(curated, symbol.strip().upper(), dias) if curated else None
    ev = escorar(b, m, dias, trades_por_dia=trades)
    sep = "=" * 72
    typer.echo(sep)
    modo = "QUEIMADO (nao grava)" if permitir_queimado else "forward"
    typer.echo(f"FASE 2 — SCORE {symbol.upper()} — {dias[0]}..{dias[-1]} — "
               f"modelo {m['sha256'][:12]} — {modo}")
    typer.echo(sep)
    if ev.empty:
        typer.echo("  nenhum evento (conf < p* em todas as barras validas)")
    else:
        cols = ["dia", "bar_id", "hora_utc", "close", "lado_previsto", "conf", "barreira_pts",
                "label", "t_evento", "label_desempatada_tape", "acerto", "pnl_liquido_proxy"]
        typer.echo(ev[cols].round(3).to_string(index=False))
    if permitir_queimado:
        typer.echo("\n  (dado queimado: nada gravado)")
        return
    livro = pasta_fase2 / "forward_eventos.csv"
    tudo = registrar_forward(ev, livro) if not ev.empty else (
        pd.read_csv(livro, dtype={"dia": str}) if livro.exists() else ev)
    p = placar(tudo, ficha)
    typer.echo("")
    typer.echo(f"  livro: {livro}   eventos acumulados: {p['n']} em {p['pregoes']} pregoes")
    if p["n"] < p["checkpoint_sanidade"]:
        typer.echo(f"  placar fechado ate' n = {p['checkpoint_sanidade']} (sanidade) e "
                   f"n = {p['n_para_veredito']} (veredito). Nao olhe antes.")
    else:
        typer.echo(f"  acerto {p['acerto']:.3f}  (nula {p['nula']:.3f}, favoravel >= "
                   f"{p['alvo_favoravel']:.3f})   pts/op {p['pts_por_op']:+.1f}")
        if p["n"] < p["n_para_veredito"]:
            typer.echo(f"  checkpoint de SANIDADE, nao veredito: veredito em n = "
                       f"{p['n_para_veredito']}")


@app.command()
def bollinger_replay(
    symbol: str = typer.Argument("WINFUT"),
    curated: Path = typer.Option(Path("data/curated"), "--curated"),
    saida: Path = typer.Option(Path("data/research/bollinger_replay"), "--saida"),
    dumps: Path | None = typer.Option(
        None, "--dumps",
        help="Pasta com dumpAAAAMMDD.txt do grafico de 15s: compara tape x grafico nesses dias"),
    dias: str | None = typer.Option(
        None, "--dias", help="Lista 2026-09-01,2026-09-02 (default: todos)"),
    ignorar_circuit_breaker: bool = typer.Option(
        False, "--ignorar-circuit-breaker",
        help="Mede a regra INTEIRA (o circuit breaker fecha o pregao na 3a perda seguida)"),
    log_level: str = typer.Option("INFO", "--log-level"),
) -> None:
    """
    Scalp de Bollinger v1: replay das tres pernas pelo TAPE (depuracao).

    Barras de 15s montadas do tape, regra v1 (docs/BOLLINGER_SCALP.md
    secao 0), limitada em t, tres pernas, trailing e zeragem executados
    negocio a negocio. Preenche os dois campos "a medir" da ficha:
    OPERACOES por pregao e um p1 de depuracao. Nao e' o forward.
    """
    configurar(log_level)
    import re

    from .research.bollinger_replay import rodar

    mapa: dict[str, Path] | None = None
    if dumps is not None:
        mapa = {}
        for f in sorted(dumps.glob("dump*.txt")):
            m = re.search(r"(\d{4})(\d{2})(\d{2})", f.name)
            if m:
                mapa[f"{m.group(1)}-{m.group(2)}-{m.group(3)}"] = f
    lista = [d.strip() for d in dias.split(",")] if dias else None
    r = rodar(curated, symbol.strip().upper(), saida, mapa, lista,
              ignorar_circuit_breaker=ignorar_circuit_breaker)
    res = r["resumo"]
    if ignorar_circuit_breaker:
        typer.echo("  [circuit breaker IGNORADO: taxa da regra inteira]")
    typer.echo("=" * 72)
    typer.echo("SCALP DE BOLLINGER v1 — replay pelo tape (DEPURACAO)")
    typer.echo("=" * 72)
    typer.echo(f"  pregoes {res['pregoes']} | sinais {res['sinais']} | operacoes "
               f"{res['operacoes']} ({res['operacoes_por_pregao']} por pregao) "
               f"| sem execucao {res['sinais_sem_execucao']} {res['nao_exec_por_motivo']}")
    if "p1" in res:
        typer.echo(f"  p1 (alvo1 antes do stop) = {res['p1']}  IC95 {res['p1_ic95']}  "
                   f"| nula de lucro apos custo = {res['p1_nula_lucro']}")
        typer.echo(f"  compra {res['compra']} venda {res['venda']} | abertura {res['abertura']} "
                   f"recuo {res['recuo']} | stop mediano {res['stop_mediano_pts']} pts "
                   f"| duracao mediana {res['duracao_mediana_s']} s")
        typer.echo(f"  BORDA BRUTA (antes de qualquer custo): {res['pnl_bruto_medio_pts']} "
                   f"pts/operacao, IC95 {res['pnl_bruto_ic95']} | p1 vs nula a custo zero 0,50")
        typer.echo(f"  CUSTO MAXIMO SUPORTADO: {res['custo_maximo_suportado_pts_por_contrato']} "
                   f"pts por contrato (IC95 {res['custo_maximo_suportado_ic95']}) "
                   f"| custo atual do YAML: {res.get('custo_por_contrato_pts', 11.0)}")
        typer.echo(f"  P&L liquido: {res['pnl_liquido_medio_pts']} pts/operacao, "
                   f"{res['pnl_liquido_por_pregao_pts']} pts/pregao (3 contratos, custo 33)")
        for i in (1, 2, 3):
            typer.echo(f"  perna {i}: {res[f'p{i}_motivos']} | media "
                       f"{res.get(f'p{i}_pts_medio')} pts | positiva em "
                       f"{res.get(f'p{i}_pct_positiva')}%")
        typer.echo("  cortes pre-declarados (abertura x recuo; compra x venda):")
        for nome, v in res["cortes_pre_declarados"].items():
            typer.echo(f"    {nome:9} n={v['n']:4d} p1={v['p1']} IC95={v['ic95']} "
                       f"P&L liq medio={v['pnl_liquido_medio_pts']} pts")
    comp = res.get("comparacoes_com_dump") or {}
    if comp:
        typer.echo("\n--- TAPE x GRAFICO (mesmo dia; qual conjunto de negocios monta o OHLC "
                   "do grafico?) ---")
        for dia, por_conjunto in comp.items():
            typer.echo(f"  {dia}:")
            for conjunto, c in por_conjunto.items():
                campos = ("open", "high", "low", "close")
                ohlc = "/".join(str(c.get(f"{k}_divergentes")) for k in campos)
                buraco = (f" | so dump {c['so_dump']} ({c.get('so_dump_de')}-"
                          f"{c.get('so_dump_ate')})" if c.get("so_dump") else "")
                typer.echo(f"    {conjunto:20} comuns {c['comuns']} | OHLC divergentes "
                           f"o/h/l/c = {ohlc}"
                           f" | sinais compra tape/dump {c.get('sinal_compra_tape')}/"
                           f"{c.get('sinal_compra_dump')} venda {c.get('sinal_venda_tape')}/"
                           f"{c.get('sinal_venda_dump')}{buraco}")
    typer.echo(f"\n  saida: {saida}")


@app.command()
def absorcao_inspecionar(
    dia: str = typer.Argument(..., help="Data no formato 2026-08-27"),
    origem: Path = typer.Option(
        Path("data/features_tempo/sym=WINFUT/tf=5m/features.parquet"),
        "--origem", help="Parquet de features OU dump ABSBARRA| do grafico"),
    so_falhas: bool = typer.Option(
        False, "--so-falhas", help="Esconde as barras que marcaram"),
    log_level: str = typer.Option("WARNING", "--log-level"),
) -> None:
    """
    Por que ESTA barra marcou (ou nao marcou)?

    Mostra o valor de cada condicao e a FOLGA ate o corte. Categoria
    `features`: nao toca em retorno, nao consome trial.

    LIMITE: nao ajuste corte a partir daqui. Se a formalizacao nao
    captura a leitura, o caminho e' pre-registro NOVO. E inspecione so'
    periodo JA' QUEIMADO — olhar o que ainda vai ser testado destroi a
    cegueira que e' a unica razao de ele valer.
    """
    configurar(log_level)
    from .research.absorcao_inspecao import rodar

    if not origem.exists():
        raise SystemExit(f"nao achei {origem}")
    r = rodar(origem, dia)

    typer.echo("=" * 78)
    typer.echo(f"INSPECAO DE {dia}")
    typer.echo("=" * 78)
    typer.echo("  cortes: " + " | ".join(f"{k} {v}"
                                          for k, v in r["cortes"].items()))
    s = r["resumo"]
    typer.echo(f"  {s['barras']} barras, {s['marcaram']} marcaram")
    typer.echo(f"  reprovaram por: resultado {s['falhou_resultado']} | "
               f"alcance {s['falhou_alcance']} | esforco {s['falhou_esforco']} "
               f"| contexto {s['falhou_contexto']}")
    typer.echo("")
    tab = r["tabela"]
    if so_falhas:
        tab = tab[~tab["MARCOU"]]
    typer.echo(tab.to_string(index=False))


@app.command()
def desenho2_emd(
    log: Path = typer.Argument(..., help="Dump ABSBARRA| da amostra de DEPURACAO"),
    unidade: float = typer.Option(
        244.0, "--unidade",
        help="Amplitude media da barra, para o EMD ficar interpretavel."),
    log_level: str = typer.Option("WARNING", "--log-level"),
) -> None:
    """
    Simula a gestao do DESENHO 2 e mede o EMD, antes de congelar.

    Categoria `features`: usa VARIANCIA, nunca a media. O resultado NAO
    e' evidencia sobre a hipotese -- responde so' se o desenho consegue
    detectar um efeito plausivel.

    Rode SO' na amostra de depuracao (parquet, maio). Rodar no periodo de
    teste queimaria a cegueira.
    """
    configurar(log_level)
    from .research.absorcao_barra import marcar_eventos, preparar
    from .research.absorcao_grafico import carregar_log, para_barras
    from .research.desenho2_risco import (
        diagnostico,
        diagnostico_por_lado,
        medir_emd,
        simular,
    )

    df, diag = carregar_log(log)
    b = para_barras(df)
    b["hora"] = df["hora"].astype(int)
    ops = simular(marcar_eventos(preparar(b)))
    if ops.empty:
        raise SystemExit("nenhum evento no dump")

    e = medir_emd(ops, unidade)
    typer.echo("=" * 72)
    typer.echo("DESENHO 2 — EMD sobre a amostra de DEPURACAO")
    typer.echo("=" * 72)
    typer.echo(f"  {diag['pregoes']} pregoes | {len(ops)} eventos | "
               f"{e['operacoes']} operadas | {e['nao_operou']} descartadas "
               f"(stop > 500)")
    typer.echo("\n--- EMD (so variancia e n; a media NAO entra) ---")
    typer.echo(pd.DataFrame(e["por_lado"]).to_string(index=False))
    op = ops[ops["saida"] != "nao_operou"]
    if len(op) >= 2:
        from .research.triagem_poder import avaliar_desenho
        junto = avaliar_desenho(op["resultado"], unidade, "AMBOS OS LADOS")
        typer.echo(pd.DataFrame([junto]).to_string(index=False))
    typer.echo("\n  referencia: DESENHO 1 no trial 2026 -> desvio 319, "
               "EMD 107 pts, 0,44 unidades")
    typer.echo("\n--- DIAGNOSTICO (nunca criterio) ---")
    for k, v in diagnostico(ops).items():
        typer.echo(f"  {k}: {v}")
    typer.echo("\n--- DIAGNOSTICO POR LADO ---")
    typer.echo(diagnostico_por_lado(ops).to_string(index=False))
    typer.echo("\n  GEOMETRIA (longe do resultado): risco_p50, risco_p90,")
    typer.echo("  descartados.")
    typer.echo("  PERTO DO RESULTADO: stop/alvo/tempo, mfe, custo_do_alvo —")
    typer.echo("  quebrados por lado, respondem 'qual lado funciona melhor'.")
    typer.echo("  Permitido aqui porque 2026 virou DEPURACAO para o desenho 2.")
    typer.echo("  Mas descartar um lado POR CAUSA disto e' SELECAO: precisa")
    typer.echo("  ser declarada, e o teste vai para 2025 — o unico periodo")
    typer.echo("  cego que resta.")
    typer.echo("\n  A media do resultado NAO e' reportada de proposito.")


@app.command()
def curva_poder(
    log: Path = typer.Argument(..., help="Dump ABSBARRA| da amostra de DEPURACAO"),
    unidade: float = typer.Option(244.0, "--unidade"),
    log_level: str = typer.Option("WARNING", "--log-level"),
) -> None:
    """
    EMD em funcao do limiar de contexto K. Categoria `features`.

    Usa VARIANCIA e n; a media do retorno nao entra. Responde "com que K
    o desenho consegue detectar algo", nunca "com que K o resultado fica
    bom".

    NAO autoriza rodar varios K no teste e ficar com o melhor: um K, um
    pre-registro.
    """
    configurar(log_level)
    from .research.absorcao_barra import marcar_eventos, preparar
    from .research.absorcao_grafico import carregar_log, para_barras
    from .research.triagem_poder import curva_de_poder

    df, diag = carregar_log(log)
    d = marcar_eventos(preparar(para_barras(df)))
    n_ev = int(d["evento"].sum())
    typer.echo("=" * 72)
    typer.echo("CURVA DE PODER — EMD por limiar de contexto")
    typer.echo("=" * 72)
    typer.echo(f"  {diag['pregoes']} pregoes | {len(d)} barras")
    typer.echo(f"  absorcao (as 3 condicoes): {n_ev} barras = "
               f"{n_ev / diag['pregoes']:.1f} por pregao")
    typer.echo("")
    typer.echo(curva_de_poder(d, (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0),
                              unidade).to_string(index=False))
    typer.echo("\n  O que vale e' o PIOR lado: o veredito precisa dos dois.")
    typer.echo("  Baixar K NAO tira a direcao (sign(mov6) existe sempre),")
    typer.echo("  mas ENFRAQUECE a hipotese: 'apos movimento forte' vira")
    typer.echo("  'apos movimento'. Essa e' a troca a decidir.")


@app.command()
def decompor_efeito(
    log: Path = typer.Argument(..., help="Dump ABSBARRA| de amostra QUEIMADA"),
    grupo: str = typer.Option(
        "controle", "--grupo",
        help="controle (contexto sem evento) | evento (evento+contexto)"),
    log_level: str = typer.Option("WARNING", "--log-level"),
) -> None:
    """
    FASE DE ENTENDIMENTO: onde o efeito esta', nao se ele existe.

    Decompoe o retorno por LADO e por TIPO DE DIA. Diagnostico puro —
    nao produz veredito e nao gasta trial.

    SO' EM AMOSTRA QUEIMADA (parquet, maio, 2026, 2025). Qualquer numero
    daqui e' HIPOTESE, nunca evidencia: testa-lo exige declaracao propria
    e amostra que nao seja esta.
    """
    configurar(log_level)
    from .research.absorcao_barra import marcar_eventos, preparar, retornos
    from .research.absorcao_grafico import carregar_log, para_barras
    from .research.decomposicao import classificar_dias, decompor, resumir

    df, diag = carregar_log(log)
    b = para_barras(df)
    d = marcar_eventos(preparar(b))
    dias = classificar_dias(b)

    if grupo == "controle":
        mascara = d["contexto_ok"] & ~d["evento"]
        titulo = "CONTROLE — contexto sem evento"
    else:
        mascara = d["evento"] & d["contexto_ok"]
        titulo = "EVENTO — evento + contexto"
    r = retornos(d, mascara)

    typer.echo("=" * 72)
    typer.echo(f"DECOMPOSICAO — {titulo}")
    typer.echo("=" * 72)
    typer.echo(f"  {diag['pregoes']} pregoes | {len(r)} observacoes\n")

    tabelas = {}
    for por, rotulo in (("tipo", "FORMA DO DIA (deslocamento / range)"),
                        ("tamanho", "TAMANHO DO DIA (range)")):
        tabelas[por] = decompor(r, dias, por)
        typer.echo(f"--- {rotulo} ---")
        typer.echo(tabelas[por].to_string(index=False))
        typer.echo("")

    s = resumir(tabelas)
    typer.echo(f"  {s['celulas']} celulas olhadas | "
               f"{s['celulas_extremas']} com |t| >= 1,96 | "
               f"{s['esperadas_por_acaso']} esperadas por acaso")
    typer.echo(f"  chance de ao menos uma extrema sob H0: "
               f"{s['chance_de_ao_menos_uma']}")
    typer.echo(f"  -> {s['leitura']}")
    typer.echo("\n  Os tercis sao do PROPRIO periodo: nao sao limiares")
    typer.echo("  transferiveis. E a forma do dia usa o dia INTEIRO, entao")
    typer.echo("  nao serve para decidir em tempo real -- serve para")
    typer.echo("  EXPLICAR. Se o efeito se concentrar num tipo, a pergunta")
    typer.echo("  seguinte e' se da' para identificar o tipo ANTES.")


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
    arquivo: Path | None = typer.Option(
        None, "--arquivo",
        help="Parquet de features direto, no lugar do caminho derivado de "
             "--features/--symbol. Existe para a barra de TEMPO, que vive em "
             "data/features_tempo/sym=X/tf=Nm/ e nao pode ser alcancada pelo "
             "caminho de barra de volume."),
    horizontes: str | None = typer.Option(
        None, "--horizontes",
        help="Lista separada por virgula (ex.: 1,3 para 5m; 5,15 para 1m). "
             "Omitido usa o padrao 1,3,10. ATENCAO: cada feature x horizonte "
             "e um TRIAL — mudar isto muda o custo estatistico da rodada."),
    trials_previstos: int | None = typer.Option(
        None, "--trials-previstos",
        help="Total contra o qual DEFLACIONAR, para uma hipotese que se "
             "resolve em mais de uma invocacao (ex.: o pre-registro de "
             "2026-08-29e gasta 6 trials no 5m e 6 no 1m, arquivos "
             "separados). Sem isto a rodada que correr primeiro e julgada "
             "contra um total menor. So' endurece: se for menor que o "
             "total real, o real prevalece."),
    promover_por_poder: bool = typer.Option(
        False, "--promover-por-poder",
        help="PRE-REGISTRO 3 (2026-08-29i): celula que passa em MAGNITUDE e "
             "falha SO em ESTABILIDADE, com consistencia de sinal >= 0.85, "
             "sai `inconclusivo` em vez de `descarta` — falhar so na unica "
             "barra que depende do numero de folds e afirmacao sobre PODER, "
             "nao sobre ausencia de efeito. OPT-IN: sem a flag, o veredito e "
             "o classico, identico a todo o historico ja registrado."),
) -> None:
    """
    IC walk-forward das features com veredito deflacionado por trials
    acumulados. Metodo pre-registrado em docs/RESEARCH_PLANO.md.
    """
    from .research.pipeline import rodar

    if arquivo is None:
        arquivo = features / f"sym={symbol.upper()}" / "features.parquet"
    if not arquivo.exists():
        raise SystemExit(f"nao achei {arquivo} — rode `profit-tape features` antes")
    hs = [int(x) for x in horizontes.split(",")] if horizontes else None
    r = rodar(arquivo, saida, horizontes=hs, treino_min=treino_min,
              teste_dias=teste_dias, trials_previstos=trials_previstos,
              promover_por_poder=promover_por_poder)
    typer.echo("=" * 62)
    typer.echo("RESEARCH — IC walk-forward")
    typer.echo("=" * 62)
    for k in ("dias", "folds", "features", "trials_rodada", "trials_acumulados",
              "limiar_deflacionado", "promover_por_poder",
              "segue", "descarta", "inconclusivo"):
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
    raiz_raw: Path = typer.Option(
        Path("data/curated"), "--raiz-raw",
        help="Arvore trade/dt=/sym= a percorrer. Default data/curated "
             "(2026-08-31, decisao do operador): e' a unica arvore que e' ao "
             "mesmo tempo COMPLETA e LIMPA no fluxo real -- data/raw local so' "
             "tem o ultimo dia, e o backup bruto tem backfills entregues duas "
             "vezes (12 de 25 dias com ~2x os negocios; replay sobre ele deu "
             "+3883 contra +6356 no curated, com os 13 dias limpos identicos)."),
    saida_operacoes: Path = typer.Option(
        Path("data/research/operacoes_replay.parquet"), "--saida-operacoes",
        help="Onde persistir TODAS as operacoes do lote, uma linha por "
             "operacao, em ordem cronologica. Input da decomposicao de "
             "drawdown (2026-08-30). Antes disto o replay so' imprimia o "
             "resumo e a lista morria com o processo."),
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
    registros_operacoes: list[dict[str, Any]] = []
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
        for seq, op in enumerate(svc.gestor.historico_detalhado, start=1):
            registros_operacoes.append({
                "dia": dia, "seq_no_dia": seq, "lado": op.lado,
                "preco_entrada": op.preco_entrada, "preco_saida": op.preco_saida,
                "bar_id_entrada": op.bar_id_entrada, "bar_id_saida": op.bar_id_saida,
                "pnl_liquido": op.pnl_liquido, "motivo": op.motivo,
            })
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

    if registros_operacoes:
        import pandas as pd
        saida_operacoes.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(registros_operacoes).to_parquet(saida_operacoes, index=False)
        log.info("ea.replay_lote_operacoes_persistidas",
                 arquivo=str(saida_operacoes), n=len(registros_operacoes))
        typer.echo(f"\noperacoes persistidas: {saida_operacoes} "
                   f"({len(registros_operacoes)} linhas)")

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
    typer.echo(f"\n  FREQUENCIA no limiar de {stop_catastrofico_pontos:.0f} pts:")
    typer.echo(f"    stop no CLOSE (hoje) : {r['n_teria_batido_stop']}"
               f"/{r['n_triggers']} ({r['pct_teria_batido_stop']:.1%})")
    typer.echo(f"    stop CONTINUO (novo) : {r['n_teria_batido_stop_intrabar']}"
               f"/{r['n_triggers']} ({r['pct_teria_batido_stop_intrabar']:.1%})")
    typer.echo(f"  CONFORMIDADE — excesso do close alem do limite: "
               f"media={r['excesso_close_medio']:.1f}  "
               f"mediana={r['excesso_close_mediana']:.1f}  "
               f"max={r['excesso_close_max']:.1f} pts")
    typer.echo("\n  TRES REGIMES (pnl bruto medio/operacao):")
    typer.echo(f"    sem stop      : {r['pnl_medio_sem_stop']:+.1f} pts")
    typer.echo(f"    stop no CLOSE : {r['pnl_medio_stop_close']:+.1f} pts")
    typer.echo(f"    stop CONTINUO : {r['pnl_medio_stop_continuo']:+.1f} pts")
    typer.echo(f"\n  MARGINAIS (so' o continuo mata): n={r['n_marginais']}  "
               f"pnl medio se deixadas correr={r['pnl_marginais_medio']:+.1f}  "
               f"positivas={r['n_marginais_positivas']}"
               f"/{r['n_marginais']} ({r['pct_marginais_positivas']:.1%})")
    typer.echo("\n  por lado (o EA roda VENDA-APENAS — a linha que decide "
               "e' a da venda):")
    for nome, s in (("compra", r["stats_compra"]), ("venda ", r["stats_venda"])):
        typer.echo(f"    {nome}: n={s['n']}  "
                   f"pnl_bruto_medio={s['pnl_bruto_medio']:+.1f}  "
                   f"mae_mediana={s['mae_close_mediana']:.1f}  "
                   f"mfe_mediana={s['mfe_close_mediana']:.1f}  "
                   f"close={s['n_batido_stop']} ({s['pct_batido_stop']:.1%})  "
                   f"continuo={s['n_batido_stop_intrabar']} "
                   f"({s['pct_batido_stop_intrabar']:.1%})  "
                   f"marginais={s['n_marginais']} "
                   f"(positivas: {s['n_marginais_positivas']})")
    typer.echo("\n  TRES REGIMES POR LADO (pnl bruto medio/operacao):")
    for nome, s in (("compra", r["stats_compra"]), ("venda ", r["stats_venda"])):
        typer.echo(f"    {nome}: sem stop={s['pnl_medio_sem_stop']:+.1f}  "
                   f"close={s['pnl_medio_stop_close']:+.1f}  "
                   f"continuo={s['pnl_medio_stop_continuo']:+.1f}  "
                   f"dif pareada={s['dif_pareada_media']:+.2f}  "
                   f"IC95=[{s['ic95_baixo']:+.2f} ; {s['ic95_alto']:+.2f}]  "
                   f"afetadas={s['n_afetadas']}")
    typer.echo("\n" + "=" * 62)
    typer.echo("PRE-REGISTRO (criterio congelado): lado VENDA, IC95 da "
               "diferenca pareada")
    typer.echo(f"  aceita se limite inferior > "
               f"{r['limite_nao_inferioridade']:.1f} pts/op")
    typer.echo(f"  observado: {r['stats_venda']['ic95_baixo']:+.2f}")
    typer.echo(f"  VEREDITO: {r['veredito']}")
    typer.echo("=" * 62)
    typer.echo(f"\nrelatorio: {r['relatorio']}")


@app.command()
def reversao_condicional(
    symbol: str = typer.Option("WINFUT", "--symbol"),
    features: Path = typer.Option(Path("data/features"), "--features"),
    feature: str = typer.Option(..., "--feature", help="ex.: z_agf_3"),
    horizonte: int = typer.Option(..., "--horizonte", help="mesmo h do sinal, ex.: 3"),
    threshold_entrada: float = typer.Option(..., "--threshold-entrada"),
    direcao: str = typer.Option("contrarian", "--direcao"),
    lado: str = typer.Option(
        "venda", "--lado",
        help="venda (o unico com edge confirmado), compra ou ambos."),
    custo_pontos: float = typer.Option(
        11.0, "--custo-pontos",
        help="Deve bater com custo_pontos_estimado do ea.yaml."),
    saida: Path = typer.Option(Path("data/research"), "--saida"),
    treino_min: int = typer.Option(3, "--treino-min"),
    teste_dias: int = typer.Option(2, "--teste-dias"),
    n_bootstrap: int = typer.Option(2000, "--n-bootstrap"),
) -> None:
    """
    Testa a hipotese (b) do PRE-REGISTRO congelado em 2026-08-29: o
    movimento contra a posicao é EVIDENCIA de que o edge expirou, ou so'
    ruido normal que metade das operacoes atravessa antes de pagar?

    Separa duas coisas que a frase "usar stop" mistura: (a) stop como
    LIMITE DE PERDA (nao afirma nada sobre o sinal) vs (b) stop como
    DETECTOR DE REVERSAO. Testa SO' (b).

    NAO consome trial: traducao economica condicional sobre sinal JA'
    validado pelo IC, mesma familia de `mae-analise` e `quintis`.

    A grade de X e o criterio de decisao estao CONGELADOS no pre-registro
    — este comando nao os expoe como opcao de propósito.
    """
    from .research.reversao import analisar_reversao_condicional

    if lado not in ("venda", "compra", "ambos"):
        raise SystemExit(f"--lado invalido: {lado!r} (use venda, compra ou ambos)")
    arquivo = features / f"sym={symbol.upper()}" / "features.parquet"
    if not arquivo.exists():
        raise SystemExit(f"nao achei {arquivo} — rode `profit-tape features` antes")

    r = analisar_reversao_condicional(
        arquivo, feature, horizonte, threshold_entrada, direcao, custo_pontos,
        saida, lado_permitido=lado, treino_min=treino_min,
        teste_dias=teste_dias, n_bootstrap=n_bootstrap)

    typer.echo("=" * 78)
    typer.echo(f"REVERSAO CONDICIONAL — {feature}@h{horizonte} lado={lado}  "
               f"n={r['n_operacoes']} em {r['n_dias']} pregoes")
    typer.echo("=" * 78)
    typer.echo(f"  media INCONDICIONAL (referencia): "
               f"{r['media_incondicional']:+.2f} pts liquidos")
    typer.echo(f"  limiar deflacionado ({len(r['grade_x'])} comparacoes): "
               f"|t| >= {r['limiar_deflacionado']:.3f}\n")
    typer.echo(f"  {'X':>5} {'n toc':>6} {'media toc':>10} {'media nao':>10} "
               f"{'dif':>8} {'t':>7}  situacao")
    for p in r["pontos"]:
        marca = ("SIGNIFICATIVO" if p["significativo"]
                 else (f"n<{r['n_minimo_por_ponto']} (nao interpretado)"
                       if not p["n_suficiente"] else "-"))
        typer.echo(f"  {p['x']:5.0f} {p['n_tocou']:6d} {p['media_tocou']:+10.2f} "
                   f"{p['media_nao_tocou']:+10.2f} {p['diferenca']:+8.2f} "
                   f"{p['t_welch']:7.2f}  {marca}")
    typer.echo(f"\n  VEREDITO: {r['veredito']}")
    typer.echo(f"  {r['justificativa']}")
    typer.echo(f"\nrelatorio: {r['relatorio']}")


@app.command()
def remanescente_apos_toque(
    symbol: str = typer.Option("WINFUT", "--symbol"),
    features: Path = typer.Option(Path("data/features"), "--features"),
    feature: str = typer.Option(..., "--feature", help="ex.: z_agf_3"),
    horizonte: int = typer.Option(..., "--horizonte"),
    threshold_entrada: float = typer.Option(..., "--threshold-entrada"),
    direcao: str = typer.Option("contrarian", "--direcao"),
    lado: str = typer.Option("venda", "--lado"),
    saida: Path = typer.Option(Path("data/research"), "--saida"),
    treino_min: int = typer.Option(3, "--treino-min"),
    teste_dias: int = typer.Option(2, "--teste-dias"),
    n_bootstrap: int = typer.Option(2000, "--n-bootstrap"),
) -> None:
    """
    PRE-REGISTRO 2 (2026-08-29b): no instante em que eu sairia a -X, qual
    a expectativa de CONTINUAR ate' o fim da janela?

    Substitui o estimador ANULADO de `reversao-condicional`. Nao ha'
    custo na conta (bruto de proposito: o giro cancela entre sair e
    segurar) e nao ha' grupo de comparacao (uma amostra contra zero).

    O PORTAO DE HONESTIDADE roda sempre, antes, sobre ruido puro, e sai
    no mesmo relatorio. Se o ruido nao devolver CONTRA (b), o resultado
    real NAO se interpreta.

    NAO consome trial.
    """
    from .research.remanescente import analisar_remanescente

    if lado not in ("venda", "compra", "ambos"):
        raise SystemExit(f"--lado invalido: {lado!r}")
    arquivo = features / f"sym={symbol.upper()}" / "features.parquet"
    if not arquivo.exists():
        raise SystemExit(f"nao achei {arquivo} — rode `profit-tape features` antes")

    r = analisar_remanescente(
        arquivo, feature, horizonte, threshold_entrada, direcao, saida,
        lado_permitido=lado, treino_min=treino_min, teste_dias=teste_dias,
        n_bootstrap=n_bootstrap)

    portao = r["portao"]
    typer.echo("=" * 78)
    typer.echo(f"PORTAO DE HONESTIDADE (ruido puro): "
               f"{'PASSOU' if portao['passou'] else 'REPROVOU'} — "
               f"veredito sobre ruido: {portao['veredito']}")
    typer.echo(f"  amplitude/sd por barra — ruido "
               f"{portao['razao_amplitude_ruido']:.2f} vs real "
               f"{portao['razao_amplitude_real']:.2f}")
    typer.echo("=" * 78)
    if not portao["passou"]:
        typer.echo("  Resultado real abaixo NAO se interpreta.\n")
    typer.echo(f"REMANESCENTE — {feature}@h{horizonte} lado={lado}  "
               f"{r['n_dias']} pregoes")
    typer.echo(f"  {'X':>5} {'n':>6} {'rem PESS':>10} {'t':>7} "
               f"{'rem OTIM':>10} {'t':>7}")
    for p in r["pontos"]:
        if not p["n"]:
            typer.echo(f"  {p['x']:5.0f} {0:6d}   (sem operacao)")
            continue
        typer.echo(f"  {p['x']:5.0f} {p['n']:6d} {p['media_pess']:+10.2f} "
                   f"{p['t_pess']:7.2f} {p['media_otim']:+10.2f} "
                   f"{p['t_otim']:7.2f}")
    typer.echo(f"\n  VEREDITO: {r['veredito']}")
    typer.echo(f"  {r['justificativa']}")
    typer.echo(f"\nrelatorio: {r['relatorio']}")


@app.command()
def decomposicao_drawdown(
    operacoes: Path = typer.Option(
        Path("data/research/operacoes_replay.parquet"), "--operacoes",
        help="Saida de `ea-replay-lote --saida-operacoes`."),
    saida: Path = typer.Option(Path("data/research"), "--saida"),
    n_bootstrap: int = typer.Option(2000, "--n-bootstrap"),
) -> None:
    """
    PRE-VOO da pergunta de drawdown (2026-08-30): de onde vem o drawdown
    maximo -- poucas operacoes grandes, uma sequencia, ou um dia ruim?
    Cada resposta aponta para um mecanismo diferente (stop por operacao /
    circuit breaker / limite diario). Regra 0: fonte antes de numero.

    Descritivo. NAO consome trial. Nao simula nada, nao escolhe numero.
    """
    from .research.decomposicao_drawdown import decompor_drawdown

    if not operacoes.exists():
        raise SystemExit(f"nao achei {operacoes} — rode `ea-replay-lote` "
                         "(ele persiste as operacoes desde v1.45)")
    r = decompor_drawdown(operacoes, saida, n_bootstrap=n_bootstrap)
    jk, bt = r["jackknife"], r["bootstrap"]
    typer.echo("=" * 70)
    typer.echo(f"DECOMPOSICAO DO DRAWDOWN — {r['n_operacoes']} ops, "
               f"{r['n_dias']} pregoes, P&L {r['pnl_total']:+.1f}")
    typer.echo("=" * 70)
    typer.echo(f"  drawdown maximo : {r['drawdown_maximo']:.1f} pts   Calmar {r['calmar']:.2f}")
    typer.echo(f"  jackknife/dia   : [{jk['minimo']:.1f} ; {jk['maximo']:.1f}]")
    typer.echo(f"  bootstrap/dia   : mediana {bt['mediana']:.1f}  "
               f"IC95 [{bt['ic95_baixo']:.1f} ; {bt['ic95_alto']:.1f}]\n")
    typer.echo(f"  {'#':>2} {'prof':>7} {'ops':>4} {'dias':>4} {'OPS':>6} {'DIA':>6} "
               f"{'SEQ':>6}  dominante")
    for i, d in enumerate(r["trechos"], start=1):
        typer.echo(f"  {i:2d} {d['profundidade']:7.1f} {d['n_operacoes']:4d} "
                   f"{d['n_dias']:4d} {d['parcela_operacoes']:6.2f} "
                   f"{d['parcela_dias']:6.2f} {d['parcela_sequencia']:6.2f}  "
                   f"{d['fonte_dominante']}")
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


@app.command("ea-ordem-teste")
def ea_ordem_teste(
    config: Path = typer.Option(Path("config/recorder.yaml"), "--config", "-c"),
    ticker: str = typer.Option("WINFUT", "--ticker"),
    bolsa: str = typer.Option("F", "--bolsa"),
    quantidade: int = typer.Option(1, "--quantidade"),
    zerar_em_seguida: bool = typer.Option(
        True, "--zerar-em-seguida/--sem-zerar",
        help="Zera a posicao logo apos comprar. Default True -- isto e' "
             "teste de conectividade, nao estrategia."),
    usar_conta_real: bool = typer.Option(
        False, "--usar-conta-real",
        help="PERIGO: envia para a conta REAL. Default False (demo). Exige "
             "tambem ROTEAMENTO_ID_ACCOUNT_REAL/ID_CORRETORA_REAL no .env "
             "(ver RoteamentoConfig)."),
    timeout: float = typer.Option(15.0, "--timeout",
                                  help="Segundos esperando conexao e corretora pronta."),
    log_level: str = typer.Option("INFO", "--log-level"),
) -> None:
    """
    E2 da trilha de execucao (2026-09-10): primeira ordem de teste real.
    Compra a mercado (default 1 lote WINFUT demo) e zera em seguida.

    RESTRICAO DE UMA CONEXAO SO' (documentada desde o E1): com uma unica
    chave de ativacao, so' existe UMA conexao com a DLL possivel. Este
    comando conecta sozinho, com login_completo=True -- NAO rode com o
    `record` de producao ativo ao mesmo tempo. Pare o record primeiro.

    Camadas de protecao ja' embutidas no ExecutorDeOrdens (ver
    ea/execucao.py): conta real exige --usar-conta-real explicito E as
    variaveis _REAL no .env; corretora e conta viajam sempre juntas
    (conta_para()); construcao falha cedo sem ROTEAMENTO_SENHA_ROTEAMENTO.
    """
    configurar(log_level, None)
    from .ea.config import RoteamentoConfig
    from .ea.decisao import Acao, Decisao
    from .ea.execucao import ExecutorDeOrdens
    from .pipeline.bus import EventBus
    from .profitdll.client import ProfitClient

    cfg = RecorderConfig.from_yaml(config)
    cred = Credenciais()
    roteamento = RoteamentoConfig()

    if usar_conta_real and not typer.confirm(
        "Isto envia uma ordem REAL, com dinheiro de verdade. Confirma?"
    ):
        raise typer.Exit(1)

    client = ProfitClient(
        dll_path=cred.dll_path, activation_key=cred.activation_key,
        user=cred.user, password=cred.password, bus=EventBus(),
        tz_offset_horas=cfg.runtime.tz_offset_horas, login_completo=True,
    )
    typer.echo("Conectando (login completo)...")
    client.connect(timeout_s=timeout)
    if not client.conectado_market:
        typer.echo("ERRO: mercado nao conectou no prazo.")
        raise typer.Exit(1)
    # A CHECAGEM QUE DECIDE (ver EA_ARQUITETURA.md, evento real de 09/09):
    # corretora_pronta caiu e voltou sozinha durante uma queda de rede de
    # ~83s -- e' o estado REAL no momento do envio que importa, nao "ja'
    # vimos o 5 alguma vez". Se nao estiver pronta agora, nao envia.
    if not client.corretora_pronta:
        typer.echo("ERRO: corretora nao ficou pronta -- sem sessao de "
                   "roteamento, nao envio ordem.")
        client.disconnect()
        raise typer.Exit(1)

    executor = ExecutorDeOrdens(client._dll, roteamento, ticker=ticker,
                                bolsa=bolsa, quantidade=quantidade,
                                usar_conta_real=usar_conta_real)

    typer.echo(f"Enviando compra a mercado: {quantidade}x {ticker} "
              f"({'REAL' if usar_conta_real else 'DEMO'})")
    r1 = executor.executar(Decisao(Acao.COMPRAR, "E2: teste manual de conectividade",
                                   0.0, "manual"))
    typer.echo(f"  enviada={r1.enviada} ordem_id={r1.ordem_id} motivo={r1.motivo}")

    if r1.enviada and zerar_em_seguida:
        time.sleep(2.0)   # da' tempo do fill chegar antes de zerar
        typer.echo("Zerando posicao...")
        r2 = executor.executar(Decisao(Acao.ZERAR, "E2: zeragem automatica do teste",
                                       0.0, "manual"))
        typer.echo(f"  enviada={r2.enviada} ordem_id={r2.ordem_id} motivo={r2.motivo}")

    client.disconnect()


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
