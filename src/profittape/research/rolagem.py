"""
ROLAGEM DO WIN — descricao (passo 1 de "anomalia medida", 2026-09-16).

CONTRAPARTE (o campo que agora vem antes da hipotese): a cada vencimento,
quem esta' posicionado no contrato vigente e' OBRIGADO a rolar ou a
fechar. Nao escolhe o dia nem o preco -- escolhe entre rolar e sair. Isso
e' fluxo que nao olha preco justo, concentrado em datas MECANICAS. E' a
melhor candidata a contraparte no WIN, e a serie continua AJUSTADA do
Profit esconde a rolagem: quem so' olha o grafico continuo nao ve.

ESTE MODULO NAO E' UMA FICHA. E' a descricao que decide se vale escrever
uma: a contraparte deixa MARCA? Categoria `features`, zero trial.

O QUE MEDE -- e o que NAO mede
------------------------------
Mede MAGNITUDE e ESTRUTURA: volume do dia, amplitude do dia, |retorno|
do dia, e a distribuicao do volume por horario. **Nao mede retorno com
SINAL.** Olhar direcao aqui seria comecar o p1 pela porta dos fundos;
direcao so' em ficha, com CONTRAPARTE escrita e criterio declarado.

CALENDARIO (declarado): o futuro de Ibovespa vence na QUARTA-FEIRA mais
proxima do dia 15 dos meses PARES. Se a data calculada nao for pregao no
dump (feriado), usa-se o proximo pregao disponivel -- regra declarada,
nao ajustada depois. `d` = distancia em PREGOES ate' o vencimento (d=0 e'
o dia do vencimento, d=-1 o pregao anterior).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from .eas_preco import TICK_WIN, carregar_log, indicadores

log = structlog.get_logger(__name__)

MESES_DE_VENCIMENTO = (2, 4, 6, 8, 10, 12)
JANELA_ROLAGEM = 5          # d de -5 a 0 e' "perto do vencimento"


def quarta_mais_proxima_do_15(ano: int, mes: int) -> dt.date:
    """Quarta-feira mais proxima do dia 15 (empate nao existe: a distancia
    a uma quarta e' unica dentro de +-3 dias)."""
    d15 = dt.date(ano, mes, 15)
    desloc = (2 - d15.weekday()) % 7          # proxima quarta (0=segunda)
    proxima = d15 + dt.timedelta(days=desloc)
    anterior = proxima - dt.timedelta(days=7)
    return proxima if (proxima - d15).days <= (d15 - anterior).days else anterior


def datas_de_vencimento(de: dt.date, ate: dt.date) -> list[dt.date]:
    out = []
    for ano in range(de.year, ate.year + 1):
        for mes in MESES_DE_VENCIMENTO:
            v = quarta_mais_proxima_do_15(ano, mes)
            if de <= v <= ate:
                out.append(v)
    return sorted(out)


def marcar_distancia(dias_pregao: list[dt.date], vencimentos: list[dt.date]) -> pd.DataFrame:
    """`d` em PREGOES ate' o vencimento mais proximo a` frente (<= 0 depois
    dele). Feriado no vencimento: usa o proximo pregao (regra declarada)."""
    idx = {d: i for i, d in enumerate(dias_pregao)}
    linhas = []
    for v in vencimentos:
        if v in idx:
            i_v = idx[v]
        else:
            posteriores = [d for d in dias_pregao if d > v]
            if not posteriores:
                continue
            i_v = idx[posteriores[0]]
        for i, d in enumerate(dias_pregao):
            dist = i - i_v
            if abs(dist) <= 10:
                linhas.append({"dia": d, "d": dist, "vencimento": dias_pregao[i_v]})
    df = pd.DataFrame(linhas)
    if df.empty:
        return df
    # um dia pode estar perto de dois vencimentos: fica com o mais proximo
    df["abs_d"] = df["d"].abs()
    return (df.sort_values(["dia", "abs_d"]).drop_duplicates("dia")
              .drop(columns="abs_d").reset_index(drop=True))


def descrever(dump: Path, saida: Path | None = None) -> dict[str, Any]:
    df, meta = carregar_log(dump)
    d = indicadores(df)
    dias = sorted(d["dia"].unique())
    venc = datas_de_vencimento(dias[0], dias[-1])
    marca = marcar_distancia(list(dias), venc)

    por_dia = d.groupby("dia").agg(
        vol=("vol_total", "sum"), high=("high", "max"), low=("low", "min"),
        open=("open", "first"), close=("close", "last"), barras=("close", "size")).reset_index()
    por_dia["amplitude_pts"] = por_dia["high"] - por_dia["low"]
    # MAGNITUDE, nao direcao (o sinal do retorno fica fora de proposito)
    por_dia["retorno_abs_pts"] = (por_dia["close"] - por_dia["open"]).abs()
    por_dia["amplitude_ticks"] = por_dia["amplitude_pts"] / TICK_WIN
    por_dia = por_dia.merge(marca, on="dia", how="left")
    por_dia["perto"] = por_dia["d"].between(-JANELA_ROLAGEM, 0)

    def resumo(sub: pd.DataFrame) -> dict[str, Any]:
        if sub.empty:
            return {}
        return {"pregoes": len(sub),
                "vol_p50": round(float(sub["vol"].median()), 1),
                "amplitude_p50_pts": round(float(sub["amplitude_pts"].median()), 1),
                "retorno_abs_p50_pts": round(float(sub["retorno_abs_pts"].median()), 1)}

    normais = por_dia[(~por_dia["perto"].fillna(False)) & (por_dia["d"].isna()
                                                           | (por_dia["d"].abs() > JANELA_ROLAGEM))]
    perto = por_dia[por_dia["perto"].fillna(False)]
    base = resumo(normais)
    por_d = {}
    for k in range(-JANELA_ROLAGEM, 3):
        sub = por_dia[por_dia["d"] == k]
        r = resumo(sub)
        if r and base:
            for campo, chave in (("vol_p50", "vol_vs_normal"),
                                 ("amplitude_p50_pts", "amplitude_vs_normal"),
                                 ("retorno_abs_p50_pts", "retorno_abs_vs_normal")):
                ref = base[campo]
                r[chave] = round(r[campo] / ref, 3) if ref else None
        por_d[str(k)] = r

    # estrutura: fracao do volume do dia por faixa de horario
    d2 = d.merge(por_dia[["dia", "d", "perto"]], on="dia", how="left")
    d2["faixa"] = pd.cut(d2["hhmm"], [0, 1000, 1200, 1500, 1700, 2400],
                         labels=["ate_10h", "10_12h", "12_15h", "15_17h", "apos_17h"])
    tot = d2.groupby("dia")["vol_total"].transform("sum")
    d2["frac"] = d2["vol_total"] / tot.replace(0, pd.NA)
    soma = (d2.groupby(["perto", "faixa"], observed=True)["frac"].sum()
            .reset_index(name="soma"))
    n_dias = d2.groupby("perto", observed=True)["dia"].nunique().to_dict()
    perfil_out: dict[str, dict[str, float]] = {"True": {}, "False": {}}
    for linha in soma.itertuples(index=False):
        n = int(n_dias.get(linha.perto, 0))
        if n:
            v_soma = float(str(linha.soma))
            perfil_out[str(bool(linha.perto))][str(linha.faixa)] = round(v_soma / n, 4)

    r = {"dump": meta, "vencimentos": [v.isoformat() for v in venc],
         "pregoes_marcados": int(marca["dia"].nunique()) if not marca.empty else 0,
         "normais": base, "perto_do_vencimento": resumo(perto), "por_d": por_d,
         "perfil_horario_fracao_do_volume": {"perto": perfil_out.get("True", {}),
                                             "normais": perfil_out.get("False", {})}}
    if saida is not None:
        saida.mkdir(parents=True, exist_ok=True)
        (saida / "rolagem.json").write_text(json.dumps(r, indent=2, default=str),
                                            encoding="utf-8")
    log.info("rolagem.descrito", vencimentos=len(venc), pregoes=len(dias),
             vol_d_menos_1=por_d.get("-1", {}).get("vol_vs_normal"))
    return r
