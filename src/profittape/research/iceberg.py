"""
ICEBERG / LOTE REPETIDO — passo 1 (2026-09-17, desenho em RESEARCH_PLANO).

CONTRAPARTE: iceberg e', por definicao, alguem que QUER ESCONDER TAMANHO
-- logo tem tamanho e uma razao para nao mostrar. Quem negocia contra
isso enfrenta profundidade que NAO VE.

ESTE MODULO NAO E' UMA FICHA. Mede se a assinatura existe, contra o
ACASO. Categoria `features`, zero trial, SEM DIRECAO (nao olha retorno).

O QUE E' UMA "CORRIDA" (run)
---------------------------
Sequencia de negocios com a MESMA quantidade no MESMO preco, em que cada
um esta' a no maximo `janela_s` do anterior. Negocios de OUTROS precos no
meio nao interrompem -- e' justamente assim que um iceberg se recompoe.

O QUE DECIDE A LINHA: O BASELINE
--------------------------------
Com milhoes de negocios e lotes concentrados em numeros pequenos, corrida
de mesma quantidade acontece MUITO por acaso. A medida so' vale contra o
embaralhado: as MESMAS quantidades, os MESMOS precos e instantes, com as
quantidades PERMUTADAS. Se o observado nao superar o embaralhado, o
"iceberg" e' coincidencia e a linha morre aqui, barato.

RLP, DECIDIDO ANTES DE OLHAR RESULTADO
--------------------------------------
RLP (`trade_type=13`, ~25% do WIN) e' preco de referencia: repete por
construcao. Tudo e' medido DUAS vezes -- com e sem RLP. Nao ha' escolha
depois: os dois numeros sao reportados sempre.

O QUE NAO SE MEDE AQUI: se o nivel segura e o retorno depois. Isso e' a
ficha (passo 2), e so' se escreve se o baseline e a recomposicao
passarem -- com a direcao declarada antes ("nivel com iceberg SEGURA" e
"nivel com iceberg ROMPE e acelera" sao hipoteses OPOSTAS).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import numpy as np
import structlog

from ..domain.enums import TradeType
from ..features.pipeline import _carregar_dia

log = structlog.get_logger(__name__)
_NS = 1_000_000_000
_RLP = int(TradeType.RLP)
JANELA_S = 30.0          # intervalo maximo entre negocios da mesma corrida
N_MINIMO = 10            # corrida "relevante" (volume e recomposicao)
# CURVA POR LIMIAR (2026-09-17, exigida pelo proprio teste): contar corridas
# de >= 5 nao separa nada -- com lotes pequenos em poucos niveis, o acaso
# produz MILHARES delas, e um iceberg plantado de 30 recargas sumia no meio
# (razao 0,999). Corrida aleatoria de 30 iguais no mesmo preco e' rara;
# iceberg de 30 recargas nao e'. Reporta-se a CURVA inteira, sempre -- nao
# se escolhe o limiar depois de ver.
LIMIARES = (5, 10, 20, 30, 50)
TOL_TICKS = 1.0          # o preco "saiu do nivel" se passou disto (recomposicao)


def _corridas(ts: np.ndarray, price: np.ndarray, qtd: np.ndarray,
              janela_ns: int) -> tuple[np.ndarray, np.ndarray]:
    """Devolve (id_da_corrida por trade, na ordem ORDENADA por
    preco/quantidade/ts) e a ordem usada. Vetorizado: com 6 M de linhas,
    groupby em Python nao termina."""
    ordem = np.lexsort((ts, qtd, price))
    p, q, t = price[ordem], qtd[ordem], ts[ordem]
    nova = np.empty(len(t), dtype=bool)
    nova[0] = True
    nova[1:] = (p[1:] != p[:-1]) | (q[1:] != q[:-1]) | ((t[1:] - t[:-1]) > janela_ns)
    return np.cumsum(nova) - 1, ordem


def _resumo_corridas(ts: np.ndarray, price: np.ndarray, qtd: np.ndarray,
                     janela_s: float, n_minimo: int) -> dict[str, Any]:
    if len(ts) == 0:
        return {}
    ids, ordem = _corridas(ts, price, qtd, int(janela_s * _NS))
    tam = np.bincount(ids)
    q_ord = qtd[ordem]
    vol_por_corrida = np.bincount(ids, weights=q_ord)
    relevantes = tam >= n_minimo
    vol_total = float(q_ord.sum())
    return {
        "por_limiar": {str(n): int((tam >= n).sum()) for n in LIMIARES},
        "trades": len(ts),
        "corridas": len(tam),
        "corridas_relevantes": int(relevantes.sum()),
        "tamanho_p50": float(np.median(tam)),
        "tamanho_p99": float(np.percentile(tam, 99)),
        "tamanho_max": int(tam.max()),
        "fracao_do_volume_em_corridas_relevantes": (
            round(float(vol_por_corrida[relevantes].sum() / vol_total), 4) if vol_total else None),
        "_ids": ids, "_ordem": ordem, "_tam": tam, "_relevantes": relevantes,
    }


def _recomposicao(ts_ord: np.ndarray, price_ord: np.ndarray, ids: np.ndarray,
                  relevantes: np.ndarray, ts_todos: np.ndarray, price_todos: np.ndarray,
                  tick: float) -> dict[str, Any]:
    """Das corridas relevantes, em quantas o preco SAIU do nivel (mais de
    `TOL_TICKS`) entre o primeiro e o ultimo negocio e VOLTOU? E' o que
    separa iceberg (recompoe) de negocio picado seguido."""
    if not relevantes.any():
        return {"avaliadas": 0}
    # max/min de preco por SEGUNDO do dia (barato: ~33 k pontos)
    seg = ((ts_todos - ts_todos[0]) // _NS).astype(np.int64)
    n_seg = int(seg[-1]) + 1
    alto = np.full(n_seg, -np.inf)
    baixo = np.full(n_seg, np.inf)
    np.maximum.at(alto, seg, price_todos)
    np.minimum.at(baixo, seg, price_todos)
    idx = np.flatnonzero(relevantes)
    inicio_de = {}
    fim_de = {}
    for i, cid in enumerate(ids):
        if cid not in inicio_de:
            inicio_de[cid] = i
        fim_de[cid] = i
    saiu = 0
    for cid in idx:
        a, b = inicio_de[int(cid)], fim_de[int(cid)]
        nivel = price_ord[a]
        s0 = int((ts_ord[a] - ts_todos[0]) // _NS)
        s1 = int((ts_ord[b] - ts_todos[0]) // _NS) + 1
        if s1 <= s0:
            continue
        if (alto[s0:s1].max() > nivel + TOL_TICKS * tick
                or baixo[s0:s1].min() < nivel - TOL_TICKS * tick):
            saiu += 1
    return {"avaliadas": len(idx), "com_recomposicao": saiu,
            "fracao_com_recomposicao": round(saiu / max(len(idx), 1), 4)}


def medir_dia(curated: Path, symbol: str, dia: dt.date, janela_s: float = JANELA_S,
              n_minimo: int = N_MINIMO, tick: float = 5.0,
              semente: int = 1) -> dict[str, Any]:
    pasta = curated / "trade" / f"dt={dia.isoformat()}"
    if not (pasta / f"sym={symbol}").exists():
        return {}
    t = _carregar_dia(pasta, symbol)
    if t.empty:
        return {}
    t = t.sort_values("ts_ns")
    saida: dict[str, Any] = {"dia": dia.isoformat()}
    rng = np.random.default_rng(semente)
    for nome, sub in (("com_rlp", t), ("sem_rlp", t[t["trade_type"] != _RLP])):
        if sub.empty:
            continue
        ts = sub["ts_ns"].to_numpy(dtype=np.int64)
        price = sub["price"].to_numpy(dtype=float)
        qtd = sub["quantidade"].to_numpy(dtype=float)
        obs = _resumo_corridas(ts, price, qtd, janela_s, n_minimo)
        rec = _recomposicao(ts[obs["_ordem"]], price[obs["_ordem"]], obs["_ids"],
                            obs["_relevantes"], ts, price, tick)
        # BASELINE: mesmas quantidades, mesmos precos e instantes, quantidades PERMUTADAS
        base = _resumo_corridas(ts, price, rng.permutation(qtd), janela_s, n_minimo)
        limpo = {k: v for k, v in obs.items() if not k.startswith("_")}
        limpo_base = {k: v for k, v in base.items() if not k.startswith("_")}
        limpo["recomposicao"] = rec
        limpo["baseline_embaralhado"] = limpo_base
        limpo["razao_por_limiar"] = {
            n: (round(obs["por_limiar"][n] / base["por_limiar"][n], 3)
                if base["por_limiar"][n] else None)
            for n in obs["por_limiar"]}
        limpo["razao_vs_baseline"] = (
            round(obs["corridas_relevantes"] / base["corridas_relevantes"], 3)
            if base["corridas_relevantes"] else None)
        saida[nome] = limpo
    return saida


def descrever(curated: Path, symbol: str, dias: list[dt.date], janela_s: float = JANELA_S,
              n_minimo: int = N_MINIMO, tick: float = 5.0,
              saida: Path | None = None) -> dict[str, Any]:
    por_dia = [medir_dia(curated, symbol, d, janela_s, n_minimo, tick) for d in dias]
    por_dia = [d for d in por_dia if d]
    if not por_dia:
        raise SystemExit(f"nenhum dia com tape de {symbol} em {curated}")
    agregado: dict[str, Any] = {}
    for nome in ("com_rlp", "sem_rlp"):
        linhas = [d[nome] for d in por_dia if nome in d]
        if not linhas:
            continue
        agregado[nome] = {
            "dias": len(linhas),
            "corridas_relevantes_p50": float(np.median([x["corridas_relevantes"] for x in linhas])),
            "baseline_p50": float(np.median(
                [x["baseline_embaralhado"]["corridas_relevantes"] for x in linhas])),
            "razao_vs_baseline_p50": float(np.median(
                [x["razao_vs_baseline"] for x in linhas if x["razao_vs_baseline"]])),
            "dias_acima_do_baseline": int(sum(
                1 for x in linhas if (x["razao_vs_baseline"] or 0) > 1)),
            "por_limiar": {
                n: {"observado_p50": float(np.median([x["por_limiar"][n] for x in linhas])),
                    "baseline_p50": float(np.median(
                        [x["baseline_embaralhado"]["por_limiar"][n] for x in linhas])),
                    "razao_p50": (float(np.median(
                        [x["razao_por_limiar"][n] for x in linhas
                         if x["razao_por_limiar"][n] is not None]))
                        if any(x["razao_por_limiar"][n] is not None for x in linhas) else None)}
                for n in linhas[0]["por_limiar"]},
            "fracao_do_volume_p50": float(np.median(
                [x["fracao_do_volume_em_corridas_relevantes"] for x in linhas])),
            "fracao_com_recomposicao_p50": float(np.median(
                [x["recomposicao"].get("fracao_com_recomposicao", 0) for x in linhas])),
        }
    r = {"symbol": symbol, "janela_s": janela_s, "n_minimo": n_minimo,
         "agregado": agregado, "por_dia": por_dia}
    if saida is not None:
        saida.mkdir(parents=True, exist_ok=True)
        (saida / "iceberg.json").write_text(json.dumps(r, indent=2, default=str),
                                            encoding="utf-8")
    log.info("iceberg.descrito", symbol=symbol, dias=len(por_dia),
             razao=agregado.get("sem_rlp", {}).get("razao_vs_baseline_p50"))
    return r
