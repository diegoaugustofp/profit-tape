"""
DEFASAGEM WIN x CESTA — descricao (passo 1, 2026-09-17).

CONTRAPARTE: o Ibovespa E' uma cesta, e o WIN tem que refletir o que
acontece nos papeis de maior peso (PETR4, VALE3, os bancos). Quem
garante isso sao ARBITRADORES, e arbitragem tem LATENCIA e custo. Se um
papel de peso se move primeiro, alguem no WIN esta' negociando um preco
que ja' esta' velho -- e' ele quem paga. A contraparte aqui nao e'
"obrigada" como na rolagem: e' LENTA, que e' a outra forma de contraparte
que perde por construcao.

POR QUE ESTA E' A UNICA QUE EXIGE A DLL: o record captura WIN, PETR4,
VALE3, ITUB4, BBAS3, BOVA11, MGLU3 e WEGE3 no MESMO tape, com timestamp
comum. Medir ordem de chegada entre ativos com precisao de milissegundo
e' impossivel para quem so' tem grafico. E' "dado raro" pelo item 3 da
lista de geracao de hipotese.

ESTE MODULO NAO E' UMA FICHA. Mede se ha' ORDEM DE CHEGADA. Categoria
`features`, zero trial.

O QUE MEDE
----------
Barras de TEMPO curtas (default 60 s; M15 e' grosso demais para ver
latencia) de cada ativo, alinhadas pelo mesmo relogio. Para cada papel:

  corr(papel_t , win_t)      -- contemporanea, a referencia
  corr(papel_t , win_{t+1})  -- o papel ANTECIPA o WIN
  corr(win_t   , papel_{t+1})-- o WIN antecipa o papel

**A assimetria e' o que importa**: se as duas defasadas forem iguais (e
proximas de zero), nao ha' ordem de chegada -- so' ha' movimento comum.
Se uma for claramente maior, ha' quem chega primeiro.

Usa RETORNO de barra (com sinal) porque correlacao defasada e' a propria
medida; mas NAO calcula p1, nao simula entrada e nao escolhe lado: o que
sai daqui e' estrutura de informacao, nao resultado. A ficha (passo 2)
so' se escreve se a assimetria existir, e ai' com custo na mesa -- 1
tick do WIN e' 5 pts, e defasagem de 60 s tem que pagar isso.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog

from ..features.pipeline import _carregar_dia

log = structlog.get_logger(__name__)
_NS = 1_000_000_000
PAPEIS_PADRAO = ("PETR4", "VALE3", "ITUB4", "BBAS3", "BOVA11")


def retornos_por_barra(curated: Path, symbol: str, dia: dt.date,
                       periodo_s: int = 60) -> pd.Series:
    """Ultimo preco de cada barra de `periodo_s`; retorno log entre barras
    consecutivas. Indice = inicio da barra em ns (relogio comum)."""
    pasta = curated / "trade" / f"dt={dia.isoformat()}"
    if not (pasta / f"sym={symbol}").exists():
        return pd.Series(dtype=float)
    t = _carregar_dia(pasta, symbol)
    if t.empty:
        return pd.Series(dtype=float)
    p = periodo_s * _NS
    t = t.assign(bar=(t["ts_ns"] // p) * p)
    ultimo = t.groupby("bar")["price"].last()
    ret: pd.Series = np.log(ultimo).diff().dropna()
    return ret


def medir_dia(curated: Path, dia: dt.date, papeis: tuple[str, ...] = PAPEIS_PADRAO,
              win: str = "WINFUT", periodo_s: int = 60) -> pd.DataFrame:
    r_win = retornos_por_barra(curated, win, dia, periodo_s)
    if r_win.empty:
        return pd.DataFrame()
    linhas = []
    for papel in papeis:
        r_p = retornos_por_barra(curated, papel, dia, periodo_s)
        if r_p.empty:
            continue
        j = pd.concat({"win": r_win, "papel": r_p}, axis=1).dropna()
        if len(j) < 30:
            continue
        linhas.append({
            "dia": dia, "papel": papel, "barras": len(j),
            "contemporanea": float(j["win"].corr(j["papel"])),
            "papel_antecipa": float(j["papel"].corr(j["win"].shift(-1))),
            "win_antecipa": float(j["win"].corr(j["papel"].shift(-1))),
        })
    return pd.DataFrame(linhas)


def descrever(curated: Path, dias: list[dt.date], papeis: tuple[str, ...] = PAPEIS_PADRAO,
              win: str = "WINFUT", periodo_s: int = 60,
              saida: Path | None = None) -> dict[str, Any]:
    partes = [medir_dia(curated, d, papeis, win, periodo_s) for d in dias]
    partes = [p for p in partes if not p.empty]
    if not partes:
        raise SystemExit(f"nenhum dia com WIN e papeis em {curated}")
    df = pd.concat(partes, ignore_index=True)
    out = {}
    for papel, sub in df.groupby("papel"):
        pa, wa = sub["papel_antecipa"], sub["win_antecipa"]
        # a assimetria por DIA, e nao so' a media: conta em quantos dias
        # cada lado ganha -- assimetria real aparece nos dois.
        out[str(papel)] = {
            "dias": len(sub), "barras_p50": int(sub["barras"].median()),
            "contemporanea_p50": round(float(sub["contemporanea"].median()), 4),
            "papel_antecipa_p50": round(float(pa.median()), 4),
            "win_antecipa_p50": round(float(wa.median()), 4),
            "assimetria_p50": round(float((pa - wa).median()), 4),
            "dias_com_papel_na_frente": int((pa > wa).sum()),
            "fracao_dias_papel_na_frente": round(float((pa > wa).mean()), 3),
        }
    r = {"periodo_s": periodo_s, "win": win,
         "dias": [d.isoformat() for d in dias], "por_papel": out}
    if saida is not None:
        saida.mkdir(parents=True, exist_ok=True)
        (saida / "defasagem.json").write_text(json.dumps(r, indent=2, default=str),
                                              encoding="utf-8")
        df.to_csv(saida / "defasagem_por_dia.csv", index=False)
    log.info("defasagem.descrita", papeis=len(out), dias=len(partes), periodo_s=periodo_s)
    return r
