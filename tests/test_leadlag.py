"""Lead-lag WDO x WIN: conferencia a mao, sintetico com defasagem conhecida,
controle NEGATIVO (independentes) e ponta a ponta pela CLI."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from profittape.cli import app
from profittape.research.leadlag import (
    AcumCorr,
    assimetria,
    carregar_precos,
    eventos,
    janela_do_dia,
    resumir_eventos,
    retornos_na_grade,
)

MS = 1_000_000
DIA = "2026-09-22"
T0, T1 = janela_do_dia(DIA, 915, 1720)
DUR = 20 * 60 * 1000 * MS          # 20 min de dado sintetico


def _caminhada(rng: np.random.Generator, n: int, passo_ms: int, p0: float,
               tick: float) -> tuple[np.ndarray, np.ndarray]:
    ts = T0 + np.arange(n, dtype=np.int64) * passo_ms * MS
    px = p0 + np.cumsum(rng.choice([-1, 0, 0, 0, 1], size=n)) * tick
    return ts, px


def _par(rng: np.random.Generator, atraso_ms: int | None
         ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Lider WDO a cada 20 ms. Seguidor WIN = espelho INVERTIDO do lider,
    1 tick de WIN por tick de WDO, `atraso_ms` depois. None = independente."""
    n = DUR // (20 * MS)
    tl, pl = _caminhada(rng, n, 20, 5000.0, 0.5)
    if atraso_ms is None:
        ts, ps = _caminhada(rng, n, 20, 120000.0, 5.0)
    else:
        ts = tl + atraso_ms * MS
        ps = 120000.0 - (pl - 5000.0) / 0.5 * 5.0
    return tl, pl, ts, ps


def _corr(tl: np.ndarray, pl: np.ndarray, ts: np.ndarray, ps: np.ndarray,
          lags: list[int]) -> dict[int, float | None]:
    acc = AcumCorr(lags)
    acc.somar(retornos_na_grade(tl, pl, 0.5, T0, T0 + DUR, 50),
              retornos_na_grade(ts, ps, 5.0, T0, T0 + DUR, 50), 50)
    return acc.corr()


LAGS = [-1000, -300, -100, 0, 100, 300, 1000]


def test_evento_conferido_a_mao() -> None:
    b = T0 + 60_000 * MS
    tl = np.array([b, b + 900 * MS, b + 1000 * MS])
    pl = np.array([5000.0, 5000.0, 5001.0])                  # +2 ticks WDO
    ts = np.array([b, b + 1300 * MS, b + 3000 * MS])
    ps = np.array([120000.0, 119990.0, 119985.0])            # WIN cai 300 ms depois
    ev = eventos(tl, pl, ts, ps, tick_lider=0.5, limiar_ticks=2, janela_ms=500,
                 horizontes_ms=[200, 500, 5000], refratario_ms=2000, sentido=-1,
                 t0=T0, t1=T1)
    assert len(ev) == 1
    e = ev[0]
    assert e.direcao_lider == 1 and e.pre_pts == 0
    assert e.pos_pts == {200: 0.0, 500: 10.0, 5000: 15.0}
    r = resumir_eventos(ev, [200, 500, 5000], 5.0)
    assert r["seguidor_parado"]["n"] == 1
    assert r["seguidor_parado"]["h500ms"]["media_pts"] == 10.0


def test_defasagem_conhecida_aparece_no_lag_certo_com_sinal_certo() -> None:
    tl, pl, ts, ps = _par(np.random.default_rng(1), atraso_ms=300)
    c = _corr(tl, pl, ts, ps, LAGS)
    assert c[300] is not None and c[300] < -0.9          # espelho invertido
    assert all(abs(c[k] or 0) < 0.05 for k in (-1000, -300, -100, 0))
    a = assimetria(c, -1)
    assert a[300] is not None and a[300] > 0.9           # lider na frente


def test_controle_negativo_independentes_nao_mostram_lider() -> None:
    """O caso que o verificador DEVE reprovar."""
    tl, pl, ts, ps = _par(np.random.default_rng(2), atraso_ms=None)
    a = assimetria(_corr(tl, pl, ts, ps, LAGS), -1)
    assert all(v is not None and abs(v) < 0.03 for v in a.values())
    ev = eventos(tl, pl, ts, ps, tick_lider=0.5, limiar_ticks=2, janela_ms=500,
                 horizontes_ms=[1000], refratario_ms=500, sentido=-1, t0=T0, t1=T1)
    r = resumir_eventos(ev, [1000], 5.0)["todos"]
    assert r["n"] > 200
    assert abs(r["h1000ms"]["media_pts"]) < 1.5


def test_eventos_com_lider_real_vao_a_favor_e_seguidor_parado() -> None:
    tl, pl, ts, ps = _par(np.random.default_rng(3), atraso_ms=300)
    ev = eventos(tl, pl, ts, ps, tick_lider=0.5, limiar_ticks=2, janela_ms=200,
                 horizontes_ms=[1000], refratario_ms=500, sentido=-1, t0=T0, t1=T1)
    r = resumir_eventos(ev, [1000], 5.0)
    assert r["seguidor_parado"]["n"] > 50
    assert r["seguidor_parado"]["h1000ms"]["media_pts"] > 5


def test_refratario_conta_um_por_episodio() -> None:
    b = T0 + 60_000 * MS
    # historico 1 s antes: sem preco de referencia na janela nao ha' evento
    tl = np.array([b - 1000 * MS, b, b + 100 * MS, b + 200 * MS, b + 300 * MS])
    pl = np.array([5000.0, 5000.0, 5001.0, 5001.5, 5002.0])  # 3 gatilhos seguidos
    ts, ps = np.array([b - 1000 * MS]), np.array([120000.0])
    kw = dict(tick_lider=0.5, limiar_ticks=2, janela_ms=500, horizontes_ms=[100],
              sentido=-1, t0=T0, t1=T1)
    assert len(eventos(tl, pl, ts, ps, refratario_ms=0, **kw)) == 3      # type: ignore[arg-type]
    assert len(eventos(tl, pl, ts, ps, refratario_ms=2000, **kw)) == 1   # type: ignore[arg-type]


def _gravar(raiz: Path, sym: str, ts: np.ndarray, px: np.ndarray,
            ids: np.ndarray | None = None) -> None:
    pasta = raiz / "trade" / f"dt={DIA}" / f"sym={sym}"
    pasta.mkdir(parents=True)
    pd.DataFrame({"ts_ns": ts, "trade_id": ids if ids is not None else np.arange(len(ts)),
                  "price": px}).to_parquet(pasta / "part-0000.parquet")


def test_carregar_deduplica_por_trade_id_ficando_a_edicao(tmp_path: Path) -> None:
    b = T0 + 60_000 * MS
    _gravar(tmp_path, "WDOFUT", np.array([b, b + MS, b + 2 * MS]),
            np.array([5000.0, 5000.5, 5001.0]), ids=np.array([7, 8, 7]))
    _, px = carregar_precos(tmp_path, "WDOFUT", DIA)
    assert list(px) == [5000.5, 5001.0]                    # id 7 = a edicao
    assert len(carregar_precos(tmp_path, "WDOFUT", "2026-01-01")[0]) == 0


def test_cli_ponta_a_ponta(tmp_path: Path) -> None:
    tl, pl, ts, ps = _par(np.random.default_rng(4), atraso_ms=300)
    _gravar(tmp_path, "WDOFUT", tl, pl)
    _gravar(tmp_path, "WINFUT", ts, ps)
    r = CliRunner().invoke(app, ["leadlag", "--raw", str(tmp_path),
                                 "--lags-ms", "100,300,1000"])
    assert r.exit_code == 0, r.output
    assert "[1/1] 2026-09-22" in r.output and "TOTAL 1 pregoes" in r.output
    linha = next(x for x in r.output.splitlines() if x.strip().startswith("300ms"))
    # assimetria e' DIFERENCA de correlacoes (-c(300) + c(-300)): pode passar de 1
    assert "1/1 dias" in linha and float(linha.split()[1]) > 0.9


def test_cli_recusa_lag_fora_da_grade(tmp_path: Path) -> None:
    tl, pl, ts, ps = _par(np.random.default_rng(5), atraso_ms=300)
    _gravar(tmp_path, "WDOFUT", tl, pl)
    _gravar(tmp_path, "WINFUT", ts, ps)
    r = CliRunner().invoke(app, ["leadlag", "--raw", str(tmp_path), "--lags-ms", "75"])
    assert r.exit_code != 0


@pytest.mark.parametrize("sentido,esperado", [(-1, 1), (1, -1)])
def test_assimetria_respeita_o_sentido(sentido: int, esperado: int) -> None:
    c: dict[int, float | None] = {-100: 0.0, 0: -0.5, 100: -0.2}
    a = assimetria(c, sentido)
    assert np.sign(a[100]) == esperado       # type: ignore[arg-type]
