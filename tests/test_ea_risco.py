"""
Testes do GestorDeRisco — as regras de ouro do framework do operador,
uma a uma. A mais importante: 3 perdas liquidas CONSECUTIVAS bloqueiam
novas entradas ate' o proximo dia, sem desbloqueio no mesmo processo.
"""

from __future__ import annotations

import pytest

from profittape.ea.config import EAConfig, RiscoConfig, SinalConfig
from profittape.ea.risco import GestorDeRisco
from profittape.ea.service import EAService, _TradeBruto

_CUSTO = 11.0


def _gestor(**kw) -> GestorDeRisco:
    return GestorDeRisco(RiscoConfig(**kw), custo_pontos=_CUSTO)


def test_stop_catastrofico_derivado_da_conta_do_operador() -> None:
    """2% de R$5.000 = R$100 = 500 pts a R$0,20/pt com 1 contrato."""
    r = RiscoConfig(capital=5000.0, risco_max_pct=0.02, valor_ponto_reais=0.20)
    assert r.stop_catastrofico_pontos == 500.0


def test_saida_por_tempo_no_horizonte_exato() -> None:
    g = _gestor()
    g.registrar_abertura(lado=+1, preco=140000.0, bar_id=10, horizonte=3)
    assert g.motivo_de_saida(11, 140000.0) is None
    assert g.motivo_de_saida(12, 140000.0) is None
    motivo = g.motivo_de_saida(13, 140000.0)      # 13-10 = 3 barras
    assert motivo is not None and "tempo" in motivo


def test_stop_catastrofico_tem_prioridade_sobre_tempo() -> None:
    g = _gestor()
    g.registrar_abertura(lado=+1, preco=140000.0, bar_id=0, horizonte=3)
    motivo = g.motivo_de_saida(1, 139500.0)       # 500 pts contra, comprado
    assert motivo is not None and "CATASTROFICO" in motivo


def test_stop_catastrofico_respeita_o_lado() -> None:
    g = _gestor()
    g.registrar_abertura(lado=-1, preco=140000.0, bar_id=0, horizonte=3)
    assert g.motivo_de_saida(1, 139500.0) is None        # a favor do vendido
    motivo = g.motivo_de_saida(1, 140500.0)              # 500 contra o vendido
    assert motivo is not None and "CATASTROFICO" in motivo


def test_circuit_breaker_apos_3_perdas_consecutivas() -> None:
    g = _gestor()
    for i in range(3):
        assert g.pode_abrir()
        g.registrar_abertura(+1, 140000.0, i * 10, 3)
        g.registrar_fechamento(140000.0)     # pnl bruto 0 - custo 11 = perda
    assert g.bloqueado
    assert not g.pode_abrir()
    with pytest.raises(RuntimeError, match="circuit breaker"):
        g.registrar_abertura(+1, 140000.0, 99, 3)


def test_ganho_liquido_zera_a_sequencia_de_perdas() -> None:
    """A regra e' CONSECUTIVAS: G-P-P-G-P-P nunca bloqueia."""
    g = _gestor()
    seq = [+50.0, -20.0, -20.0, +50.0, -20.0, -20.0]   # pnl bruto por operacao
    for i, bruto in enumerate(seq):
        assert g.pode_abrir(), f"bloqueou indevidamente na operacao {i}"
        g.registrar_abertura(+1, 140000.0, i * 10, 3)
        g.registrar_fechamento(140000.0 + bruto)
    assert not g.bloqueado
    assert g.perdas_consecutivas == 2


def test_pnl_liquido_desconta_o_custo() -> None:
    g = _gestor()
    g.registrar_abertura(+1, 140000.0, 0, 3)
    pnl = g.registrar_fechamento(140030.0)     # +30 bruto - 11 custo
    assert pnl == pytest.approx(19.0)
    assert g.perdas_consecutivas == 0          # ganho liquido


def test_ganho_bruto_menor_que_custo_conta_como_perda() -> None:
    """+5 pts bruto com custo 11 e' perda LIQUIDA — e' o que importa."""
    g = _gestor()
    g.registrar_abertura(+1, 140000.0, 0, 3)
    pnl = g.registrar_fechamento(140005.0)
    assert pnl == pytest.approx(-6.0)
    assert g.perdas_consecutivas == 1


def test_sem_piramide_por_construcao() -> None:
    g = _gestor()
    g.registrar_abertura(+1, 140000.0, 0, 3)
    with pytest.raises(RuntimeError, match="posicao ja aberta"):
        g.registrar_abertura(+1, 140100.0, 1, 3)


# ------------------------- integracao com o service (fluxo Rota A completo)

_SINAL = SinalConfig(feature="z_agf_3", horizonte=3, agent_id=3,
                     threshold_entrada=1.0, direcao="contrarian")


def _svc(**risco_kw) -> EAService:
    cfg = EAConfig(symbol="WINFUT", volume_barra=50, janela_z=6,
                   sinais=[_SINAL], tamanho_posicao=1, dry_run=True,
                   custo_pontos_estimado=_CUSTO,
                   risco=RiscoConfig(**risco_kw))
    return EAService(cfg)


def _trade(i: int, comp: int, preco: float = 140000.0) -> _TradeBruto:
    return _TradeBruto(ts_ns=i * 10**8, price=preco, quantidade=5,
                       trade_type=2, agente_comprador=comp, agente_vendedor=85)


def test_service_sai_por_tempo_apos_horizonte_barras() -> None:
    """Entra quando o fluxo do XP fica extremo; conta as barras entre a
    entrada e o ZERAR — tem que ser exatamente o horizonte (3)."""
    svc = _svc()
    bar_da_entrada = bar_do_zerar = None
    for i in range(30000):
        comp = 3 if (svc.stats.barras > 8 and bar_da_entrada is None) else 85
        decisoes = svc.processar_trade_bruto(_trade(i, comp))
        for d in decisoes:
            if d.acao.value in ("comprar", "vender") and bar_da_entrada is None:
                bar_da_entrada = svc.stats.barras
            elif d.acao.value == "zerar" and bar_da_entrada is not None:
                bar_do_zerar = svc.stats.barras
        if bar_do_zerar:
            break
    assert bar_da_entrada is not None and bar_do_zerar is not None
    assert bar_do_zerar - bar_da_entrada == 3


def test_service_bloqueia_entradas_apos_circuit_breaker() -> None:
    svc = _svc()
    svc.gestor.bloqueado = True
    svc.gestor.perdas_consecutivas = 3
    # alimenta fluxo extremo que NORMALMENTE geraria entrada
    for i in range(30000):
        decisoes = svc.processar_trade_bruto(_trade(i, comp=3))
        assert all(d.acao.value not in ("comprar", "vender") for d in decisoes)
    assert svc.stats.posicao_simulada == 0


def test_modo_diagnostico_ignora_circuit_breaker_mas_continua_calculando() -> None:
    """
    Pedido do operador (2026-08-27): entender o comportamento do dia
    INTEIRO em analise, sem o circuit breaker cortar cedo. 'bloqueado'
    continua sendo CALCULADO normalmente (para saber quando teria
    disparado em producao de verdade) -- so' nao impede nova entrada.
    """
    g = GestorDeRisco(RiscoConfig(), custo_pontos=_CUSTO,
                      ignorar_circuit_breaker=True)
    for i in range(6):   # 6 perdas seguidas -- bem alem do limiar de 3
        assert g.pode_abrir(), f"nao deveria bloquear em modo diagnostico ({i})"
        g.registrar_abertura(+1, 140000.0, i * 10, 3)
        g.registrar_fechamento(140000.0)   # perda (custo > 0, bruto = 0)
    assert g.bloqueado   # calculado normalmente
    assert g.perdas_consecutivas == 6   # nao trava em 3, continua contando
    assert len(g.historico_pnl) == 6


def test_historico_pnl_registra_cada_operacao() -> None:
    g = _gestor()
    valores_brutos = [10.0, -5.0, 20.0]
    for i, bruto in enumerate(valores_brutos):
        g.registrar_abertura(+1, 140000.0, i * 10, 3)
        g.registrar_fechamento(140000.0 + bruto)
    assert g.historico_pnl == pytest.approx([b - _CUSTO for b in valores_brutos])
