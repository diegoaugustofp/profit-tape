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

O que NAO faz: nao escolhe limiar por resultado, nao varre grade de
resultado. As unicas grades sao a de HORIZONTES da sonda e a de VARIANTES
de taxa (z_banda x tolerancia), as duas declaradas na ficha ANTES da
primeira rodada; a variante e' escolhida por TAXA (contagem), nunca pela
sonda, e a sonda so' e' impressa para a escolhida (regra aceita em 30/09).

v3.89 (apos a primeira rodada real, 30/09, 46 dias em 2.875 s):
- o z de absorcao atravessa os dias, como no grafico (antes reiniciava
  por dia e so' existia a partir de ~13:10: 55% das barras);
- CACHE POR DIA das barras (OHLC, VWAP, SD, absorcao crua) e da sonda de
  toda barra com |z_vwap| >= 1,5: a rodada cara acontece uma vez, e
  qualquer variacao de clausula responde em segundos, sem guardar os
  negocios (4 GB na primeira rodada);
- log por dia com segundos.

Estimador de absorcao -- CORRIGIDO EM v3.90 (30/09), ANTES da segunda rodada
-------------------------------------------------------------------------------
A v3.87 reaproveitou `absorcao_dir = imbalance - desloc_norm` (Rota B, z50,
REPROVADO sozinho em 30/08). O unico episodio da primeira rodada (27/07
18:10) mostrou o defeito de MECANISMO: a barra era VENDEDORES batendo e o
preco CAINDO (imbalance -0,26, desloc -0,56 -> +0,30). Isso e' momento
vendedor, nao "exaustao do fluxo comprador" como o documento define. O
`absorcao_dir` da' positivo em duas situacoes opostas: (a) compradores
agridem e o preco nao sobe (absorcao, o que se quer) e (b) vendedores
agridem e o preco despenca (eficiencia vendedora). Pego pela pergunta do
Diego "como e' calculado".

Definicao fiel ao documento (conferida a mao):

    imb = (agr_compra - agr_venda) / (agr_compra + agr_venda)   > 0: compradores agridem
    des = (close - open) / (high - low)                          > 0: preco subiu
    absorcao_comp = max(imb, 0) * (1 - des)    gate da VENDA em +2SD: compradores
                                               agridem e o preco nao sobe (ou cai)
    absorcao_vend = max(-imb, 0) * (1 + des)   gate da COMPRA em -2SD: espelho

Zero quando o agressor nao e' o lado que deveria estar exausto. Exemplos:
compra 30 / venda 10, preco sobe 20% do range -> 0,5 x 0,8 = 0,40; mesma
agressao com o preco caindo ate' a minima (des = -1) -> 0,5 x 2 = 1,0;
27/07 18:10 -> comp = 0 (nao eram compradores), vend = 0,26 x 0,44 = 0,11.
z de 50 barras CONTINUO em cada serie; `estimador` da barra = z_comp se
z_vwap > 0, z_vend se z_vwap < 0; p80/p90 sao dessa serie. O
`absorcao_dir` continua no CSV como coluna, nao como clausula.

OHLC da barra: `barra_tempo` usa TODOS os negocios (e' o do grafico;
conferido em 28/09: 112 de 113 barras identicas ao Profit em OHLC e
volume, a ultima sem o call de fechamento); imbalance usa so' 2/3.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import structlog

from ..ea.barra_tempo import ConstrutorDeBarraDeTempo
from ..ea.cache_barras import assinatura
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
    # variantes de TAXA declaradas (ficha, 29/09): (z_banda, tolerancia_pts)
    variantes: tuple[tuple[float, float], ...] = (
        (2.0, 25.0), (2.0, 50.0), (1.5, 25.0), (1.5, 50.0))
    minimo_por_dia: float = 1.0        # regra de escolha: >= 1 episodio/dia em c_janela
    z_sonda_minimo: float = 0.0        # v3.99: sonda cacheada para TODAS as barras (era 1,5)
    # v3.91: dia completo = primeira barra abre as 09:00 e >= minimo_barras (113 e' o dia cheio).
    # 31/07 (comeca 12:35) e 15/09 (10:05) entraram na 1a rodada com VWAP de sessao parcial.
    hhmm_abertura_sessao: int = 900
    minimo_barras: int = 110
    # v3.95: barra que abre >= isto (call de fechamento, que o grafico tem e o
    # tape nao) entra como ZERO nas series de absorcao, nos dois lados.
    hhmm_call_fechamento: int = 1820


# ---------------------------------------------------------------- utilitarios
def _imb_des(b: BarraFechada) -> tuple[float, float] | None:
    va = b.vol_agr_compra + b.vol_agr_venda
    amp = b.high - b.low
    if va <= 0 or amp <= 0:
        return None
    return (b.vol_agr_compra - b.vol_agr_venda) / va, (b.close - b.open) / amp


def absorcao_dir(b: BarraFechada) -> float | None:
    """Rota B (historico): imbalance - desloc. NAO e' a clausula; ver docstring."""
    r = _imb_des(b)
    return None if r is None else r[0] - r[1]


def absorcao_comp(b: BarraFechada) -> float | None:
    """Compradores agridem e o preco nao sobe: max(imb,0) x (1 - des)."""
    r = _imb_des(b)
    return None if r is None else max(r[0], 0.0) * (1.0 - r[1])


def absorcao_vend(b: BarraFechada) -> float | None:
    """Vendedores agridem e o preco nao cai: max(-imb,0) x (1 + des)."""
    r = _imb_des(b)
    return None if r is None else max(-r[0], 0.0) * (1.0 + r[1])


class ZRolante:
    """z de x contra as J observacoes ANTERIORES (media[1..J] do NTSL), com
    desvio de divisor (J - 1) -- a convencao do `absorcao_dir.ntsl`, que e'
    o arquivo verificado a 2,4e-08 (skill de engenharia, 3.1). Ate' v3.92
    era populacional (/J): divergencia de sqrt(50/49) ~ 1% no z, alinhada
    em v3.93 ANTES da conferencia NTSL. Conferido a mao: historico [1,2,3],
    x = 4 -> media 2, var 1 -> z = 2."""

    def __init__(self, janela: int) -> None:
        self._h: deque[float] = deque(maxlen=janela)
        self.janela = janela

    def z(self, x: float) -> float | None:
        if len(self._h) < self.janela or self.janela < 2:
            return None
        m = sum(self._h) / self.janela
        var = sum((v - m) ** 2 for v in self._h) / (self.janela - 1)
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
    ref: dict[str, Any] = field(default_factory=dict)
    completo: bool = True


def dia_completo(df: pd.DataFrame, p: ParametrosReplay) -> bool:
    return (len(df) >= p.minimo_barras
            and int(df["hhmm_abertura"].iloc[0]) == p.hhmm_abertura_sessao)


_VERSAO_CACHE = 3      # v3.99: sonda para TODAS as barras (v2: so' |z| >= 1,5)


def _referencia(curated: Path, symbol: str, ref_dia: dt.date | None, p: ParametrosReplay,
                cache_dir: Path | None) -> dict[str, Any]:
    """VAH/VAL/POC do dia de referencia (D2: ultimo dia COMPLETO anterior),
    do cache do perfil quando ha'."""
    if ref_dia is None:
        return {}
    perfil = perfil_do_dia(curated, symbol, ref_dia, p.bin_pts, None, cache_dir)
    if perfil.vazio:
        return {}
    va = perfil.area_de_valor(p.pct, "bin")
    vp = perfil.area_de_valor(p.pct, "pares")
    pf = perfil.poc_faixa()
    assert va is not None and vp is not None and pf is not None
    return {"dia": ref_dia.isoformat(), "poc": perfil.poc(), "poc_faixa": list(pf),
            "val": va[0], "vah": va[1], "val_pares": vp[0], "vah_pares": vp[1]}


def _construir_barras(t: pd.DataFrame, p: ParametrosReplay) -> pd.DataFrame:
    """O caminho caro: M5 + VWAP negocio a negocio, absorcao CRUA por barra
    (o z e' calculado depois, continuo entre dias), e a sonda de toda barra
    com |z_vwap| >= z_sonda_minimo enquanto os negocios do dia estao na
    memoria -- e' o que dispensa guarda-los."""
    vwap = VWAPSessao()
    c = ConstrutorDeBarraDeTempo(p.periodo_s)
    linhas: list[dict[str, Any]] = []

    def fechar(b: BarraFechada) -> None:
        vw, sd = vwap.vwap, vwap.desvio
        z_vwap = None if vw is None or not sd else (b.close - vw) / sd
        linhas.append({
            "ts_close_ns": b.ts_close_ns, "hhmm": _hhmm(b.ts_close_ns - 1),
            "hhmm_abertura": _hhmm(b.ts_open_ns),   # rotulo do Profit (09:00 = 09:00-09:05)
            "open": b.open, "high": b.high, "low": b.low, "close": b.close,
            "vol_total": b.vol_total, "vol_agr_compra": b.vol_agr_compra,
            "vol_agr_venda": b.vol_agr_venda, "volume_confiavel": b.volume_confiavel,
            "vwap": vw, "sd": sd, "z_vwap": z_vwap,
            "absorcao_dir": absorcao_dir(b),
            "absorcao_comp": absorcao_comp(b), "absorcao_vend": absorcao_vend(b),
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
    if df.empty:
        return df
    # sonda por barra, para TODAS as barras (v3.99): a direcao "a favor" e'
    # EM DIRECAO A VWAP (venda acima dela, compra abaixo). Para um evento de
    # continuacao, a favor e' o espelho: usa-se MAE como favor e MFE como
    # contra. Barras com vwap indefinida ou close == vwap ficam sem sonda.
    sondas: list[dict[str, Any]] = []
    for i, r in df.iterrows():
        vw = r["vwap"]
        if vw is None or pd.isna(vw) or r["close"] == vw:
            continue
        ep = pd.Series({"ts_close_ns": r["ts_close_ns"], "lado": -1 if r["close"] > vw else 1,
                        "close": r["close"], "vwap": vw})
        sondas.append({"_i": i, **_sonda(ep, ts, px, p.horizontes_s)})
    if sondas:
        sd_df = pd.DataFrame(sondas).set_index("_i")
        df = df.join(sd_df)
    return df


def _caminho_cache(curated: Path, symbol: str, dia: dt.date, p: ParametrosReplay,
                   cache_dir: Path | None) -> Path:
    destino = cache_dir or (curated.parent / "cache" / "vwapvp_barras")
    hz = "-".join(str(h) for h in p.horizontes_s)
    return destino / f"{symbol}_{dia.isoformat()}_{p.periodo_s}_{p.z_sonda_minimo:g}_{hz}.json"


def _barras_do_dia(curated: Path, symbol: str, dia: dt.date, p: ParametrosReplay,
                   cache_dir: Path | None) -> DiaReplay | None:
    from ..features.pipeline import _carregar_dia

    pasta = curated / "trade" / f"dt={dia.isoformat()}"
    if not (pasta / f"sym={symbol}").exists():
        return None
    ass = assinatura(curated, symbol, dia)
    arq = _caminho_cache(curated, symbol, dia, p, cache_dir)
    df: pd.DataFrame | None = None
    if ass is not None and arq.exists():
        try:
            d = json.loads(arq.read_text(encoding="utf-8"))
            if tuple(d["assinatura"]) == ass and d.get("versao") == _VERSAO_CACHE:
                df = pd.DataFrame(d["barras"])
        except Exception:
            df = None
    origem = "cache"
    if df is None:
        t0 = time.perf_counter()
        t = _carregar_dia(pasta, symbol)
        if t.empty:
            return None
        df = _construir_barras(t, p)
        origem = f"construido em {time.perf_counter() - t0:.0f} s"
        if ass is not None and not df.empty:
            try:
                arq.parent.mkdir(parents=True, exist_ok=True)
                arq.write_text(json.dumps({"versao": _VERSAO_CACHE, "assinatura": list(ass),
                                           "barras": df.to_dict(orient="records")},
                                          default=_json_default), encoding="utf-8")
            except OSError as e:
                log.warning("vwapvp.replay.cache_nao_gravou", erro=str(e), arquivo=str(arq))
    if df.empty:
        return None
    df = df.copy()
    df["dia"] = dia.isoformat()
    call = df["hhmm_abertura"].astype(int) >= p.hhmm_call_fechamento
    df.loc[call, ["absorcao_dir", "absorcao_comp", "absorcao_vend"]] = 0.0
    completo = dia_completo(df, p)
    log.info("vwapvp.replay.dia", dia=dia.isoformat(), barras=len(df), origem=origem,
             completo=completo, primeira=int(df["hhmm_abertura"].iloc[0]))
    return DiaReplay(dia.isoformat(), None, df, {}, completo)


def _json_default(o: Any) -> Any:
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, float) and math.isnan(o):
        return None
    raise TypeError(f"nao serializavel: {type(o)}")


# --------------------------------------------------------- clausulas/episodios
def _marcar_clausulas(df: pd.DataFrame, p: ParametrosReplay,
                      p80: float, p90: float) -> pd.DataFrame:
    d = df.copy()
    z = d["z_vwap"]
    d["lado"] = np.where(z >= p.z_banda, -1, np.where(z <= -p.z_banda, 1, 0))  # -1 venda, +1 compra
    if "estimador" not in d:          # barras sinteticas de teste trazem so' z_absorcao
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
def _resumo_sonda(s: pd.DataFrame, horizontes_s: tuple[int, ...]) -> dict[str, Any]:
    if s.empty or "dist_vwap_pts" not in s:
        return {"n": 0}
    s = s[s["dist_vwap_pts"].notna()]
    if s.empty:
        return {"n": 0}
    out: dict[str, Any] = {"n": len(s), "dist_vwap_mediana": float(s["dist_vwap_pts"].median())}
    for h in horizontes_s:
        out[f"h{h}"] = {
            "mfe_mediana": float(s[f"mfe_{h}"].median()),
            "mfe_p25": float(s[f"mfe_{h}"].quantile(0.25)),
            "mae_mediana": float(s[f"mae_{h}"].median()),
            "mae_p75": float(s[f"mae_{h}"].quantile(0.75)),
            "frac_tocou_vwap": float(s[f"tocou_vwap_{h}"].astype(bool).mean()),
        }
    return out


_COLS_CLAUSULA = [f"c_{c}" for c in CLAUSULAS] + ["c_absorcao_p90", "c_janela_p90"]


def _avaliar_variante(barras: pd.DataFrame, p: ParametrosReplay, p80: float, p90: float,
                      n_dias_ref: int) -> dict[str, Any]:
    d = _marcar_clausulas(barras, p, p80, p90)
    episodios = {c: _episodios(d, c, p.cooldown_s) for c in _COLS_CLAUSULA}
    n = {c: len(e) for c, e in episodios.items()}
    return {
        "z_banda": p.z_banda, "tolerancia_pts": p.tolerancia_pts,
        "barras_por_clausula": {c: int(d[c].sum()) for c in _COLS_CLAUSULA},
        "episodios_por_clausula": n,
        "episodios_por_dia": {c: (v / n_dias_ref if n_dias_ref else 0.0) for c, v in n.items()},
        "episodios_por_hora": {c: (episodios[c]["hhmm"] // 100).value_counts().sort_index()
                               .to_dict() if len(episodios[c]) else {} for c in _COLS_CLAUSULA},
        "_barras": d, "_episodios": episodios,
    }


def escolher_variante(variantes: list[dict[str, Any]], minimo_por_dia: float) -> int | None:
    """REGRA ACEITA EM 30/09 (taxa, nunca resultado): entre as variantes com
    >= minimo_por_dia episodios/dia em c_janela, a mais restritiva = a de
    MENOR taxa em c_nivel; empate -> maior z_banda, depois menor tolerancia.
    None = nenhuma chega: abandono por taxa."""
    ok = [(i, v) for i, v in enumerate(variantes)
          if v["episodios_por_dia"]["c_janela"] >= minimo_por_dia]
    if not ok:
        return None
    ok.sort(key=lambda iv: (iv[1]["episodios_por_dia"]["c_nivel"],
                            -iv[1]["z_banda"], iv[1]["tolerancia_pts"]))
    return ok[0][0]


@dataclass
class Preparado:
    """Barras de todos os dias completos com z continuo, estimador, dist a
    VAH/VAL de ontem, e os percentis do estimador. E' o que `rodar` (Setup
    B) e `contar_taxa` (eventos declarados em 01/10) compartilham."""
    barras: pd.DataFrame
    dias_ok: list[DiaReplay]
    excluidos: list[dict[str, Any]]
    percentis: dict[int, float]
    p80: float
    p90: float
    n_dias_ref: int
    todos: list[dt.date]


def preparar(curated: Path, symbol: str = "WINFUT", dias: list[str] | None = None,
             p: ParametrosReplay | None = None,
             cache_dir: Path | None = None) -> Preparado | dict[str, Any]:
    p = p or ParametrosReplay()
    todos = dias_disponiveis(curated, symbol)
    escolhidos = [dt.date.fromisoformat(d) for d in dias] if dias else todos
    dias_ok: list[DiaReplay] = []
    excluidos: list[dict[str, Any]] = []
    for dia in escolhidos:
        r = _barras_do_dia(curated, symbol, dia, p, cache_dir)
        if r is None:
            log.info("vwapvp.replay.dia_sem_tape", dia=dia.isoformat())
            continue
        if not r.completo:
            excluidos.append({"dia": r.dia, "barras": len(r.barras),
                              "primeira": int(r.barras["hhmm_abertura"].iloc[0])})
            log.warning("vwapvp.replay.dia_incompleto_excluido", **excluidos[-1])
            continue
        dias_ok.append(r)
    if not dias_ok:
        return {"erro": "nenhum dia completo com tape",
                "dias_disponiveis": [d.isoformat() for d in todos], "excluidos": excluidos}
    # referencia = ultimo dia COMPLETO anterior (entre os processados ou nao:
    # se o replay for de um subconjunto, o anterior no curated pode ser um dia
    # nao pedido; usa-se dia_de_referencia e confere-se completude pelo cache)
    completos = {r.dia for r in dias_ok}
    for r in dias_ok:
        cand = dia_de_referencia(curated, symbol, dt.date.fromisoformat(r.dia))
        while cand is not None and cand.isoformat() not in completos:
            anterior = _barras_do_dia(curated, symbol, cand, p, cache_dir)
            if anterior is not None and anterior.completo:
                completos.add(cand.isoformat())
                break
            cand = dia_de_referencia(curated, symbol, cand)
        r.ref = _referencia(curated, symbol, cand, p, cache_dir)
        r.referencia = r.ref.get("dia")
        r.barras["dist_vah"] = (r.barras["close"] - r.ref["vah"]) if r.ref else np.nan
        r.barras["dist_val"] = (r.barras["close"] - r.ref["val"]) if r.ref else np.nan
        # v4.01: espessura da borda de ontem (POC -> borda, em bins) e regime
        r.barras["ref_poc"] = r.ref["poc"] if r.ref else np.nan
        r.barras["ref_vah"] = r.ref["vah"] if r.ref else np.nan
        r.barras["ref_val"] = r.ref["val"] if r.ref else np.nan
        if r.ref:
            abre = float(r.barras["open"].iloc[0])
            r.barras["abriu_dentro_va"] = bool(r.ref["val"] <= abre <= r.ref["vah"])
        else:
            r.barras["abriu_dentro_va"] = False
        if not r.ref:
            log.info("vwapvp.replay.sem_referencia", dia=r.dia,
                     nota="sem dia completo anterior: so' distribuicao")

    barras = pd.concat([r.barras for r in dias_ok], ignore_index=True)
    barras = barras.sort_values(["dia", "ts_close_ns"], kind="stable").reset_index(drop=True)
    # z CONTINUO entre dias (como no grafico), sobre cada serie crua
    for col in ("absorcao_dir", "absorcao_comp", "absorcao_vend"):
        zr = ZRolante(p.janela_z)
        zs: list[float | None] = []
        for a in barras[col]:
            if a is None or pd.isna(a):
                zs.append(None)
                continue
            zs.append(zr.z(float(a)))
            zr.empurrar(float(a))
        barras["z_" + col] = pd.Series(zs, dtype="float64")
    # estimador da barra: z da serie do LADO QUE DEVERIA ESTAR EXAUSTO (v3.90)
    zv = barras["z_vwap"].astype("float64").fillna(0.0)
    barras["estimador"] = np.where(zv > 0, barras["z_absorcao_comp"],
                                   np.where(zv < 0, barras["z_absorcao_vend"], np.nan))

    # 1. distribuicao do estimador (amostra queimada, congelada como valor)
    est = barras["estimador"][(zv != 0) & barras["estimador"].notna()]
    if est.empty:
        return {"erro": "nenhuma barra com z de absorcao (janela de 50 barras nao fechou)"}
    perc = {q: float(np.percentile(est, q)) for q in (50, 80, 90, 95)}
    p80, p90 = perc[p.percentil_gatilho], perc[p.percentil_subgrupo]
    n_dias_ref = sum(1 for r in dias_ok if r.ref)
    return Preparado(barras, dias_ok, excluidos, perc, p80, p90, n_dias_ref, todos)


def rodar(curated: Path, symbol: str = "WINFUT", dias: list[str] | None = None,
          p: ParametrosReplay | None = None,
          cache_dir: Path | None = None) -> dict[str, Any]:
    from dataclasses import replace

    p = p or ParametrosReplay()
    prep = preparar(curated, symbol, dias, p, cache_dir)
    if isinstance(prep, dict):
        return prep
    barras, dias_ok, excluidos = prep.barras, prep.dias_ok, prep.excluidos
    perc, p80, p90, n_dias_ref = prep.percentis, prep.p80, prep.p90, prep.n_dias_ref
    n_dias = len(dias_ok)
    est = barras["estimador"][(barras["z_vwap"].astype("float64").fillna(0.0) != 0)
                              & barras["estimador"].notna()]

    # 2. variantes declaradas: so' TAXA. A primeira e' a principal (2.0, 25).
    variantes = [_avaliar_variante(barras, replace(p, z_banda=z, tolerancia_pts=tol),
                                   p80, p90, n_dias_ref) for z, tol in p.variantes]
    escolhida = escolher_variante(variantes, p.minimo_por_dia)
    principal = variantes[0]

    # 3. sonda: linha de base (c_banda da principal) e, se houver escolhida,
    #    c_nivel e c_janela DELA. Nada mais e' impresso.
    sonda: dict[str, dict[str, Any]] = {
        f"c_banda (linha de base, z={principal['z_banda']:g})":
            _resumo_sonda(principal["_episodios"]["c_banda"], p.horizontes_s)}
    if escolhida is not None:
        v = variantes[escolhida]
        rot = f"z={v['z_banda']:g} tol={v['tolerancia_pts']:g}"
        for c in ("c_nivel", "c_janela", "c_janela_p90"):
            sonda[f"{c} ({rot})"] = _resumo_sonda(v["_episodios"][c], p.horizontes_s)

    # 4. area de valor: os dois algoritmos
    va_dif = [{"dia": r.dia, "ref": r.ref["dia"], "poc": r.ref["poc"],
               "val_bin": r.ref["val"], "val_pares": r.ref["val_pares"],
               "vah_bin": r.ref["vah"], "vah_pares": r.ref["vah_pares"],
               "dif_val_bins": (r.ref["val"] - r.ref["val_pares"]) / p.bin_pts,
               "dif_vah_bins": (r.ref["vah"] - r.ref["vah_pares"]) / p.bin_pts,
               "poc_faixa_pts": r.ref["poc_faixa"][1] - r.ref["poc_faixa"][0]}
              for r in dias_ok if r.ref]
    banda_por_hora = (principal["_barras"].assign(h=barras["hhmm"] // 100,
                                                  b2=2 * barras["sd"].astype("float64"))
                      .groupby("h")["b2"].median().round(0).to_dict())

    return {
        "parametros": asdict(p), "symbol": symbol,
        "dias": n_dias, "dias_com_referencia": n_dias_ref, "dias_excluidos": excluidos,
        "primeiro_dia": dias_ok[0].dia, "ultimo_dia": dias_ok[-1].dia,
        "barras": len(barras), "barras_com_z": int(est.size),
        "estimador_percentis": perc,
        "limiar_p80_congelado": p80, "limiar_p90_congelado": p90,
        "variantes": [{k: v for k, v in x.items() if not k.startswith("_")} for x in variantes],
        "variante_escolhida": escolhida,
        "regra_de_escolha": (f">= {p.minimo_por_dia:g} episodio/dia em c_janela; a mais "
                             "restritiva = menor taxa em c_nivel; nenhuma = abandono por taxa"),
        "banda_2sd_por_hora_pts": banda_por_hora,
        "sonda": sonda,
        "area_de_valor_dois_algoritmos": va_dif,
        "_barras": principal["_barras"],
        "_episodios": principal["_episodios"],
        "_variantes": variantes,
    }


# ------------------------------------------------- taxa dos eventos declarados
ESPESSURA_FINA_BINS = 15      # borda a <= 15 bins (375 pts) do POC de ontem = "fina"

EVENTOS_DECLARADOS = {
    # 01/10/2026, DECLARADOS ANTES DE CONTAR, SEM SONDA. Clausulas acumulativas.
    "rejeicao": ("toque", "janela", "nivel", "janela_abs"),
    "continuacao": ("banda", "janela", "primeira_do_dia"),
    # 01/10 (tarde), depois de olhar 28/09 no grafico com os niveis: o preco
    # interagiu 6x com o VAH de ontem pela MAXIMA (furou e fechou abaixo) e o
    # Setup B contou 0 porque le o fechamento a 25 pts. Evento visto, nao
    # medido: contagem abaixo, fast-track.
    "rejeicao_nivel": ("fura", "janela", "esticado", "primeira",
                       # 01/10 (noite), subgrupos declarados DEPOIS da sonda e ANTES de
                       # contar, a partir do que o Diego viu no VAH de 25/09 (a 390 pts
                       # do POC, 9,8% do volume acima). Cada um e' janela E condicao.
                       # Borda fina preve MOVIMENTO, nao direcao; quem da' a direcao e'
                       # o regime (preco negociando DENTRO da area de ontem). So' contagem.
                       "fina", "grossa", "dentro", "abriu_dentro", "fina_dentro"),
    # 01/10 (pregao): o Diego viu nos candles 19-23 o Setup A do documento --
    # dia de queda, pullback ate' a VWAP sentada no POC de ontem (187875, VWAP
    # 187886-187966), cinco testes, furo ate' o VAH de ontem, rejeicao e minima
    # nova. Eu tinha dito "coincidencia rara" sem medir. Declarado e contado.
    "retorno_vwap": ("toque", "janela", "poc_perto", "primeira"),
}
POC_PERTO_PTS = 250.0          # |VWAP - POC de ontem| <= isto (platô do POC ~100-150 pts)


def _marcar_eventos_declarados(d: pd.DataFrame, p: ParametrosReplay, p80: float) -> pd.DataFrame:
    """
    REJEICAO INTRABARRA (venda; compra e' o espelho), VWAP/SD da barra ao
    FECHAR (declarado: a banda no instante da maxima e' um pouco diferente):
        toque   : high >= vwap + z_banda*sd  E  close < vwap + z_banda*sd
        janela  : toque E 09:30 <= hhmm_abertura < 17:00
        nivel   : janela E |close - VAH_ontem| <= tolerancia (VAL para compra)
        janela_abs: janela E estimador >= p80 (sem nivel)
    Barra que toca os dois lados (so' em barra enorme) nao conta.

    RETORNO_VWAP (Setup A; a favor do lado esticado s):
        toque     : antes nesta sessao |z| >= z_banda do lado s; barra toca a VWAP
                    (low <= vwap <= high) e fecha do lado s
        janela    : toque E 09:30 <= abertura < 17:00
        poc_perto : janela E |VWAP - POC de ontem| <= 250 pts
        primeira  : janela E primeiro toque do dia
    REJEICAO_NIVEL (venda; compra e' o espelho no VAL de ontem):
        fura     : high >= VAH_ontem  E  close < VAH_ontem
        janela   : fura E 09:30 <= abertura < 17:00
        esticado : janela E z_close >= 1,5 (do lado do furo)
        primeira : janela E primeiro furo do dia
    CONTINUACAO (a favor do estiramento):
        banda   : |z_close| >= z_banda   (= c_banda do replay)
        janela  : banda E 09:30 <= hhmm_abertura < 17:00
        primeira_do_dia: janela E primeira barra do dia a satisfazer banda
    """
    d = d.copy()
    z = d["z_vwap"].astype("float64")
    vw, sd = d["vwap"].astype("float64"), d["sd"].astype("float64")
    sup, inf = vw + p.z_banda * sd, vw - p.z_banda * sd
    ok = sd > 0
    toque_v = ok & (d["high"] >= sup) & (d["close"] < sup)
    toque_c = ok & (d["low"] <= inf) & (d["close"] > inf)
    ambos = toque_v & toque_c
    d["r_lado"] = np.where(toque_v & ~ambos, -1, np.where(toque_c & ~ambos, 1, 0))
    d["r_toque"] = d["r_lado"] != 0
    janela = (d["hhmm_abertura"].astype(int) >= p.hhmm_inicio) & \
             (d["hhmm_abertura"].astype(int) < p.hhmm_fim)
    d["r_janela"] = d["r_toque"] & janela
    perto = np.where(d["r_lado"] == -1, d["dist_vah"].abs() <= p.tolerancia_pts,
                     np.where(d["r_lado"] == 1, d["dist_val"].abs() <= p.tolerancia_pts, False))
    d["r_nivel"] = d["r_janela"] & perto & d["dist_vah"].notna()
    d["r_janela_abs"] = d["r_janela"] & (d["estimador"] >= p80)

    # REJEICAO NO NIVEL DE ONTEM (venda: fura o VAH pela maxima e fecha abaixo;
    # compra: espelho no VAL). "esticado" = z_close >= 1,5 do lado do furo.
    vah = d["close"] - d["dist_vah"]           # recupera o nivel absoluto
    val = d["close"] - d["dist_val"]
    tem = d["dist_vah"].notna()
    fura_v = tem & (d["high"] >= vah) & (d["close"] < vah)
    fura_c = tem & (d["low"] <= val) & (d["close"] > val)
    d["n_lado"] = np.where(fura_v & ~fura_c, -1, np.where(fura_c & ~fura_v, 1, 0))
    d["n_fura"] = d["n_lado"] != 0
    d["n_janela"] = d["n_fura"] & janela
    d["n_esticado"] = d["n_janela"] & (z * d["n_lado"] * -1 >= 1.5)
    prim_n = d[d["n_janela"]].groupby("dia")["ts_close_ns"].transform("min")
    d["n_primeira"] = False
    d.loc[prim_n.index, "n_primeira"] = d.loc[prim_n.index, "ts_close_ns"] == prim_n
    # subgrupos (v4.01): espessura da borda FURADA e regime
    esp_vah = (d["ref_vah"] - d["ref_poc"]) / p.bin_pts
    esp_val = (d["ref_poc"] - d["ref_val"]) / p.bin_pts
    d["n_espessura_bins"] = np.where(d["n_lado"] == -1, esp_vah,
                                     np.where(d["n_lado"] == 1, esp_val, np.nan))
    d["n_fina"] = d["n_janela"] & (d["n_espessura_bins"] <= ESPESSURA_FINA_BINS)
    d["n_grossa"] = d["n_janela"] & (d["n_espessura_bins"] > ESPESSURA_FINA_BINS)
    vwap_dentro = (d["vwap"] >= d["ref_val"]) & (d["vwap"] <= d["ref_vah"])
    d["n_dentro"] = d["n_janela"] & vwap_dentro.fillna(False)
    d["n_abriu_dentro"] = d["n_janela"] & d["abriu_dentro_va"].astype(bool)
    d["n_fina_dentro"] = d["n_fina"] & d["n_dentro"]

    # RETORNO A VWAP depois de esticao (Setup A): antes nesta sessao houve barra
    # com |z| >= z_banda (lado s); a barra atual TOCA a VWAP (low <= vwap <=
    # high) e fecha do lado s (rejeicao a favor do lado esticado).
    lado_est = pd.Series(np.sign(z.where(z.abs() >= p.z_banda, 0.0)), index=d.index).fillna(0.0)
    acum = (lado_est.groupby(d["dia"])
            .transform(lambda x: x.replace(0.0, np.nan).ffill().shift(1)).fillna(0.0))
    toca = (d["low"] <= vw) & (d["high"] >= vw) & (sd > 0)
    fecha_lado = np.sign(d["close"] - vw) == acum
    d["v_lado"] = np.where(toca & (acum != 0) & fecha_lado, acum, 0).astype(int)
    d["v_toque"] = d["v_lado"] != 0
    d["v_janela"] = d["v_toque"] & janela
    d["v_poc_perto"] = d["v_janela"] & ((vw - d["ref_poc"]).abs() <= POC_PERTO_PTS).fillna(False)
    prim_v = d[d["v_janela"]].groupby("dia")["ts_close_ns"].transform("min")
    d["v_primeira"] = False
    d.loc[prim_v.index, "v_primeira"] = d.loc[prim_v.index, "ts_close_ns"] == prim_v

    d["c_banda"] = z.abs() >= p.z_banda
    d["c_janela"] = d["c_banda"] & janela
    primeira = d[d["c_janela"]].groupby("dia")["ts_close_ns"].transform("min")
    d["c_primeira_do_dia"] = False
    d.loc[primeira.index, "c_primeira_do_dia"] = d.loc[primeira.index, "ts_close_ns"] == primeira
    return d


def contar_taxa(curated: Path, symbol: str = "WINFUT", p: ParametrosReplay | None = None,
                cache_dir: Path | None = None) -> dict[str, Any]:
    """So' CONTAGEM dos eventos declarados em EVENTOS_DECLARADOS: episodios
    (cooldown) por dia e por hora, por clausula. Nenhuma sonda, nenhum
    resultado. E' a linha TAXA das fichas de 'rejeicao' e 'continuacao'."""
    p = p or ParametrosReplay()
    prep = preparar(curated, symbol, None, p, cache_dir)
    if isinstance(prep, dict):
        return prep
    d = _marcar_eventos_declarados(prep.barras, p, prep.p80)
    out: dict[str, Any] = {"parametros": asdict(p), "dias": len(prep.dias_ok),
                           "dias_com_referencia": prep.n_dias_ref,
                           "dias_excluidos": prep.excluidos,
                           "p80_congelado": prep.p80, "eventos": {}}
    for ev, clausulas in EVENTOS_DECLARADOS.items():
        pref = {"rejeicao": "r_", "continuacao": "c_", "rejeicao_nivel": "n_",
                "retorno_vwap": "v_"}[ev]
        bloco: dict[str, Any] = {}
        for c in clausulas:
            col = pref + c
            ep = _episodios(d, col, p.cooldown_s)
            bloco[c] = {"barras": int(d[col].sum()), "episodios": len(ep),
                        "por_dia": (len(ep) / prep.n_dias_ref if prep.n_dias_ref else 0.0),
                        "por_hora": ((ep["hhmm_abertura"] // 100).value_counts().sort_index()
                                     .to_dict() if len(ep) else {}),
                        "lados": (ep[pref + "lado"].value_counts().to_dict()
                                  if (pref + "lado") in ep and len(ep) else {})}
        out["eventos"][ev] = bloco
    esp = d.loc[d["n_janela"], "n_espessura_bins"].dropna()
    out["espessura_bins_nos_furos"] = ({q: float(esp.quantile(q)) for q in (0.25, 0.5, 0.75)}
                                       if len(esp) else {})
    out["_barras"] = d
    return out


def formatar_taxa(r: dict[str, Any]) -> list[str]:
    if "erro" in r:
        return [f"  {r['erro']}"]
    ln = [f"  {r['dias']} dias completos, {r['dias_com_referencia']} com referencia; "
          f"p80 do estimador = {r['p80_congelado']:.3f}; cooldown "
          f"{r['parametros']['cooldown_s'] // 60} min; SO' CONTAGEM, sem sonda"]
    for ev, bloco in r["eventos"].items():
        ln.append(f"  {ev.upper()} (clausulas acumulativas):")
        ln.append("    clausula            barras  episodios   /dia   por hora")
        for c, x in bloco.items():
            horas = ", ".join(f"{h}h:{n}" for h, n in x["por_hora"].items())
            ln.append(f"    {c:18s} {x['barras']:7d} {x['episodios']:10d} "
                      f"{x['por_dia']:6.2f}   {horas}")
    if r.get("espessura_bins_nos_furos"):
        e = r["espessura_bins_nos_furos"]
        ln.append(f"  Espessura POC->borda furada (bins de 25): p25 {e[0.25]:.0f}  "
                  f"p50 {e[0.5]:.0f}  p75 {e[0.75]:.0f}  (fina = <= {ESPESSURA_FINA_BINS})")
    return ln


# ------------------------------------------------- sonda dos eventos declarados
CLAUSULA_SONDA = {"rejeicao": "r_janela", "continuacao": "c_janela",
                  "rejeicao_nivel": "n_janela", "retorno_vwap": "v_janela"}
LADO_COL = {"rejeicao": "r_lado", "continuacao": None, "rejeicao_nivel": "n_lado",
            "retorno_vwap": "v_lado"}
FRACOES_ALVO = (0.25, 0.50, 0.75, 1.00)
CORTE_MANHA_HHMM = 1100


def sondar_eventos(curated: Path, symbol: str = "WINFUT", p: ParametrosReplay | None = None,
                   cache_dir: Path | None = None,
                   clausulas: dict[str, str] | None = None) -> dict[str, Any]:
    """
    Sonda dos eventos declarados, na unidade proposta pelo Diego em 01/10:
    excursao a FAVOR e CONTRA como FRACAO DA DISTANCIA ATE' A VWAP no
    fechamento da barra de sinal (a distancia varia de 600 a 1.300 pts
    conforme a hora; a fracao normaliza). Tambem em pontos e em SD.

    Direcao do evento: rejeicao e rejeicao_nivel -> contra o furo, rumo a
    VWAP (lado do evento). Continuacao -> a favor do estiramento, para
    LONGE da VWAP: o alvo nao e' a VWAP, entao "a favor" sai em SD e em
    pontos, e "contra" (volta a VWAP) em fracao da distancia.

    A sonda cacheada por barra tem direcao RUMO A VWAP. Quando o lado do
    evento coincide, favor = mfe / contra = mae; quando e' o oposto
    (continuacao sempre; rejeicao no nivel quando o VAH de ontem esta'
    ABAIXO da VWAP de hoje), favor = mae / contra = mfe, e a fracao da
    distancia so' faz sentido para o lado que aponta para a VWAP.

    Partido em manha (abertura < 11:00) e tarde: a rejeicao na banda e'
    45% antes das 11h, quando o desvio tem 200-400 pts (taxa de 01/10).
    FAST-TRACK: isto e' calibracao na amostra queimada. O que sair daqui
    vira alvo/stop DECLARADO na ficha, uma vez.
    """
    p = p or ParametrosReplay()
    clausulas = clausulas or CLAUSULA_SONDA
    prep = preparar(curated, symbol, None, p, cache_dir)
    if isinstance(prep, dict):
        return prep
    d = _marcar_eventos_declarados(prep.barras, p, prep.p80)
    out: dict[str, Any] = {"parametros": asdict(p), "dias": len(prep.dias_ok),
                           "dias_com_referencia": prep.n_dias_ref, "eventos": {}}
    for ev, col in clausulas.items():
        if col not in d.columns:
            raise SystemExit(f"{ev}: coluna {col!r} nao existe; colunas do evento: "
                             f"{sorted(c for c in d.columns if c.startswith(col[:2]))}")
        ep = _episodios(d, col, p.cooldown_s)
        if ep.empty or "dist_vwap_pts" not in ep:
            out["eventos"][ev] = {"clausula": col, "n": 0}
            continue
        ep = ep[ep["dist_vwap_pts"].notna() & (ep["dist_vwap_pts"] > 0)].copy()
        col_lado = LADO_COL[ev]
        lado_ev = (np.sign(ep["z_vwap"].astype(float).to_numpy()) if col_lado is None
                   else ep[col_lado].astype(float).to_numpy())
        rumo_vwap = np.where(ep["close"] > ep["vwap"], -1.0, 1.0)
        coincide = lado_ev == rumo_vwap
        ep["manha"] = ep["hhmm_abertura"].astype(int) < CORTE_MANHA_HHMM
        bloco: dict[str, Any] = {"clausula": col, "n": len(ep),
                                 "n_lado_rumo_vwap": int(coincide.sum()),
                                 "dist_vwap_mediana_pts": float(ep["dist_vwap_pts"].median()),
                                 "sd_mediana_pts": float(ep["sd"].median()),
                                 "por_horizonte": {}}
        for h in p.horizontes_s:
            mfe, mae = ep[f"mfe_{h}"].astype(float), ep[f"mae_{h}"].astype(float)
            favor = np.where(coincide, mfe, mae)
            contra = np.where(coincide, mae, mfe)
            dist = ep["dist_vwap_pts"].astype(float).to_numpy()
            sd = ep["sd"].astype(float).to_numpy()
            # fracao da distancia so' para o lado que aponta para a VWAP
            favor_frac = np.where(coincide, favor / dist, np.nan)
            contra_frac = np.where(~coincide, contra / dist, np.nan)
            linha: dict[str, Any] = {}
            for rot, m in (("todos", np.ones(len(ep), dtype=bool)),
                           ("manha", ep["manha"].to_numpy()),
                           ("tarde", ~ep["manha"].to_numpy())):
                if m.sum() == 0:
                    continue
                q: dict[str, Any] = {
                     "n": int(m.sum()),
                     "favor_pts_p50": float(np.median(favor[m])),
                     "favor_sd_p50": float(np.median(favor[m] / sd[m])),
                     "contra_pts_p50": float(np.median(contra[m])),
                     "contra_pts_p75": float(np.percentile(contra[m], 75))}
                ff = favor_frac[m]
                if np.isfinite(ff).any():
                    ff = ff[np.isfinite(ff)]
                    q["favor_frac_p25"] = float(np.percentile(ff, 25))
                    q["favor_frac_p50"] = float(np.median(ff))
                    q["favor_frac_p75"] = float(np.percentile(ff, 75))
                    q["alcanca"] = {f"{f:.0%}": float((ff >= f).mean()) for f in FRACOES_ALVO}
                    ca = contra[m][np.isfinite(favor_frac[m])] / dist[m][np.isfinite(favor_frac[m])]
                    q["contra_frac_p50"] = float(np.median(ca))
                    q["contra_frac_p75"] = float(np.percentile(ca, 75))
                    q["contra_passa"] = {"50%": float((ca >= 0.5).mean()),
                                         "100%": float((ca >= 1.0).mean())}
                cf = contra_frac[m]
                if np.isfinite(cf).any():
                    cf = cf[np.isfinite(cf)]
                    q["volta_vwap_frac_p50"] = float(np.median(cf))
                    q["volta_vwap_passa"] = {"50%": float((cf >= 0.5).mean()),
                                             "100%": float((cf >= 1.0).mean())}
                    fv = favor[m][np.isfinite(contra_frac[m])] / sd[m][np.isfinite(contra_frac[m])]
                    q["favor_sd_p75"] = float(np.percentile(fv, 75))
                    q["favor_sd_alcanca"] = {"0,5 SD": float((fv >= 0.5).mean()),
                                             "1 SD": float((fv >= 1.0).mean())}
                linha[rot] = q
            bloco["por_horizonte"][h] = linha
        out["eventos"][ev] = bloco
    out["_barras"] = d
    return out


def formatar_sonda_eventos(r: dict[str, Any]) -> list[str]:
    if "erro" in r:
        return [f"  {r['erro']}"]
    ln = [f"  {r['dias']} dias completos, {r['dias_com_referencia']} com referencia. "
          "Unidade: FRACAO da distancia ate' a VWAP no sinal (a favor rumo a VWAP; "
          "continuacao: a favor em SD, contra = volta a VWAP). FAST-TRACK: amostra queimada."]
    for ev, b in r["eventos"].items():
        if b["n"] == 0:
            ln.append(f"  {ev.upper()} ({b['clausula']}): nenhum episodio")
            continue
        ln.append(f"  {ev.upper()} ({b['clausula']}): n={b['n']} "
                  f"({b['n_lado_rumo_vwap']} com o lado rumo a VWAP); "
                  f"dist. a VWAP mediana {b['dist_vwap_mediana_pts']:.0f} pts; "
                  f"SD mediana {b['sd_mediana_pts']:.0f} pts")
        if ev in ("continuacao", "retorno_vwap"):     # a favor = para LONGE da VWAP
            ln.append("    horiz  parte     n  favor_pts  favor_SD(p50/p75)  >=0,5SD  >=1SD  "
                      "| contra_pts(p50/p75)  volta VWAP frac p50  >=50%  >=100%")
        else:
            ln.append("    horiz  parte     n  favor_pts  favor_frac(p25/p50/p75)  "
                      "alcanca 25/50/75/100%  | contra_pts(p50/p75)  contra_frac(p50/p75)  "
                      "passa 50/100%")
        for h, linha in b["por_horizonte"].items():
            for rot, q in linha.items():
                if ev in ("continuacao", "retorno_vwap"):
                    if "favor_sd_alcanca" not in q:
                        continue
                    fa = q["favor_sd_alcanca"]
                    vp = q["volta_vwap_passa"]
                    ln.append(f"    {h // 60:4d}m  {rot:6s} {q['n']:4d}  "
                              f"{q['favor_pts_p50']:8.0f}  "
                              f"{q['favor_sd_p50']:5.2f}/{q['favor_sd_p75']:4.2f}        "
                              f"{fa['0,5 SD']:5.0%}  {fa['1 SD']:5.0%}  "
                              f"| {q['contra_pts_p50']:6.0f}/{q['contra_pts_p75']:5.0f}        "
                              f"{q['volta_vwap_frac_p50']:5.2f}          "
                              f"{vp['50%']:5.0%}  {vp['100%']:5.0%}")
                else:
                    if "alcanca" not in q:
                        continue
                    a = q["alcanca"]
                    cp = q["contra_passa"]
                    ln.append(f"    {h // 60:4d}m  {rot:6s} {q['n']:4d}  "
                              f"{q['favor_pts_p50']:8.0f}  "
                              f"{q['favor_frac_p25']:4.2f}/{q['favor_frac_p50']:4.2f}/"
                              f"{q['favor_frac_p75']:4.2f}"
                              f"       {a['25%']:4.0%} {a['50%']:4.0%} {a['75%']:4.0%} "
                              f"{a['100%']:4.0%}"
                              f"      | {q['contra_pts_p50']:6.0f}/{q['contra_pts_p75']:5.0f}      "
                              f"{q['contra_frac_p50']:4.2f}/{q['contra_frac_p75']:4.2f}        "
                              f"{cp['50%']:4.0%} {cp['100%']:4.0%}")
    return ln


# -------------------------------------------- simulacao de regra (barras M5)
@dataclass(frozen=True)
class Regra:
    """Regra de saida simulada sobre as barras M5 do cache. Alvo e stop em
    uma de duas unidades: 'sd' (multiplos do desvio no sinal) ou 'dist'
    (fracao da distancia a VWAP no sinal). `lado_evento`: 'rumo' = contra
    o furo, em direcao a VWAP (rejeicoes); 'longe' = a favor do estirao
    (continuacao). Mesma barra toca alvo e stop -> conta STOP (conservador).
    Saida por tempo: ao fechamento da barra que completa `tempo_max_s`."""
    evento: str
    clausula: str
    lado_evento: str                  # 'rumo' | 'longe'
    alvo: float
    alvo_unidade: str                 # 'sd' | 'dist'
    stop: float
    stop_unidade: str                 # 'sd' | 'dist'
    tempo_max_s: int = 3600
    custo_pts: float = 11.0
    so_tarde: bool = False            # abertura >= CORTE_MANHA_HHMM
    so_rumo_vwap: bool = False        # rejeicao no nivel: so' quando o lado aponta para a VWAP


REGRAS_CANDIDATAS = {
    # declaradas em 01/10 a partir da sonda em fracao (amostra queimada, fast-track)
    "continuacao_tarde": Regra("continuacao", "c_janela", "longe", 0.5, "sd", 0.5, "dist",
                               3600, 11.0, so_tarde=True),
    "continuacao_tarde_1sd": Regra("continuacao", "c_janela", "longe", 1.0, "sd", 0.5, "dist",
                                   3600, 11.0, so_tarde=True),
    "nivel_tarde_vwap": Regra("rejeicao_nivel", "n_janela", "rumo", 1.0, "dist", 1.0, "dist",
                              3600, 11.0, so_tarde=True, so_rumo_vwap=True),
    "banda_tarde_meio": Regra("rejeicao", "r_janela", "rumo", 0.5, "dist", 0.5, "dist",
                              3600, 11.0, so_tarde=True),
}


def _simular_episodio(barras_dia: pd.DataFrame, i0: int, lado: int, alvo_px: float,
                      stop_px: float, tempo_max_s: int) -> tuple[str, float, int]:
    """Percorre as barras seguintes a i0 (mesmo dia). Devolve (saida, pnl_pts,
    barras_usadas). lado +1 = comprado, -1 = vendido. Entrada = close de i0."""
    entrada = float(barras_dia["close"].iloc[i0])
    t0 = int(barras_dia["ts_close_ns"].iloc[i0])
    for j in range(i0 + 1, len(barras_dia)):
        r = barras_dia.iloc[j]
        hi, lo = float(r["high"]), float(r["low"])
        bate_stop = lo <= stop_px if lado == 1 else hi >= stop_px
        bate_alvo = hi >= alvo_px if lado == 1 else lo <= alvo_px
        if bate_stop:                                   # conservador: stop antes do alvo
            return "stop", (stop_px - entrada) * lado, j - i0
        if bate_alvo:
            return "alvo", (alvo_px - entrada) * lado, j - i0
        if int(r["ts_close_ns"]) - t0 >= tempo_max_s * _NS:
            return "tempo", (float(r["close"]) - entrada) * lado, j - i0
    ult = float(barras_dia["close"].iloc[-1])
    return "fim_dia", (ult - entrada) * lado, len(barras_dia) - 1 - i0


def simular_regras(curated: Path, symbol: str = "WINFUT", p: ParametrosReplay | None = None,
                   cache_dir: Path | None = None,
                   regras: dict[str, Regra] | None = None) -> dict[str, Any]:
    p = p or ParametrosReplay()
    regras = regras or REGRAS_CANDIDATAS
    prep = preparar(curated, symbol, None, p, cache_dir)
    if isinstance(prep, dict):
        return prep
    d = _marcar_eventos_declarados(prep.barras, p, prep.p80)
    d = d.sort_values(["dia", "ts_close_ns"]).reset_index(drop=True)
    por_dia = {dia: g.reset_index(drop=True) for dia, g in d.groupby("dia", sort=False)}
    out: dict[str, Any] = {"dias": len(prep.dias_ok), "regras": {}, "_trades": {}}
    for nome, rg in regras.items():
        ep = _episodios(d, rg.clausula, p.cooldown_s)
        if rg.so_tarde and len(ep):
            ep = ep[ep["hhmm_abertura"].astype(int) >= CORTE_MANHA_HHMM]
        trades = []
        for _, e in ep.iterrows():
            col_lado = LADO_COL[rg.evento]
            lado_ev = (int(np.sign(e["z_vwap"])) if col_lado is None else int(e[col_lado]))
            rumo = -1 if e["close"] > e["vwap"] else 1
            if rg.so_rumo_vwap and lado_ev != rumo:
                continue
            # rejeicao: lado_ev ja' e' contra o furo (venda apos furar o VAH);
            # continuacao: lado_ev = sinal do z (a favor do estirao). Nos dois
            # casos o lado operado e' o do evento.
            lado = lado_ev
            sd, dist = float(e["sd"]), abs(float(e["close"]) - float(e["vwap"]))
            if sd <= 0 or dist <= 0:
                continue
            u = {"sd": sd, "dist": dist}
            alvo_px = float(e["close"]) + lado * rg.alvo * u[rg.alvo_unidade]
            stop_px = float(e["close"]) - lado * rg.stop * u[rg.stop_unidade]
            g = por_dia[e["dia"]]
            i0 = int(g.index[g["ts_close_ns"] == e["ts_close_ns"]][0])
            saida, pnl, nb = _simular_episodio(g, i0, lado, alvo_px, stop_px, rg.tempo_max_s)
            trades.append({"dia": e["dia"], "hhmm": int(e["hhmm_abertura"]), "lado": lado,
                           "entrada": float(e["close"]), "alvo_px": alvo_px, "stop_px": stop_px,
                           "alvo_pts": abs(alvo_px - float(e["close"])),
                           "stop_pts": abs(stop_px - float(e["close"])),
                           "saida": saida, "pnl_bruto": pnl, "pnl": pnl - rg.custo_pts,
                           "barras": nb})
        t = pd.DataFrame(trades)
        out["_trades"][nome] = t
        if t.empty:
            out["regras"][nome] = {"regra": asdict(rg), "n": 0}
            continue
        saidas = t["saida"].value_counts().to_dict()
        pnls = t["pnl"].astype(float)
        por_dia_pnl = t.groupby("dia")["pnl"].sum()
        ep_m = float(pnls.std(ddof=1) / np.sqrt(len(t))) if len(t) > 1 else 0.0
        out["regras"][nome] = {
            "regra": asdict(rg), "n": len(t), "por_dia": len(t) / len(prep.dias_ok),
            "saidas": saidas,
            "pnl_medio": float(pnls.mean()), "pnl_mediano": float(pnls.median()),
            "pnl_total": float(pnls.sum()), "frac_positivo": float((pnls > 0).mean()),
            "pnl_p10": float(pnls.quantile(0.10)), "pnl_p90": float(pnls.quantile(0.90)),
            "alvo_pts_mediano": float(t["alvo_pts"].median()),
            "stop_pts_mediano": float(t["stop_pts"].median()),
            "ic95_media": (float(pnls.mean() - 1.96 * ep_m), float(pnls.mean() + 1.96 * ep_m)),
            "pior_dia": float(por_dia_pnl.min()),
            "dias_negativos": int((por_dia_pnl < 0).sum()),
            "dias_com_trade": int(t["dia"].nunique()),
        }
    return out


def formatar_regras(r: dict[str, Any]) -> list[str]:
    if "erro" in r:
        return [f"  {r['erro']}"]
    ln = [f"  {r['dias']} dias; custo por trade 11 pts; mesma barra toca alvo e stop = STOP; "
          "saida por tempo ao fechamento. AMOSTRA QUEIMADA (fast-track)."]
    for nome, x in r["regras"].items():
        rg = x["regra"]
        cab = (f"  {nome}: {rg['evento']}/{rg['clausula']}, "
               f"alvo {rg['alvo']:g} {rg['alvo_unidade']}, "
               f"stop {rg['stop']:g} {rg['stop_unidade']}, {rg['tempo_max_s'] // 60} min"
               f"{', so tarde' if rg['so_tarde'] else ''}"
               f"{', so rumo VWAP' if rg['so_rumo_vwap'] else ''}")
        if x["n"] == 0:
            ln.append(cab + " -> nenhum trade")
            continue
        s = x["saidas"]
        ln.append(cab)
        ln.append(f"    n={x['n']} ({x['por_dia']:.2f}/dia, {x['dias_com_trade']} dias)  "
                  f"alvo med {x['alvo_pts_mediano']:.0f} pts  "
                  f"stop med {x['stop_pts_mediano']:.0f} pts")
        ln.append(f"    saidas: alvo {s.get('alvo', 0)}  stop {s.get('stop', 0)}  "
                  f"tempo {s.get('tempo', 0)}  fim_dia {s.get('fim_dia', 0)}")
        ln.append(f"    pnl/trade: media {x['pnl_medio']:+.0f}  "
                  f"IC95 [{x['ic95_media'][0]:+.0f}, {x['ic95_media'][1]:+.0f}]  "
                  f"mediana {x['pnl_mediano']:+.0f}  p10 {x['pnl_p10']:+.0f}  "
                  f"p90 {x['pnl_p90']:+.0f}  positivos {x['frac_positivo']:.0%}")
        ln.append(f"    total {x['pnl_total']:+.0f} pts  pior dia {x['pior_dia']:+.0f}  "
                  f"dias negativos {x['dias_negativos']}/{x['dias_com_trade']}")
    return ln


# ---------------------------------------------------------------- console
def formatar(r: dict[str, Any]) -> list[str]:
    if "erro" in r:
        ln = [f"  {r['erro']}"]
        if r.get("dias_disponiveis"):
            ln.append("  dias disponiveis: " + ", ".join(r["dias_disponiveis"]))
        return ln
    p = r["parametros"]
    ln = [f"  {r['dias']} dias completos ({r['primeiro_dia']}..{r['ultimo_dia']}), "
          f"{r['dias_com_referencia']} com VAH/VAL do ultimo dia completo anterior, "
          f"{r['barras']} barras M{p['periodo_s'] // 60}"]
    if r["dias_excluidos"]:
        ln.append("  EXCLUIDOS (incompletos: sem barra das 09:00 ou < "
                  f"{p['minimo_barras']} barras): " + ", ".join(
                      f"{x['dia']} ({x['barras']} barras, comeca {x['primeira']:04d})"
                      for x in r["dias_excluidos"]))
    pc = r["estimador_percentis"]
    ln.append(f"  Estimador: z da absorcao do lado exausto (v3.90), {r['barras_com_z']} barras: "
              f"p50={pc[50]:.2f} p80={pc[80]:.2f} p90={pc[90]:.2f} p95={pc[95]:.2f}")
    ln.append(f"    CONGELADO: gatilho p{p['percentil_gatilho']} = "
              f"{r['limiar_p80_congelado']:.3f}   "
              f"subgrupo p{p['percentil_subgrupo']} = {r['limiar_p90_congelado']:.3f}")
    ln.append("  Variantes declaradas (so' TAXA; episodios/dia, cooldown "
              f"{p['cooldown_s'] // 60} min, {r['dias_com_referencia']} dias com referencia):")
    ln.append("    z_banda tol   c_banda  c_nivel  c_abs_p80  c_janela  c_abs_p90  c_janela_p90")
    for i, v in enumerate(r["variantes"]):
        e = v["episodios_por_dia"]
        marca = "  <- escolhida" if r["variante_escolhida"] == i else ""
        ln.append(f"    {v['z_banda']:5.1f}  {v['tolerancia_pts']:4.0f}  "
                  f"{e['c_banda']:7.2f}  {e['c_nivel']:7.2f}  {e['c_absorcao_p80']:9.2f}  "
                  f"{e['c_janela']:8.2f}  {e['c_absorcao_p90']:9.2f}  "
                  f"{e['c_janela_p90']:12.2f}{marca}")
    ln.append(f"    regra: {r['regra_de_escolha']}")
    if r["variante_escolhida"] is None:
        ln.append("    NENHUMA variante chega ao minimo: ABANDONO POR TAXA do Setup B com VP "
                  "de ontem (decisao de poder, tomada antes de olhar resultado).")
    v0 = r["variantes"][0]
    ln.append(f"  Episodios de c_banda por hora (z={v0['z_banda']:g}): " + ", ".join(
        f"{h}h:{n}" for h, n in v0["episodios_por_hora"]["c_banda"].items()))
    ln.append(f"  Episodios de c_nivel por hora (z={v0['z_banda']:g}, "
              f"tol={v0['tolerancia_pts']:g}): "
              + (", ".join(f"{h}h:{n}" for h, n in v0["episodios_por_hora"]["c_nivel"].items())
                 or "nenhum"))
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
