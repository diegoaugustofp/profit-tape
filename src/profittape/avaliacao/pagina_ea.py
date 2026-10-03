"""Pagina de resultado de UM EA (v4.18): `data/diario/ea_<slug>.html`.

Le so' arquivos (ver a fronteira em `avaliacao/__init__.py`). Mostra o que a ficha manda olhar,
sem inventar veredito: quando a ficha proibe olhar resultado antes da meta (`veredito_parcial:
false`) a pagina diz isso no topo e os numeros ficam marcados como descritivos."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..diario_html import _CSS, _e, _n, _tab
from ..diario_metas import progresso, status_da_ficha
from . import metricas as M
from .fichas import carimbos, historico_da_ficha


def slug(ea: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", ea.lower()).strip("_")


def nome_arquivo(ea: str) -> str:
    """`ea_ignicao` -> ea_ignicao.html; `123 (E4)` -> ea_123_e4.html (sem "ea_ea_")."""
    s = slug(ea)
    return f"{s if s.startswith('ea_') else 'ea_' + s}.html"


def _brl(v: float | None, sinal: bool = False) -> str:
    if v is None:
        return '<span class="mudo">—</span>'
    return "R$ " + _n(v, 0, sinal)


def _grafico_capital(capital: np.ndarray, dd: dict[str, Any], dias: list[tuple[str, int]],
                     capital_inicial: float) -> str:
    n = len(capital) - 1
    if n < 1:
        return ""
    w, h, ml, mb = 1000, 210, 70, 24
    lo, hi = float(min(capital.min(), capital_inicial)), float(max(capital.max(), capital_inicial))
    if hi - lo < 1:
        hi = lo + 1

    def X(k: int) -> float:
        return ml + k / n * (w - ml - 10)

    def Y(v: float) -> float:
        return 10 + (1 - (v - lo) / (hi - lo)) * (h - mb - 16)
    pts = " ".join(f"{X(k):.1f},{Y(float(v)):.1f}" for k, v in enumerate(capital))
    eixo = "".join(
        f'<line x1="{ml}" x2="{w - 10}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#e1e5ec"/>'
        f'<text x="{ml - 6}" y="{Y(v) + 4:.1f}" font-size="10" text-anchor="end" '
        f'fill="#5b6577">{v:,.0f}</text>'.replace(",", ".")
        for v in (lo, (lo + hi) / 2, hi))
    base = (f'<line x1="{ml}" x2="{w - 10}" y1="{Y(capital_inicial):.1f}" '
            f'y2="{Y(capital_inicial):.1f}" stroke="#7a8aa5" stroke-dasharray="4 3"/>')
    marca = ""
    if dd["max_pts"] > 0:
        kp, kv = dd["k_pico"], dd["k_vale"]
        marca = (f'<line x1="{X(kp):.1f}" y1="{Y(float(capital[kp])):.1f}" x2="{X(kv):.1f}" '
                 f'y2="{Y(float(capital[kv])):.1f}" stroke="#b42318" stroke-width="3"/>')
    passo = max(1, len(dias) // 8)
    ticks = "".join(
        f'<text x="{X(k):.1f}" y="{h - 8}" font-size="10" text-anchor="middle" fill="#5b6577">'
        f'{_e(d[5:])}</text>' for d, k in dias[::passo])
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'xmlns="http://www.w3.org/2000/svg">{eixo}{base}'
            f'<polyline fill="none" stroke="#1f6feb" stroke-width="1.8" points="{pts}"/>'
            f'{marca}{ticks}</svg>'
            "<small>Capital depois de cada operação fechada (azul); tracejado = capital inicial; "
            "vermelho = o drawdown máximo (do pico ao vale).</small>")


def _pos_op(ops: pd.DataFrame, k: int) -> str:
    """Rotulo da posicao k da curva (k = depois de k operacoes; 0 = inicio)."""
    if k <= 0:
        return "início"
    r = ops.iloc[k - 1]
    return f"{r['dia']} {r['hora_saida']}"


def renderizar_pagina_ea(ea: str, ops_ea: pd.DataFrame, ops_todas: pd.DataFrame,
                         dias: pd.DataFrame, meta: dict[str, Any] | None, conta: dict[str, Any],
                         recomendado_projeto: float | None, raiz_fichas: Path | None) -> str:
    ops = M.ordenar(ops_ea[ops_ea["pnl_liquido"].notna()])
    vp, ctr = float(conta["valor_ponto"]), int(meta.get("contratos", conta["contratos"])
                                               if meta else conta["contratos"])
    r = M.resumo(ops)
    pnl = ops["pnl_liquido"].astype(float).tolist()
    dd = M.drawdown(pnl)
    cap0 = float(conta["capital_inicial"])
    capital_curva = M.curva_de_capital(pnl, cap0, vp, ctr)
    descartado = bool(ops["descartado"].fillna(False).astype(bool).any()) \
        if "descartado" in ops else False
    stops = ops["stop_pts"].dropna() if "stop_pts" in ops else pd.Series(dtype=float)
    cap = M.capital(mdd_pts=dd["max_pts"], pior_perda_pts=abs(min(0.0, r["pior_pts"] or 0.0)),
                    pior_stop_pts=float(stops.max()) if len(stops) else None,
                    valor_ponto=vp, contratos=ctr,
                    risco_max_pct=float(conta["risco_max_pct"]),
                    margem_por_contrato=conta.get("margem_por_contrato"),
                    recomendado_projeto=recomendado_projeto, capital_inicial=cap0)
    status = (status_da_ficha(raiz_fichas, meta["ficha"]) if (meta and raiz_fichas)
              else "sem ficha registrada em metas.yaml")
    partes = ["<div class='nav'><a href='index.html'>&larr; indice (todos os dias)</a></div>",
              f"<h1>EA — {_e(ea)}</h1>",
              f"<div class='sub'>Situação na ficha: {_e(status)}"
              + (f" · <a href='{_e(meta['ficha'])}'>{_e(meta['ficha'])}</a>" if meta else "")
              + "</div>"]
    if descartado:
        partes.append("<div class='aviso'>EA descartado (ficha): estes números são o que ele "
                      "ainda produz enquanto o YAML estiver em <code>data\\eas_ativos</code>; "
                      "não entram nos totais do diário.</div>")
    if meta and meta.get("veredito_parcial") is False:
        partes.append("<div class='aviso'>A ficha proíbe olhar resultado antes da meta "
                      "(veredito parcial = não). Os números abaixo são <b>descritivos</b>: "
                      "não decidem parar, mexer nem aprovar.</div>")
    ndias = ops["dia"].nunique()
    cards = [("Operações", _n(r["n"])), ("Dias com operação", _n(ndias)),
             ("% ganho", _n(r["pct_ganho"], 0) + " %"), ("P&L (pts)", _n(r["pnl_pts"], 0, True)),
             ("P&L (R$)", _brl(r["pnl_pts"] * vp * ctr, True)),
             ("Expectativa (pts/op)", _n(r["media_pts"], 1, True)),
             ("Payoff", _n(r["payoff"], 2)), ("Fator de lucro", _n(r["fator_de_lucro"], 2)),
             ("Drawdown máx (pts)", _n(dd["max_pts"], 0)),
             ("Drawdown máx (R$)", _brl(cap["mdd_brl"]))]
    partes.append("<div class='cards'>" + "".join(
        f"<div class='card'><b>{v}</b><span>{_e(k)}</span></div>" for k, v in cards) + "</div>")

    # ---- resumo
    partes.append("<h2>Resumo dos resultados</h2>")
    mot = ops.groupby("motivo")["pnl_liquido"].agg(["size", "sum", "mean"]).reset_index()
    partes.append(_tab(
        [("Saída (motivo)", True), ("Operações", False), ("P&L (pts)", False),
         ("Média (pts)", False)],
        [[_e(x.motivo), _n(x.size), _n(x.sum, 0, True), _n(x.mean, 1, True)]
         for x in mot.itertuples()]))
    dec = ops[ops["residuo"].notna()] if "residuo" in ops else ops.iloc[0:0]
    if len(dec):
        partes.append(_tab(
            [("Decomposição acumulada (pts)", True), ("Soma", False), ("Média por op", False)],
            [[nome, _n(float(dec[c].sum()) * sg, 0, True), _n(float(dec[c].mean()) * sg, 1, True)]
             for nome, c, sg in (("Ideal (movimento até a barreira)", "ideal", 1),
                                 ("- Piora de entrada", "entrada_slip", -1),
                                 ("- Gap", "gap", -1), ("- Deslizamento da saída (fill)",
                                                         "fill", -1), ("- Custo", "custo", -1),
                                 ("= P&L líquido", "pnl_liquido", 1))]))
    pd_ = M.por_dia(ops)
    acum = 0.0
    linhas = []
    for dia_, nops, pts in zip(pd_["dia"].tolist(), pd_["ops"].tolist(),
                               pd_["pnl_pts"].tolist(), strict=True):
        acum += float(pts)
        linhas.append([f"<a href='diario_{_e(dia_)}.html'>{_e(dia_)}</a>", _n(nops),
                       _n(pts, 0, True), _brl(float(pts) * vp * ctr, True), _n(acum, 0, True)])
    partes.append(_tab([("Dia", True), ("Ops", False), ("P&L (pts)", False), ("P&L (R$)", False),
                        ("Acumulado (pts)", False)], linhas))

    # ---- proxima avaliacao
    if meta:
        p = progresso(meta, ops_todas, dias)
        prox = p["proximo"]
        partes.append("<h2>Próxima avaliação (segundo a ficha)</h2>")
        partes.append(_tab(
            [("Contado", False), ("Próximo marco", True), ("Faltam", False),
             ("Ritmo obs. (ficha)", False), ("Previsão", False), ("Critério (ficha)", True)],
            [[_n(p["n"]), (f"n = {prox['n']} — {_e(prox['rotulo'])}" if prox else "—"),
              _n(p["faltam"]) if p["faltam"] is not None else "—",
              (f"{_n(p['ritmo_obs'], 2)} ({_n(p['ritmo_ficha'], 2)})"
               if p.get("ritmo_obs") is not None else "—"),
              p["previsao"].strftime("%d/%m/%Y") if p.get("previsao") else "—",
              _e(meta.get("criterio"))]]))

    # ---- drawdown
    partes.append("<h2>Drawdown máximo</h2>")
    if dd["max_pts"] > 0:
        rec = (f"recuperado em {_pos_op(ops, dd['k_rec'])}" if dd["recuperado"]
               else "<b>ainda não recuperado</b>")
        partes.append(_tab(
            [("Máximo (pts)", False), ("Máximo (R$)", False), ("Pico", True), ("Vale", True),
             ("Operações do pico ao vale", False), ("Situação", True), ("Atual (pts)", False)],
            [[_n(dd["max_pts"], 0), _brl(cap["mdd_brl"]), _e(_pos_op(ops, dd["k_pico"])),
              _e(_pos_op(ops, dd["k_vale"])), _n(dd["ops_pico_ao_vale"]), rec,
              _n(dd["atual_pts"], 0)]]))
    else:
        partes.append("<p>Sem drawdown: a curva de operações fechadas nunca ficou abaixo do "
                      "seu pico.</p>")
    partes.append("<small>Curva acumulada das operações <b>fechadas</b>. O que a operação "
                  "sofreu entre a entrada e a saída (excursão adversa) não entra: o drawdown "
                  "marcado a mercado é maior ou igual a este. Amostra de "
                  f"{_n(r['n'])} operações.</small>")

    # ---- capital
    partes.append("<h2>Capital necessário</h2>")
    projeto = (f"R$ {_n(cap['recomendado_projeto'], 0)}" if cap["recomendado_projeto"]
               else '<span class="mudo">— (sem ea.supervisor.resumo no log)</span>')
    linhas = [
        ["Capital recomendado pelo supervisor do record", projeto,
         "o que o record calcula ao incluir o EA"],
        ["Pela regra dos 2% com o PIOR STOP PROGRAMADO",
         _brl(cap["regra_2pct"]) if cap["regra_2pct"] else '<span class="mudo">—</span>',
         (f"stop {_n(float(stops.max()), 0)} pts x R$ {_n(vp, 2)} x {ctr} ÷ "
          f"{_n(100 * float(conta['risco_max_pct']), 0)}%" if len(stops)
          else "sem stop programado registrado")],
        ["Para sobreviver ao drawdown observado", _brl(cap["sobreviver"]),
         "margem + drawdown máx + 1 pior perda"],
        ["Com folga (2x o drawdown observado)", _brl(cap["com_folga"]),
         "margem + 2 x drawdown máx + 1 pior perda"]]
    partes.append(_tab([("Leitura", True), ("Capital", False), ("Como é calculado", True)],
                       linhas))
    if cap["projeto_subestima"]:
        partes.append("<div class='aviso'><b>O supervisor subestima este EA:</b> ele calcula o "
                      "capital a partir do stop genérico do bloco <code>risco</code>, não do "
                      f"stop programado do EA (até {_n(float(stops.max()), 0)} pts). Pela regra "
                      f"dos 2% seriam R$ {_n(cap['regra_2pct'], 0)}.</div>")
    if not cap["margem_informada"]:
        partes.append("<div class='aviso'>Margem por contrato não informada em "
                      "<code>docs/eas/metas.yaml</code> (<code>conta.margem_por_contrato</code>): "
                      "as leituras acima estão <b>sem margem</b> e portanto são piso.</div>")
    partes.append("<small>Não há fórmula única de capital; as três leituras estão declaradas "
                  "acima. O drawdown observado é <b>amostra</b>: o pior ainda não "
                  "aconteceu.</small>")

    # ---- evolucao do capital
    partes.append("<h2>Evolução do capital</h2>")
    dias_k: list[tuple[str, int]] = []
    vistos: set[str] = set()
    for k, d in enumerate(ops["dia"].astype(str).tolist(), start=1):
        if d not in vistos:
            vistos.add(d)
            dias_k.append((d, k - 1))
    partes.append(_grafico_capital(capital_curva, dd, dias_k, cap0))
    partes.append(
        f"<p>Capital inicial R$ {_n(cap0, 0)} → R$ {_n(float(capital_curva[-1]), 0)} "
        f"({_n(100 * (float(capital_curva[-1]) / cap0 - 1), 2, True)}%), com {ctr} contrato(s) "
        f"e R$ {_n(vp, 2)} por ponto. Menor capital da série: R$ "
        f"{_n(float(capital_curva.min()), 0)}.</p>")

    # ---- evolucao da ficha
    partes.append("<h2>Evolução da ficha</h2>")
    c = carimbos(ops)
    if c["linhas"]:
        partes.append(_tab(
            [("config_sha (YAML)", True), ("Código (tag)", True), ("Operações", False),
             ("Primeiro dia", True), ("Último dia", True), ("P&L (pts)", False)],
            [[_e(x["config_sha"]), _e(x["codigo"]), _n(x["n"]), _e(x["primeiro"]),
              _e(x["ultimo"]), _n(x["pnl"], 0, True)] for x in c["linhas"]]))
        if c["mudou"]:
            partes.append("<div class='aviso'><b>O config_sha mudou.</b> Pela regra do projeto "
                          "(mudou número, regra ou saída ⇒ contagem nova) só valem as "
                          f"<b>{_n(c['n_no_atual'])}</b> operações desde {_e(c['desde_ultimo'])}. "
                          "O contador do índice ainda soma todas.</div>")
        else:
            partes.append("<small>Um único config_sha em toda a amostra: a contagem não foi "
                          "reiniciada.</small>")
    else:
        partes.append(f"<p class='mudo'>{_n(c['sem_carimbo'])} operações sem carimbo no CSV "
                      "(gerado antes da v4.18): rode o diário de novo para registrar o "
                      "config_sha de cada uma.</p>")
    hist = historico_da_ficha(raiz_fichas, meta["ficha"]) if (meta and raiz_fichas) else []
    if hist:
        partes.append(_tab([("Data", True), ("Commit", True), ("O que mudou na ficha", True)],
                           [[_e(x["data"]), _e(x["hash"]), _e(x["assunto"])] for x in hist]))
    else:
        partes.append("<p class='mudo'>Histórico da ficha indisponível (sem git ou fora do "
                      "repositório).</p>")
    gerado = dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    return (f"<!doctype html><html lang='pt-BR'><meta charset='utf-8'><title>EA {_e(ea)}</title>"
            f"<style>{_CSS}</style><body>" + "".join(partes)
            + f"<p><small>gerado em {gerado} a partir de operacoes.csv, dias.csv, "
              "eas_config.csv e metas.yaml.</small></p></body></html>")


def gerar_paginas_ea(pasta: Path, metas: list[dict[str, Any]], conta: dict[str, Any],
                     raiz_fichas: Path | None) -> dict[str, str]:
    """Uma pagina por EA com operacoes. Devolve {ea: nome_do_arquivo}."""
    fops, fdias = pasta / "operacoes.csv", pasta / "dias.csv"
    if not fops.exists() or not fdias.exists():
        return {}
    ops = pd.read_csv(fops)
    if "descartado" not in ops:
        ops["descartado"] = False
    dias = pd.read_csv(fdias)
    cfg = pd.read_csv(pasta / "eas_config.csv") if (pasta / "eas_config.csv").exists() \
        else pd.DataFrame(columns=["dia", "ea", "capital_recomendado"])
    por_ea = {m["ea"]: m for m in metas}
    out: dict[str, str] = {}
    for ea in sorted(ops["ea"].dropna().unique()):
        x = ops[(ops["ea"] == ea) & ops["pnl_liquido"].notna()]
        if x.empty:
            continue
        meta = por_ea.get(str(ea))
        nome_sup = (meta or {}).get("nome_supervisor", str(ea))
        rc = cfg[cfg["ea"] == nome_sup].sort_values("dia")
        rec = float(rc["capital_recomendado"].iloc[-1]) if len(rc) and pd.notna(
            rc["capital_recomendado"].iloc[-1]) else None
        html = renderizar_pagina_ea(str(ea), x, ops, dias, meta, conta, rec, raiz_fichas)
        arq = nome_arquivo(str(ea))
        (pasta / arq).write_text(html, encoding="utf-8")
        out[str(ea)] = arq
    return out


__all__ = ["gerar_paginas_ea", "nome_arquivo", "renderizar_pagina_ea", "slug"]
