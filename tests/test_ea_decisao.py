"""
Testes de decisao.py — unica parte do EA com logica real (pura, sem I/O).
Cobre a regra central: contrarian opera no EXTREMO, zona neutra nao faz
nada, e troca de posicao passa por ZERAR antes de inverter.
"""

from __future__ import annotations

from profittape.ea.config import SinalConfig
from profittape.ea.decisao import Acao, decidir

_SINAL = SinalConfig(feature="z_agf_3", horizonte=3, agent_id=3,
                     threshold_entrada=1.0, direcao="contrarian")


def test_sinal_alto_sem_posicao_vende() -> None:
    d = decidir(_SINAL, valor_atual=1.5, posicao_atual=0)
    assert d.acao == Acao.VENDER


def test_sinal_baixo_sem_posicao_compra() -> None:
    d = decidir(_SINAL, valor_atual=-1.5, posicao_atual=0)
    assert d.acao == Acao.COMPRAR


def test_zona_neutra_nao_faz_nada() -> None:
    for v in (-0.99, 0.0, 0.5, 0.99):
        assert decidir(_SINAL, valor_atual=v, posicao_atual=0).acao == Acao.NADA


def test_no_limiar_exato_ja_conta_como_extremo() -> None:
    """Fronteira inclusiva: exatamente no threshold ja' e' sinal, nao zona morta."""
    assert decidir(_SINAL, valor_atual=1.0, posicao_atual=0).acao == Acao.VENDER
    assert decidir(_SINAL, valor_atual=-1.0, posicao_atual=0).acao == Acao.COMPRAR


def test_sinal_vira_contra_posicao_comprada_zera_nao_inverte_direto() -> None:
    """Nunca pula de comprado direto pra vendido -- zera primeiro."""
    d = decidir(_SINAL, valor_atual=1.5, posicao_atual=3)
    assert d.acao == Acao.ZERAR


def test_sinal_vira_contra_posicao_vendida_zera_nao_inverte_direto() -> None:
    d = decidir(_SINAL, valor_atual=-1.5, posicao_atual=-2)
    assert d.acao == Acao.ZERAR


def test_posicao_ja_alinhada_com_sinal_nao_faz_nada() -> None:
    """Ja' vendido e o sinal continua pedindo venda -- nao dobra posicao
    (tamanho fixo, sem piramidar; gestao de risco ainda nao existe)."""
    d = decidir(_SINAL, valor_atual=1.8, posicao_atual=-1)
    assert d.acao == Acao.NADA


def test_direcao_momentum_inverte_a_logica() -> None:
    sinal_momentum = SinalConfig(feature="z_teste", horizonte=1, agent_id=1,
                                 threshold_entrada=1.0, direcao="momentum")
    # momentum: sinal ALTO -> espera retorno POSITIVO -> compra (oposto do contrarian)
    assert decidir(sinal_momentum, valor_atual=1.5, posicao_atual=0).acao == Acao.COMPRAR
    assert decidir(sinal_momentum, valor_atual=-1.5, posicao_atual=0).acao == Acao.VENDER


def test_direcao_invalida_levanta() -> None:
    import pytest
    sinal_ruim = SinalConfig(feature="x", horizonte=1, agent_id=1,
                             threshold_entrada=1.0, direcao="lateral")
    with pytest.raises(ValueError, match="direcao desconhecida"):
        decidir(sinal_ruim, valor_atual=2.0, posicao_atual=0)


def test_execucao_dry_run_apenas_loga(capsys) -> None:
    from profittape.ea.execucao import executar

    d = decidir(_SINAL, valor_atual=1.5, posicao_atual=0)
    executar(d, dry_run=True)   # nao pode levantar nem falar com DLL nenhuma
    saida = capsys.readouterr().out
    assert "ea.decisao_dry_run" in saida


def test_execucao_real_recusa_ate_estar_implementada() -> None:
    """
    Protecao contra ativacao acidental: dry_run=False hoje SEMPRE levanta
    NotImplementedError -- nao existe caminho de codigo que envie ordem
    real ainda. Isso e' intencional ate' os pre-requisitos do
    docs/EA_ARQUITETURA.md serem cumpridos.
    """
    import pytest

    from profittape.ea.execucao import executar

    d = decidir(_SINAL, valor_atual=1.5, posicao_atual=0)
    with pytest.raises(NotImplementedError):
        executar(d, dry_run=False)


def test_roteamento_default_e_demo_e_recusa_sem_config() -> None:
    """
    Seguranca financeira: sem NENHUM .env configurado, pedir a conta demo
    (o caminho padrao) tem que RECUSAR explicitamente, nao inventar um
    IDAccount vazio que poderia ser mal-interpretado a jusante.
    """
    import pytest

    from profittape.ea.config import RoteamentoConfig

    r = RoteamentoConfig()
    with pytest.raises(SystemExit, match="ROTEAMENTO_ID_ACCOUNT_DEMO"):
        r.conta_para(usar_conta_real=False)


def test_roteamento_conta_real_exige_config_propria() -> None:
    """Ter a conta demo configurada NAO habilita a conta real por engano
    -- cada uma precisa estar explicitamente presente."""
    import pytest

    from profittape.ea.config import RoteamentoConfig

    r = RoteamentoConfig(id_account_demo="123")   # so' demo configurado
    with pytest.raises(SystemExit, match="ROTEAMENTO_ID_ACCOUNT_REAL"):
        r.conta_para(usar_conta_real=True)


def test_roteamento_com_as_duas_contas_configuradas_escolhe_certo() -> None:
    from profittape.ea.config import RoteamentoConfig

    r = RoteamentoConfig(id_account_demo="DEMO123", id_account_real="REAL456")
    assert r.conta_para(usar_conta_real=False) == "DEMO123"
    assert r.conta_para(usar_conta_real=True) == "REAL456"


def test_eaconfig_default_usar_conta_real_e_falso() -> None:
    """O default do EAConfig inteiro tem que ser demo -- ninguem deveria
    precisar lembrar de desligar 'conta real' explicitamente; e' o
    contrario, tem que LIGAR explicitamente."""
    from profittape.ea.config import EAConfig, SinalConfig

    cfg = EAConfig(
        symbol="WINFUT", volume_barra=120000, janela_z=50,
        sinais=[SinalConfig(feature="z_agf_3", horizonte=3, agent_id=3,
                            threshold_entrada=1.0, direcao="contrarian")],
    )
    assert cfg.usar_conta_real is False
    assert cfg.dry_run is True
