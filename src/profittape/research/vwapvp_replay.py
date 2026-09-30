"""
F2 do EA vwap_vp (docs/eas/vwap_vp.md): REPLAY do Setup B sobre o tape
curado, para fechar as linhas TAXA / HORIZONTE / EFEITO da ficha ANTES de
escrever o EA.

O que este modulo mede (e nada mais)
------------------------------------
1. DISTRIBUICAO do estimador de absorcao por barra M5 na amostra queimada
   (percentis 50/80/90/95): o limiar p80 e' congelado como VALOR (D5),
   nunca recalculado ao vivo.
2. EVENTOS por clausula, acumulando: banda (|z_vwap| >= 2) -> nivel
   (|close - VAH/VAL de ontem| <= tolerancia) -> absorcao (>= p80) ->
   janela horaria. Por dia e por HORA do dia -- a banda dobra de largura
   entre 10h e 12h (F1), entao "z = 2" nao e' a mesma coisa o dia inteiro.
3. SONDA nos episodios (barras consecutivas colapsadas com cooldown): a
   partir do fechamento da barra de sinal, excursao a FAVOR (em direcao
   a VWAP) e CONTRA em pontos, e se tocou a VWAP, em varios horizontes.
   E' o dado que reescreve a linha EFEITO: a distancia banda -> VWAP e'
   de 1.000+ pts a partir de 12h (F1) e o binario "VWAP antes do stop"
   com stop de 50 nao significa nada.
4. Diferenca de VAL/VAH entre os dois algoritmos da area de valor (bin a
   bin x pares), porque o Profit nao marca VAL/VAH e a escolha nao e'
   conferivel na tela.

O que NAO faz: nao decide, nao escolhe limiar por resultado, nao varre
grade. A unica grade e' a de HORIZONTES da sonda, declarada.

Estimador de absorcao (o que ja' existe, `absorcao_dir.ntsl` /
`research/absorcao_barra.py`, REPROVADO sozinho em 30/08 -- aqui e' gate
em local, hipotese diferente):

    imbalance    = (agr_compra - agr_venda) / (agr_compra + agr_venda)
    desloc_norm  = (close - open) / (high - low)
    absorcao_dir = imbalance - desloc_norm
    z            = (x - media[1..J]) / desvio[1..J]      J = 50 barras

Lado: venda em +2SD quer compradores absorvidos (imbalance > 0, preco nao
sobe -> absorcao_dir > 0); compra em -2SD quer o espelho (< 0). O
`estimador` da distribuicao e' `z * sinal(z_vwap)`, positivo quando a
absorcao esta' do lado do setup.

OHLC da barra: `barra_tempo` usa TODOS os negocios (e' o do grafico);
imbalance usa so' 2/3. E' o mesmo desenho do NTSL.
"""

from __future__ import annotations

import datetime as dt
import math
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import structlog

from ..ea.barra_tempo import ConstrutorDeBarraDeTempo
from ..ea.perfil_preco import dia_de_referencia, dias_disponiveis, perfil_do_dia
from ..ea.sinal import BarraFechada
from ..ea.vwap_sessao import VWAPSessao

log = structlog.get_logger(__name__)
_TZ = ZoneInfo("America/Sao_Paulo")
_NS = 1_000_000_000

CLAUSULAS = ("banda", "nivel", "absorcao_p80", "janela")   # acumulativas, nesta ordem
SUBGRUPOS = ("absorcao_p90",)                              # declarados na ficha; nenhum outro


@dataclass(frozen=True)
class ParametrosReplay:
    bin_pts: float = 25.0
    pct: float = 0.70
    periodo_s: int = 300
    janela_z: int = 50
    z_banda: float = 2.0
    tolerancia_pts: float = 25.0
    hhmm_inicio: int = 930
    hhmm_fim: int = 1700
    cooldown_s: int = 1800
    horizontes_s: tuple[int, ...] = (300, 900, 1800, 3600)
    percentil_gatilho: int = 80
    percentil_subgrupo: int = 90


# ---------------------------------------------------------------- utilitarios
def absorcao_dir(b: BarraFechada) -> float | None:
    va = b.vol_agr_compra + b.vol_agr_venda
    amp = b.high - b.low
    if va <= 0 or amp <= 0:
        return None
    return (b.vol_agr_compra - b.vol_agr_venda) / va - (b.close - b.open) / amp


class ZRolante:
    """z de x contra as J observacoes ANTERIORES (media[1..J] do NTSL)."""

    def __init__(self, janela: int) -> None:
        self._h: deque[float] = deque(maxlen=janela)
        self.janela = janela

    def z(self, x: float) -> float | None:
        if len(self._h) < self.janela:
            return None
        m = sum(self._h) / self.janela
        var = sum((v - m) ** 2 for v in self._h) / self.janela
        if var <= 0:
            return None
        return (x - m) / math.sqrt(var)

    def empurrar(self, x: float) -> None:
        self._h.append(x)


def _hhmm(ts_ns: int) -> int:
    t = dt.datetime.fromtimestamp(ts_ns / 1e9, tz=_TZ)
    return t.hour * 100 + t.minute


# ------------------------------------------------------------------ um dia
@dataclass
class DiaReplay:
    dia: str
    referencia: str | None
    barras: pd.DataFrame
    trades_ts: np.ndarray
    trades_px: np.ndarray
    ref: dict[str, Any] = field(default_factory=dict)


def _barras_do_dia(curated: Path, symbol: str, dia: dt.date, p: ParametrosReplay,
                   cache_dir: Path | None) -> DiaReplay | None:
    from ..features.pipeline import _carregar_dia

    pasta = curated / "trade" / f"dt={dia.isoformat()}"
    if not (pasta / f"sym={symbol}").exists():
        return None
    t = _carregar_dia(pasta, symbol)
    if t.empty:
        return None

    ref_dia = dia_de_referencia(curated, symbol, dia)
    ref: dict[str, Any] = {}
    if ref_dia is not None:
        perfil = perfil_do_dia(curated, symbol, ref_dia, p.bin_pts, None, cache_dir)
        if not perfil.vazio:
            va = perfil.area_de_valor(p.pct, "bin")
            vp = perfil.area_de_valor(p.pct, "pares")
            pf = perfil.poc_faixa()
            assert va is not None and vp is not None and pf is not None
            ref = {"dia": ref_dia.isoformat(), "poc": perfil.poc(),
                   "poc_faixa": pf, "val": va[0], "vah": va[1],
                   "val_pares": vp[0], "vah_pares": vp[1]}

    vwap = VWAPSessao()
    c = ConstrutorDeBarraDeTempo(p.periodo_s)
    zr = ZRolante(p.janela_z)
    linhas: list[dict[str, Any]] = []

    def fechar(b: BarraFechada) -> None:
        vw, sd = vwap.vwap, vwap.desvio
        z_vwap = None if vw is None or not sd else (b.close - vw) / sd
        a = absorcao_dir(b)
        z_abs = None if a is None else zr.z(a)
        if a is not None:
            zr.empurrar(a)
        linhas.append({
            "ts_close_ns": b.ts_close_ns, "hhmm": _hhmm(b.ts_close_ns - 1),
            "open": b.open, "high": b.high, "low": b.low, "close": b.close,
            "vol_total": b.vol_total, "vol_agr_compra": b.vol_agr_compra,
            "vol_agr_venda": b.vol_agr_venda, "volume_confiavel": b.volume_confiavel,
            "vwap": vw, "sd": sd, "z_vwap": z_vwap,
            "absorcao": a, "z_absorcao": z_abs,
        })

    ts = t["ts_ns"].to_numpy(dtype=np.int64)
    px = t["price"].to_numpy(dtype=np.float64)
    for ts_ns, price, qtd, tipo in t[["ts_ns", "price", "quantidade",
                                      "trade_type"]].itertuples(index=False):
        b = c.processar_trade(int(ts_ns), float(price), int(qtd), int(tipo))
        if b is not None:
            fechar(b)
        vwap.registrar(float(price), int(qtd))
    fim = c.avancar_relogio(int(ts[-1]) + p.periodo_s * _NS)
    if fim is not None:
        fechar(fim)

    df = pd.DataFrame(linhas)
    df["dia"] = dia.isoformat()
    if ref:
        df["dist_vah"] = df["close"] - ref["vah"]
        df["dist_val"] = df["close"] - ref["val"]
    else:
        df["dist_vah"] = np.nan
        df["dist_val"] = np.nan
    return DiaReplay(dia.isoformat(), ref.get("dia"), df, ts, px, ref)


# --------------------------------------------------------- clausulas/episodios
def _marcar_clausulas(df: pd.DataFrame, p: ParametrosReplay,
                      p80: float, p90: float) -> pd.DataFrame:
    d = df.copy()
    z = d["z_vwap"]
    d["lado"] = np.where(z >= p.z_banda, -1, np.where(z <= -p.z_banda, 1, 0))  # -1 venda, +1 compra
    d["estimador"] = d["z_absorcao"] * np.sign(z.fillna(0.0))
    d["c_banda"] = d["lado"] != 0
    perto = np.where(d["lado"] == -1, d["dist_vah"].abs() <= p.tolerancia_pts,
                     np.where(d["lado"] == 1, d["dist_val"].abs() <= p.tolerancia_pts, False))
    d["c_nivel"] = d["c_banda"] & perto & d["dist_vah"].notna()
    d["c_absorcao_p80"] = d["c_nivel"] & (d["estimador"] >= p80)
    d["c_absorcao_p90"] = d["c_nivel"] & (d["estimador"] >= p90)
    janela = (d["hhmm"] >= p.hhmm_inicio) & (d["hhmm"] < p.hhmm_fim)
    d["c_janela"] = d["c_absorcao_p80"] & janela
    d["c_janela_p90"] = d["c_absorcao_p90"] & janela
    return d


def _episodios(d: pd.DataFrame, coluna: str, cooldown_s: int) -> pd.DataFrame:
    """Primeira barra de cada bloco; a proxima so' depois de `cooldown_s`."""
    sel = d[d[coluna]].sort_values("ts_close_ns")
    out = []
    ultimo = -math.inf
    for _, r in sel.iterrows():
        if r["ts_close_ns"] - ultimo >= cooldown_s * _NS:
            out.append(r)
            ultimo = r["ts_close_ns"]
    return pd.DataFrame(out) if out else sel.iloc[0:0]


def _sonda(ep: pd.Series, ts: np.ndarray, px: np.ndarray,
           horizontes_s: tuple[int, ...]) -> dict[str, Any]:
    """Excursao a favor (em direcao a VWAP) e contra, a partir do close da
    barra de sinal, e toque na VWAP DA HORA DO SINAL (fixa)."""
    t0 = int(ep["ts_close_ns"])
    lado = int(ep["lado"])                 # +1 compra (quer subir), -1 venda (quer cair)
    c0 = float(ep["close"])
    vw = float(ep["vwap"])
    i0 = int(np.searchsorted(ts, t0, side="right"))
    out: dict[str, Any] = {"dist_vwap_pts": abs(c0 - vw)}
    for h in horizontes_s:
        i1 = int(np.searchsorted(ts, t0 + h * _NS, side="right"))
        seg = px[i0:i1]
        if seg.size == 0:
            out[f"mfe_{h}"] = out[f"mae_{h}"] = np.nan
            out[f"tocou_vwap_{h}"] = False
            out[f"s_ate_vwap_{h}"] = np.nan
            continue
        favor = (seg - c0) * lado
        out[f"mfe_{h}"] = float(favor.max())
        out[f"mae_{h}"] = float(-favor.min())
        toque = np.nonzero((seg - vw) * lado >= 0)[0]
        out[f"tocou_vwap_{h}"] = bool(toque.size)
        out[f"s_ate_vwap_{h}"] = (float((ts[i0 + toque[0]] - t0) / _NS)
                                  if toque.size else np.nan)
    return out


# ------------------------------------------------------------------- rodar
def rodar(curated: Path, symbol: str = "WINFUT", dias: list[str] | None = None,
          p: ParametrosReplay | None = None,
          cache_dir: Path | None = None) -> dict[str, Any]:
    p = p or ParametrosReplay()
    todos = dias_disponiveis(curated, symbol)
    escolhidos = [dt.date.fromisoformat(d) for d in dias] if dias else todos
    dias_ok: list[DiaReplay] = []
    for dia in escolhidos:
        r = _barras_do_dia(curated, symbol, dia, p, cache_dir)
        if r is None:
            log.info("vwapvp.replay.dia_sem_tape", dia=dia.isoformat())
            continue
        if not r.ref:
            log.info("vwapvp.replay.sem_referencia", dia=dia.isoformat(),
                     nota="primeiro dia do curated: sem VAH/VAL de ontem, so' distribuicao")
        dias_ok.append(r)
    if not dias_ok:
        return {"erro": "nenhum dia com tape", "dias_disponiveis": [d.isoformat() for d in todos]}

    barras = pd.concat([r.barras for r in dias_ok], ignore_index=True)
    # 1. distribuicao do estimador (amostra queimada, congelada como valor)
    zv = barras["z_vwap"].fillna(0.0)
    est = (barras["z_absorcao"] * np.sign(zv))[(zv != 0) & barras["z_absorcao"].notna()]
    if est.empty:
        return {"erro": "nenhuma barra com z de absorcao (janela de 50 barras nao fechou)"}
    perc = {q: float(np.percentile(est, q)) for q in (50, 80, 90, 95)}
    p80, p90 = perc[p.percentil_gatilho], perc[p.percentil_subgrupo]

    d = _marcar_clausulas(barras, p, p80, p90)
    n_dias = len(dias_ok)
    n_dias_ref = sum(1 for r in dias_ok if r.ref)

    # 2. eventos por clausula, por dia e por hora
    cols = [f"c_{c}" for c in CLAUSULAS] + ["c_absorcao_p90", "c_janela_p90"]
    barras_por_clausula = {c: int(d[c].sum()) for c in cols}
    episodios: dict[str, pd.DataFrame] = {c: _episodios(d, c, p.cooldown_s) for c in cols}
    ep_por_clausula = {c: len(e) for c, e in episodios.items()}
    por_hora = {c: (episodios[c]["hhmm"] // 100).value_counts().sort_index().to_dict()
                if len(episodios[c]) else {} for c in cols}
    por_dia = {c: episodios[c].groupby("dia").size().to_dict() if len(episodios[c]) else {}
               for c in cols}

    # 3. sonda nos episodios de nivel (so' local) e de janela (evento completo)
    ts_por_dia = {r.dia: (r.trades_ts, r.trades_px) for r in dias_ok}

    sondas: dict[str, pd.DataFrame] = {}
    for c in ("c_nivel", "c_janela", "c_janela_p90"):
        rows = []
        for _, ep in episodios[c].iterrows():
            ts, px = ts_por_dia[ep["dia"]]
            s = _sonda(ep, ts, px, p.horizontes_s)
            s.update({"dia": ep["dia"], "hhmm": int(ep["hhmm"]), "lado": int(ep["lado"]),
                      "close": ep["close"], "z_vwap": ep["z_vwap"],
                      "estimador": ep["estimador"], "sd": ep["sd"]})
            rows.append(s)
        sondas[c] = pd.DataFrame(rows)

    def resumo_sonda(s: pd.DataFrame) -> dict[str, Any]:
        if s.empty:
            return {"n": 0}
        out: dict[str, Any] = {"n": len(s), "dist_vwap_mediana": float(s["dist_vwap_pts"].median())}
        for h in p.horizontes_s:
            out[f"h{h}"] = {
                "mfe_mediana": float(s[f"mfe_{h}"].median()),
                "mfe_p25": float(s[f"mfe_{h}"].quantile(0.25)),
                "mae_mediana": float(s[f"mae_{h}"].median()),
                "mae_p75": float(s[f"mae_{h}"].quantile(0.75)),
                "frac_tocou_vwap": float(s[f"tocou_vwap_{h}"].mean()),
            }
        return out

    # 4. area de valor: os dois algoritmos
    va_dif = [{"dia": r.dia, "ref": r.ref["dia"],
               "val_bin": r.ref["val"], "val_pares": r.ref["val_pares"],
               "vah_bin": r.ref["vah"], "vah_pares": r.ref["vah_pares"],
               "dif_val_bins": (r.ref["val"] - r.ref["val_pares"]) / p.bin_pts,
               "dif_vah_bins": (r.ref["vah"] - r.ref["vah_pares"]) / p.bin_pts,
               "poc_faixa_pts": r.ref["poc_faixa"][1] - r.ref["poc_faixa"][0]}
              for r in dias_ok if r.ref]

    # largura da banda por hora (D6): mediana de 2*sd por hora do dia
    banda_por_hora = (d.assign(h=d["hhmm"] // 100, b2=2 * d["sd"])
                      .groupby("h")["b2"].median().round(0).to_dict())

    return {
        "parametros": asdict(p), "symbol": symbol,
        "dias": n_dias, "dias_com_referencia": n_dias_ref,
        "primeiro_dia": dias_ok[0].dia, "ultimo_dia": dias_ok[-1].dia,
        "barras": len(barras), "barras_com_z": int(est.size),
        "estimador_percentis": perc,
        "limiar_p80_congelado": p80, "limiar_p90_congelado": p90,
        "barras_por_clausula": barras_por_clausula,
        "episodios_por_clausula": ep_por_clausula,
        "episodios_por_dia_medio": {c: (n / n_dias_ref if n_dias_ref else 0.0)
                                    for c, n in ep_por_clausula.items()},
        "episodios_por_hora": por_hora, "episodios_por_dia": por_dia,
        "banda_2sd_por_hora_pts": banda_por_hora,
        "sonda": {c: resumo_sonda(s) for c, s in sondas.items()},
        "area_de_valor_dois_algoritmos": va_dif,
        "_barras": d, "_episodios": episodios, "_sondas": sondas,
    }


# ---------------------------------------------------------------- console
def formatar(r: dict[str, Any]) -> list[str]:
    if "erro" in r:
        ln = [f"  {r['erro']}"]
        if r.get("dias_disponiveis"):
            ln.append("  dias disponiveis: " + ", ".join(r["dias_disponiveis"]))
        return ln
    p = r["parametros"]
    ln = [f"  {r['dias']} dias ({r['primeiro_dia']}..{r['ultimo_dia']}), "
          f"{r['dias_com_referencia']} com VAH/VAL de ontem, "
          f"{r['barras']} barras M{p['periodo_s'] // 60}"]
    pc = r["estimador_percentis"]
    ln.append(f"  Estimador de absorcao (z x lado), {r['barras_com_z']} barras: "
              f"p50={pc[50]:.2f} p80={pc[80]:.2f} p90={pc[90]:.2f} p95={pc[95]:.2f}")
    ln.append(f"    CONGELADO: gatilho p{p['percentil_gatilho']} = "
              f"{r['limiar_p80_congelado']:.3f}   "
              f"subgrupo p{p['percentil_subgrupo']} = {r['limiar_p90_congelado']:.3f}")
    ln.append("  Episodios por clausula (acumulativas; cooldown "
              f"{p['cooldown_s'] // 60} min) -> por dia:")
    for c in [f"c_{x}" for x in CLAUSULAS] + ["c_absorcao_p90", "c_janela_p90"]:
        ln.append(f"    {c:16s} barras={r['barras_por_clausula'][c]:5d}  "
                  f"episodios={r['episodios_por_clausula'][c]:4d}  "
                  f"/dia={r['episodios_por_dia_medio'][c]:.2f}")
    ln.append("  Episodios de c_banda por hora: " + ", ".join(
        f"{h}h:{n}" for h, n in r["episodios_por_hora"]["c_banda"].items()))
    ln.append("  Episodios de c_nivel por hora: " + ", ".join(
        f"{h}h:{n}" for h, n in r["episodios_por_hora"]["c_nivel"].items()))
    ln.append("  Largura 2SD mediana por hora (pts): " + ", ".join(
        f"{h}h:{v:.0f}" for h, v in r["banda_2sd_por_hora_pts"].items()))
    for c, s in r["sonda"].items():
        if s["n"] == 0:
            ln.append(f"  Sonda {c}: nenhum episodio")
            continue
        ln.append(f"  Sonda {c} (n={s['n']}, "
                  f"dist. a VWAP mediana {s['dist_vwap_mediana']:.0f} pts):")
        ln.append("    horizonte   MFE med  MFE p25   MAE med  MAE p75   tocou VWAP")
        for h in p["horizontes_s"]:
            q = s[f"h{h}"]
            ln.append(f"    {h // 60:5d} min  {q['mfe_mediana']:8.0f} {q['mfe_p25']:8.0f}  "
                      f"{q['mae_mediana']:8.0f} {q['mae_p75']:8.0f}   {q['frac_tocou_vwap']:.0%}")
    va = r["area_de_valor_dois_algoritmos"]
    if va:
        dv = [abs(x["dif_val_bins"]) for x in va]
        dh = [abs(x["dif_vah_bins"]) for x in va]
        pf = [x["poc_faixa_pts"] for x in va]
        ln.append(f"  Area de valor bin x pares ({len(va)} dias): |dif VAL| mediana "
                  f"{np.median(dv):.1f} bins (max {max(dv):.0f}); |dif VAH| mediana "
                  f"{np.median(dh):.1f} bins (max {max(dh):.0f}); plato do POC mediana "
                  f"{np.median(pf):.0f} pts")
    return ln
