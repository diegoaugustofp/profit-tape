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
    # agentes: muitos, como no mercado real (dezenas de corretoras)
    ag_c = rng.integers(1, 40, n)
    ag_v = rng.integers(1, 40, n)
    df = pd.DataFrame({"ts_ns": ts, "price": price, "quantidade": qtd, "trade_type": tipo,
                       "agente_comprador": ag_c, "agente_vendedor": ag_v})
    if com_iceberg:
        extras = []
        for k in range(6):                               # 6 niveis defendidos
            nivel = float(price[n // 8 * (k + 1)])
            base = int(ts[n // 8 * (k + 1)])
            for j in range(30):                          # 30 recargas de 37 contratos
                # SEMPRE o mesmo agente PASSIVO (99): e' a assinatura de iceberg.
                # Agressor comprador (2) -> passivo e' o vendedor.
                extras.append({"ts_ns": base + j * 20 * NS, "price": nivel,
                               "quantidade": 37.0, "trade_type": 2,
                               "agente_comprador": int(rng.integers(1, 40)),
                               "agente_vendedor": 99})
        df = pd.concat([df, pd.DataFrame(extras)], ignore_index=True)
    return df.sort_values("ts_ns").reset_index(drop=True)


def test_sem_iceberg_a_razao_fica_perto_de_um(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dia = dt.date(2026, 8, 3)
    c = _curated(monkeypatch, tmp_path, _fluxo(60_000, 1, False, dia), dia)
    r = ib.medir_dia(c, "WINFUT", dia)["sem_rlp"]
    # sem iceberg plantado, com o agente na definicao, quase nao ha' corrida
    # -- nem no observado nem no baseline. A razao suavizada fica perto de 1.
    for n, razao in r["razao_por_limiar"].items():
        assert 0.3 < razao < 3.0, (n, razao)


def test_iceberg_plantado_aparece_contra_o_baseline(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dia = dt.date(2026, 8, 4)
    c = _curated(monkeypatch, tmp_path, _fluxo(60_000, 2, True, dia), dia)
    r = ib.medir_dia(c, "WINFUT", dia)["sem_rlp"]
    # com o AGENTE PASSIVO na definicao (v2) o ruido some: o baseline vai a
    # ZERO e sobram exatamente os 6 icebergs plantados. Medido: obs
    # {5:9, 10:6, 20:6, 30:6}, baseline {0,0,0,0}.
    assert r["por_limiar"]["30"] >= 6
    assert r["baseline_embaralhado"]["por_limiar"]["30"] == 0
    assert r["razao_por_limiar"]["30"] > 3.0, r["razao_por_limiar"]
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
    passivo = np.array([9, 9, 9], dtype=np.int64)
    r = ib._resumo_corridas(ts, price, qtd, passivo, janela_s=30.0, n_minimo=2)
    assert r["corridas"] == 2 and r["tamanho_max"] == 2


def test_agente_passivo_e_o_contrario_do_agressor() -> None:
    comprador = np.array([10, 20, 30], dtype=np.int64)
    vendedor = np.array([11, 21, 31], dtype=np.int64)
    tipo = np.array([2, 3, 13], dtype=np.int64)          # agride comprador / vendedor / RLP
    p = ib.agente_passivo(comprador, vendedor, tipo)
    assert p.tolist() == [11, 20, 0]


def test_agente_diferente_quebra_a_corrida() -> None:
    """Mesma quantidade e mesmo preco, mas cada negocio com um passivo
    diferente: NAO e' iceberg -- e' o pregao normal (foi o que o Times &
    Trades mostrou nas 8 maiores corridas de 17/09)."""
    ts = (np.arange(20) * NS).astype(np.int64)
    price = np.full(20, 100.0)
    qtd = np.full(20, 1.0)
    passivo = np.arange(1, 21, dtype=np.int64)
    r = ib._resumo_corridas(ts, price, qtd, passivo, janela_s=30.0, n_minimo=5)
    assert r["corridas"] == 20 and r["tamanho_max"] == 1 and r["corridas_relevantes"] == 0


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
    assert a["por_limiar"]["30"]["razao_p50"] > 1.0


def test_sem_dado_recusa(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="nenhum dia"):
        ib.descrever(tmp_path, "WINFUT", [dt.date(2026, 8, 3)])
