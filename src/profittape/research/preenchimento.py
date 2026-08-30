"""
Preenchimento de stop lido do TAPE, negocio a negocio.

POR QUE ISTO EXISTE
-------------------
Dois estimadores da Rota B morreram pela MESMA causa: selecao num
extremo de barra.

  - 2026-08-29a: condicionava em `MAE_intrabar >= X` (que usa o HIGH da
    barra) e media o desfecho ate o fim. Como o high e' o pior ponto,
    o grupo "nao tocou" ficava com teto de perda X por construcao. Sobre
    ruido puro, t ~ -25.
  - 2026-08-29c: media a partir de `F` = extremo da barra de cruzamento.
    Sobre ruido puro devolveu +30 pontos com t entre 8 e 13.

A raiz e' a mesma nos dois: **o extremo de uma barra nao e' um tempo de
parada**. Ele so' e' conhecido quando a barra FECHA — usa informacao do
futuro dentro da propria barra. Um stop real nao tem esse privilegio.

O QUE MUDA COM O TAPE
---------------------
Aqui `F` e' o preco do PRIMEIRO NEGOCIO que atinge ou ultrapassa o
nivel. Isso e' um tempo de parada legitimo na filtracao dos negocios, e
o teorema da parada opcional se aplica direto: sob martingal,

    E[preco_final - F] = 0

Ou seja, o estimador construido sobre este `F` DEVE devolver zero no
ruido — por teorema, nao por esperanca. O portao de honestidade passa a
ser confirmacao de implementacao, nao descoberta de vies.

Este modulo NAO testa hipotese nenhuma: ele so' localiza o negocio. E'
infraestrutura de medicao, categoria `features`, e NAO consome trial.

DECISAO DE DESENHO: QUAIS NEGOCIOS DISPARAM
-------------------------------------------
Default `so_agressao=True`: apenas AGGRESSOR_BUYER/SELLER disparam o
stop. RLP e' varejo internalizado bilateralmente — nao consome liquidez
do livro e nao deveria acionar uma ordem stop que la' repousa. E' a
mesma regra que ja' rege o relogio das barras (`bars.py`) e o
`vol_agr`, entao manter aqui evita duas definicoes de "negocio" no
mesmo projeto.

O parametro existe porque a pergunta e' empirica, nao obvia: se a
escolha mudar o resultado de forma relevante, isso e' um achado sobre a
microestrutura e precisa aparecer, nao ficar escondido num default.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..domain.enums import TradeType

_AGRESSAO = (int(TradeType.AGGRESSOR_BUYER), int(TradeType.AGGRESSOR_SELLER))


def preparar_tape(df: pd.DataFrame, so_agressao: bool = True) -> pd.DataFrame:
    """
    Reduz o tape ao minimo necessario e garante ordem temporal.

    A ordenacao e' condicao de correcao, nao de desempenho: "o PRIMEIRO
    negocio que cruza" so' faz sentido sobre uma sequencia ordenada, e um
    tape fora de ordem devolveria um `F` posterior sem qualquer erro
    visivel.
    """
    if so_agressao:
        df = df[df["trade_type"].isin(_AGRESSAO)]
    fora = ["ts_ns", "price"]
    df = df.loc[:, fora]
    if not df["ts_ns"].is_monotonic_increasing:
        df = df.sort_values("ts_ns", kind="stable")
    return df.reset_index(drop=True)


def localizar_toque(tape: pd.DataFrame, ts_inicio: int, ts_fim: int,
                    nivel: float, lado: int) -> tuple[int, float] | None:
    """
    Primeiro negocio em (ts_inicio, ts_fim] que atinge `nivel`.

    `lado`: +1 comprado (stop ABAIXO, dispara em price <= nivel)
            -1 vendido  (stop ACIMA,  dispara em price >= nivel)

    Devolve `(ts_ns, preco)` do negocio, ou None se nunca tocar.

    O intervalo e' ABERTO no inicio: o negocio que originou a entrada nao
    pode disparar o proprio stop. Fechado no fim: o ultimo negocio da
    janela conta.

    `F` e' o preco do negocio, NAO o nivel. A diferenca e' o overshoot do
    cruzamento, e ignora-la seria supor preenchimento perfeito — que foi
    justamente o limite "otimista" do pre-registro anulado.
    """
    ts = tape["ts_ns"].to_numpy()
    # searchsorted 'right' => primeiro indice com ts_ns > ts_inicio.
    ini = int(np.searchsorted(ts, ts_inicio, side="right"))
    fim = int(np.searchsorted(ts, ts_fim, side="right"))
    if ini >= fim:
        return None

    precos = tape["price"].to_numpy()
    janela = precos[ini:fim]
    tocou = janela <= nivel if lado > 0 else janela >= nivel
    onde = np.flatnonzero(tocou)
    if len(onde) == 0:
        return None
    # `onde` indexa a JANELA; somar `ini` volta ao indice absoluto. Errar
    # isto devolve o timestamp certo com o preco de outra linha — e um
    # agregado de F so' ficaria levemente torto, sem nada parecer
    # quebrado. Foi o que a conferencia a mao pegou.
    i = ini + int(onde[0])
    return int(ts[i]), float(precos[i])


def localizar_preenchimentos(tape: pd.DataFrame,
                             entradas: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica `localizar_toque` a um conjunto de entradas.

    `entradas` precisa de: ts_entrada, ts_limite, nivel, lado.
    Devolve as mesmas linhas com `tocou`, `ts_toque` e `F`.

    Loop simples de proposito: sao centenas de entradas, nao milhoes, e
    uma versao vetorizada trocaria clareza por desempenho que nao falta.
    """
    obrigatorias = {"ts_entrada", "ts_limite", "nivel", "lado"}
    faltando = obrigatorias - set(entradas.columns)
    if faltando:
        raise ValueError(f"entradas sem colunas {sorted(faltando)}")

    tocou: list[bool] = []
    ts_toque: list[float] = []
    precos: list[float] = []
    # Arrays em vez de itertuples: o pandas nao expressa estaticamente o
    # dtype de uma celula, entao cada `int(linha.x)` vira um Union amplo
    # que o mypy rejeita. Mesma solucao ja usada em mae.py.
    ts_ent = entradas["ts_entrada"].to_numpy(dtype=np.int64)
    ts_lim = entradas["ts_limite"].to_numpy(dtype=np.int64)
    niveis = entradas["nivel"].to_numpy(dtype=float)
    lados = entradas["lado"].to_numpy(dtype=np.int64)

    for j in range(len(entradas)):
        r = localizar_toque(tape, int(ts_ent[j]), int(ts_lim[j]),
                            float(niveis[j]), int(lados[j]))
        tocou.append(r is not None)
        # NaN e nao pd.NA: mantem a coluna float e evita que um `object`
        # se propague silenciosamente para as contas do estimador.
        ts_toque.append(float(r[0]) if r else float("nan"))
        precos.append(r[1] if r else float("nan"))

    return entradas.assign(tocou=tocou, ts_toque=ts_toque, F=precos)
