"""E4 x gemeo simulado: custo de execucao e a checagem do simulador."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from profittape.research import e4_comparar as ec

NS = 1_000_000_000


def _op(hhmm: int, lado: str, fills: dict[str, tuple[float, float, str]],
        desfecho: str = "stop") -> dict[str, Any]:
    """fills: papel -> (nivel, fill, lado_da_ordem)."""
    return {"candidato": {"hhmm": hhmm, "lado": lado}, "desfecho": desfecho,
            "ordens": {p: {"papel": p, "lado": ld, "nivel": n, "fill": f,
                           "latencia_aceite_ms": 20.0}
                       for p, (n, f, ld) in fills.items()}}


def _escrever(d: Path, dia: str, ops: list[dict[str, Any]]) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / f"sinais_123_{dia}.jsonl").write_text(
        "\n".join(json.dumps(o) for o in ops) + "\n", encoding="utf-8")


def _tape(tmp: Path, dia: str, precos: list[float], t0: int, passo_ns: int = NS // 10,
          sym: str = "WINFUT") -> Path:
    curated = tmp / "curated"
    (curated / "trade" / f"dt={dia}" / f"sym={sym}").mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"ts_ns": [t0 + i * passo_ns for i in range(len(precos))],
                       "price": precos, "quantidade": 1, "trade_type": 2})
    import profittape.research.e4_comparar as m
    m._carregar_dia = lambda pasta, s: df       # type: ignore[assignment]
    return curated


def test_custo_de_execucao_por_ordem_e_pareamento(tmp_path: Path) -> None:
    dia = "2026-09-22"
    # venda: entrada 186700 executada 186700 (sem custo); stop de COMPRA
    # 187670 executado 187690 -> 20 pts PIOR
    _escrever(tmp_path / "real", dia, [_op(1115, "venda",
              {"entrada": (186700.0, 186700.0, "venda"),
               "stop": (187670.0, 187690.0, "compra")})])
    _escrever(tmp_path / "sim", dia, [_op(1115, "venda",
              {"entrada": (186700.0, 186700.0, "venda"),
               "stop": (187670.0, 187670.0, "compra")})])
    r = ec.comparar(tmp_path / "real", tmp_path / "sim")
    assert r["pareadas"] == 1 and r["ordens_com_fill"] == 2
    custos = {x["papel"]: x["custo_pts"] for x in r["linhas"]}
    assert custos == {"entrada": 0.0, "stop": 20.0}
    assert r["custo_total_pts"] == 20.0
    assert all(x["pareado"] for x in r["linhas"])


def test_operacao_real_sem_par_no_simulado_aparece_como_nao_pareada(tmp_path: Path) -> None:
    dia = "2026-09-22"
    _escrever(tmp_path / "real", dia, [_op(1115, "venda",
              {"entrada": (186700.0, 186700.0, "venda")})])
    _escrever(tmp_path / "sim", dia, [])
    r = ec.comparar(tmp_path / "real", tmp_path / "sim")
    assert r["pareadas"] == 0 and r["linhas"][0]["pareado"] is False
    assert r["linhas"][0]["fill_simulado"] is None


def test_simulador_IDEAL_e_detectado(tmp_path: Path) -> None:
    """O mercado negociou 40 pts ACIMA do stop de compra na janela, e a demo
    executou no nivel: preenchimento idealizado."""
    dia = "2026-09-22"
    t0 = int(pd.Timestamp(f"{dia} 14:00", tz="UTC").value)
    curated = _tape(tmp_path, dia, [187600.0, 187670.0, 187700.0, 187710.0, 187650.0], t0)
    _escrever(tmp_path / "real", dia, [_op(1115, "venda",
              {"stop": (187670.0, 187670.0, "compra")})])
    _escrever(tmp_path / "sim", dia, [_op(1115, "venda",
              {"stop": (187670.0, 187670.0, "compra")})])
    r = ec.comparar(tmp_path / "real", tmp_path / "sim", curated)
    s = r["simulador"]
    assert s["ordens_conferidas_no_tape"] == 1
    assert s["com_mercado_PIOR_na_janela"] == 1 and s["dessas_executadas_no_NIVEL"] == 1
    assert r["linhas"][0]["pior_que_o_nivel_pts"] == 40.0


def test_demo_que_reproduz_a_fila_NAO_e_contada_como_ideal(tmp_path: Path) -> None:
    dia = "2026-09-22"
    t0 = int(pd.Timestamp(f"{dia} 14:00", tz="UTC").value)
    curated = _tape(tmp_path, dia, [187600.0, 187670.0, 187700.0, 187710.0], t0)
    _escrever(tmp_path / "real", dia, [_op(1115, "venda",
              {"stop": (187670.0, 187700.0, "compra")})])   # executou PIOR
    _escrever(tmp_path / "sim", dia, [_op(1115, "venda",
              {"stop": (187670.0, 187670.0, "compra")})])
    r = ec.comparar(tmp_path / "real", tmp_path / "sim", curated)
    assert r["simulador"]["com_mercado_PIOR_na_janela"] == 1
    assert r["simulador"]["dessas_executadas_no_NIVEL"] == 0
    assert r["linhas"][0]["custo_pts"] == 30.0


def test_mercado_que_NAO_foi_pior_nao_acusa_nada(tmp_path: Path) -> None:
    """Executou no nivel e o mercado nao negociou pior: nao diz nada sobre o
    simulador -- e' so' mercado calmo."""
    dia = "2026-09-22"
    t0 = int(pd.Timestamp(f"{dia} 14:00", tz="UTC").value)
    curated = _tape(tmp_path, dia, [187600.0, 187670.0, 187660.0, 187600.0], t0)
    _escrever(tmp_path / "real", dia, [_op(1115, "venda",
              {"stop": (187670.0, 187670.0, "compra")})])
    _escrever(tmp_path / "sim", dia, [])
    r = ec.comparar(tmp_path / "real", tmp_path / "sim", curated)
    assert r["simulador"]["com_mercado_PIOR_na_janela"] == 0
    assert r["linhas"][0]["pior_que_o_nivel_pts"] == 0.0


def test_janela_limita_o_que_conta_como_pior(tmp_path: Path) -> None:
    """O pior preco 10 s depois do cruzamento nao e' slippage da ordem."""
    dia = "2026-09-22"
    t0 = int(pd.Timestamp(f"{dia} 14:00", tz="UTC").value)
    precos = [187670.0] + [187660.0] * 40 + [188000.0]
    curated = _tape(tmp_path, dia, precos, t0)
    _escrever(tmp_path / "real", dia, [_op(1115, "venda",
              {"stop": (187670.0, 187670.0, "compra")})])
    _escrever(tmp_path / "sim", dia, [])
    r = ec.comparar(tmp_path / "real", tmp_path / "sim", curated, janela_s=2.0)
    assert r["linhas"][0]["pior_que_o_nivel_pts"] == 0.0


def test_sem_operacao_real_recusa(tmp_path: Path) -> None:
    (tmp_path / "real").mkdir()
    with pytest.raises(SystemExit, match="nenhuma operacao real"):
        ec.comparar(tmp_path / "real", tmp_path / "sim")
