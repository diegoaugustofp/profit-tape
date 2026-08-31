"""Testes do comparador NTSL <-> profit-tape."""

from __future__ import annotations

import numpy as np
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
    # data|hora|hora_bolsa|O|H|L|C|vol_tot|vol_agr|agrC|agrV|imb|desloc|
    # absdir|media|desvio|z
    return (f"ABSDIR|{data}|{hora}|{hora}|100|110|95|97|1200|1000|700|300|"
            f"{imb}|{desloc}|{imb - desloc}|0.1|0.2|{z}|0.0")


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


def test_numero_no_formato_do_profit(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """
    O Profit imprime "157.722,86300000" — separador de milhar E virgula
    decimal. Trocar so' a virgula produziria "157.722.86300000" -> NaN,
    e como o comparador ignora NaN o campo sumiria da tabela em vez de
    acusar erro. Caso real do dump de 2026-08-30.
    """
    arq = tmp_path / "console.txt"
    arq.write_text(
        "ABSDIR|1250716|1410|1410|157.722,86300000|158.116,51890000|"
        "157.699,70680000|157.908,11280000|250.000,00|198.891,00|"
        "116.514,00|82.377,00|0,17163673|0,44444444|-0,27280772|"
        "0,00|0,00|0,00|0,00\n",
        encoding="utf-8")
    df, diag = carregar_log(arq)
    assert diag["barras"] == 1
    assert df["open"].iloc[0] == pytest.approx(157722.863)
    assert df["agr_compra"].iloc[0] == pytest.approx(116514.0)
    assert df["vol_total"].iloc[0] == pytest.approx(250000.0)
    # e a aritmetica do proprio Profit fecha nesse numero
    assert df["absorcao_dir"].iloc[0] == pytest.approx(
        df["imbalance"].iloc[0] - df["desloc_norm"].iloc[0], abs=1e-7)


def test_deteccao_de_formato_numerico() -> None:
    """
    Os dois erros possiveis sao SILENCIOSOS, por isso a deteccao:
    assumir pt-BR faria "2.5" virar 25 (numero valido, resultado errado);
    assumir en-US faria "157.722,863" virar NaN, e o comparador ignora
    NaN — o campo sumiria da tabela em vez de acusar.
    """
    import pandas as pd

    from profittape.tools.ntsl_equivalencia import _numero_ptbr

    s = pd.Series(["157.722,86300000", "2.5", "0,17163673", "-1", "0"])
    r = _numero_ptbr(s)
    assert r.iloc[0] == pytest.approx(157722.863)
    assert r.iloc[1] == pytest.approx(2.5)
    assert r.iloc[2] == pytest.approx(0.17163673)
    assert r.iloc[3] == -1.0
    assert r.iloc[4] == 0.0


def test_erro_aponta_a_causa_real_quando_o_ntsl_esta_defasado(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """
    Caso real: o dump de 2026-08-30 tinha 15 campos e o parser esperava
    17. A mensagem antiga perguntava se `LogAtivo=1` — mandaria caçar o
    problema no lugar errado. Tem que dizer QUANTOS campos viu.
    """
    arq = tmp_path / "console.txt"
    arq.write_text("ABSDIR|1|2|3|4|5\nABSDIR|1|2|3|4|5\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        carregar_log(arq)
    msg = str(e.value)
    assert "[5]" in msg and str(len(CAMPOS)) in msg
    assert "desatualizado" in msg


def test_arquivo_inexistente_da_mensagem_util(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """40 linhas de traceback para um caminho errado nao ajudam ninguem."""
    with pytest.raises(SystemExit) as e:
        carregar_log(tmp_path / "nao_existe.txt")
    assert "nao achei" in str(e.value) and "acento" in str(e.value)


def _parquet_com_historico(tmp_path, n_barras: int = 200) -> object:  # type: ignore[no-untyped-def]
    """Parquet com bar_id comecando em 0, para exercitar o aviso de borda."""
    rng = np.random.default_rng(1)
    inicio = pd.Timestamp("2026-08-24", tz="UTC").value + 13 * 3600 * S
    df = pd.DataFrame({
        "bar_id": range(n_barras),
        "ts_open": [inicio + i * 300 * S + 3 * S for i in range(n_barras)],
        "open": 100.0, "high": 110.0, "low": 95.0, "close": 97.0,
        "imbalance": 0.4,
        "desloc_norm": rng.normal(-0.2, 0.05, n_barras),
        "absorcao_dir": 0.6,
        "z_absorcao_dir": rng.normal(0, 1, n_barras),
    })
    arq = tmp_path / "features.parquet"
    df.to_parquet(arq, index=False)
    return arq


def test_avisa_quando_o_z_cai_na_borda_do_parquet(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """
    Caso real (2026-08-30): a sobreposição caiu em 24/07, o PRIMEIRO dia
    do parquet. Ali o z do Python normaliza contra uma janela mais curta
    que a do gráfico — divergência não indica erro de implementação.
    Sem o aviso, seria lida como bug.
    """
    inicio = pd.Timestamp("2026-08-24", tz="UTC") + pd.Timedelta(hours=13)
    linhas = []
    for i in range(10):  # primeiras barras => dentro da janela de 50
        t = (inicio + pd.Timedelta(minutes=5 * i)).tz_convert("America/Sao_Paulo")
        linhas.append(_linha(1260824, t.hour * 100 + t.minute))
    arq_log = tmp_path / "console.txt"
    arq_log.write_text("\n".join(linhas), encoding="utf-8")

    r = comparar(arq_log, _parquet_com_historico(tmp_path),  # type: ignore[arg-type]
                 segundos=300, janela_z=50)
    assert r["barras_casadas"] > 0
    assert r["z_na_borda"]["z_comparavel"] is False
    assert "NAO indica erro de implementacao" in r["z_na_borda"]["aviso"]


def test_atribuicao_decompoe_numerador_e_denominador(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """
    Duas explicacoes foram refutadas por este diagnostico antes desta:
    (1) o erro cresceria com o VOLUME de RLP -- correlacao deu -0,12;
    (2) o erro viria de um print TOCAR um extremo -- mas 79 de 80 barras
        tinham extremos identicos e o erro continuava la.

    Se o denominador bate, a diferenca esta no NUMERADOR: `open` e
    `close` sao o primeiro e o ultimo negocio, e um RLP dentro da faixa
    muda um deles sem mexer em maxima nem minima.

    Aqui: 1/3 das barras so' com numerador diferente, 1/3 so' com
    denominador, 1/3 sem diferenca. A decomposicao tem que separar as
    tres.
    """
    inicio = pd.Timestamp("2026-08-24", tz="UTC") + pd.Timedelta(hours=13)
    n = 45
    py = pd.DataFrame({
        "bar_id": range(200, 200 + n),
        "ts_open": [inicio.value + i * 300 * S + 3 * S for i in range(n)],
        "open": 100.0, "high": 155.0, "low": 100.0, "close": 120.0,
        "imbalance": 0.4, "desloc_norm": 20.0 / 55.0,
        "absorcao_dir": 0.4 - 20.0 / 55.0, "z_absorcao_dir": 1.0,
    })
    arq_py = tmp_path / "features.parquet"
    py.to_parquet(arq_py, index=False)

    linhas = []
    for i in range(n):
        t_ = (inicio + pd.Timedelta(minutes=5 * i)).tz_convert("America/Sao_Paulo")
        hhmm = t_.hour * 100 + t_.minute
        caso = i % 3
        close = 125.0 if caso == 0 else 120.0     # numerador difere
        high = 160.0 if caso == 1 else 155.0      # denominador difere
        desloc = (close - 100.0) / (high - 100.0)
        linhas.append(
            f"ABSDIR|1260824|{hhmm}|{hhmm}|100|{high}|100|{close}"
            f"|1000|720|700|300|0.4|{desloc}|{0.4 - desloc}|0.1|0.2|1.0|0.0")
    arq_log = tmp_path / "console.txt"
    arq_log.write_text("\n".join(linhas), encoding="utf-8")

    a = comparar(arq_log, arq_py, segundos=300)["atribuicao_rlp"]
    assert a["barras_so_numerador_difere"] == 15
    assert a["barras_so_denominador_difere"] == 15
    assert a["barras_nada_difere"] == 15
    assert a["erro_mediano_nada_difere"] == pytest.approx(0.0, abs=1e-9)
    assert a["tick_estimado"] == pytest.approx(5.0)


def test_separa_open_de_close_no_numerador(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """
    A decomposicao mostrou que o numerador `(close - open)` e' o culpado
    (46 de 80 barras, exatamente 1 tick). Falta saber QUAL ponta.

    Se o primeiro/ultimo negocio da barra e' de um tipo que um lado
    inclui e o outro nao, as duas pontas divergem em taxas parecidas. Se
    so' o fechamento diverge, a causa e' outra — fronteira de barra, que
    afeta preferencialmente o ultimo negocio.
    """
    inicio = pd.Timestamp("2026-08-24", tz="UTC") + pd.Timedelta(hours=13)
    n = 40
    py = pd.DataFrame({
        "bar_id": range(300, 300 + n),
        "ts_open": [inicio.value + i * 300 * S + 3 * S for i in range(n)],
        "open": 100.0, "high": 155.0, "low": 100.0, "close": 120.0,
        "imbalance": 0.4, "desloc_norm": 20.0 / 55.0,
        "absorcao_dir": 0.4 - 20.0 / 55.0, "z_absorcao_dir": 1.0,
    })
    arq_py = tmp_path / "features.parquet"
    py.to_parquet(arq_py, index=False)

    linhas = []
    for i in range(n):
        t_ = (inicio + pd.Timedelta(minutes=5 * i)).tz_convert("America/Sao_Paulo")
        hhmm = t_.hour * 100 + t_.minute
        op = 105.0 if i % 4 == 0 else 100.0     # 10 barras: so' open
        cl = 125.0 if i % 4 == 1 else 120.0     # 10 barras: so' close
        desloc = (cl - op) / 55.0
        linhas.append(
            f"ABSDIR|1260824|{hhmm}|{hhmm}|{op}|155|100|{cl}"
            f"|1000|720|700|300|0.4|{desloc}|{0.4 - desloc}|0.1|0.2|1.0|0.0")
    arq_log = tmp_path / "console.txt"
    arq_log.write_text("\n".join(linhas), encoding="utf-8")

    a = comparar(arq_log, arq_py, segundos=300)["atribuicao_rlp"]
    assert a["barras_so_open"] == 10
    assert a["barras_so_close"] == 10
    assert a["barras_open_e_close"] == 0
    assert a["dif_open_mediana_ticks"] == pytest.approx(1.0)


def test_k_por_pregao_lida_com_rolagem(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """
    Caso real (28/07-21/08/2026): a serie continua trocou de contrato no
    meio da amostra e o fator de ajuste saltou de 1,02048 para 1,0.

    Um k global vira media dos dois regimes e desloca open/close em ~2%
    — que num numerador tipico vale ~1 tick, indistinguivel do efeito
    que se quer medir. A versao global reportou "1,0 tick" de diferenca
    mediana e "682 ticks" no diagnostico de pontas: os dois artefatos.

    Aqui o dado e' IDENTICO nos dois lados; so' o fator muda de dia. Com
    k por pregao o erro tem que ser zero.
    """
    linhas, registros, bar = [], [], 0
    for dia, k in (("1260810", 1.02048), ("1260812", 1.0)):
        base = pd.Timestamp(f"2026-08-{dia[-2:]}", tz="UTC") + pd.Timedelta(hours=13)
        for i in range(30):
            t_ = (base + pd.Timedelta(minutes=5 * i)).tz_convert("America/Sao_Paulo")
            hhmm = t_.hour * 100 + t_.minute
            o, h, low, c = 100000.0, 100150.0, 99950.0, 100100.0
            registros.append({
                "bar_id": bar, "ts_open": base.value + i * 300 * S + 3 * S,
                "open": o, "high": h, "low": low, "close": c,
                "imbalance": 0.4, "desloc_norm": (c - o) / (h - low),
                "absorcao_dir": 0.4 - (c - o) / (h - low),
                "z_absorcao_dir": 1.0,
            })
            bar += 1
            linhas.append(
                f"ABSDIR|{dia}|{hhmm}|{hhmm}|{o * k}|{h * k}|{low * k}|{c * k}"
                f"|1000|720|700|300|0.4|{(c - o) / (h - low)}"
                f"|{0.4 - (c - o) / (h - low)}|0.1|0.2|1.0|0.0")

    arq_py = tmp_path / "features.parquet"
    pd.DataFrame(registros).to_parquet(arq_py, index=False)
    arq_log = tmp_path / "console.txt"
    arq_log.write_text("\n".join(linhas), encoding="utf-8")

    a = comparar(arq_log, arq_py, segundos=300)["atribuicao_rlp"]
    assert a["k_distintos"] == 2, "tem que detectar os dois regimes"
    assert a["barras_nada_difere"] == 60, "com k por pregao, nada difere"
    assert a["barras_so_open"] == 0 and a["barras_so_close"] == 0


def test_recusa_log_com_agressao_zerada(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """
    Caso real (2026-08-31): WINFUT 5m, periodo SOBREPOSTO a dois dumps
    que funcionaram no mesmo dia, e `AgressionVolBuy/Sell` deram ZERO nas
    2.001 barras — enquanto `QuantityVol(False, True)` deu 78.115 contra
    108.534 do total. O dado de agressao EXISTIA; uma API o entregou e a
    outra devolveu zero.

    Com `imbalance = 0`, `absorcao_dir` vira EXATAMENTE `-desloc_norm`:
    o indicador mede deslocamento com o sinal trocado, sem erro e sem
    aviso. As cores continuam pintando e o log continua saindo.

    A checagem compara as DUAS fontes de propósito: agressao zerada COM
    volume presente e' contradicao, nao ausencia de negocio (madrugada,
    leilao, feriado).
    """
    arq = tmp_path / "console.txt"
    arq.write_text("\n".join(
        f"ABSDIR|1260724|{900 + i}|{900 + i}|100|110|95|97"
        f"|250000|173825|0|0|0.0|0.6|-0.6|0.1|0.2|0.0|0.0" for i in range(10)),
        encoding="utf-8")
    with pytest.raises(SystemExit, match="AGRESSAO ZERADA"):
        carregar_log(arq)


def test_barra_sem_negocio_algum_nao_e_recusada(tmp_path) -> None:
    """
    Agressao zero COM volume zero e' barra sem negocio — normal, e nao
    pode disparar a guarda. Recusar aqui transformaria a protecao em
    falso positivo, e uma guarda que grita a toa acaba desligada.
    """
    arq = tmp_path / "console.txt"
    arq.write_text("\n".join(
        f"ABSDIR|1260724|{900 + i}|{900 + i}|100|100|100|100"
        f"|0|0|0|0|0.0|0.0|0.0|0.1|0.2|0.0|0.0" for i in range(10)),
        encoding="utf-8")
    _, diag = carregar_log(arq)
    assert diag["barras"] == 10
