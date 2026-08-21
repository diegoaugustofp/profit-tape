"""
Parser do timestamp do ProfitDLL.

POR QUE NAO strptime
--------------------
`datetime.strptime` custa na casa de 10 microssegundos por chamada. Isso roda
DENTRO do callback da DLL, com o feed parado esperando. A 50 mil eventos por
segundo em rajada, strptime sozinho consome meio segundo de CPU por segundo de
mercado — o feed nao sobrevive a isso.

O formato e' fixo ("DD/MM/YYYY HH:MM:SS.mmm"), entao fatiar a string e chamar
int() em cada pedaco resolve em cerca de um microssegundo. Uma ordem de
grandeza importa aqui.

FUSO
----
A DLL entrega horario local de Brasilia. Gravamos SEMPRE em UTC. O Brasil nao
usa horario de verao desde 2019, entao o deslocamento e' constante em -03:00 —
mas deixamos configuravel porque isso e' decisao politica e ja mudou antes.
"""

from __future__ import annotations

from datetime import UTC, datetime


def _dias_desde_epoch(ano: int, mes: int, dia: int) -> int:
    """
    Calendario -> dias desde 1970-01-01, sem construir datetime.

    Algoritmo `days_from_civil` de Howard Hinnant: desloca o ano para comecar
    em marco, o que joga o dia bissexto para o FIM do ano e elimina o caso
    especial de fevereiro. Vale para todo o calendario gregoriano proletico —
    inclusive a regra dos 400 anos (2000 bissexto, 2100 nao).
    """
    y = ano - (1 if mes <= 2 else 0)
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400                                  # [0, 399]
    m_shift = mes + (-3 if mes > 2 else 9)               # marco = 0
    doy = (153 * m_shift + 2) // 5 + dia - 1             # [0, 365]
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy        # [0, 146096]
    return era * 146097 + doe - 719468


def parse_ts_ns(s: str | None, offset_horas: int = -3) -> int:
    """
    "DD/MM/YYYY HH:MM:SS.mmm" -> epoch em nanossegundos UTC.

    Devolve 0 quando a string vem vazia ou malformada. Zero e' sentinela
    reconhecivel na auditoria posterior — melhor que levantar excecao dentro
    do callback, o que derrubaria o processo.
    """
    if not s or len(s) < 19:
        return 0
    try:
        dia = int(s[0:2])
        mes = int(s[3:5])
        ano = int(s[6:10])
        hora = int(s[11:13])
        minuto = int(s[14:16])
        seg = int(s[17:19])
        ms = int(s[20:23]) if len(s) >= 23 and s[19] == "." else 0
    except (ValueError, IndexError):
        return 0

    dias = _dias_desde_epoch(ano, mes, dia)
    segundos = dias * 86_400 + (hora - offset_horas) * 3_600 + minuto * 60 + seg
    return segundos * 1_000_000_000 + ms * 1_000_000


def formatar(ts_ns: int) -> str:
    """Inverso, para inspecao humana em log e teste."""
    if ts_ns == 0:
        return "(invalido)"
    dt = datetime.fromtimestamp(ts_ns / 1e9, tz=UTC)
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + "Z"
