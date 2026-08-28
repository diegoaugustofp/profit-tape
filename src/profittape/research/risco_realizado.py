"""
VaR e Expected Shortfall REALIZADOS -- aplicando o insight central de
"Realized Quantiles" (estimar quantis de risco direto de retornos de
alta frequencia, em "tempo intrinseco") ao contexto especifico deste
projeto: calibrar o stop catastrofico contra o comportamento EMPIRICO
de cauda do proprio instrumento, nao so' contra a regra de capital.

CONEXAO DE DESIGN (2026-08-27): a fundacao teorica do RQ (Realized
Quantiles, Journal of Business & Economic Statistics 2021) assume
precos subordinados em "tempo intrinseco" -- transformado pela
ATIVIDADE de negociacao, nao pelo relogio. Isso e' EXATAMENTE o
conceito de "volume clock" (Easley/Lopez de Prado/O'Hara) que ja
motivou a escolha de barras por VOLUME neste projeto (nao por tempo)
desde o inicio. Nao e' coincidencia -- e' a mesma linhagem de ideias.
Nossas barras JA SAO amostragem em tempo intrinseco; a fundacao que o
RQ pressupoe ja esta embutida na arquitetura, sem esforco extra.

NAO consome trial: engenharia/descricao sobre o comportamento do
INSTRUMENTO (incondicional a qualquer sinal), mesmo espirito de
mae.py/quintis.py -- nao e' uma nova hipotese preditiva.

ESCOPO DELIBERADAMENTE LIMITADO: isto e' o "primeiro passo concreto"
(nao a maquinaria completa do paper de RQ, que projeta quantil
intradiario para VaR diario via relacao de escala de autossimilaridade
-- essa relacao NAO foi validada aqui, seria trabalho futuro separado).
Aqui: quantis e ES empiricos diretos sobre retorno de barra (magnitude
absoluta, ja que o stop catastrofico e' simetrico por lado), OPCIONALMENTE
segmentados por faixa de horario -- sazonalidade intradiaria (padrao em
U de volume, ja documentado neste projeto) quebra a suposicao de
estacionariedade se tudo for agrupado sem essa segmentacao.
"""

from __future__ import annotations

import pandas as pd


def var_es_realizado(
    retornos_abs: pd.Series,
    niveis_confianca: tuple[float, ...] = (0.90, 0.95, 0.99, 0.995),
) -> pd.DataFrame:
    """
    Para cada nivel de confianca c: VaR_c = quantil c da distribuicao
    empirica de |retorno| por barra. ES_c = media dos valores que EXCEDEM
    (>=) o VaR_c -- "quando estoura, qual o tamanho medio do estouro".

    retornos_abs: serie de magnitudes NAO-NEGATIVAS (ex.: close.diff().abs()
    por barra) -- simetrico por design, o stop catastrofico nao distingue
    lado.
    """
    linhas = []
    for c in niveis_confianca:
        var_c = retornos_abs.quantile(c)
        cauda = retornos_abs[retornos_abs >= var_c]
        es_c = cauda.mean() if len(cauda) > 0 else float("nan")
        linhas.append({"nivel_confianca": c, "var_pontos": var_c,
                       "es_pontos": es_c, "n_na_cauda": len(cauda)})
    return pd.DataFrame(linhas)


def nivel_implicado_por_limiar(retornos_abs: pd.Series, limiar: float) -> dict:
    """
    Pergunta inversa: dado um limiar JA' ESCOLHIDO (ex.: os 500 pts do
    stop catastrofico), que nivel de confianca empirico ele representa?

    nivel_confianca: fracao de barras com magnitude ESTRITAMENTE menor
    que o limiar -- "o stop cobre esta fracao das barras observadas".
    es_no_limiar: media das magnitudes que atingem ou passam do limiar --
    "quando uma barra sozinha ja' bate ou passa do limiar, qual o tamanho
    medio dela".
    """
    n = len(retornos_abs)
    if n == 0:
        raise ValueError("retornos_abs vazio")
    abaixo = retornos_abs < limiar
    nivel_confianca = abaixo.mean()
    cauda = retornos_abs[~abaixo]
    return {
        "limiar_pontos": limiar,
        "nivel_confianca_implicado": nivel_confianca,
        "pct_barras_que_excedem": 1 - nivel_confianca,
        "n_barras_que_excedem": len(cauda),
        "es_no_limiar_pontos": cauda.mean() if len(cauda) > 0 else float("nan"),
    }


def var_es_por_faixa_horario(df: pd.DataFrame, coluna_ts_ns: str, coluna_close: str,
                             faixas: tuple[tuple[str, int, int], ...] = (
                                 ("abertura", 9, 10),
                                 ("meio", 10, 17),
                                 ("fechamento", 17, 18),
                             ),
                             niveis_confianca: tuple[float, ...] = (0.95, 0.99),
                             tz_offset_horas: int = -3) -> pd.DataFrame:
    """
    A mesma pergunta, mas segmentada por faixa de horario -- necessario
    porque o padrao em U de volume/volatilidade intradiaria (documentado
    neste projeto) quebra a suposicao de estacionariedade se as barras de
    abertura (mais voláteis) forem misturadas com as de meio de pregao
    (mais calmas) num unico quantil agregado. Sem isto, um VaR "medio"
    poderia ser otimista demais para operar na abertura e pessimista
    demais para operar no meio do dia.
    """
    ts = pd.to_datetime(df[coluna_ts_ns], unit="ns", utc=True)
    hora_local = (ts + pd.Timedelta(hours=tz_offset_horas)).dt.hour
    retornos_abs = df[coluna_close].diff().abs()

    linhas = []
    for nome, h_ini, h_fim in faixas:
        mascara = (hora_local >= h_ini) & (hora_local < h_fim)
        sub = retornos_abs[mascara].dropna()
        if sub.empty:
            continue
        tabela = var_es_realizado(sub, niveis_confianca)
        tabela.insert(0, "faixa", nome)
        tabela.insert(1, "n_barras", len(sub))
        linhas.append(tabela)
    if not linhas:
        raise ValueError("nenhuma barra caiu em nenhuma faixa de horario")
    return pd.concat(linhas, ignore_index=True)
