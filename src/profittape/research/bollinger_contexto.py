"""
Estocastico de CONTEXTO (timeframe maior) como filtro do scalp de
Bollinger -- medicao de FUNIL, categoria `features`, zero trial.

O ERRO QUE ISTO CORRIGE (2026-10-01)
-------------------------------------
A clausula de estocastico da v1 foi medida com o %K lento calculado
sobre as MESMAS barras de 15s das Bollinger -- janela de 8 barras de
15s = 2 minutos. Resultado: 1 disparo em 164 na compra, ZERO na venda,
e a secao 7.6 do BOLLINGER_SCALP.md concluiu "a clausula nunca dispara,
e' estrutural".

A conclusao estava certa PARA AQUELE ACOPLAMENTO e errada como leitura
da hipotese. Com os dois indicadores na mesma janela, um branco que
fecha ACIMA da banda superior fecha, por construcao, no topo da faixa
de 8 barras -- o %K lento nao pode estar no fundo dela ao mesmo tempo.
As duas condicoes eram quase mutuamente exclusivas POR DEFINICAO.

O operador apontou (2026-10-01) que a spec sempre disse outra coisa: o
estocastico e' do GRAFICO MAIOR (6 minutos), nao da barra de 15s. Com
janela de 8 barras de 6 min (48 minutos), a dependencia geometrica
desaparece: onde o preco esta' dentro de 48 minutos nao e' determinado
por um fechamento de 15s acima da banda.

Bollinger de 15s = tendencia imediata. Estocastico de 6 min = exaustao
do contexto. Dois horizontes, que e' o que torna o filtro nao-redundante
com a propria banda.

LOOK-AHEAD: O PONTO CRITICO DESTE MODULO
-----------------------------------------
Uma barra de 6 minutos so' esta' COMPLETA no fim dela. Usar o
estocastico da barra de 6 min que CONTEM a barra de 15s do sinal seria
usar informacao do futuro -- o valor final daquela barra de 6 min
depende de precos que, no instante do sinal, ainda nao aconteceram.

Por isso `estocastico_de_contexto` alinha pela ULTIMA barra de 6 min
JA' FECHADA antes do inicio da barra de 15s. O custo e' que o contexto
tem ate' 6 minutos de defasagem -- e' o preco de nao trapacear.

`--permitir-look-ahead` existe SO' para medir o tamanho desse custo
(quanto do funil vem da defasagem). NUNCA use para decidir nada.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import structlog

from . import bollinger_scalp as bs

log = structlog.get_logger(__name__)

SEGUNDOS_CONTEXTO = 360          # 6 minutos, escolha do operador (2026-10-01)
EST_PERIODO_CONTEXTO = 8         # mesmos parametros do estocastico lento da v1
EST_MEDIA_CONTEXTO = 3


def barras_de_contexto(barras15: pd.DataFrame,
                      segundos: int = SEGUNDOS_CONTEXTO) -> pd.DataFrame:
    """
    Agrega as barras de 15s em barras de `segundos`. Os baldes de 15s ja'
    vem alinhados ao epoch (ver `barras_15s_do_tape`), e 360 e' multiplo
    de 15, entao o balde maior tambem alinha -- 24 barras de 15s por
    barra de 6 min, sem sobra.

    Devolve uma linha por barra de contexto, com `ts_fim` = instante em
    que aquela barra FECHA (e a partir do qual o valor dela pode ser
    usado sem look-ahead).
    """
    if barras15.empty:
        return pd.DataFrame()
    x = barras15.copy()
    passo = int(segundos) * 1_000_000_000
    x["balde_ctx"] = (x["ts"].astype("int64") // passo) * passo
    g = x.groupby(["dia", "balde_ctx"], sort=True)
    ctx = pd.DataFrame({
        "open": g["open"].first(),
        "high": g["high"].max(),
        "low": g["low"].min(),
        "close": g["close"].last(),
        "barras15": g["close"].size(),
    }).reset_index()
    # A barra de contexto FECHA no fim do seu balde. So' a partir dai' o
    # valor dela existe para quem esta' olhando o mercado ao vivo.
    ctx["ts_fim"] = ctx["balde_ctx"] + passo
    ctx["bloco"] = ctx["dia"]
    return ctx


def estocastico_de_contexto(ctx: pd.DataFrame,
                           periodo: int = EST_PERIODO_CONTEXTO,
                           media: int = EST_MEDIA_CONTEXTO) -> pd.DataFrame:
    """%K lento sobre as barras de contexto, mesma formula da v1
    (`bollinger_scalp.indicadores`), reiniciando por pregao."""
    if ctx.empty:
        return ctx
    d = ctx.copy()
    hh = d.groupby("bloco")["high"].transform(lambda s: s.rolling(periodo).max())
    ll = d.groupby("bloco")["low"].transform(lambda s: s.rolling(periodo).min())
    faixa = hh - ll
    d["k_rapido_ctx"] = np.where(faixa > 0, 100.0 * (d["close"] - ll) / faixa, np.nan)
    d["est_ctx"] = d.groupby("bloco")["k_rapido_ctx"].transform(
        lambda s: s.rolling(media).mean())
    return d


def alinhar_contexto(barras15: pd.DataFrame, ctx: pd.DataFrame,
                    permitir_look_ahead: bool = False) -> Any:
    """
    Para cada barra de 15s, o valor do estocastico de contexto
    DISPONIVEL naquele instante: o da ultima barra de 6 min JA' FECHADA.

    `permitir_look_ahead=True` usa a barra de 6 min que CONTEM a barra de
    15s -- informacao do futuro. So' para medir o custo da defasagem,
    NUNCA para decidir.
    """
    if barras15.empty or ctx.empty:
        return pd.Series(dtype=float, index=barras15.index)
    if permitir_look_ahead:
        chave = (barras15["ts"].astype("int64")
                // (SEGUNDOS_CONTEXTO * 10**9)) * (SEGUNDOS_CONTEXTO * 10**9)
        mapa = ctx.set_index("balde_ctx")["est_ctx"]
        return chave.map(mapa)
    # Sem look-ahead: merge_asof pega a ultima barra de contexto cujo
    # ts_fim <= ts da barra de 15s. `allow_exact_matches=True` esta'
    # certo: se a barra de contexto fecha exatamente no ts de abertura da
    # barra de 15s, ela ja' fechou -- o valor existe.
    esq = barras15[["ts"]].copy()
    esq["_ordem"] = np.arange(len(esq))
    esq = esq.sort_values("ts", kind="stable")
    dir_ = ctx[["ts_fim", "est_ctx"]].dropna(subset=["est_ctx"]).sort_values("ts_fim")
    junto = pd.merge_asof(esq, dir_, left_on="ts", right_on="ts_fim",
                         direction="backward", allow_exact_matches=True)
    return junto.sort_values("_ordem")["est_ctx"].to_numpy()


@dataclass
class FunilContexto:
    """Uma linha do funil: quantos candidatos sobrevivem a cada limiar."""

    lado: str
    candidatos: int
    com_contexto: int          # candidatos que tem estocastico de contexto definido
    passa_extremo: int         # <20 compra / >80 venda
    passa_direcao: int         # <50 compra / >50 venda

    def como_dict(self) -> dict[str, object]:
        def pct(n: int) -> str:
            return f"{100.0 * n / self.com_contexto:.1f}%" if self.com_contexto else "--"
        return {
            "lado": self.lado, "candidatos": self.candidatos,
            "com_contexto": self.com_contexto,
            "extremo": f"{self.passa_extremo} ({pct(self.passa_extremo)})",
            "direcao": f"{self.passa_direcao} ({pct(self.passa_direcao)})",
        }


def medir_funil(barras15: pd.DataFrame, permitir_look_ahead: bool = False,
               segundos: int = SEGUNDOS_CONTEXTO) -> tuple[list[FunilContexto], pd.DataFrame]:
    """
    `barras15` = saida de `indicadores_e_sinais_do_tape` (ja' com
    sinal_compra/sinal_venda pela clausula de BANDA, sem estocastico).

    Devolve (funil por lado, barras com a coluna `est_ctx` anexada).

    Categoria `features`: nao testa regra de saida, nao consome trial.
    Responde UMA pergunta -- a hipotese com contexto de 6 min tem
    eventos suficientes para valer um pre-registro? (disciplina 7.4)
    """
    ctx = estocastico_de_contexto(barras_de_contexto(barras15, segundos))
    x = barras15.copy()
    x["est_ctx"] = alinhar_contexto(x, ctx, permitir_look_ahead)

    linhas: list[FunilContexto] = []
    for lado, col, extremo, direcao in (
        ("compra", "sinal_compra", x["est_ctx"] < bs.EST_SOBREVENDIDO, x["est_ctx"] < 50),
        ("venda", "sinal_venda", x["est_ctx"] > bs.EST_SOBRECOMPRADO, x["est_ctx"] > 50),
    ):
        cand = x[col].fillna(False).astype(bool)
        com_ctx = cand & x["est_ctx"].notna()
        linhas.append(FunilContexto(
            lado=lado,
            candidatos=int(cand.sum()),
            com_contexto=int(com_ctx.sum()),
            passa_extremo=int((com_ctx & extremo).sum()),
            passa_direcao=int((com_ctx & direcao).sum()),
        ))
    return linhas, x
