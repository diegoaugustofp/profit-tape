"""Evolucao da ficha de um EA: o que mudou nela (git) e sob quais carimbos as operacoes
rodaram. A regra do projeto -- "mudou numero, regra ou saida => contagem nova" -- so' e'
verificavel olhando o `config_sha` de cada operacao."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


def historico_da_ficha(raiz_fichas: Path, ficha: str, n: int = 14) -> list[dict[str, str]]:
    """Ultimos `n` commits que tocaram a ficha (data, hash, assunto). Sem git ou fora de um
    repositorio devolve lista vazia -- a pagina avisa em vez de falhar."""
    try:
        r = subprocess.run(
            ["git", "-C", str(raiz_fichas), "log", "--follow", f"-n{n}",
             "--format=%ad\t%h\t%s", "--date=short", "--", ficha],
            capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if r.returncode != 0:
        return []
    out = []
    for linha in r.stdout.splitlines():
        partes = linha.split("\t", 2)
        if len(partes) == 3:
            out.append({"data": partes[0], "hash": partes[1], "assunto": partes[2][:150]})
    return out


def carimbos(ops: pd.DataFrame) -> dict[str, Any]:
    """Operacoes por (config_sha, codigo): primeiro/ultimo dia, quantas, P&L. `mudou` = mais de
    um config_sha (contagem nova a partir de `desde_ultimo`). Linhas sem carimbo (CSV de antes
    da v4.18) contam em `sem_carimbo`."""
    if "config_sha" not in ops or ops["config_sha"].isna().all():
        return {"linhas": [], "mudou": False, "sem_carimbo": len(ops), "desde_ultimo": None,
                "n_no_atual": None}
    x = ops[ops["config_sha"].notna()]
    g = (x.groupby(["config_sha", "codigo"], dropna=False)
         .agg(n=("pnl_liquido", "size"), primeiro=("dia", "min"), ultimo=("dia", "max"),
              pnl=("pnl_liquido", "sum")).reset_index().sort_values("primeiro"))
    linhas = []
    for sha, cod, n, pri, ult, pnl in zip(g["config_sha"].tolist(), g["codigo"].tolist(),
                                          g["n"].tolist(), g["primeiro"].tolist(),
                                          g["ultimo"].tolist(), g["pnl"].tolist(), strict=True):
        linhas.append({"config_sha": str(sha), "codigo": "" if pd.isna(cod) else str(cod),
                       "n": int(n), "primeiro": str(pri), "ultimo": str(ult), "pnl": float(pnl)})
    shas = []
    for linha in linhas:                       # ordem de aparicao
        if linha["config_sha"] not in shas:
            shas.append(linha["config_sha"])
    atual = x.sort_values(["dia", "hora_saida"]).iloc[-1]["config_sha"]
    no_atual = x[x["config_sha"] == atual]
    return {"linhas": linhas, "mudou": len(shas) > 1, "sem_carimbo": len(ops) - len(x),
            "desde_ultimo": str(no_atual["dia"].min()), "n_no_atual": len(no_atual)}
