"""
ROLAGEM, pergunta A: o fluxo LIQUIDO de uma corretora no instrumento de roll
PERSISTE de um dia para o seguinte? (2026-10-04)

Motivo. A v4.28 procurava a rolagem casando quantidade e milissegundo entre as
pernas e mirava ~1% do volume. Quem rola grande trabalha uma ORDEM PAI, em
lotes e horarios diferentes. O instrumento de roll (WD1/DR1/WI1/IR1) e' onde
a rolagem acontece e esta' no tape: aqui se mede o fluxo da corretora NELE,
nao nas pernas (RESEARCH_PLANO, secao ROLAGEM: ensaio do WDO).

ESTE MODULO NAO E' UMA FICHA E NAO TEM DIRECAO. Categoria `features`, zero
trial. Responder "sim" NAO diz que o preco se move: so' libera a pergunta C.

O QUE SE MEDE
-------------
`n_a(d)` = contratos comprados menos vendidos pela corretora `a` no dia `d`,
SO' em negocios com corretoras DIFERENTES (mesma corretora nos dois lados e'
cross: o cliente que rola e' invisivel, nao ha direcao).

    S = soma_(transicoes d->d+1) soma_a min(|n_a(d)|, |n_a(d+1)|) * sinal(n_a(d) * n_a(d+1))

Volume casado de MESMO sinal menos o de sinal oposto. S > 0 = persistencia.

NULO (o que decide): inversao de sinal INDEPENDENTE por corretora e por dia
(o primeiro dia fica fixo). Preserva as magnitudes e a identidade, e testa so'
a relacao de sinal. A PERMUTACAO entre corretoras esta' ERRADA aqui: destroi a
correlacao de magnitude (corretora grande e' grande nos dois dias) e inventa
sinal. Foi o erro do baseline da v4.28 e voltou na sessao de 2026-10-03.
Limite conhecido: a inversao nao preserva a soma zero do dia (cada negocio tem
comprador e vendedor); o tamanho do teste e' conferido por simulacao.

PODER, ANTES DE OLHAR: `poder()` planta persistencia de uma fracao `f` das
corretoras nas magnitudes REAIS do evento e diz quanto o teste enxerga.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
import structlog

from ..features.pipeline import _carregar_dia

log = structlog.get_logger(__name__)
_COLS = ["ts_ns", "price", "quantidade", "agente_comprador", "agente_vendedor", "trade_type"]
FRACOES_PODER = (0.0, 0.25, 0.5, 0.75, 1.0)
Mat = npt.NDArray[np.float64]


def carregar(curated: Path, symbol: str, dia: dt.date) -> pd.DataFrame:
    pasta = curated / "trade" / f"dt={dia.isoformat()}"
    if not (pasta / f"sym={symbol}").exists():
        return pd.DataFrame()
    t = _carregar_dia(pasta, symbol)
    if t.empty:
        return pd.DataFrame()
    return t[[c for c in _COLS if c in t.columns]].reset_index(drop=True)


def liquido_por_agente(trades: pd.DataFrame) -> pd.Series:
    """Compra menos venda por corretora, so' em negocios com corretoras diferentes."""
    if trades.empty:
        return pd.Series(dtype="float64")
    d = trades[trades["agente_comprador"] != trades["agente_vendedor"]]
    comprou = d.groupby("agente_comprador")["quantidade"].sum()
    vendeu = d.groupby("agente_vendedor")["quantidade"].sum()
    return comprou.sub(vendeu, fill_value=0).astype("float64")


def alinhar(vetores: list[pd.Series]) -> Mat:
    """Matriz (dias x corretoras) sobre a uniao das corretoras; ausente = 0."""
    idx = sorted(set().union(*[set(v.index) for v in vetores]))
    return np.vstack([v.reindex(idx).fillna(0.0).to_numpy(dtype="float64") for v in vetores])


def estatistica_s(v: Mat) -> float:
    """S: volume casado de mesmo sinal menos o de sinal oposto, somado nas transicoes."""
    sg, m = np.sign(v), np.abs(v)
    total = 0.0
    for k in range(len(v) - 1):
        total += float((np.minimum(m[k], m[k + 1]) * sg[k] * sg[k + 1]).sum())
    return total


def nulo_s(v: Mat, n_sorteios: int, rng: np.random.Generator) -> npt.NDArray[np.float64]:
    """S sob H0: sinais independentes por corretora e por dia (dia 1 fixo)."""
    sg, m = np.sign(v), np.abs(v)
    n_dias, n_ag = v.shape
    f = rng.choice([-1.0, 1.0], size=(n_sorteios, n_dias, n_ag))
    f[:, 0, :] = 1.0
    out = np.zeros(n_sorteios)
    for k in range(n_dias - 1):
        casado = np.minimum(m[k], m[k + 1]) * sg[k] * sg[k + 1]
        out += (casado * f[:, k, :] * f[:, k + 1, :]).sum(axis=1)
    return out


def testar(v: Mat, n_sorteios: int = 20000, seed: int = 2026) -> dict[str, float]:
    """S observado, z contra o nulo e p UNILATERAL (persistencia positiva)."""
    rng = np.random.default_rng(seed)
    obs = estatistica_s(v)
    nulo = nulo_s(v, n_sorteios, rng)
    sd = float(nulo.std())
    z = (obs - float(nulo.mean())) / sd if sd > 0 else float("nan")
    p = (1 + int((nulo >= obs).sum())) / (1 + n_sorteios)
    return {"S": obs, "z": z, "p": p, "agentes": float(v.shape[1])}


def _plantar(v: Mat, f: float, rng: np.random.Generator) -> Mat:
    w = v.copy()
    for k in range(1, len(v)):
        base = np.sign(w[k - 1])
        aleat = rng.choice([-1.0, 1.0], size=v.shape[1])
        manter = (rng.random(v.shape[1]) < f) & (base != 0)
        w[k] = np.abs(v[k]) * np.where(manter, base, aleat)
    return w


def poder(v: Mat, fracoes: tuple[float, ...] = FRACOES_PODER, repeticoes: int = 300,
          n_sorteios: int = 1000, seed: int = 7) -> dict[str, float]:
    """Taxa de rejeicao (alfa 0,05 unilateral) quando uma fracao `f` das corretoras
    mantem o sinal do dia anterior, nas magnitudes reais. f=0 e' o TAMANHO do teste."""
    rng = np.random.default_rng(seed)
    out: dict[str, float] = {}
    for f in fracoes:
        rej = 0
        for _ in range(repeticoes):
            w = _plantar(v, f, rng)
            rej += testar(w, n_sorteios, int(rng.integers(1 << 30)))["p"] < 0.05
        out[f"{f:.2f}"] = rej / repeticoes
    return out


def descrever(curated: Path, roll: str, dias: list[dt.date], n_sorteios: int, com_poder: bool,
              saida: Path) -> dict[str, Any]:
    """Fluxo liquido por corretora no instrumento de roll, dia a dia, e a persistencia."""
    vets: list[pd.Series] = []
    uteis: list[dt.date] = []
    por_dia: list[dict[str, Any]] = []
    for i, d in enumerate(dias, 1):
        t = carregar(curated, roll, d)
        if t.empty:
            log.info("rolagem_persistencia.dia_vazio", dia=d.isoformat(), roll=roll, i=i,
                     n=len(dias))
            continue
        liq = liquido_por_agente(t)
        total = int(t["quantidade"].sum())
        dif = int(t.loc[t["agente_comprador"] != t["agente_vendedor"], "quantidade"].sum())
        por_dia.append({"dia": d.isoformat(), "negocios": len(t), "contratos": total,
                        "contratos_corretoras_diferentes": dif,
                        "agentes_com_liquido": int((liq != 0).sum()),
                        "maior_liquido_abs": int(liq.abs().max()) if len(liq) else 0})
        log.info("rolagem_persistencia.dia", dia=d.isoformat(), roll=roll, i=i, n=len(dias),
                 negocios=len(t), contratos=total, contratos_dif=dif,
                 agentes=int((liq != 0).sum()))
        vets.append(liq)
        uteis.append(d)
    r: dict[str, Any] = {"roll": roll, "dias": [d.isoformat() for d in uteis], "por_dia": por_dia,
                         "n_sorteios": n_sorteios}
    if len(vets) >= 2:
        v = alinhar(vets)
        r["transicoes"] = []
        for k in range(len(vets) - 1):
            par = testar(v[k:k + 2], n_sorteios)
            rho = float(pd.Series(v[k]).corr(pd.Series(v[k + 1]), method="spearman"))
            r["transicoes"].append({"de": uteis[k].isoformat(), "para": uteis[k + 1].isoformat(),
                                    "S": par["S"], "z": par["z"], "p": par["p"],
                                    "agentes": int(par["agentes"]), "spearman": rho})
        r["conjunto"] = testar(v, n_sorteios)
        if com_poder:
            r["poder"] = poder(v)
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "rolagem_persistencia.json").write_text(
        json.dumps(r, indent=2, ensure_ascii=False, default=float), encoding="utf-8")
    return r
