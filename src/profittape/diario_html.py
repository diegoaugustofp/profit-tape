"""Renderizacao do diario (v4.12): HTML unico, sem JS e sem recursos externos --
abre offline, em qualquer maquina, e pode ser arquivado junto com o CSV."""

from __future__ import annotations

import datetime as dt
import html
import math
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

_TZ = ZoneInfo("America/Sao_Paulo")
_NS = 1_000_000_000

_CSS = """
body{font:14px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;margin:24px auto;max-width:1180px;
color:#1d2433;background:#fafbfc;padding:0 16px}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:16px;margin:28px 0 8px;border-bottom:1px solid #d8dde6;padding-bottom:4px}
.sub{color:#5b6577;margin-bottom:12px}
.cards{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0}
.card{background:#fff;border:1px solid #d8dde6;border-radius:6px;padding:8px 12px;min-width:130px}
.card b{display:block;font-size:19px}.card span{color:#5b6577;font-size:12px}
table{border-collapse:collapse;width:100%;background:#fff;margin:6px 0 12px;font-size:13px}
th,td{border:1px solid #e1e5ec;padding:4px 7px;text-align:right}th{background:#f0f3f8}
td.l,th.l{text-align:left}.neg{color:#b42318}.pos{color:#067647}
.aviso{background:#fff6e0;border:1px solid #f0d28a;padding:6px 10px;border-radius:6px;
margin:6px 0}
.nota{background:#eef5ff;border:1px solid #b9d3f5;padding:6px 10px;border-radius:6px;
white-space:pre-wrap}
.mudo{color:#9aa3b2}small{color:#5b6577}
"""


def _e(x: Any) -> str:
    return html.escape("" if x is None else str(x))


def _n(v: Any, casas: int = 0, sinal: bool = False) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return '<span class="mudo">—</span>'
    txt = f"{float(v):{'+' if sinal else ''},.{casas}f}".replace(",", "X").replace(".", ",")
    txt = txt.replace("X", ".")
    cls = ""
    if sinal and float(v) < 0:
        cls = "neg"
    elif sinal and float(v) > 0:
        cls = "pos"
    return f'<span class="{cls}">{txt}</span>' if cls else txt


def _tab(cabecalho: list[tuple[str, bool]], linhas: list[list[str]]) -> str:
    th = "".join(f'<th class="{"l" if esq else ""}">{_e(t)}</th>' for t, esq in cabecalho)
    corpo = "".join("<tr>" + "".join(
        f'<td class="{"l" if cabecalho[i][1] else ""}">{c}</td>' for i, c in enumerate(r)) + "</tr>"
        for r in linhas)
    return f"<table><tr>{th}</tr>{corpo}</table>"


def _lado(v: Any) -> str:
    if str(v).lower() in ("1", "1.0", "compra", "buy"):
        return "compra"
    if str(v).lower() in ("-1", "-1.0", "venda", "sell"):
        return "venda"
    return _e(v)


def _atraso(v: float | None, tape_ok: bool) -> str:
    if v is None:
        return '<span class="neg">feed mudo</span>' if tape_ok else '<span class="mudo">—</span>'
    return _n(max(v, 0.0), 1)


def _grafico(dados: dict[str, Any]) -> str:
    pm = dados["por_minuto"]
    if not pm:
        return ""
    w, h, ml, mb = 1080, 190, 46, 22
    x0 = 9 * 60
    span = (18 * 60 + 30) - x0

    def X(hhmm: str) -> float:
        hh, mm = hhmm.split(":")
        return ml + (int(hh) * 60 + int(mm) - x0) / span * (w - ml - 8)

    topo = max(1.0, math.log10(1 + max(0.0, max(float(p["max"]) for p in pm))))

    def Y(v: float) -> float:
        # v pode vir levemente negativo (jitter do relogio): escala log so' de 0 para cima
        return 8 + (1 - math.log10(1 + max(v, 0.0)) / topo) * (h - mb - 14)

    def linha(chave: str, cor: str) -> str:
        pts = " ".join(f"{X(p['hhmm']):.1f},{Y(float(p[chave])):.1f}" for p in pm)
        return f'<polyline fill="none" stroke="{cor}" stroke-width="1.4" points="{pts}"/>'
    eixos = "".join(
        f'<line x1="{ml}" x2="{w - 8}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#e1e5ec"/>'
        f'<text x="{ml - 4}" y="{Y(v) + 4:.1f}" font-size="10" text-anchor="end" fill="#5b6577">'
        f'{v}s</text>' for v in (0, 1, 10, 100, 1000) if math.log10(1 + v) <= topo + 1e-9)
    horas = "".join(
        f'<text x="{X(f"{hh:02d}:00"):.1f}" y="{h - 6}" font-size="10" text-anchor="middle" '
        f'fill="#5b6577">{hh}h</text>' for hh in range(9, 19))
    marcas = ""
    for o in dados["operacoes"]:
        d = dt.datetime.fromtimestamp(o["t_saida"] / 1e9, tz=_TZ)
        hhmm = d.strftime("%H:%M")
        if not "09:00" <= hhmm <= "18:30":
            continue
        cor = "#b42318" if (o.get("pnl_liquido") or 0) < 0 else "#067647"
        marcas += (f'<line x1="{X(hhmm):.1f}" x2="{X(hhmm):.1f}" y1="8" y2="{h - mb}" '
                   f'stroke="{cor}" stroke-dasharray="3 3"/>'
                   f'<text x="{X(hhmm) + 2:.1f}" y="18" font-size="10" fill="{cor}">'
                   f'{_e(str(o.get("ea") or "")[:10])}</text>')
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'xmlns="http://www.w3.org/2000/svg">{eixos}{linha("p50", "#7a8aa5")}'
            f'{linha("max", "#d9480f")}{marcas}{horas}</svg>'
            '<small>Atraso do feed por minuto de evento (escala log): cinza = mediana, '
            'laranja = maximo. Tracejado = saida de operacao (vermelho = perda).</small>')


def renderizar(dados: dict[str, Any]) -> str:
    ops: list[dict[str, Any]] = sorted(dados["operacoes"], key=lambda o: o["t_saida"])
    a, t, s = dados["atribuicao"], dados["tape"], dados["saude"]
    tape_ok = t is not None
    pnl = sum((o.get("pnl_liquido") or 0) for o in ops)
    razao = a["stop_real_sobre_programado_mediano"]
    cards = [
        ("Operações", _n(len(ops))), ("P&L líquido (pts)", _n(pnl, 0, True)),
        ("Stops", _n(a["stops"])),
        ("Stop real ÷ programado (mediana)", _n(razao, 2) if razao else "—"),
        ("Atraso p99 / máx do feed (s)",
         f"{_n(t['atraso_p99'], 1)} / {_n(t['atraso_max'], 1)}" if t else "—"),
        ("Incidentes de atraso", _n(len(dados["incidentes"])) if tape_ok else "—"),
        ("Buracos de chegada", _n(len(dados["buracos"])) if tape_ok else "—"),
        ("Fila máx do record", _n(s.get("fila_max"))),
    ]
    partes = [f"<h1>Diário operacional — {_e(dados['symbol'])} — "
              f"{dt.date.fromisoformat(dados['dia']).strftime('%d/%m/%Y')}</h1>",
              f"<div class='sub'>gerado em {_e(dados['gerado_em'])} · log + tape curado</div>"]
    partes += [f"<div class='aviso'>{_e(x)}</div>" for x in dados["avisos"]]
    desc = dados.get("ops_descartadas") or []
    if desc:
        por_ea: dict[str, list[float]] = {}
        for o in desc:
            por_ea.setdefault(str(o.get("ea")), []).append(float(o.get("pnl_liquido") or 0))
        resumo_desc = "; ".join(f"{k}: {len(v)} ops, {sum(v):+.0f} pts"
                                for k, v in por_ea.items())
        partes.append(
            "<div class='aviso'><b>EAs descartados ainda em execução</b> (fora dos totais "
            f"abaixo; ficam no CSV): {_e(resumo_desc)}. Para parar sem reiniciar o record, tire "
            "o YAML de <code>data\\eas_ativos</code>.</div>")
    if dados.get("nao_executadas"):
        c: dict[str, int] = {}
        for x in dados["nao_executadas"]:
            c[str(x["ea"])] = c.get(str(x["ea"]), 0) + 1
        partes.append("<div class='aviso'>Sinais sem execução (não contam como operação): "
                      + _e(", ".join(f"{k}: {v}" for k, v in c.items())) + ".</div>")
    if t is not None and t.get("offset_relogio_s"):
        partes.append(
            "<div class='aviso'>Relógio local "
            f"{'atrasado' if t['offset_relogio_s'] < 0 else 'adiantado'} em relação à bolsa por "
            f"~{abs(t['offset_relogio_s']):.2f} s (mediana bruta de ts_recv-ts negativa): os "
            "atrasos abaixo já estão corrigidos por esse desvio.</div>")
    if dados["notas"]:
        partes.append(f"<h2>Anotações do operador</h2><div class='nota'>{_e(dados['notas'])}</div>")
    partes.append("<div class='cards'>" + "".join(
        f"<div class='card'><b>{v}</b><span>{_e(k)}</span></div>" for k, v in cards) + "</div>")

    # ---- operacoes
    partes.append("<h2>Operações e decomposição do resultado</h2>")
    if ops:
        cab = [("EA", True), ("Saída", True), ("Lado", True), ("Motivo", True), ("Entrada", False),
               ("Saída px", False), ("P&L líq", False), ("Ideal", False), ("Entr. (+pior)", False),
               ("Gap (+pior)", False), ("Fill (+pior)", False), ("Custo", False),
               ("Stop prog", False),
               ("Real÷prog", False), ("Fill de", True), ("Atraso entr (s)", False),
               ("Atraso saída (s)", False), ("Custo atraso est.", False)]
        linhas = []
        for o in ops:
            hora = dt.datetime.fromtimestamp(o["t_saida"] / 1e9, tz=_TZ).strftime("%H:%M:%S")
            lado = _lado(o.get("lado"))
            linhas.append([
                _e(o.get("ea")), hora, lado, _e(o.get("motivo")), _n(o.get("entrada")),
                _n(o.get("saida")), _n(o.get("pnl_liquido"), 0, True),
                _n(o.get("ideal"), 0, True), _n(o.get("entrada_slip"), 0),
                _n(o.get("gap"), 0), _n(o.get("fill"), 0), _n(o.get("custo"), 0),
                _n(o.get("stop_pts"), 0), _n(o.get("stop_real_sobre_programado"), 2),
                _e(o.get("fill_origem")),
                _atraso(o.get("atraso_entrada_s"), tape_ok) if o.get("t_entrada")
                else '<span class="mudo">—</span>',
                _atraso(o.get("atraso_saida_s"), tape_ok),
                _n((o.get("custo_atraso_saida_est") or 0) + (o.get("custo_atraso_entrada_est")
                                                             or 0), 0)
                if (o.get("custo_atraso_saida_est") is not None
                    or o.get("custo_atraso_entrada_est") is not None)
                else '<span class="mudo">—</span>'])
        partes.append(_tab(cab, linhas))
        partes.append("<small>pnl líquido = ideal - gap - fill - entrada - custo (pontos). "
                      "<b>Gap</b>: o primeiro negócio além da barreira já estava longe dela "
                      "(mercado rápido; nenhum stop evita). <b>Fill</b>: deslizamento da "
                      "execução simulada contra o tape (atraso e spread entram aqui). "
                      "Atraso = mediana de ts_recv-ts dos negócios que chegaram a ±1 s da hora "
                      "em que o EA processou. <b>Custo atraso est.</b> é CONTRAFACTUAL e fica fora "
                      "da identidade: quanto o mercado andou contra, entre o gatilho e o "
                      "instante em que o EA o processou (saída no alvo = ordem limite: não "
                      "pesa).</small>")
    else:
        partes.append("<p class='mudo'>Nenhuma operação encerrada neste dia.</p>")

    # ---- atribuicao
    partes.append("<h2>Quanto cada variável pesou</h2>")
    sm = a["soma"]
    if a["operacoes_decompostas"]:
        linhas = [["Ideal (movimento até a barreira)", _n(sm["ideal"], 0, True)],
                  ["- Piora de entrada", _n(-sm["entrada_slip"], 0, True)],
                  ["- Gap (mercado além do stop/alvo)", _n(-sm["gap"], 0, True)],
                  ["- Deslizamento da saída (fill)", _n(-sm["fill"], 0, True)],
                  ["- Custo", _n(-sm["custo"], 0, True)],
                  ["<b>= P&L líquido das operações decompostas</b>",
                   f"<b>{_n(sm['pnl_liquido'], 0, True)}</b>"]]
        partes.append(_tab([("Parcela (pontos)", True), ("Soma", False)], linhas))
        if a["ops_com_fill_do_tape"]:
            partes.append(
                "<div class='aviso'>Em " + _n(a["ops_com_fill_do_tape"]) + " operação(ões) o "
                "fill é o <b>preço do tape no gatilho</b> (vwap_vp em dry_run; ignição só quando "
                "o livro está indisponível ou velho): ali o <b>fill é zero por construção</b> e "
                "o atraso do feed não muda o P&amp;L simulado — o excesso sobre o stop aparece "
                "como <b>gap</b>; o custo do atraso é a estimativa contrafactual da coluna "
                "ao lado. Nas operações com fill do <b>livro</b> (ignição normalmente) o "
                "atraso JÁ está dentro de <i>Fill</i> e <i>Entr.</i>: é medido, não "
                "estimado.</div>")
        partes.append(
            f"<p>{a['stops']} stop(s); em {a['ops_com_atraso_na_saida']} operação(ões) a saída "
            f"ocorreu com feed atrasado (&gt; 2 s) ou mudo: gap+fill somam "
            f"{_n(a['gap_mais_fill_com_atraso'], 0, True)} pts ali, contra "
            f"{_n(a['gap_mais_fill_sem_atraso'], 0, True)} nas demais. Custo contrafactual do "
            f"atraso no dia: {_n(a['custo_atraso_est'], 0, True)} pts. Um dia é uma amostra de "
            f"{a['operacoes_decompostas']}: o dado acumula em <code>operacoes.csv</code>.</p>")
    else:
        partes.append("<p class='mudo'>Sem operação decomponível (ignição e vwap_vp).</p>")

    # ---- feed
    partes.append("<h2>Atraso do feed (tape curado)</h2>")
    if tape_ok:
        partes.append(f"<p>{_n(t['negocios'])} negócios · atraso mediano "
                      f"{_n(t['atraso_p50'], 2)} s · p99 {_n(t['atraso_p99'], 1)} s · "
                      f"máximo {_n(t['atraso_max'], 1)} s.</p>")
        partes.append(_grafico(dados))
        if dados["incidentes"]:
            partes.append(_tab(
                [("Início", True), ("Fim", True), ("Minutos", False), ("Pico (s)", False),
                 ("Negócios", False)],
                [[_e(i["inicio"]), _e(i["fim"]), _n(i["minutos"]), _n(i["pico_s"], 1),
                  _n(i["negocios"])] for i in dados["incidentes"]]))
        if dados["buracos"]:
            partes.append(_tab(
                [("Buraco de chegada (início)", True), ("Duração (s)", False),
                 ("Negócios na bolsa nesse intervalo", False), ("Classe", True)],
                [[_e(b["inicio"]), _n(b["duracao_s"], 1), _n(b["negocios_no_intervalo"]),
                  _e(b["classe"])] for b in dados["buracos"]]))
        if not dados["incidentes"] and not dados["buracos"]:
            partes.append("<p>Sem incidentes (&ge; 10 s de atraso) nem buracos (&ge; 20 s).</p>")
    else:
        partes.append("<p class='mudo'>Sem tape curado.</p>")

    # ---- saude do record
    partes.append("<h2>Saúde do record</h2>")
    if s.get("heartbeats", 0) >= 2:
        partes.append(_tab(
            [("Heartbeats", False), ("Maior intervalo (s)", False), (">45 s", False),
             ("Fila máx", False), ("Descartados", False), ("Sem evento máx (s)", False),
             ("Linhas/s mediana", False), ("mín", False), ("máx", False)],
            [[_n(s["heartbeats"]), _n(s["maior_intervalo_s"], 1), _n(s["intervalos_acima_45s"]),
              _n(s["fila_max"]), _n(s["descartados"]), _n(s["sem_evento_max_s"], 1),
              _n(s["linhas_s_mediana"]), _n(s["linhas_s_min"]), _n(s["linhas_s_max"])]]))
    else:
        partes.append("<p class='mudo'>Sem heartbeats suficientes no log do dia.</p>")
    if dados["estados_dll"]:
        partes.append(_tab([("Hora", True), ("Estado DLL (tipo)", False), ("Valor", False)],
                           [[_e(x["hora"]), _e(x["tipo"]), _e(x["valor"])]
                            for x in dados["estados_dll"]]))
    if dados["ocorrencias"]:
        partes.append(_tab(
            [("Nível", True), ("Evento", True), ("Vezes", False), ("Primeiro", False),
             ("Último", False)],
            [[_e(o["nivel"]), _e(o["evento"]), _n(o["n"]), _e(o["primeiro"]), _e(o["ultimo"])]
             for o in dados["ocorrencias"][:40]]))
    return (f"<!doctype html><html lang='pt-BR'><meta charset='utf-8'>"
            f"<title>Diário {dados['dia']}</title><style>{_CSS}</style><body>"
            + "".join(partes) + "</body></html>")


def renderizar_indice(pasta: Path) -> str:
    f = pasta / "dias.csv"
    if not f.exists():
        return "<!doctype html><meta charset='utf-8'><p>Sem dias gerados.</p>"
    df = pd.read_csv(f).sort_values("dia", ascending=False)
    linhas = []
    for r in df.itertuples():
        arq = f"diario_{r.dia}.html"
        link = f"<a href='{_e(arq)}'>{_e(r.dia)}</a>" if (pasta / arq).exists() else _e(r.dia)
        linhas.append([link, _n(r.operacoes), _n(r.pnl_liquido, 0, True), _n(r.stops),
                       _n(r.stop_real_sobre_programado_mediano, 2), _n(r.gap, 0), _n(r.fill, 0),
                       _n(getattr(r, "custo_atraso_est", None), 0),
                       _n(r.atraso_p99, 1), _n(r.atraso_max, 1), _n(r.incidentes),
                       _n(r.buracos), _n(r.fila_max)])
    tab = _tab([("Dia", True), ("Ops", False), ("P&L líq", False), ("Stops", False),
                ("Real÷prog", False), ("Gap", False), ("Fill", False), ("Custo atraso", False),
                ("Atraso p99", False),
                ("Atraso máx", False), ("Incid.", False), ("Buracos", False),
                ("Fila máx", False)], linhas)
    return (f"<!doctype html><html lang='pt-BR'><meta charset='utf-8'><title>Diário — índice"
            f"</title><style>{_CSS}</style><body><h1>Diário operacional — todos os dias</h1>"
            f"<div class='sub'>uma linha por dia; abra o dia para a decomposição</div>{tab}"
            "</body></html>")
