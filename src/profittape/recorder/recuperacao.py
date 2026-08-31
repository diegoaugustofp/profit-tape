"""
Recuperacao de tape por `GetHistoryTrades`, e a VERIFICACAO dela.

A PERGUNTA
----------
Se o `record` ficar dias parado — crash, maquina desligada, feriado mal
configurado — da' para recuperar o tape perdido? O incidente de
2026-08-25 (processo morreu com exit code 1, causa nunca confirmada)
deixou um pregao incompleto que ate hoje nao foi preenchido.

O QUE O MANUAL DIZ, E O QUE ELE NAO DIZ
---------------------------------------
Sao DUAS funcoes com limites diferentes, e confundi-las custou uma
resposta errada em 2026-08-31:

    RequestSerieHistory   series de BARRAS      WIN: 8 dias (tabela)
    GetHistoryTrades      NEGOCIOS individuais  data inicial ate 30 dias
                                                (via NL_HISTORY_PERIOD_LIMIT)

O limite de 30 dias aparece so' na descricao do codigo de erro, nao numa
tabela por ativo como a dos 8 dias. Pode haver limite especifico do WIN
que o manual nao tabela.

E `THistoryTradeCallback` entrega os MESMOS campos de
`TNewTradeCallback` (preco, quantidade, agentes, `nTradeType`), menos o
`bEdit`, que so' faz sentido em tempo real.

POR QUE ISTO E' UMA VERIFICACAO E NAO UM IMPORTADOR
---------------------------------------------------
"Esta documentado" e "funciona" sao coisas diferentes. So' em
2026-08-31, `AgressionVolBuy/Sell` devolveu ZERO em 2.001 barras sem
erro nenhum, e `QuantityVol` funcionou na mesma barra.

Entao o primeiro uso desta funcao NAO e' preencher buraco: e' pedir um
dia que JA' TEMOS e comparar negocio a negocio. Se bater, a recuperacao
e' confiavel. Se nao bater, saber ANTES vale mais do que um parquet
preenchido com dado silenciosamente diferente.

Categoria `features`: nao consome trial.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

log = structlog.get_logger(__name__)

# Chave de identidade de um negocio. `nTradeNumber` e' o numero de serie
# do trade e deveria bastar sozinho, mas comparar tambem preco/quantidade
# detecta o caso em que a numeracao coincide e o CONTEUDO nao — que e'
# exatamente a falha que passaria despercebida.
CHAVE = ["trade_number", "price", "quantidade"]


@dataclass
class ComparacaoDia:
    dia: str
    n_curated: int = 0
    n_historico: int = 0
    so_no_curated: int = 0
    so_no_historico: int = 0
    em_ambos: int = 0
    divergencias: list[dict[str, Any]] = field(default_factory=list)

    @property
    def confere(self) -> bool:
        return (self.so_no_curated == 0 and self.so_no_historico == 0
                and not self.divergencias)

    def resumo(self) -> dict[str, Any]:
        return {
            "dia": self.dia,
            "n_curated": self.n_curated,
            "n_historico": self.n_historico,
            "em_ambos": self.em_ambos,
            "so_no_curated": self.so_no_curated,
            "so_no_historico": self.so_no_historico,
            "divergencias": len(self.divergencias),
            "confere": self.confere,
        }


def comparar(curated: pd.DataFrame, historico: pd.DataFrame,
             dia: str) -> ComparacaoDia:
    """
    Compara os dois conjuntos pela chave, e depois o CONTEUDO das linhas
    que casaram.

    Contar linhas nao basta: dois conjuntos podem ter o mesmo tamanho e
    conteudo diferente. A segunda etapa — conferir `trade_type` e agentes
    nas linhas casadas — e' o que pega "veio tudo, mas sem a agressao",
    que e' a falha mais provavel dado o historico deste projeto.
    """
    c = ComparacaoDia(dia=dia, n_curated=len(curated), n_historico=len(historico))
    if curated.empty or historico.empty:
        c.so_no_curated = len(curated)
        c.so_no_historico = len(historico)
        return c

    cur = curated.set_index(CHAVE, drop=False)
    his = historico.set_index(CHAVE, drop=False)
    idx_cur, idx_his = set(cur.index), set(his.index)

    c.so_no_curated = len(idx_cur - idx_his)
    c.so_no_historico = len(idx_his - idx_cur)
    comuns = idx_cur & idx_his
    c.em_ambos = len(comuns)

    # Conteudo das linhas que casaram. `trade_type` primeiro: e' o campo
    # da agressao, o unico que ja' voltou zerado em silencio antes.
    for campo in ("trade_type", "agente_comprador", "agente_vendedor"):
        if campo not in cur.columns or campo not in his.columns:
            continue
        a = cur.loc[list(comuns), campo]
        b = his.loc[list(comuns), campo]
        difere = int((a.to_numpy() != b.to_numpy()).sum())
        if difere:
            c.divergencias.append({
                "campo": campo,
                "linhas_diferentes": difere,
                "pct": round(100.0 * difere / max(len(comuns), 1), 3),
            })
    return c


def carregar_curated_do_dia(curated: Path, symbol: str,
                            dia: date) -> pd.DataFrame:
    from ..features.pipeline import _carregar_dia

    pasta = curated / "trade" / f"dt={dia.isoformat()}"
    if not pasta.exists():
        raise SystemExit(
            f"nao ha' curated para {dia.isoformat()} em {pasta}.\n"
            "  A verificacao precisa de um dia que voce JA' TEM — comparar\n"
            "  com o vazio nao mede nada."
        )
    return _carregar_dia(pasta, symbol)


def normalizar_historico(linhas: list[dict[str, Any]]) -> pd.DataFrame:
    """
    Poe o retorno do callback no mesmo formato do curated.

    `pwcDate` vem como `DD/MM/YYYY HH:mm:SS.ZZZ` — formato diferente do
    `ts_ns` do curated, e converter errado produziria "nenhum negocio em
    comum" que pareceria falha da API.
    """
    if not linhas:
        return pd.DataFrame(columns=[*CHAVE, "ts_ns", "trade_type"])
    df = pd.DataFrame(linhas)
    # `.astype("int64")` sozinho devolve a unidade INTERNA da coluna, que
    # no pandas 3 e' microssegundo — nao nanossegundo. O nome `ts_ns` nao
    # protege de nada: o valor sairia 1.000x menor e NENHUM negocio
    # casaria, o que pareceria falha da API em vez de bug de conversao.
    # Pego pelo teste, que fixava o valor esperado em ns.
    df["ts_ns"] = pd.to_datetime(
        df["data"], format="%d/%m/%Y %H:%M:%S.%f").astype("datetime64[ns]").astype("int64")
    return df.sort_values("ts_ns").reset_index(drop=True)
