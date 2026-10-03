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

import contextlib
import datetime as dt
import os
import re
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow.parquet as pq

_TZ = ZoneInfo("America/Sao_Paulo")
_NS = 1_000_000_000
STREAMS_BOOK = ("book_offer", "book_price", "tiny_book")
_PRIORIDADE_CAMADA = {"curated": 0, "raw": 1, "backup": 2}
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


# ------------------------------------------------------------ varredura com ORCAMENTO de I/O
# v4.23 abria TODOS os parquet de TODOS os streams (book e' o grosso do raw), 8 ao mesmo tempo, e
# so' devolvia no fim: no disco do operador (milhares de partes, backup em USB, antivirus lendo
# cada arquivo) travou a maquina inteira, e sem uma linha de progresso. Agora:
#   1. LISTAR (so' diretorios; nenhum parquet aberto) -> plano;
#   2. ABRIR rodapes apenas do que o `nivel` pede, com teto de arquivos, poucas threads, pausa
#      opcional e progresso continuo.
NIVEIS = ("listar", "leve", "trade", "completo")
NIVEL_AJUDA = {
    "listar": "nenhum parquet aberto: só pastas, arquivos e MB (linhas e origem ficam em branco)",
    "leve": "padrão: abre rodapés só de curated/trade (poucos arquivos: um por dia e ativo)",
    "trade": "leve + raw/trade (milhares de partes: só com o record parado)",
    "completo": "tudo, inclusive book e backup (centenas de milhares de arquivos: so' com teto)",
}
LIMITE_PADRAO = 20_000


class LimiteExcedido(RuntimeError):
    """O nivel pedido abriria mais arquivos do que o teto: nada foi aberto."""

    def __init__(self, a_abrir: int, teto: int, nivel: str) -> None:
        super().__init__(f"nivel '{nivel}' abriria {a_abrir:,} arquivos (teto {teto:,})"
                         .replace(",", "."))
        self.a_abrir, self.teto, self.nivel = a_abrir, teto, nivel


@dataclass
class Folha:
    """Uma pasta `<camada>/<stream>/dt=<dia>/sym=<ativo>` (so' metadados de diretorio)."""

    camada: str
    stream: str
    ativo: str
    dia: dt.date
    pasta: Path
    n_arquivos: int
    bytes: int


def _entradas(p: Path) -> list[os.DirEntry[str]]:
    try:
        with os.scandir(p) as it:
            return list(it)
    except OSError:
        return []


def _partes(pasta: Path) -> list[os.DirEntry[str]]:
    """`part-*.parquet` prontos (ignora `.inprogress` e lixo). `DirEntry.stat()` vem da propria
    listagem no Windows: nao e' uma leitura a mais de disco."""
    return sorted((e for e in _entradas(pasta) if e.is_file() and e.name.startswith("part-")
                   and e.name.endswith(".parquet")), key=lambda e: e.name)


def listar(raizes: dict[str, Path],
           progresso: Callable[[str, int, int | None], None] | None = None) -> list[Folha]:
    """ETAPA 1: percorre so' diretorios. Nenhum parquet e' aberto aqui."""
    folhas: list[Folha] = []
    ultimo = time.monotonic()
    def por_nome(es: list[os.DirEntry[str]]) -> list[os.DirEntry[str]]:
        return sorted(es, key=lambda e: e.name)

    for camada, raiz in raizes.items():
        if not raiz.exists():
            continue
        for st in por_nome([e for e in _entradas(raiz)
                            if e.is_dir() and not e.name.startswith("_")]):
            for edia in por_nome([e for e in _entradas(Path(st.path)) if e.is_dir()]):
                dia = _dia_de(Path(edia.path))
                if dia is None:
                    continue
                for esym in por_nome([e for e in _entradas(Path(edia.path))
                                      if e.is_dir() and e.name.startswith("sym=")]):
                    arqs = _partes(Path(esym.path))
                    tamanho = 0
                    for a in arqs:
                        with contextlib.suppress(OSError):
                            tamanho += a.stat().st_size
                    folhas.append(Folha(camada, st.name, esym.name[4:], dia, Path(esym.path),
                                        len(arqs), tamanho))
                    if progresso and time.monotonic() - ultimo >= 2.0:
                        progresso("listando", len(folhas), None)
                        ultimo = time.monotonic()
    return folhas


def escolher(folhas: list[Folha], nivel: str) -> list[Folha]:
    """Folhas cujos rodapes o `nivel` autoriza abrir."""
    if nivel not in NIVEIS:
        raise ValueError(f"nivel invalido: {nivel!r} (use {', '.join(NIVEIS)})")
    if nivel == "listar":
        return []
    if nivel == "leve":
        return [f for f in folhas if f.camada == "curated" and f.stream == "trade"]
    if nivel == "trade":
        return [f for f in folhas if f.stream == "trade" and f.camada in ("curated", "raw")]
    return list(folhas)


def plano(folhas: list[Folha], nivel: str) -> dict[str, Any]:
    """O que a varredura vai fazer, ANTES de abrir qualquer arquivo."""
    sel = escolher(folhas, nivel)
    por: dict[tuple[str, str], list[int]] = {}
    for f in folhas:
        x = por.setdefault((f.camada, f.stream), [0, 0, 0])
        x[0] += 1
        x[1] += f.n_arquivos
        x[2] += f.bytes
    return {"nivel": nivel, "pastas": len(folhas), "arquivos": sum(f.n_arquivos for f in folhas),
            "bytes": sum(f.bytes for f in folhas), "a_abrir": sum(f.n_arquivos for f in sel),
            "por_stream": [{"camada": c, "stream": st, "pastas": v[0], "arquivos": v[1],
                            "bytes": v[2]} for (c, st), v in sorted(por.items())]}


def _linha_vazia(f: Folha) -> dict[str, Any]:
    return {"camada": f.camada, "stream": f.stream, "ativo": f.ativo, "dia": f.dia,
            "arquivos": f.n_arquivos, "bytes": f.bytes, "linhas": None, "recv_min": None,
            "recv_max": None, "origem": "desconhecido", "ilegiveis": 0}


def abrir(folhas: list[Folha], nivel: str, threads: int = 2, pausa_ms: int = 0,
          teto: int = LIMITE_PADRAO,
          progresso: Callable[[str, int, int | None], None] | None = None) -> pd.DataFrame:
    """ETAPA 2: abre so' os rodapes que o nivel autoriza, no maximo `teto` arquivos."""
    sel = escolher(folhas, nivel)
    total = sum(f.n_arquivos for f in sel)
    if total > teto:
        raise LimiteExcedido(total, teto, nivel)
    selecionadas = {id(f) for f in sel}
    feitos, trava, ultimo = [0], threading.Lock(), [time.monotonic()]

    def uma(f: Folha) -> dict[str, Any]:
        row = _linha_vazia(f)
        n, lo, hi, ok = 0, None, None, True
        for e in _partes(f.pasta):
            try:
                nn, l1, h1 = _rodape(Path(e.path))
            except Exception:                    # parquet sem footer / corrompido
                row["ilegiveis"] += 1
                nn, l1, h1 = 0, None, None
                ok = ok and True
            n += nn
            if l1 is None or h1 is None:
                ok = False if nn else ok
            else:
                lo = l1 if lo is None else min(lo, l1)
                hi = h1 if hi is None else max(hi, h1)
            if pausa_ms:
                time.sleep(pausa_ms / 1000)
            with trava:
                feitos[0] += 1
                agora = time.monotonic()
                if progresso and (feitos[0] % 250 == 0 or agora - ultimo[0] >= 3.0):
                    progresso("abrindo rodapes", feitos[0], total)
                    ultimo[0] = agora
        row["linhas"] = n
        if ok and lo is not None and hi is not None:
            row["recv_min"], row["recv_max"] = lo, hi
            row["origem"] = classificar_origem(f.dia, lo, hi)
        return row

    linhas: list[dict[str, Any]] = []
    com_rodape = [f for f in folhas if id(f) in selecionadas]
    if com_rodape:
        with ThreadPoolExecutor(max_workers=max(1, threads)) as ex:
            feitas = dict(zip((id(f) for f in com_rodape), ex.map(uma, com_rodape), strict=True))
    else:
        feitas = {}
    for f in folhas:
        linhas.append(feitas.get(id(f)) or _linha_vazia(f))
    if progresso and total:
        progresso("abrindo rodapes", total, total)
    return pd.DataFrame(linhas, columns=COLUNAS) if linhas else pd.DataFrame(columns=COLUNAS)


def escanear(raizes: dict[str, Path], nivel: str = "leve", threads: int = 2, pausa_ms: int = 0,
             teto: int = LIMITE_PADRAO,
             progresso: Callable[[str, int, int | None], None] | None = None) -> pd.DataFrame:
    """Listar + abrir, em uma chamada (a CLI usa as duas etapas para mostrar o plano antes)."""
    return abrir(listar(raizes, progresso), nivel, threads, pausa_ms, teto, progresso)


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
        # v4.24 ficava com a linha do BACKUP (rodape nao aberto: origem desconhecida) e descartava a
        # do curated, que tinha a origem: o relatorio saia com 0/0/0 em todo ativo.
        orig = (t.assign(_ign=t["origem"] == "desconhecido",
                         _p=t["camada"].map(_PRIORIDADE_CAMADA).fillna(9))
                 .sort_values(["_ign", "_p"]).drop_duplicates("dia")["origem"]
                 .value_counts().to_dict()) if len(t) else {}
        streams = sorted(set(g["stream"]))
        d_of = len(set(g[g["stream"] == "book_offer"]["dia"]))
        d_pr = len(set(g[g["stream"] == "book_price"]["dia"]))
        d_tp = len(set(g[g["stream"] == "tiny_book"]["dia"]))
        if not len(t):
            tipo = "só book" if len(b) else "—"
        elif d_of:
            tipo = "trade + book de ofertas"
        elif d_pr:
            tipo = "trade + book de preço"
        elif d_tp:
            tipo = "trade + só topo (tiny_book)"
        else:
            tipo = "só trade"
        linhas.append({
            "ativo": ativo, "familia": familia(str(ativo)), "tipo": tipo,
            "dias_ofertas": d_of, "dias_preco": d_pr, "dias_topo": d_tp,
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


def _gb(v: float) -> str:
    return f"{v / 1e9:.1f}".replace(".", ",")


def _mb(v: float) -> str:
    return f"{v / 1e6:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def relatorio_md(df: pd.DataFrame, coletas: list[dict[str, Any]], hoje: dt.date,
                 raizes: dict[str, Path], carimbo: str, dumps: list[dict[str, Any]] | None,
                 plan: dict[str, Any] | None = None) -> str:
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
         *( [f"- **Nível de varredura:** `{plan['nivel']}` — {NIVEL_AJUDA[plan['nivel']]}. "
             f"Listados {_n(plan['arquivos'])} arquivos em {_n(plan['pastas'])} pastas "
             f"({_gb(plan['bytes'])} GB); rodapés abertos: {_n(plan['a_abrir'])}."]
            if plan else []),
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
              "Ao vivo / importado / misto / desconhecido | Livro (dias): ofertas / preço / topo | "
              "Camadas | Lacunas |", "|---|---|---|---|---|---|---|---|---|---|"]
        for r in resumo.itertuples():
            per = f"{_d(r.trade_primeiro)} a {_d(r.trade_ultimo)}" if r.trade_dias else "—"
            L.append(f"| `{r.ativo}` | {r.familia} | {r.tipo} | {per} | {r.trade_dias} | "
                     f"{_n(r.trade_linhas)} | {r.ao_vivo} / {r.importado} / {r.misto} / "
                     f"{r.desconhecido} | {r.dias_ofertas} / {r.dias_preco} / {r.dias_topo} | "
                     f"{r.camadas} | {r.lacunas} |")
        L += ["", "*Tipo*: **book de ofertas** = `book_offer` (profundidade, por ordem); "
              "**só topo** = só `tiny_book` (melhor compra e venda), que chega para todo ticker "
              "assinado. "
              "*Linhas* e *origem* (ao vivo/importado) só existem onde o rodapé foi lido: no "
              "nível padrão (`leve`) são os dias do `curated`; dia só no raw aparece como "
              "desconhecido (`--nivel trade`, com o record parado, lê o raw). *Linhas*: do "
              "`trade`, por dia, a maior entre as camadas. *Lacunas*: dias da semana sem dado "
              "entre o primeiro e o último dia; pode incluir feriado da B3.", ""]
    if len(df):
        L += ["## Por camada e stream", "",
              "| Camada | Stream | Ativos | Dias (de-até) | Arquivos | MB | Linhas |",
              "|---|---|---|---|---|---|---|"]
        for (cam, st), g in df.groupby(["camada", "stream"]):
            periodo = f"{_d(g['dia'].min())} a {_d(g['dia'].max())}"
            lidas = _n(g["linhas"].sum()) if g["linhas"].notna().any() else "— (rodapé não aberto)"
            L.append(f"| {cam} | {st} | {g['ativo'].nunique()} | {periodo} | "
                     f"{_n(g['arquivos'].sum())} | {_mb(g['bytes'].sum())} | {lidas} |")
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
            rep = ("n/d" if d["repetidas"] is None
                   else f"**{d['repetidas']}**" if d["repetidas"] else "0")
            L.append(f"| `{d['arquivo']}` | {d['tipo']} | {_n(d['linhas'])} | {d['dias']} | "
                     f"{_d(d['primeira'])} | {_d(d['ultima'])} | {_n(d['por_dia_mediana'])} | "
                     f"{d['ativo']} | {rep} |")
        L += ["", "*Repetidas*: barras com a mesma identidade do parser da ficha (dia + "
              "`current_bar` em PRCBARRA e BBSBARRA; dia + hora em ABSBARRA) no mesmo arquivo: "
              "dumps sobrepostos inflam o n sem informação nova. `n/d` = o tipo não tem "
              "identidade de barra. *Ativo "
              "provável* é estimativa pelo nome do arquivo ou pela ordem de grandeza do preço "
              "(só PRCBARRA); confirme.", ""]
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
# Identidade da barra = a do parser de cada ficha (indices dos campos apos o prefixo):
#   PRCBARRA e BBSBARRA: (data, current_bar) -- em 15 s quatro barras dividem a MESMA `hora`;
#   ABSBARRA: (data, hora). VWAPVP e ABSDIR: sem parser que desduplique -> "n/d", nunca um palpite.
# (v4.24 usava (data, hora) para todos e acusou 75% de "repetidas" nos dumps de 15 s: falso alarme.)
_IDENTIDADE: dict[str, tuple[int, ...]] = {"PRCBARRA|": (0, 3), "BBSBARRA|": (0, 3),
                                           "ABSBARRA|": (0, 1)}
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


LIMITE_DUMP_BYTES = 300 * 1024 * 1024
LIMITE_DUMP_ARQUIVOS = 300
_PODAR = {".git", ".venv", "venv", "node_modules", "__pycache__", "raw", "curated", "_quarentena"}
_RE_PREFIXO = re.compile(r"(PRCBARRA|ABSBARRA|VWAPVP|BBSBARRA|ABSDIR)\|")
_MAX_CHAVES = 2_000_000


def _candidatos_dump(destino: Path) -> tuple[list[Path], bool]:
    """Arquivos .txt/.log/.dump/.csv sob `destino` (sem entrar em .git, .venv, raw, curated...).
    Arquivo SEM extensao nao entra (v4.23 lia ate' os objetos do .git). Teto de arquivos."""
    if destino.is_file():
        return [destino], False
    achados: list[Path] = []
    for raiz, dirs, nomes in os.walk(destino):
        dirs[:] = sorted(d for d in dirs if d not in _PODAR)
        for n in sorted(nomes):
            if Path(n).suffix.lower() in (".txt", ".log", ".csv", ".dump"):
                achados.append(Path(raiz) / n)
                if len(achados) > LIMITE_DUMP_ARQUIVOS:
                    return achados[:LIMITE_DUMP_ARQUIVOS], True
    return achados, False


def escanear_dumps(destino: Path, limite_bytes: int = LIMITE_DUMP_BYTES) -> list[dict[str, Any]]:
    """Inventaria os dumps de `destino` (pasta ou arquivo): por arquivo e por TIPO de linha, o
    numero de linhas, dias, primeiro e ultimo dia, barras por dia (mediana) e barras REPETIDAS
    (dumps sobrepostos inflam o n sem informacao nova). O console pode por texto antes do
    prefixo. Le em STREAMING, uma passada (a v4.23 lia o arquivo inteiro e o percorria uma vez por
    prefixo). Arquivo acima de `limite_bytes` e' pulado e dito; pasta acima de 300 arquivos e'
    cortada e dita."""
    arquivos, cortado = _candidatos_dump(destino)
    out: list[dict[str, Any]] = []
    if cortado:
        out.append({"arquivo": "(pasta com arquivos demais)", "bytes": 0, "tipo": (
            f"CORTADO: so' os primeiros {LIMITE_DUMP_ARQUIVOS} arquivos foram lidos; aponte "
            "--dumps para a pasta certa"), "prefixo": "", "linhas": None, "dias": None,
            "primeira": None, "ultima": None, "por_dia_mediana": None, "repetidas": None,
            "ativo": "—"})
    for f in arquivos:
        nome = f.name if destino.is_file() else str(f.relative_to(destino))
        try:
            tamanho = f.stat().st_size
        except OSError:
            continue
        if tamanho > limite_bytes:
            out.append({"arquivo": nome, "caminho": str(f.resolve()), "bytes": tamanho, "tipo": (
                f"PULADO: arquivo de {tamanho / 1e6:,.0f} MB (limite {limite_bytes / 1e6:,.0f} MB)"
                .replace(",", ".")), "prefixo": "", "linhas": None, "dias": None,
                "primeira": None, "ultima": None, "por_dia_mediana": None, "repetidas": None,
                "ativo": "—"})
            continue
        est: dict[str, dict[str, Any]] = {}
        try:
            with f.open("r", encoding="utf-8", errors="replace") as fh:
                for linha in fh:
                    m = _RE_PREFIXO.search(linha)
                    if m is None:
                        continue
                    prefixo = m.group(1) + "|"
                    e = est.setdefault(prefixo, {"n": 0, "dias": {}, "chaves": set(), "rep": 0,
                                                 "closes": []})
                    e["n"] += 1
                    campos = linha[m.end():].strip().split("|")
                    dia = _data_ntsl(campos[0])
                    if dia is not None:
                        e["dias"][dia] = e["dias"].get(dia, 0) + 1
                    idx = _IDENTIDADE.get(prefixo)
                    if idx and len(campos) > max(idx) and len(e["chaves"]) < _MAX_CHAVES:
                        chave = tuple(campos[i] for i in idx)
                        e["rep"] += chave in e["chaves"]
                        e["chaves"].add(chave)
                    if prefixo == "PRCBARRA|" and len(campos) > 7 and len(e["closes"]) < 5000:
                        c = _numero(campos[7])
                        if c is not None:
                            e["closes"].append(c)
        except OSError:
            continue
        for prefixo, rotulo in PREFIXOS_DUMP.items():
            achado = est.get(prefixo)
            if achado is None:
                continue
            por_dia: dict[dt.date, int] = achado["dias"]
            cont = sorted(por_dia.values())
            closes = achado["closes"] if prefixo == "PRCBARRA|" else []
            out.append({
                "arquivo": nome, "caminho": str(f.resolve()), "bytes": tamanho, "tipo": rotulo,
                "prefixo": prefixo.rstrip("|"),
                "linhas": achado["n"], "dias": len(por_dia),
                "primeira": min(por_dia) if por_dia else None,
                "ultima": max(por_dia) if por_dia else None,
                "por_dia_mediana": cont[len(cont) // 2] if cont else None,
                "repetidas": achado["rep"] if prefixo in _IDENTIDADE else None,
                "ativo": _ativo_provavel(f.name, closes),
            })
    return out


def escanear_dumps_varios(destinos: list[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    """Varios `--dumps` (pastas e/ou arquivos). Um arquivo alcancado por dois caminhos (uma pasta
    dentro da outra) entra UMA vez. Com mais de um destino o nome ganha o da pasta de origem.
    Devolve (entradas, avisos): destino inexistente e' dito, nunca ignorado em silencio."""
    vistos: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    avisos: list[str] = []
    for d in destinos:
        if not d.exists():
            avisos.append(f"--dumps nao existe: {d}")
            continue
        for e in escanear_dumps(d):
            chave = (e.get("caminho", e["arquivo"]), e.get("prefixo", ""))
            if chave in vistos:
                continue
            vistos.add(chave)
            if len(destinos) > 1 and d.is_dir() and not e["tipo"].startswith("CORTADO"):
                e = {**e, "arquivo": f"{d.name}/{e['arquivo']}".replace("\\", "/")}
            out.append(e)
    return out, avisos
