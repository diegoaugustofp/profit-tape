"""
ROLAGEM: o PAR CASADO entre os dois contratos (2026-09-22).

A v1 (setembro) mediu a rolagem no AGREGADO da serie continua e nao achou
marca -- e foi RECLASSIFICADA como teste fraco: a serie continua do Profit
substitui o contrato por baixo, ou seja, o dado com que medi APAGA o
evento. A assinatura de verdade e' o PAR CASADO: o mesmo agente vendendo
num contrato e comprando no outro, em segundos.

CONTRAPARTE: quem esta' posicionado no contrato que vence e' OBRIGADO a
rolar ou fechar. Nao escolhe o dia nem o preco -- escolhe entre rolar e
sair.

ESTE MODULO NAO E' UMA FICHA. Mede se o par casado existe ALEM DO ACASO.
Categoria `features`, zero trial, SEM DIRECAO.

O QUE E' UM PAR
---------------
Negocio no contrato A em que o agente X esta' de um lado, e negocio no
contrato B, em ate' `janela_s`, em que o MESMO agente X esta' do lado
CONTRARIO. Conta-se cada negocio de A que tem contraparte em B.

BASELINE (o que decide): os mesmos negocios, com os rotulos de AGENTE
PERMUTADOS dentro de cada contrato. Preserva volume, horario e preco;
destroi so' a identidade. Com dezenas de corretoras e milhoes de negocios,
coincidencia e' muita -- sem o embaralhado, qualquer contagem parece
grande (licao do iceberg no tape).

LIMITE DECLARADO: agente na B3 e' CORRETORA, nao cliente final. Um par
casado pode ser dois clientes diferentes da mesma corretora. Reduz o
poder; nao invalida -- o embaralhado sofre o mesmo e serve de controle.
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
JANELA_S = 2.0
_COLS = ["ts_ns", "price", "quantidade", "agente_comprador", "agente_vendedor", "trade_type"]


def carregar(curated: Path, symbol: str, dia: dt.date) -> pd.DataFrame:
    pasta = curated / "trade" / f"dt={dia.isoformat()}"
    if not (pasta / f"sym={symbol}").exists():
        return pd.DataFrame()
    t = _carregar_dia(pasta, symbol)
    if t.empty:
        return pd.DataFrame()
    return t.sort_values("ts_ns")[[c for c in _COLS if c in t.columns]].reset_index(drop=True)


def _casar(ts_a: np.ndarray, ag_a: np.ndarray, ts_b: np.ndarray, ag_b: np.ndarray,
           janela_ns: int) -> np.ndarray:
    """Para cada negocio de A, existe negocio de B do MESMO agente em ate'
    `janela_ns` (nos dois sentidos do tempo)? Vetorizado por agente."""
    casou = np.zeros(len(ts_a), dtype=bool)
    if not len(ts_a) or not len(ts_b):
        return casou
    ordem_b = np.argsort(ag_b, kind="stable")
    ag_b_ord, ts_b_ord = ag_b[ordem_b], ts_b[ordem_b]
    inicio = np.searchsorted(ag_b_ord, ag_a, side="left")
    fim = np.searchsorted(ag_b_ord, ag_a, side="right")
    for i in np.flatnonzero(fim > inicio):
        bloco = np.sort(ts_b_ord[inicio[i]:fim[i]])
        j = int(np.searchsorted(bloco, ts_a[i]))
        for k in (j - 1, j):
            if 0 <= k < len(bloco) and abs(int(bloco[k]) - int(ts_a[i])) <= janela_ns:
                casou[i] = True
                break
    return casou


def medir_dia(curated: Path, vencendo: str, proximo: str, dia: dt.date,
              janela_s: float = JANELA_S, semente: int = 1) -> dict[str, Any]:
    a, b = carregar(curated, vencendo, dia), carregar(curated, proximo, dia)
    if a.empty or b.empty:
        return {}
    janela_ns = int(janela_s * _NS)
    rng = np.random.default_rng(semente)
    ts_a = a["ts_ns"].to_numpy(dtype=np.int64)
    ts_b = b["ts_ns"].to_numpy(dtype=np.int64)
    r: dict[str, Any] = {"dia": dia.isoformat(), "negocios_vencendo": len(a),
                         "negocios_proximo": len(b),
                         "volume_vencendo": int(a["quantidade"].sum()),
                         "volume_proximo": int(b["quantidade"].sum())}
    # ROLAR UMA COMPRA: vende no que vence e compra no proximo (e o inverso).
    for nome, lado_a, lado_b in (("vende_A_compra_B", "agente_vendedor", "agente_comprador"),
                                 ("compra_A_vende_B", "agente_comprador", "agente_vendedor")):
        ag_a = a[lado_a].to_numpy(dtype=np.int64)
        ag_b = b[lado_b].to_numpy(dtype=np.int64)
        obs = _casar(ts_a, ag_a, ts_b, ag_b, janela_ns)
        base = _casar(ts_a, rng.permutation(ag_a), ts_b, rng.permutation(ag_b), janela_ns)
        vol = int(a.loc[obs, "quantidade"].sum())
        r[nome] = {
            "pares": int(obs.sum()), "pares_baseline": int(base.sum()),
            "razao": round((int(obs.sum()) + 1) / (int(base.sum()) + 1), 3),
            "volume_nos_pares": vol,
            "fracao_do_volume": round(vol / max(int(a["quantidade"].sum()), 1), 4),
        }
    log.info("rolagem_par.dia", **{k: v for k, v in r.items() if not isinstance(v, dict)},
             razao_vende_A=r["vende_A_compra_B"]["razao"],
             razao_compra_A=r["compra_A_vende_B"]["razao"])
    return r


def descrever(curated: Path, vencendo: str, proximo: str, dias: list[dt.date],
              janela_s: float = JANELA_S, saida: Path | None = None) -> dict[str, Any]:
    linhas = [x for d in dias if (x := medir_dia(curated, vencendo, proximo, d, janela_s))]
    if not linhas:
        raise SystemExit(f"nenhum dia com tape de {vencendo} E {proximo} em {curated}")
    agregado = {
        nome: {
            "pares_p50": float(np.median([x[nome]["pares"] for x in linhas])),
            "baseline_p50": float(np.median([x[nome]["pares_baseline"] for x in linhas])),
            "razao_p50": float(np.median([x[nome]["razao"] for x in linhas])),
            "fracao_do_volume_p50": float(np.median([x[nome]["fracao_do_volume"]
                                                     for x in linhas])),
        } for nome in ("vende_A_compra_B", "compra_A_vende_B")}
    r = {"vencendo": vencendo, "proximo": proximo, "janela_s": janela_s, "dias": len(linhas),
         "agregado": agregado, "por_dia": linhas}
    if saida is not None:
        saida.mkdir(parents=True, exist_ok=True)
        (saida / "rolagem_par.json").write_text(json.dumps(r, indent=2, default=str),
                                                encoding="utf-8")
    return r
