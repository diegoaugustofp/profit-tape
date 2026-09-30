"""
Conferencia do replay `ea-vwapvp-replay` contra o dump do
`ntsl/vwapvp_conferir.ntsl` (ConsoleLog do Profit, grafico M5 do WINFUT).

Mesma tecnica do `tools/ntsl_equivalencia.py` (absorcao_dir, 2,4e-08):
o Python RECALCULA as series a partir das suas proprias barras (o cache do
replay, `data/cache/vwapvp_barras`) e MEDE a diferenca por coluna. Copiar
o logado so' confiaria; recalcular mede se concordam.

Tres perguntas, tres blocos de saida:

1. EXATO? imbalance, desloc_norm, absorcao_comp/vend, z_comp/z_vend e o
   estimador: mesma formula dos dois lados -> diferenca esperada ~1e-8.
   Se nao for, e' formula, janela ou divisor, e o comparador diz qual
   coluna.
2. AGRESSAO: AgressionVolBuy/Sell (Profit) x vol_agr_compra/venda (tape,
   tipos 2/3). Nunca foi batido. Se o Profit incluir RLP, a diferenca e'
   ~26% do volume; se excluir, ~0. E' o numero que decide se a absorcao
   medida no replay e' a mesma que o operador ve no grafico.
3. VWAP: o NTSL so' pode fazer VWAP POR BARRA ((H+L+C)/3 x QuantityVol).
   O Python faz a MESMA aproximacao das suas barras (equivalencia exata
   esperada) e reporta a parte |vwap_negocio - vwap_barra|, em pontos,
   por hora do dia: e' quanto a aproximacao vale, medido.

Ordem dos campos CONGELADA com o `.ntsl`: muda nos dois lados junto
(skill de engenharia, 3.2).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..research.vwapvp_replay import ParametrosReplay, ZRolante, _barras_do_dia
from .ntsl_equivalencia import _data_easylanguage, _numero_ptbr

PREFIXO = "VWAPVP|"
CAMPOS = [
    "data", "hora", "hora_bolsa", "open", "high", "low", "close",
    "vol_total", "vol_so_agr", "agr_compra", "agr_venda",
    "vwap_bar", "sd_bar", "z_bar",
    "imbalance", "desloc_norm", "absorcao_comp", "absorcao_vend",
    "z_comp", "z_vend", "estimador",
]
# colunas com a MESMA formula dos dois lados (espera-se ~1e-8)
EXATAS = ["open", "high", "low", "close", "vol_total",
          "imbalance", "desloc_norm", "absorcao_comp", "absorcao_vend",
          "z_comp", "z_vend", "estimador", "vwap_bar", "sd_bar", "z_bar"]
# colunas MEDIDAS (nao se espera zero; o numero e' a resposta)
MEDIDAS = ["vol_so_agr", "agr_compra", "agr_venda"]


# ------------------------------------------------------------------ dump
def carregar_dump(caminho: Path) -> tuple[pd.DataFrame, dict[str, int]]:
    if not caminho.exists():
        raise SystemExit(f"nao achei {caminho} (no PowerShell, caminho entre aspas)")
    ok: list[list[str]] = []
    n_total = n_mal = 0
    larguras: set[int] = set()
    for bruta in caminho.read_text(encoding="utf-8", errors="replace").splitlines():
        pos = bruta.find(PREFIXO)
        if pos < 0:
            continue
        n_total += 1
        campos = bruta[pos + len(PREFIXO):].strip().split("|")
        if len(campos) != len(CAMPOS):
            n_mal += 1
            larguras.add(len(campos))
            continue
        ok.append(campos)
    if not ok:
        if n_mal:
            raise SystemExit(f"dump com {sorted(larguras)} campos depois de '{PREFIXO}', "
                             f"esperava {len(CAMPOS)}: o .ntsl do grafico e' de outra versao")
        raise SystemExit(f"nenhuma linha '{PREFIXO}' em {caminho}: LogAtivo=1 e console "
                         "exportado inteiro?")
    df = pd.DataFrame(ok, columns=CAMPOS)
    for c in CAMPOS[3:]:
        df[c] = _numero_ptbr(df[c])
    n_antes = len(df)
    df = df.drop_duplicates(subset=["data", "hora"], keep="last")
    zerada = bool((df["agr_compra"].fillna(0) == 0).all()
                  and (df["agr_venda"].fillna(0) == 0).all())
    if zerada:
        raise SystemExit("AgressionVolBuy/Sell zerados em todas as barras: o plano nao tem "
                         "o modulo (Pro/Ultra/Scalper). Sem isso a absorcao nao e' conferivel.")
    df["chave_data"] = [dt.date(*_data_easylanguage(int(float(x)))) for x in df["data"]]
    df["chave_hora"] = pd.to_numeric(df["hora"], errors="coerce").astype(int)
    return df, {"linhas": n_total, "malformadas": n_mal, "duplicadas": n_antes - len(df),
                "barras": len(df)}


# -------------------------------------------------------------- python
def _series_python(curated: Path, symbol: str, dias: list[dt.date], p: ParametrosReplay,
                   cache_dir: Path | None, aquecimento: int) -> pd.DataFrame:
    """Barras do cache dos dias do dump + `aquecimento` dias antes (para a
    janela do z fechar antes do primeiro dia comparado), com as mesmas
    series do .ntsl recalculadas."""
    from ..ea.perfil_preco import dias_disponiveis

    todos = dias_disponiveis(curated, symbol)
    anteriores = [d for d in todos if d < min(dias)][-aquecimento:]
    partes = []
    for d in anteriores + sorted(dias):
        r = _barras_do_dia(curated, symbol, d, p, cache_dir)
        if r is not None:
            partes.append(r.barras)
    if not partes:
        raise SystemExit("nenhum dia do dump existe no curated")
    b = (pd.concat(partes, ignore_index=True).sort_values(["dia", "ts_close_ns"])
         .reset_index(drop=True))

    # z com divisor (J-1), barra atual fora, continuo entre dias (= .ntsl)
    for col, nome in (("absorcao_comp", "z_comp"), ("absorcao_vend", "z_vend")):
        zr = ZRolante(p.janela_z)
        out: list[float] = []
        for a in b[col]:
            if a is None or pd.isna(a):
                out.append(0.0)               # o .ntsl loga 0 quando nao ha' z
                continue
            zz = zr.z(float(a))
            out.append(0.0 if zz is None else zz)
            zr.empurrar(float(a))
        b[nome] = out
    # VWAP por barra: (H+L+C)/3 x vol_total acumulado no dia, desvio populacional
    tip = (b["high"] + b["low"] + b["close"]) / 3
    g = b.groupby("dia", sort=False)
    pv = (tip * b["vol_total"]).groupby(b["dia"]).cumsum()
    v = g["vol_total"].cumsum()
    ppv = (tip * tip * b["vol_total"]).groupby(b["dia"]).cumsum()
    b["vwap_bar"] = np.where(v > 0, pv / v.replace(0, np.nan), 0.0)
    var = ppv / v.replace(0, np.nan) - b["vwap_bar"] ** 2
    b["sd_bar"] = np.where(var > 0, np.sqrt(var.clip(lower=0)), 0.0)
    b["z_bar"] = np.where(b["sd_bar"] > 0,
                          (b["close"] - b["vwap_bar"]) / b["sd_bar"].replace(0, np.nan), 0.0)
    b["estimador"] = np.where(b["z_bar"] > 0, b["z_comp"],
                              np.where(b["z_bar"] < 0, b["z_vend"], 0.0))
    va = b["vol_agr_compra"] + b["vol_agr_venda"]
    amp = b["high"] - b["low"]
    b["imbalance"] = np.where(
        va > 0, (b["vol_agr_compra"] - b["vol_agr_venda"]) / va.replace(0, np.nan), 0.0)
    b["desloc_norm"] = np.where(amp > 0, (b["close"] - b["open"]) / amp.replace(0, np.nan), 0.0)
    b["absorcao_comp"] = b["absorcao_comp"].fillna(0.0)
    b["absorcao_vend"] = b["absorcao_vend"].fillna(0.0)
    b["agr_compra"] = b["vol_agr_compra"]
    b["agr_venda"] = b["vol_agr_venda"]
    b["vol_so_agr"] = va          # QuantityVol(False, True) do Profit x tipos 2/3 do tape
    b["chave_data"] = [dt.date.fromisoformat(x) for x in b["dia"]]
    b["chave_hora"] = b["hhmm_abertura"].astype(int)
    b["vwap_negocio"] = b["vwap"]
    return b


# ------------------------------------------------------------- comparar
def comparar(log_ntsl: Path, curated: Path, symbol: str = "WINFUT",
             cache_dir: Path | None = None, aquecimento_dias: int = 2) -> dict[str, Any]:
    ntsl, meta = carregar_dump(log_ntsl)
    p = ParametrosReplay()
    dias = sorted(set(ntsl["chave_data"]))
    py = _series_python(curated, symbol, dias, p, cache_dir, aquecimento_dias)
    juntos = ntsl.merge(py, on=["chave_data", "chave_hora"], how="inner",
                        suffixes=("_ntsl", "_py"))
    if juntos.empty:
        return {"erro": "nenhuma barra casou (data, hora de abertura)",
                "dias_dump": [d.isoformat() for d in dias],
                "dias_python": sorted({d.isoformat() for d in py["chave_data"]}),
                "meta": meta}
    # dias em que o tape tem MENOS barras que o grafico (tape truncado: 31/07,
    # 15/09): as barras ausentes nao casam e o z das 50 barras seguintes
    # diverge nos dois lados por razoes conhecidas.
    n_ntsl = ntsl.groupby("chave_data").size().to_dict()
    n_py = py[py["chave_data"].isin(dias)].groupby("chave_data").size().to_dict()
    parciais = {d.isoformat(): {"grafico": int(n_ntsl.get(d, 0)), "tape": int(n_py.get(d, 0))}
                for d in dias if int(n_py.get(d, 0)) < int(n_ntsl.get(d, 0))}
    # fator de rolagem por pregao (serie continua do grafico)
    k = (juntos["close_ntsl"] / juntos["close_py"]).groupby(juntos["chave_data"]).median()
    k_por_dia = {str(d): round(float(x), 6) for d, x in k.items()}
    rolagem = any(abs(x - 1.0) > 1e-6 for x in k.values)

    def dif(col: str) -> dict[str, Any]:
        a = juntos[f"{col}_ntsl"].astype(float).to_numpy()
        b = juntos[f"{col}_py"].astype(float).to_numpy()
        d = np.abs(a - b)
        i = int(np.nanargmax(d)) if np.isfinite(d).any() else 0
        pior: dict[str, Any] | None = None
        if np.nansum(d >= 1e-6) > 0:
            pior = {"data": str(juntos["chave_data"].iloc[i]),
                    "hora": int(juntos["chave_hora"].iloc[i]),
                    "ntsl": float(a[i]), "py": float(b[i])}
        return {"n": int(np.isfinite(d).sum()), "max": float(np.nanmax(d)),
                "mediana": float(np.nanmedian(d)), "exatas_1e-6": int(np.nansum(d < 1e-6)),
                "pior": pior}

    exatas = {c: dif(c) for c in EXATAS}
    medidas = {c: dif(c) for c in MEDIDAS}
    # agressao: razao Profit/tape e comparacao com o RLP do tape (~26%)
    razao_c = (juntos["agr_compra_ntsl"] / juntos["agr_compra_py"].replace(0, np.nan))
    razao_v = (juntos["agr_venda_ntsl"] / juntos["agr_venda_py"].replace(0, np.nan))
    agressao = {"razao_compra_mediana": float(razao_c.median()),
                "razao_venda_mediana": float(razao_v.median()),
                "leitura": ("Profit ~= tape (2/3 sem RLP)" if abs(razao_c.median() - 1) < 0.03
                            else "Profit acima do tape: provavelmente INCLUI RLP (~+35% = 26%/74%)"
                            if razao_c.median() > 1.1 else "divergencia a investigar")}
    # vwap por negocio x por barra, em pontos, por hora
    gap = (juntos["vwap_negocio"] - juntos["vwap_bar_py"]).abs()
    por_hora = gap.groupby(juntos["chave_hora"] // 100).median().round(1).to_dict()
    vwap_gap = {"mediana_pts": float(gap.median()), "p95_pts": float(gap.quantile(0.95)),
                "max_pts": float(gap.max()), "por_hora_mediana": por_hora}
    return {"meta": meta, "barras_casadas": len(juntos),
            "dias": [d.isoformat() for d in dias], "k_por_dia": k_por_dia,
            "rolagem_detectada": rolagem, "dias_parciais_no_tape": parciais,
            "exatas": exatas, "medidas": medidas,
            "agressao": agressao, "vwap_negocio_x_barra": vwap_gap, "_juntos": juntos}


def formatar(r: dict[str, Any]) -> list[str]:
    if "erro" in r:
        return [f"  {r['erro']}", f"  dump: {r.get('dias_dump')}",
                f"  python: {r.get('dias_python')}"]
    m = r["meta"]
    ln = [f"  dump: {m['linhas']} linhas, {m['malformadas']} malformadas, "
          f"{m['duplicadas']} duplicadas, {m['barras']} barras; casadas com o cache: "
          f"{r['barras_casadas']} ({r['dias'][0]}..{r['dias'][-1]})"]
    if r["rolagem_detectada"]:
        ln.append(f"  ATENCAO: fator de rolagem <> 1 em algum pregao: {r['k_por_dia']} "
                  "(serie continua; precos nao comparaveis nesses dias)")
    if r["dias_parciais_no_tape"]:
        ln.append("  ATENCAO: tape com menos barras que o grafico em "
                  f"{r['dias_parciais_no_tape']}: as 50 barras seguintes tem z diferente "
                  "pelos dois lados (esperado)")
    ln.append("  1. EXATAS (mesma formula; espera-se ~1e-8):")
    ln.append("     coluna          n    exatas   mediana|dif|    max|dif|   pior barra")
    for c, d in r["exatas"].items():
        pior = d["pior"]
        s = ("" if pior is None else
             f"{pior['data']} {pior['hora']:04d} ntsl={pior['ntsl']:.4f} py={pior['py']:.4f}")
        ln.append(f"     {c:14s} {d['n']:5d} {d['exatas_1e-6']:8d}   {d['mediana']:12.6f} "
                  f"{d['max']:11.4f}   {s}")
    ln.append("  2. AGRESSAO (medida, nao suposta):")
    for c, d in r["medidas"].items():
        ln.append(f"     {c:14s} n={d['n']}  mediana|dif|={d['mediana']:.0f}  max={d['max']:.0f}")
    a = r["agressao"]
    ln.append(f"     razao Profit/tape: compra {a['razao_compra_mediana']:.3f}  "
              f"venda {a['razao_venda_mediana']:.3f}")
    ln.append(f"     -> {a['leitura']}")
    g = r["vwap_negocio_x_barra"]
    ln.append("  3. VWAP por negocio (replay) x por barra (grafico), em pontos: "
              f"mediana {g['mediana_pts']:.1f}  p95 {g['p95_pts']:.1f}  max {g['max_pts']:.1f}")
    ln.append("     por hora (mediana): "
              + ", ".join(f"{h}h:{v}" for h, v in g["por_hora_mediana"].items()))
    return ln


# --------------------------------------------------------- niveis (NTSL)
def data_easylanguage(d: dt.date) -> int:
    """Inversa de _data_easylanguage: 25/09/2026 -> 1260925."""
    return (d.year - 1900) * 10000 + d.month * 100 + d.day


def gerar_ntsl_niveis(curated: Path, symbol: str = "WINFUT", cache_dir: Path | None = None,
                      p: ParametrosReplay | None = None) -> str:
    """Gera um indicador NTSL que plota, em cada dia, VAH/VAL/POC do ultimo
    dia COMPLETO anterior (a referencia do replay, D2), como constantes por
    data. O Profit nao marca VAL/VAH; assim o operador VE onde as barras
    c_nivel do replay caem. So' plota; nao decide nada."""
    from ..research.vwapvp_replay import rodar

    p = p or ParametrosReplay()
    r = rodar(curated, symbol, None, p, cache_dir)
    if "erro" in r:
        raise SystemExit(r["erro"])
    linhas = []
    for x in r["area_de_valor_dois_algoritmos"]:
        d = dt.date.fromisoformat(x["dia"])
        linhas.append(f"  if sData = {data_easylanguage(d)} then begin sVAH := {x['vah_bin']:.0f}; "
                      f"sVAL := {x['val_bin']:.0f}; sPOC := {x['poc']:.0f}; end;  "
                      f"// ref {x['ref']}")
    corpo = "\n".join(linhas)
    return f"""//=====================================================================
// vwapvp_niveis — GERADO por `profit-tape vwapvp-ntsl-niveis` em
// {dt.date.today().isoformat()}. NAO EDITE A MAO: regenere.
//
// Plota, em cada pregao, VAH / VAL / POC (bin de {p.bin_pts:g} pts, area de
// valor {p.pct:.0%}, bin a bin) do ULTIMO DIA COMPLETO ANTERIOR no tape —
// exatamente a referencia que o replay `ea-vwapvp-replay` usou para a
// clausula c_nivel (|close - VAH/VAL| <= tolerancia). Serve para VER no
// grafico onde as 9 barras c_nivel cairam, e conferir o POC contra o
// Volume Profile nativo com "negocios de leilao" DESLIGADO.
//
// Dias sem referencia (primeiro do curated, dia apos truncado) repetem o
// nivel anterior para nao deformar a escala.
//=====================================================================

var
  sData, sVAH, sVAL, sPOC, sVAHant, sVALant, sPOCant : Float;
begin
  sVAHant := sVAH[1];
  sVALant := sVAL[1];
  sPOCant := sPOC[1];
  sData := Date;
  sVAH := sVAHant;
  sVAL := sVALant;
  sPOC := sPOCant;
{corpo}
  if sVAH > 0 then
  begin
    Plot(sVAH);
    Plot2(sVAL);
    Plot3(sPOC);
  end;
end;
"""

