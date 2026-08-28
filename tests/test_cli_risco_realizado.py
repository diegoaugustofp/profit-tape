"""
Teste de regressao do bug de exibicao (2026-08-27, achado pelo operador):
0.99 e 0.995 colidiam visualmente na tabela (float_format unico
arredondava os dois para "0.99"). Mesma familia de bug ja corrigida em
quintis.py (v0.58) -- corrigida aqui tambem, com teste dedicado desta
vez para nao repetir.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from typer.testing import CliRunner

from profittape.cli import app

runner = CliRunner()


def test_niveis_de_confianca_proximos_nao_colidem_na_tabela(tmp_path: Path) -> None:
    rng = np.random.default_rng(3)
    n = 500
    base = int(datetime(2026, 8, 27, 9, 0, tzinfo=UTC).timestamp() * 1e9)
    df = pd.DataFrame({
        "ts_close": base + np.arange(n) * 60 * 10**9,
        "close": 140000.0 + np.cumsum(rng.normal(0, 10, n)),
    })
    raiz = tmp_path / "features" / "sym=WINFUT"
    raiz.mkdir(parents=True)
    df.to_parquet(raiz / "features.parquet", index=False)

    resultado = runner.invoke(app, [
        "risco-realizado", "--symbol", "WINFUT",
        "--features", str(tmp_path / "features"),
        "--limiar-pontos", "50",
    ])
    assert resultado.exit_code == 0, resultado.output
    # 99.0% e 99.5% tem que aparecer DISTINTOS na saida -- nao mais "0.99"
    # duas vezes por causa de arredondamento.
    assert "99.0%" in resultado.output
    assert "99.5%" in resultado.output
    assert resultado.output.count("99.0%") + resultado.output.count("99.5%") >= 2
