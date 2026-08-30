"""
Compara o log do indicador NTSL com as features calculadas em Python.

POR QUE ISTO EXISTE
-------------------
O indicador NTSL e o pipeline Python calculam a MESMA formula em dois
lugares diferentes, a partir de fontes de dado diferentes: o grafico do
Profit e o tape capturado via ProfitDLL. Se os dois nao produzem o mesmo
numero, nada do que for observado no grafico diz respeito ao que foi (ou
sera) medido em Python — e a comparacao vira opiniao.

DUAS DIVERGENCIAS SAO ESPERADAS, E ESTAO PREVISTAS POR ESCRITO
--------------------------------------------------------------
1. O OHLC do grafico inclui TODOS os negocios; o do profit-tape usa so'
   agressao (RLP e leilao fora). Um RLP que imprima nova maxima muda
   `desloc_norm` no NTSL e nao muda no Python.
2. Nao esta documentado se AgressionVolBuy/Sell excluem RLP.

Por isso a saida NAO e' um booleano "bate / nao bate": e' a distribuicao
da diferenca campo a campo. Divergencia grande em `desloc_norm` com
`imbalance` batendo aponta para (1); divergencia nos dois aponta para
(2). Esta ferramenta mede para que a causa seja diagnosticada, em vez de
suposta.

NAO consome trial: nao ha hipotese sendo testada aqui, so' duas
implementacoes sendo confrontadas.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import structlog

log = structlog.get_logger(__name__)

# Ordem CONGELADA, espelha o ConsoleLog de ntsl/absorcao_dir.ntsl.
# Mudar de um lado sem o outro produz colunas trocadas silenciosamente,
# entao o parser confere a contagem de campos linha a linha.
CAMPOS = [
    "data", "hora", "hora_bolsa", "open", "high", "low", "close",
    "vol_total", "vol_so_agressores",
    "agr_compra", "agr_venda",
    "imbalance", "desloc_norm", "absorcao_dir",
    "media", "desvio", "z",
]
PREFIXO = "ABSDIR|"
COMPARAVEIS = ["open", "high", "low", "close", "imbalance",
               "desloc_norm", "absorcao_dir", "z"]

# Serie continua ajustada: o WINFUT do grafico e' o contrato continuo,
# com preco multiplicado por um fator de rolagem (medido em 2026-08-30:
# k = 1,1578 no trecho de julho/2025). NIVEL de preco nao e' comparavel
# entre grafico e tape; RAZAO e'. Por isso o OHLC entra na tabela como
# diagnostico de escala, nunca como criterio de equivalencia.
SO_DIAGNOSTICO = {"open", "high", "low", "close"}


def _numero_ptbr(coluna: pd.Series) -> pd.Series:
    """
    Converte numero do Profit, DETECTANDO o formato em vez de assumi-lo.

        "157.722,86300000" -> 157722.863    (pt-BR: . milhar, , decimal)
        "2.5"              -> 2.5           (en-US: . decimal)

    A deteccao e' por VALOR, nao por configuracao: se o texto tem
    virgula, o ponto so' pode ser separador de milhar; se nao tem, o
    ponto e' o decimal. Assumir pt-BR sempre transformaria "2.5" em 25 —
    e o erro passaria calado, porque o numero continua sendo um numero
    valido. Assumir en-US sempre transformaria "157.722,863" em NaN, e o
    comparador ignora NaN: o campo sumiria da tabela em vez de acusar.

    Os dois erros sao silenciosos, e e' por isso que a deteccao vale o
    codigo a mais.
    """
    texto = coluna.astype(str).str.strip()
    tem_virgula = texto.str.contains(",", regex=False)
    ptbr = (texto.str.replace(".", "", regex=False)
                 .str.replace(",", ".", regex=False))
    return pd.to_numeric(texto.where(~tem_virgula, ptbr), errors="coerce")


def carregar_log(caminho: Path) -> tuple[pd.DataFrame, dict[str, int]]:
    """
    Le o dump do ConsoleLog. Tolera lixo em volta: o console do Profit
    mistura mensagens de outras fontes, e exigir arquivo limpo so'
    transferiria o trabalho de limpeza para o operador.
    """
    linhas_ok: list[list[str]] = []
    larguras_vistas: list[list[str]] = []
    n_total = 0
    n_malformadas = 0
    for bruta in caminho.read_text(encoding="utf-8", errors="replace").splitlines():
        pos = bruta.find(PREFIXO)
        if pos < 0:
            continue
        n_total += 1
        campos = bruta[pos + len(PREFIXO):].strip().split("|")
        if len(campos) != len(CAMPOS):
            n_malformadas += 1
            larguras_vistas.append(campos)
            continue
        linhas_ok.append(campos)

    if not linhas_ok:
        if n_malformadas:
            larguras = sorted({len(x) for x in larguras_vistas})
            raise SystemExit(
                f"{n_malformadas} linhas 'ABSDIR|' com contagem de campos "
                f"errada em {caminho}: vi {larguras}, esperava "
                f"{len(CAMPOS)}. O .ntsl do grafico esta desatualizado em "
                f"relacao a tools/ntsl_equivalencia.py — a ordem dos "
                f"campos e' CONGELADA e muda nos dois lados junto."
            )
        raise SystemExit(
            f"nenhuma linha '{PREFIXO}' em {caminho} — o indicador rodou "
            "com LogAtivo=1 e o console foi exportado inteiro?"
        )

    df = pd.DataFrame(linhas_ok, columns=CAMPOS)
    for c in CAMPOS[3:]:
        df[c] = _numero_ptbr(df[c])

    n_antes = len(df)
    # O manual avisa que candles passados PODEM ser reprocessados. Se
    # isso acontecer havera linhas repetidas; deduplicar e' correto, mas
    # esconder quantas houve nao e'.
    df = df.drop_duplicates(subset=["data", "hora"], keep="last")
    return df, {
        "linhas_com_prefixo": n_total,
        "malformadas": n_malformadas,
        "duplicadas": n_antes - len(df),
        "barras": len(df),
    }


def _data_easylanguage(valor: int) -> tuple[int, int, int]:
    """
    Date() do NTSL vem no formato 1AnoMesDia (manual, secao 16.15): o ano
    e' deslocado de 1900, entao 24/08/2026 chega como 1260824. Converter
    isto na mao e' onde um off-by-100-anos passaria despercebido, por isso
    tem teste proprio.
    """
    return 1900 + valor // 10000, (valor // 100) % 100, valor % 100


def comparar(log_ntsl: Path, features_parquet: Path, segundos: int,
             usar_hora_bolsa: bool = False,
             tolerancia: float = 1e-6) -> dict[str, Any]:
    ntsl, diag = carregar_log(log_ntsl)
    py = pd.read_parquet(features_parquet)

    # Chave de juncao: instante de ABERTURA DO BALDE, nao do primeiro
    # negocio. `ts_open` no parquet e' o ts do primeiro TRADE da barra, que
    # cai alguns milissegundos (ou segundos, numa barra magra) depois da
    # fronteira; `Time()` no NTSL e' a fronteira. Truncar ao periodo alinha
    # os dois pela mesma referencia.
    periodo_ns = int(segundos) * 1_000_000_000
    inicio = pd.to_datetime(
        (py["ts_open"].astype("int64") // periodo_ns) * periodo_ns,
        unit="ns", utc=True).dt.tz_convert("America/Sao_Paulo")
    py = py.assign(chave_data=inicio.dt.strftime("%Y%m%d").astype(int),
                   chave_hora=(inicio.dt.hour * 100 + inicio.dt.minute))

    coluna_hora = "hora_bolsa" if usar_hora_bolsa else "hora"
    bruto = pd.to_numeric(ntsl["data"], errors="coerce")
    partes = bruto.dropna().astype(int).map(_data_easylanguage)
    ntsl = ntsl.assign(
        chave_data=[a * 10000 + m * 100 + d for a, m, d in partes],
        chave_hora=pd.to_numeric(ntsl[coluna_hora], errors="coerce").astype(int),
    )

    juntos = ntsl.merge(py, on=["chave_data", "chave_hora"], how="inner",
                        suffixes=("_ntsl", "_py"))

    linhas = []
    for campo in COMPARAVEIS:
        col_n, col_p = f"{campo}_ntsl", f"{campo}_py"
        if campo == "z":
            col_n, col_p = "z", "z_absorcao_dir"
        if col_n not in juntos.columns or col_p not in juntos.columns:
            continue
        par = juntos[[col_n, col_p]].dropna()
        if par.empty:
            continue
        dif = (par[col_n] - par[col_p]).abs()
        linhas.append({
            "campo": campo,
            "n": len(par),
            "iguais": int((dif <= tolerancia).sum()),
            "frac_iguais": float((dif <= tolerancia).mean()),
            "dif_mediana": float(dif.median()),
            "dif_p95": float(dif.quantile(0.95)),
            "dif_max": float(dif.max()),
            "papel": "diagnostico" if campo in SO_DIAGNOSTICO else "equivalencia",
        })

    tabela = pd.DataFrame(linhas)
    log.info("ntsl_equivalencia.resumo", barras_ntsl=diag["barras"],
             barras_casadas=len(juntos), duplicadas=diag["duplicadas"])
    return {
        **diag,
        "barras_python": len(py),
        "barras_casadas": len(juntos),
        "sem_par_no_python": int(len(ntsl) - len(juntos)),
        "coluna_hora_usada": coluna_hora,
        "tolerancia": tolerancia,
        "tabela": tabela,
    }
