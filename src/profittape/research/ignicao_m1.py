"""
IGNICAO no historico M1 (set/2021 -> hoje) -- FAST-TRACK (decisao do
operador, 2026-09-25): uma ou mais rodadas em todo o historico, sem guarda
de amostra, sem trial, sem deflacao. O que fica: parametros fixados ANTES
(proporcoes do tape), conta a mao, ambiguo reportado, consistencia POR ANO
no lugar da amostra cega.

REGRA (declarada antes de qualquer numero; HISTORICO 2026-09-25)
----------------------------------------------------------------
A_d      mediana das amplitudes de 60 min (max-min em blocos de 60 candles
         a partir de 09:15) de cada pregao, e depois a mediana disso nos
         20 PREGOES ANTERIORES (so' passado). Serie ajustada: movimento e
         amplitude escalam pelo mesmo fator -> a razao e' invariante.
evento   fechamento(t) - fechamento(t-1) (candles CONSECUTIVOS, 60 s -- o
         analogo do tape), |mov| >= LAMBDA * A_d; decisao no FIM do candle t
         (rotulo + 1 min, conferido: o rotulo e' o INICIO) em [09:16, 17:00);
         refratario 30 min a partir da decisao.
         LAMBDA = 500 / 1.058 = 0,4726: a proporcao do tape (limiar 500 pela
         regra cega da taxa; amplitude mediana de 60 min 1.058).
entrada  fechamento(t).
barreira B = 0,5 * A_d, nos candles t+1 ... com rotulo <= rotulo(t) + 60 min:
         maxima/minima atinge +B -> alvo; -B -> stop; os DOIS no mesmo
         candle -> AMBIGUO (sai do p_alvo, reportado). Nenhum -> sem decisao.
empate   (B + C) / 2B por evento, C = (9 + 30) pts REAIS x fator do dia
         (spread 5 + taxas 4 + deslizamento 30). Reporta-se a media.

DIFERENCA PARA O TAPE (e' outro evento, nao o mesmo com menos precisao):
movimento que atravessa a virada do minuto aparece em dois candles e
pode nao disparar; a entrada e' no fechamento do candle, nao no negocio.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from .m1_historico import fator_por_granularidade

LAMBDA_TAPE = 500.0 / 1058.0          # 0,4726
FRACAO_BARREIRA = 0.5
CUSTO_REAL_PTS = 9.0
DESLIZAMENTO_REAL_PTS = 30.0
JANELA_AMPLITUDE_PREGOES = 20


def _minuto(t: pd.Series) -> np.ndarray:
    return np.asarray((t.dt.hour * 60 + t.dt.minute).to_numpy(), dtype=np.int64)


def amplitude_60_do_dia(g: pd.DataFrame, inicio_min: int = 9 * 60 + 15,
                        fim_min: int = 17 * 60) -> float | None:
    """Mediana de (max - min) em blocos de 60 min a partir de 09:15."""
    m = _minuto(g["data_hora"])
    h, lo = g["maxima"].to_numpy(), g["minima"].to_numpy()
    amps = []
    for a in range(inicio_min, fim_min - 59, 60):
        sel = (m >= a) & (m < a + 60)
        if sel.sum() >= 2:
            amps.append(float(h[sel].max() - lo[sel].min()))
    return float(np.median(amps)) if amps else None


@dataclass
class EventoM1:
    dia: str
    ano: int
    hora_decisao: str
    direcao: int
    mov: float                 # pontos AJUSTADOS
    limiar: float
    barreira: float
    fator: float
    mov_real: float            # pontos reais (/ fator)
    barreira_real: float
    entrada: float
    resultado: str             # alvo / stop / ambiguo / sem_decisao
    candles_ate_decidir: int | None
    empate: float


def detectar_dia(g: pd.DataFrame, A: float, fator: float, *,
                 lambda_: float = LAMBDA_TAPE, fracao_barreira: float = FRACAO_BARREIRA,
                 refratario_min: int = 30, janela_barreira_min: int = 60,
                 inicio_decisao_min: int = 9 * 60 + 16, fim_decisao_min: int = 17 * 60
                 ) -> list[EventoM1]:
    g = g.sort_values("data_hora")
    m = _minuto(g["data_hora"])
    c = g["fechamento"].to_numpy(float)
    h = g["maxima"].to_numpy(float)
    lo = g["minima"].to_numpy(float)
    dia = str(g["dia"].iloc[0])
    limiar, B = lambda_ * A, fracao_barreira * A
    C = (CUSTO_REAL_PTS + DESLIZAMENTO_REAL_PTS) * fator
    out: list[EventoM1] = []
    livre = -1
    for i in range(1, len(c)):
        dec = m[i] + 1                                    # fim do candle t
        if m[i] - m[i - 1] != 1 or not (inicio_decisao_min <= dec < fim_decisao_min):
            continue
        if dec < livre:
            continue
        mov = c[i] - c[i - 1]
        if abs(mov) < limiar - 1e-9:
            continue
        livre = dec + refratario_min
        d = 1 if mov > 0 else -1
        e = c[i]
        resultado, k = "sem_decisao", None
        for j in range(i + 1, len(c)):
            if m[j] > m[i] + janela_barreira_min:
                break
            fav = (h[j] - e) if d > 0 else (e - lo[j])
            adv = (e - lo[j]) if d > 0 else (h[j] - e)
            ha, hs = fav >= B - 1e-9, adv >= B - 1e-9
            if ha or hs:
                resultado = "ambiguo" if (ha and hs) else ("alvo" if ha else "stop")
                k = j - i
                break
        out.append(EventoM1(dia, int(dia[:4]), f"{dec // 60:02d}:{dec % 60:02d}", d,
                            float(mov), float(limiar), float(B), float(fator),
                            float(mov / fator), float(B / fator), float(e), resultado, k,
                            float((B + C) / (2 * B))))
    return out


def detectar_historico(df: pd.DataFrame, *, lambda_: float = LAMBDA_TAPE,
                       fracao_barreira: float = FRACAO_BARREIRA,
                       janela_pregoes: int = JANELA_AMPLITUDE_PREGOES
                       ) -> tuple[list[EventoM1], pd.DataFrame]:
    """Todos os pregoes; os `janela_pregoes` primeiros so' alimentam A."""
    grupos = [(d, g) for d, g in df.groupby("dia", sort=True)]
    amp = [amplitude_60_do_dia(g) for _, g in grupos]
    evs: list[EventoM1] = []
    linhas = []
    for k, (d, g) in enumerate(grupos):
        passado = [a for a in amp[max(0, k - janela_pregoes):k] if a is not None]
        precos = g[["abertura", "maxima", "minima", "fechamento"]].to_numpy().ravel()
        f = fator_por_granularidade(precos)
        A = float(np.median(passado)) if len(passado) >= janela_pregoes else None
        linhas.append({"dia": d, "amplitude_dia": amp[k], "A": A, "fator": f})
        if A is None or f is None:
            continue
        evs.extend(detectar_dia(g, A, f, lambda_=lambda_, fracao_barreira=fracao_barreira))
    return evs, pd.DataFrame(linhas)


def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float] | None:
    if n == 0:
        return None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return round(c - m, 3), round(c + m, 3)


def placar(evs: list[EventoM1], n_pregoes: int | None = None) -> dict[str, Any]:
    r = pd.Series([e.resultado for e in evs])
    alvo, stop = int((r == "alvo").sum()), int((r == "stop").sum())
    dec = alvo + stop
    emp = float(np.mean([e.empate for e in evs if e.resultado in ("alvo", "stop")])) \
        if dec else None
    return {"eventos": len(evs),
            "por_pregao": round(len(evs) / n_pregoes, 2) if n_pregoes else None,
            "alvo": alvo, "stop": stop, "ambiguo": int((r == "ambiguo").sum()),
            "sem_decisao": int((r == "sem_decisao").sum()),
            "p_alvo": round(alvo / dec, 3) if dec else None, "ic95": wilson(alvo, dec),
            "empate_medio": round(emp, 3) if emp is not None else None,
            "barreira_real_mediana": round(float(np.median([e.barreira_real for e in evs])))
            if evs else None,
            "limiar_real_mediano": round(float(np.median([e.limiar / e.fator for e in evs])))
            if evs else None}


def comparar_com_tape(evs: list[EventoM1], tape: pd.DataFrame,
                      tolerancia_min: int = 2) -> dict[str, Any]:
    """Conferencia de TRADUCAO (dias de 2026 com tape): `tape` = CSV de
    eventos do `profit-tape ignicao` (colunas dia, hora_brt, direcao,
    barreira). Casa por dia, direcao e |hora| <= tolerancia."""
    t_dia = [str(x) for x in tape["dia"]]
    t_dir = [int(x) for x in tape["direcao"]]
    t_min = [int(h[:2]) * 60 + int(h[3:5]) for h in tape["hora_brt"].astype(str)]
    t_bar = [str(x) for x in tape["barreira"]]
    dias = set(t_dia)
    m1 = [e for e in evs if e.dia in dias]
    usados: set[int] = set()
    pares: list[tuple[EventoM1, str]] = []
    for e in m1:
        em = int(e.hora_decisao[:2]) * 60 + int(e.hora_decisao[3:])
        cand = [i for i in range(len(t_dia)) if t_dia[i] == e.dia and t_dir[i] == e.direcao
                and i not in usados and abs(t_min[i] - em) <= tolerancia_min]
        if cand:
            i = min(cand, key=lambda x: abs(t_min[x] - em))
            usados.add(i)
            pares.append((e, t_bar[i]))
    concorda = sum(1 for e, b in pares if (e.resultado, b) in (("alvo", "alvo"), ("stop", "stop")))
    decid = sum(1 for e, b in pares if e.resultado in ("alvo", "stop") and b in ("alvo", "stop"))
    return {"dias": len(dias), "eventos_tape": len(tape), "eventos_m1": len(m1),
            "casados": len(pares), "so_no_tape": len(tape) - len(pares),
            "so_no_m1": len(m1) - len(pares),
            "barreira_concorda": f"{concorda}/{decid}" if decid else None}


def linha(e: EventoM1) -> dict[str, Any]:
    return asdict(e)
