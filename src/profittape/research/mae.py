"""
Analise de MAE (Maximum Adverse Excursion) por operacao -- responde uma
pergunta especifica que a tabela de quintis nao responde: o stop
catastrofico e' so' seguro de cauda (raramente tocado), ou ja esta
mordendo de verdade dentro da janela real de holding do sinal?

NAO consome trial: e' engenharia de risco sobre um sinal JA' validado
(mesmo espirito de quintis.py -- traducao pratica, nao hipotese nova).

Metodologia:
  - Para cada barra t onde a condicao de entrada dispara (MESMA regra de
    ea/decisao.py: contrarian ou momentum, no extremo do threshold_entrada
    -- nao reimplementada, replicada aqui so' para o dado ja' vir em
    dataframe em vez de streaming), abre uma posicao simulada de lado L.
  - MAE_close: pior excursao contra a posicao usando o CLOSE de cada uma
    das h barras seguintes -- e' EXATAMENTE o que GestorDeRisco.
    motivo_de_saida() avalia no sistema real (checagem a cada fechamento
    de barra, nao intrabar continuo). Este e' o numero PRIMARIO: o que o
    nosso sistema de verdade teria visto.
  - MAE_intrabar: pior excursao usando o LOW (se comprado) ou HIGH (se
    vendido) de cada barra -- limite mais severo, o que uma ordem de stop
    reagindo em tempo real (nao so' no fechamento) poderia ter sofrido.
    Reportado como referencia adicional -- nosso sistema real NAO monitora
    intrabar, entao este numero e' teorico/conservador, nao o que
    aconteceria na pratica hoje.
  - Nunca cruza o dia (mesmo purge estrutural de retornos.py -- as ultimas
    h barras de cada pregao ficam de fora, sem futuro intra-dia).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def _sinal_de_entrada(z: pd.Series, threshold: float, direcao: str) -> pd.Series:
    """+1 = compra, -1 = venda, 0 = nao dispara. Mesma regra de
    ea/decisao.py::decidir(), replicada para dataframe (nao streaming)."""
    limiar = abs(threshold)
    extremo_alto = z >= limiar
    extremo_baixo = z <= -limiar
    if direcao == "contrarian":
        quer_vender, quer_comprar = extremo_alto, extremo_baixo
    elif direcao == "momentum":
        quer_vender, quer_comprar = extremo_baixo, extremo_alto
    else:
        raise ValueError(f"direcao desconhecida: {direcao!r}")
    return pd.Series(np.select([quer_comprar, quer_vender], [1, -1], default=0),
                     index=z.index)


def analisar_mae(arquivo_features: Path, feature: str, horizonte: int,
                 threshold_entrada: float, direcao: str,
                 stop_catastrofico_pontos: float, saida: Path) -> dict:
    df = pd.read_parquet(arquivo_features)
    if "dia" not in df.columns:
        df["dia"] = pd.to_datetime(df["ts_close"], unit="ns", utc=True).dt.date

    lado = _sinal_de_entrada(df[feature], threshold_entrada, direcao)
    triggers = df.index[lado != 0]
    if len(triggers) == 0:
        raise SystemExit(f"nenhum trigger de {feature}@h{horizonte} "
                         f"threshold={threshold_entrada} direcao={direcao}")

    linhas = []
    for i in triggers:
        dia = df.at[i, "dia"]
        L = lado.at[i]
        entrada = df.at[i, "close"]
        # janela [i+1, i+horizonte] -- nunca atravessa o dia (mesmo purge
        # estrutural de retornos.py). Se a janela sair do dia, descarta.
        janela = df.loc[i + 1:i + horizonte]
        janela = janela[janela["dia"] == dia]
        if len(janela) < horizonte:
            continue   # janela incompleta (fim do dia) -- sem futuro valido

        # MAE_close: pior excursao usando CLOSE de cada barra da janela --
        # o que GestorDeRisco.motivo_de_saida() de fato avalia hoje.
        excursao_close = (entrada - janela["close"]) * L
        mae_close = excursao_close.max()

        # MAE_intrabar: pior excursao usando LOW (comprado) / HIGH (vendido)
        # -- limite teorico mais severo, NAO monitorado pelo sistema hoje.
        pior_preco_intrabar = janela["low"] if L > 0 else janela["high"]
        excursao_intrabar = (entrada - pior_preco_intrabar) * L
        mae_intrabar = excursao_intrabar.max()

        pnl_final = (janela["close"].iloc[-1] - entrada) * L

        linhas.append({
            "dia": dia, "lado": L, "entrada": entrada,
            "mae_close": mae_close, "mae_intrabar": mae_intrabar,
            "pnl_final_h": pnl_final,
            "teria_batido_stop": mae_close >= stop_catastrofico_pontos,
        })

    r = pd.DataFrame(linhas)
    if r.empty:
        raise SystemExit("nenhuma janela completa (todos os triggers "
                         "ficaram no fim do dia) -- amostra insuficiente")

    n = len(r)
    n_batido = int(r["teria_batido_stop"].sum())
    resumo = {
        "feature": feature, "horizonte": horizonte,
        "threshold_entrada": threshold_entrada, "direcao": direcao,
        "stop_catastrofico_pontos": stop_catastrofico_pontos,
        "n_triggers": n,
        "mae_close_media": r["mae_close"].mean(),
        "mae_close_mediana": r["mae_close"].median(),
        "mae_close_p90": r["mae_close"].quantile(0.9),
        "mae_close_p99": r["mae_close"].quantile(0.99),
        "mae_close_max": r["mae_close"].max(),
        "mae_intrabar_p90": r["mae_intrabar"].quantile(0.9),
        "mae_intrabar_p99": r["mae_intrabar"].quantile(0.99),
        "mae_intrabar_max": r["mae_intrabar"].max(),
        "n_teria_batido_stop": n_batido,
        "pct_teria_batido_stop": n_batido / n,
        "pnl_medio_sem_stop": r["pnl_final_h"].mean(),
        "pnl_medio_com_stop_hipotetico": np.where(
            r["teria_batido_stop"], -stop_catastrofico_pontos, r["pnl_final_h"]
        ).mean(),
    }

    saida.mkdir(parents=True, exist_ok=True)
    arq = saida / "mae_analise.md"
    linhas_md = [
        "# Analise de MAE (Maximum Adverse Excursion) por operacao\n",
        f"- feature: {feature} @ h={horizonte}",
        f"- threshold_entrada: {threshold_entrada}  direcao: {direcao}",
        f"- stop catastrofico: {stop_catastrofico_pontos:.0f} pts",
        f"- triggers com janela completa: {n}\n",
        "Nao gasta trial: engenharia de risco sobre sinal JA' validado, "
        "nao hipotese estatistica nova.\n",
        "## MAE_close (o que o sistema REAL avalia -- checagem a cada "
        "fechamento de barra)\n",
        f"- media: {resumo['mae_close_media']:.1f} pts",
        f"- mediana: {resumo['mae_close_mediana']:.1f} pts",
        f"- p90: {resumo['mae_close_p90']:.1f} pts",
        f"- p99: {resumo['mae_close_p99']:.1f} pts",
        f"- MAXIMO: {resumo['mae_close_max']:.1f} pts\n",
        "## MAE_intrabar (limite teorico mais severo -- NAO monitorado "
        "pelo sistema hoje, so' referencia)\n",
        f"- p90: {resumo['mae_intrabar_p90']:.1f} pts",
        f"- p99: {resumo['mae_intrabar_p99']:.1f} pts",
        f"- MAXIMO: {resumo['mae_intrabar_max']:.1f} pts\n",
        f"## Quantas operacoes teriam BATIDO o stop catastrofico "
        f"({stop_catastrofico_pontos:.0f} pts) antes do horizonte natural\n",
        f"- {n_batido} de {n} ({resumo['pct_teria_batido_stop']:.1%})\n",
        "## Efeito no P&L medio se o stop realmente tivesse disparado nesses casos\n",
        f"- pnl medio SEM considerar o stop (so' saida por tempo): "
        f"{resumo['pnl_medio_sem_stop']:+.1f} pts",
        f"- pnl medio COM o stop hipotetico aplicado: "
        f"{resumo['pnl_medio_com_stop_hipotetico']:+.1f} pts",
        "\n## Leitura\n",
        "- MAE_close alto e frequente == o stop catastrofico ja esta "
        "mordendo de verdade, nao e' so' seguro de cauda.",
        "- Comparar pnl_medio COM vs SEM stop: se o stop hipotetico piora "
        "o pnl medio, ele esta cortando caudas GANHADORAS que se "
        "recuperariam ate' o horizonte -- tensao real com a Rota A "
        "(saida por tempo). Se melhora ou nao muda muito, o stop e' "
        "seguro de cauda de verdade, coerente com o desenho original.",
    ]
    arq.write_text("\n".join(linhas_md), encoding="utf-8")
    resumo["relatorio"] = str(arq)
    resumo["tabela"] = r
    return resumo
