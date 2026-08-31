"""
Testes da triagem de features candidatas.

Os dois primeiros sao REGRESSAO DE CASOS REAIS: as duas formalizacoes
que morreram em 2026-08-30/31. Se a triagem nao reprovar essas duas, ela
nao serve para o que foi construida.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from profittape.features.triagem import (
    FRACAO_MINIMA_DA_NORMAL,
    LIMITE_REDUNDANCIA,
    _diagnostico_de_razao,
    _forma_da_cauda,
    triar,
)


def _absorcao_dir_sintetica(n: int = 2000) -> pd.DataFrame:
    """
    Reproduz a estrutura medida: `desloc_norm` com 4x o desvio de
    `imbalance`, os dois correlacionados +0,86, e `absorcao_dir` sendo a
    subtracao. Isso basta para a correlacao com `-desloc_norm` passar de
    0,95, como os dados reais (0,9883).
    """
    rng = np.random.default_rng(11)
    desloc = rng.normal(0, 0.49, n)
    imb = 0.86 * (0.1175 / 0.49) * desloc + rng.normal(
        0, 0.1175 * np.sqrt(1 - 0.86 ** 2), n)
    return pd.DataFrame({"imbalance": imb, "desloc_norm": desloc,
                         "absorcao_dir": imb - desloc})


def test_reprova_absorcao_dir_por_redundancia() -> None:
    """
    CASO REAL: gastou 12 trials e levou CONTRA nas 12 celulas. Depois
    medido: corr(absorcao_dir, -desloc_norm) = 0,9883 nos dados de
    24-31/08. Era `desloc_norm` renomeado, e a checagem custa uma linha.
    """
    d = _absorcao_dir_sintetica()
    r = triar(d["absorcao_dir"], d[["imbalance", "desloc_norm"]])
    assert r["veredito"] == "REPROVA"
    assert any("REDUNDANTE" in m for m in r["motivos"])
    pior = r["redundancia"][0]
    assert pior["feature"] == "desloc_norm"
    assert abs(pior["correlacao"]) >= LIMITE_REDUNDANCIA


def test_correlacao_entre_partes_sozinha_NAO_reprova() -> None:
    """
    CORRECAO DE UMA AFIRMACAO MINHA ERRADA (2026-08-31).

    Reprovei `esforco` por `corr(vol, amplitude) = +0,888`, dizendo que a
    razao seria "quase constante". Medido depois sobre 2.723 barras: ela
    tem **1,33x a cauda de uma normal** e vai de 290 a 5.198 contratos
    por tick — 18x entre extremos.

    Atenuar NAO e' anular. So' reprova quando a atenuacao de fato matou a
    cauda; um verificador que reprova bom candidato e' tao ruim quanto um
    que aprova ruim.
    """
    rng = np.random.default_rng(12)
    amp = rng.gamma(9.0, 5.0, 3000)
    vol = 2100 * amp + rng.normal(0, 12_000, 3000)
    razao = pd.Series(vol / amp)
    d = pd.DataFrame({"outra": rng.normal(size=3000)})

    r = triar(razao, d, numerador=pd.Series(vol), denominador=pd.Series(amp))
    assert r["razao"]["correlacao_numerador_denominador"] > 0.7
    assert r["razao"]["atenua_a_variacao"]
    if r["cauda"]["tem_cauda"]:
        assert not any("RAZAO ENTRE PARTES" in m for m in r["motivos"]), (
            "correlacao alta entre as partes nao pode reprovar sozinha")


def test_correlacao_entre_partes_nunca_reprova_sozinha() -> None:
    """
    Criterio REMOVIDO do veredito em 2026-08-31, e este teste guarda a
    razao para nao voltar por engano.

    Duas medicoes o derrubaram: (1) `esforco` tem corr +0,888 entre as
    partes E 1,33x a cauda de uma normal; (2) uma razao construida quase
    CONSTANTE de proposito (ruido de 0,2%) tambem passa no teste de
    cauda, porque o z-score e' INVARIANTE A ESCALA.

    O criterio media a coisa errada, e nenhum limiar conserta. Fica como
    diagnostico, sem peso de veredito.
    """
    rng = np.random.default_rng(31)
    den = rng.gamma(9.0, 5.0, 3000)
    num = 2100 * den * (1 + rng.normal(0, 0.002, 3000))
    outras = pd.DataFrame({"o": rng.normal(size=3000)})

    r = triar(pd.Series(num / den), outras,
              numerador=pd.Series(num), denominador=pd.Series(den))
    assert r["razao"]["atenua_a_variacao"], "o diagnostico continua sendo reportado"
    assert not any("RAZAO" in m for m in r["motivos"]), (
        "correlacao entre as partes nao pode figurar como motivo de reprova")


def test_sinal_negativo_conta_como_redundante() -> None:
    """
    O sinal engana: -0,988 parece "oposto, logo diferente", mas e' a
    mesma informacao trocada de sinal. Por isso a comparacao e' pelo
    MODULO.
    """
    rng = np.random.default_rng(13)
    x = pd.Series(rng.normal(size=500))
    d = pd.DataFrame({"existente": x})
    r = triar(-x, d)
    assert r["veredito"] == "REPROVA"
    assert r["redundancia"][0]["correlacao"] < -LIMITE_REDUNDANCIA


def test_cauda_e_medida_CONTRA_a_normal_e_nao_por_limiar_absoluto() -> None:
    """
    A primeira versao usava a razao p99/p50 do |z| com corte em 2,0, e
    ERRAVA OS DOIS CASOS REAIS: aprovava `absorcao_dir` (2,34x) e dava ao
    `esforco` MAIS cauda que uma normal (4,30x contra 3,85x). Razao entre
    dois quantis e' instavel e nao se compara a referencia nenhuma.
    """
    rng = np.random.default_rng(14)
    normal = _forma_da_cauda(pd.Series(rng.normal(size=4000)))
    pesada = _forma_da_cauda(pd.Series(rng.standard_t(3, size=4000)))
    # uniforme: sub-gaussiana, nenhuma observacao alem de 2,5 sd
    leve = _forma_da_cauda(pd.Series(rng.uniform(-1, 1, 4000)))

    assert normal["tem_cauda"] and pesada["tem_cauda"]
    assert not leve["tem_cauda"]
    assert leve["pct_acima_de_2_5_sd"] < (
        FRACAO_MINIMA_DA_NORMAL * normal["pct_esperado_sob_normal"])
    assert pesada["razao_com_a_normal"] > normal["razao_com_a_normal"]


def test_feature_boa_passa() -> None:
    """PASSA nao autoriza nada — so' significa que nao da' para descartar
    olhando a forma."""
    rng = np.random.default_rng(15)
    d = pd.DataFrame({"a": rng.normal(size=1500), "b": rng.normal(size=1500)})
    nova = pd.Series(rng.standard_t(4, size=1500))
    r = triar(nova, d)
    assert r["veredito"] == "PASSA"
    assert r["motivos"] == []


def test_razao_com_partes_independentes_nao_e_penalizada() -> None:
    rng = np.random.default_rng(16)
    num = pd.Series(rng.gamma(4, 2, 800))
    den = pd.Series(rng.gamma(4, 2, 800))
    d = _diagnostico_de_razao(num, den)
    assert not d["atenua_a_variacao"]


def test_nao_declarada_como_razao_nao_dispara_o_criterio() -> None:
    d = _diagnostico_de_razao(None, None)
    assert "situacao" in d and "atenua_a_variacao" not in d


def _parquet_de_teste(tmp_path, n: int = 1200):  # type: ignore[no-untyped-def]
    rng = np.random.default_rng(21)
    amp = rng.gamma(9.0, 5.0, n)
    df = pd.DataFrame({
        "high": 100_000 + amp * 5, "low": 100_000.0,
        "vol_agr": 2100 * amp + rng.normal(0, 12_000, n),
        "imbalance": rng.normal(0, 0.12, n),
        "desloc_norm": rng.normal(0, 0.49, n),
    })
    arq = tmp_path / "features.parquet"
    df.to_parquet(arq, index=False)
    return arq


def test_tria_candidata_DERIVADA_que_nao_esta_no_parquet(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """
    O caso de uso PRINCIPAL: triar candidata NOVA, que por definicao
    ainda nao foi gravada. A primeira versao so' aceitava coluna
    existente e falhava com "nao tem a coluna `esforco`" — inutil
    justamente para o que a triagem existe.
    """
    from profittape.features.triagem import triar_parquet

    r = triar_parquet(_parquet_de_teste(tmp_path), "esforco",
                      expr="vol_agr / ((high - low) / 5)",
                      numerador="vol_agr", denominador="(high - low) / 5")
    assert r["expressao"] == "vol_agr / ((high - low) / 5)"
    # o ponto do teste e' que a expressao E' AVALIADA, nao o veredito
    assert r["cauda"]["n"] > 1000
    assert r["razao"]["correlacao_numerador_denominador"] > 0.7


def test_expressao_invalida_lista_as_colunas(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A mensagem tem que dizer o que existe, nao so' o que falta."""
    import pytest

    from profittape.features.triagem import triar_parquet

    with pytest.raises(SystemExit, match="colunas disponiveis"):
        triar_parquet(_parquet_de_teste(tmp_path), "nao_existe")
