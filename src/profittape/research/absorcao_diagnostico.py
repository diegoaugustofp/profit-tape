"""
Diagnostico da leitura de absorcao: ESFORCO por tick e separacao A/B.

CATEGORIA `features`: descreve o dado, nao testa hipotese. NAO consome
trial. Nada aqui autoriza conclusao sobre retorno.

POR QUE EXISTE
--------------
Uma barra real de 2026-08-31 (09:03-09:05) foi pintada AQUA pelo
indicador, e a leitura do operador foi a oposta: "os compradores
agrediram e levaram o preco embora".

Os numeros deram razao a ele:

    imbalance    +0,049   (agressao praticamente empatada)
    desloc_norm  +0,951   (quase marubozu de alta, +326 ticks)
    absorcao_dir -0,902   -> aqua

Nao houve vendedor agredindo nada. O preco subiu porque o livro estava
FINO.

O DEFEITO CONCEITUAL
--------------------
`absorcao_dir = imbalance - desloc_norm` e' uma SUBTRACAO, e um valor
extremo pode vir de dois lugares OPOSTOS:

  CASO A  agressao forte num sentido, preco no outro.
          Ha' esforco, e ele FALHOU -> absorcao de verdade.

  CASO B  preco anda muito SEM agressao dominante.
          Nao e' resistencia escondida; e' AUSENCIA de resistencia.

Os dois produziam a MESMA cor. E como `imbalance` raramente sai de +-0,3
enquanto `desloc_norm` vai ate +-1, quem domina a subtracao quase sempre
e' o `desloc_norm` — ou seja, boa parte do que o indicador pintava era
deslocamento normalizado com o sinal trocado, nao absorcao.

Isso e' coerente com o CONTRA nas 12 celulas, e com o achado de
2026-08-30b: a formula satura porque os dois termos sao limitados.

O TERMO QUE FALTA
-----------------
Absorcao, na leitura de tape, e' ESFORCO GRANDE com RESULTADO PEQUENO. O
esforco precisa de um termo ILIMITADO — `imbalance` nunca passa de 1:

    esforco = vol_agr / amplitude_em_ticks

Barra que anda muito com volume normal  -> esforco BAIXO (livro fino).
Barra que anda pouco com volume enorme  -> esforco ALTO  (absorcao).

Este modulo MEDE a distribuicao desse termo e a separacao A/B. Nao
propoe limiar, nao testa predicao: e' o insumo empirico para um
pre-registro futuro.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import structlog

log = structlog.get_logger(__name__)

# Rotulos das quatro leituras. Espelham as cores do .ntsl.
ROTULOS = {
    ("alto", "A"): "A_compra_absorvida",   # comprador agrediu e nao levou
    ("alto", "B"): "B_queda_sem_esforco",  # preco caiu sem vendedor agredir
    ("baixo", "A"): "A_venda_absorvida",   # vendedor agrediu e nao levou
    ("baixo", "B"): "B_alta_sem_esforco",  # preco subiu sem comprador agredir
}


def classificar(z_absorcao: pd.Series, z_imbalance: pd.Series,
                limiar: float, limiar_imb: float) -> pd.Series:
    """
    Reproduz EXATAMENTE a regra de cor do `.ntsl`.

    Duas implementacoes da mesma regra divergem em silencio quando uma
    das duas muda; por isso a regra esta escrita aqui na mesma forma, e
    o teste compara as duas contra os mesmos casos de fronteira.
    """
    fora = pd.Series("nao_pintou", index=z_absorcao.index, dtype=object)
    alto = z_absorcao >= limiar
    baixo = z_absorcao <= -limiar
    fora[alto & (z_imbalance >= limiar_imb)] = ROTULOS[("alto", "A")]
    fora[alto & ~(z_imbalance >= limiar_imb)] = ROTULOS[("alto", "B")]
    fora[baixo & (z_imbalance <= -limiar_imb)] = ROTULOS[("baixo", "A")]
    fora[baixo & ~(z_imbalance <= -limiar_imb)] = ROTULOS[("baixo", "B")]
    return fora


def calcular_esforco(barras: pd.DataFrame, tick: float) -> pd.Series:
    """
    `vol_agr / amplitude_em_ticks` — contratos por tick percorrido.

    ILIMITADO de proposito: e' a propriedade que falta a `imbalance` e a
    `desloc_norm`, ambos presos em [-1, +1]. Uma barra pode ter cinco
    vezes o volume normal na mesma amplitude; nenhuma pode ter
    `imbalance` cinco vezes maior que 1.

    Barra de amplitude ZERO (todos os negocios no mesmo preco) e' o
    esforco maximo concebivel e nao um erro — mas dividir por zero
    devolveria `inf`, que contamina qualquer media. Fica NaN e sai das
    estatisticas, com a contagem reportada a parte.
    """
    ticks = (barras["high"] - barras["low"]) / tick
    return (barras["vol_agr"] / ticks.where(ticks > 0)).astype(float)


def resumir(barras: pd.DataFrame, tick: float, limiar: float,
            limiar_imb: float) -> dict[str, Any]:
    """Distribuicao do esforco, global e por leitura."""
    d = barras.copy()
    d["esforco"] = calcular_esforco(d, tick)
    d["leitura"] = classificar(d["z_absorcao_dir"], d["z_imbalance"],
                               limiar, limiar_imb)

    validas = d["esforco"].notna()
    quantis = [0.05, 0.25, 0.50, 0.75, 0.95, 0.99]
    geral = {f"p{int(q * 100)}": round(float(d.loc[validas, "esforco"]
                                             .quantile(q)), 1)
             for q in quantis}

    por_leitura = []
    for rotulo, g in d[validas].groupby("leitura"):
        por_leitura.append({
            "leitura": rotulo,
            "n": len(g),
            "pct_das_barras": round(100.0 * len(g) / len(d), 2),
            "esforco_mediano": round(float(g["esforco"].median()), 1),
            "esforco_p95": round(float(g["esforco"].quantile(0.95)), 1),
            "imbalance_mediano": round(float(g["imbalance"].median()), 4),
            "desloc_norm_mediano": round(float(g["desloc_norm"].median()), 4),
            "amplitude_mediana_ticks": round(
                float(((g["high"] - g["low"]) / tick).median()), 1),
        })

    return {
        "barras": len(d),
        "amplitude_zero": int((~validas).sum()),
        "esforco_geral": geral,
        "por_leitura": sorted(por_leitura, key=lambda x: -x["n"]),
        "tabela": d,
    }


def rodar(features_parquet: Path, tick: float = 5.0, limiar: float = 1.75,
          limiar_imb: float = 1.0) -> dict[str, Any]:
    faltando = [c for c in ("z_absorcao_dir", "z_imbalance", "z_desloc_norm",
                            "imbalance", "desloc_norm", "high", "low",
                            "vol_agr")
                if c not in pd.read_parquet(features_parquet).columns]
    if faltando:
        raise SystemExit(
            f"{features_parquet} nao tem {faltando}.\n"
            "O `features-tempo` grava so' as 3 colunas pre-registradas. "
            "Rode com --diagnostico para incluir as auxiliares."
        )
    barras = pd.read_parquet(features_parquet)
    r = resumir(barras, tick, limiar, limiar_imb)
    log.info("absorcao_diagnostico.resumo", barras=r["barras"],
             leituras=len(r["por_leitura"]))
    return r


def esforco_de_uma_barra(vol_agr: float, high: float, low: float,
                         tick: float = 5.0) -> float:
    """Atalho para conferir uma barra a mao, como a de 2026-08-31."""
    ticks = (high - low) / tick
    return float(vol_agr / ticks) if ticks > 0 else float("nan")
