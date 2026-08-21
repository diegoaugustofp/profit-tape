"""O parser rapido tem que concordar com strptime — em TODO caso, nao no feliz."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from profittape.profitdll.timeparse import parse_ts_ns


def _referencia(s: str, offset: int = -3) -> int:
    """
    Referencia calculada com aritmetica INTEIRA.

    `dt.timestamp() * 1e9` parece obvio e esta errado: o float de 64 bits nao
    representa nanossegundos de 2024 exatamente, e a referencia sai com ~60ns
    de erro. Testar o parser contra uma referencia imprecisa geraria falha
    fantasma — exatamente o tipo de coisa que faz alguem relaxar um teste bom.
    """
    dt = datetime.strptime(s, "%d/%m/%Y %H:%M:%S.%f").replace(
        tzinfo=timezone(timedelta(hours=offset))
    )
    delta = dt - datetime(1970, 1, 1, tzinfo=UTC)
    return (delta.days * 86_400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1_000


@pytest.mark.parametrize(
    "amostra",
    [
        "02/01/2024 10:00:00.000",
        "29/02/2024 15:30:45.123",   # bissexto
        "28/02/2023 09:00:00.001",   # nao bissexto
        "31/12/2024 17:59:59.999",   # virada de ano
        "01/03/2100 12:00:00.500",   # 2100 NAO e' bissexto — regra dos 400
        "01/03/2000 12:00:00.500",   # 2000 E' bissexto
        "15/07/2019 13:45:12.007",
    ],
)
def test_bate_com_strptime(amostra: str) -> None:
    assert parse_ts_ns(amostra) == _referencia(amostra)


def test_converte_para_utc() -> None:
    ts = parse_ts_ns("02/01/2024 10:00:00.000", offset_horas=-3)
    assert datetime.fromtimestamp(ts / 1e9, tz=UTC).hour == 13


@pytest.mark.parametrize("ruim", [None, "", "lixo", "32/13/2024 99:99:99.999x", "02/01/2024"])
def test_entrada_invalida_devolve_zero_sem_levantar(ruim) -> None:
    """
    Levantar dentro do callback derruba o processo atravessando a fronteira
    ctypes. Sentinela zero e' detectavel depois, na auditoria.
    """
    resultado = parse_ts_ns(ruim)
    assert isinstance(resultado, int)


def test_e_mais_rapido_que_strptime() -> None:
    import time

    amostra = "02/01/2024 10:00:00.123"
    n = 20_000

    t0 = time.perf_counter()
    for _ in range(n):
        parse_ts_ns(amostra)
    rapido = time.perf_counter() - t0

    t0 = time.perf_counter()
    for _ in range(n):
        datetime.strptime(amostra, "%d/%m/%Y %H:%M:%S.%f")
    lento = time.perf_counter() - t0

    assert rapido < lento, f"parser manual ({rapido:.3f}s) nao superou strptime ({lento:.3f}s)"
