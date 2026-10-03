"""INVENTARIO DE DADOS (v4.22): o que existe em disco, por ativo, antes de formular uma hipotese.

Sob demanda, NAO diario: `profit-tape inventario-dados` escreve `docs/INVENTARIO_DADOS.md` (e um
CSV), que fica versionado e a mao para saber de antemao quanto dado e qual periodo ha' por ativo.

Le so' o RODAPE dos parquet (numero de linhas e min/max de `ts_recv_ns`): nao carrega dado.
Layout do sink: `<raiz>/<stream>/dt=AAAA-MM-DD/sym=<ATIVO>/part-NNNN.parquet`.

Vocabulario (docs/GLOSSARIO.md): *tape* = negocios com agente agressor e passivo (o stream `trade`);
book = `book_offer`, `book_price`, `tiny_book`. "So' trade" = o ativo tem o stream trade e nenhum de
book. Origem do dia: AO VIVO (capturado no pregao), IMPORTADO (historico recuperado depois: 01 a
14/09 foram importados em 15/09) ou MISTO."""

from __future__ import annotations

import datetime as dt
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow.parquet as pq

_TZ = ZoneInfo("America/Sao_Paulo")
_NS = 1_000_000_000
STREAMS_BOOK = ("book_offer", "book_price", "tiny_book")
GRACA_AO_VIVO_S = 3600          # recv ate' 1 h depois da meia-noite do dia ainda e' "ao vivo"
COLUNAS = ["camada", "stream", "ativo", "dia", "arquivos", "bytes", "linhas", "recv_min",
           "recv_max", "origem", "ilegiveis"]


def _rodape(arq: Path) -> tuple[int, int | None, int | None]:
    """(linhas, min(ts_recv_ns), max(ts_recv_ns)) pelo rodape; None sem estatistica."""
    md = pq.ParquetFile(arq).metadata
    nomes = md.schema.names
    lo = hi = None
    if "ts_recv_ns" in nomes:
        j = nomes.index("ts_recv_ns")
        for g in range(md.num_row_groups):
            st = md.row_group(g).column(j).statistics
            if st is None or not st.has_min_max:
                lo = hi = None
                break
            lo = st.min if lo is None else min(lo, st.min)
            hi = st.max if hi is None else max(hi, st.max)
    return int(md.num_rows), (None if lo is None else int(lo)), (None if hi is None else int(hi))


def classificar_origem(dia: dt.date, recv_min: int | None, recv_max: int | None) -> str:
    """ao_vivo / importado / misto / desconhecido: `ts_recv_ns` contra o fim do dia."""
    if recv_min is None or recv_max is None:
        return "desconhecido"
    fim = int(dt.datetime(dia.year, dia.month, dia.day, tzinfo=_TZ).timestamp()) * _NS \
        + 86400 * _NS
    if recv_max - fim <= GRACA_AO_VIVO_S * _NS:
        return "ao_vivo"
    return "importado" if recv_min >= fim else "misto"


def _dia_de(pasta: Path) -> dt.date | None:
    m = re.fullmatch(r"dt=(\d{4}-\d{2}-\d{2})", pasta.name)
    return dt.date.fromisoformat(m.group(1)) if m else None


def _dia_ativo(args: tuple[str, str, str, dt.date, Path, bool]) -> dict[str, Any]:
    camada, stream, ativo, dia, pasta, linhas = args
    arqs = sorted(pasta.glob("part-*.parquet"))            # ignora .inprogress e lixo
    row: dict[str, Any] = {"camada": camada, "stream": stream, "ativo": ativo, "dia": dia,
                           "arquivos": len(arqs), "bytes": sum(a.stat().st_size for a in arqs),
                           "linhas": None, "recv_min": None, "recv_max": None,
                           "origem": "desconhecido", "ilegiveis": 0}
    if not linhas:
        return row
    n, lo, hi, ok_stats = 0, None, None, True
    for a in arqs:
        try:
            nn, l1, h1 = _rodape(a)
        except Exception:                    # parquet sem footer / corrompido
            row["ilegiveis"] += 1
            continue
        n += nn
        if l1 is None or h1 is None:
            ok_stats = False
        else:
            lo = l1 if lo is None else min(lo, l1)
            hi = h1 if hi is None else max(hi, h1)
    row["linhas"] = n
    if ok_stats and lo is not None:
        row["recv_min"], row["recv_max"] = lo, hi
        row["origem"] = classificar_origem(dia, lo, hi)
    return row


def escanear(raizes: dict[str, Path], contar_linhas: bool = True, threads: int = 8) -> pd.DataFrame:
    """Uma linha por (camada, stream, ativo, dia). Camada ausente e' ignorada."""
    tarefas: list[tuple[str, str, str, dt.date, Path, bool]] = []
    for camada, raiz in raizes.items():
        if not raiz.exists():
            continue
        streams = [p for p in raiz.iterdir() if p.is_dir() and not p.name.startswith("_")]
        for stream in sorted(streams):
            for pdia in sorted(stream.glob("dt=*")):
                dia = _dia_de(pdia)
                if dia is None:
                    continue
                for pativo in sorted(pdia.glob("sym=*")):
                    tarefas.append((camada, stream.name, pativo.name[4:], dia, pativo,
                                    contar_linhas))
    if not tarefas:
        return pd.DataFrame(columns=COLUNAS)
    with ThreadPoolExecutor(max_workers=max(1, threads)) as ex:
        linhas = list(ex.map(_dia_ativo, tarefas))
    return pd.DataFrame(linhas, columns=COLUNAS)


# ------------------------------------------------------------------ agregados
def familia(ativo: str) -> str:
    op = re.fullmatch(r"([A-Z]{4})[A-X]\d{2,3}", ativo)      # PETRJ49, PETRV494, VALEJ80...
    if op:
        return f"opcao {op.group(1)}"
    if re.fullmatch(r"W(IN|DO)[A-Z]\d{2}", ativo):
        return "futuro (contrato)"
    if re.fullmatch(r"W(IN|DO)FUT|IND[A-Z0-9]+|DOL[A-Z0-9]+", ativo):
        return "futuro (serie continua)"
    if re.fullmatch(r"[A-Z]{4}\d{1,2}", ativo):
        return "acao"
    return "outro"


def dias_uteis_sem_dado(dias: set[dt.date]) -> list[dt.date]:
    """Dias da semana entre o primeiro e o ultimo dia com dado que NAO tem dado (pode incluir
    feriado: o inventario nao conhece o calendario da B3)."""
    if not dias:
        return []
    d, fim, out = min(dias), max(dias), []
    while d <= fim:
        if d.weekday() < 5 and d not in dias:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def por_ativo(df: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por ativo: periodo e dias do trade (uniao das camadas), linhas por dia (a maior
    entre as camadas, que guardam o MESMO dia), streams de book, origem, camadas, lacunas."""
    linhas: list[dict[str, Any]] = []
    for ativo, g in df.groupby("ativo"):
        t = g[g["stream"] == "trade"]
        b = g[g["stream"].isin(STREAMS_BOOK)]
        dias_t = set(t["dia"])
        por_dia = t.groupby("dia")["linhas"].max() if len(t) else pd.Series(dtype=float)
        orig = t.sort_values("camada").drop_duplicates("dia")["origem"].value_counts().to_dict() \
            if len(t) else {}
        streams = sorted(set(g["stream"]))
        linhas.append({
            "ativo": ativo, "familia": familia(str(ativo)),
            "tipo": ("trade + book" if len(t) and len(b) else "so' trade" if len(t)
                     else "so' book" if len(b) else "—"),
            "streams": ", ".join(streams),
            "trade_primeiro": min(dias_t) if dias_t else None,
            "trade_ultimo": max(dias_t) if dias_t else None, "trade_dias": len(dias_t),
            "trade_linhas": int(por_dia.fillna(0).sum()) if len(por_dia) else 0,
            "book_dias": len(set(b["dia"])), "ao_vivo": int(orig.get("ao_vivo", 0)),
            "importado": int(orig.get("importado", 0)), "misto": int(orig.get("misto", 0)),
            "desconhecido": int(orig.get("desconhecido", 0)),
            "camadas": ", ".join(sorted(set(g["camada"]))),
            "lacunas": len(dias_uteis_sem_dado(dias_t)),
            "ilegiveis": int(g["ilegiveis"].sum())})
    out = pd.DataFrame(linhas)
    return out.sort_values(["familia", "ativo"]).reset_index(drop=True) if len(out) else out


# ------------------------------------------------------- cruzamento com coletas
def cruzar_coleta(c: dict[str, Any], df: pd.DataFrame, hoje: dt.date) -> dict[str, Any]:
    """O que o disco diz de uma coleta declarada: por ativo, periodo e dias; dias em que TODOS
    os ativos tem trade (o par, no caso da rolagem); cobertura contra os dias uteis esperados."""
    from .coletas import _data

    desde, fim = _data(c.get("desde")), _data(c.get("fim"))
    por: dict[str, set[dt.date]] = {}
    for ativo in c["ativos"]:
        g = df[(df["ativo"] == ativo) & (df["stream"] == "trade")]
        por[ativo] = set(g["dia"])
    comuns = set.intersection(*por.values()) if por else set()
    esperado = 0
    if desde:
        d, ate = desde, min(hoje, fim) if fim else hoje
        while d <= ate:
            esperado += d.weekday() < 5
            d += dt.timedelta(days=1)
    return {"id": c["id"],
            "ativos": {a: {"dias": len(s), "primeiro": min(s) if s else None,
                           "ultimo": max(s) if s else None} for a, s in por.items()},
            "ausentes": [a for a, s in por.items() if not s],
            "dias_em_comum": len(comuns),
            "comuns_primeiro": min(comuns) if comuns else None,
            "comuns_ultimo": max(comuns) if comuns else None,
            "dias_uteis_esperados": esperado}


# ------------------------------------------------------------------- relatorio
def _n(v: Any) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{int(v):,}".replace(",", ".")


def _d(v: Any) -> str:
    return "—" if v is None or (isinstance(v, float) and pd.isna(v)) else f"{v:%d/%m/%Y}"


def _mb(v: float) -> str:
    return f"{v / 1e6:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def relatorio_md(df: pd.DataFrame, coletas: list[dict[str, Any]], hoje: dt.date,
                 raizes: dict[str, Path], carimbo: str, dumps: list[dict[str, Any]] | None) -> str:
    from .coletas import frase_de_situacao, situacao

    raizes_txt = "; ".join(
        f"`{k}` = `{v}`" + ("" if v.exists() else " (NÃO existe)") for k, v in raizes.items())
    n_linhas = f"{len(df):,}".replace(",", ".")
    L = ["# Inventário de dados", "",
         "> **Status:** gerado — **NÃO é diário**: rode sob demanda (antes de formular uma "
         "hipótese, ou quando uma coleta terminar) com `profit-tape inventario-dados`. Confira a "
         "data abaixo antes de confiar.", "",
         f"- **Gerado em:** {carimbo}",
         f"- **Raízes varridas:** {raizes_txt}",
         f"- **Linhas de inventário:** {n_linhas} (camada x stream x ativo x dia)",
         "", "**Vocabulário.** *tape* = negócios com agente agressor e passivo (stream `trade`; "
         "`docs/GLOSSARIO.md`). *Book* = `book_offer`, `book_price`, `tiny_book`. "
         "\"Só trade\" = o ativo tem `trade` e nenhum stream de book. **Origem do dia:** *ao vivo* "
         "(capturado no pregão), *importado* (histórico recuperado depois; 01 a 14/09 foram "
         "importados em 15/09) ou *misto*, pelo `ts_recv_ns` no rodapé do parquet.", ""]
    if coletas:
        L += ["## Coletas em andamento (declaradas x em disco)", "",
              "| Coleta | Situação | Ativos | O que o disco mostra |", "|---|---|---|---|"]
        for c in coletas:
            x = cruzar_coleta(c, df, hoje)
            s = frase_de_situacao(situacao(c, hoje))
            if len(c["ativos"]) > 3:
                ok = len(c["ativos"]) - len(x["ausentes"])
                disco = (f"{ok} de {len(c['ativos'])} séries com trade; "
                         f"{x['dias_uteis_esperados']} dias úteis esperados desde "
                         f"{_d(situacao(c, hoje)['desde'])}")
                if x["ausentes"]:
                    disco += "; **sem dado:** " + ", ".join(x["ausentes"])
                dias = [v["dias"] for v in x["ativos"].values() if v["dias"]]
                if dias:
                    disco += f"; dias por série: {min(dias)} a {max(dias)}"
                rot_ativos = f"{len(c['ativos'])} séries"
            else:
                rot_ativos = ", ".join(c["ativos"])
                partes = []
                for a, v in x["ativos"].items():
                    janela = f"({_d(v['primeiro'])} a {_d(v['ultimo'])})"
                    partes.append(f"`{a}`: {v['dias']} dias {janela}" if v["dias"]
                                  else f"`{a}`: **sem dado**")
                if len(c["ativos"]) > 1:
                    partes.append(f"**dias com os dois (o par): {x['dias_em_comum']}**"
                                  + (f" ({_d(x['comuns_primeiro'])} a {_d(x['comuns_ultimo'])})"
                                     if x["dias_em_comum"] else ""))
                disco = "; ".join(partes)
            L.append(f"| **{c['titulo']}** | {s} | {rot_ativos} | {disco} |")
        L += ["", "Hipótese, leitura declarada antes, limite e próximo passo de cada coleta: "
              "`docs/coletas.yaml`.", ""]
    resumo = por_ativo(df)
    L += ["## Resumo por ativo", ""]
    if resumo.empty:
        L += ["_Nenhum dado encontrado nas raízes acima._", ""]
    else:
        L += ["| Ativo | Família | Tipo | Trade: período | Dias | Linhas | "
              "Ao vivo / importado / misto | Book (dias) | Camadas | Lacunas | Streams |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in resumo.itertuples():
            per = f"{_d(r.trade_primeiro)} a {_d(r.trade_ultimo)}" if r.trade_dias else "—"
            L.append(f"| `{r.ativo}` | {r.familia} | {r.tipo} | {per} | {r.trade_dias} | "
                     f"{_n(r.trade_linhas)} | {r.ao_vivo} / {r.importado} / {r.misto} | "
                     f"{r.book_dias} | {r.camadas} | {r.lacunas} | {r.streams} |")
        L += ["", "*Linhas*: do `trade`, por dia, a maior entre as camadas (elas guardam o mesmo "
              "dia). *Lacunas*: dias da semana sem dado entre o primeiro e o último dia; pode "
              "incluir feriado da B3.", ""]
    if len(df):
        L += ["## Por camada e stream", "",
              "| Camada | Stream | Ativos | Dias (de-até) | Arquivos | MB | Linhas |",
              "|---|---|---|---|---|---|---|"]
        for (cam, st), g in df.groupby(["camada", "stream"]):
            periodo = f"{_d(g['dia'].min())} a {_d(g['dia'].max())}"
            L.append(f"| {cam} | {st} | {g['ativo'].nunique()} | {periodo} | "
                     f"{_n(g['arquivos'].sum())} | {_mb(g['bytes'].sum())} | "
                     f"{_n(g['linhas'].sum())} |")
        L.append("")
        lac = []
        for ativo, g in df[df["stream"] == "trade"].groupby("ativo"):
            falt = dias_uteis_sem_dado(set(g["dia"]))
            if falt:
                lac.append((ativo, falt))
        if lac:
            L += ["## Lacunas no trade (dias da semana sem dado entre o primeiro e o último)", ""]
            for ativo, falt in lac[:40]:
                txt = ", ".join(f"{x:%d/%m}" for x in falt[:12]) + (" …" if len(falt) > 12 else "")
                L.append(f"- `{ativo}`: {len(falt)} dia(s): {txt}")
            L.append("")
    L += ["## Dumps do console do Profit (histórico de preço e indicadores)", "",
          "*Dump* = arquivo de texto com as linhas que um indicador NTSL escreve no console do "
          "Profit (`PRCBARRA|`, `ABSBARRA|`, `VWAPVP|`...) e que você copia à mão: **não é CSV nem "
          "parquet**. É a amostra longa de preço (ex.: out/2015 a dez/2022), sem agente. O NTSL "
          "não escreve o ticker na linha.", ""]
    if dumps is None:
        L += ["_Não varrido: passe `--dumps <pasta ou arquivo>` ao gerar (o projeto não fixa onde "
              "esses arquivos ficam)._", ""]
    elif not dumps:
        L += ["_Nenhuma linha de dump (`PRCBARRA|`, `ABSBARRA|`, `VWAPVP|`, `BBSBARRA|`, "
              "`ABSDIR|`) encontrada no caminho informado._", ""]
    else:
        L += ["| Arquivo | Tipo | Linhas | Dias | Primeiro dia | Último dia | Por dia (mediana) | "
              "Ativo provável | Repetidas |", "|---|---|---|---|---|---|---|---|---|"]
        for d in dumps:
            rep = f"**{d['repetidas']}**" if d["repetidas"] else "0"
            L.append(f"| `{d['arquivo']}` | {d['tipo']} | {_n(d['linhas'])} | {d['dias']} | "
                     f"{_d(d['primeira'])} | {_d(d['ultima'])} | {_n(d['por_dia_mediana'])} | "
                     f"{d['ativo']} | {rep} |")
        L += ["", "*Repetidas*: barras com o mesmo dia e hora no mesmo arquivo — dumps sobrepostos "
              "inflam o n sem informação nova (o parser das fichas recusa). *Ativo provável* é "
              "estimativa pelo nome do arquivo ou pela ordem de grandeza do preço; confirme.", ""]
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------- dumps
# DUMP, no projeto: arquivo de texto com as linhas que um indicador NTSL escreve no console do
# Profit (`ConsoleLog`) e que o operador COPIA a mao para um arquivo (nao e' CSV nem parquet). Cada
# linha tem um prefixo, e o primeiro campo e' a data no formato do NTSL (1AAMMDD: 1150102 =
# 02/01/2015). Sao o "historico (amostra) out/2015 a dez/2022" do glossario. O NTSL nao emite o
# ticker na linha.
PREFIXOS_DUMP = {
    "PRCBARRA|": "preco M15 (barras)",
    "ABSBARRA|": "absorcao M5 (barras)",
    "VWAPVP|": "VWAP + VP M5 (barras)",
    "BBSBARRA|": "bollinger scalp (barras)",
    "ABSDIR|": "absorcao direcional (eventos)",
}
_BARRAS = ("PRCBARRA|", "ABSBARRA|", "VWAPVP|", "BBSBARRA|")      # uma linha = uma barra
_TICKERS_NO_NOME = ("WINFUT", "WDOFUT", "WIN", "WDO", "PETR4", "VALE3", "ITUB4")


def _data_ntsl(campo: str) -> dt.date | None:
    """1AAMMDD do NTSL (`1900 + d // 10000`, como o parser do projeto). None se nao for data."""
    campo = campo.strip()
    if not campo.isdigit() or not 5 <= len(campo) <= 7:
        return None
    d = int(campo)
    ano, mes, dia = 1900 + d // 10000, (d // 100) % 100, d % 100
    if not (1990 <= ano <= 2100 and 1 <= mes <= 12 and 1 <= dia <= 31):
        return None
    try:
        return dt.date(ano, mes, dia)
    except ValueError:
        return None


def _numero(v: str) -> float | None:
    try:
        return float(v.strip().replace(",", "."))
    except ValueError:
        return None


def _ativo_provavel(nome: str, closes: list[float]) -> str:
    """O dump nao traz o ticker. Pista 1: o nome do arquivo. Pista 2 (so' PRCBARRA): a ordem de
    grandeza do preco (WIN ~ 40 a 200 mil pontos; WDO ~ 2 a 6 mil). E' ESTIMATIVA."""
    baixo = nome.lower()
    for t in _TICKERS_NO_NOME:
        if t.lower() in baixo:
            return f"{t} (pelo nome do arquivo)"
    if closes:
        med = sorted(closes)[len(closes) // 2]
        if med > 20_000:
            return "WIN (estimado pelo preco)"
        if 1_000 <= med <= 10_000:
            return "WDO (estimado pelo preco)"
    return "nao consta"


def escanear_dumps(destino: Path) -> list[dict[str, Any]]:
    """Inventaria os dumps de `destino` (pasta ou arquivo): por arquivo e por TIPO de linha, o
    numero de linhas, dias, primeiro e ultimo dia, barras por dia (mediana) e barras REPETIDAS
    (dumps sobrepostos inflam o n sem informacao nova). O console pode por texto antes do
    prefixo."""
    arquivos = ([destino] if destino.is_file() else sorted(
        f for f in destino.rglob("*") if f.is_file()
        and f.suffix.lower() in (".txt", ".log", ".csv", ".dump", "")))
    out: list[dict[str, Any]] = []
    for f in arquivos:
        try:
            texto = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for prefixo, rotulo in PREFIXOS_DUMP.items():
            if prefixo not in texto:
                continue
            por_dia: dict[dt.date, int] = {}
            chaves: set[tuple[str, str]] = set()
            repetidas, n = 0, 0
            closes: list[float] = []
            for linha in texto.splitlines():
                if prefixo not in linha:
                    continue
                n += 1
                campos = linha.split(prefixo, 1)[1].strip().split("|")
                dia = _data_ntsl(campos[0])
                if dia is not None:
                    por_dia[dia] = por_dia.get(dia, 0) + 1
                if prefixo in _BARRAS and len(campos) > 1:
                    chave = (campos[0], campos[1])
                    repetidas += chave in chaves
                    chaves.add(chave)
                if prefixo == "PRCBARRA|" and len(campos) > 7 and len(closes) < 5000:
                    c = _numero(campos[7])
                    if c is not None:
                        closes.append(c)
            cont = sorted(por_dia.values())
            out.append({
                "arquivo": f.name if destino.is_file() else str(f.relative_to(destino)),
                "bytes": f.stat().st_size, "tipo": rotulo, "prefixo": prefixo.rstrip("|"),
                "linhas": n, "dias": len(por_dia),
                "primeira": min(por_dia) if por_dia else None,
                "ultima": max(por_dia) if por_dia else None,
                "por_dia_mediana": cont[len(cont) // 2] if cont else None,
                "repetidas": repetidas,
                "ativo": _ativo_provavel(f.name, closes) if prefixo == "PRCBARRA|" else (
                    _ativo_provavel(f.name, [])),
            })
    return out
