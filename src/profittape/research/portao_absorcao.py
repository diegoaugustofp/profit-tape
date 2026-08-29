"""
PORTAO DE HONESTIDADE do pre-registro de 2026-08-29e (absorcao direcional).

POR QUE ESTE PORTAO EXISTE
--------------------------
Dois estimadores morreram seguidos neste projeto pela MESMA causa: selecao
num extremo (2026-08-29b e 2026-08-29c). `desloc_norm` seleciona pela
posicao do fechamento entre os proprios extremos da barra — mesma familia.

O vies concreto tem nome e direcao previsivel: uma barra que fecha na minima
tem probabilidade elevada de ter tido o ultimo negocio agredido na VENDA, ou
seja, impresso no bid. O fechamento seguinte tende a voltar do bid. Isso
produz autocorrelacao negativa MECANICA entre `desloc_norm` e `ret_fut_h`,
sem edge nenhum, na direcao EXATA que a hipotese preve. Em 1m o efeito e'
proporcionalmente maior que em 5m (o tick e' o mesmo, a amplitude da barra
e' menor), o que contaminaria tambem a comparacao entre timeframes.

Um portao que rode sobre ruido "liso" (passeio continuo sem tick e sem
bounce) NAO testa esse vies — passaria com folga e nao provaria nada. Por
isso o gerador aqui e' de TAPE, negocio a negocio, com grade de tick e
spread bid/ask explicitos.

A PROPRIEDADE QUE FAZ DELE UM NULO
----------------------------------
O lado agressor de cada negocio e' sorteado de forma INDEPENDENTE do passo
do preco. Nao ha nenhuma informacao na agressao, por construcao. Logo:
qualquer IC nao-nulo que apareca e' artefato de medicao, nunca sinal.

CRITERIO (declarado antes de rodar)
-----------------------------------
PASSA somente se as 12 celulas (3 features x 2 timeframes x 2 horizontes)
sairem `descarta`. Qualquer `segue` sobre ruido puro REPROVA o desenho,
antes de gastar um unico trial.

NULO EMPIRICO (diagnostico exigido pelo proprio pre-registro)
-------------------------------------------------------------
O binario acima e' o criterio CONGELADO e roda sobre a semente declarada.
Ao lado dele, e SEM alterar criterio nenhum, o portao repete o experimento
sobre `n_semeaduras` tapes independentes e devolve a DISTRIBUICAO do IC de
cada celula sob ruido. E' isso que o pre-registro chama de nulo empirico:
o IC real deve ser comparado contra essa distribuicao, nao contra zero.
Um ponto so' de ruido nao e' um nulo; uma distribuicao e'.

NAO consome trial: nao ha dado real envolvido, `trials.json` nao e' tocado.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
import structlog

from ..features import bars, flow, normalize
from ..features.pipeline_tempo import COLUNAS_Z_TEMPO, PERIODOS
from .ic import avaliar
from .pipeline import _veredito
from .retornos import adicionar_ret_futuro
from .trials import RegistroTrials, limiar_deflacionado
from .walkforward import gerar_folds

log = structlog.get_logger(__name__)

# Horizontes CASADOS EM TEMPO DE RELOGIO (pre-registro 2026-08-29e):
# os dois timeframes olham 5 e 15 minutos a frente.
HORIZONTES_POR_PERIODO = {300: [1, 3], 60: [5, 15]}

_BUY, _SELL = 2, 3


def gerar_tape_ruido(
    n_dias: int = 25,
    segundos_sessao: int = 8 * 3600,
    trades_por_minuto: int = 20,
    tick: float = 5.0,
    preco_inicial: float = 140_000.0,
    prob_passo: float = 0.12,
    semente: int = 20260829,
) -> pd.DataFrame:
    """
    Tape sintetico com grade de tick e bounce bid/ask, no formato do curated.

    Modelo, deliberadamente simples e sem edge:
      - o livro e' um nivel inteiro `n`; bid = n*tick, ask = (n+1)*tick
        (spread de 1 tick, o tipico do WIN);
      - cada negocio sorteia o lado agressor com p=0.5 e imprime no ask
        (comprador agride) ou no bid (vendedor agride) — E' DAQUI que sai o
        bounce que o portao precisa testar;
      - depois de cada negocio, `n` anda -1/0/+1 com probabilidade
        `prob_passo` para cada lado, INDEPENDENTE do lado agredido. Essa
        independencia e' o que garante que nao ha informacao nenhuma na
        agressao.

    `prob_passo` calibra a amplitude da barra; o valor default foi escolhido
    para dar uma barra de 5m na ordem de grandeza do WIN. A amplitude
    efetivamente obtida e' reportada pelo portao, para conferencia — nao se
    confia no default, confere-se o resultado.
    """
    rng = np.random.default_rng(semente)
    n_por_dia = trades_por_minuto * (segundos_sessao // 60)
    passo_ns = int(segundos_sessao * 1_000_000_000 / n_por_dia)
    nivel_base = round(preco_inicial / tick)

    partes = []
    dia = date(2026, 1, 5)          # segunda-feira qualquer
    for _ in range(n_dias):
        # Meia-noite UTC do dia + 12h, para cair no meio do dia e o balde
        # ficar alinhado como em dado real.
        t0 = pd.Timestamp(dia, tz="UTC").value + 12 * 3600 * 1_000_000_000
        lado = rng.choice([_BUY, _SELL], size=n_por_dia)
        passo = rng.choice([-1, 0, 1], size=n_por_dia,
                           p=[prob_passo, 1 - 2 * prob_passo, prob_passo])
        # Nivel ANTES do negocio: o passo do negocio i so' afeta o i+1.
        nivel = nivel_base + np.concatenate([[0], np.cumsum(passo)[:-1]])
        preco = np.where(lado == _BUY, (nivel + 1) * tick, nivel * tick)
        partes.append(pd.DataFrame({
            "ts_ns": t0 + np.arange(n_por_dia, dtype=np.int64) * passo_ns,
            "price": preco.astype(float),
            "quantidade": rng.integers(1, 6, size=n_por_dia).astype(np.int64),
            "trade_type": lado.astype(np.int64),
            "agente_comprador": np.ones(n_por_dia, dtype=np.int64),
            "agente_vendedor": np.full(n_por_dia, 2, dtype=np.int64),
            "dt": [dia.isoformat()] * n_por_dia,
        }))
        dia += timedelta(days=1)
        if dia.weekday() >= 5:
            dia += timedelta(days=7 - dia.weekday())

    df = pd.concat(partes, ignore_index=True)
    df["dt"] = pd.Categorical(df["dt"])
    return df


def _avaliar_periodo(tape: pd.DataFrame, segundos: int, tick: float,
                     janela_minutos: int, limiar_z: float,
                     treino_min: int, teste_dias: int) -> pd.DataFrame:
    """Mesmo caminho do dado real: barras -> features -> z -> IC -> veredito."""
    barrado, _descartadas = bars.atribuir_barras_tempo(tape, segundos)
    barras_df = flow.calcular(barrado, agentes=[], tick=tick,
                              incluir_absorcao_dir=True)
    janela = max(2, (janela_minutos * 60) // segundos)
    barras_df = normalize.aplicar(barras_df, COLUNAS_Z_TEMPO, janela)

    horizontes = HORIZONTES_POR_PERIODO[segundos]
    barras_df = adicionar_ret_futuro(barras_df, horizontes)
    dias = sorted(barras_df["dia"].unique())
    folds = gerar_folds(dias, treino_min=treino_min, teste_dias=teste_dias)
    features = [f"z_{c}" for c in COLUNAS_Z_TEMPO]
    res = avaliar(barras_df, features, horizontes, folds)
    res["veredito"] = res.apply(lambda linha: _veredito(linha, limiar_z), axis=1)
    res["tf"] = PERIODOS[segundos]
    amplitude = (barras_df["high"] - barras_df["low"]) / tick
    res["range_ticks_mediano"] = float(amplitude.median())
    res["barras"] = len(barras_df)
    res["folds"] = len(folds)
    return res


def rodar_portao(
    trials_json: str | None = "data/research/trials.json",
    trials_extra: int = 12,
    n_dias: int = 25,
    janela_minutos: int = 250,
    treino_min: int = 3,
    teste_dias: int = 2,
    semente: int = 20260829,
    n_semeaduras: int = 20,
    tick: float = 5.0,
    prob_passo: float = 0.12,
    trades_por_minuto: int = 20,
) -> dict[str, Any]:
    """
    Duas coisas, nessa ordem:

    1. O PORTAO CONGELADO: uma rodada sobre a semente declarada no
       pre-registro. `passou` exige `descarta` nas 12 celulas — criterio
       duro adotado em 2026-08-29c. O limiar usado e' o que a rodada REAL
       vai enfrentar (trials acumulados + os 12 desta hipotese); um portao
       com limiar mais frouxo que o teste real nao provaria nada sobre o
       teste real.

    2. O NULO EMPIRICO: `n_semeaduras` tapes independentes, devolvendo a
       distribuicao do IC de cada celula sob ruido. Nao altera criterio
       nenhum — e' o diagnostico que o proprio pre-registro exige, para
       que o IC real seja comparado contra o vies medido em vez de contra
       zero.
    """
    from pathlib import Path as _Path

    total = 0
    if trials_json and _Path(trials_json).exists():
        total = RegistroTrials(_Path(trials_json)).total
    limiar_z = limiar_deflacionado(total + trials_extra)

    def _uma_rodada(sem: int) -> pd.DataFrame:
        tape = gerar_tape_ruido(n_dias=n_dias, tick=tick, prob_passo=prob_passo,
                                trades_por_minuto=trades_por_minuto, semente=sem)
        return pd.concat(
            [_avaliar_periodo(tape, s, tick, janela_minutos, limiar_z,
                              treino_min, teste_dias)
             for s in sorted(PERIODOS, reverse=True)],
            ignore_index=True,
        )

    log.info("portao_absorcao.inicio", limiar_z=round(limiar_z, 3),
             trials_base=total, n_semeaduras=n_semeaduras)
    tabela = _uma_rodada(semente)
    passou = bool((tabela["veredito"] == "descarta").all())
    log.info("portao_absorcao.congelado", passou=passou, celulas=len(tabela),
             segue=int((tabela["veredito"] == "segue").sum()))

    amostras = []
    for i in range(n_semeaduras):
        sem = semente + 1000 * (i + 1)
        r = _uma_rodada(sem)
        r["semente"] = sem
        amostras.append(r)
        log.info("portao_absorcao.nulo", i=i + 1, n=n_semeaduras, semente=sem)
    nulo_bruto = pd.concat(amostras, ignore_index=True)
    nulo = (
        nulo_bruto.groupby(["tf", "feature", "horizonte"], observed=True)
        .agg(ic_ruido_medio=("ic_medio", "mean"),
             ic_ruido_desvio=("ic_medio", "std"),
             ic_ruido_p05=("ic_medio", lambda s: float(np.quantile(s, 0.05))),
             ic_ruido_p95=("ic_medio", lambda s: float(np.quantile(s, 0.95))),
             segue_sob_ruido=("veredito", lambda s: int((s == "segue").sum())))
        .reset_index()
    )
    log.info("portao_absorcao.veredito", passou=passou,
             limiar_z=round(limiar_z, 3),
             segue_total_sob_ruido=int(nulo["segue_sob_ruido"].sum()),
             rodadas_de_ruido=n_semeaduras)
    return {
        "passou": passou,
        "limiar_z": limiar_z,
        "trials_base": total,
        "trials_extra": trials_extra,
        "celulas": len(tabela),
        "vereditos": tabela["veredito"].value_counts().to_dict(),
        "n_semeaduras": n_semeaduras,
        "tabela": tabela,
        "nulo_empirico": nulo,
    }
