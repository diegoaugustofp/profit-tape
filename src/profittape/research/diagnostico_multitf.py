"""
Armadilhas do modelo de DOIS TIMEFRAMES -- diagnóstico, não estratégia.

O operador perguntou (2026-09-23): *"essa estratégia diferente das
outras usa 2 timeframes. Quais armadilhas tem nesse modelo que podemos
ter caído nelas?"*. Este módulo mede as que são mensuráveis no dado que
já temos. Categoria `features`, zero trial.

AS ARMADILHAS
-------------

**1. CLUSTERING (a que o operador levantou).** Durante 24 barras de 15s
o estocástico de contexto fica CONGELADO. Se ele estiver em zona de
extremo, todas as barras daquela janela passam no filtro -- e os sinais
vêm em RAJADAS, não espalhados. Duas operações da mesma janela de 6 min
compartilham contexto, regime e provavelmente o mesmo movimento.

Consequência: as operações NÃO são independentes, e todo IC que
calculamos (o CONTRA de -26,0, o INCONCLUSIVO de -18,1, o poder do
forward) assumiu independência. Com clustering a variância real é
maior, e o IC verdadeiro é MAIS LARGO do que reportamos.

O fator de inflação da variância é o "design effect":

    deff = 1 + (m̄ - 1) * rho

onde m_bar e' o tamanho medio do cluster e rho a correlacao
Aproximação conservadora usada aqui: rho = 1 (operações do mesmo
cluster totalmente redundantes), que da' deff = m_bar -- o pior
caso. O n efetivo vira `n / m_bar`.

**2. AQUECIMENTO ASSIMÉTRICO.** O contexto precisa de 10 barras de 6
min (60 minutos) para existir. A janela da estratégia começa às 09:08,
então de 09:08 a ~10:08 NENHUM sinal é possível -- 26% do pregão útil.
Isso não é defeito, mas significa que a estratégia com contexto opera
numa janela horária DIFERENTE da sem contexto. Comparar as duas versões
sem saber disso é comparar coisas distintas.

**3. BARRAS DE CONTEXTO INCOMPLETAS.** A barra de 6 min é montada a
partir das barras de 15s que EXISTEM. Balde sem negócio nenhum não
aparece no dado, então uma "barra de 6 min" pode ter 5 barras de 15s em
vez de 24 -- e o estocástico calculado sobre ela mistura períodos de
liquidez muito diferentes, sem que nada acuse.

**4. EQUIVALÊNCIA NUNCA VALIDADA NO TIMEFRAME MAIOR.** Os indicadores
de 15s foram validados contra o gráfico do Profit (dif_max = 0,0,
seção 2). O estocástico de 6 MIN nunca foi. Se o Profit montar a barra
de 6 min de forma diferente (tipos de negócio incluídos, tratamento de
leilão), o número que o operador vê na tela não é o que o código usa.
Isto NÃO é mensurável sem um dump do gráfico de 6 min -- fica
registrado como lacuna.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import structlog

from .bollinger_contexto import SEGUNDOS_CONTEXTO, barras_de_contexto

log = structlog.get_logger(__name__)


@dataclass
class DiagnosticoMultiTF:
    # clustering
    operacoes: int
    janelas_com_sinal: int
    tamanho_medio_cluster: float
    maior_cluster: int
    deff_conservador: float
    n_efetivo: float
    # aquecimento
    primeira_hora_com_contexto: str
    # barras parciais
    barras_contexto: int
    barras_contexto_incompletas: int
    barras15_mediana: float

    def resumo(self) -> dict[str, object]:
        return {
            "operacoes": self.operacoes,
            "janelas_de_6min_com_sinal": self.janelas_com_sinal,
            "tamanho_medio_do_cluster": round(self.tamanho_medio_cluster, 2),
            "maior_cluster": self.maior_cluster,
            "deff_conservador": round(self.deff_conservador, 2),
            "n_efetivo": round(self.n_efetivo, 1),
            "primeiro_sinal_possivel": self.primeira_hora_com_contexto,
            "barras_de_contexto": self.barras_contexto,
            "incompletas": self.barras_contexto_incompletas,
            "barras15_por_contexto_mediana": self.barras15_mediana,
        }


def medir(barras: pd.DataFrame, segundos: int = SEGUNDOS_CONTEXTO) -> DiagnosticoMultiTF:
    """
    `barras` = saída de `indicadores_e_sinais_do_tape`, já com os sinais
    marcados (com ou sem filtro de contexto -- o clustering se mede sobre
    os sinais que de fato existem).
    """
    x = barras.copy()
    passo_ctx = int(segundos) * 10**9
    x["janela_ctx"] = (x["ts_ini_ns"].astype("int64") // passo_ctx) * passo_ctx
    vazio = pd.Series(False, index=x.index)
    compra = x["sinal_compra"].fillna(False) if "sinal_compra" in x.columns else vazio
    venda = x["sinal_venda"].fillna(False) if "sinal_venda" in x.columns else vazio
    tem_sinal = (compra | venda).astype(bool)

    # --- clustering ---
    sinais = x.loc[tem_sinal]
    n = len(sinais)
    por_janela = sinais.groupby("janela_ctx").size() if n else pd.Series(dtype=int)
    janelas = len(por_janela)
    m_bar = float(por_janela.mean()) if janelas else 0.0
    maior = int(por_janela.max()) if janelas else 0
    # deff com rho=1 (pior caso): a variancia infla pelo tamanho do cluster
    deff = max(m_bar, 1.0)
    n_ef = n / deff if deff > 0 else 0.0

    # --- aquecimento: primeiro instante em que o contexto existe ---
    ctx = barras_de_contexto(x, segundos)
    aquecimento_barras = 8 + 3 - 1          # periodo + media - 1
    if len(ctx) > aquecimento_barras:
        ts_prim = int(ctx["ts_fim"].iloc[aquecimento_barras])
        # ts_fim esta' em SEGUNDOS (ver barras_de_contexto)
        primeira = pd.to_datetime(ts_prim, unit="s").strftime("%H:%M")
    else:
        primeira = "(sem contexto no periodo)"

    # --- barras de contexto incompletas ---
    esperado = int(segundos // 15)
    incompletas = int((ctx["barras15"] < esperado).sum()) if len(ctx) else 0
    mediana = float(ctx["barras15"].median()) if len(ctx) else float("nan")

    return DiagnosticoMultiTF(
        operacoes=n, janelas_com_sinal=janelas, tamanho_medio_cluster=m_bar,
        maior_cluster=maior, deff_conservador=deff, n_efetivo=n_ef,
        primeira_hora_com_contexto=primeira,
        barras_contexto=len(ctx), barras_contexto_incompletas=incompletas,
        barras15_mediana=mediana,
    )


def ic_corrigido(media: float, ic_lo: float, ic_hi: float, n: int,
                deff: float, z: float = 1.959964) -> tuple[float, float]:
    """
    Reabre um IC calculado sob independência, inflando o erro padrão por
    sqrt(deff).

    Serve para responder "a conclusão sobrevive ao clustering?" sem
    refazer o replay: o ponto estimado não muda, só a incerteza em volta
    dele -- que é exatamente o que o clustering afeta.
    """
    se = (ic_hi - ic_lo) / (2 * z)
    se_corr = se * np.sqrt(max(deff, 1.0))
    return (media - z * se_corr, media + z * se_corr)
