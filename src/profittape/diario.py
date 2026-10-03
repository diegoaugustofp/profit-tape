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
# Negocio que chega com mais de 1 h de atraso nao e' feed: e' dado IMPORTADO depois (historico
# recuperado). 01-14/09: dia + atraso = 15/09 em todos (lote unico); 18/09 reapareceu em 21/09.
LIMIAR_RECUPERADO_S = 3600.0
JANELA_ATRASO_S = 2.0            # atraso "relevante" na hora da saida
SESSAO_HHMM = (900, 1830)
# EAs com veredito "descartado" que ainda estao na pasta de EAs ativos: seguem
# registrados (o dado fica no CSV) mas FORA dos totais. microprice: taker descartado em
# 25/09; passiva pendente de modelo de fila (docs/eas/microprice.md).
DESCARTADOS = ("ea_microprice", "ea_microprice_passiva")
_RE_SAIDA_GENERICA = re.compile(r"ea\.[a-z0-9_]+\.(saida|operacao_fechada)")


# --------------------------------------------------------------------- log
def _utc_ns(ts: str) -> int:
    d = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return int(d.timestamp()) * _NS + d.microsecond * 1000


def _brt(t_ns: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(t_ns / 1e9, tz=_TZ)


def ler_log_varios(caminho: Path, dias: set[dt.date]
                   ) -> tuple[dict[dt.date, list[dict[str, Any]]], int]:
    """UMA passada no log para varios dias de Brasilia (o log guarda meses; o
    modo retroativo nao pode reler o arquivo inteiro por dia). Devolve
    ({dia: eventos em ordem}, linhas_invalidas)."""
    prefixos = {d.isoformat() for x in dias for d in (x, x + dt.timedelta(days=1))}
    por_dia: dict[dt.date, list[dict[str, Any]]] = {d: [] for d in dias}
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
            alvo = _brt(t).date()
            if alvo in por_dia:
                d["_t"] = t
                por_dia[alvo].append(d)
    for ev in por_dia.values():
        ev.sort(key=lambda e: e["_t"])
    return por_dia, ruins


def ler_log(caminho: Path, dia: dt.date) -> tuple[list[dict[str, Any]], int]:
    """Eventos do `dia` (data de Brasilia), em ordem. Devolve (eventos,
    linhas_invalidas)."""
    por_dia, ruins = ler_log_varios(caminho, {dia})
    return por_dia[dia], ruins


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


def _carimbo(e: dict[str, Any]) -> dict[str, Any]:
    """sha do YAML e tag de codigo que o EA carimba no log (ignicao/vwap_vp: config_sha; 123:
    yaml_sha256). Sem eles a pagina do EA nao sabe sob qual configuracao rodou."""
    return {"config_sha": e.get("config_sha") or e.get("yaml_sha256"),
            "codigo": e.get("codigo")}


def _f(e: dict[str, Any], k: str) -> float | None:
    v = e.get(k)
    return None if v is None else float(v)


def _op_ign(s: dict[str, Any], ent: dict[str, Any] | None) -> dict[str, Any]:
    op: dict[str, Any] = {"ea": s.get("nome"), "tipo": "ignicao", "lado": int(s["lado"]),
                          "motivo": str(s["motivo"]), "t_saida": s["_t"],
                          "t_entrada": ent["_t"] if ent else None,
                          "entrada": _f(s, "entrada"), "saida": _f(s, "saida"),
                          "saida_tape": _f(s, "saida_tape"),
                          "preco_ref": _f(s, "preco_deteccao"),
                          "pnl_bruto": _f(s, "pnl_bruto"), "pnl_liquido": _f(s, "pnl_liquido"),
                          "duracao_s": _f(s, "duracao_s"), "fill_origem": s.get("fill_origem"),
                          "atraso_log_entrada_s": _f(ent, "atraso_s") if ent else None,
                          "ancora": s.get("ancora"), **_carimbo(s)}
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
                          "saida_tape": _f(s, "saida"),
                          "preco_ref": _f(sin, "close") if sin else None,
                          "pnl_bruto": _f(s, "pnl_bruto"), "pnl_liquido": _f(s, "pnl_liquido"),
                          "duracao_s": _f(s, "duracao_s"), "fill_origem": "tape",
                          "hhmm_sinal": s.get("hhmm_sinal"), **_carimbo(s)}
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
    nome = e.get("nome")
    if not nome:
        nome = e["event"].split(".")[1]
        if nome == "123" and e.get("desfecho") != "nao_executou":
            # o log do ciclo do 123 NAO traz o nome do EA: ordens reais => a instancia E4
            nome = "123 (E4)" if ordens else "123 (dry_run)"
    return {"ea": nome, "tipo": e["event"],
            "lado": e.get("lado"), "motivo": e.get("motivo") or e.get("desfecho"),
            "t_saida": e["_t"], "t_entrada": None,
            "pnl_liquido": None if pnl is None else float(pnl),
            "slippage_ordens_pts": float(sum(slip)) if slip else None,
            "latencia_fill_max_ms": float(max(lat)) if lat else None, **_carimbo(e)}


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

    def __init__(self, ts_ns: np.ndarray, recv_ns: np.ndarray,
                 preco: np.ndarray | None = None) -> None:
        ordem = np.argsort(recv_ns, kind="stable")
        self.recv = recv_ns[ordem]
        self.ts = ts_ns[ordem]
        bruto = (self.recv - self.ts) / _NS              # segundos, com o desvio do relogio
        # Relogio local ATRASADO em relacao a bolsa => `ts_recv - ts` negativo (visto em
        # 30/09: mediana -1,02 s; 01/10: -0,11 s). O piso do atraso verdadeiro e' ~0, entao o
        # 1o percentil, se negativo, mede o desvio; parada so' ADICIONA atraso, nao o move.
        self.offset = float(min(np.quantile(bruto, 0.01), 0.0)) if bruto.size else 0.0
        self.lag = bruto - self.offset                   # corrigido (>= ~0)
        self.vivo = self.lag <= LIMIAR_RECUPERADO_S       # False = importado depois (backfill)
        self.n_recuperados = int((~self.vivo).sum())
        self.pct_recuperado = self.n_recuperados / bruto.size if bruto.size else 0.0
        self.n = int(self.recv.size)
        self._ts_ord: np.ndarray | None = None
        self._ts_orig, self._px = ts_ns, preco
        self._ev: tuple[np.ndarray, np.ndarray] | None = None   # por hora de EVENTO, sob demanda

    def preco_em(self, t_ns: int) -> float | None:
        """Preco do ultimo negocio com hora de EVENTO <= t_ns (o mercado naquele
        instante, como a bolsa o viu). None sem coluna de preco ou antes do 1o."""
        if self._px is None:
            return None
        if self._ev is None:
            o = np.argsort(self._ts_orig, kind="stable")
            self._ev = (self._ts_orig[o], self._px[o])
        ts, px = self._ev
        i = int(np.searchsorted(ts, t_ns, side="right")) - 1
        return float(px[i]) if i >= 0 else None

    def atraso_na_hora(self, t_ns: int, janela_s: float = 1.0) -> float | None:
        """Mediana de `ts_recv - ts` dos negocios que CHEGARAM a +-janela_s de
        t_ns (relogio de parede). None = nada chegou: o feed estava mudo."""
        i0 = int(np.searchsorted(self.recv, t_ns - int(janela_s * _NS)))
        i1 = int(np.searchsorted(self.recv, t_ns + int(janela_s * _NS)))
        return float(np.median(self.lag[i0:i1])) if i1 > i0 else None

    def por_minuto(self) -> pd.DataFrame:
        """Atraso por minuto de EVENTO (hora da bolsa), em Brasilia."""
        df = pd.DataFrame({"m": self.ts // (60 * _NS), "lag": self.lag})[self.vivo]
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
        """Intervalos sem NENHUMA chegada dentro do pregao, classificados pela hora de
        EVENTO: houve negocios na bolsa nesse intervalo (a entrega e' que parou) ou nao
        (leilao / parada de negociacao)?"""
        def ns(hhmm: int) -> int:
            h, m = divmod(hhmm, 100)
            d0 = dt.datetime(dia.year, dia.month, dia.day, h, m, tzinfo=_TZ)
            return int(d0.timestamp()) * _NS
        if self.pct_recuperado >= 0.5:      # dia gravado por importacao: chegadas em blocos
            return []
        i0 = int(np.searchsorted(self.recv, ns(SESSAO_HHMM[0])))
        i1 = int(np.searchsorted(self.recv, ns(SESSAO_HHMM[1])))
        r = self.recv[i0:i1]
        if r.size < 2:
            return []
        if self._ts_ord is None:
            self._ts_ord = np.sort(self.ts)
        d = np.diff(r) / _NS
        out: list[dict[str, Any]] = []
        for i in np.nonzero(d >= limiar_s)[0]:
            a, b = int(r[i]), int(r[i + 1])
            n_ev = max(0, int(np.searchsorted(self._ts_ord, b - _NS))
                       - int(np.searchsorted(self._ts_ord, a + _NS)))
            out.append({"inicio": _brt(a).strftime("%H:%M:%S"), "duracao_s": float(d[i]),
                        "negocios_no_intervalo": n_ev,
                        "classe": ("entrega atrasada" if n_ev > 0
                                   else "sem negocios (leilao/parada)")})
        return out


def ler_tape(curated: Path, symbol: str, dia: dt.date) -> tuple[Tape | None, str | None]:
    """(tape, motivo_se_nao_houver). Dia antigo ou gravacao ruim nao derruba o
    diario: devolve None e diz por que."""
    pasta = curated / "trade" / f"dt={dia.isoformat()}" / f"sym={symbol}"
    if not pasta.exists():
        return None, "sem tape curado deste dia (rode depois do compact)"
    for cols in (["ts_ns", "ts_recv_ns", "price"], ["ts_ns", "ts_recv_ns"]):
        try:
            df = pd.read_parquet(pasta, columns=cols)
        except Exception as exc:   # coluna ausente em dia antigo, parquet corrompido, etc.
            erro = repr(exc)
            continue
        if df.empty:
            return None, "tape curado vazio"
        px = df["price"].to_numpy(dtype=np.float64) if "price" in df else None
        return (Tape(df["ts_ns"].to_numpy(dtype=np.int64),
                     df["ts_recv_ns"].to_numpy(dtype=np.int64), px), None)
    return None, f"tape ilegivel ({erro[:80]})"


def carregar_tape(curated: Path, symbol: str, dia: dt.date) -> Tape | None:
    return ler_tape(curated, symbol, dia)[0]


def custo_atraso(tape: Tape, o: dict[str, Any]) -> None:
    """Custo CONTRAFACTUAL do atraso (pontos; positivo = pior), SO' para operacao cujo
    fill e' o preco do tape (vwap_vp em dry_run; ignicao sem livro utilizavel) --
    ai' o atraso nao muda o P&L simulado. Numa execucao real o
    EA so' sabe do gatilho L segundos depois; a ordem a mercado encontra o
    mercado de AGORA:
        saida   = (preco do gatilho - preco do tape na hora do processamento) * L
        entrada = (preco do tape na hora do processamento - preco do tape L antes) * L
    Saida no alvo = ordem limite ja' no livro: o atraso nao pesa (None)."""
    lado = o.get("lado")
    o["custo_atraso_saida_est"] = o["custo_atraso_entrada_est"] = None
    if lado not in (1, -1) or o.get("fill_origem") == "livro":
        return          # fill do livro no instante do processamento: o atraso JA' esta' em
                        # `fill` e `entrada_slip` (medido); somar aqui seria contar duas vezes
    la = o.get("atraso_saida_s")
    p_trig = o.get("saida_tape")
    if la is not None and p_trig is not None and o.get("motivo") != "alvo":
        p_agora = tape.preco_em(o["t_saida"])
        if p_agora is not None:
            o["custo_atraso_saida_est"] = (float(p_trig) - p_agora) * lado
    le = o.get("atraso_entrada_s")
    if le is not None and o.get("t_entrada"):
        p_agora = tape.preco_em(o["t_entrada"])
        p_antes = tape.preco_em(o["t_entrada"] - int(le * _NS))
        if p_agora is not None and p_antes is not None:
            o["custo_atraso_entrada_est"] = (p_agora - p_antes) * lado


# ------------------------------------------------------- saude do record
def _no_pregao(t_ns: int) -> bool:
    d = _brt(t_ns)
    return SESSAO_HHMM[0] <= d.hour * 100 + d.minute < SESSAO_HHMM[1]


def saude_record(eventos: list[dict[str, Any]]) -> dict[str, Any]:
    """So' o PREGAO (09:00-18:30 BRT): fora dele nao chega evento e `sem_evento_ha_s` cresce
    sem que nada esteja errado (v4.16 mostrava 3.198 s e linhas/s minimo 0 por isso)."""
    hb = [e for e in eventos
          if e.get("event") == "recorder.heartbeat" and _no_pregao(e["_t"])]
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
    """Estados da DLL com nome e descricao do manual; repeticoes consecutivas iguais no
    mesmo segundo (rajada da subida) viram uma linha com `vezes`."""
    from .dll_estados import descrever

    out: list[dict[str, Any]] = []
    for e in eventos:
        if e.get("event") != "profitdll.estado":
            continue
        hora = _brt(e["_t"]).strftime("%H:%M:%S")
        tipo_txt, nome, desc, grave = descrever(e.get("tipo"), e.get("valor"))
        chave = (hora, tipo_txt, nome)
        if out and (out[-1]["hora"], out[-1]["tipo_txt"], out[-1]["nome"]) == chave:
            out[-1]["vezes"] += 1
            continue
        out.append({"hora": hora, "t": e["_t"], "tipo": e.get("tipo"), "valor": e.get("valor"),
                    "tipo_txt": tipo_txt, "nome": nome, "descricao": desc, "grave": grave,
                    "vezes": 1})
    return out


def supervisor_do_dia(eventos: list[dict[str, Any]]) -> dict[str, Any]:
    """Capital em conta e capital recomendado por EA, do ULTIMO `ea.supervisor.resumo` do dia."""
    ult = [e for e in eventos if e.get("event") == "ea.supervisor.resumo"]
    if not ult:
        return {}
    e = ult[-1]
    por_ea = e.get("por_ea")
    return {"capital_em_conta": e.get("capital_em_conta"),
            "por_ea": por_ea if isinstance(por_ea, dict) else {}}


RUIDO_CONHECIDO = {"ea.cancel_todas_recusado", "ea.123.limpeza_na_subida",
                   "ea.123.limpeza_na_subida_desistiu"}


def contexto_incidente(dia: dt.date, inc: dict[str, Any], eventos: list[dict[str, Any]],
                       estados: list[dict[str, Any]], antes_min: int = 10) -> dict[str, Any]:
    """O que o log diz em volta de um incidente de atraso: estados GRAVES da DLL (de 2 min
    antes ao fim) e avisos/erros dos `antes_min` minutos que o precedem (sem o ruido ja'
    conhecido). Mostra a associacao; nao a declara causa."""
    def ns(hhmm: str, extra_s: int = 0) -> int:
        h, m = (int(x) for x in hhmm.split(":"))
        d0 = dt.datetime(dia.year, dia.month, dia.day, h, m, tzinfo=_TZ)
        return int(d0.timestamp()) * _NS + extra_s * _NS
    ini, fim = ns(inc["inicio"]), ns(inc["fim"], 60)
    dll = [f"{x['hora']} {x['nome']}" for x in estados
           if x.get("grave") and ini - 120 * _NS <= x["t"] <= fim + 120 * _NS]
    c: Counter[str] = Counter()
    for e in eventos:
        if (str(e.get("level")) in ("warning", "error") and ini - antes_min * 60 * _NS <= e["_t"]
                <= ini + 60 * _NS and str(e.get("event")) not in RUIDO_CONHECIDO):
            c[str(e.get("event"))] += 1
    return {"dll": dll, "avisos_antes": [f"{k} x{v}" for k, v in c.most_common(3)]}


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
                                                  if o not in com_atraso)),
            "custo_atraso_est": float(sum((o.get("custo_atraso_saida_est") or 0)
                                          + (o.get("custo_atraso_entrada_est") or 0)
                                          for o in ops)),
            "ops_com_fill_do_tape": sum(1 for o in dec if o.get("fill_origem") == "tape")}


def montar(dia: dt.date, log: Path, curated: Path, symbol: str = "WINFUT",
           notas: str = "",
           eventos_pre: tuple[list[dict[str, Any]], int] | None = None,
           descartados: tuple[str, ...] = DESCARTADOS) -> dict[str, Any]:
    avisos: list[str] = []
    if eventos_pre is None:
        if not log.exists():
            raise SystemExit(f"log nao encontrado: {log}")
        eventos, ruins = ler_log(log, dia)
    else:
        eventos, ruins = eventos_pre
    if ruins:
        avisos.append(f"{ruins} linhas do log ilegiveis foram ignoradas")
    if not eventos:
        avisos.append(f"nenhum evento de {dia} em {log}")
    todas = extrair_operacoes(eventos)
    nao_exec = [o for o in todas if o.get("motivo") == "nao_executou"]
    ops_all = [o for o in todas if o.get("motivo") != "nao_executou"]
    for o in ops_all:
        o["descartado"] = o.get("ea") in descartados
    ops = [o for o in ops_all if not o["descartado"]]
    desc = [o for o in ops_all if o["descartado"]]
    tape, motivo = ler_tape(curated, symbol, dia)
    if tape is None:
        avisos.append(f"{motivo}: atraso do feed, buracos de chegada e custo do atraso "
                      "nao medidos")
    for o in ops_all:
        o["tape_disponivel"] = tape is not None
        if tape is not None:
            o["atraso_saida_s"] = tape.atraso_na_hora(o["t_saida"])
            o["atraso_entrada_s"] = (tape.atraso_na_hora(o["t_entrada"])
                                     if o.get("t_entrada") else None)
            custo_atraso(tape, o)
    dados: dict[str, Any] = {
        "dia": dia.isoformat(), "symbol": symbol, "n_eventos": len(eventos),
        "gerado_em": dt.datetime.now(tz=_TZ).strftime("%d/%m/%Y %H:%M"),
        "operacoes": ops, "ops_descartadas": desc,
        "nao_executadas": [
            {"ea": o.get("ea"), "hora": _brt(o["t_saida"]).strftime("%H:%M:%S")}
            for o in nao_exec],
        "atribuicao": atribuicao(ops), "avisos": avisos,
        "saude": saude_record(eventos), "ocorrencias": ocorrencias(eventos),
        "estados_dll": estados_dll(eventos), "notas": notas,
        "supervisor": supervisor_do_dia(eventos),
        "tape": None, "incidentes": [], "buracos": [], "por_minuto": [],
    }
    if tape is not None:
        pm = tape.por_minuto()
        lv = tape.lag[tape.vivo]
        dados["tape"] = {"negocios": tape.n, "offset_relogio_s": tape.offset,
                         "recuperados": tape.n_recuperados,
                         "pct_recuperado": tape.pct_recuperado,
                         "atraso_p50": float(np.median(lv)) if lv.size else None,
                         "atraso_p99": float(np.quantile(lv, 0.99)) if lv.size else None,
                         "atraso_max": float(lv.max()) if lv.size else None}
        if tape.pct_recuperado > 0:
            avisos.append(
                f"{tape.pct_recuperado:.1%} dos negocios ({tape.n_recuperados:,}) chegaram com "
                f"mais de {LIMIAR_RECUPERADO_S / 3600:.0f} h de atraso: sao dado IMPORTADO depois "
                "(historico recuperado), nao feed ao vivo. Ficam fora das estatisticas de "
                "atraso e dos incidentes" + ("; buracos de chegada nao medidos neste dia."
                                             if tape.pct_recuperado >= 0.5 else "."))
        dados["incidentes"] = tape.incidentes()
        for i in dados["incidentes"]:
            i.update(contexto_incidente(dia, i, eventos, dados["estados_dll"]))
        dados["buracos"] = tape.buracos(dia)
        dados["por_minuto"] = [
            {"hhmm": str(h), "p50": float(a), "max": float(b)}
            for h, a, b in zip(pm["hhmm"].tolist(), pm["p50"].tolist(), pm["max"].tolist(),
                               strict=True)]
    return dados


# -------------------------------------------------------------------- CSV
_COLUNAS_OPS = [
    "dia", "ea", "descartado", "tipo", "lado", "motivo", "hora_saida", "entrada", "saida",
    "pnl_bruto", "pnl_liquido", "duracao_s", "ideal", "entrada_slip", "gap", "fill", "custo",
    "residuo", "stop_pts", "alvo_pts", "stop_real_sobre_programado", "atraso_entrada_s",
    "atraso_saida_s", "custo_atraso_entrada_est", "custo_atraso_saida_est", "saida_tape",
    "fill_origem", "slippage_ordens_pts", "latencia_fill_max_ms", "config_sha", "codigo"]


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
    for o in dados["operacoes"] + dados["ops_descartadas"]:
        r: dict[str, Any] = {k: o.get(k) for k in _COLUNAS_OPS}
        r.update({"dia": dia, "hora_saida": _brt(o["t_saida"]).strftime("%H:%M:%S")})
        linhas.append(r)
    _atualiza_csv(pasta / "operacoes.csv",
                  pd.DataFrame(linhas, columns=_COLUNAS_OPS), dia)
    inc = [{"dia": dia, **i} for i in dados["incidentes"]]
    bur = [{"dia": dia, "tipo": f"buraco: {b['classe']}", "inicio": b["inicio"],
            "duracao_s": b["duracao_s"]} for b in dados["buracos"]]
    _atualiza_csv(pasta / "incidentes.csv",
                  pd.DataFrame(inc + bur, columns=["dia", "inicio", "fim", "minutos", "pico_s",
                                                   "negocios", "tipo", "duracao_s"]), dia)
    sup = dados.get("supervisor") or {}
    cfg_rows = [{"dia": dia, "ea": nome, "capital_recomendado": v.get("capital_recomendado"),
                 "contratos": v.get("contratos"), "ticker": v.get("ticker"),
                 "capital_em_conta": sup.get("capital_em_conta")}
                for nome, v in (sup.get("por_ea") or {}).items()]
    _atualiza_csv(pasta / "eas_config.csv",
                  pd.DataFrame(cfg_rows, columns=["dia", "ea", "capital_recomendado", "contratos",
                                                  "ticker", "capital_em_conta"]), dia)
    a, t, s = dados["atribuicao"], dados["tape"] or {}, dados["saude"]
    ops = dados["operacoes"]
    desc = dados["ops_descartadas"]
    resumo = {"dia": dia, "operacoes": len(ops),
              "pnl_liquido": float(sum(o["pnl_liquido"] or 0 for o in ops)),
              "n_descartados": len(desc),
              "pnl_descartados": float(sum(o["pnl_liquido"] or 0 for o in desc)),
              "sinais_sem_execucao": len(dados["nao_executadas"]),
              "offset_relogio_s": t.get("offset_relogio_s"),
              "stops": a["stops"],
              "stop_real_sobre_programado_mediano": a["stop_real_sobre_programado_mediano"],
              "gap": a["soma"]["gap"], "fill": a["soma"]["fill"],
              "custo_atraso_est": a["custo_atraso_est"],
              "pct_recuperado": t.get("pct_recuperado"),
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


def linha_resumo_dia(dia: dt.date, dados: dict[str, Any]) -> str:
    """Linha de console do dia. Atraso pode ser None (dia importado depois, sem negocio ao
    vivo): em v4.15 o `:.1f` direto derrubou a rodada retroativa no 1o dia importado."""
    ops = dados["operacoes"]
    t = dados["tape"]
    s = (f"diario {dia}: {len(ops)} operacao(oes), "
         f"P&L liquido {sum((o.get('pnl_liquido') or 0) for o in ops):+.0f} pts, "
         f"{len(dados['incidentes'])} incidente(s) de atraso, "
         f"{len(dados['buracos'])} buraco(s) de chegada")
    if t and t.get("atraso_p99") is not None and t.get("atraso_max") is not None:
        s += f", atraso p99 {t['atraso_p99']:.1f} s, max {t['atraso_max']:.0f} s"
    elif t:
        s += f", {t.get('pct_recuperado', 0):.0%} importado depois (sem atraso ao vivo)"
    if dados["ops_descartadas"]:
        s += f" [+{len(dados['ops_descartadas'])} de EA descartado fora do total]"
    return s

