"""Ignicao M1 (fast-track): conta a mao, bordas, INVARIANCIA ao ajuste
multiplicativo (a premissa do uso da serie ajustada), controle negativo,
traducao M1 x tape e CLI."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from typer.testing import CliRunner

from profittape.cli import app
from profittape.research.ignicao_m1 import (
    LAMBDA_TAPE,
    amplitude_60_do_dia,
    comparar_com_tape,
    detectar_dia,
    detectar_historico,
    placar,
)

DIA = "2026-09-24"


def _dia(linhas: list[tuple[str, float, float, float]], dia: str = DIA) -> pd.DataFrame:
    """(hh:mm, maxima, minima, fechamento)."""
    g = pd.DataFrame({"data_hora": pd.to_datetime([f"{dia} {h}" for h, *_ in linhas]),
                      "abertura": [c for *_, c in linhas],
                      "maxima": [x for _, x, _, _ in linhas],
                      "minima": [x for _, _, x, _ in linhas],
                      "fechamento": [c for *_, c in linhas]})
    g["dia"] = dia
    return g


def test_caso_conferido_a_mao() -> None:
    g = _dia([("10:29", 188000, 188000, 188000), ("10:30", 188480, 188000, 188480),
              ("10:31", 188700, 188300, 188500), ("10:32", 188990, 188600, 188900)])
    (e,) = detectar_dia(g, A=1000, fator=1.5)
    assert (e.hora_decisao, e.direcao, e.mov, e.entrada) == ("10:31", 1, 480, 188480)
    assert (e.resultado, e.candles_ate_decidir) == ("alvo", 2)
    assert (e.mov_real, e.empate) == (320.0, 0.5585)


def test_stop_ambiguo_e_sem_decisao() -> None:
    base = [("10:29", 188000, 188000, 188000), ("10:30", 188480, 188000, 188480)]
    assert detectar_dia(_dia([*base, ("10:31", 188500, 187980, 188000)]),
                        A=1000, fator=1.0)[0].resultado == "stop"
    assert detectar_dia(_dia([*base, ("10:31", 188980, 187980, 188000)]),
                        A=1000, fator=1.0)[0].resultado == "ambiguo"
    longe = [("11:31", 188600, 188400, 188500)]                # depois de 60 min
    assert detectar_dia(_dia(base + longe), A=1000, fator=1.0)[0].resultado == "sem_decisao"


def test_bordas_de_horario_consecutivo_e_refratario() -> None:
    def ev(linhas: list[tuple[str, float, float, float]]) -> list[str]:
        return [e.hora_decisao for e in detectar_dia(_dia(linhas), A=1000, fator=1.0)]
    assert ev([("09:14", 1, 1, 188000), ("09:15", 1, 1, 188500)]) == ["09:16"]
    assert ev([("09:13", 1, 1, 188000), ("09:14", 1, 1, 188500)]) == []   # decide 09:15
    assert ev([("16:58", 1, 1, 188000), ("16:59", 1, 1, 188500)]) == []   # decide 17:00
    assert ev([("10:28", 1, 1, 188000), ("10:30", 1, 1, 188500)]) == []   # nao consecutivo
    assert ev([("10:00", 1, 1, 188000), ("10:01", 1, 1, 188500),          # 10:02
               ("10:20", 1, 1, 188500), ("10:21", 1, 1, 189000),          # refratario
               ("10:31", 1, 1, 189000), ("10:32", 1, 1, 189500)]) == ["10:02", "10:33"]


def test_amplitude_60_a_mao() -> None:
    g = _dia([("09:15", 188100, 188000, 188050), ("10:14", 188300, 188050, 188200),
              ("10:15", 188200, 187900, 188000), ("11:14", 188400, 188000, 188300)])
    assert amplitude_60_do_dia(g) == (300 + 500) / 2                     # blocos 300 e 500


def _historico(n_dias: int, seed: int, momento: bool) -> pd.DataFrame:
    """Passeio de candles de 1 min (09:00-18:24) com 3 SALTOS de 600 pts por
    dia. momento=True: o salto continua (+700 pts em 14 min); False: o salto
    NAO continua. Sem os saltos o passeio gaussiano nunca dispara (550 pts em
    1 min seriam 9 desvios) e o controle negativo seria vazio."""
    rng = np.random.default_rng(seed)
    dfs = []
    for k in range(n_dias):
        dia = (pd.Timestamp("2022-01-03") + pd.tseries.offsets.BDay(k)).strftime("%Y-%m-%d")
        t = pd.date_range(f"{dia} 09:00", f"{dia} 18:24", freq="1min")
        passos = rng.normal(0, 60, size=len(t))
        for i in rng.choice(np.arange(30, 450), size=3, replace=False):
            passos[i] += 600 * rng.choice([-1, 1])
            if momento:
                passos[i + 1:i + 15] += np.sign(passos[i]) * 50
        c = 120000 + np.cumsum(passos)
        o = np.r_[c[0], c[:-1]]
        ruido = np.abs(rng.normal(0, 30, size=len(t)))
        h, lo = np.maximum(o, c) + ruido, np.minimum(o, c) - ruido
        g = pd.DataFrame({"data_hora": t, "abertura": o, "maxima": h, "minima": lo,
                          "fechamento": c, "volume": 1, "volume_ticks": 1})
        g[["abertura", "maxima", "minima", "fechamento"]] = (
            np.round(g[["abertura", "maxima", "minima", "fechamento"]] / 5) * 5)
        g["dia"] = dia
        dfs.append(g)
    return pd.concat(dfs, ignore_index=True)


def test_invariancia_ao_ajuste_multiplicativo() -> None:
    """A premissa do historico ajustado: escalar TUDO por 1,7 nao muda
    nenhum evento nem resultado (so' os pontos ajustados)."""
    df = _historico(30, seed=1, momento=True)
    ajust = df.copy()
    cols = ["abertura", "maxima", "minima", "fechamento"]
    ajust[cols] = np.round(ajust[cols] * 1.7)
    e1, _ = detectar_historico(df)
    e2, _ = detectar_historico(ajust)
    assert len(e1) >= 10
    assert [(e.dia, e.hora_decisao, e.direcao, e.resultado) for e in e1] == \
           [(e.dia, e.hora_decisao, e.direcao, e.resultado) for e in e2]
    assert abs(np.median([e.mov_real / e1[i].mov_real for i, e in enumerate(e2)]) - 1) < 0.01


def test_primeiros_20_pregoes_so_alimentam_a_amplitude() -> None:
    evs, dias = detectar_historico(_historico(25, seed=2, momento=True))
    assert dias["A"].isna().sum() == 20
    assert all(e.dia > dias["dia"].iloc[19] for e in evs)


def test_controle_negativo_passeio_sem_momento() -> None:
    """O caso que o verificador DEVE reprovar: sem momento, p_alvo ~ 0,5."""
    evs, dias = detectar_historico(_historico(120, seed=3, momento=False))
    p = placar(evs, int(dias["A"].notna().sum()))
    assert p["alvo"] + p["stop"] >= 40
    assert 0.35 < p["p_alvo"] < 0.65


def test_momento_plantado_aparece() -> None:
    evs, _ = detectar_historico(_historico(60, seed=4, momento=True))
    assert placar(evs)["p_alvo"] > 0.7


def test_traducao_m1_x_tape() -> None:
    g = _dia([("10:29", 188000, 188000, 188000), ("10:30", 188480, 188000, 188480),
              ("10:31", 188990, 188300, 188900)])
    evs = detectar_dia(g, A=1000, fator=1.0)
    tape = pd.DataFrame({"dia": [DIA, DIA], "hora_brt": ["10:30:40", "14:00:00"],
                         "direcao": [1, -1], "barreira": ["alvo", "stop"]})
    c = comparar_com_tape(evs, tape)
    assert (c["casados"], c["so_no_tape"], c["so_no_m1"], c["barreira_concorda"]) == (
        1, 1, 0, "1/1")


def test_cli_ponta_a_ponta(tmp_path: Path) -> None:
    df = _historico(40, seed=5, momento=True)
    csv = tmp_path / "m1.csv"
    out = df.drop(columns=["dia"]).copy()
    out["data_hora"] = out["data_hora"].dt.strftime("%Y-%m-%d %H:%M:%S")
    out.to_csv(csv, index=False)
    r = CliRunner().invoke(app, ["ignicao-m1", str(csv), "--saida", str(tmp_path / "o")])
    assert r.exit_code == 0, r.output
    assert f"lambda={LAMBDA_TAPE:.4f}" in r.output and "20 pregoes com A" in r.output
    assert "2022:" in r.output and "TOTAL:" in r.output and "criterio:" in r.output
    assert (tmp_path / "o" / "eventos_m1.csv").exists()
