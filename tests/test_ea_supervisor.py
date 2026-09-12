"""
E5.0 — SupervisorDeRisco: calcula e AVISA, NUNCA impede.

A decisao do operador (2026-09-11) e' o que estes testes protegem:
capital e risco sao INFORMATIVOS. Se algum teste aqui algum dia exigir
um "nao pode", o desenho foi violado.
"""

from __future__ import annotations

import pytest

from profittape.ea.supervisor import (
    ExigenciaDeEA,
    SupervisorDeRisco,
    capital_recomendado_para,
)


def test_capital_recomendado_bate_com_o_default_historico() -> None:
    """Stop 500 pts, 1 contrato WIN (R$0,20/pt), risco 2% -> R$5.000,
    exatamente o default de RiscoConfig desde 2026-08-26. A formula e' a
    inversa de GestorDeRisco.stop_catastrofico_pontos."""
    assert capital_recomendado_para(500, 1, 0.20, 0.02) == 5000.0
    assert capital_recomendado_para(500, 2, 0.20, 0.02) == 10000.0   # dobra com o lote
    assert capital_recomendado_para(250, 1, 0.20, 0.02) == 2500.0    # metade do stop


def test_capital_recomendado_recusa_parametros_impossiveis() -> None:
    with pytest.raises(ValueError):
        capital_recomendado_para(500, 1, 0.20, 0.0)
    with pytest.raises(ValueError):
        capital_recomendado_para(500, 0, 0.20, 0.02)


def test_capital_abaixo_do_recomendado_AVISA_mas_nao_impede() -> None:
    """O coracao da decisao do operador: R$2.000 em conta com R$5.000
    recomendado gera ALERTA, e mais nada. Nao existe metodo que devolva
    'bloqueado' -- se existisse, este teste nao teria como falhar."""
    s = SupervisorDeRisco(capital_em_conta=2000.0)
    s.registrar(ExigenciaDeEA("z_agf_3", 5000.0, 1, "WINV26", "SUB-A"))
    alertas = s.avaliar()
    codigos = [a.codigo for a in alertas]
    assert "capital_abaixo_do_recomendado" in codigos
    assert s.cobertura == pytest.approx(0.4)
    # cobertura < 50% -> critico (mas ainda so' alerta)
    assert [a.nivel for a in alertas if a.codigo == "capital_abaixo_do_recomendado"] == ["critico"]
    assert "risco e' sempre do operador" in " ".join(a.mensagem for a in alertas) or \
           "decisao e risco do operador" in " ".join(a.mensagem for a in alertas)
    # o supervisor NAO tem como dizer nao: nenhum metodo devolve bool de permissao
    assert not hasattr(s, "pode_abrir")
    assert not hasattr(s, "bloqueado")


def test_capital_suficiente_vira_alerta_informativo() -> None:
    s = SupervisorDeRisco(capital_em_conta=12000.0)
    s.registrar(ExigenciaDeEA("a", 5000.0, 1, "WINV26", "SUB-A"))
    s.registrar(ExigenciaDeEA("b", 5000.0, 1, "WDOV26", "SUB-B"))
    alertas = s.avaliar()
    assert [a.codigo for a in alertas] == ["capital_suficiente"]
    assert alertas[0].nivel == "info"
    assert s.capital_recomendado_total == 10000.0
    assert s.contratos_totais == 2


def test_pouco_abaixo_e_atencao_muito_abaixo_e_critico() -> None:
    s = SupervisorDeRisco(capital_em_conta=4000.0)   # 80% de 5000
    s.registrar(ExigenciaDeEA("a", 5000.0, 1, "WINV26", "SUB-A"))
    assert [a.nivel for a in s.avaliar()] == ["atencao"]
    s2 = SupervisorDeRisco(capital_em_conta=1000.0)  # 20% de 5000
    s2.registrar(ExigenciaDeEA("a", 5000.0, 1, "WINV26", "SUB-A"))
    assert [a.nivel for a in s2.avaliar()] == ["critico"]


def test_registrar_e_idempotente_por_nome() -> None:
    """Montagem rodando duas vezes nao pode dobrar o capital exigido."""
    s = SupervisorDeRisco(capital_em_conta=5000.0)
    e = ExigenciaDeEA("a", 5000.0, 1, "WINV26", "SUB-A")
    s.registrar(e)
    s.registrar(e)
    s.registrar(ExigenciaDeEA("a", 5000.0, 1, "WINV26", "SUB-A"))
    assert s.capital_recomendado_total == 5000.0
    assert len(s.exigencias) == 1


def test_subconta_compartilhada_alerta_porque_volta_o_netting() -> None:
    """Dois EAs na mesma subconta anulam posicoes opostas -- exatamente o
    que a decisao de usar subcontas separadas (4.2) existe para evitar."""
    s = SupervisorDeRisco(capital_em_conta=999999.0)
    s.registrar(ExigenciaDeEA("a", 100.0, 1, "WINV26", "MESMA"))
    s.registrar(ExigenciaDeEA("b", 100.0, 1, "WINV26", "MESMA"))
    assert s.subcontas_duplicadas() == {"MESMA": ["a", "b"]}
    codigos = [a.codigo for a in s.avaliar()]
    assert "subconta_compartilhada" in codigos


def test_ea_sem_subconta_so_alerta_com_multi_ea() -> None:
    """Um EA sozinho sem subconta e' o caso atual (z_agf_3) -- normal.
    Dois EAs, um sem subconta, e' problema."""
    s1 = SupervisorDeRisco(capital_em_conta=99999.0)
    s1.registrar(ExigenciaDeEA("sozinho", 100.0, 1, "WINV26", None))
    assert "ea_sem_subconta" not in [a.codigo for a in s1.avaliar()]

    s2 = SupervisorDeRisco(capital_em_conta=99999.0)
    s2.registrar(ExigenciaDeEA("a", 100.0, 1, "WINV26", None))
    s2.registrar(ExigenciaDeEA("b", 100.0, 1, "WINV26", "SUB-B"))
    assert "ea_sem_subconta" in [a.codigo for a in s2.avaliar()]


def test_sem_eas_registrados_nao_alerta_nada() -> None:
    s = SupervisorDeRisco(capital_em_conta=0.0)
    assert s.avaliar() == []
    assert s.cobertura == float("inf")


def test_logar_nao_levanta_e_devolve_alertas() -> None:
    """`logar()` roda no caminho de montagem do record -- nao pode
    derrubar o processo por causa de um alerta."""
    s = SupervisorDeRisco(capital_em_conta=1.0)
    s.registrar(ExigenciaDeEA("a", 5000.0, 1, "WINV26", "SUB-A"))
    alertas = s.logar()
    assert [a.codigo for a in alertas] == ["capital_abaixo_do_recomendado"]


def test_resumo_tem_os_numeros_para_o_operador_decidir() -> None:
    s = SupervisorDeRisco(capital_em_conta=3000.0)
    s.registrar(ExigenciaDeEA("z_agf_3", 5000.0, 1, "WINV26", "SUB-A"))
    r = s.resumo()
    assert r["eas"] == 1
    assert r["capital_recomendado_total"] == 5000.0
    assert r["cobertura_pct"] == 60.0
    assert r["por_ea"]["z_agf_3"]["subconta"] == "SUB-A"  # type: ignore[index]
