"""
Testes do EAService via o nucleo puro (processar_trade_bruto) — sem DLL.
O loop real (rodar) e' fino de proposito: conexao espelhada do contas.py
ja' validado, e o nucleo e' o que decide dinheiro.
"""

from __future__ import annotations

import numpy as np
import pytest

from profittape.ea.config import EAConfig, SinalConfig
from profittape.ea.execucao import ExecutorDeOrdens
from profittape.ea.service import EAService, _TradeBruto

_SINAL = SinalConfig(feature="z_agf_3", horizonte=3, agent_id=3,
                     threshold_entrada=1.0, direcao="contrarian")


def _config(**kw) -> EAConfig:
    padrao = dict(symbol="WINFUT", volume_barra=50, janela_z=6,
                  sinais=[_SINAL], tamanho_posicao=1, dry_run=True)
    padrao.update(kw)
    return EAConfig(**padrao)


def _alimentar(svc: EAService, n_trades: int, seed: int = 3,
               agente_dominante_compra: int | None = None) -> list:
    """Gera trades sinteticos; se agente_dominante_compra for dado, esse
    agente compra em ~90% dos trades (fluxo desequilibrado -> z alto)."""
    rng = np.random.default_rng(seed)
    decisoes = []
    for i in range(n_trades):
        if agente_dominante_compra is not None and rng.random() < 0.9:
            comp = agente_dominante_compra
            vend = 999
        else:
            comp = int(rng.choice([3, 85, 999]))
            vend = int(rng.choice([3, 85, 999]))
        decisoes += svc.processar_trade_bruto(_TradeBruto(
            ts_ns=i * 10**8, price=140000.0 + float(rng.integers(-50, 50)),
            quantidade=int(rng.integers(1, 8)), trade_type=int(rng.choice([2, 3])),
            agente_comprador=comp, agente_vendedor=vend))
    return decisoes


def test_fluxo_completo_produz_barras_e_decisoes() -> None:
    svc = EAService(_config())
    decisoes = _alimentar(svc, 4000)
    assert svc.stats.trades == 4000
    assert svc.stats.barras > 10
    # depois do aquecimento da janela, alguma decisao (mesmo NADA) aparece
    assert len(decisoes) > 0
    assert sum(svc.stats.decisoes.values()) == len(decisoes)


def test_aquecimento_da_janela_nao_gera_decisao() -> None:
    """Primeiras barras tem z=NaN (min_periods) — decidir() nao e' chamado."""
    svc = EAService(_config(janela_z=10))
    rng = np.random.default_rng(5)
    barras_antes_da_primeira_decisao = 0
    for i in range(2000):
        decisoes = svc.processar_trade_bruto(_TradeBruto(
            ts_ns=i * 10**8, price=140000.0, quantidade=int(rng.integers(1, 6)),
            trade_type=int(rng.choice([2, 3])),
            agente_comprador=int(rng.choice([3, 85])),
            agente_vendedor=int(rng.choice([3, 85]))))
        if not decisoes and svc.stats.barras > 0:
            barras_antes_da_primeira_decisao = svc.stats.barras
        if decisoes:
            break
    assert barras_antes_da_primeira_decisao >= 4   # min_periods = 10//2 = 5


def test_posicao_simulada_zera_antes_de_inverter() -> None:
    """Regra do decisao.py respeitada na simulacao: nunca pula de comprado
    para vendido sem passar por zero."""
    svc = EAService(_config())
    posicoes_vistas = set()
    ultima = 0
    for i in range(30000):
        rng_fase = 3 if i < 15000 else 999   # XP compra forte, depois neutro
        svc.processar_trade_bruto(_TradeBruto(
            ts_ns=i * 10**8, price=140000.0, quantidade=2,
            trade_type=2 if i % 2 == 0 else 3,
            agente_comprador=rng_fase, agente_vendedor=85))
        pos = svc.stats.posicao_simulada
        if pos != ultima:
            # transicao valida: nunca de +x direto para -x
            assert not (ultima > 0 and pos < 0), "inverteu sem zerar"
            assert not (ultima < 0 and pos > 0), "inverteu sem zerar"
            ultima = pos
        posicoes_vistas.add(pos)
    assert len(posicoes_vistas) >= 2   # a posicao de fato variou no teste


def test_encerrar_dia_zera_posicao_aberta() -> None:
    svc = EAService(_config())
    svc.stats.posicao_simulada = 2
    d = svc.encerrar_dia()
    assert d is not None
    assert svc.stats.posicao_simulada == 0
    assert "encerramento" in d.motivo


def test_encerrar_dia_sem_posicao_nao_faz_nada() -> None:
    svc = EAService(_config())
    d = svc.encerrar_dia()
    assert d is None
    assert svc.stats.decisoes == {}


def test_dry_run_false_sem_executor_recusa_na_construcao() -> None:
    with pytest.raises(RuntimeError, match="ExecutorDeOrdens"):
        EAService(_config(dry_run=False))


def test_dry_run_false_com_executor_envia_de_verdade() -> None:
    from tests.test_ea_execucao import _FakeDllOrdens, _rot

    dll = _FakeDllOrdens()
    ex = ExecutorDeOrdens(dll, _rot(), "WINFUT", "F", 1)
    svc = EAService(_config(dry_run=False), executor=ex)
    _alimentar(svc, 30000, agente_dominante_compra=3)
    n_ordens = sum(v for k, v in svc.stats.decisoes.items() if k != "nada")
    assert n_ordens > 0, "fluxo desequilibrado do XP deveria ter gerado ordem"
    assert len(dll.chamadas) == n_ordens   # cada decisao nao-NADA virou chamada real


def test_rodar_replay_le_parquet_e_alimenta_o_mesmo_nucleo(tmp_path) -> None:
    """
    Resposta a um problema real de licenciamento (2026-08-27): duas
    conexoes MarketLogin simultaneas (record + ea) colidem -- a chave de
    ativacao so' permite uma sessao por vez (confirmado na pratica, erro
    identico ao de MarketLogin+LoginCompleto). rodar_replay reusa o MESMO
    nucleo (processar_trade_bruto) mas le trades JA' CAPTURADOS do
    parquet, sem nenhuma conexao -- portanto sem conflito possivel.
    """
    import pandas as pd

    rng = np.random.default_rng(11)
    n = 5000
    df = pd.DataFrame({
        "ts_ns": np.arange(n, dtype=np.int64) * 10**8,
        "ts_recv_ns": np.arange(n, dtype=np.int64) * 10**8,
        "symbol": "WINFUT", "exchange": "F", "trade_id": np.arange(n),
        "price": 140000.0 + np.cumsum(rng.choice([-5.0, 0.0, 5.0], n)),
        "volume_financeiro": 0.0,
        "quantidade": rng.integers(1, 8, n),
        "agente_comprador": rng.choice([3, 85], n),
        "agente_vendedor": rng.choice([3, 85], n),
        "trade_type": rng.choice([2, 3], n),
        "is_edit": False,
    })
    raiz = tmp_path / "trade" / "dt=2026-08-27" / "sym=WINFUT"
    raiz.mkdir(parents=True)
    df.to_parquet(raiz / "part-0000.parquet", index=False)

    svc = _config_svc = EAService(_config())
    svc.rodar_replay(raiz)

    assert svc.stats.trades == n
    assert svc.stats.barras > 10
    assert svc.stats.posicao_simulada == 0   # encerrar_dia zerou no final


def test_rodar_replay_sem_parquet_falha_com_mensagem_clara(tmp_path) -> None:
    svc = EAService(_config())
    with pytest.raises(SystemExit, match="nenhum parquet"):
        svc.rodar_replay(tmp_path / "vazio")
