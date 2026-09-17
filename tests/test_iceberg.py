"""Iceberg / lote repetido, passo 1: a assinatura existe alem do ACASO?

Os testes plantam (ou nao) um iceberg num fluxo sintetico e exigem que a
razao contra o baseline EMBARALHADO separe os dois casos -- que e' a
medida que decide a linha inteira.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from profittape.research import iceberg as ib

NS = 1_000_000_000


def _curated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, trades: pd.DataFrame,
             dia: dt.date) -> Path:
    curated = tmp_path / "curated"
    (curated / "trade" / f"dt={dia.isoformat()}" / "sym=WINFUT").mkdir(parents=True,
                                                                      exist_ok=True)
    monkeypatch.setattr(ib, "_carregar_dia", lambda pasta, sym: trades)
    return curated


def _fluxo(n: int, seed: int, com_iceberg: bool, dia: dt.date) -> pd.DataFrame:
    """Passeio de precos com lotes pequenos (como o WIN). Com iceberg: em
    alguns niveis, 30 negocios de quantidade FIXA e incomum (37), espalhados
    no tempo, com o preco saindo e voltando ao nivel."""
    rng = np.random.default_rng(seed)
    t0 = int(pd.Timestamp(f"{dia} 12:00:00", tz="UTC").value)
    ts = np.sort(rng.integers(t0, t0 + 6 * 3600 * NS, n))
    price = 140000.0 + np.cumsum(rng.choice([-5.0, 0.0, 5.0], n))
    qtd = rng.choice([1, 2, 3, 5, 10], n, p=[0.45, 0.25, 0.15, 0.1, 0.05]).astype(float)
    tipo = np.full(n, 2)
    tipo[rng.random(n) < 0.25] = 13                      # RLP, como no WIN
    df = pd.DataFrame({"ts_ns": ts, "price": price, "quantidade": qtd, "trade_type": tipo})
    if com_iceberg:
        extras = []
        for k in range(6):                               # 6 niveis defendidos
            nivel = float(price[n // 8 * (k + 1)])
            base = int(ts[n // 8 * (k + 1)])
            for j in range(30):                          # 30 recargas de 37 contratos
                extras.append({"ts_ns": base + j * 20 * NS, "price": nivel,
                               "quantidade": 37.0, "trade_type": 2})
        df = pd.concat([df, pd.DataFrame(extras)], ignore_index=True)
    return df.sort_values("ts_ns").reset_index(drop=True)


def test_sem_iceberg_a_razao_fica_perto_de_um(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dia = dt.date(2026, 8, 3)
    c = _curated(monkeypatch, tmp_path, _fluxo(60_000, 1, False, dia), dia)
    r = ib.medir_dia(c, "WINFUT", dia)["sem_rlp"]
    # sem iceberg, a curva inteira tem que ficar perto do acaso
    for n, razao in r["razao_por_limiar"].items():
        if razao is not None:
            assert 0.5 < razao < 2.0, (n, razao)


def test_iceberg_plantado_aparece_contra_o_baseline(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dia = dt.date(2026, 8, 4)
    c = _curated(monkeypatch, tmp_path, _fluxo(60_000, 2, True, dia), dia)
    r = ib.medir_dia(c, "WINFUT", dia)["sem_rlp"]
    # o que SEPARA nao e' a contagem de corridas de 5 (o acaso produz
    # milhares, e a razao la' fica em 1,00): e' a CAUDA. Medido neste
    # fluxo: razao 0,999 / 1,03 / 1,05 / 2,75 para N = 5 / 10 / 20 / 30.
    assert r["razao_por_limiar"]["5"] < 1.2
    assert r["razao_por_limiar"]["30"] > 2.0, r["razao_por_limiar"]
    assert r["por_limiar"]["30"] > r["baseline_embaralhado"]["por_limiar"]["30"]
    assert r["recomposicao"]["avaliadas"] >= 6


def test_com_e_sem_rlp_sao_reportados_sempre(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dia = dt.date(2026, 8, 5)
    c = _curated(monkeypatch, tmp_path, _fluxo(40_000, 3, True, dia), dia)
    r = ib.medir_dia(c, "WINFUT", dia)
    assert set(r) >= {"com_rlp", "sem_rlp"}
    assert r["com_rlp"]["trades"] > r["sem_rlp"]["trades"]
    for nome in ("com_rlp", "sem_rlp"):
        assert "baseline_embaralhado" in r[nome] and "recomposicao" in r[nome]


def test_corridas_respeitam_a_janela() -> None:
    """Dois negocios iguais separados por mais que a janela sao corridas
    DIFERENTES -- senao 'iceberg' viraria 'o dia inteiro no mesmo preco'."""
    ts = np.array([0, 10 * NS, 300 * NS], dtype=np.int64)
    price = np.array([100.0, 100.0, 100.0])
    qtd = np.array([7.0, 7.0, 7.0])
    r = ib._resumo_corridas(ts, price, qtd, janela_s=30.0, n_minimo=2)
    assert r["corridas"] == 2 and r["tamanho_max"] == 2


def test_agregado_e_saida(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dia = dt.date(2026, 8, 6)
    c = _curated(monkeypatch, tmp_path, _fluxo(20_000, 4, True, dia), dia)
    r = ib.descrever(c, "WINFUT", [dia], saida=tmp_path / "s")
    assert (tmp_path / "s" / "iceberg.json").exists()
    a = r["agregado"]["sem_rlp"]
    assert a["dias"] == 1 and 0.0 <= a["fracao_do_volume_p50"] <= 1.0
    # com 20 k trades o baseline pode nao ter nenhuma corrida de 30 (razao
    # indefinida): o que importa e' o observado estar la'.
    assert a["por_limiar"]["30"]["observado_p50"] >= 6
    razao30 = a["por_limiar"]["30"]["razao_p50"]
    assert razao30 is None or razao30 > 1.0


def test_sem_dado_recusa(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="nenhum dia"):
        ib.descrever(tmp_path, "WINFUT", [dt.date(2026, 8, 3)])
