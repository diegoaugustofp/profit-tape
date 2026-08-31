"""
Testes do pre-voo de drawdown (2026-08-30): registro rico de operacao no
gestor + decomposicao do drawdown maximo. Numeros conferidos A MAO antes
dos testes existirem.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from profittape.research.decomposicao_drawdown import (
    _maior_sequencia_de_perdas,
    decompor_drawdown,
    decompor_trecho,
    drawdown_maximo,
    drawdowns,
)

# Serie A MAO: curva (com zero na frente) 0,100,50,20,40,-160,-150,150,110
# trecho 1: pico 100 (i=1) -> vale -160 (i=5): profundidade 260
# trecho 2: pico 150 (i=7) -> vale 110 (i=8): profundidade 40
PNL = np.array([100.0, -50.0, -30.0, 20.0, -200.0, 10.0, 300.0, -40.0])


def _ops() -> pd.DataFrame:
    return pd.DataFrame({
        "dia": [date(2026, 8, 1)] * 3 + [date(2026, 8, 2)] * 2 + [date(2026, 8, 3)] * 3,
        "seq_no_dia": [1, 2, 3, 1, 2, 1, 2, 3],
        "pnl_liquido": PNL,
    })


def test_drawdowns_confere_a_mao() -> None:
    ts = drawdowns(PNL, 3)
    assert len(ts) == 2
    assert ts[0].profundidade == 260.0 and ts[0].i_pico == 1 and ts[0].i_vale == 5
    assert ts[1].profundidade == 40.0 and ts[1].i_pico == 7 and ts[1].i_vale == 8
    assert drawdown_maximo(PNL) == 260.0


def test_drawdown_do_inicio_conta() -> None:
    """Pico no zero inicial: uma serie que so' cai tem drawdown = soma."""
    assert drawdown_maximo(np.array([-10.0, -20.0, -5.0])) == 35.0


def test_serie_so_sobe_nao_tem_drawdown() -> None:
    assert drawdowns(np.array([1.0, 2.0, 3.0]), 3) == []
    assert drawdown_maximo(np.array([1.0, 2.0])) == 0.0


def test_maior_sequencia_de_perdas() -> None:
    """[-50,-30] soma -80; [-200] soma -200 -> a maior em VALOR e' a de 1."""
    assert _maior_sequencia_de_perdas(np.array([-50.0, -30.0, 20.0, -200.0])) == (1, -200.0)
    assert _maior_sequencia_de_perdas(np.array([-10.0, -10.0, -10.0, 5.0, -25.0])) == (3, -30.0)
    assert _maior_sequencia_de_perdas(np.array([1.0, 2.0])) == (0, 0.0)


def test_decomposicao_do_trecho_confere_a_mao() -> None:
    """Trecho 1 cobre ops [-50,-30,+20,-200].
    3 piores: -200,-50,-30 = 280 -> 280/260 = 1.0769 (passa de 1: ha' um
    +20 no meio compensando). Pior dia: 02/08 = +20-200 = -180 -> 0.6923.
    Maior sequencia: [-200] -> 0.7692. Dominante = operacoes (>= 0.50)."""
    d = decompor_trecho(_ops(), drawdowns(PNL, 1)[0])
    assert d["parcela_operacoes"] == pytest.approx(280 / 260)
    assert d["parcela_dias"] == pytest.approx(180 / 260)
    assert d["parcela_sequencia"] == pytest.approx(200 / 260)
    assert d["fonte_dominante"] == "operacoes"
    assert d["pior_dia"] == date(2026, 8, 2)
    assert d["sequencia_tamanho"] == 1


def test_difuso_quando_nenhuma_parcela_chega_a_metade() -> None:
    """Muitas perdas pequenas em dias diferentes, sem sequencia longa."""
    pnl = np.array([100.0] + [-8.0, 3.0] * 20)
    dias = [date(2026, 8, 1)] + [date(2026, 8, 1 + (i // 2) % 20) for i in range(40)]
    ops = pd.DataFrame({"dia": dias, "seq_no_dia": range(len(pnl)), "pnl_liquido": pnl})
    d = decompor_trecho(ops, drawdowns(pnl, 1)[0])
    assert d["fonte_dominante"] == "difuso"


def test_ponta_a_ponta_gera_relatorio(tmp_path: Path) -> None:
    # 3 dias da serie conferida a mao + 3 dias de ganhos pequenos (nao
    # criam drawdown novo, so' satisfazem o minimo de 5 pregoes).
    ops = _ops()
    extra = pd.DataFrame({"dia": [date(2026, 8, 4), date(2026, 8, 5), date(2026, 8, 6)],
                          "seq_no_dia": [1, 1, 1], "pnl_liquido": [5.0, 5.0, 5.0]})
    ops = pd.concat([ops, extra], ignore_index=True)
    arq = tmp_path / "ops.parquet"
    ops.to_parquet(arq, index=False)
    r = decompor_drawdown(arq, tmp_path / "out", n_bootstrap=50)
    assert r["drawdown_maximo"] == 260.0
    assert r["calmar"] == pytest.approx((PNL.sum() + 15.0) / 260.0)
    assert len(r["trechos"]) == 2
    assert r["jackknife"]["minimo"] <= r["jackknife"]["maximo"]
    texto = Path(r["relatorio"]).read_text(encoding="utf-8")
    assert "NAO consome trial" in texto or "nao consome trial" in texto
    assert "**operacoes**" in texto


# ------------------------------------------ registro rico no gestor
def test_gestor_registra_operacao_detalhada() -> None:
    from profittape.ea.config import RiscoConfig
    from profittape.ea.risco import GestorDeRisco

    cfg = RiscoConfig()
    g = GestorDeRisco(cfg, custo_pontos=11.0)
    g.registrar_abertura(-1, 100.0, 10, horizonte=3)
    pnl = g.registrar_fechamento(90.0, 13, motivo="saida por tempo")
    assert pnl == pytest.approx(10.0 - 11.0)
    assert len(g.historico_detalhado) == 1
    op = g.historico_detalhado[0]
    assert op.lado == -1 and op.preco_entrada == 100.0 and op.preco_saida == 90.0
    assert op.bar_id_entrada == 10 and op.bar_id_saida == 13
    assert op.motivo == "saida por tempo"
    # os historicos antigos continuam iguais (retrocompatibilidade)
    assert g.historico_pnl == [pnl]
    assert g.historico_operacoes == [(-1, pnl)]


def test_recusa_populacao_de_um_pregao(tmp_path: Path) -> None:
    """Incidente 2026-08-31: 5 ops em 1 pregao -> parcelas 1,00 por
    tautologia. Agora recusa com dica de --raiz-raw."""
    ops = pd.DataFrame({"dia": [date(2026, 8, 27)] * 5, "seq_no_dia": range(1, 6),
                        "pnl_liquido": [599.0, 499.0, -56.0, -181.0, -206.0]})
    arq = tmp_path / "ops.parquet"
    ops.to_parquet(arq, index=False)
    with pytest.raises(SystemExit, match="populacao insuficiente"):
        decompor_drawdown(arq, tmp_path / "out", n_bootstrap=10)
