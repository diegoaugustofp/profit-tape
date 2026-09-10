"""
Scalp de Bollinger (15s): barras do TAPE e replay das tres pernas.

POR QUE PELO TAPE, E NAO PELO OHLC
----------------------------------
Numa barra de 15s a barra mediana anda 49-64 pts e o stop e' ~62: em
2 de 3 barras stop e alvo cabem na MESMA barra. O high/low nao diz quem
bateu primeiro; o tape diz. E' a mesma razao pela qual o projeto existe
em ProfitDLL/Python -- o Profit so' tem 1 semana de tick a tick.

TRES PARTES
-----------
1. `barras_15s_do_tape`  -- OHLC de 15s de um pregao a partir dos
                            negocios. Reinicia a cada pregao (ficha:
                            "os indicadores so' enxergam o pregao de
                            hoje").
2. `comparar_com_dump`   -- as barras do tape contra as do grafico
                            (dump BBSBARRA). Recalcular e comparar MEDE.
3. `replay_pregao`       -- percorre o tape negocio a negocio: a
                            limitada em t, as tres pernas, o trailing,
                            a zeragem. Sai uma linha por OPERACAO.

O que o replay NAO consegue simular, e assume (registrado para nao
virar surpresa no forward):
- Preenchimento da limitada: `abertura` se o primeiro negocio de t ja'
  esta' a favor (executa nesse preco); `recuo` so' se um negocio
  imprime ESTRITAMENTE atraves do limite (fila da B3: tocar nao e'
  executar). Pessimista.
- Lote 3 preenchido inteiro (a execucao parcial nao e' simulavel).
- Alvo executa no toque (limitada ja' no book); stop executa NO PRECO
  do stop (slippage zero). O custo de 11 pts por contrato, ida e volta,
  cobre parte disso; o resto e' o forward que mede.
- Dentro de um mesmo negocio, stop e' checado antes do alvo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog

from ..features.pipeline import _carregar_dia, _dias_do_symbol
from . import bollinger_scalp as bs

log = structlog.get_logger(__name__)

_NS = 1_000_000_000
_PERIODO_NS = bs.SEGUNDOS_BARRA * _NS
TZ_OFFSET_H = -3
TIPOS_OHLC_PADRAO = (2, 3)  # agressao; RLP (13) e leilao (4) fora
# O grafico do Profit pode montar o OHLC com outro conjunto de negocios.
# Medido em 2026-09-10 com (2, 3): high/low divergem em ~4% das barras,
# open/close em ~30% -- padrao de RLP (imprime DENTRO do spread: nao
# muda o extremo, muda o primeiro/ultimo negocio). Candidatos medidos:
CANDIDATOS_OHLC: dict[str, tuple[int, ...]] = {
    "agressao": (2, 3),
    "agressao+rlp": (2, 3, 13),
    "agressao+rlp+leilao": (2, 3, 4, 13),
}
CUSTO_POR_CONTRATO_PTS = 11.0
CONTRATOS = 3
HORA_ZERAGEM = 1730
MAX_PERDAS_CONSECUTIVAS = 3


# ---------------------------------------------------------------------
# 1. Barras de 15s do tape
# ---------------------------------------------------------------------
def barras_15s_do_tape(
    trades: pd.DataFrame, dia: str, tipos_ohlc: tuple[int, ...] = TIPOS_OHLC_PADRAO
) -> pd.DataFrame:
    """
    Um pregao. Balde = ts_ns // 15s (epoch; alinha com :00/:15/:30/:45
    porque o fuso da B3 e' hora inteira). Barra sem negocio dos tipos
    escolhidos nao existe -- o Profit desenha toda barra (medido), mas
    so' porque o WIN tem negocio em todo 15s; se um balde faltar, o
    parser do dump e este aqui vao divergir e a comparacao mostra.

    Colunas no mesmo espirito do dump: dia, hora_int (HHMM local), ts,
    open/high/low/close, vol_total, current_bar (indice no dia), bloco
    (= um por pregao: os indicadores reiniciam).
    """
    t = trades[trades["trade_type"].isin(tipos_ohlc)]
    if t.empty:
        return pd.DataFrame()
    chaves = ["ts_ns", "trade_id"] if "trade_id" in t.columns else ["ts_ns"]
    t = t.sort_values(chaves, kind="stable")
    balde = (t["ts_ns"].to_numpy() // _PERIODO_NS).astype(np.int64)
    g = t.groupby(balde, sort=True)
    b = pd.DataFrame(
        {
            "open": g["price"].first(),
            "high": g["price"].max(),
            "low": g["price"].min(),
            "close": g["price"].last(),
            "vol_total": g["quantidade"].sum().astype(float),
            "negocios": g.size().astype(int),
        }
    )
    b.index.name = "balde"
    b = b.reset_index()
    b["ts"] = pd.to_datetime(b["balde"] * bs.SEGUNDOS_BARRA + TZ_OFFSET_H * 3600, unit="s")
    b["dia"] = pd.to_datetime(dia).date()
    b["hora_int"] = b["ts"].dt.hour * 100 + b["ts"].dt.minute
    b["current_bar"] = np.arange(1, len(b) + 1)
    b["bloco"] = 1
    b["ts_ini_ns"] = b["balde"] * _PERIODO_NS
    return b.reset_index(drop=True)


def indicadores_e_sinais_do_tape(barras: pd.DataFrame) -> pd.DataFrame:
    """Indicadores Python (as variantes que BATEM com o Profit: ddof=0,
    %K lento, SMA do TR) e a regra v1."""
    d = bs.indicadores(barras)
    return bs.marcar_sinais(
        d, col_sup="bb_sup_ddof0", col_inf="bb_inf_ddof0", col_est="k_lento", col_atr="atr_sma"
    )


# ---------------------------------------------------------------------
# 2. Tape x grafico
# ---------------------------------------------------------------------
def comparar_com_dump(
    tape: pd.DataFrame, dump: pd.DataFrame, tol_pts: float = 0.5
) -> dict[str, Any]:
    """
    Junta por (dia, ts). Conta barras so' de um lado, OHLC divergente
    (por campo) e SINAIS divergentes -- o que importa no fim e' se o
    replay ve os mesmos gatilhos que o operador ve no grafico.
    """
    chaves = ["dia", "ts"]
    t = tape.set_index(chaves)
    d = dump.set_index(chaves)
    comuns = t.index.intersection(d.index)
    out: dict[str, Any] = {
        "barras_tape": len(t),
        "barras_dump": len(d),
        "comuns": len(comuns),
        "so_tape": len(t.index.difference(d.index)),
        "so_dump": len(d.index.difference(t.index)),
    }
    so_dump = d.index.difference(t.index)
    if len(so_dump):
        horas = sorted(int(h) for _, h in [(k[0], d.loc[k, "hora_int"]) for k in so_dump])
        out["so_dump_de"] = horas[0]
        out["so_dump_ate"] = horas[-1]
    if len(comuns) == 0:
        return out
    tt, dd = t.loc[comuns], d.loc[comuns]
    for c in ("open", "high", "low", "close"):
        dif = (tt[c] - dd[c]).abs()
        out[f"{c}_divergentes"] = int((dif > tol_pts).sum())
        out[f"{c}_dif_max"] = round(float(dif.max()), 1)
    for s in ("sinal_compra", "sinal_venda"):
        if s in tt.columns and s in dd.columns:
            a, b = tt[s].astype(bool), dd[s].astype(bool)
            out[f"{s}_tape"] = int(a.sum())
            out[f"{s}_dump"] = int(b.sum())
            out[f"{s}_so_tape"] = int((a & ~b).sum())
            out[f"{s}_so_dump"] = int((~a & b).sum())
    return out


# ---------------------------------------------------------------------
# 3. Replay das tres pernas
# ---------------------------------------------------------------------
@dataclass
class Perna:
    alvo: float
    stop: float
    trailing: bool
    ativa_pts: float
    puxa_pts: float
    passo_pts: float
    ativada: bool = False
    ultimo_max_fav: float = 0.0
    aberta: bool = True
    resultado_pts: float = 0.0
    motivo: str = ""
    ts_saida: int = 0


@dataclass
class Operacao:
    dia: str
    lado: int  # +1 compra, -1 venda
    ts_sinal_ns: int
    hora_sinal: int
    preco_limite: float
    stop_pts: float
    preco_entrada: float = 0.0
    ts_entrada_ns: int = 0
    tipo_execucao: str = ""
    motivo_nao_exec: str = ""  # posicao_aberta | circuit_breaker | nao_atravessou
    pernas: list[Perna] = field(default_factory=list)
    max_fav_pts: float = 0.0

    def fechada(self) -> bool:
        return all(not p.aberta for p in self.pernas)

    def pnl_bruto_pts(self) -> float:
        return float(sum(p.resultado_pts for p in self.pernas))


def _hora_local(ts_ns: int) -> int:
    seg = (ts_ns // _NS + TZ_OFFSET_H * 3600) % 86400
    return int(seg // 3600) * 100 + int((seg % 3600) // 60)


def _abrir_pernas(op: Operacao, sinal: pd.Series) -> None:
    alvos = (sinal["alvo1_pts"], sinal["alvo2_pts"], sinal["alvo3_pts"])
    for i, a in enumerate(alvos):
        op.pernas.append(
            Perna(
                alvo=op.preco_entrada + op.lado * a,
                stop=op.preco_entrada - op.lado * op.stop_pts,
                trailing=(i > 0),
                ativa_pts=float(sinal["trailing_ativa_pts"]),
                puxa_pts=float(sinal["trailing_puxa_pts"]),
                passo_pts=float(sinal["trailing_passo_pts"]),
            )
        )


def _processar_negocio(op: Operacao, preco: float, ts_ns: int) -> None:
    """Um negocio contra uma operacao aberta. Stop antes do alvo; depois
    o trailing e' atualizado com este mesmo preco (ele so' vale para o
    PROXIMO negocio -- um stop puxado nao e' executado pelo negocio que
    o puxou)."""
    fav = op.lado * (preco - op.preco_entrada)
    for p in op.pernas:
        if not p.aberta:
            continue
        if op.lado * (preco - p.stop) <= 0:
            p.aberta, p.motivo, p.ts_saida = False, "stop", ts_ns
            p.resultado_pts = op.lado * (p.stop - op.preco_entrada)
        elif op.lado * (preco - p.alvo) >= 0:
            p.aberta, p.motivo, p.ts_saida = False, "alvo", ts_ns
            p.resultado_pts = op.lado * (p.alvo - op.preco_entrada)
    if fav > op.max_fav_pts:
        op.max_fav_pts = fav
        for p in op.pernas:
            if not (p.aberta and p.trailing):
                continue
            if not p.ativada and fav >= p.ativa_pts:
                p.ativada = True
                p.ultimo_max_fav = fav
                p.stop = op.preco_entrada + op.lado * (fav - p.puxa_pts)
            elif p.ativada and fav - p.ultimo_max_fav >= p.passo_pts:
                p.ultimo_max_fav = fav
                p.stop = op.preco_entrada + op.lado * (fav - p.puxa_pts)


def _zerar(op: Operacao, preco: float, ts_ns: int, motivo: str) -> None:
    for p in op.pernas:
        if p.aberta:
            p.aberta, p.motivo, p.ts_saida = False, motivo, ts_ns
            p.resultado_pts = op.lado * (preco - op.preco_entrada)


def replay_pregao(
    sinais: pd.DataFrame,
    trades: pd.DataFrame,
    dia: str,
    custo_por_contrato: float = CUSTO_POR_CONTRATO_PTS,
    contratos: int = CONTRATOS,
    max_perdas: int = MAX_PERDAS_CONSECUTIVAS,
) -> list[dict[str, Any]]:
    """
    `sinais` = saida de `indicadores_e_sinais_do_tape` para o pregao.
    `trades` = todos os negocios do pregao (a limitada e as pernas sao
    executadas contra negocios de AGRESSAO; RLP e leilao nao imprimem
    preco negociavel).
    """
    t = trades[trades["trade_type"].isin(TIPOS_OHLC_PADRAO)].sort_values("ts_ns", kind="stable")
    ts = t["ts_ns"].to_numpy(dtype=np.int64)
    px = t["price"].to_numpy(dtype=float)
    n = len(ts)
    ini_balde = (ts // _PERIODO_NS).astype(np.int64)
    # indice do primeiro negocio de cada barra (pelo ts_ini_ns da barra)
    baldes_sinal = sinais.loc[sinais["sinal_compra"] | sinais["sinal_venda"]]
    ops: list[Operacao] = []
    perdas_seguidas = 0
    bloqueado = False
    proximo_negocio_livre = 0  # posicao so' pode abrir apos fechar

    for _, s in baldes_sinal.iterrows():
        if bloqueado:
            break
        balde = int(s["ts_ini_ns"] // _PERIODO_NS)
        i0 = int(np.searchsorted(ini_balde, balde, side="left"))
        i1 = int(np.searchsorted(ini_balde, balde, side="right"))
        if i0 >= n or i0 < proximo_negocio_livre:
            continue  # posicao aberta (ou fechou dentro de t)
        lado = 1 if bool(s["sinal_compra"]) else -1
        limite = float(s["preco_limite"])
        op = Operacao(
            dia=dia,
            lado=lado,
            ts_sinal_ns=int(s["ts_ini_ns"]),
            hora_sinal=int(s["hora_int"]),
            preco_limite=limite,
            stop_pts=float(s["stop_pts"]),
        )
        # --- preenchimento da limitada dentro da barra t ---
        j_fill = -1
        if lado * (px[i0] - limite) <= 0:  # abertura ja' a favor
            j_fill, op.preco_entrada, op.tipo_execucao = i0, float(px[i0]), "abertura"
        else:
            atravessa = np.where(lado * (px[i0:i1] - limite) < 0)[0]
            if len(atravessa):
                j_fill, op.preco_entrada, op.tipo_execucao = i0 + int(atravessa[0]), limite, "recuo"
        if j_fill < 0:
            op.motivo_nao_exec = "nao_atravessou"
            ops.append(op)
            continue
        op.ts_entrada_ns = int(ts[j_fill])
        _abrir_pernas(op, s)
        # --- percorre o tape ate' fechar as tres pernas ---
        j = j_fill + 1
        while j < n and not op.fechada():
            if _hora_local(int(ts[j])) >= HORA_ZERAGEM:
                _zerar(op, float(px[j]), int(ts[j]), "zeragem")
                break
            _processar_negocio(op, float(px[j]), int(ts[j]))
            j += 1
        if not op.fechada():
            _zerar(op, float(px[n - 1]), int(ts[n - 1]), "fim_do_tape")
            j = n
        proximo_negocio_livre = j
        ops.append(op)
        liquido = op.pnl_bruto_pts() - custo_por_contrato * contratos
        perdas_seguidas = perdas_seguidas + 1 if liquido < 0 else 0
        if perdas_seguidas >= max_perdas:
            bloqueado = True

    return [_op_para_dict(o, custo_por_contrato, contratos) for o in ops]


def _op_para_dict(o: Operacao, custo: float, contratos: int) -> dict[str, Any]:
    d: dict[str, Any] = {
        "dia": o.dia,
        "lado": o.lado,
        "hora_sinal": o.hora_sinal,
        "ts_sinal_ns": o.ts_sinal_ns,
        "preco_limite": o.preco_limite,
        "stop_pts": o.stop_pts,
        "executou": bool(o.pernas),
        "tipo_execucao": o.tipo_execucao,
        "motivo_nao_exec": o.motivo_nao_exec,
        "preco_entrada": o.preco_entrada,
        "ts_entrada_ns": o.ts_entrada_ns,
        "max_fav_pts": o.max_fav_pts,
    }
    for i, p in enumerate(o.pernas, 1):
        d[f"p{i}_pts"] = p.resultado_pts
        d[f"p{i}_motivo"] = p.motivo
        d[f"p{i}_ts_saida_ns"] = p.ts_saida
    if o.pernas:
        d["pnl_bruto_pts"] = o.pnl_bruto_pts()
        d["pnl_liquido_pts"] = o.pnl_bruto_pts() - custo * contratos
        d["duracao_s"] = (max(p.ts_saida for p in o.pernas) - o.ts_entrada_ns) / _NS
        d["p1_alvo"] = o.pernas[0].motivo == "alvo"
    return d


# ---------------------------------------------------------------------
# 4. Resumo (o que a ficha pede)
# ---------------------------------------------------------------------
def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    meia = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (centro - meia, centro + meia)


def resumo(ops: pd.DataFrame, pregoes: int) -> dict[str, Any]:
    ex = ops[ops["executou"]] if "executou" in ops.columns else ops.iloc[0:0]
    out: dict[str, Any] = {
        "pregoes": pregoes,
        "sinais": len(ops),
        "operacoes": len(ex),
        "operacoes_por_pregao": round(len(ex) / max(pregoes, 1), 1),
        "sinais_sem_execucao": int(len(ops) - len(ex)),
        "nao_exec_por_motivo": (
            ops.loc[~ops["executou"], "motivo_nao_exec"].value_counts().to_dict()
            if "motivo_nao_exec" in ops.columns
            else {}
        ),
    }
    if ex.empty:
        return out
    k = int(ex["p1_alvo"].sum())
    lo, hi = _wilson(k, len(ex))
    out.update(
        {
            "p1": round(k / len(ex), 3),
            "p1_ic95": (round(lo, 3), round(hi, 3)),
            "p1_nula_lucro": round(
                float(((ex["stop_pts"] + CUSTO_POR_CONTRATO_PTS) / (2 * ex["stop_pts"])).median()),
                3,
            ),
            "abertura": int((ex["tipo_execucao"] == "abertura").sum()),
            "recuo": int((ex["tipo_execucao"] == "recuo").sum()),
            "pnl_liquido_medio_pts": round(float(ex["pnl_liquido_pts"].mean()), 1),
            "pnl_liquido_por_pregao_pts": round(
                float(ex["pnl_liquido_pts"].sum()) / max(pregoes, 1), 1
            ),
            "duracao_mediana_s": round(float(ex["duracao_s"].median()), 0),
            "stop_mediano_pts": round(float(ex["stop_pts"].median()), 1),
            "compra": int((ex["lado"] == 1).sum()),
            "venda": int((ex["lado"] == -1).sum()),
        }
    )
    for i in (1, 2, 3):
        out[f"p{i}_motivos"] = ex[f"p{i}_motivo"].value_counts().to_dict()
        col = f"p{i}_pts"
        if col in ex.columns:
            out[f"p{i}_pts_medio"] = round(float(ex[col].mean()), 1)
            out[f"p{i}_pct_positiva"] = round(100 * float((ex[col] > 0).mean()), 1)
    # Cortes PRE-DECLARADOS (docs/BOLLINGER_SCALP.md §3 e §1): abertura x
    # recuo sao regimes de preenchimento distintos; compra x venda testa
    # o espelho. Nao sao busca -- sao conferencia de especificacao.
    cortes: dict[str, Any] = {}
    for nome, mask in (
        ("abertura", ex["tipo_execucao"] == "abertura"),
        ("recuo", ex["tipo_execucao"] == "recuo"),
        ("compra", ex["lado"] == 1),
        ("venda", ex["lado"] == -1),
    ):
        sub = ex[mask]
        if len(sub):
            kk = int(sub["p1_alvo"].sum())
            lo, hi = _wilson(kk, len(sub))
            cortes[nome] = {
                "n": len(sub),
                "p1": round(kk / len(sub), 3),
                "ic95": (round(lo, 3), round(hi, 3)),
                "pnl_liquido_medio_pts": round(float(sub["pnl_liquido_pts"].mean()), 1),
            }
    out["cortes_pre_declarados"] = cortes
    return out


# ---------------------------------------------------------------------
# 5. Rodada
# ---------------------------------------------------------------------
def rodar(
    curated: Path,
    symbol: str,
    saida: Path,
    dumps: dict[str, Path] | None = None,
    dias: list[str] | None = None,
) -> dict[str, Any]:
    origem = curated / "trade"
    pastas = _dias_do_symbol(origem, symbol)
    if dias:
        pastas = [p for p in pastas if p.name.split("=", 1)[1] in set(dias)]
    if not pastas:
        raise SystemExit(f"nenhum pregao de {symbol} em {origem}")
    todas_ops: list[dict[str, Any]] = []
    comparacoes: dict[str, Any] = {}
    barras_por_dia: list[pd.DataFrame] = []
    for i, pasta in enumerate(pastas, 1):
        dia = pasta.name.split("=", 1)[1]
        trades = _carregar_dia(pasta, symbol)
        barras = barras_15s_do_tape(trades, dia)
        if barras.empty:
            log.warning("bollinger_replay.sem_barras", dia=dia)
            continue
        sinais = indicadores_e_sinais_do_tape(barras)
        barras_por_dia.append(sinais)
        if dumps and dia in dumps:
            dump, _ = bs.carregar_log(dumps[dia])
            dump = bs.marcar_sinais(bs.indicadores(dump))
            comparacoes[dia] = {}
            for nome, tipos in CANDIDATOS_OHLC.items():
                b_c = barras_15s_do_tape(trades, dia, tipos)
                s_c = indicadores_e_sinais_do_tape(b_c) if not b_c.empty else b_c
                comparacoes[dia][nome] = comparar_com_dump(s_c, dump)
        ops = replay_pregao(sinais, trades, dia)
        todas_ops.extend(ops)
        n_ex = sum(1 for o in ops if o["executou"])
        log.info(
            "bollinger_replay.pregao",
            i=i,
            n=len(pastas),
            dia=dia,
            barras=len(barras),
            sinais=len(ops),
            operacoes=n_ex,
        )
    ops_df = pd.DataFrame(todas_ops)
    saida.mkdir(parents=True, exist_ok=True)
    ops_df.to_parquet(saida / "operacoes.parquet", index=False)
    pd.concat(barras_por_dia, ignore_index=True).to_parquet(
        saida / "barras_15s_tape.parquet", index=False
    )
    r = resumo(ops_df, len(barras_por_dia))
    r["comparacoes_com_dump"] = comparacoes
    return {"resumo": r, "operacoes": ops_df}
