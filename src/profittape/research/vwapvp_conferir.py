"""
CONFERENCIA do VWAP de sessao e do perfil por preco (F1 do EA vwap_vp,
docs/eas/vwap_vp.md): recalcula do TAPE curado o que o grafico do Profit
plota, para o operador bater numero a numero ANTES de qualquer replay.
Recalcular e comparar MEDE; copiar o logado so' CONFIA (disciplina
forward, secao 3).

Tres conjuntos de negocios, lado a lado, porque D3 (todos os negocios)
e' decisao e nao medida -- aqui se ve o tamanho da diferenca:

    todos          agressao (2/3) + RLP (13) + leilao (4) + o resto
    agressao_rlp   o que o grafico do Profit usa no OHLC (medido 10/09)
    agressao       so' tipos 2/3

`checkpoints_hhmm`: o VWAP e o desvio em horarios fixos do dia (o SD
cresce com a sessao; a distancia da banda +-2SD ate' o VWAP em pontos e'
o que a linha D6 da ficha precisa para dimensionar stop e alvo).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from ..domain.enums import TradeType
from ..ea.perfil_preco import AGRESSAO, perfil_do_dia
from ..ea.vwap_sessao import VWAPSessao

_TZ = ZoneInfo("America/Sao_Paulo")
CONJUNTOS: dict[str, frozenset[int] | None] = {
    "todos": None,
    "agressao_rlp": frozenset((*AGRESSAO, int(TradeType.RLP))),
    "agressao": frozenset(AGRESSAO),
}
CHECKPOINTS_PADRAO = (1000, 1200, 1400, 1600)


def _hhmm(ts_ns: int) -> int:
    t = dt.datetime.fromtimestamp(ts_ns / 1e9, tz=_TZ)
    return t.hour * 100 + t.minute


def conferir_dia(curated: Path, symbol: str, dia: dt.date, bin_pts: float = 25.0,
                 pct: float = 0.70, lvn_frac: float = 0.30, hvn_frac: float = 0.50,
                 vizinhos: int = 2,
                 checkpoints_hhmm: tuple[int, ...] = CHECKPOINTS_PADRAO,
                 cache_dir: Path | None = None) -> dict[str, Any]:
    from ..features.pipeline import _carregar_dia

    pasta = curated / "trade" / f"dt={dia.isoformat()}"
    if not (pasta / f"sym={symbol}").exists():
        return {"erro": "dia sem tape no curated"}
    t = _carregar_dia(pasta, symbol)
    if t.empty:
        return {"erro": "dia vazio no curated"}

    vwaps = {nome: VWAPSessao() for nome in CONJUNTOS}
    pendentes = sorted(checkpoints_hhmm)
    marcas: dict[int, dict[str, Any]] = {}
    for ts_ns, price, qtd, tipo in t[["ts_ns", "price", "quantidade",
                                      "trade_type"]].itertuples(index=False):
        h = _hhmm(int(ts_ns))
        while pendentes and h >= pendentes[0]:
            marcas[pendentes.pop(0)] = {n: v.resumo() for n, v in vwaps.items()}
        for nome, tipos in CONJUNTOS.items():
            if tipos is None or int(tipo) in tipos:
                vwaps[nome].registrar(float(price), int(qtd))
    for cp in pendentes:                                   # dia acabou antes do checkpoint
        marcas[cp] = {n: v.resumo() for n, v in vwaps.items()}

    perfil = perfil_do_dia(curated, symbol, dia, bin_pts, None, cache_dir)
    r = perfil.resumo(pct)
    va = perfil.area_de_valor(pct)
    nos = perfil.nos(lvn_frac, hvn_frac, vizinhos)
    delta_va = None if va is None else perfil.delta_na_faixa(va[0], va[1] - bin_pts)
    hist = pd.DataFrame({"bin": perfil.bins()})
    hist["volume"] = [perfil.volume_no_bin(b) for b in hist["bin"]]
    hist["delta_agr"] = [perfil.delta_no_bin(b) for b in hist["bin"]]
    hist["rlp"] = [perfil._rlp.get(b, 0.0) for b in hist["bin"]]
    return {
        "dia": dia.isoformat(), "symbol": symbol, "negocios": len(t),
        "vwap_final": {n: v.resumo() for n, v in vwaps.items()},
        "vwap_checkpoints": marcas,
        "perfil": r, "nos": nos, "delta_agr_na_area_de_valor": delta_va,
        "histograma": hist,
        "parametros": {"bin_pts": bin_pts, "pct": pct, "lvn_frac": lvn_frac,
                       "hvn_frac": hvn_frac, "vizinhos": vizinhos},
    }


def conferir(curated: Path, symbol: str, dias: list[str], **kw: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"dias": {}}
    for d in dias:
        out["dias"][d] = conferir_dia(curated, symbol, dt.date.fromisoformat(d), **kw)
    return out


def formatar(r: dict[str, Any]) -> list[str]:
    """Linhas prontas para o console, um dia."""
    if "erro" in r:
        return [f"  {r.get('dia', '?')}: {r['erro']}"]
    ln = [f"  {r['dia']}  negocios={r['negocios']}"]
    ln.append("    VWAP final (vwap | sd | -2sd .. +2sd):")
    for nome, s in r["vwap_final"].items():
        if s["vwap"] is None:
            ln.append(f"      {nome:13s} sem negocio")
            continue
        ln.append(f"      {nome:13s} {s['vwap']:10.1f} | {s['sd']:7.1f} | "
                  f"{s['inf_2sd']:10.1f} .. {s['sup_2sd']:10.1f}   vol={s['volume']:.0f}")
    ln.append("    VWAP 'todos' nos checkpoints (hhmm: vwap | sd | 2sd em pts):")
    for cp in sorted(r["vwap_checkpoints"]):
        s = r["vwap_checkpoints"][cp]["todos"]
        if s["vwap"] is None:
            ln.append(f"      {cp:04d}: sem negocio ainda")
        else:
            ln.append(f"      {cp:04d}: {s['vwap']:10.1f} | {s['sd']:7.1f} | {2 * s['sd']:7.1f}")
    p = r["perfil"]
    ln.append(f"    Perfil (bin {p['bin_pts']:g} pts, {p['bins']} bins, "
              f"{p['min']:.0f}..{p['max']:.0f}):")
    ln.append(f"      POC={p['poc']:.0f}  VAL={p['val']:.0f}  VAH={p['vah']:.0f}  "
              f"(area de valor {r['parametros']['pct']:.0%})")
    ln.append(f"      volume={p['volume']:.0f}  rlp={p['volume_rlp']:.0f} "
              f"({p['volume_rlp'] / p['volume']:.1%})  leilao={p['volume_leilao']:.0f}  "
              f"agr compra={p['agr_compra']:.0f} venda={p['agr_venda']:.0f}")
    ln.append(f"      delta agressao dentro da area de valor: "
              f"{r['delta_agr_na_area_de_valor']:+.0f}")
    hvn = ", ".join(f"{b:.0f}" for b in r["nos"]["hvn"]) or "nenhum"
    lvn = ", ".join(f"{b:.0f}" for b in r["nos"]["lvn"]) or "nenhum"
    ln.append(f"      HVN (>= {r['parametros']['hvn_frac']:.0%} do POC, max local): {hvn}")
    ln.append(f"      LVN (< {r['parametros']['lvn_frac']:.0%} da media de "
              f"+-{r['parametros']['vizinhos']} bins): {lvn}")
    return ln
