"""Historico M1: fator do ajuste pela granularidade (conferido na amostra
real), conferencia contra o tape com fator e rotulo CONHECIDOS, controle
negativo (rotulo pelo FIM do minuto tem de ser apontado) e CLI."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from profittape.cli import app
from profittape.research.ignicao import Tape
from profittape.research.leadlag import janela_do_dia
from profittape.research.m1_historico import (
    barras_do_tape,
    carregar_m1,
    comparar_com_tape,
    fator_por_granularidade,
    inventario_dia,
    melhor_deslocamento,
)

S = 1_000_000_000
DIA = "2026-09-24"
T0, _ = janela_do_dia(DIA, 900, 900)

# As 22 primeiras linhas reais do export (27/09/2021), OHLC.
AMOSTRA = np.array([
    195629, 195749, 195440, 195577, 195577, 195586, 194780, 194943, 194952, 194960,
    194823, 194866, 194866, 194874, 194754, 194849, 194849, 194934, 194806, 194832,
    194832, 194883, 194729, 194797, 194789, 194840, 194763, 194832, 194823, 194917,
    194660, 194703, 194703, 194720, 194600, 194626, 194626, 194677, 194609, 194634,
    194643, 194643, 194463, 194471, 194480, 194523, 194446, 194506, 194497, 194566,
    194497, 194540, 194540, 194591, 194489, 194523, 194523, 194591, 194514, 194574,
    194566, 194600, 194489, 194531, 194531, 194540, 194403, 194489, 194489, 194557,
    194480, 194523, 194523, 194600, 194471, 194566, 194566, 194634, 194497, 194531,
    194540, 194617, 194523, 194591, 194591, 194677, 194557, 194600], dtype=float)


def test_fator_na_amostra_real_conferido_a_mao() -> None:
    f = fator_por_granularidade(AMOSTRA)
    assert f is not None and abs(f - 1.7146) < 0.001
    assert abs(195629 / f - 114_093) < 10                       # WIN de fim de set/2021


def test_fator_um_em_preco_real() -> None:
    precos = 188000 + 5.0 * np.random.default_rng(0).integers(-200, 200, size=500)
    assert fator_por_granularidade(precos) == pytest.approx(1.0)
    assert fator_por_granularidade(np.array([1.0, 2.0])) is None


def _tape(seed: int = 1, horas: float = 2.0) -> Tape:
    rng = np.random.default_rng(seed)
    n = int(horas * 3600 * 5)                  # ~5 negocios/s, intervalos ALEATORIOS
    # (intervalo fixo daria contagem por minuto constante: correlacao indefinida)
    ts = T0 + np.cumsum(rng.exponential(0.2 * S, size=n)).astype(np.int64)
    px = 188000 + 5.0 * np.cumsum(rng.choice([-1, 0, 1], size=n, p=[0.3, 0.4, 0.3]))
    return Tape(ts, px, np.ones(n, np.int64), np.full(n, 2, np.int64))


def _export(tape: Tape, fator: float, rotulo_fim: bool = False) -> pd.DataFrame:
    """Export sintetico: candles do tape x fator, arredondados (como o Profit)."""
    b = barras_do_tape(tape)
    e = pd.DataFrame({
        "data_hora": b.index + (pd.Timedelta(minutes=1) if rotulo_fim else pd.Timedelta(0)),
        **{c: np.round(b[c].to_numpy() * fator) for c in
           ("abertura", "maxima", "minima", "fechamento")},
        "volume": b["contratos"].to_numpy(), "volume_ticks": b["negocios"].to_numpy()})
    e["dia"] = e["data_hora"].dt.strftime("%Y-%m-%d")
    return e.reset_index(drop=True)


def test_conferencia_com_fator_e_rotulo_conhecidos() -> None:
    tape = _tape()
    e = _export(tape, 1.7146)
    f = fator_por_granularidade(e[["abertura", "maxima", "minima", "fechamento"]]
                                .to_numpy().ravel())
    assert f is not None and abs(f - 1.7146) < 0.002
    comp = comparar_com_tape(e, barras_do_tape(tape))
    assert comp[0]["fech_ok_pct"] == 100.0
    assert comp[0]["razao_mediana"] == pytest.approx(1.7146, abs=1e-4)
    assert comp[0]["corr_negocios_x_volume_ticks"] == pytest.approx(1.0)
    assert melhor_deslocamento(comp) == {"por_preco": 0, "por_contagem": 0}


def test_controle_negativo_rotulo_pelo_fim_e_apontado() -> None:
    """O verificador DEVE reprovar o alinhamento 0 quando o export rotula pelo
    FIM do minuto: o candle rotulado T e' o que COMECA em T-1 -> s = -1."""
    tape = _tape(2)
    comp = comparar_com_tape(_export(tape, 1.0, rotulo_fim=True), barras_do_tape(tape))
    assert melhor_deslocamento(comp) == {"por_preco": -1, "por_contagem": -1}
    assert comp[0]["fech_ok_pct"] < comp[-1]["fech_ok_pct"]


def test_inventario_conta_lacunas_e_duplicatas() -> None:
    t = pd.to_datetime(["2026-09-24 09:00", "2026-09-24 09:01", "2026-09-24 09:01",
                        "2026-09-24 09:05"])
    g = pd.DataFrame({"data_hora": t, "abertura": 1.0, "maxima": 1.0, "minima": 1.0,
                      "fechamento": 1.0})
    inv = inventario_dia(g)
    assert (inv["barras"], inv["duplicatas"], inv["lacunas"]) == (4, 1, 1)
    assert (inv["primeira"], inv["ultima"]) == ("09:00", "09:05")


def test_carregar_recusa_cabecalho_diferente(tmp_path: Path) -> None:
    p = tmp_path / "m1.csv"
    p.write_text("data,o,h,l,c\n2021-09-27 09:00:00,1,1,1,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="colunas ausentes"):
        carregar_m1(p)


def test_cli_ponta_a_ponta(tmp_path: Path) -> None:
    tape = _tape(3)
    e = _export(tape, 1.0)
    csv = tmp_path / "winfut_m1_historico.csv"
    out = e.drop(columns=["dia"]).copy()
    out["data_hora"] = out["data_hora"].dt.strftime("%Y-%m-%d %H:%M:%S")
    out.to_csv(csv, index=False)
    pasta = tmp_path / "raw" / "trade" / f"dt={DIA}" / "sym=WINFUT"
    pasta.mkdir(parents=True)
    pd.DataFrame({"ts_ns": tape.ts, "trade_id": np.arange(len(tape)), "price": tape.px,
                  "quantidade": tape.qtd, "trade_type": tape.tipo}
                 ).to_parquet(pasta / "part-0000.parquet")
    r = CliRunner().invoke(app, ["m1-valida", str(csv), "--raw", str(tmp_path / "raw"),
                                 "--saida", str(tmp_path / "out")])
    assert r.exit_code == 0, r.output
    assert "1 pregoes" in r.output and "2026-09=1.0000" in r.output
    assert "melhor: preco=0 contagem=0" in r.output and "concordam: 1/1" in r.output
    assert (tmp_path / "out" / "conferencia_tape.csv").exists()
    r = CliRunner().invoke(app, ["m1-valida", str(csv), "--sem-tape",
                                 "--saida", str(tmp_path / "out2")])
    assert r.exit_code == 0 and "CONFERENCIA" not in r.output
