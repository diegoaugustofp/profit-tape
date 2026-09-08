"""
Simulador de replay barra a barra — Fase 1 do pre-registro DeepScalper
(docs/RESEARCH_PLANO.md, 2026-09-07; decisao de custo 2026-09-08).

CONVENCOES (todas iguais ao EA, de proposito):
- Fonte: features.parquet (uma linha por barra de volume, bar_id continuo).
  Dia = data UTC de ts_open (mesma regra do writer: dt e' UTC).
- Fill: CLOSE da barra em que a decisao e' tomada, nas duas pernas.
  `custo_pontos` (11) e' ida-e-volta e JA' INCLUI spread (decisao do
  operador, 2026-09-08) -- nao ha' modelo de book aqui. Cobrado inteiro
  no fechamento, como em risco.py.
- Risco: reusa ea.risco.GestorDeRisco (stop catastrofico no close, saida
  por tempo, circuit breaker). Nao reimplementa: divergencia na
  conferencia so' pode vir da barra ou do sinal.
- Zeragem: ultimo close do dia (encerrar_dia do EA). Posicao aberta na
  ultima barra fecha na mesma barra com -custo.
- Sem piramide, sem inversao direta (igual a decidir()): sinal contrario
  com posicao aberta = ZERAR, e so' na barra seguinte pode abrir.

O que a politica ve (Obs) e' SO' a barra atual + estado privado. Ela nao
recebe o DataFrame -- e' isso que verificar_lookahead() fiscaliza.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
import structlog

from ..ea.config import RiscoConfig, SinalConfig
from ..ea.decisao import Acao, decidir
from ..ea.risco import GestorDeRisco
from ..features import normalize

log = structlog.get_logger(__name__)

SEM_HORIZONTE = 10**9

# Colunas do features.parquet que OLHAM PARA FRENTE por construcao
# (labels.py). Nunca entram em Obs.barra: a politica nao tem como le-las
# por engano. Se surgir coluna futura nova, entra aqui -- e' o unico
# lugar.
COLUNAS_FUTURAS = ("label", "label_valida", "label_ambigua", "ret_h", "t_evento")


@dataclass(frozen=True)
class Obs:
    dia: str
    idx: int                 # posicao da linha DENTRO do dia (0 = primeira)
    n_barras_dia: int
    bar_id: int              # continuo do features.parquet
    bar_local: int           # bar_id - primeiro bar_id do dia = balde do EA
                             # (nao denso: balde pulado por trade gigante
                             # conta como barra para a saida por tempo)
    close: float
    pos: int                 # +1 / 0 / -1
    barras_desde_entrada: int
    barra: pd.Series         # a linha do features.parquet desta barra, e SO' ela


@dataclass(frozen=True)
class Ordem:
    lado: int                # +1 compra, -1 venda, 0 zerar
    horizonte: int | None = None   # barras ate' saida por tempo; None = sem


Politica = Callable[[Obs], Ordem | None]


@dataclass(frozen=True)
class Regras:
    custo_pontos: float = 11.0
    risco: RiscoConfig | None = None
    circuit_breaker: bool = True


def dia_de_ts(ts_ns: int) -> str:
    return datetime.fromtimestamp(ts_ns / 1e9, tz=UTC).strftime("%Y-%m-%d")


def preparar(barras: pd.DataFrame,
             z_por_dia: list[str] | None = None,
             janela_z: int = 50) -> pd.DataFrame:
    """
    Ordena por bar_id, deriva `dia` e, se pedido, RECALCULA z_{col} com a
    janela zerando a cada dia -- e' o que o EA faz ao vivo (deque por
    processo, normalize.zscore_rolante espelhado em ea/sinal.py). O
    features.parquet tem z continuo entre dias; para conferir contra o
    ea-replay-lote as duas convencoes precisam ser a mesma.
    """
    b = barras.sort_values("bar_id", kind="stable").reset_index(drop=True).copy()
    b["dia"] = b["ts_open"].map(dia_de_ts)
    for col in z_por_dia or []:
        if col not in b.columns:
            raise KeyError(f"coluna {col!r} nao existe para recalcular z por dia")
        b[f"z_{col}"] = b.groupby("dia", sort=False)[col].transform(
            lambda s: normalize.zscore_rolante(s, janela_z))
    return b


def politica_ea(sinais: list[SinalConfig], janela_z: int = 50) -> Politica:
    """
    A regra do EA (Rota A) como politica: zerado -> decidir() sobre o
    z_agf_{agent_id} da barra; com posicao -> None (o gestor manda: saida
    por tempo/stop). NaN na feature = aquecimento, nao age.
    """
    del janela_z  # a janela ja' esta' aplicada nas colunas z_*

    def _p(obs: Obs) -> Ordem | None:
        if obs.pos != 0:
            return None
        for s in sinais:
            valor = obs.barra.get(f"z_agf_{s.agent_id}")
            if valor is None or valor != valor:
                continue
            d = decidir(s, valor_atual=float(valor), posicao_atual=0)
            if d.acao == Acao.COMPRAR:
                return Ordem(+1, s.horizonte)
            if d.acao == Acao.VENDER:
                return Ordem(-1, s.horizonte)
        return None

    return _p


class Simulador:
    def __init__(self, barras: pd.DataFrame, regras: Regras | None = None) -> None:
        if "dia" not in barras.columns:
            raise ValueError("chame preparar() antes: falta a coluna dia")
        self.barras = barras
        self.regras = regras or Regras()
        self.risco = self.regras.risco or RiscoConfig()

    def rodar(self, politica: Politica) -> dict[str, Any]:
        operacoes: list[dict[str, Any]] = []
        decisoes: list[tuple[int, int]] = []     # (bar_id, lado da ordem)
        por_dia: list[dict[str, Any]] = []
        visiveis = [c for c in self.barras.columns if c not in COLUNAS_FUTURAS]
        for dia, grupo in self.barras.groupby("dia", sort=True):
            g = grupo.reset_index(drop=True)
            g_vis = g[visiveis]
            gestor = GestorDeRisco(self.risco, self.regras.custo_pontos,
                                   ignorar_circuit_breaker=not self.regras.circuit_breaker)
            n = len(g)
            pos = 0
            local_entrada = -1
            primeiro = int(g["bar_id"].iloc[0])
            for i in range(n):
                linha = g_vis.iloc[i]
                close = float(linha["close"])
                bar_id = int(linha["bar_id"])
                local = bar_id - primeiro
                if gestor.em_posicao():
                    motivo = gestor.motivo_de_saida(local, close)
                    if motivo is None:
                        o = politica(Obs(str(dia), i, n, bar_id, local, close, pos,
                                         local - local_entrada, linha))
                        if o is not None and (o.lado == 0 or o.lado == -pos):
                            motivo = ("saida pela politica" if o.lado == 0
                                      else "sinal virou contra a posicao")
                    if motivo is not None:
                        self._fechar(gestor, close, local, motivo, operacoes, str(dia))
                        pos = 0
                    continue
                if not gestor.pode_abrir():
                    continue
                o = politica(Obs(str(dia), i, n, bar_id, local, close, 0, 0, linha))
                if o is None or o.lado == 0:
                    continue
                pos = o.lado
                local_entrada = local
                decisoes.append((bar_id, o.lado))
                gestor.registrar_abertura(o.lado, close, local,
                                          o.horizonte if o.horizonte is not None
                                          else SEM_HORIZONTE)
            if gestor.em_posicao():
                ultimo = float(g.iloc[n - 1]["close"])
                self._fechar(gestor, ultimo, int(g["bar_id"].iloc[n - 1]) - primeiro,
                             "encerramento do dia", operacoes, str(dia))
            por_dia.append({"dia": str(dia), "barras": n,
                            "n_operacoes": len(gestor.historico_pnl),
                            "pnl_dia": round(gestor.pnl_dia_pontos, 1),
                            "bloqueado": gestor.bloqueado})
        # idx_entrada/idx_saida sao o BALDE local (= bar_id do ea-replay-lote)
        ops = pd.DataFrame(operacoes, columns=[
            "dia", "seq_no_dia", "lado", "preco_entrada", "preco_saida",
            "idx_entrada", "idx_saida", "pnl_liquido", "motivo"])
        return {"operacoes": ops, "por_dia": pd.DataFrame(por_dia),
                "decisoes": decisoes,
                "pnl_total": float(ops["pnl_liquido"].sum()) if len(ops) else 0.0}

    @staticmethod
    def _fechar(gestor: GestorDeRisco, preco: float, idx: int, motivo: str,
                operacoes: list[dict[str, Any]], dia: str) -> None:
        gestor.registrar_fechamento(preco, idx, motivo)
        op = gestor.historico_detalhado[-1]
        operacoes.append({"dia": dia, "seq_no_dia": len(gestor.historico_pnl),
                          "lado": op.lado, "preco_entrada": op.preco_entrada,
                          "preco_saida": op.preco_saida,
                          "idx_entrada": op.bar_id_entrada, "idx_saida": idx,
                          "pnl_liquido": op.pnl_liquido, "motivo": motivo})


# ----------------------------------------------------------- verificador 7.3
FabricaDePolitica = Callable[[pd.DataFrame], Politica]


def verificar_lookahead(barras: pd.DataFrame, fabrica: FabricaDePolitica,
                        n_cortes: int = 12, seed: int = 0) -> dict[str, Any]:
    """
    Causalidade da POLITICA: a decisao na barra t nao pode depender de
    nenhuma barra > t. Teste: roda no dado inteiro e em `n_cortes`
    prefixos truncados; as decisoes ate' o corte tem de ser identicas.

    `fabrica(df)` constroi a politica A PARTIR do DataFrame em que ela vai
    rodar -- assim uma politica que le `df.iloc[t+1]` por closure le o
    prefixo truncado e reprova (ver teste dedicado). Circuit breaker
    desligado aqui: com ele, uma politica que perde 3 vezes cedo para de
    decidir e o teste ficaria cego.

    O QUE ISTO NAO COBRE: coluna do features.parquet calculada com futuro
    (ex.: rolling sem shift). Isso e' auditoria do PIPELINE de features
    (normalize.py e' o unico lugar com janela; labels.py e' declaradamente
    futuro e fica fora de Obs via COLUNAS_FUTURAS), nao da politica.
    """
    regras = Regras(circuit_breaker=False)
    inteiro = Simulador(barras, regras).rodar(fabrica(barras))["decisoes"]
    rng = np.random.default_rng(seed)
    n = len(barras)
    cortes = sorted(set(int(c) for c in rng.integers(2, max(3, n), size=n_cortes)))
    divergencias: list[dict[str, Any]] = []
    for corte in cortes:
        prefixo = barras.iloc[:corte].reset_index(drop=True)
        bar_corte = int(barras["bar_id"].iloc[corte - 1])
        antes = [d for d in inteiro if d[0] <= bar_corte]
        trunc = Simulador(prefixo, regras).rodar(fabrica(prefixo))["decisoes"]
        if antes != trunc:
            primeira = next((a for a, b in zip(antes, trunc, strict=False) if a != b),
                            (antes[len(trunc):] or trunc[len(antes):] or [None])[0])
            divergencias.append({"corte": corte, "bar_id_corte": bar_corte,
                                 "primeira_divergencia": primeira})
    return {"ok": not divergencias, "cortes": len(cortes),
            "decisoes_no_inteiro": len(inteiro), "divergencias": divergencias}


# ---------------------------------------------------------- conferencia EA
def conferir_com_replay(sim_ops: pd.DataFrame, replay_ops: pd.DataFrame,
                        tolerancia_pts: float = 0.5) -> dict[str, Any]:
    """
    Casa operacao a operacao por (dia, barra de entrada, lado). O
    ea-replay-lote grava bar_id POR DIA (o construtor ao vivo reinicia a
    cada processo), que e' o `idx_entrada` do simulador.
    """
    r = replay_ops.rename(columns={"bar_id_entrada": "idx_entrada"})
    chave = ["dia", "idx_entrada", "lado"]
    m = sim_ops.merge(r[[*chave, "pnl_liquido", "preco_entrada", "preco_saida"]],
                      on=chave, how="outer", suffixes=("_sim", "_ea"), indicator=True)
    casadas = m[m["_merge"] == "both"]
    dif = (casadas["pnl_liquido_sim"] - casadas["pnl_liquido_ea"]).abs()
    por_dia = (m.assign(so_sim=m["_merge"] == "left_only",
                        so_ea=m["_merge"] == "right_only",
                        ambas=m["_merge"] == "both")
                .groupby("dia")[["ambas", "so_sim", "so_ea"]].sum().reset_index())
    return {
        "n_sim": len(sim_ops), "n_ea": len(replay_ops),
        "casadas": len(casadas),
        "so_sim": int((m["_merge"] == "left_only").sum()),
        "so_ea": int((m["_merge"] == "right_only").sum()),
        "casadas_fora_da_tolerancia": int((dif > tolerancia_pts).sum()),
        "max_dif_pnl_casadas": float(dif.max()) if len(dif) else 0.0,
        "pnl_sim": float(sim_ops["pnl_liquido"].sum()) if len(sim_ops) else 0.0,
        "pnl_ea": float(replay_ops["pnl_liquido"].sum()) if len(replay_ops) else 0.0,
        "por_dia": por_dia,
        "nao_casadas": m[m["_merge"] != "both"][[*chave, "_merge"]].head(40),
    }
