"""
Volume bars com relogio de AGRESSAO.

POR QUE VOLUME BARS
-------------------
Barra de tempo fixo amostra o mercado no ritmo do relogio; informacao chega no
ritmo da atividade. Amostrar por volume (Lopez de Prado, cap. 2) aproxima as
barras de retornos mais bem-comportados e evita que a madrugada do after e o
leilao de abertura tenham o mesmo peso.

O DETALHE B3: SO AGRESSAO AVANCA O RELOGIO
------------------------------------------
RLP e' ~25% do volume do WIN e NAO e' agressao em livro — e' varejo
internalizado. Se RLP avancasse o relogio, as barras encolheriam nos horarios
de pico de varejo sem que houvesse mais informacao de microestrutura. Leilao
idem. Regra: o relogio conta apenas AGGRESSOR_BUYER/SELLER; os demais negocios
sao ATRIBUIDOS a barra corrente (para features auxiliares como fracao RLP),
mas nao a fecham.

FRONTEIRA DE SESSAO
-------------------
Barra nunca atravessa dia: o resto incompleto do fim do pregao e' DESCARTADO
(flag `descartadas_parciais` no resumo). Barra parcial tem variancia de outro
regime e contaminaria qualquer estatistica por barra.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..domain.enums import TradeType

_AGRESSAO = (int(TradeType.AGGRESSOR_BUYER), int(TradeType.AGGRESSOR_SELLER))


def sugerir_volume_barra(df: pd.DataFrame, barras_por_dia: int = 100) -> int:
    """
    Threshold = mediana do volume de agressao diario / alvo de barras.

    Mediana, nao media: um vencimento de opcoes no meio da amostra nao deve
    ditar o tamanho da barra dos dias normais.
    """
    agr = df[df["trade_type"].isin(_AGRESSAO)]
    por_dia = agr.groupby(agr["dt"], observed=True)["quantidade"].sum()
    alvo = float(por_dia.median()) / barras_por_dia
    # Arredonda para 2 algarismos significativos: threshold "bonito" facilita
    # comparar rodadas e evita falsa precisao.
    if alvo <= 0:
        raise ValueError("sem volume de agressao no dataset")
    magnitude = 10 ** (int(np.floor(np.log10(alvo))) - 1)
    return max(1, int(round(alvo / magnitude) * magnitude))


def atribuir_barras(df: pd.DataFrame, volume_barra: int) -> tuple[pd.DataFrame, int]:
    """
    Adiciona a coluna `bar_id` (global, crescente atraves dos dias) e devolve
    (df_sem_parciais, n_barras_parciais_descartadas).

    Convencao de fechamento: o negocio cuja soma cumulativa CRUZA o threshold
    pertence a barra que ele completa (bar_id = cum_anterior // T).
    """
    if not df["ts_ns"].is_monotonic_increasing:
        df = df.sort_values("ts_ns", kind="stable").reset_index(drop=True)

    vol_clock = np.where(df["trade_type"].isin(_AGRESSAO), df["quantidade"], 0)

    partes: list[pd.DataFrame] = []
    descartadas = 0
    offset = 0
    for _, grupo in df.groupby("dt", observed=True, sort=True):
        vc = vol_clock[grupo.index]
        cum_prev = np.cumsum(vc) - vc          # exclusivo: soma ANTES do negocio
        bar_local = (cum_prev // volume_barra).astype(np.int64)

        # Descarta a ultima barra do dia se incompleta.
        total = cum_prev[-1] + vc[-1]
        completas = int(total // volume_barra)
        mask = bar_local < completas
        descartadas += int((~mask).any())

        g = grupo.loc[mask].copy()
        g["bar_id"] = bar_local[mask] + offset
        offset += completas
        partes.append(g)

    if not partes:
        raise ValueError("nenhuma barra completa — volume_barra grande demais?")
    return pd.concat(partes, ignore_index=True), descartadas


def atribuir_barras_tempo(df: pd.DataFrame, segundos: int) -> tuple[pd.DataFrame, int]:
    """
    Barra de TEMPO fixo. Adiciona `bar_id` (global, crescente atraves dos
    dias) e devolve (df_sem_a_ultima_barra_do_dia, n_barras_descartadas).

    POR QUE ELA EXISTE, JA QUE O PROJETO USA VOLUME BAR
    ---------------------------------------------------
    O argumento a favor de volume bar (relogio de informacao, nao de parede)
    continua valendo e nao esta sendo revogado. Esta funcao existe para o
    pre-registro de 2026-08-29e, cuja HIPOTESE e' explicitamente sobre a
    barra de 1m/5m que o operador le no grafico — a barra de volume apaga
    exatamente a estrutura que a hipotese descreve. Sao dois regimes de
    amostragem diferentes, com resultados que NAO se misturam.

    O QUE SE MANTEM DA CONVENCAO JA TRAVADA
    ---------------------------------------
    - Barra nunca atravessa o dia (bucket calculado dentro de cada `dt`).
    - A ULTIMA barra de cada pregao e' descartada: ela e' parcial por
      construcao (o pregao acaba no meio do balde) e tem variancia de outro
      regime, igual a parcial da volume bar.
    - RLP e leilao sao ATRIBUIDOS a barra, mas nao entram em `vol_agr` nem
      no OHLC — isso e' resolvido em flow.calcular, nao aqui.

    O QUE MUDA, E E' DIFERENCA REAL
    -------------------------------
    O relogio e' de parede, entao um balde SEM negocio nenhum simplesmente
    nao existe na saida (nao ha linha para agrupar). Como flow.calcular
    monta a barra a partir dos negocios de AGRESSAO, um balde que so' teve
    RLP tambem desaparece. Isso e' deliberado: barra preenchida artificial
    teria `range = 0` e `vol_agr = 0`, e produziria `desloc_norm`
    degenerado. O custo e' que `bar_id` pode ter buracos, e portanto
    "h barras a frente" nem sempre e' "h*segundos a frente" — o numero de
    buracos e' reportado pelo pipeline para que isso seja auditavel em vez
    de silencioso.
    """
    if segundos <= 0:
        raise ValueError("segundos deve ser positivo")
    if not df["ts_ns"].is_monotonic_increasing:
        df = df.sort_values("ts_ns", kind="stable").reset_index(drop=True)

    # O balde vem do EPOCH (ts_ns // periodo). Para 60s e 300s isso coincide
    # com a fronteira de minuto/5-minutos de relogio em UTC, e como o fuso da
    # B3 e' deslocado em horas inteiras, coincide tambem com a fronteira
    # local — a barra de 5m comeca em :00, :05, :10, como no grafico. Vale
    # para qualquer periodo que divida 3600; para um periodo esquisito
    # (ex.: 7s) o alinhamento seria arbitrario, e por isso o pipeline so'
    # expoe 60 e 300.
    periodo_ns = int(segundos) * 1_000_000_000
    partes: list[pd.DataFrame] = []
    descartadas = 0
    offset = 0
    for _, grupo in df.groupby("dt", observed=True, sort=True):
        balde = (grupo["ts_ns"].to_numpy() // periodo_ns).astype(np.int64)
        ultimo = balde[-1]
        mask = balde < ultimo          # descarta o balde final do pregao
        descartadas += 1
        g = grupo.loc[mask].copy()
        if g.empty:
            continue
        b = balde[mask]
        # Indice RELATIVO ao primeiro balde do dia — nao denso. A versao
        # original usava np.unique(return_inverse=True), que renumera
        # densamente e portanto APAGA os baldes vazios; o contador de
        # buracos do pipeline media o resultado ja achatado e devolvia
        # zero por construcao, sempre (bug real, 2026-08-29, pego ao
        # investigar dois pregoes curtos no log do operador). Preservar o
        # indice relativo e' o que torna o buraco visivel e contavel.
        g["bar_id"] = (b - b.min()).astype(np.int64) + offset
        offset += int(b.max() - b.min()) + 1
        partes.append(g)

    if not partes:
        raise ValueError("nenhuma barra de tempo completa — periodo grande demais?")
    return pd.concat(partes, ignore_index=True), descartadas


def inferir_tick(df: pd.DataFrame) -> float:
    """
    Tick = menor variacao de preco positiva observada na agressao.

    Inferido do dado em vez de tabelado: sobrevive a mudanca de regra da B3 e
    a simbolos que nao previmos. Mediana por dia para robustez a outlier.
    """
    agr = df[df["trade_type"].isin(_AGRESSAO)]
    ticks = []
    for _, g in agr.groupby("dt", observed=True):
        difs = g["price"].diff().abs()
        positivos = difs[difs > 0]
        if len(positivos):
            ticks.append(positivos.min())
    if not ticks:
        raise ValueError("impossivel inferir tick: sem variacao de preco")
    return float(np.median(ticks))
