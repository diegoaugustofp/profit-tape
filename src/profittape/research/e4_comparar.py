"""
E4 x GEMEO SIMULADO — custo de execucao, e o simulador executa no ideal?
(2026-09-22)

Os dois EAs recebem os MESMOS sinais: o `ea_123_vb_e4` manda ordem de
verdade na conta demo, o `ea_123_vb` preenche no nivel. A diferenca, ordem
a ordem, e' o custo de execucao.

A SEGUNDA PERGUNTA, que decide o que o E4 consegue concluir: em 22/09 as
duas ordens executaram EXATAMENTE no gatilho. Pode ser mercado calmo ou
pode ser a regra do simulador da Nelogica. Aqui isso se mede no TAPE: para
cada ordem preenchida, procura-se o primeiro negocio que cruza o nivel e
olha-se o pior preco negociado na janela seguinte. Se o mercado negociou
PIOR que o nivel e a demo executou no nivel, o preenchimento e' IDEALIZADO
-- e entao o E4 em demo mede latencia e robustez, mas NAO mede slippage, e
o criterio de "slippage <= 6 pts" so' pode ser julgado na conta real.

Nao decide nada sozinho: imprime os numeros e a leitura declarada.
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
PAPEIS = ("entrada", "stop", "alvo", "zeragem")


def carregar_operacoes(diretorio: Path, dia: dt.date | None = None) -> list[dict[str, Any]]:
    padrao = f"sinais_123_{dia.isoformat()}.jsonl" if dia else "sinais_123_*.jsonl"
    ops = []
    for arq in sorted(diretorio.glob(padrao)):
        for linha in arq.read_text(encoding="utf-8").splitlines():
            if linha.strip():
                op = json.loads(linha)
                op["_dia"] = arq.stem.replace("sinais_123_", "")
                ops.append(op)
    return ops


def _chave(op: dict[str, Any]) -> tuple[str, int, str]:
    c = op["candidato"]
    return (op["_dia"], int(c["hhmm"]), str(c["lado"]))


def _adverso(lado_ordem: str) -> int:
    """+1 se preco MAIOR e' pior (ordem de compra), -1 se menor e' pior."""
    return 1 if lado_ordem == "compra" else -1


def pior_preco_na_janela(tape: pd.DataFrame, nivel: float, lado_ordem: str,
                         janela_s: float = JANELA_S) -> dict[str, Any]:
    """Primeiro negocio que CRUZA o nivel e o pior preco nos `janela_s`
    seguintes. Cruzar = preco >= nivel (ordem de compra) ou <= (venda)."""
    if tape.empty:
        return {}
    p = tape["price"].to_numpy(dtype=float)
    ts = tape["ts_ns"].to_numpy(dtype=np.int64)
    sinal = _adverso(lado_ordem)
    cruzou = np.flatnonzero((p - nivel) * sinal >= 0)
    if not len(cruzou):
        return {"cruzou": False}
    i = int(cruzou[0])
    fim = ts[i] + int(janela_s * _NS)
    janela = p[i:][ts[i:] <= fim]
    pior = float(janela.max() if sinal > 0 else janela.min())
    return {"cruzou": True, "ts_cruzamento_ns": int(ts[i]), "preco_no_cruzamento": float(p[i]),
            "pior_na_janela": pior, "negocios_na_janela": len(janela),
            "pior_que_o_nivel_pts": round((pior - nivel) * sinal, 1)}


def comparar(dir_real: Path, dir_sim: Path, curated: Path | None = None,
             symbol: str = "WINFUT", dia: dt.date | None = None,
             janela_s: float = JANELA_S, saida: Path | None = None) -> dict[str, Any]:
    reais = {_chave(o): o for o in carregar_operacoes(dir_real, dia)}
    sims = {_chave(o): o for o in carregar_operacoes(dir_sim, dia)}
    if not reais:
        raise SystemExit(f"nenhuma operacao real em {dir_real}")
    tapes: dict[str, pd.DataFrame] = {}

    def tape_do_dia(d: str) -> pd.DataFrame:
        if curated is None:
            return pd.DataFrame()
        if d not in tapes:
            pasta = curated / "trade" / f"dt={d}"
            tapes[d] = (_carregar_dia(pasta, symbol).sort_values("ts_ns")
                        if (pasta / f"sym={symbol}").exists() else pd.DataFrame())
        return tapes[d]

    linhas: list[dict[str, Any]] = []
    for ch, real in sorted(reais.items()):
        sim = sims.get(ch)
        tape = tape_do_dia(ch[0])
        for papel in PAPEIS:
            o_r = (real.get("ordens") or {}).get(papel)
            if not o_r or o_r.get("fill") is None:
                continue
            o_s = ((sim or {}).get("ordens") or {}).get(papel) or {}
            nivel, fill = float(o_r["nivel"]), float(o_r["fill"])
            sinal = _adverso(str(o_r["lado"]))
            linha = {
                "dia": ch[0], "hhmm": ch[1], "lado_sinal": ch[2], "papel": papel,
                "nivel": nivel, "fill_real": fill,
                "fill_simulado": (float(o_s["fill"]) if o_s.get("fill") is not None else None),
                # POSITIVO = executou PIOR que o nivel (custo)
                "custo_pts": round((fill - nivel) * sinal, 1),
                "latencia_aceite_ms": o_r.get("latencia_aceite_ms"),
                "desfecho_real": real.get("desfecho"),
                "desfecho_simulado": (sim or {}).get("desfecho"),
                "pareado": sim is not None,
            }
            if not tape.empty and papel != "zeragem":
                linha.update(pior_preco_na_janela(tape, nivel, str(o_r["lado"]), janela_s))
            linhas.append(linha)

    df = pd.DataFrame(linhas)
    if "pior_que_o_nivel_pts" in df:
        com_tape = df[df["pior_que_o_nivel_pts"].notna()]
        mercado_pior = com_tape[com_tape["pior_que_o_nivel_pts"] > 0]
        no_nivel = mercado_pior[mercado_pior["custo_pts"] == 0]
    else:
        com_tape = mercado_pior = no_nivel = df.iloc[:0]
    r = {
        "operacoes_reais": len(reais), "operacoes_simuladas": len(sims),
        "pareadas": int(sum(1 for c in reais if c in sims)),
        "ordens_com_fill": len(df),
        "custo_medio_pts": (round(float(df["custo_pts"].mean()), 2) if not df.empty else None),
        "custo_total_pts": (round(float(df["custo_pts"].sum()), 1) if not df.empty else None),
        "fills_exatamente_no_nivel": int((df["custo_pts"] == 0).sum()) if not df.empty else 0,
        "simulador": {
            "ordens_conferidas_no_tape": len(com_tape),
            "com_mercado_PIOR_na_janela": len(mercado_pior),
            "dessas_executadas_no_NIVEL": len(no_nivel),
            "janela_s": janela_s,
        },
        "linhas": linhas,
    }
    if saida is not None:
        saida.mkdir(parents=True, exist_ok=True)
        (saida / "e4_comparacao.json").write_text(json.dumps(r, indent=2, default=str),
                                                  encoding="utf-8")
        pd.DataFrame(linhas).to_csv(saida / "e4_comparacao.csv", index=False)
    log.info("e4.comparado", **{k: v for k, v in r.items() if k != "linhas"})
    return r
