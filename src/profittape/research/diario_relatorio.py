"""
Relatorio do DIARIO de sinais (2026-09-16).

CONTRATO, no topo porque e' o que importa
-----------------------------------------
Este relatorio e' para DIMENSIONAR e para DIAGNOSTICAR EXECUCAO. Nao e'
para escolher regra. Um relatorio de backtest e' uma maquina de gerar
decisoes pos-hoc ("perde as sextas", "o drawdown vem de 2020") e cada
filtro desses e' um trial nao declarado. Vale para decidir CAPITAL e
TAMANHO, e para ver se a execucao esta' sa'. Nao vale para criar
clausula -- clausula nasce em ficha, antes.

O que ele responde, e que so' o diario sabe responder:
  - quanto as REGRAS custaram: sinais descartados por vaga (modo
    exclusivo), pelo gate, por posicao aberta, por pendente;
  - o que os descartados TERIAM dado -- reportado, nunca usado para
    decidir (o `resultado_hipotetico` so' existe se o diario tiver sido
    gravado com ele; hoje nao e', de proposito);
  - execucao: slippage por perna, latencias, avisos CONFIRA;
  - infra: quantos sinais com feed nao confiavel, reconciliacoes.

Curva e drawdown sao em PONTOS e por operacao EXECUTADA, na ordem do
tempo. Sem anualizar, sem Sharpe: com n de forward pequeno, essas
metricas dao uma precisao que o dado nao tem.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

log = structlog.get_logger(__name__)

DESCARTES = ("rejeitado_gate", "gate_indefinido", "sem_vaga", "posicao_aberta", "pendente")


def carregar(diretorio: Path, ea: str | None = None) -> pd.DataFrame:
    padrao = f"diario_{ea}_*.jsonl" if ea else "diario_*.jsonl"
    arquivos = sorted(diretorio.glob(padrao))
    if not arquivos:
        raise SystemExit(f"nenhum {padrao} em {diretorio}")
    linhas = []
    for a in arquivos:
        for ln in a.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                linhas.append(json.loads(ln))
    df = pd.json_normalize(linhas)
    df["arquivos"] = len(arquivos)
    return df


def _curva(exec_: pd.DataFrame) -> dict[str, Any]:
    """Curva e drawdown em PONTOS, por operacao executada, na ordem do
    tempo. P&L liquido = bruto - custo declarado na ficha."""
    if exec_.empty or "pnl_pts" not in exec_:
        return {}
    s = exec_.sort_values("gravado_em")["pnl_pts"].astype(float).fillna(0.0)
    acum = s.cumsum()
    pico = acum.cummax()
    dd = acum - pico
    i_min = int(dd.to_numpy().argmin()) if len(dd) else 0
    return {"operacoes": len(s), "pnl_total_pts": round(float(acum.iloc[-1]), 1),
            "pnl_medio_pts": round(float(s.mean()), 1),
            "vencedoras": int((s > 0).sum()), "perdedoras": int((s < 0).sum()),
            "maior_ganho": round(float(s.max()), 1), "maior_perda": round(float(s.min()), 1),
            "drawdown_max_pts": round(float(dd.min()), 1),
            "drawdown_max_em_operacao": i_min + 1,
            "curva_pts": [round(float(v), 1) for v in acum.tolist()]}


def _execucao(exec_: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for perna in ("entrada", "stop", "alvo", "zeragem"):
        col = f"ordens.{perna}.slippage_pts"
        if col in exec_:
            s = exec_[col].dropna().astype(float)
            if len(s):
                out[perna] = {"n": len(s), "slippage_medio_pts": round(float(s.mean()), 2),
                              "p50": round(float(s.median()), 2),
                              "p90": round(float(s.quantile(0.9)), 2)}
        lat = f"ordens.{perna}.latencia_fill_ms"
        if lat in exec_:
            s = exec_[lat].dropna().astype(float)
            if len(s):
                out.setdefault(perna, {})["latencia_fill_ms_p50"] = round(float(s.median()), 1)
    avisos = exec_["avisos"].apply(len).sum() if "avisos" in exec_ else 0
    out["avisos_confira"] = int(avisos)
    return out


def relatorio(diretorio: Path, ea: str | None = None) -> dict[str, Any]:
    df = carregar(diretorio, ea)
    por_desfecho = df["desfecho"].value_counts().to_dict()
    exec_ = df[df["desfecho"] == "executou"]
    descartados = df[df["desfecho"].isin(DESCARTES)]
    n_sinais = len(df)
    infra_cols = [c for c in df.columns if c.startswith("infra.")]
    infra = {}
    if "candidato.volume_confiavel_t" in df:
        infra["sinais_com_barra_nao_confiavel"] = int(
            (~df["candidato.volume_confiavel_t"].fillna(True).astype(bool)).sum())
    if "infra.reconciliacoes_ate_aqui" in df:
        infra["reconciliacoes_max"] = int(df["infra.reconciliacoes_ate_aqui"].fillna(0).max())
    if "infra.dia_completo" in df:
        infra["sinais_em_dia_incompleto"] = int(
            (~df["infra.dia_completo"].fillna(True).astype(bool)).sum())
    # CUSTO DO GATE SOBRE TODOS OS SINAIS (2026-09-21): os que ele reprovou
    # de fato + os bloqueados por posicao/pendencia que ele REPROVARIA (o
    # ciclo agora registra `motivo.gate_passaria` nesses). Sem isto, a fracao
    # rejeitada pelo gate sai subestimada sempre que ha' posicao aberta.
    gate_total: dict[str, Any] = {}
    if "motivo.gate_passaria" in df:
        bloqueados = df[df["desfecho"].isin(("posicao_aberta", "pendente"))]
        julgados = bloqueados["motivo.gate_passaria"].dropna()
        reprovaria = int((~julgados.astype(bool)).sum())
        reprovou = int(por_desfecho.get("rejeitado_gate", 0))
        indef = int(por_desfecho.get("gate_indefinido", 0))
        base = len(df) - len(bloqueados) + len(julgados)
        gate_total = {
            "reprovados_de_fato": reprovou, "indefinidos": indef,
            "bloqueados_que_o_gate_reprovaria": reprovaria,
            "bloqueados_sem_julgamento": int(len(bloqueados) - len(julgados)),
            "fracao_que_o_gate_barra": (round((reprovou + indef + reprovaria) / base, 3)
                                        if base else None),
        }
    return {
        "arquivos": int(df["arquivos"].iloc[0]) if "arquivos" in df else 0,
        "sinais": n_sinais,
        "por_desfecho": dict(sorted(por_desfecho.items())),
        "custo_das_regras": {
            "descartados": len(descartados),
            "fracao_dos_sinais": (round(len(descartados) / n_sinais, 3) if n_sinais else None),
            "por_regra": {d: int(por_desfecho.get(d, 0)) for d in DESCARTES},
            "gate_sobre_todos_os_sinais": gate_total,
        },
        "curva_e_drawdown_pts": _curva(exec_),
        "execucao": _execucao(exec_),
        "infra": infra,
        "campos_de_infra_disponiveis": sorted(infra_cols),
    }
