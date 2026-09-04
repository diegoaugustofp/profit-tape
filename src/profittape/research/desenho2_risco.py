"""
Simula a gestao de risco do DESENHO 2 e mede o EMD.

CATEGORIA `features`. Roda na amostra de DEPURACAO e o resultado **nao
e' interpretavel como evidencia**: serve para responder uma unica
pergunta antes de congelar —

    o desenho consegue detectar um efeito plausivel?

O EMD sai de `desvio` e `n`. A media observada NAO entra na conta, e por
isso medir aqui nao e' olhar resultado. E' a regra 4 do criterio de
abandono registrado em 2026-09-03.

O QUE ESTA SIMULACAO NAO E'
---------------------------
Nao e' backtest. Nao produz curva de capital, nao desconta custo, nao
decide nada sobre a hipotese. Se alguem ler a media daqui como
resultado, estara' lendo a amostra de depuracao — que existe justamente
para nao ser lida assim.

AMBIGUIDADE INTRABARRA
----------------------
Quando a MESMA barra toca stop e alvo, o OHLC nao diz qual veio antes.
Resolvido por LIMITE PESSIMISTA: assume stop primeiro.

Medido na depuracao: stop e alvo distam 1.500 pts, e barras com essa
amplitude sao 1 em 2.260 (0,04%). Foi essa raridade que tornou o desenho
mensuravel no grafico, ao contrario da Rota B — que media a expectativa
A PARTIR DO TOQUE e por isso precisava do preco exato, so' disponivel no
tape.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import structlog

from .absorcao_barra import JANELA_CONTEXTO

log = structlog.get_logger(__name__)

# --- parametros do DESENHO 2 (rascunho, NAO congelado) ---
AFASTAMENTO = 20.0        # pts do extremo ate' o stop
STOP_MINIMO = 150.0       # abaixo disso, opera com 150
STOP_MAXIMO = 500.0       # acima disso, NAO opera
ALVO = 1000.0             # pts fixos
HORA_SAIDA = 1730         # HHMM: fecha a posicao
HORA_LIMITE_ABERTURA = 1700   # HHMM: nao abre depois
# ---------------------------------------------------------


def _nivel_de_stop(janela: pd.DataFrame, lado: int) -> float:
    """
    Extremo da janela `[t-6, t]`, INCLUINDO a barra de sinal.

    Medido na depuracao: em 70% dos eventos o extremo E' a propria barra
    de sinal — esperado, porque o evento exige `z_amplitude` alto e a
    barra de sinal e' por construcao uma das maiores da vizinhanca.
    """
    if lado < 0:                      # venda: stop ACIMA da maxima
        return float(janela["high"].max()) + AFASTAMENTO
    return float(janela["low"].min()) - AFASTAMENTO


def simular(d: pd.DataFrame) -> pd.DataFrame:
    """
    Uma linha por operacao. `d` ja' vem de `marcar_eventos(preparar(...))`
    e precisa de `hora` (HHMM) para os horarios.
    """
    d = d.reset_index(drop=True)
    hora = d["hora"].astype(int) if "hora" in d.columns else pd.Series(
        900, index=d.index)

    # Arrays em vez de `.at`: o pandas nao expressa estaticamente o dtype
    # de uma celula, entao cada `float(d.at[...])` vira um Union amplo que
    # o mypy rejeita. Mesma solucao ja usada em mae.py, remanescente_tape
    # e absorcao_barra.
    alto_ = d["high"].to_numpy(dtype=float)
    baixo_ = d["low"].to_numpy(dtype=float)
    fecha_ = d["close"].to_numpy(dtype=float)
    lados_ = d["lado"].to_numpy(dtype=np.int64)
    dias_ = d["dia"].to_numpy()
    horas_ = hora.to_numpy(dtype=np.int64)

    idx = d.index[d["evento"] & d["contexto_ok"] & (d["lado"] != 0)]
    linhas: list[dict[str, Any]] = []

    for i in idx:
        if horas_[i] > HORA_LIMITE_ABERTURA:
            continue
        lado = int(lados_[i])
        entrada = float(fecha_[i])
        janela = d.loc[max(0, i - JANELA_CONTEXTO):i]
        stop = _nivel_de_stop(janela, lado)
        distancia = abs(stop - entrada)

        if distancia > STOP_MAXIMO:
            linhas.append({"dia": dias_[i], "lado": lado,
                           "saida": "nao_operou", "risco": distancia,
                           "resultado": np.nan, "mfe_em_risco": np.nan,
                           "sem_alvo": np.nan})
            continue
        if distancia < STOP_MINIMO:
            distancia = STOP_MINIMO
            stop = entrada - distancia * lado

        alvo = entrada + ALVO * lado
        dia = dias_[i]

        saida, preco_saida, mfe = "tempo", entrada, 0.0
        # `sem_alvo`: mesmo caminho, ignorando o alvo. E' o custo do alvo
        # fixo em dia direcional -- defeito que o operador aceitou, e que
        # so' da' para avaliar se for medido junto.
        saida_sem_alvo, preco_sem_alvo = "tempo", entrada

        for j in range(i + 1, len(d)):
            if dias_[j] != dia or horas_[j] >= HORA_SAIDA:
                preco_saida = float(fecha_[j - 1])
                if saida_sem_alvo == "tempo":
                    preco_sem_alvo = preco_saida
                break
            alto, baixo = float(alto_[j]), float(baixo_[j])
            mfe = max(mfe, (alto - entrada) * lado if lado > 0
                      else (entrada - baixo) * lado * -1)
            bateu_stop = baixo <= stop if lado > 0 else alto >= stop
            bateu_alvo = alto >= alvo if lado > 0 else baixo <= alvo

            if saida_sem_alvo == "tempo" and bateu_stop:
                saida_sem_alvo, preco_sem_alvo = "stop", stop
            # PESSIMISTA: stop primeiro quando os dois batem na mesma barra
            if bateu_stop:
                saida, preco_saida = "stop", stop
                break
            if bateu_alvo:
                saida, preco_saida = "alvo", alvo
                break
        else:
            preco_saida = float(fecha_[-1])
            if saida_sem_alvo == "tempo":
                preco_sem_alvo = preco_saida

        if saida_sem_alvo == "tempo":
            preco_sem_alvo = preco_saida if saida != "alvo" else preco_sem_alvo

        linhas.append({
            "dia": dia, "lado": lado, "saida": saida,
            "risco": abs(entrada - stop),
            "resultado": (preco_saida - entrada) * lado,
            "mfe_em_risco": mfe / max(abs(entrada - stop), 1e-9),
            "sem_alvo": (preco_sem_alvo - entrada) * lado,
        })
    return pd.DataFrame(linhas)


def medir_emd(ops: pd.DataFrame, unidade: float = 244.0) -> dict[str, Any]:
    """
    EMD por lado. **So' variancia e n** — a media nao entra.

    `unidade` = amplitude media da barra de 5m, para o EMD ficar
    interpretavel: "107 pts" nao diz nada, "0,44 de uma barra" diz tudo.
    """
    from .triagem_poder import avaliar_desenho

    fora = []
    operadas = ops[ops["saida"] != "nao_operou"]
    for lado, rotulo in ((-1, "BAIXA (aqua)"), (1, "ALTA (fucsia)")):
        s = operadas.loc[operadas["lado"] == lado, "resultado"]
        fora.append(avaliar_desenho(s, unidade, rotulo))
    return {
        "por_lado": fora,
        "operacoes": len(operadas),
        "nao_operou": int((ops["saida"] == "nao_operou").sum()),
    }


def diagnostico_por_lado(ops: pd.DataFrame) -> pd.DataFrame:
    """
    O mesmo diagnostico, separado por lado.

    ATENCAO AO QUE ISTO E'. Nem toda metrica esta' na mesma distancia do
    resultado:

      GEOMETRIA (longe do resultado):
        distancia do stop, descartados por passar de 500

      PERTO DO RESULTADO:
        por_saida  -> taxa de acerto por lado
        MFE        -> o quanto o preco foi A FAVOR
        custo do alvo -> usa o retorno

    Quebrar os tres ultimos por lado responde, na pratica, "qual lado
    funciona melhor". Isso e' permitido na amostra de DEPURACAO — e 2026
    passou a ser depuracao para o desenho 2 quando foi usado para
    dimensiona-lo.

    Mas tem custo: **se um desenho futuro descartar um lado PORQUE ele
    foi pior aqui, isso e' SELECAO.** Legitima num fluxo
    depuracao/teste, e precisa ser DECLARADA — o teste vai para 2025,
    que e' o unico periodo cego que resta.

    O que NAO vale e' olhar isto e depois dizer que o desenho novo saiu
    "do mecanismo". Se saiu daqui, saiu do dado.
    """
    linhas = []
    for lado, rotulo in ((-1, "BAIXA (aqua)"), (1, "ALTA (fucsia)")):
        do_lado = ops[ops["lado"] == lado]
        op = do_lado[do_lado["saida"] != "nao_operou"]
        if op.empty:
            linhas.append({"lado": rotulo, "n": 0})
            continue
        saidas = op["saida"].value_counts()
        linhas.append({
            "lado": rotulo,
            "n": len(op),
            "descartados": int((do_lado["saida"] == "nao_operou").sum()),
            # --- geometria ---
            "risco_p50": round(float(op["risco"].median()), 0),
            "risco_p90": round(float(op["risco"].quantile(0.9)), 0),
            # --- perto do resultado ---
            "stop": int(saidas.get("stop", 0)),
            "alvo": int(saidas.get("alvo", 0)),
            "tempo": int(saidas.get("tempo", 0)),
            "mfe_p50": round(float(op["mfe_em_risco"].median()), 2),
            "mfe_p90": round(float(op["mfe_em_risco"].quantile(0.9)), 2),
            "custo_do_alvo": round(
                float((op["sem_alvo"] - op["resultado"]).mean()), 1),
        })
    return pd.DataFrame(linhas)


def diagnostico(ops: pd.DataFrame) -> dict[str, Any]:
    """Metricas obrigatorias do desenho. DIAGNOSTICO, nunca criterio."""
    op = ops[ops["saida"] != "nao_operou"]
    if op.empty:
        return {"situacao": "nenhuma operacao"}
    return {
        "por_saida": op["saida"].value_counts().to_dict(),
        "risco_p10": round(float(op["risco"].quantile(0.1)), 0),
        "risco_p50": round(float(op["risco"].median()), 0),
        "risco_p90": round(float(op["risco"].quantile(0.9)), 0),
        "mfe_em_risco_p50": round(float(op["mfe_em_risco"].median()), 2),
        "mfe_em_risco_p90": round(float(op["mfe_em_risco"].quantile(0.9)), 2),
        # custo do alvo fixo: quanto a operacao teria feito SEM ele
        "custo_do_alvo_medio": round(
            float((op["sem_alvo"] - op["resultado"]).mean()), 1),
    }
