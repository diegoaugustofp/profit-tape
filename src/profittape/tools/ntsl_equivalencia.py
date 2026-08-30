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

import numpy as np
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
    if not caminho.exists():
        # 40 linhas de traceback para um caminho errado nao ajudam
        # ninguem. Caso real: o arquivo tinha cedilha no nome.
        raise SystemExit(
            f"nao achei {caminho}\n"
            "  - o nome do dump costuma ter acento (ex.: automacao.txt vs "
            "automação.txt)\n"
            "  - no PowerShell, ponha o caminho entre aspas"
        )

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


def _atribuir_divergencia(juntos: pd.DataFrame) -> dict[str, Any]:
    """
    DECOMPOE a divergencia de `desloc_norm` em numerador e denominador.

    DUAS EXPLICACOES ANTERIORES FORAM REFUTADAS POR ESTA FUNCAO
    -----------------------------------------------------------
    (1) "o erro cresce com a fracao de VOLUME de RLP da barra".
        Medido em 24/07/2026: correlacao -0,12, e o quartil de MAIOR RLP
        com erro ZERO. Refutada.

    (2) "o erro vem de um print de RLP TOCAR um extremo, mudando
        (high-low)". Medido: 79 das 80 barras tem os extremos IDENTICOS
        e o erro mediano nesse grupo e' 0,0137 — o erro geral. Refutada.

    Se o denominador bate, a diferenca esta no NUMERADOR. `open` e
    `close` sao o PRIMEIRO e o ULTIMO negocio da barra: um print de RLP
    dentro da faixa nao mexe em maxima nem minima, mas muda a abertura
    ou o fechamento se for o primeiro ou o ultimo. Com ~28% do volume em
    RLP, isso acontece com frequencia — e explica os 41% de barras
    exatas (aquelas em que nem o primeiro nem o ultimo negocio foi RLP).

    Esta versao mede numerador e denominador SEPARADAMENTE, em ticks.
    Nao ha para onde a causa fugir: ou o numerador diverge, ou o
    denominador, ou os dois.
    """
    precisa = ("desloc_norm_ntsl", "desloc_norm_py", "high_ntsl", "high_py",
               "low_ntsl", "low_py", "open_ntsl", "open_py",
               "close_ntsl", "close_py")
    faltando = [c for c in precisa if c not in juntos.columns]
    if faltando:
        return {"situacao": f"colunas ausentes: {faltando}"}

    d = juntos.dropna(subset=list(precisa))
    if len(d) < 8:
        return {"situacao": f"amostra pequena demais ({len(d)} barras)"}

    # k robusto: so' a RAZAO entre niveis e' comparavel (serie ajustada).
    k = float((d["close_ntsl"] / d["close_py"]).median())
    num_n = (d["close_ntsl"] - d["open_ntsl"]) / k
    num_p = d["close_py"] - d["open_py"]
    den_n = (d["high_ntsl"] - d["low_ntsl"]) / k
    den_p = d["high_py"] - d["low_py"]

    # Tick estimado pela GRADE DE PRECO do parquet (gcd das diferencas
    # entre precos distintos), nao pelas amplitudes: a primeira versao
    # usou o gcd das amplitudes e, num caso onde todas valiam o mesmo,
    # devolveu a propria amplitude como "tick".
    precos = np.unique(np.concatenate(
        [d["open_py"], d["high_py"], d["low_py"], d["close_py"]]))
    difs = np.diff(precos)
    difs = np.round(difs[difs > 0]).astype(np.int64)
    tick = float(np.gcd.reduce(difs)) if len(difs) else 1.0
    if tick <= 0:
        tick = 1.0

    # Classificacao por tolerancia RELATIVA ao denominador — que e' a
    # escala que importa para a razao — e nao em ticks: assim ela nao
    # depende de o tick ter sido bem estimado.
    escala = den_p.abs().where(den_p.abs() > 0, 1.0)
    dif_num = (num_n - num_p).abs()
    dif_den = (den_n - den_p).abs()
    num_difere = dif_num > 1e-3 * escala
    den_difere = dif_den > 1e-3 * escala
    erro = (d["desloc_norm_ntsl"] - d["desloc_norm_py"]).abs()

    def mediana(mask: pd.Series[bool]) -> float | None:
        return round(float(erro[mask].median()), 6) if mask.any() else None

    return {
        "n": len(d),
        "k_estimado": round(k, 6),
        "tick_estimado": round(tick, 4),
        "barras_so_numerador_difere": int((num_difere & ~den_difere).sum()),
        "barras_so_denominador_difere": int((~num_difere & den_difere).sum()),
        "barras_ambos_diferem": int((num_difere & den_difere).sum()),
        "barras_nada_difere": int((~num_difere & ~den_difere).sum()),
        "erro_mediano_nada_difere": mediana(~num_difere & ~den_difere),
        "erro_mediano_so_numerador": mediana(num_difere & ~den_difere),
        "dif_numerador_mediana_ticks": round(
            float(dif_num[num_difere].median() / tick), 3)
        if num_difere.any() else None,
        "dif_denominador_mediana_ticks": round(
            float(dif_den[den_difere].median() / tick), 3)
        if den_difere.any() else None,
    }


def _barras_na_borda(juntos: pd.DataFrame, py: pd.DataFrame,
                     janela_z: int) -> dict[str, Any]:
    """
    Avisa quando o `z` NAO e' comparavel por construcao.

    O z do NTSL usa a janela do GRAFICO, que costuma ter meses de
    historico. O do Python usa a janela do PARQUET. Nas primeiras
    `janela_z` barras do parquet as duas janelas tem CONTEUDO diferente
    — o Python normaliza contra menos passado, ou contra passado nenhum
    (NaN).

    Caso real (2026-08-30): a sobreposicao caiu em 24/07, o primeiro dia
    do parquet. 25 das 80 celulas sairam NaN e as 55 restantes usavam
    janelas diferentes. Divergencia de z ali nao diz NADA sobre a
    implementacao — e sem este aviso seria lida como bug.
    """
    if "bar_id" not in py.columns or py.empty:
        return {"situacao": "sem bar_id no parquet"}
    limite = int(py["bar_id"].min()) + janela_z
    if "bar_id" not in juntos.columns:
        return {"situacao": "sem bar_id no merge"}
    na_borda = int((juntos["bar_id"] < limite).sum())
    return {
        "barras_casadas_na_borda": na_borda,
        "janela_z": janela_z,
        "z_comparavel": na_borda == 0,
        "aviso": (
            "" if na_borda == 0 else
            f"{na_borda} das {len(juntos)} barras casadas estao nas "
            f"primeiras {janela_z} barras do parquet: ali o z do Python "
            "normaliza contra uma janela mais curta que a do grafico, "
            "entao a divergencia de z NAO indica erro de implementacao. "
            "Use um dia mais distante do inicio do parquet."
        ),
    }


def comparar(log_ntsl: Path, features_parquet: Path, segundos: int,
             usar_hora_bolsa: bool = False,
             janela_z: int = 50,
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
    atribuicao = _atribuir_divergencia(juntos)
    borda = _barras_na_borda(juntos, py, janela_z)
    log.info("ntsl_equivalencia.resumo", barras_ntsl=diag["barras"],
             barras_casadas=len(juntos), duplicadas=diag["duplicadas"])
    return {
        **diag,
        "barras_python": len(py),
        "barras_casadas": len(juntos),
        "sem_par_no_python": int(len(ntsl) - len(juntos)),
        "coluna_hora_usada": coluna_hora,
        "tolerancia": tolerancia,
        "atribuicao_rlp": atribuicao,
        "z_na_borda": borda,
        "tabela": tabela,
    }
