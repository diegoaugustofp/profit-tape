"""
DIARIO OPERACIONAL (v4.12): um lugar so' para o que os EAs fizeram e para o
que a infraestrutura fez COM eles naquele dia.

Pedido do operador (02/10): consolidar os eventos que ja' sao medidos --
atraso do record e o custo disso, stop maior que o programado -- para saber
quanto cada variavel pesou no resultado. Duas fontes, as duas que existem:

  * o log do record (`logs/record_diario.jsonl`, structlog, uma linha JSON,
    timestamp ISO UTC): entradas e saidas dos EAs, heartbeat, estados da DLL,
    avisos e erros;
  * o tape curado do dia (`ts_ns`, `ts_recv_ns`): o atraso REAL de cada
    negocio (`ts_recv - ts`, carimbado na entrada do callback da DLL) e os
    buracos de chegada. Existe depois do compact; sem ele o diario sai so'
    com a parte do log e avisa.

DECOMPOSICAO DE UMA OPERACAO (identidade exata, testada):

    D       = preco de referencia do sinal (ignicao: preco de deteccao;
              vwap_vp: close da barra de sinal)
    L       = +1 comprado, -1 vendido
    entrada = (fill_entrada - D) * L                  piora de entrada
    ref     = (preco_do_tape_no_gatilho - D) * L
    ideal   = +alvo_pts (saiu no alvo) | -stop_pts (saiu no stop) | ref (tempo)
    gap     = ideal - ref        o quanto o PRIMEIRO negocio alem da barreira
                                 ja' estava longe dela (mercado andou rapido)
    fill    = (preco_do_tape_no_gatilho - fill_saida) * L   deslizamento da
                                 execucao simulada em relacao ao tape
    custo   = pnl_bruto - pnl_liquido

    pnl_liquido = ideal - gap - fill - entrada - custo

`gap` e' o que um stop NAO consegue evitar; `fill` e' onde atraso e spread
entram. O diario mede o atraso do feed NA HORA da saida (mediana de
`ts_recv - ts` dos negocios que chegaram a +-1 s do instante em que o EA
processou) e mostra ao lado: nao atribui causa, deixa o dado acumular.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

_TZ = ZoneInfo("America/Sao_Paulo")
_NS = 1_000_000_000
LIMIAR_ATRASO_S = 10.0           # minuto de EVENTO com atraso maximo >= isto = incidente
LIMIAR_BURACO_S = 20.0           # intervalo sem NENHUMA chegada dentro do pregao
JANELA_ATRASO_S = 2.0            # atraso "relevante" na hora da saida
SESSAO_HHMM = (900, 1830)
_RE_SAIDA_GENERICA = re.compile(r"ea\.[a-z0-9_]+\.(saida|operacao_fechada)")


# --------------------------------------------------------------------- log
def _utc_ns(ts: str) -> int:
    d = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return int(d.timestamp()) * _NS + d.microsecond * 1000


def _brt(t_ns: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(t_ns / 1e9, tz=_TZ)


def ler_log(caminho: Path, dia: dt.date) -> tuple[list[dict[str, Any]], int]:
    """Eventos do `dia` (data de Brasilia), em ordem. Devolve (eventos,
    linhas_invalidas). Pre-filtra pela data UTC da linha (dia e dia+1) antes
    de converter: o log guarda meses."""
    prefixos = {dia.isoformat(), (dia + dt.timedelta(days=1)).isoformat()}
    eventos: list[dict[str, Any]] = []
    ruins = 0
    with caminho.open(encoding="utf-8", errors="replace") as f:
        for linha in f:
            linha = linha.strip()
            if not linha.startswith("{"):
                continue
            try:
                d = json.loads(linha)
                ts = str(d["timestamp"])
                if ts[:10] not in prefixos:
                    continue
                t = _utc_ns(ts)
            except (json.JSONDecodeError, KeyError, ValueError):
                ruins += 1
                continue
            if _brt(t).date() != dia:
                continue
            d["_t"] = t
            eventos.append(d)
    eventos.sort(key=lambda e: e["_t"])
    return eventos, ruins


# ------------------------------------------------------------ operacoes
def decompor(*, lado: int, d: float, entrada: float, saida: float, saida_tape: float,
             motivo: str, alvo_px: float | None, stop_px: float | None,
             pnl_bruto: float, pnl_liquido: float) -> dict[str, float | None]:
    """Decomposicao de uma operacao (ver docstring do modulo). Vale para
    qualquer EA que tenha referencia, barreiras e preco do tape no gatilho."""
    ref = (saida_tape - d) * lado
    alvo_pts = None if alvo_px is None else (alvo_px - d) * lado
    stop_pts = None if stop_px is None else (d - stop_px) * lado
    if motivo == "alvo" and alvo_pts is not None:
        ideal = alvo_pts
    elif motivo == "stop" and stop_pts is not None:
        ideal = -stop_pts
    else:
        ideal = ref
    entrada_slip = (entrada - d) * lado
    fill = (saida_tape - saida) * lado
    custo = pnl_bruto - pnl_liquido
    gap = ideal - ref
    residuo = pnl_liquido - (ideal - gap - fill - entrada_slip - custo)
    perda_real = -pnl_bruto if motivo == "stop" else None
    razao = (perda_real / stop_pts) if (perda_real is not None and stop_pts) else None
    return {"ideal": ideal, "entrada_slip": entrada_slip, "gap": gap, "fill": fill,
            "custo": custo, "residuo": residuo, "alvo_pts": alvo_pts, "stop_pts": stop_pts,
            "stop_real_sobre_programado": razao}


def _f(e: dict[str, Any], k: str) -> float | None:
    v = e.get(k)
    return None if v is None else float(v)


def _op_ign(s: dict[str, Any], ent: dict[str, Any] | None) -> dict[str, Any]:
    op: dict[str, Any] = {"ea": s.get("nome"), "tipo": "ignicao", "lado": int(s["lado"]),
                          "motivo": str(s["motivo"]), "t_saida": s["_t"],
                          "t_entrada": ent["_t"] if ent else None,
                          "entrada": _f(s, "entrada"), "saida": _f(s, "saida"),
                          "pnl_bruto": _f(s, "pnl_bruto"), "pnl_liquido": _f(s, "pnl_liquido"),
                          "duracao_s": _f(s, "duracao_s"), "fill_origem": s.get("fill_origem"),
                          "atraso_log_entrada_s": _f(ent, "atraso_s") if ent else None,
                          "ancora": s.get("ancora")}
    if ent is not None and None not in (op["entrada"], op["saida"], op["pnl_bruto"],
                                        op["pnl_liquido"], _f(s, "saida_tape"),
                                        _f(s, "preco_deteccao")):
        op.update(decompor(lado=op["lado"], d=float(s["preco_deteccao"]),
                           entrada=op["entrada"], saida=op["saida"],
                           saida_tape=float(s["saida_tape"]), motivo=op["motivo"],
                           alvo_px=_f(ent, "alvo"), stop_px=_f(ent, "stop"),
                           pnl_bruto=op["pnl_bruto"], pnl_liquido=op["pnl_liquido"]))
    return op


def _op_vwapvp(s: dict[str, Any], ent: dict[str, Any] | None,
               sin: dict[str, Any] | None) -> dict[str, Any]:
    op: dict[str, Any] = {"ea": s.get("nome"), "tipo": "vwap_vp", "lado": int(s["lado"]),
                          "motivo": str(s["motivo"]), "t_saida": s["_t"],
                          "t_entrada": ent["_t"] if ent else None,
                          "entrada": _f(s, "entrada"), "saida": _f(s, "saida"),
                          "pnl_bruto": _f(s, "pnl_bruto"), "pnl_liquido": _f(s, "pnl_liquido"),
                          "duracao_s": _f(s, "duracao_s"), "fill_origem": "tape",
                          "hhmm_sinal": s.get("hhmm_sinal")}
    if sin is not None and None not in (op["entrada"], op["saida"], op["pnl_bruto"],
                                        op["pnl_liquido"], _f(sin, "close")):
        # dry_run: o fill de saida e' o proprio preco do negocio -> tape == fill
        op.update(decompor(lado=op["lado"], d=float(sin["close"]), entrada=op["entrada"],
                           saida=op["saida"], saida_tape=op["saida"], motivo=op["motivo"],
                           alvo_px=_f(s, "alvo_px"), stop_px=_f(s, "stop_px"),
                           pnl_bruto=op["pnl_bruto"], pnl_liquido=op["pnl_liquido"]))
    return op


def _op_generica(e: dict[str, Any]) -> dict[str, Any]:
    """EAs sem decomposicao (123, microprice, z_agf): o que o log trouxer."""
    pnl = next((e[k] for k in ("pnl_liquido", "pnl_pts", "pnl_liq", "pnl") if k in e), None)
    bruto = e.get("ordens")
    ordens: dict[str, Any] = bruto if isinstance(bruto, dict) else {}
    slip = [o.get("slippage_pts") for o in ordens.values() if o.get("slippage_pts") is not None]
    lat = [o.get("latencia_fill_ms") for o in ordens.values()
           if o.get("latencia_fill_ms") is not None]
    return {"ea": e.get("nome") or e["event"].split(".")[1], "tipo": e["event"],
            "lado": e.get("lado"), "motivo": e.get("motivo") or e.get("desfecho"),
            "t_saida": e["_t"], "t_entrada": None,
            "pnl_liquido": None if pnl is None else float(pnl),
            "slippage_ordens_pts": float(sum(slip)) if slip else None,
            "latencia_fill_max_ms": float(max(lat)) if lat else None}


def extrair_operacoes(eventos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = []
    ign: dict[Any, dict[str, Any]] = {}
    vv_sinal: dict[Any, dict[str, Any]] = {}
    vv_ent: dict[Any, tuple[dict[str, Any], dict[str, Any] | None]] = {}
    for e in eventos:
        ev = str(e.get("event", ""))
        nome = e.get("nome")
        try:
            if ev == "ea.ign.entrada":
                ign[nome] = e
            elif ev == "ea.ign.saida":
                ops.append(_op_ign(e, ign.pop(nome, None)))
            elif ev == "ea.vwapvp.sinal":
                vv_sinal[nome] = e
            elif ev == "ea.vwapvp.entrada":
                vv_ent[nome] = (e, vv_sinal.get(nome))
            elif ev == "ea.vwapvp.saida":
                ent, sin = vv_ent.pop(nome, (None, None))
                ops.append(_op_vwapvp(e, ent, sin))
            elif _RE_SAIDA_GENERICA.fullmatch(ev):
                ops.append(_op_generica(e))
        except (KeyError, TypeError, ValueError):
            ops.append({"ea": nome, "tipo": ev, "motivo": "evento ilegivel",
                        "t_saida": e["_t"], "t_entrada": None})
    return ops


# ------------------------------------------------------------------ tape
class Tape:
    """Tape do dia ordenado por chegada, com o atraso de cada negocio."""

    def __init__(self, ts_ns: np.ndarray, recv_ns: np.ndarray) -> None:
        ordem = np.argsort(recv_ns, kind="stable")
        self.recv = recv_ns[ordem]
        self.ts = ts_ns[ordem]
        self.lag = (self.recv - self.ts) / _NS          # segundos
        self.n = int(self.recv.size)

    def atraso_na_hora(self, t_ns: int, janela_s: float = 1.0) -> float | None:
        """Mediana de `ts_recv - ts` dos negocios que CHEGARAM a +-janela_s de
        t_ns (relogio de parede). None = nada chegou: o feed estava mudo."""
        i0 = int(np.searchsorted(self.recv, t_ns - int(janela_s * _NS)))
        i1 = int(np.searchsorted(self.recv, t_ns + int(janela_s * _NS)))
        return float(np.median(self.lag[i0:i1])) if i1 > i0 else None

    def por_minuto(self) -> pd.DataFrame:
        """Atraso por minuto de EVENTO (hora da bolsa), em Brasilia."""
        df = pd.DataFrame({"m": self.ts // (60 * _NS), "lag": self.lag})
        g = df.groupby("m")["lag"]
        out = pd.DataFrame({"n": g.size(), "p50": g.median(), "p99": g.quantile(0.99),
                            "max": g.max()})
        out["hhmm"] = [_brt(int(m) * 60 * _NS).strftime("%H:%M") for m in out.index]
        return out

    def incidentes(self, limiar_s: float = LIMIAR_ATRASO_S) -> list[dict[str, Any]]:
        pm = self.por_minuto()
        grupos: list[list[int]] = []
        for m in (int(x) for x in pm[pm["max"] >= limiar_s].index):
            if grupos and m - grupos[-1][-1] <= 1:
                grupos[-1].append(m)
            else:
                grupos.append([m])
        out: list[dict[str, Any]] = []
        for g in grupos:
            sub = pm.loc[g]
            out.append({"inicio": sub["hhmm"].iloc[0], "fim": sub["hhmm"].iloc[-1],
                        "minutos": len(g), "pico_s": float(sub["max"].max()),
                        "negocios": int(sub["n"].sum())})
        return out

    def buracos(self, dia: dt.date, limiar_s: float = LIMIAR_BURACO_S) -> list[dict[str, Any]]:
        """Intervalos sem NENHUMA chegada dentro do pregao."""
        def ns(hhmm: int) -> int:
            h, m = divmod(hhmm, 100)
            d0 = dt.datetime(dia.year, dia.month, dia.day, h, m, tzinfo=_TZ)
            return int(d0.timestamp()) * _NS
        i0 = int(np.searchsorted(self.recv, ns(SESSAO_HHMM[0])))
        i1 = int(np.searchsorted(self.recv, ns(SESSAO_HHMM[1])))
        r = self.recv[i0:i1]
        if r.size < 2:
            return []
        d = np.diff(r) / _NS
        return [{"inicio": _brt(int(r[i])).strftime("%H:%M:%S"), "duracao_s": float(d[i])}
                for i in np.nonzero(d >= limiar_s)[0]]


def carregar_tape(curated: Path, symbol: str, dia: dt.date) -> Tape | None:
    pasta = curated / "trade" / f"dt={dia.isoformat()}" / f"sym={symbol}"
    if not pasta.exists():
        return None
    df = pd.read_parquet(pasta, columns=["ts_ns", "ts_recv_ns"])
    if df.empty:
        return None
    return Tape(df["ts_ns"].to_numpy(dtype=np.int64), df["ts_recv_ns"].to_numpy(dtype=np.int64))


# ------------------------------------------------------- saude do record
def saude_record(eventos: list[dict[str, Any]]) -> dict[str, Any]:
    hb = [e for e in eventos if e.get("event") == "recorder.heartbeat"]
    out: dict[str, Any] = {"heartbeats": len(hb)}
    if len(hb) >= 2:
        t = np.array([e["_t"] for e in hb], dtype=np.int64)
        linhas = np.array([e.get("linhas", 0) for e in hb], dtype=float)
        dts = np.diff(t) / _NS
        taxa = np.diff(linhas) / np.maximum(dts, 1e-9)
        out.update({
            "maior_intervalo_s": float(dts.max()),
            "intervalos_acima_45s": int((dts > 45).sum()),
            "fila_max": int(max(e.get("fila", 0) for e in hb)),
            "fila_pico": int(max(e.get("fila_pico", 0) for e in hb)),
            "descartados": int(max(e.get("descartados", 0) for e in hb)),
            "sem_evento_max_s": float(max(e.get("sem_evento_ha_s", 0.0) for e in hb)),
            "linhas_s_mediana": float(np.median(taxa)),
            "linhas_s_min": float(taxa.min()), "linhas_s_max": float(taxa.max()),
        })
    return out


def ocorrencias(eventos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Avisos e erros agrupados por evento (o ruido repetitivo vira uma linha)."""
    c: Counter[tuple[str, str]] = Counter()
    primeiro: dict[tuple[str, str], int] = {}
    ultimo: dict[tuple[str, str], int] = {}
    for e in eventos:
        nivel = str(e.get("level", ""))
        if nivel not in ("warning", "error", "critical"):
            continue
        k = (nivel, str(e.get("event")))
        c[k] += 1
        primeiro.setdefault(k, e["_t"])
        ultimo[k] = e["_t"]
    return [{"nivel": k[0], "evento": k[1], "n": n,
             "primeiro": _brt(primeiro[k]).strftime("%H:%M:%S"),
             "ultimo": _brt(ultimo[k]).strftime("%H:%M:%S")}
            for k, n in sorted(c.items(), key=lambda kv: (kv[0][0] != "error", -kv[1]))]


def estados_dll(eventos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"hora": _brt(e["_t"]).strftime("%H:%M:%S"), "tipo": e.get("tipo"),
             "valor": e.get("valor")} for e in eventos if e.get("event") == "profitdll.estado"]


# ----------------------------------------------------------------- montar
def atribuicao(ops: list[dict[str, Any]]) -> dict[str, Any]:
    """Soma das parcelas das operacoes decompostas + o recorte dos stops."""
    dec = [o for o in ops if o.get("residuo") is not None]
    soma: dict[str, float] = {k: float(sum(o[k] for o in dec))
                              for k in ("ideal", "entrada_slip", "gap", "fill", "custo")}
    soma["pnl_liquido"] = float(sum(o["pnl_liquido"] for o in dec))
    stops = [o for o in dec if o["motivo"] == "stop"]
    def atrasada(o: dict[str, Any]) -> bool:
        a = o.get("atraso_saida_s")
        if a is None:                 # tape existe e nada chegou a +-1 s: feed mudo
            return bool(o.get("tape_disponivel"))
        return bool(a > JANELA_ATRASO_S)

    com_atraso = [o for o in dec if atrasada(o)]
    return {"operacoes_decompostas": len(dec), "soma": soma, "stops": len(stops),
            "stop_real_sobre_programado_mediano": (
                float(np.median([o["stop_real_sobre_programado"] for o in stops]))
                if stops else None),
            "ops_com_atraso_na_saida": len(com_atraso),
            "gap_mais_fill_com_atraso": float(sum(o["gap"] + o["fill"] for o in com_atraso)),
            "gap_mais_fill_sem_atraso": float(sum(o["gap"] + o["fill"] for o in dec
                                                  if o not in com_atraso))}


def montar(dia: dt.date, log: Path, curated: Path, symbol: str = "WINFUT",
           notas: str = "") -> dict[str, Any]:
    avisos: list[str] = []
    if not log.exists():
        raise SystemExit(f"log nao encontrado: {log}")
    eventos, ruins = ler_log(log, dia)
    if ruins:
        avisos.append(f"{ruins} linhas do log ilegiveis foram ignoradas")
    if not eventos:
        avisos.append(f"nenhum evento de {dia} em {log}")
    ops = extrair_operacoes(eventos)
    tape = carregar_tape(curated, symbol, dia)
    if tape is None:
        avisos.append("sem tape curado deste dia (rode depois do compact): atraso do feed "
                      "e buracos de chegada nao medidos")
    for o in ops:
        o["tape_disponivel"] = tape is not None
        if tape is not None:
            o["atraso_saida_s"] = tape.atraso_na_hora(o["t_saida"])
            o["atraso_entrada_s"] = (tape.atraso_na_hora(o["t_entrada"])
                                     if o.get("t_entrada") else None)
    dados: dict[str, Any] = {
        "dia": dia.isoformat(), "symbol": symbol,
        "gerado_em": dt.datetime.now(tz=_TZ).strftime("%d/%m/%Y %H:%M"),
        "operacoes": ops, "atribuicao": atribuicao(ops), "avisos": avisos,
        "saude": saude_record(eventos), "ocorrencias": ocorrencias(eventos),
        "estados_dll": estados_dll(eventos), "notas": notas,
        "tape": None, "incidentes": [], "buracos": [], "por_minuto": [],
    }
    if tape is not None:
        pm = tape.por_minuto()
        dados["tape"] = {"negocios": tape.n, "atraso_p50": float(np.median(tape.lag)),
                         "atraso_p99": float(np.quantile(tape.lag, 0.99)),
                         "atraso_max": float(tape.lag.max())}
        dados["incidentes"] = tape.incidentes()
        dados["buracos"] = tape.buracos(dia)
        dados["por_minuto"] = [
            {"hhmm": str(h), "p50": float(a), "max": float(b)}
            for h, a, b in zip(pm["hhmm"].tolist(), pm["p50"].tolist(), pm["max"].tolist(),
                               strict=True)]
    return dados


# -------------------------------------------------------------------- CSV
_COLUNAS_OPS = ["dia", "ea", "tipo", "lado", "motivo", "hora_saida", "entrada", "saida",
                "pnl_bruto", "pnl_liquido", "duracao_s", "ideal", "entrada_slip", "gap", "fill",
                "custo", "residuo", "stop_pts", "alvo_pts", "stop_real_sobre_programado",
                "atraso_entrada_s", "atraso_saida_s", "fill_origem", "slippage_ordens_pts",
                "latencia_fill_max_ms"]


def _atualiza_csv(caminho: Path, novas: pd.DataFrame, dia: str) -> None:
    if caminho.exists():
        antigas = pd.read_csv(caminho)
        antigas = antigas[antigas["dia"].astype(str) != dia]
        novas = pd.concat([antigas, novas], ignore_index=True) if len(antigas) else novas
    novas.to_csv(caminho, index=False)


def gravar_csv(dados: dict[str, Any], pasta: Path) -> None:
    """Acumula por dia (reexecutar o mesmo dia SUBSTITUI as linhas dele)."""
    pasta.mkdir(parents=True, exist_ok=True)
    dia = dados["dia"]
    linhas = []
    for o in dados["operacoes"]:
        r: dict[str, Any] = {k: o.get(k) for k in _COLUNAS_OPS}
        r.update({"dia": dia, "hora_saida": _brt(o["t_saida"]).strftime("%H:%M:%S")})
        linhas.append(r)
    _atualiza_csv(pasta / "operacoes.csv",
                  pd.DataFrame(linhas, columns=_COLUNAS_OPS), dia)
    inc = [{"dia": dia, **i} for i in dados["incidentes"]]
    bur = [{"dia": dia, "tipo": "buraco", "inicio": b["inicio"], "duracao_s": b["duracao_s"]}
           for b in dados["buracos"]]
    _atualiza_csv(pasta / "incidentes.csv",
                  pd.DataFrame(inc + bur, columns=["dia", "inicio", "fim", "minutos", "pico_s",
                                                   "negocios", "tipo", "duracao_s"]), dia)
    a, t, s = dados["atribuicao"], dados["tape"] or {}, dados["saude"]
    ops = dados["operacoes"]
    resumo = {"dia": dia, "operacoes": len(ops),
              "pnl_liquido": float(sum(o["pnl_liquido"] or 0 for o in ops)),
              "stops": a["stops"],
              "stop_real_sobre_programado_mediano": a["stop_real_sobre_programado_mediano"],
              "gap": a["soma"]["gap"], "fill": a["soma"]["fill"],
              "atraso_p50": t.get("atraso_p50"), "atraso_p99": t.get("atraso_p99"),
              "atraso_max": t.get("atraso_max"), "incidentes": len(dados["incidentes"]),
              "buracos": len(dados["buracos"]), "fila_max": s.get("fila_max"),
              "maior_intervalo_hb_s": s.get("maior_intervalo_s"),
              "descartados": s.get("descartados")}
    _atualiza_csv(pasta / "dias.csv", pd.DataFrame([resumo]), dia)


def ler_notas(pasta: Path, dia: dt.date) -> str:
    f = pasta / "notas" / f"{dia.isoformat()}.md"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def anotar(pasta: Path, dia: dt.date, texto: str) -> None:
    f = pasta / "notas" / f"{dia.isoformat()}.md"
    f.parent.mkdir(parents=True, exist_ok=True)
    hora = dt.datetime.now(tz=_TZ).strftime("%H:%M")
    with f.open("a", encoding="utf-8") as fh:
        fh.write(f"- {hora} {texto.strip()}\n")
