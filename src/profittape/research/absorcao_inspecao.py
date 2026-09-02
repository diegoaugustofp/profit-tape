"""
Por que ESTA barra marcou (ou nao marcou)?

Diagnostico de MECANISMO, categoria `features`: mostra o valor de cada
condicao e a folga ate o corte. **Nao toca em retorno**, nao consome
trial.

PARA QUE SERVE, E O LIMITE QUE O ACOMPANHA
------------------------------------------
Entender por que uma barra ficou de fora e' investigacao legitima — foi
assim que se descobriu, em 2026-08-31, que a formula antiga pintava
MARUBOZUS enquanto o conceito era DOJI com pavio. Sem olhar barras
concretas, aquele erro continuaria de pe'.

O que NAO pode sair daqui e' ajuste de corte. Baixar `MAX_DESLOC_NORM`
de 0,25 para 0,28 porque uma barra especifica ficou de fora e' ajustar o
modelo a' amostra — mesmo sem olhar retorno, e' calibrar ao julgamento
sobre AQUELES dados.

Se a inspecao mostrar que a formalizacao nao captura a leitura, o
caminho e' pre-registro NOVO com formalizacao diferente, testada em dado
que ela nao viu.

**E so' inspecione periodo JA' QUEIMADO** (parquet 24/07-27/08, maio do
grafico). Olhar o periodo que ainda vai ser testado destroi a cegueira
que e' a unica razao de ele valer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from .absorcao_barra import (
    JANELA_CONTEXTO,
    K_CONTEXTO,
    MAX_DESLOC_NORM,
    MIN_Z_AMPLITUDE,
    MIN_Z_VOL_AGR,
    marcar_eventos,
    preparar,
)

log = structlog.get_logger(__name__)


def _folga(valor: float, corte: float, maior_e_melhor: bool) -> str:
    """
    Quanto falta (ou sobra) para a condicao passar.

    A FOLGA e' o que torna a inspecao util: saber que uma barra falhou
    por 0,01 e' informacao diferente de saber que falhou por 0,60. A
    primeira sugere corte apertado; a segunda, que a barra nao e' o que
    se procura. Sem o numero, as duas parecem iguais.
    """
    if pd.isna(valor):
        return "sem dado"
    d = (valor - corte) if maior_e_melhor else (corte - valor)
    return f"{'passa' if d >= 0 else 'FALHA'} por {abs(d):.3f}"


def inspecionar_dia(barras: pd.DataFrame, dia: str) -> pd.DataFrame:
    """Uma linha por barra do dia, com o veredito de cada condicao."""
    d = marcar_eventos(preparar(barras))
    alvo = pd.Timestamp(dia).date()
    do_dia = d[d["dia"] == alvo]
    if do_dia.empty:
        disponiveis = sorted({str(x) for x in d["dia"].unique()})
        raise SystemExit(
            f"nenhuma barra em {dia}.\n"
            f"  dias disponiveis: {disponiveis[0]} a {disponiveis[-1]} "
            f"({len(disponiveis)} pregoes)"
        )

    linhas = []
    for i, (_, b) in enumerate(do_dia.iterrows(), start=1):
        linhas.append({
            "n": i,
            "hora": (str(b["hora"])[:5] if "hora" in b
                     else str(pd.Timestamp(b["ts_close"], unit="ns").time())[:5]),
            "desloc_norm": round(float(b["desloc_norm"]), 3),
            "resultado": _folga(abs(float(b["desloc_norm"])),
                                MAX_DESLOC_NORM, maior_e_melhor=False),
            "z_amp": round(float(b["z_amplitude"]), 2),
            "alcance": _folga(float(b["z_amplitude"]), MIN_Z_AMPLITUDE, True),
            "z_vol": round(float(b["z_vol_agr"]), 2),
            "esforco": _folga(float(b["z_vol_agr"]), MIN_Z_VOL_AGR, True),
            "mov6": round(float(b["mov_contexto"]), 2),
            "contexto": _folga(abs(float(b["mov_contexto"])),
                               K_CONTEXTO, maior_e_melhor=True),
            "EVENTO": bool(b["evento"]),
            "MARCOU": bool(b["evento"] and b["contexto_ok"]),
        })
    return pd.DataFrame(linhas)


def resumir_falhas(tabela: pd.DataFrame) -> dict[str, Any]:
    """
    Qual condicao mais reprova no dia.

    Se uma condicao sozinha reprova quase tudo, ela e' a que define o
    evento na pratica — e as outras duas estao decorativas. Isso e'
    exatamente o defeito que o `absorcao_dir` tinha (o `desloc_norm`
    dominava a subtracao), e vale saber se voltou por outro caminho.
    """
    nao = tabela[~tabela["MARCOU"]]
    return {
        "barras": len(tabela),
        "marcaram": int(tabela["MARCOU"].sum()),
        "falhou_resultado": int(nao["resultado"].str.startswith("FALHA").sum()),
        "falhou_alcance": int(nao["alcance"].str.startswith("FALHA").sum()),
        "falhou_esforco": int(nao["esforco"].str.startswith("FALHA").sum()),
        "falhou_contexto": int(nao["contexto"].str.startswith("FALHA").sum()),
    }


def carregar(origem: Path) -> pd.DataFrame:
    """Aceita o parquet de features OU um dump `ABSBARRA|` do grafico."""
    if origem.suffix == ".parquet":
        b = pd.read_parquet(origem)
        if "vol_agr" not in b.columns:
            b["vol_agr"] = b["vol_buy"] + b["vol_sell"]
        return b
    from .absorcao_grafico import carregar_log, para_barras

    df, _ = carregar_log(origem)
    b = para_barras(df)
    b["hora"] = df["hora"].astype(int).astype(str).str.zfill(4)
    b["hora"] = b["hora"].str[:2] + ":" + b["hora"].str[2:]
    return b


def rodar(origem: Path, dia: str) -> dict[str, Any]:
    tabela = inspecionar_dia(carregar(origem), dia)
    log.info("absorcao_inspecao", dia=dia, **resumir_falhas(tabela))
    return {"tabela": tabela, "resumo": resumir_falhas(tabela),
            "cortes": {"|desloc_norm| <=": MAX_DESLOC_NORM,
                       "z_amplitude >=": MIN_Z_AMPLITUDE,
                       "z_vol_agr >=": MIN_Z_VOL_AGR,
                       f"|mov{JANELA_CONTEXTO}| >=": K_CONTEXTO}}
