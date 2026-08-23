"""
Validacao da classificacao de corretoras (perfil) contra a serie OFICIAL da B3.

Passo pre-registrado (RESEARCH_PLANO.md): antes de gastar trials de IC em
features de perfil, a classificacao nacional/estrangeiro precisa provar que
mede algo real — o fluxo diario agregado por perfil no NOSSO tick (WIN) deve
correlacionar com o saldo oficial por participante da B3. Se nao correlaciona,
a classificacao esta errada e a hipotese cai por dado, sem custar um trial.

Convencao de fluxo: identica a da B3 — comprador soma +quantidade, vendedor
soma -quantidade, TODOS os tipos de negocio (a serie oficial nao filtra
agressao). Ressalva registrada: a serie oficial e' do mercado A VISTA; o nosso
dado e' futuro de indice — proxy contra proxy, correlacao moderada (>=0.4)
ja' valida a DIRECAO da classificacao.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

LIMIAR_CORRELACAO = 0.4          # pre-registrado: valida direcao, nao precisao


def carregar_perfis(agentes_csv: Path) -> dict[int, str]:
    """agent_id -> perfil (vazio = nao classificado)."""
    perfis: dict[int, str] = {}
    with agentes_csv.open(encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            perfis[int(linha["agent_id"])] = (linha.get("perfil") or "").strip().upper()
    return perfis


def fluxo_diario_por_perfil(curated: Path, symbol: str,
                            perfis: dict[int, str]) -> pd.DataFrame:
    """
    Uma linha por dia, uma coluna por perfil (+ NAO_CLASSIFICADO), valor =
    saldo liquido em contratos. Streaming por dia — memoria de 1 pregao.
    """
    origem = curated / "trade"
    linhas = []
    for pasta in sorted(origem.glob("dt=*")):
        if not (pasta / f"sym={symbol}").exists():
            continue
        dia = pasta.name.split("=", 1)[1]
        dataset = ds.dataset(pasta, format="parquet", partitioning="hive",
                             exclude_invalid_files=True)
        df = dataset.to_table(
            filter=ds.field("sym") == symbol,
            columns=["quantidade", "agente_comprador", "agente_vendedor"],
        ).to_pandas()
        saldo: dict[str, float] = {}
        for lado, sinal in (("agente_comprador", 1), ("agente_vendedor", -1)):
            grupo = df.groupby(lado)["quantidade"].sum()
            for ag, q in grupo.items():
                p = perfis.get(int(ag), "") or "NAO_CLASSIFICADO"
                saldo[p] = saldo.get(p, 0.0) + sinal * float(q)
        linhas.append({"data": dia, **saldo})
        del df
    return pd.DataFrame(linhas).fillna(0.0)


def validar(fluxo: pd.DataFrame, referencia_csv: Path) -> dict:
    """
    Correlaciona (Pearson + concordancia de sinal) o fluxo por perfil com a
    serie oficial, nos dias em comum. Teste central pre-registrado:
    ESTRANGEIRO (nosso) x estrangeiro_rs_mil (oficial) >= 0.4.
    """
    ref = pd.read_csv(referencia_csv, comment="#")
    juntos = fluxo.merge(ref, on="data", how="inner")
    if len(juntos) < 8:
        raise SystemExit(f"so' {len(juntos)} dias em comum com a referencia — "
                         f"insuficiente para correlacao honesta")

    oficial_nacional = (
        juntos.get("institucional_rs_mil", 0)
        + juntos.get("pessoa_fisica_rs_mil", 0)
        + juntos.get("inst_financeiras_rs_mil", 0)
        + juntos.get("outros_rs_mil", 0)
    )
    pares = []
    if "ESTRANGEIRO" in juntos.columns:
        pares.append(("ESTRANGEIRO", juntos["ESTRANGEIRO"],
                      juntos["estrangeiro_rs_mil"], True))
    if "NACIONAL" in juntos.columns:
        pares.append(("NACIONAL", juntos["NACIONAL"], oficial_nacional, True))
    for extra in ("MISTO", "HFT", "NAO_CLASSIFICADO"):
        if extra in juntos.columns:
            pares.append((extra, juntos[extra],
                          juntos["estrangeiro_rs_mil"], False))

    resultados = []
    for nome, nosso, oficial, julga in pares:
        r = float(np.corrcoef(nosso, oficial)[0, 1]) if nosso.std() > 0 else float("nan")
        concord = float((np.sign(nosso) == np.sign(oficial)).mean())
        veredito = ""
        if julga:
            veredito = "VALIDA" if (not np.isnan(r) and r >= LIMIAR_CORRELACAO) \
                       else "NAO_VALIDA"
        resultados.append({"perfil": nome, "pearson": r,
                           "concordancia_sinal": concord, "veredito": veredito,
                           "dias": len(juntos)})
    return {"tabela": pd.DataFrame(resultados), "dias_em_comum": len(juntos)}
