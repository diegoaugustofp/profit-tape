"""
Regime: RLP e desequilíbrio do TOPO DO LIVRO como filtro do rompimento.
Medição de FUNIL — categoria `features`, zero trial.

POR QUE ESTES DOIS (decisão do operador, 2026-09-23)
-----------------------------------------------------
Depois de três variantes do Bollinger sem borda, a leitura do operador
foi: *"essas estratégias conseguiriam gerar retorno se descobríssemos
onde ou em qual momento elas performam melhor"*. Regime, não parâmetro.

O eixo tem que vir de MECANISMO, e a escolha caiu no que este projeto
tem e quase ninguém tem:

  RLP  — `trade_type == 13` é negócio internalizado, essencialmente
         varejo que nem chega ao livro. Uma barra sustentada por RLP
         tem composição de fluxo diferente de uma sustentada por
         agressão institucional no livro.

  BOOK — o topo do livro (`tiny_book`, melhor bid/ask com quantidade)
         no instante do sinal. Para um ROMPIMENTO o mecanismo é direto:
         romper para cima com o ask minguado é diferente de romper
         contra uma oferta grande. É resistência ao movimento, medida
         no instante exato, não inferida depois.

O QUE ESTE MÓDULO **NÃO** DECIDE
---------------------------------
Ele mede TAXA (quantos eventos cada corte deixa passar), nos DOIS
lados de cada eixo. Taxa alta significa "dá para medir", **não**
"está certo".

Escolher a direção do corte pela taxa seria conveniência disfarçada de
mecanismo. A direção tem que ser declarada por argumento, antes, e a
taxa serve só para saber se o desenho é viável no calendário
(disciplina de forward: horizonte < 6 meses).

E o número que importa depois NÃO pode sair daqui: os 42 pregões estão
queimados. Isto responde "vale ligar o forward?", não "funciona?".
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import structlog

log = structlog.get_logger(__name__)

TRADE_TYPE_RLP = 13
LADO_BID, LADO_ASK = 0, 1      # `side` do tiny_book: 0=compra(bid), 1=venda(ask)


def rlp_por_barra(trades: pd.DataFrame, barras: pd.DataFrame) -> pd.Series:
    """
    Fração de RLP no volume de cada barra de 15s, alinhada por `bar_id`.

    `rlp_frac = vol_rlp / (vol_rlp + vol_agressao)` -- mesma definição já
    usada em `features/flow.py` (não reinventar: disciplina 7.2 manda
    procurar antes de criar).
    """
    t = trades.copy()
    passo = 15 * 10**9
    t["balde"] = (t["ts_ns"] // passo) * passo
    # Vetorizado em vez de groupby.apply: a soma condicional vira uma
    # coluna zerada fora da condicao, e o groupby soma. Em 4 milhoes de
    # negocios por pregao a diferenca nao e' cosmetica.
    t["_v_rlp"] = np.where(t["trade_type"] == TRADE_TYPE_RLP, t["quantidade"], 0)
    t["_v_agr"] = np.where(t["trade_type"].isin((2, 3)), t["quantidade"], 0)
    soma = t.groupby("balde")[["_v_rlp", "_v_agr"]].sum()
    total = soma["_v_rlp"] + soma["_v_agr"]
    frac: pd.Series = (soma["_v_rlp"] / total.where(total > 0)).rename("rlp_frac")
    return frac


def topo_do_livro_por_barra(tiny: pd.DataFrame) -> pd.DataFrame:
    """
    Último estado do topo do livro em cada balde de 15s: quantidade no
    melhor bid e no melhor ask.

    "Último" e não "médio" de propósito: o que importa para o sinal é o
    livro COMO ESTAVA quando a barra fechou -- é ele que a ordem vai
    encontrar na barra seguinte. Média misturaria estados que já não
    existem.
    """
    if tiny.empty:
        return pd.DataFrame(columns=["balde", "qtd_bid", "qtd_ask", "desequilibrio"])
    t = tiny.sort_values("ts_ns", kind="stable").copy()
    passo = 15 * 10**9
    t["balde"] = (t["ts_ns"] // passo) * passo
    ultimo = t.groupby(["balde", "side"]).last().reset_index()
    bid = ultimo[ultimo["side"] == LADO_BID].set_index("balde")["quantidade"]
    ask = ultimo[ultimo["side"] == LADO_ASK].set_index("balde")["quantidade"]
    out = pd.DataFrame({"qtd_bid": bid, "qtd_ask": ask}).reset_index()
    soma = out["qtd_bid"] + out["qtd_ask"]
    # +1 = só tem bid (livro de venda vazio); -1 = só tem ask.
    out["desequilibrio"] = ((out["qtd_bid"] - out["qtd_ask"]) / soma.where(soma > 0))
    return out


@dataclass
class LinhaFunil:
    eixo: str
    corte: str
    lado: str
    candidatos: int
    com_dado: int
    passa: int

    def pct(self) -> float:
        return 100.0 * self.passa / self.com_dado if self.com_dado else float("nan")


def medir(barras: pd.DataFrame, trades: pd.DataFrame, tiny: pd.DataFrame,
         quantil: float = 0.5) -> list[LinhaFunil]:
    """
    Funil dos DOIS lados de cada eixo, por lado do sinal.

    `quantil` = corte pela MEDIANA do próprio dia por default. Mediana é
    a escolha que não precisa de calibração: divide em dois e deixa a
    taxa em ~50% por construção, então a pergunta "sobra evento?" fica
    respondida sem escolher número nenhum. Um limiar ajustado ao dado
    seria calibração, e calibração antes do mecanismo é o erro que a
    disciplina 0 nomeia.
    """
    x = barras.copy()
    passo = 15 * 10**9
    x["balde"] = (x["ts"].astype("int64") // passo) * passo if pd.api.types.is_datetime64_any_dtype(
        x["ts"]) is False else (x["ts"].dt.as_unit("s").astype("int64") * 10**9 // passo) * passo

    rlp = rlp_por_barra(trades, x)
    livro = topo_do_livro_por_barra(tiny).set_index("balde")
    x = x.join(rlp, on="balde").join(livro[["desequilibrio"]], on="balde")

    linhas: list[LinhaFunil] = []
    for lado, col in (("compra", "sinal_compra"), ("venda", "sinal_venda")):
        cand = x[col].fillna(False).astype(bool)
        n_cand = int(cand.sum())
        for eixo, coluna in (("rlp", "rlp_frac"), ("book", "desequilibrio")):
            v = x[coluna]
            com_dado = cand & v.notna()
            n_dado = int(com_dado.sum())
            if n_dado == 0:
                continue
            corte_valor = float(v[com_dado].quantile(quantil))
            for nome, mask in ((f"alto (>{corte_valor:.3f})", v > corte_valor),
                              (f"baixo (<={corte_valor:.3f})", v <= corte_valor)):
                linhas.append(LinhaFunil(
                    eixo=eixo, corte=nome, lado=lado, candidatos=n_cand,
                    com_dado=n_dado, passa=int((com_dado & mask).sum())))
    return linhas


def combinado(barras: pd.DataFrame, trades: pd.DataFrame, tiny: pd.DataFrame,
             quantil: float = 0.5) -> dict[str, int]:
    """
    Quantos eventos sobram com as DUAS cláusulas juntas, em cada uma das
    quatro combinações de direção.

    É o número que decide se a ficha é viável: somar cláusula multiplica
    a restrição, e isso já matou um desenho inteiro neste projeto (326
    eventos viraram 62 com uma linha de contexto -- 5x no calendário).
    """
    x = barras.copy()
    passo = 15 * 10**9
    x["balde"] = (x["ts"].dt.as_unit("s").astype("int64") * 10**9 // passo) * passo \
        if pd.api.types.is_datetime64_any_dtype(x["ts"]) \
        else (x["ts"].astype("int64") // passo) * passo
    x = (x.join(rlp_por_barra(trades, x), on="balde")
          .join(topo_do_livro_por_barra(tiny).set_index("balde")[["desequilibrio"]], on="balde"))
    cand = (x["sinal_compra"].fillna(False) | x["sinal_venda"].fillna(False)).astype(bool)
    com = cand & x["rlp_frac"].notna() & x["desequilibrio"].notna()
    q_rlp = float(x.loc[com, "rlp_frac"].quantile(quantil))
    q_bk = float(x.loc[com, "desequilibrio"].quantile(quantil))
    out = {"candidatos": int(cand.sum()), "com_os_dois_dados": int(com.sum())}
    for nr, mr in (("rlp_alto", x["rlp_frac"] > q_rlp), ("rlp_baixo", x["rlp_frac"] <= q_rlp)):
        for nb, mb in (("book_alto", x["desequilibrio"] > q_bk),
                      ("book_baixo", x["desequilibrio"] <= q_bk)):
            out[f"{nr}+{nb}"] = int((com & mr & mb).sum())
    return out
