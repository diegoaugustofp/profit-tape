"""
Scalp de Bollinger -- conteudo direcional do sinal (docs/BOLLINGER_SCALP.md
5.6), ANTES de qualquer variante de saida.

PERGUNTA
--------
Nas barras em que a clausula de banda dispara (t-2 correcao, t-1 retomada
-- a mesma extracao da v1, SEM estocastico), o preco depois anda na
direcao do sinal mais do que o ruido explicaria?

NAO E' UMA REGRA DE ENTRADA
----------------------------
Sem stop, sem alvo, sem ordem. So' caracterizacao: retorno assinado e
excursao maxima favoravel/adversa (MFE/MAE) em 1, 4 e 16 barras a partir
do fechamento da ULTIMA barra do padrao (t-1), contra o mesmo em barras
de CONTROLE sem sinal, pareadas por faixa horaria de 30 min (o perfil de
volume ja mostrou que a manha e a tarde sao regimes diferentes -- comparar
sinal da manha com controle da tarde enviesaria).

Ponto de referencia (`ref`): a barra t-1 do padrao (a ultima antes da
entrada), nao a barra t (que ja e' a entrada em si). h=1 mede ate' o
fechamento de t (a primeira barra em que dava para ter agido).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import structlog

log = structlog.get_logger(__name__)

HORIZONTES = (1, 4, 16)


def _lado_dos_candidatos(x: pd.DataFrame) -> pd.Series:
    """+1 nas barras t de sinal de compra, -1 nas de venda, 0 no resto.
    Usa a mesma extracao da v1 (marcar_sinais com usar_estocastico=False,
    ja' aplicado por quem chama)."""
    lado = pd.Series(0, index=x.index, dtype=int)
    lado[x["sinal_compra"]] = 1
    lado[x["sinal_venda"]] = -1
    return lado


def _retorno_mfe_mae(
    x: pd.DataFrame, ref_pos: int, lado: int, h: int
) -> tuple[float, float, float]:
    """
    `ref_pos` = posicao (iloc) da barra t-1 (ultima do padrao) DENTRO do
    bloco contiguo de x. Janela futura = [ref_pos+1, ref_pos+h], inclusive.
    Fora do bloco (janela vazaria para outro pregao) -> NaN nos tres.
    """
    fim = ref_pos + h
    if fim >= len(x):
        return (np.nan, np.nan, np.nan)
    close_ref = float(x["close"].iloc[ref_pos])
    janela = x.iloc[ref_pos + 1 : fim + 1]
    retorno = lado * (float(x["close"].iloc[fim]) - close_ref)
    if lado >= 0:
        mfe = float(janela["high"].max()) - close_ref
        mae = float(janela["low"].min()) - close_ref
    else:
        mfe = close_ref - float(janela["low"].min())
        mae = close_ref - float(janela["high"].max())
    return (retorno, mfe, mae)


def medir(barras: pd.DataFrame, horizontes: tuple[int, ...] = HORIZONTES,
         seed: int = 0) -> pd.DataFrame:
    """
    `barras` = saida de `indicadores_e_sinais_do_tape` (replay) ou de
    `bs.marcar_sinais(bs.indicadores(dump))` (dump do grafico) -- qualquer
    coisa com as colunas de `marcar_sinais` e "bloco" contiguo por pregao.

    Devolve uma linha por (grupo, lado, horizonte, observacao): grupo em
    {"sinal","controle"}. `resumir()` agrega em media + IC95.
    """
    x = barras.reset_index(drop=True)
    lado = _lado_dos_candidatos(x)
    candidatos_pos = np.flatnonzero(lado.to_numpy() != 0)
    # ref_pos = a barra t-1 do padrao = uma posicao ANTES da barra de sinal t
    refs_sinal = candidatos_pos - 1
    valido = refs_sinal >= 0
    refs_sinal, pos_sinal = refs_sinal[valido], candidatos_pos[valido]

    faixa = ((x["hora_int"] // 30).astype(int) if "hora_int" in x.columns
             else pd.Series(0, index=x.index))
    # elegivel a virar CONTROLE: nao e' ele mesmo nem a barra de sinal
    # adjacente (t ou t-1 de qualquer candidato), para nao reamostrar o
    # proprio evento por acidente.
    marcado = np.zeros(len(x), dtype=bool)
    marcado[candidatos_pos] = True
    marcado[np.clip(candidatos_pos - 1, 0, None)] = True
    elegivel = ~marcado

    rng = np.random.default_rng(seed)
    linhas: list[dict[str, Any]] = []

    def _emitir(grupo: str, ref_pos: int, lado_i: int) -> None:
        for h in horizontes:
            r, mfe, mae = _retorno_mfe_mae(x, ref_pos, lado_i, h)
            linhas.append({"grupo": grupo, "lado": lado_i, "horizonte": h,
                           "retorno": r, "mfe": mfe, "mae": mae,
                           "hora_int": int(x["hora_int"].iloc[ref_pos])
                           if "hora_int" in x.columns else -1})

    for ref_pos, lado_i in zip(refs_sinal, lado.to_numpy()[pos_sinal], strict=True):
        _emitir("sinal", int(ref_pos), int(lado_i))

    # controle: mesma contagem por faixa horaria que o sinal teve.
    faixa_sinal = faixa.to_numpy()[refs_sinal]
    pool_por_faixa: dict[int, np.ndarray] = {}
    for f in np.unique(faixa_sinal):
        pool_por_faixa[int(f)] = np.flatnonzero(elegivel & (faixa.to_numpy() == f))
    for f in np.unique(faixa_sinal):
        precisa = int((faixa_sinal == f).sum())
        pool = pool_por_faixa.get(int(f), np.array([], dtype=int))
        if len(pool) == 0:
            log.warning("direcao_sinal.faixa_sem_controle", faixa=int(f), precisa=precisa)
            continue
        escolhidos = rng.choice(pool, size=precisa, replace=len(pool) < precisa)
        lados_controle = rng.choice([-1, 1], size=precisa)
        for ref_pos, lado_i in zip(escolhidos, lados_controle, strict=True):
            _emitir("controle", int(ref_pos), int(lado_i))

    return pd.DataFrame(linhas)


def _ic_media(x: pd.Series, z: float = 1.96) -> tuple[float, float]:
    x = x.dropna()
    n = len(x)
    if n < 2:
        return (float("nan"), float("nan"))
    m, se = float(x.mean()), float(x.std(ddof=1)) / np.sqrt(n)
    return (round(m - z * se, 2), round(m + z * se, 2))


def resumir(medidas: pd.DataFrame) -> pd.DataFrame:
    linhas = []
    for (grupo, h), g in medidas.groupby(["grupo", "horizonte"]):
        for campo in ("retorno", "mfe", "mae"):
            s = g[campo]
            lo, hi = _ic_media(s)
            linhas.append({"grupo": grupo, "horizonte": h, "campo": campo,
                           "n": int(s.notna().sum()), "media": round(float(s.mean()), 2),
                           "ic95_lo": lo, "ic95_hi": hi})
    return pd.DataFrame(linhas).sort_values(["horizonte", "campo", "grupo"]).reset_index(drop=True)
