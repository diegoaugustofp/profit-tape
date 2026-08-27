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

from .walkforward import gerar_folds


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
                 stop_catastrofico_pontos: float, saida: Path,
                 treino_min: int = 3, teste_dias: int = 2) -> dict:
    df = pd.read_parquet(arquivo_features)
    if "dia" not in df.columns:
        df["dia"] = pd.to_datetime(df["ts_close"], unit="ns", utc=True).dt.date

    # BUG REAL corrigido (2026-08-27, achado comparando com quintis.py): a
    # primeira versao rodava sobre a amostra INTEIRA, misturando dias que o
    # walk-forward do IC usou como TREINO com dias de TESTE -- diferente da
    # disciplina que quintis.py ja seguia (restringir ao pool out-of-sample
    # da uniao dos blocos de teste). Isso inflava artificialmente o numero
    # de venda (+33.73 bruto inferido da tabela de quintis OOS vs +11.6
    # bruto medido aqui sobre amostra cheia contaminada com in-sample) --
    # a diferenca e' exatamente essa contaminacao, nao ruido. Corrigido:
    # MESMOS dias de teste que quintis.py usaria com os mesmos treino_min/
    # teste_dias, para os dois numeros serem genuinamente comparaveis.
    dias = sorted(df["dia"].unique())
    folds = gerar_folds(dias, treino_min=treino_min, teste_dias=teste_dias)
    dias_teste = set()
    for _treino, teste in folds:
        dias_teste.update(teste)
    df = df[df["dia"].isin(dias_teste)].reset_index(drop=True)

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

    def _stats_lado(sub: pd.DataFrame) -> dict:
        if sub.empty:
            return {"n": 0, "pnl_bruto_medio": float("nan"),
                   "mae_close_mediana": float("nan"), "pct_batido_stop": float("nan")}
        return {
            "n": len(sub),
            "pnl_bruto_medio": sub["pnl_final_h"].mean(),
            "mae_close_mediana": sub["mae_close"].median(),
            "pct_batido_stop": sub["teria_batido_stop"].mean(),
        }

    # Quebra por lado (2026-08-27, achado real): threshold_entrada simetrico
    # para compra e venda pode estar escondendo uma assimetria de edge --
    # um lado pode carregar o sinal inteiro, o outro pode ser diluidor puro.
    # Confirma (ou descarta) isso direto nos triggers REAIS, nao so' inferido
    # da tabela de quintis (que usa quintil, nao o threshold exato do EA).
    stats_compra = _stats_lado(r[r["lado"] == 1])
    stats_venda = _stats_lado(r[r["lado"] == -1])

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
        "stats_compra": stats_compra,
        "stats_venda": stats_venda,
    }

    saida.mkdir(parents=True, exist_ok=True)
    arq = saida / "mae_analise.md"
    linhas_md = [
        "# Analise de MAE (Maximum Adverse Excursion) por operacao\n",
        f"- feature: {feature} @ h={horizonte}",
        f"- threshold_entrada: {threshold_entrada}  direcao: {direcao}",
        f"- stop catastrofico: {stop_catastrofico_pontos:.0f} pts",
        f"- pool out-of-sample: treino_min={treino_min} teste_dias={teste_dias} "
        f"(mesma disciplina de research/quintis.py — nunca a amostra inteira)",
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
        "\n## Quebra por lado (compra vs venda)\n",
        "threshold_entrada simetrico para compra e venda pode esconder "
        "uma assimetria real de edge -- um lado pode carregar o sinal "
        "inteiro, o outro pode ser diluidor puro do resultado combinado.\n",
        "| lado | n | pnl bruto medio | MAE_close mediana | %% bateria o stop |",
        "|---|---|---|---|---|",
        f"| compra | {resumo['stats_compra']['n']} | "
        f"{resumo['stats_compra']['pnl_bruto_medio']:+.1f} | "
        f"{resumo['stats_compra']['mae_close_mediana']:.1f} | "
        f"{resumo['stats_compra']['pct_batido_stop']:.1%} |",
        f"| venda | {resumo['stats_venda']['n']} | "
        f"{resumo['stats_venda']['pnl_bruto_medio']:+.1f} | "
        f"{resumo['stats_venda']['mae_close_mediana']:.1f} | "
        f"{resumo['stats_venda']['pct_batido_stop']:.1%} |",
        "\nSe um lado tem pnl bruto medio abaixo do custo de transacao "
        "(tipicamente ~11pts no WIN) e o outro bem acima, o threshold "
        "simetrico esta operando um lado sem edge real ao lado de um "
        "lado forte -- vale considerar threshold assimetrico ou desativar "
        "o lado fraco, com o CUIDADO de isso ser uma decisao de design "
        "nova (nao gratuita -- precisa de pre-registro proprio antes de "
        "mudar o comportamento do EA, mesma disciplina de sempre).",
    ]
    arq.write_text("\n".join(linhas_md), encoding="utf-8")
    resumo["relatorio"] = str(arq)
    resumo["tabela"] = r
    return resumo
