"""
Testes do diagnostico por barra.

Categoria `features`: descreve a forma, nunca toca em retorno.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from profittape.research import absorcao_barra as ab
from profittape.research.absorcao_inspecao import (
    _folga,
    inspecionar_dia,
    resumir_falhas,
)


def _barras(n: int = 130) -> pd.DataFrame:
    rng = np.random.default_rng(4)
    preco = 140_000.0
    linhas = []
    for _ in range(n):
        amp = rng.gamma(4.0, 40.0)
        o = preco
        c = o + rng.normal(0, amp / 3)
        h = max(o, c) + rng.gamma(2.0, amp / 6)
        low = min(o, c) - rng.gamma(2.0, amp / 6)
        linhas.append({"dia": pd.Timestamp("2026-08-27").date(),
                       "ts_close": 0, "open": o, "high": h, "low": low,
                       "close": c, "vol_agr": (h - low) * rng.gamma(20.0, 5.0)})
        preco = c
    b = pd.DataFrame(linhas)
    a = b["high"] - b["low"]
    b["desloc_norm"] = ((b["close"] - b["open"]) / a).where(a > 0, 0.0)
    b["hora"] = [f"{9 + i // 12:02d}:{(i % 12) * 5:02d}" for i in range(n)]
    return b


def test_folga_distingue_quase_de_longe() -> None:
    """
    O numero e' o que torna a inspecao util: falhar por 0,01 sugere corte
    apertado; falhar por 0,60 sugere que a barra nao e' o que se procura.
    Sem a folga, as duas parecem iguais.
    """
    assert _folga(0.26, 0.25, maior_e_melhor=False) == "FALHA por 0.010"
    assert _folga(0.85, 0.25, maior_e_melhor=False) == "FALHA por 0.600"
    assert _folga(1.20, 0.50, maior_e_melhor=True) == "passa por 0.700"


def test_folga_com_dado_ausente_nao_mente() -> None:
    """No aquecimento o z nao existe; dizer 'FALHA' ali seria falso."""
    assert _folga(float("nan"), 0.25, maior_e_melhor=False) == "sem dado"


def test_inspecao_mostra_uma_linha_por_barra_com_os_quatro_vereditos() -> None:
    t = inspecionar_dia(_barras(), "2026-08-27")
    assert len(t) == 130
    for col in ("resultado", "alcance", "esforco", "contexto",
                "EVENTO", "MARCOU"):
        assert col in t.columns


def test_marcou_exige_evento_E_contexto() -> None:
    t = inspecionar_dia(_barras(), "2026-08-27")
    assert not (t["MARCOU"] & ~t["EVENTO"]).any(), (
        "MARCOU sem EVENTO e' impossivel: a conjuncao inclui as tres "
        "condicoes")


def test_dia_inexistente_lista_os_disponiveis() -> None:
    """A mensagem tem que dizer o que existe, nao so' o que falta."""
    with pytest.raises(SystemExit, match="dias disponiveis"):
        inspecionar_dia(_barras(), "2020-01-01")


def test_resumo_conta_falhas_por_condicao() -> None:
    """
    Se uma condicao sozinha reprova quase tudo, ela define o evento na
    pratica e as outras estao decorativas -- exatamente o defeito do
    `absorcao_dir`, onde o `desloc_norm` dominava a subtracao.
    """
    t = inspecionar_dia(_barras(), "2026-08-27")
    r = resumir_falhas(t)
    assert r["barras"] == 130
    assert r["marcaram"] == int(t["MARCOU"].sum())
    for k in ("falhou_resultado", "falhou_alcance", "falhou_esforco",
              "falhou_contexto"):
        assert 0 <= r[k] <= r["barras"]


def test_a_inspecao_usa_os_MESMOS_cortes_congelados() -> None:
    """
    Inspecionar com corte diferente do estimador mostraria outra coisa e
    daria a impressao de erro onde nao ha'.
    """
    t = inspecionar_dia(_barras(), "2026-08-27")
    marcadas = t[t["MARCOU"]]
    assert (marcadas["desloc_norm"].abs() <= ab.MAX_DESLOC_NORM).all()
    assert (marcadas["z_amp"] >= ab.MIN_Z_AMPLITUDE).all()
    assert (marcadas["z_vol"] >= ab.MIN_Z_VOL_AGR).all()
    assert (marcadas["mov6"].abs() >= ab.K_CONTEXTO).all()
