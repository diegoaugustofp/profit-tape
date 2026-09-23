"""
diagnostico_historico.py -- baixa historico da ProfitDLL e salva no
MESMO padrao do backfill do projeto (raw/trade/dt=.../sym=.../part-NNNN.parquet),
para entrar direto no `profit-tape curate` depois.

Script AUTOCONTIDO no sentido de nao importar o pacote profittape (para
poder ser lido e compartilhado sozinho se um dia for preciso de novo com
a Nelogica). Usa ctypes (padrao) + pyarrow (a mesma biblioteca que o
projeto usa para gravar; se nao estiver instalada, `pip install pyarrow`).

HISTORICO DESTE SCRIPT
-----------------------
Nasceu em 2026-09-10 para investigar por que o backfill do projeto vinha
vazio. Achados, na ordem: (1) GetHistoryTrades exige data COM HORA
("DD/MM/YYYY HH:mm:SS"), so' data vira janela vazia; (2) a DLL 4.0.0.4x
exige SubscribeTicker antes; (3) a 1a chamada de historico de um ticker
NA SESSAO vem TRUNCADA -- so' a cauda do periodo (medido: 102.400
negocios de 17:29-18:31 de um dia com 6,1 milhoes) -- uma chamada de
PRIMING, descartada, resolve. As tres causas ja' estao corrigidas no
backfill do projeto (`profit-tape backfill`); este script replica o
mesmo desenho de forma standalone.

MODOS
-----
--modo salvar (default): assina -> prima (descarta) -> baixa e SALVA
    cada dia pedido, no layout do backfill. E' o modo de uso normal.
--modo diagnostico: o comportamento exploratorio original (varias
    combinacoes de formato/ticker, sem salvar nada) -- para
    investigar um problema novo, nao para uso rotineiro.

Uso:
    python diagnostico_historico.py --de 02/09/2026 --ate 03/09/2026
    python diagnostico_historico.py --ticker WINFUT --saida-raiz data/raw
    python diagnostico_historico.py --modo diagnostico --de 31/08/2026 --ate 31/08/2026
"""

from __future__ import annotations

import argparse
import ctypes
import os
import sys
import threading
import time
from ctypes import (
    Structure,
    WINFUNCTYPE,
    c_char,
    c_double,
    c_int,
    c_int64,
    c_uint,
    c_void_p,
    c_wchar_p,
)
from datetime import datetime, timedelta
from pathlib import Path

# --------------------------------------------------------------------------
# log
# --------------------------------------------------------------------------
_T0 = time.monotonic()
_ARQ = open(f"diagnostico_historico_{datetime.now():%Y%m%d_%H%M%S}.log", "w",
            encoding="utf-8")
_LOCK = threading.Lock()


def log(msg: str) -> None:
    linha = f"{datetime.now():%H:%M:%S.%f}"[:-3] + f" +{time.monotonic() - _T0:8.3f}s  {msg}"
    with _LOCK:
        print(linha, flush=True)
        _ARQ.write(linha + "\n")
        _ARQ.flush()


# --------------------------------------------------------------------------
# .env (leitura minima, sem dependencia)
# --------------------------------------------------------------------------
def ler_env(caminho: str = ".env") -> dict[str, str]:
    env: dict[str, str] = {}
    if os.path.exists(caminho):
        for linha in open(caminho, encoding="utf-8"):
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            k, v = linha.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("PROFIT_ACTIVATION_KEY", "PROFIT_USER", "PROFIT_PASSWORD", "PROFIT_DLL_PATH"):
        if k in os.environ:
            env[k] = os.environ[k]
    return env


def mascarar(s: str) -> str:
    return (s[:2] + "*" * max(len(s) - 2, 0)) if s else "(vazio)"


# --------------------------------------------------------------------------
# timestamp -- MESMO algoritmo de profitdll/timeparse.py, copiado (script
# standalone: nao importa o pacote). "DD/MM/YYYY HH:MM:SS.mmm" -> epoch ns
# UTC, DLL entrega horario local (-03:00, sem horario de verao desde 2019).
# --------------------------------------------------------------------------
def _dias_desde_epoch(ano: int, mes: int, dia: int) -> int:
    y = ano - (1 if mes <= 2 else 0)
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    m_shift = mes + (-3 if mes > 2 else 9)
    doy = (153 * m_shift + 2) // 5 + dia - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def parse_ts_ns(s: str | None, offset_horas: int = -3) -> int:
    if not s or len(s) < 19:
        return 0
    try:
        dia, mes, ano = int(s[0:2]), int(s[3:5]), int(s[6:10])
        hora, minuto, seg = int(s[11:13]), int(s[14:16]), int(s[17:19])
        ms = int(s[20:23]) if len(s) >= 23 and s[19] == "." else 0
    except (ValueError, IndexError):
        return 0
    dias = _dias_desde_epoch(ano, mes, dia)
    segundos = dias * 86_400 + (hora - offset_horas) * 3_600 + minuto * 60 + seg
    return segundos * 1_000_000_000 + ms * 1_000_000


# --------------------------------------------------------------------------
# tipos da DLL (identicos aos usados em producao pelo projeto)
# --------------------------------------------------------------------------
class TAssetIDRec(Structure):
    _fields_ = (("ticker", c_wchar_p), ("bolsa", c_wchar_p), ("feed", c_int))


TStateCallback = WINFUNCTYPE(None, c_int, c_int)
TNewTradeCallback = WINFUNCTYPE(None, TAssetIDRec, c_wchar_p, c_uint, c_double, c_double,
                                c_int, c_int, c_int, c_int, c_char)
TNewDailyCallback = WINFUNCTYPE(None, TAssetIDRec, c_wchar_p,
                                c_double, c_double, c_double, c_double,
                                c_double, c_double, c_double, c_double,
                                c_double, c_double,
                                c_int, c_int, c_int, c_int, c_int, c_int)
TPriceBookCallbackV1 = WINFUNCTYPE(None, TAssetIDRec, c_int, c_int, c_int, c_int, c_int,
                                   c_double, c_void_p, c_void_p)
TOfferBookCallbackV1 = WINFUNCTYPE(None, TAssetIDRec, c_int, c_int, c_int, c_int, c_int,
                                   c_int64, c_double, c_char, c_char, c_char, c_char, c_char,
                                   c_wchar_p, c_void_p, c_void_p)
THistoryTradeCallback = WINFUNCTYPE(None, TAssetIDRec, c_wchar_p, c_uint, c_double,
                                    c_double, c_int, c_int, c_int, c_int)
TProgressCallback = WINFUNCTYPE(None, TAssetIDRec, c_int)
TTinyBookCallback = WINFUNCTYPE(None, TAssetIDRec, c_double, c_int, c_int)

_ESTADOS = {0: "LOGIN", 1: "ROTEAMENTO", 2: "MARKET_DATA", 3: "ATIVACAO"}
_NL_BASE = -2147483648
_NL = {
    -2147483647: "NL_INTERNAL_ERROR", -2147483646: "NL_NOT_INITIALIZED (login nao efetuado)",
    -2147483645: "NL_INVALID_ARGS / login invalido", -2147483644: "NL_ALREADY_INITIALIZED",
    -2147483643: "ticker invalido", -2147483642: "sem permissao para o ativo",
    -2147483640: "falta parametro obrigatorio", -2147483639: "parametro invalido",
    -2147483637: "DLL nao inicializada",
    -2147483602: "NL_HISTORY_PERIOD_LIMIT (data inicial > 30 dias ou intervalo > 10 dias)",
}


def descrever(code: int) -> str:
    if code == 0:
        return "0 = NL_OK"
    nome = _NL.get(code, "codigo nao tabelado")
    return f"{code} (hex {code & 0xFFFFFFFF:#010x}, NL base+{code - _NL_BASE}) = {nome}"


def versao_dll(caminho: str) -> str:
    try:
        ver = ctypes.windll.version
        tam = ver.GetFileVersionInfoSizeW(caminho, None)
        buf = ctypes.create_string_buffer(tam)
        ver.GetFileVersionInfoW(caminho, 0, tam, buf)
        ptr, n = ctypes.c_void_p(), ctypes.c_uint()
        ver.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(n))
        ffi = (ctypes.c_uint32 * (n.value // 4)).from_address(ptr.value)
        ms, ls = ffi[2], ffi[3]
        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
    except Exception as e:  # noqa: BLE001
        return f"desconhecida ({e!r})"


# --------------------------------------------------------------------------
# estado compartilhado com os callbacks
#
# Regra do projeto (client.py): NENHUM callback faz I/O ou trabalho alem de
# montar a tupla e guardar. Quem grava em disco e' sempre a thread
# principal, depois que a chamada termina.
# --------------------------------------------------------------------------
class Estado:
    def __init__(self) -> None:
        self.market_ok = threading.Event()
        self.login_ok = threading.Event()
        self.progresso: dict[str, list[int]] = {}
        self.progresso_100 = threading.Event()
        self.trades_tempo_real = 0
        # Buffer da chamada de historico EM ANDAMENTO. `gravando=False`
        # durante o priming: os negocios chegam (a DLL nao tem como saber
        # que vamos descartar) mas o callback nao os guarda -- e' o mesmo
        # mecanismo do `_descartar_historico` no client.py do projeto.
        self.gravando = False
        self.buffer: list[tuple[str, int, float, float, int, int, int, int]] = []
        # so' para o modo diagnostico (contagem por data, sem salvar)
        self.hist_diag: list[tuple[str, int, float, int]] = []
        self.hist_por_dia: dict[str, int] = {}


E = Estado()


@TStateCallback
def cb_state(tipo: int, valor: int) -> None:
    log(f"CALLBACK state: tipo={tipo} ({_ESTADOS.get(tipo, '?')}) valor={valor}")
    if tipo == 0 and valor == 0:
        E.login_ok.set()
    if tipo == 2 and valor in (2, 3, 4):
        E.market_ok.set()


@TNewTradeCallback
def cb_trade(ativo, data, num, preco, vol, qtd, ac, av, tipo, edit) -> None:
    E.trades_tempo_real += 1


@TNewDailyCallback
def cb_daily(*_: object) -> None:
    return


@TPriceBookCallbackV1
def cb_price(*_: object) -> None:
    return


@TOfferBookCallbackV1
def cb_offer(*_: object) -> None:
    return


@TTinyBookCallback
def cb_tiny(*_: object) -> None:
    return


@THistoryTradeCallback
def cb_hist(ativo, data, num, preco, vol, qtd, ac, av, tipo) -> None:
    if E.gravando:
        E.buffer.append((str(data or ""), int(num), float(preco), float(vol),
                         int(qtd), int(ac), int(av), int(tipo)))
    # modo diagnostico: contagem por data, independente de `gravando`
    d = str(data or "")
    E.hist_por_dia[d[:10]] = E.hist_por_dia.get(d[:10], 0) + 1
    if len(E.hist_diag) < 5:
        log(f"CALLBACK history #{len(E.hist_diag) + 1}: ticker={ativo.ticker} "
            f"data={d} num={num} preco={preco} qtd={qtd} tipo={tipo}")
    E.hist_diag.append((d, int(num), float(preco), int(qtd)))


@TProgressCallback
def cb_progress(ativo, pct) -> None:
    E.progresso.setdefault(str(ativo.ticker or ""), []).append(int(pct))
    log(f"CALLBACK progress: ticker={ativo.ticker} progresso={pct}")
    if int(pct) >= 100:
        E.progresso_100.set()


# --------------------------------------------------------------------------
# gravacao no padrao do backfill (storage/parquet_sink.py + domain/schema.py)
# --------------------------------------------------------------------------
def salvar_parquet(raiz: Path, dia: str, ticker: str, bolsa: str,
                   registros: list[tuple[str, int, float, float, int, int, int, int]],
                   tz_offset_horas: int = -3) -> Path | None:
    """
    `raiz`/trade/dt=<dia>/sym=<ticker>/part-NNNN.parquet -- MESMO layout,
    schema e escrita atomica (.inprogress + rename) do
    `storage/parquet_sink.py` do projeto. Devolve o caminho final, ou
    None se `registros` vier vazio (nao cria particao vazia -- o
    proprio backfill tambem nao cria).
    """
    if not registros:
        return None
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise SystemExit(
            "pyarrow nao esta' instalado (precisa para salvar no padrao do "
            "backfill). `pip install pyarrow`, ou rode com --modo diagnostico "
            "para so' investigar, sem salvar."
        ) from exc

    sym = pa.dictionary(pa.int16(), pa.string())
    schema = pa.schema([
        pa.field("ts_ns", pa.int64(), nullable=False),
        pa.field("ts_recv_ns", pa.int64(), nullable=False),
        pa.field("symbol", sym, nullable=False),
        pa.field("exchange", sym, nullable=False),
        pa.field("trade_id", pa.int64()),
        pa.field("price", pa.float64()),
        pa.field("volume_financeiro", pa.float64()),
        pa.field("quantidade", pa.int64()),
        pa.field("agente_comprador", pa.int32()),
        pa.field("agente_vendedor", pa.int32()),
        pa.field("trade_type", pa.int16()),
        pa.field("is_edit", pa.bool_()),
    ])
    ts_recv = time.time_ns()
    cols: dict[str, list] = {
        "ts_ns": [], "ts_recv_ns": [], "symbol": [], "exchange": [], "trade_id": [],
        "price": [], "volume_financeiro": [], "quantidade": [], "agente_comprador": [],
        "agente_vendedor": [], "trade_type": [], "is_edit": [],
    }
    for data_str, num, preco, vol, qtd, ac, av, tipo in registros:
        cols["ts_ns"].append(parse_ts_ns(data_str, tz_offset_horas))
        cols["ts_recv_ns"].append(ts_recv)
        cols["symbol"].append(ticker)
        cols["exchange"].append(bolsa)
        cols["trade_id"].append(num)
        cols["price"].append(preco)
        cols["volume_financeiro"].append(vol)
        cols["quantidade"].append(qtd)
        cols["agente_comprador"].append(ac)
        cols["agente_vendedor"].append(av)
        cols["trade_type"].append(tipo)
        cols["is_edit"].append(False)   # historico nao carrega flag de edicao
    tabela = pa.table(cols, schema=schema)

    pasta = raiz / "trade" / f"dt={dia}" / f"sym={ticker}"
    pasta.mkdir(parents=True, exist_ok=True)
    # proximo indice livre olhando o disco (mesma regra do ParquetSink:
    # numeracao pertence ao diretorio, nao ao processo)
    usados = []
    for arq in pasta.glob("part-*.parquet*"):
        try:
            usados.append(int(arq.name.split("-")[1].split(".")[0]))
        except (IndexError, ValueError):
            continue
    seq = max(usados) + 1 if usados else 0
    final = pasta / f"part-{seq:04d}.parquet"
    tmp = pasta / f"part-{seq:04d}.parquet.inprogress"
    pq.write_table(tabela, tmp, compression="zstd", compression_level=3,
                   write_statistics=True)
    with open(tmp, "rb+") as fh:
        fh.flush()
        os.fsync(fh.fileno())
    tmp.rename(final)
    log(f"salvo: {final} ({len(registros)} negocios)")
    return final


# --------------------------------------------------------------------------
def dias_uteis(de: datetime, ate: datetime) -> list[datetime]:
    d, out = de, []
    while d <= ate:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def esperar_download(ocioso_s: float = 10.0, max_s: float = 300.0) -> str:
    """
    Dois tempos, como a DLL trabalha (medido 2026-09-10/11): baixa
    primeiro (progresso sobe ate' 99 e fica la' por MINUTOS num dia cheio
    de WIN -- nesse periodo nao chega negocio nenhum) e entrega depois.
    Espera progresso==100 (ate' `max_s`) E DEPOIS o fim da entrega
    (`ocioso_s` sem nenhum callback de historico).
    """
    n_antes = len(E.hist_diag)
    chegou = E.progresso_100.wait(max_s)
    if not chegou:
        log(f"AVISO: progresso nao chegou a 100 em {max_s}s")
    ultimo = time.monotonic()
    n_visto = len(E.hist_diag)
    ini = time.monotonic()
    while True:
        time.sleep(0.3)
        if len(E.hist_diag) != n_visto:
            n_visto = len(E.hist_diag)
            ultimo = time.monotonic()
        if time.monotonic() - ultimo > ocioso_s:
            break
        if time.monotonic() - ini > max_s + 120:
            log("AVISO: entrega nao terminou; seguindo")
            return "timeout_entrega"
    if len(E.hist_diag) == n_antes:
        return "sem_negocios" if chegou else "sem_progresso_100"
    return "ok" if chegou else "negocios_sem_progresso_100"


def preparar_dll(dll_path: str, chave: str, user: str, senha: str, timeout_s: float) -> object:
    log(f"dll_path={dll_path} existe={os.path.exists(dll_path)} versao={versao_dll(dll_path)}")
    log(f"credenciais: key={mascarar(chave)} user={mascarar(user)} senha={mascarar(senha)}")
    dll = ctypes.WinDLL(dll_path)
    dll.DLLInitializeMarketLogin.argtypes = [
        c_wchar_p, c_wchar_p, c_wchar_p, TStateCallback, TNewTradeCallback,
        TNewDailyCallback, TPriceBookCallbackV1, TOfferBookCallbackV1,
        THistoryTradeCallback, TProgressCallback, TTinyBookCallback]
    dll.DLLInitializeMarketLogin.restype = c_int
    dll.GetHistoryTrades.argtypes = [c_wchar_p, c_wchar_p, c_wchar_p, c_wchar_p]
    dll.GetHistoryTrades.restype = c_int
    dll.SubscribeTicker.argtypes = [c_wchar_p, c_wchar_p]
    dll.SubscribeTicker.restype = c_int
    dll.DLLFinalize.restype = c_int
    log("chamando DLLInitializeMarketLogin...")
    ret = dll.DLLInitializeMarketLogin(chave, user, senha, cb_state, cb_trade, cb_daily,
                                       cb_price, cb_offer, cb_hist, cb_progress, cb_tiny)
    log(f"DLLInitializeMarketLogin retornou {descrever(ret)}")
    if ret < 0:
        raise SystemExit("login falhou -- ver retorno acima")
    log(f"esperando MARKET_DATA conectado (ate' {timeout_s}s)...")
    if not E.market_ok.wait(timeout_s):
        dll.DLLFinalize()
        raise SystemExit(f"market data nao conectou (login_ok={E.login_ok.is_set()})")
    log(f"conectado: login_ok={E.login_ok.is_set()} market_ok=True")
    time.sleep(1.0)
    return dll


def primar(dll: object, ticker: str, bolsa: str, dia_amostra: datetime) -> None:
    """Uma chamada de GetHistoryTrades DESCARTADA -- a 1a chamada de
    historico de um ticker na sessao vem truncada (so' a cauda do
    periodo). Ver o cabecalho do arquivo."""
    ini = fim = f"{dia_amostra:%d/%m/%Y}"
    ini, fim = f"{ini} 09:00:00", f"{fim} 18:35:00"
    log(f"--- PRIMING (descartado) GetHistoryTrades({ticker!r}, {bolsa!r}, {ini!r}, {fim!r}) ---")
    E.gravando = False
    E.progresso_100.clear()
    r = dll.GetHistoryTrades(ticker, bolsa, ini, fim)
    log(f"priming retornou {descrever(r)}")
    resultado = esperar_download()
    log(f"priming concluido: {resultado}")


def baixar_e_salvar(dll: object, ticker: str, bolsa: str, dia: datetime,
                    raiz: Path) -> None:
    s = f"{dia:%d/%m/%Y}"
    ini, fim = f"{s} 09:00:00", f"{s} 18:35:00"
    log(f"--- GetHistoryTrades({ticker!r}, {bolsa!r}, {ini!r}, {fim!r}) ---")
    E.buffer = []
    E.gravando = True
    E.progresso_100.clear()
    t = time.monotonic()
    r = dll.GetHistoryTrades(ticker, bolsa, ini, fim)
    log(f"GetHistoryTrades retornou {descrever(r)} em {(time.monotonic() - t) * 1000:.1f} ms")
    resultado = esperar_download()
    E.gravando = False
    n = len(E.buffer)
    log(f"RESULTADO {s}: negocios={n} terminou_por={resultado}")
    if n == 0:
        log(f"AVISO: {s} sem nenhum negocio -- particao NAO criada "
            "(feriado? fora da janela de 30 dias? servidor sem o dia?)")
        return
    caminho = salvar_parquet(raiz, f"{dia:%Y-%m-%d}", ticker, bolsa, E.buffer)
    log(f"dia {s} -> {caminho}")


# --------------------------------------------------------------------------
def modo_salvar(dll: object, args: argparse.Namespace) -> None:
    de = datetime.strptime(args.de, "%d/%m/%Y")
    ate = datetime.strptime(args.ate, "%d/%m/%Y")
    dias = dias_uteis(de, ate)
    log(f"modo SALVAR: {args.ticker} de {args.de} a {args.ate} ({len(dias)} "
        f"dia(s) uteis) -> {args.saida_raiz}")
    r = dll.SubscribeTicker(args.ticker, args.bolsa)
    log(f"SubscribeTicker({args.ticker},{args.bolsa}) retornou {descrever(r)}")
    time.sleep(1.0)
    primar(dll, args.ticker, args.bolsa, dias[0])
    raiz = Path(args.saida_raiz)
    for dia in dias:
        baixar_e_salvar(dll, args.ticker, args.bolsa, dia, raiz)
    log("=" * 70)
    log(f"CONCLUIDO. Proximo passo: profit-tape curate --de {args.de[6:]}-"
        f"{args.de[3:5]}-{args.de[0:2]} --ate {args.ate[6:]}-{args.ate[3:5]}-"
        f"{args.ate[0:2]} (raiz={raiz})")


def modo_diagnostico(dll: object, args: argparse.Namespace) -> None:
    """Comportamento exploratorio original: varias combinacoes de
    formato/ticker, NADA e' salvo. Use so' para investigar um problema
    novo (ex.: outro simbolo, outra bolsa)."""
    de = datetime.strptime(args.de, "%d/%m/%Y")
    ate = datetime.strptime(args.ate, "%d/%m/%Y")
    hoje = datetime.now()
    log(f"modo DIAGNOSTICO (nada e' salvo). hoje={hoje:%d/%m/%Y}; limite de "
        f"30 dias corridos = {(hoje - timedelta(days=30)):%d/%m/%Y}; limite "
        "por requisicao = 10 dias")
    tickers = [args.ticker, *args.tickers_extras]
    formatos = [("so_data", lambda d: (f"{d:%d/%m/%Y}", f"{d:%d/%m/%Y}")),
                ("data_e_hora", lambda d: (f"{d:%d/%m/%Y} 09:00:00", f"{d:%d/%m/%Y} 18:35:00"))]

    def chamar(ticker: str, rotulo: str, ini: str, fim: str) -> None:
        E.gravando = False
        E.progresso_100.clear()
        antes = E.hist_por_dia.copy()
        log(f"--- [{rotulo}] GetHistoryTrades({ticker!r}, {args.bolsa!r}, {ini!r}, {fim!r}) ---")
        t = time.monotonic()
        r = dll.GetHistoryTrades(ticker, args.bolsa, ini, fim)
        log(f"GetHistoryTrades retornou {descrever(r)} em {(time.monotonic() - t) * 1000:.1f} ms")
        fim_por = esperar_download()
        por_data = {d: c - antes.get(d, 0) for d, c in E.hist_por_dia.items() if c - antes.get(d, 0)}
        log(f"RESULTADO [{rotulo}] por_data_do_negocio={por_data} terminou_por={fim_por}")

    for ticker in tickers:
        r = dll.SubscribeTicker(ticker, args.bolsa)
        log(f"SubscribeTicker({ticker},{args.bolsa}) retornou {descrever(r)}")
        time.sleep(1.0)
        for i, dia in enumerate(dias_uteis(de, ate)):
            for nome_fmt, fmt in formatos:
                if nome_fmt == "so_data" and i > 0:
                    continue
                ini, fim = fmt(dia)
                chamar(ticker, f"{ticker} {dia:%d/%m} {nome_fmt}", ini, fim)
    log(f"trades em TEMPO REAL recebidos durante o teste: {E.trades_tempo_real}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modo", choices=["salvar", "diagnostico"], default="salvar")
    ap.add_argument("--ticker", default="WINFUT")
    ap.add_argument("--bolsa", default="F")
    ap.add_argument("--de", default="31/08/2026")
    ap.add_argument("--ate", default="03/09/2026")
    ap.add_argument("--saida-raiz", default="data/raw",
                    help="Raiz do storage, no padrao do backfill (default: data/raw)")
    ap.add_argument("--tickers-extras", nargs="*", default=[],
                    help="So' no --modo diagnostico: contratos adicionais a testar")
    ap.add_argument("--timeout-conexao", type=float, default=30.0)
    args = ap.parse_args()

    env = ler_env()
    chave, user, senha = (env.get("PROFIT_ACTIVATION_KEY", ""), env.get("PROFIT_USER", ""),
                          env.get("PROFIT_PASSWORD", ""))
    dll_path = env.get("PROFIT_DLL_PATH", r"C:\Profit\ProfitDLL64.dll")
    log(f"python={sys.version.split()[0]} plataforma={sys.platform} modo={args.modo}")
    if not (chave and user and senha):
        log("ERRO: credenciais ausentes no .env")
        return 2

    dll = preparar_dll(dll_path, chave, user, senha, args.timeout_conexao)
    try:
        if args.modo == "salvar":
            modo_salvar(dll, args)
        else:
            modo_diagnostico(dll, args)
    finally:
        ret = dll.DLLFinalize()
        log(f"DLLFinalize retornou {ret}")
        log(f"log gravado em {_ARQ.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
