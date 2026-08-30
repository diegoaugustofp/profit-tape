"""Testes do comparador NTSL <-> profit-tape."""

from __future__ import annotations

import pandas as pd
import pytest

from profittape.tools.ntsl_equivalencia import (
    CAMPOS,
    _data_easylanguage,
    carregar_log,
    comparar,
)

S = 1_000_000_000


def _linha(data: int, hora: int, z: float = 2.5, imb: float = 0.4,
           desloc: float = -0.2) -> str:
    # ordem: data|hora|hora_bolsa|O|H|L|C|agrC|agrV|imb|desloc|absdir|med|dp|z
    return (f"ABSDIR|{data}|{hora}|{hora}|100|110|95|97|700|300|"
            f"{imb}|{desloc}|{imb - desloc}|0.1|0.2|{z}")


def test_data_easylanguage() -> None:
    """1AnoMesDia: o ano vem deslocado de 1900 (manual, secao 16.15)."""
    assert _data_easylanguage(1260824) == (2026, 8, 24)
    assert _data_easylanguage(1260101) == (2026, 1, 1)
    assert _data_easylanguage(991231) == (1999, 12, 31)


def test_parser_ignora_lixo_e_conta_malformadas(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """
    O console do Profit mistura mensagens de outras fontes. Exigir arquivo
    limpo so' transferiria o trabalho de limpeza para o operador.
    """
    arq = tmp_path / "console.txt"
    arq.write_text("\n".join([
        "mensagem qualquer do Profit",
        "12:00:01  " + _linha(1260824, 1000),      # com prefixo de horario
        _linha(1260824, 1005),
        "ABSDIR|so|tres|campos",                    # malformada
        "",
    ]), encoding="utf-8")

    df, diag = carregar_log(arq)
    assert diag["linhas_com_prefixo"] == 3
    assert diag["malformadas"] == 1
    assert diag["barras"] == 2
    assert list(df.columns) == CAMPOS


def test_parser_deduplica_mas_reporta(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """
    O manual avisa que candles passados podem ser reprocessados. Deduplicar
    e' correto; esconder quantas houve, nao.
    """
    arq = tmp_path / "console.txt"
    arq.write_text("\n".join([_linha(1260824, 1000)] * 3
                             + [_linha(1260824, 1005)]), encoding="utf-8")
    _df, diag = carregar_log(arq)
    assert diag["duplicadas"] == 2
    assert diag["barras"] == 2


def test_arquivo_sem_nenhuma_linha_valida(tmp_path) -> None:  # type: ignore[no-untyped-def]
    arq = tmp_path / "vazio.txt"
    arq.write_text("nada aqui\noutra linha\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        carregar_log(arq)


def _parquet_py(tmp_path, hora_utc: int = 13) -> object:  # type: ignore[no-untyped-def]
    """
    Barra de 5m em 24/08/2026. 13:00 UTC = 10:00 em Sao Paulo, que e' o
    horario que o NTSL registraria.
    """
    inicio = pd.Timestamp("2026-08-24", tz="UTC").value + hora_utc * 3600 * S
    df = pd.DataFrame({
        # ts_open e' o primeiro TRADE, alguns segundos depois da fronteira
        # do balde — o comparador tem que truncar ao periodo para casar.
        "ts_open": [inicio + 3 * S, inicio + 300 * S + 12 * S],
        "open": [100.0, 100.0], "high": [110.0, 110.0],
        "low": [95.0, 95.0], "close": [97.0, 97.0],
        "imbalance": [0.4, 0.4], "desloc_norm": [-0.2, -0.2],
        "absorcao_dir": [0.6, 0.6], "z_absorcao_dir": [2.5, 1.0],
    })
    arq = tmp_path / "features.parquet"
    df.to_parquet(arq, index=False)
    return arq


def test_casa_pela_fronteira_do_balde(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """
    ts_open e' o primeiro negocio, nao a fronteira. Sem truncar ao periodo,
    uma barra cujo primeiro negocio caisse no minuto seguinte nao casaria.
    """
    arq_log = tmp_path / "console.txt"
    arq_log.write_text("\n".join([_linha(1260824, 1000, z=2.5),
                                  _linha(1260824, 1005, z=1.0)]),
                       encoding="utf-8")
    r = comparar(arq_log, _parquet_py(tmp_path), segundos=300)  # type: ignore[arg-type]
    assert r["barras_casadas"] == 2
    tabela = r["tabela"].set_index("campo")
    assert tabela.loc["z", "frac_iguais"] == 1.0
    assert tabela.loc["imbalance", "frac_iguais"] == 1.0


def test_divergencia_aparece_no_campo_certo(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """
    O caso REAL previsto: o OHLC do grafico inclui RLP, o do profit-tape
    nao. `desloc_norm` diverge e `imbalance` bate — e a saida tem que
    mostrar exatamente isso, para a causa ser diagnosticada em vez de
    suposta.
    """
    arq_log = tmp_path / "console.txt"
    arq_log.write_text("\n".join([
        _linha(1260824, 1000, z=2.5, imb=0.4, desloc=-0.5),   # desloc difere
        _linha(1260824, 1005, z=1.0, imb=0.4, desloc=-0.2),
    ]), encoding="utf-8")
    r = comparar(arq_log, _parquet_py(tmp_path), segundos=300)  # type: ignore[arg-type]
    tabela = r["tabela"].set_index("campo")
    assert tabela.loc["imbalance", "frac_iguais"] == 1.0
    assert tabela.loc["desloc_norm", "frac_iguais"] == 0.5
    assert tabela.loc["desloc_norm", "dif_max"] == pytest.approx(0.3)


def test_nenhuma_barra_casa_nao_explode(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Fuso errado deve dar zero casadas, nao exception."""
    arq_log = tmp_path / "console.txt"
    arq_log.write_text(_linha(1260824, 700), encoding="utf-8")
    r = comparar(arq_log, _parquet_py(tmp_path), segundos=300)  # type: ignore[arg-type]
    assert r["barras_casadas"] == 0
    assert r["tabela"].empty
