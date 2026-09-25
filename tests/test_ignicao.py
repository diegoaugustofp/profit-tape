"""Ignicoes: conferencia a mao, MFE/MAE, barreira, classes do WDO, Wilson,
controle NEGATIVO (passeio sem momento) e CLI ponta a ponta."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from typer.testing import CliRunner

from profittape.cli import app
from profittape.research.ignicao import Tape, detectar, resumir, wilson
from profittape.research.leadlag import janela_do_dia

S = 1_000_000_000
DIA = "2026-09-24"
T0, _ = janela_do_dia(DIA, 915, 1700)
B = T0 + 600 * S
KW = dict(limiar_pts=150, janela_s=60, refratario_s=1800, conf_pts=1.0,
          horizontes_s=[300, 900, 1800], alvo_pts=100, stop_pts=100,
          inicio_hhmm=915, fim_hhmm=1700)


def _tape(ts: list[int], px: list[float], tipo: list[int] | None = None,
          q: list[int] | None = None) -> Tape:
    n = len(ts)
    return Tape(np.array(ts, dtype=np.int64), np.array(px, dtype=float),
                np.array(q or [1] * n, dtype=np.int64), np.array(tipo or [0] * n, dtype=np.int64))


def _wdo(delta: float) -> Tape:
    return _tape([B - 100 * S, B + 30 * S], [5180.0, 5180.0 + delta])


def test_caso_conferido_a_mao() -> None:
    win = _tape([B - 100 * S, B, B + 10 * S, B + 30 * S, B + 31 * S, B + 120 * S,
                 B + 400 * S, B + 1000 * S, B + 2000 * S],
                [188000, 188000, 188050, 188150, 188160, 188200, 188040, 188100, 188300],
                tipo=[0, 2, 2, 2, 2, 3, 3, 3, 2], q=[1, 10, 10, 10, 5, 1, 1, 1, 1])
    ev = detectar(win, _wdo(-1.5), DIA, **KW)  # type: ignore[arg-type]
    e = ev[0]
    assert (e.hora_brt, e.direcao, e.mov_pts, e.preco) == ("09:25:30", 1, 150.0, 188150.0)
    assert (e.classe, e.wdo_mov_pts, e.agressao) == ("confirma", -1.5, 1.0)
    assert e.ret == {300: 50.0, 900: -110.0, 1800: -50.0}
    assert (e.mfe, e.mae, e.barreira) == (50.0, -110.0, "stop")
    # segunda so' depois do refratario, sem horizontes (tape acaba antes)
    assert len(ev) == 2 and ev[1].ret == {} and ev[1].barreira == "nenhuma"


def test_mfe_nao_negativo_e_mae_nao_positivo() -> None:
    """Regressao: com um ponto so' depois da deteccao, contra, o MFE saia -200."""
    win = _tape([B - 100 * S, B, B + 30 * S, B + 60 * S],
                [188000, 188000, 188150, 187950])
    e = detectar(win, _wdo(0.0), DIA, **KW)[0]  # type: ignore[arg-type]
    assert e.mfe == 0.0 and e.mae == -200.0 and e.barreira == "stop"


def test_continuacao_toca_o_alvo_e_queda_e_simetrica() -> None:
    sobe = _tape([B - 100 * S, B, B + 30 * S, B + 90 * S], [188000, 188000, 188150, 188260])
    assert detectar(sobe, _wdo(-1.0), DIA, **KW)[0].barreira == "alvo"  # type: ignore[arg-type]
    cai = _tape([B - 100 * S, B, B + 30 * S, B + 90 * S], [188000, 188000, 187850, 187740])
    e = detectar(cai, _wdo(+1.0), DIA, **KW)[0]  # type: ignore[arg-type]
    assert (e.direcao, e.classe, e.barreira, e.mfe) == (-1, "confirma", "alvo", 110.0)


def test_classes_do_confirmador() -> None:
    win = _tape([B - 100 * S, B, B + 30 * S], [188000, 188000, 188150])
    assert detectar(win, _wdo(+1.0), DIA, **KW)[0].classe == "contra"   # type: ignore[arg-type]
    assert detectar(win, _wdo(-0.5), DIA, **KW)[0].classe == "neutro"   # type: ignore[arg-type]
    assert detectar(win, _tape([], []), DIA, **KW)[0].classe == "sem_wdo"  # type: ignore[arg-type]


def test_wilson() -> None:
    assert wilson(50, 100) == (0.404, 0.596)
    assert wilson(0, 0) is None


def test_controle_negativo_passeio_sem_momento() -> None:
    """O caso que o verificador DEVE reprovar: sem momento, p_alvo ~ 0,5."""
    rng = np.random.default_rng(7)
    n = 7 * 3600 * 5                              # 7 h, um negocio a cada 200 ms
    ts = T0 + np.arange(n, dtype=np.int64) * (S // 5)
    px = 188000 + np.cumsum(rng.choice([-5, 0, 5], size=n, p=[0.3, 0.4, 0.3]))
    win = Tape(ts, px.astype(float), np.ones(n, np.int64), np.zeros(n, np.int64))
    kw = dict(KW, limiar_pts=40, refratario_s=300, horizontes_s=[60, 300],
              alvo_pts=40, stop_pts=40)
    ev = detectar(win, _tape([], []), DIA, **kw)  # type: ignore[arg-type]
    b = resumir(ev, [60, 300], 1)["todos"]["barreira"]
    assert b["decididos"] > 50
    assert 0.35 < b["p_alvo"] < 0.65


def _gravar(raiz: Path, sym: str, ts: list[int], px: list[float]) -> None:
    pasta = raiz / "trade" / f"dt={DIA}" / f"sym={sym}"
    pasta.mkdir(parents=True)
    pd.DataFrame({"ts_ns": ts, "trade_id": range(len(ts)), "price": px,
                  "quantidade": [1] * len(ts), "trade_type": [2] * len(ts)}
                 ).to_parquet(pasta / "part-0000.parquet")


def test_cli_ponta_a_ponta(tmp_path: Path) -> None:
    _gravar(tmp_path, "WINFUT", [B - 100 * S, B, B + 30 * S, B + 90 * S],
            [188000, 188000, 188150, 188260])
    _gravar(tmp_path, "WDOFUT", [B - 100 * S, B + 30 * S], [5180.0, 5179.0])
    r = CliRunner().invoke(app, ["ignicao", "--raw", str(tmp_path),
                                 "--saida", str(tmp_path / "out")])
    assert r.exit_code == 0, r.output
    assert "[1/1] 2026-09-24  ignicoes=1" in r.output and "empate p_alvo = 0.545" in r.output
    assert "09:25:30  +150 pts  confirma" in r.output
    df = pd.read_csv(tmp_path / "out" / "ignicao_eventos.csv")
    assert list(df["barreira"]) == ["alvo"] and list(df["classe"]) == ["confirma"]


# ================================================================ v3.67
from profittape.research.ignicao import (  # noqa: E402
    amplitude_mediana,
    candidatos,
    maximo_possivel,
)

CKW = dict(janela_s=60, refratario_s=1800, inicio_hhmm=915, fim_hhmm=1700)


def test_teto_de_eventos_por_dia_conferido_a_mao() -> None:
    # 09:16 a 17:00 = 27.840 s; 27.840 // 1.800 = 15, +1 = 16
    assert maximo_possivel(1800, 60, 915, 1700) == 16.0


def test_candidatos_sao_cegos_ao_que_vem_depois() -> None:
    """Truncar o tape logo depois de cada deteccao nao muda nada: a contagem
    do --so-taxa nao depende do desfecho."""
    rng = np.random.default_rng(11)
    n = 7 * 3600 * 5
    ts = T0 + np.arange(n, dtype=np.int64) * (S // 5)
    px = (188000 + np.cumsum(rng.choice([-5, 0, 5], size=n, p=[0.3, 0.4, 0.3]))).astype(float)
    win = Tape(ts, px, np.ones(n, np.int64), np.zeros(n, np.int64))
    c = candidatos(win, DIA, limiar_pts=40, **CKW)  # type: ignore[arg-type]
    assert len(c) > 5
    corte = c[-1][0] + 1
    trunc = Tape(ts[:corte], px[:corte], win.qtd[:corte], win.tipo[:corte])
    assert candidatos(trunc, DIA, limiar_pts=40, **CKW) == c  # type: ignore[arg-type]
    # limiar maior nunca gera MAIS eventos
    assert len(candidatos(win, DIA, limiar_pts=80, **CKW)) <= len(c)  # type: ignore[arg-type]


def test_amplitude_mediana_conferida_a_mao() -> None:
    b0 = T0
    win = _tape([b0 + 10 * S, b0 + 20 * S, b0 + 1810 * S, b0 + 1820 * S,
                 b0 + 3610 * S, b0 + 3620 * S],
                [188000, 188300, 188000, 188100, 188000, 188500])
    # blocos de 30 min: amplitudes 300, 100, 500 -> mediana 300
    assert amplitude_mediana(win, DIA, 1800, 915, 1700) == 300.0


def test_barreira_s_mais_longa_decide_o_que_30min_nao_decidia() -> None:
    win = _tape([B - 100 * S, B, B + 30 * S, B + 2500 * S],
                [188000, 188000, 188150, 188500])
    kw = dict(KW, alvo_pts=300, stop_pts=300)
    assert detectar(win, _wdo(-1.0), DIA, **kw)[0].barreira == "nenhuma"  # type: ignore[arg-type]
    e = detectar(win, _wdo(-1.0), DIA, barreira_s=3600, **kw)[0]  # type: ignore[arg-type]
    assert e.barreira == "alvo"
    assert e.mfe == 0.0          # MFE/MAE continuam no maior horizonte (30 min)


def test_cli_so_taxa_nao_mostra_resultado(tmp_path: Path) -> None:
    _gravar(tmp_path, "WINFUT", [B - 100 * S, B, B + 30 * S, B + 90 * S],
            [188000, 188000, 188150, 188260])
    r = CliRunner().invoke(app, ["ignicao", "--raw", str(tmp_path), "--so-taxa", "100,150,500",
                                 "--saida", str(tmp_path / "out")])
    assert r.exit_code == 0, r.output
    assert "TAXA DE IGNICOES" in r.output and "teto 16.0/dia" in r.output
    assert "100:1  150:1  500:0" in r.output
    for proibido in ("p_alvo", "ret_", "mfe", "alvo=", "stop="):
        assert proibido not in r.output
    assert not (tmp_path / "out").exists()      # nem CSV


def test_cli_so_taxa_aplica_a_regra_declarada(tmp_path: Path) -> None:
    """Regra (HISTORICO 2026-09-25): limiar = menor com por_dia <= taxa-alvo;
    barreira = fracao x amplitude mediana. Conferido a mao: contagens
    100:1 150:1 500:0 -> 100; um bloco de 30 min de 188000 a 188260 ->
    amplitude 260 -> barreira 130."""
    _gravar(tmp_path, "WINFUT", [B - 100 * S, B, B + 30 * S, B + 90 * S],
            [188000, 188000, 188150, 188260])
    r = CliRunner().invoke(app, ["ignicao", "--raw", str(tmp_path),
                                 "--so-taxa", "100,150,500"])
    assert r.exit_code == 0, r.output
    assert "amplitude normal em 30 min" in r.output and "260 pts" in r.output
    assert "-> limiar 100 pts, barreira +-130 pts" in r.output
    assert "--limiar-pts 100 --alvo-pts 130 --stop-pts 130 --barreira-s 1800" in r.output
    r = CliRunner().invoke(app, ["ignicao", "--raw", str(tmp_path),
                                 "--so-taxa", "100,150", "--taxa-alvo", "0.5"])
    assert r.exit_code == 0 and "acrescente limiares MAIORES" in r.output
