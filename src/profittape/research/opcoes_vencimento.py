"""
OPCAO SOBRE ACAO — passo 1: o hedge deixa marca no PAPEL? (2026-09-22)

CONTRAPARTE: quem vendeu opcao e esta' com delta e' OBRIGADO a hedgear, e
o hedge fica mais violento quanto mais perto do strike no vencimento --
compra quando o papel sobe, vende quando cai. Fluxo que nao escolhe preco,
concentrado em DATA e em NIVEL DE PRECO.

ESTE MODULO NAO E' UMA FICHA. Categoria `features`, zero trial, SEM
DIRECAO (nao olha retorno com sinal).

AS DUAS PERGUNTAS, e por que a segunda e' a que importa
-------------------------------------------------------
1. A semana do vencimento e' diferente das outras em MAGNITUDE (volume,
   amplitude, |retorno| do papel)? Sozinha, isso e' so' sazonalidade.
2. O volume do papel se CONCENTRA perto dos strikes com OI relevante? E'
   o que separa "semana agitada" de "o preco e' atraido pelos strikes" --
   a unica das duas com mecanismo.

O PLACEBO (o que decide a pergunta 2), v2 -- 2026-09-22
--------------------------------------------------------
A v1 deslocava os strikes 1,7% para cima. O ENSAIO com setembro mostrou
que o desenho nao funciona: 48,67 e 49,92 viraram 49,50 e 50,77, FORA da
faixa em que a PETR4 negociou (~48), entao os falsos receberam volume
ZERO por construcao e a razao explodiu (310 milhoes). Placebo que nao
recebe volume nao testa nada.

E a tolerancia fixa de +-0,4% (+-0,19 em PETR4) era maior que meio
intervalo da grade (0,25 entre strikes): a faixa "perto de um strike"
engolia quase tudo -- 86% do volume em 18/09.

v2: o placebo e' o MEIO DO CAMINHO entre strikes consecutivos (dentro da
faixa negociada por construcao), e a tolerancia e' uma FRACAO do
espacamento da grade (default 0,2 = +-20% do intervalo), de modo que as
duas faixas tenham a MESMA largura e nunca se toquem. A razao so' e'
reportada quando as duas faixas cobrem parte da faixa negociada no dia --
senao sai `None` com o motivo.

LIMITE DECLARADO: o OI vem do Trade Hunter e e' de FECHAMENTO (EOD), nao
intradiario; e e' posicao em aberto, nao fluxo. Os strikes entram como
parametro -- este modulo nao busca dado externo.
"""

from __future__ import annotations

import datetime as dt
import json
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog

from ..features.pipeline import _carregar_dia

log = structlog.get_logger(__name__)
_NS = 1_000_000_000
TOL_FRAC_DO_ESPACAMENTO = 0.2   # +-20% do intervalo entre strikes


def carregar_papel(curated: Path, papel: str, dia: dt.date) -> pd.DataFrame:
    pasta = curated / "trade" / f"dt={dia.isoformat()}"
    if not (pasta / f"sym={papel}").exists():
        return pd.DataFrame()
    t = _carregar_dia(pasta, papel)
    return t.sort_values("ts_ns") if not t.empty else pd.DataFrame()


def grade(strikes: list[float]) -> tuple[list[float], float]:
    """Strikes ordenados e o espacamento (mediana das diferencas)."""
    ss = sorted(float(x) for x in strikes)
    if len(ss) < 2:
        return ss, 0.0
    return ss, float(np.median(np.diff(ss)))


def placebos(strikes: list[float]) -> list[float]:
    """MEIO DO CAMINHO entre strikes consecutivos."""
    ss, _ = grade(strikes)
    return [(a + b) / 2 for a, b in pairwise(ss)]


def concentracao(precos: np.ndarray, qtds: np.ndarray, niveis: list[float],
                 tol: float) -> dict[str, Any]:
    """Fracao do volume negociada a menos de `tol` (em preco) de algum
    nivel, e quanto da FAIXA NEGOCIADA no dia essas bandas cobrem -- e' a
    cobertura que diz se a comparacao com o placebo e' justa."""
    if not len(precos) or not niveis or tol <= 0:
        return {}
    perto = np.zeros(len(precos), dtype=bool)
    lo, hi = float(precos.min()), float(precos.max())
    coberto = 0.0
    for n in niveis:
        perto |= np.abs(precos - n) <= tol
        coberto += max(0.0, min(hi, n + tol) - max(lo, n - tol))
    total = float(qtds.sum())
    faixa = max(hi - lo, 1e-9)
    return {"fracao_do_volume_perto": round(float(qtds[perto].sum() / total), 4) if total else None,
            "negocios_perto": int(perto.sum()),
            "cobertura_da_faixa_do_dia": round(min(coberto / faixa, 1.0), 4),
            "niveis_dentro_da_faixa": int(sum(1 for n in niveis if lo - tol <= n <= hi + tol))}


def medir_dia(curated: Path, papel: str, dia: dt.date, strikes: list[float],
              vencimento: dt.date, series: list[str] | None = None,
              tol_frac: float = TOL_FRAC_DO_ESPACAMENTO,
              **_legado: Any) -> dict[str, Any]:
    t = carregar_papel(curated, papel, dia)
    if t.empty:
        return {}
    p = t["price"].to_numpy(dtype=float)
    q = t["quantidade"].to_numpy(dtype=float)
    ss, espacamento = grade(strikes)
    tol = tol_frac * espacamento
    r: dict[str, Any] = {
        "dia": dia.isoformat(),
        "pregoes_ate_o_vencimento": int(np.busday_count(dia, vencimento)),
        "negocios": len(t), "volume": int(q.sum()),
        "faixa_do_dia": [round(float(p.min()), 2), round(float(p.max()), 2)],
        "espacamento_da_grade": round(espacamento, 4), "tolerancia": round(tol, 4),
        "amplitude_pct": round(float((p.max() - p.min()) / p[0] * 100), 3),
        "retorno_abs_pct": round(float(abs(p[-1] - p[0]) / p[0] * 100), 3),
        "strikes": concentracao(p, q, ss, tol),
        "strikes_PLACEBO": concentracao(p, q, placebos(strikes), tol),
    }
    a, b = (r["strikes"].get("fracao_do_volume_perto"),
            r["strikes_PLACEBO"].get("fracao_do_volume_perto"))
    cob_a = r["strikes"].get("cobertura_da_faixa_do_dia", 0.0)
    cob_b = r["strikes_PLACEBO"].get("cobertura_da_faixa_do_dia", 0.0)
    if a is None or b is None or min(cob_a, cob_b) < 0.02:
        r["razao_strike_vs_placebo"] = None
        r["razao_indefinida_porque"] = (
            "alguma das faixas quase nao toca o intervalo negociado no dia "
            f"(cobertura real {cob_a}, placebo {cob_b}) -- a comparacao nao e' justa")
    else:
        r["razao_strike_vs_placebo"] = round((a + 1e-6) / (b + 1e-6), 3)
    if series:
        ativ = {}
        for s_ in series:
            ts = carregar_papel(curated, s_, dia)
            if not ts.empty:
                ativ[s_] = {"negocios": len(ts), "volume": int(ts["quantidade"].sum())}
        r["series"] = ativ
        r["negocios_nas_series"] = int(sum(x["negocios"] for x in ativ.values()))
    log.info("opcoes_vencimento.dia", dia=r["dia"],
             pregoes_ate_o_vencimento=r["pregoes_ate_o_vencimento"], volume=r["volume"],
             razao=r["razao_strike_vs_placebo"],
             cobertura=[cob_a, cob_b], negocios_nas_series=r.get("negocios_nas_series"))
    return r


def descrever(curated: Path, papel: str, dias: list[dt.date], strikes: list[float],
              vencimento: dt.date, series: list[str] | None = None,
              tol_frac: float = TOL_FRAC_DO_ESPACAMENTO,
              saida: Path | None = None) -> dict[str, Any]:
    linhas = [x for d in dias
              if (x := medir_dia(curated, papel, d, strikes, vencimento, series, tol_frac))]
    if not linhas:
        raise SystemExit(f"nenhum dia com tape de {papel} em {curated}")
    df = pd.DataFrame([{k: v for k, v in x.items() if not isinstance(v, dict)} for x in linhas])
    semana = df[df["pregoes_ate_o_vencimento"] <= 5]
    resto = df[df["pregoes_ate_o_vencimento"] > 5]

    def resumo(d: pd.DataFrame) -> dict[str, Any]:
        if d.empty:
            return {}
        return {"pregoes": len(d),
                "volume_p50": float(d["volume"].median()),
                "amplitude_pct_p50": float(d["amplitude_pct"].median()),
                "retorno_abs_pct_p50": float(d["retorno_abs_pct"].median()),
                "razao_strike_vs_placebo_p50": (float(d["razao_strike_vs_placebo"].median())
                                                if d["razao_strike_vs_placebo"].notna().any()
                                                else None)}

    r = {"papel": papel, "vencimento": vencimento.isoformat(), "strikes": sorted(strikes),
         "placebos": placebos(strikes), "tol_frac_do_espacamento": tol_frac,
         "semana_do_vencimento": resumo(semana), "demais_pregoes": resumo(resto),
         "por_dia": linhas}
    if saida is not None:
        saida.mkdir(parents=True, exist_ok=True)
        (saida / "opcoes_vencimento.json").write_text(json.dumps(r, indent=2, default=str),
                                                      encoding="utf-8")
    return r
