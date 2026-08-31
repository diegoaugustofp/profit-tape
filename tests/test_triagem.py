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


def test_reprova_esforco_por_razao_entre_partes_correlacionadas() -> None:
    """
    CASO REAL: registrada como "a direcao certa, porque e' ILIMITADA".
    Medido: corr(vol_agr, amplitude) = +0,892, e a razao ficou quase
    constante. Ilimitado NAO implica ter cauda.
    """
    rng = np.random.default_rng(12)
    amp = rng.gamma(9.0, 5.0, 2000)
    vol = 2100 * amp + rng.normal(0, 12_000, 2000)
    d = pd.DataFrame({"amplitude": amp, "vol_agr": vol,
                      "esforco": vol / amp,
                      "outra": rng.normal(size=2000)})
    r = triar(d["esforco"], d[["outra"]],
              numerador=d["vol_agr"], denominador=d["amplitude"])
    assert r["veredito"] == "REPROVA"
    assert any("RAZAO ENTRE PARTES" in m for m in r["motivos"])
    assert r["razao"]["correlacao_numerador_denominador"] > 0.7


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
    assert not d["risco_de_cancelamento"]


def test_nao_declarada_como_razao_nao_dispara_o_criterio() -> None:
    d = _diagnostico_de_razao(None, None)
    assert "situacao" in d and "risco_de_cancelamento" not in d


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
    assert r["veredito"] == "REPROVA"
    assert any("RAZAO ENTRE PARTES" in m for m in r["motivos"])
    assert r["expressao"] == "vol_agr / ((high - low) / 5)"


def test_expressao_invalida_lista_as_colunas(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A mensagem tem que dizer o que existe, nao so' o que falta."""
    import pytest

    from profittape.features.triagem import triar_parquet

    with pytest.raises(SystemExit, match="colunas disponiveis"):
        triar_parquet(_parquet_de_teste(tmp_path), "nao_existe")
