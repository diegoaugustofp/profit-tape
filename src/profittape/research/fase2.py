"""
Fase 2 do DeepScalper — `fase2-preparar` (docs/RESEARCH_PLANO.md, "FICHA
FORWARD: Fase 2", 2026-09-08). Roda SO' em dado queimado. Preenche os tres
[MEDIR] da ficha (p*, nula, TAXA), escolhe k, treina UMA configuracao e
congela o modelo com hashes. Nao decide nada sobre a hipotese: os
numeros de validacao aqui sao DEPURACAO, nao evidencia.

CONVENCOES
- Features: z_{col} das Tier 1 recalculadas POR DIA (simulador.preparar),
  mesma convencao do EA. Aquecimento (NaN) sai.
- Label: Triple-Barrier POR DIA (nao atravessa o pregao), h barras,
  barreiras em close*exp(+-k*sigma), sigma = desvio rolante dos retornos
  de barra do proprio dia com shift(1). Valido so' se i + h cabe no dia
  ("h cabe antes da ultima barra", ficha).
- Empate intrabarra (high e low da mesma barra cruzam as duas): resolvido
  pelo TAPE se `curated` for dado -- primeiro negocio de agressao da barra
  que cruza uma barreira decide. Sem tape, fica ambiguo e conta como 0.
- Escolha de k (regra FIXA, escrita antes de olhar): o MAIOR k da grade
  tal que >= 60% das barras validas resolvem por barreira (vertical <
  40%) E a barreira mediana em pontos >= 2 * custo. Maior k = barreira
  economicamente relevante; o piso de resolucao mantem a nula perto de
  0,5. Se nenhum k passa, o menor da grade e' usado e isso e' REGISTRADO.
- Modelo: HistGradientBoostingClassifier, 3 classes (-1, 0, +1),
  hiperparametros fixos (HP), sem busca, sem early stopping.
- Split temporal por DIA: primeiros 80% treinam, ultimos 20% medem p*,
  nula e TAXA. Depois retreina no total e congela (.pkl + sha256).
- p* = percentil 90 da confianca (max(P(+1), P(-1))) na validacao.
- TAXA = eventos NAO sobrepostos por pregao na validacao: evento em t
  bloqueia ate' t + h.
"""

from __future__ import annotations

import hashlib
import json
import pickle
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog

from ..features.pipeline import _carregar_dia
from .simulador import preparar

log = structlog.get_logger(__name__)

HP: dict[str, Any] = {"max_depth": 4, "max_iter": 200, "learning_rate": 0.05,
                      "min_samples_leaf": 50, "l2_regularization": 1.0,
                      "early_stopping": False, "random_state": 0}
GRADE_K = (0.25, 0.5, 0.75, 1.0, 1.5)
PISO_RESOLUCAO = 0.60
FRACAO_TREINO = 0.80
PERCENTIL_PSTAR = 0.90
RHO_REDUNDANTE = 0.90
_AGRESSAO = (2, 3)
_CLASSES = (-1, 0, 1)


@dataclass(frozen=True)
class Alvo:
    h: int
    k: float
    custo_pontos: float


# ------------------------------------------------------------------ features
def colunas_tier1(barras: pd.DataFrame) -> list[str]:
    base = ["imbalance", "tick_imbalance", "absorcao", "rlp_frac"]
    agf = sorted(c for c in barras.columns if c.startswith("agf_"))
    extra = ["fluxo_nacional"] if "fluxo_nacional" in barras.columns else []
    return [c for c in base if c in barras.columns] + agf + extra


def triagem_redundancia(df: pd.DataFrame, colunas_z: list[str],
                        rho_max: float = RHO_REDUNDANTE) -> dict[str, Any]:
    """Par com |rho| > rho_max: fica a PRIMEIRA na ordem dada, a outra sai.
    Ordem = a de colunas_tier1 (base antes de agf), deliberada e fixa."""
    corr = df[colunas_z].corr()
    mat = corr.to_numpy(dtype=float)
    pos = {c: i for i, c in enumerate(colunas_z)}
    mantidas: list[str] = []
    removidas: list[tuple[str, str, float]] = []
    for c in colunas_z:
        par = next(((m, float(mat[pos[c], pos[m]])) for m in mantidas
                    if abs(mat[pos[c], pos[m]]) > rho_max), None)
        if par is None:
            mantidas.append(c)
        else:
            removidas.append((c, par[0], par[1]))
    return {"corr": corr, "mantidas": mantidas, "removidas": removidas}


# -------------------------------------------------------------------- labels
def rotular_por_dia(b: pd.DataFrame, alvo: Alvo, janela_vol: int = 50,
                    trades_por_dia: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    """Colunas novas: label, label_valida, label_ambigua, sup, inf, t_evento
    (indice GLOBAL da barra que resolveu), ret_h (log), pnl_proxy_pts.

    pnl_proxy_pts = entrar no close de t no lado da barreira PREVISTA
    (preenchido depois, por evento); aqui gravamos so' a distancia da
    barreira em pontos (`barreira_pts`) e o retorno vertical em pontos."""
    out = b.copy()
    n = len(out)
    label = np.zeros(n, dtype=np.int8)
    valida = np.zeros(n, dtype=bool)
    ambigua = np.zeros(n, dtype=bool)
    desempatada = np.zeros(n, dtype=bool)
    sup = np.full(n, np.nan)
    inf = np.full(n, np.nan)
    t_ev = np.full(n, -1, dtype=np.int64)
    ret_h = np.full(n, np.nan)
    close = out["close"].to_numpy(dtype=float)
    high = out["high"].to_numpy(dtype=float)
    low = out["low"].to_numpy(dtype=float)
    for dia, idx in out.groupby("dia", sort=True).indices.items():
        idx = np.asarray(idx)
        c = close[idx]
        sig = (pd.Series(np.log(c)).diff().rolling(janela_vol, min_periods=max(2, janela_vol // 2))
               .std().shift(1).to_numpy())
        m = len(idx)
        tr = trades_por_dia.get(str(dia)) if trades_por_dia else None
        for ii in range(m):
            if not np.isfinite(sig[ii]) or sig[ii] <= 0 or ii + alvo.h > m - 1:
                continue
            g = idx[ii]
            valida[g] = True
            sup[g] = c[ii] * np.exp(alvo.k * sig[ii])
            inf[g] = c[ii] * np.exp(-alvo.k * sig[ii])
            for jj in range(ii + 1, ii + alvo.h + 1):
                gj = idx[jj]
                ts, ti = high[gj] >= sup[g], low[gj] <= inf[g]
                if ts and ti:
                    lado = _desempate_pelo_tape(tr, out.iloc[gj], sup[g], inf[g])
                    if lado == 0:
                        label[g], ambigua[g] = 0, True
                    else:
                        label[g], desempatada[g] = lado, True
                elif ts:
                    label[g] = 1
                elif ti:
                    label[g] = -1
                else:
                    continue
                t_ev[g] = gj
                ret_h[g] = np.log(close[gj] / c[ii])
                break
            else:
                gj = idx[ii + alvo.h]
                label[g] = 0
                t_ev[g] = gj
                ret_h[g] = np.log(close[gj] / c[ii])
    out["label"] = label
    out["label_valida"] = valida
    out["label_ambigua"] = ambigua
    out["label_desempatada_tape"] = desempatada
    out["sup"] = sup
    out["inf"] = inf
    out["t_evento"] = t_ev
    out["ret_h"] = ret_h
    out["barreira_pts"] = (sup - close)
    out["ret_h_pts"] = np.where(t_ev >= 0, close[np.maximum(t_ev, 0)] - close, np.nan)
    return out


def _desempate_pelo_tape(tr: pd.DataFrame | None, barra: pd.Series,
                         sup: float, inf: float) -> int:
    """Primeiro negocio de agressao da barra que cruza uma barreira decide.
    Sem tape, 0 (ambiguo)."""
    if tr is None:
        return 0
    t = tr[(tr["ts_ns"] >= int(barra["ts_open"])) & (tr["ts_ns"] <= int(barra["ts_close"]))]
    t = t[t["trade_type"].isin(_AGRESSAO)].sort_values("ts_ns", kind="stable")
    p = t["price"].to_numpy(dtype=float)
    hit = np.flatnonzero((p >= sup) | (p <= inf))
    if len(hit) == 0:
        return 0
    return 1 if p[hit[0]] >= sup else -1


def carregar_trades_dos_dias(curated: Path, symbol: str,
                             dias: list[str]) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for d in dias:
        pasta = curated / "trade" / f"dt={d}" / f"sym={symbol}"
        if pasta.exists():
            out[d] = _carregar_dia(pasta, symbol)[["ts_ns", "price", "trade_type"]]
    return out


def _resumo_k(k: float, v: pd.DataFrame) -> dict[str, float]:
    if not len(v):
        nan = float("nan")
        return {"k": k, "n_validas": 0, "frac_resolvidas": nan, "frac_ambiguas": nan,
                "frac_desempatadas_tape": nan, "barreira_pts_mediana": nan}
    return {"k": k, "n_validas": len(v),
            "frac_resolvidas": float((v["label"] != 0).mean()),
            "frac_ambiguas": float(v["label_ambigua"].mean()),
            "frac_desempatadas_tape": float(v["label_desempatada_tape"].mean()),
            "barreira_pts_mediana": float(v["barreira_pts"].median())}


def escolher_k(b: pd.DataFrame, h: int, custo: float, grade: tuple[float, ...] = GRADE_K,
               trades_por_dia: dict[str, pd.DataFrame] | None = None) -> dict[str, Any]:
    linhas = []
    for k in grade:
        r = rotular_por_dia(b, Alvo(h, k, custo), trades_por_dia=trades_por_dia)
        linhas.append(_resumo_k(k, r[r["label_valida"]]))
    tab = pd.DataFrame(linhas)
    ok = tab[(tab["frac_resolvidas"] >= PISO_RESOLUCAO)
             & (tab["barreira_pts_mediana"] >= 2 * custo)]
    if len(ok):
        k = float(ok["k"].max())
        motivo = "maior k com >= 60% resolvidas e barreira >= 2x custo"
    else:
        k = float(min(grade))
        motivo = "NENHUM k passou na regra; usado o menor da grade -- REGISTRAR"
    return {"tabela": tab, "k": k, "motivo": motivo}


# ------------------------------------------------------------------- modelo
def _treinar(X: pd.DataFrame, y: pd.Series) -> Any:
    from sklearn.ensemble import HistGradientBoostingClassifier
    m = HistGradientBoostingClassifier(**HP)
    m.fit(X.to_numpy(dtype=float), y.to_numpy())
    return m


def confianca_e_lado(modelo: Any, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    proba = modelo.predict_proba(X.to_numpy(dtype=float))
    classes = list(modelo.classes_)
    p_up = proba[:, classes.index(1)] if 1 in classes else np.zeros(len(X))
    p_dn = proba[:, classes.index(-1)] if -1 in classes else np.zeros(len(X))
    conf = np.maximum(p_up, p_dn)
    lado = np.where(p_up >= p_dn, 1, -1)
    return conf, lado


def eventos_nao_sobrepostos(df: pd.DataFrame, conf: np.ndarray, lado: np.ndarray,
                            p_star: float, h: int, custo: float) -> pd.DataFrame:
    """df ja' filtrado (validas, sem NaN), na ordem original, com colunas
    dia, bar_id, label, barreira_pts, ret_h_pts. Evento em t bloqueia
    ate' t + h (por posicao dentro do dia)."""
    d = df.reset_index(drop=True)
    d["conf"] = conf
    d["lado_previsto"] = lado
    ev = []
    for dia, g in d.groupby("dia", sort=True):
        bloqueado_ate = -1
        for _, row in g.iterrows():
            pos = int(row["bar_id"])
            if pos <= bloqueado_ate or row["conf"] < p_star:
                continue
            bloqueado_ate = pos + h
            acerto = int(row["label"] == row["lado_previsto"])
            if row["label"] == row["lado_previsto"]:
                pnl = float(row["barreira_pts"]) - custo
            elif row["label"] == -row["lado_previsto"]:
                pnl = -float(row["barreira_pts"]) - custo
            else:
                pnl = float(row["ret_h_pts"]) * int(row["lado_previsto"]) - custo
            ev.append({"dia": str(dia), "bar_id": pos, "lado_previsto": int(row["lado_previsto"]),
                       "conf": float(row["conf"]), "label": int(row["label"]),
                       "acerto": acerto, "pnl_liquido_proxy": pnl})
    return pd.DataFrame(ev, columns=["dia", "bar_id", "lado_previsto", "conf", "label",
                                     "acerto", "pnl_liquido_proxy"])


# ------------------------------------------------------------------ pipeline
def preparar_fase2(features: Path, saida: Path, symbol: str, h: int = 3,
                   custo: float = 11.0, janela_z: int = 50,
                   curated: Path | None = None) -> dict[str, Any]:
    barras = pd.read_parquet(features)
    tier1 = colunas_tier1(barras)
    b = preparar(barras, z_por_dia=tier1, janela_z=janela_z)
    dias = sorted(b["dia"].unique())
    trades = carregar_trades_dos_dias(curated, symbol, dias) if curated else None

    tri = triagem_redundancia(b.dropna(subset=[f"z_{c}" for c in tier1]),
                              [f"z_{c}" for c in tier1])
    feats = tri["mantidas"]

    esc = escolher_k(b, h, custo, trades_por_dia=trades)
    alvo = Alvo(h, esc["k"], custo)
    r = rotular_por_dia(b, alvo, trades_por_dia=trades)
    d = r[r["label_valida"]].dropna(subset=feats)

    n_tr = int(len(dias) * FRACAO_TREINO)
    dias_tr, dias_va = dias[:n_tr], dias[n_tr:]
    tr, va = d[d["dia"].isin(dias_tr)], d[d["dia"].isin(dias_va)]
    if len(tr) < 200 or len(va) < 50:
        raise SystemExit(f"amostra insuficiente: treino={len(tr)} validacao={len(va)}")
    modelo_va = _treinar(tr[feats], tr["label"])
    conf, lado = confianca_e_lado(modelo_va, va[feats])
    p_star = float(np.quantile(conf, PERCENTIL_PSTAR))
    ev = eventos_nao_sobrepostos(va, conf, lado, p_star, h, custo)
    resolvidas = float((va["label"] != 0).mean())
    nula = resolvidas / 2
    taxa = float(len(ev) / max(1, len(dias_va)))

    modelo = _treinar(d[feats], d["label"])
    saida.mkdir(parents=True, exist_ok=True)
    pkl = saida / "modelo_fase2.pkl"
    with open(pkl, "wb") as f:
        pickle.dump({"modelo": modelo, "features": feats, "alvo": asdict(alvo),
                     "janela_z": janela_z, "p_star": p_star, "HP": HP}, f)
    hash_modelo = hashlib.sha256(pkl.read_bytes()).hexdigest()

    ficha = {
        "symbol": symbol, "h": h, "k": alvo.k, "k_motivo": esc["motivo"],
        "custo_pontos": custo, "janela_z": janela_z,
        "features": feats, "features_removidas_redundancia": tri["removidas"],
        "HP": HP,
        "dias_treino": [dias_tr[0], dias_tr[-1]], "dias_validacao": [dias_va[0], dias_va[-1]],
        "n_treino": len(tr), "n_validacao": len(va),
        "MEDIDO_p_star": p_star, "MEDIDO_nula": nula,
        "MEDIDO_frac_resolvidas": resolvidas,
        "MEDIDO_taxa_eventos_por_pregao": taxa,
        "DEPURACAO_acerto_validacao": float(ev["acerto"].mean()) if len(ev) else None,
        "DEPURACAO_pnl_proxy_por_op": float(ev["pnl_liquido_proxy"].mean()) if len(ev) else None,
        "DEPURACAO_n_eventos_validacao": len(ev),
        "horizonte_pregoes_para_150": (150 / taxa) if taxa > 0 else None,
        "modelo_sha256": hash_modelo, "modelo_arquivo": str(pkl),
        "desempate_pelo_tape": trades is not None,
        "classes_treino": {str(k): int(v) for k, v in d["label"].value_counts().items()},
    }
    ficha["ficha_sha256"] = hashlib.sha256(
        json.dumps(ficha, sort_keys=True, default=str).encode()).hexdigest()
    with open(saida / "ficha_fase2.json", "w", encoding="utf-8") as f:
        json.dump(ficha, f, ensure_ascii=False, indent=2, default=str)
    tri["corr"].to_csv(saida / "correlacao_tier1.csv")
    esc["tabela"].to_csv(saida / "escolha_k.csv", index=False)
    ev.to_csv(saida / "eventos_validacao.csv", index=False)
    return {"ficha": ficha, "escolha_k": esc["tabela"], "triagem": tri, "eventos": ev}
