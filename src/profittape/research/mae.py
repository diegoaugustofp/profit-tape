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
    vendido) de cada barra -- o que uma ordem de stop reagindo por negocio
    (nao so' no fechamento) teria visto.
  - Nunca cruza o dia (mesmo purge estrutural de retornos.py -- as ultimas
    h barras de cada pregao ficam de fora, sem futuro intra-dia).

TRES REGIMES DE SAIDA (2026-08-31, pre-voo do stop continuo): o modulo
compara explicitamente "sem stop" x "stop no CLOSE" (o que o EA faz hoje)
x "stop CONTINUO" (o proposto), com o preco REAL de cada um -- mais a
contagem no limiar por lado e o conjunto MARGINAL (as operacoes que so' o
continuo mata). Ate' a versao anterior havia um unico numero hipotetico
que modelava o stop do close saindo exatamente no limite, ou seja, media
o regime continuo e o rotulava como o atual; os dois nunca tinham sido
separados. Ver a secao de errata no relatorio gerado.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, cast

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
                 treino_min: int = 3, teste_dias: int = 2) -> dict[str, Any]:
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
        dia = cast(date, df.at[i, "dia"])
        L = int(cast(Any, lado.at[i]))
        # cast explicito (2026-08-28, causa raiz de 57 erros em cascata do
        # mypy strict): df.at[] com pandas-stubs devolve um Union amplo
        # demais (qualquer tipo escalar que uma celula PODERIA conter --
        # str, date, complex, etc.), ja' que o pandas nao expressa
        # estaticamente "esta coluna e' sempre float64". Toda operacao
        # subsequente usando 'entrada' sem essa narrowing herda o mesmo
        # Union amplo e gera erro de overload. Um cast aqui resolve a
        # cascata inteira de uma vez.
        entrada = float(cast(Any, df.at[i, "close"]))
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

        # MFE_close (2026-08-27, preparacao para Rota B -- payoff fixo):
        # complemento simetrico do MAE, excursao A FAVOR (nao contra) usando
        # CLOSE de cada barra -- responde "quanto de lucro estava disponivel
        # dentro da janela, se um alvo fixo tivesse sido usado em vez da
        # saida por tempo". Mesma disciplina de janela/purge do MAE.
        mfe_close = (-excursao_close).max()   # excursao_close negativo = a favor

        # MAE_intrabar: pior excursao usando LOW (comprado) / HIGH (vendido)
        # -- limite teorico mais severo, NAO monitorado pelo sistema hoje.
        pior_preco_intrabar = janela["low"] if L > 0 else janela["high"]
        excursao_intrabar = (entrada - pior_preco_intrabar) * L
        mae_intrabar = excursao_intrabar.max()

        pnl_final = (janela["close"].iloc[-1] - entrada) * L

        # TRES REGIMES DE SAIDA (2026-08-31, desenho do stop continuo).
        # Antes desta versao havia um so' numero hipotetico
        # ("pnl_medio_com_stop_hipotetico"), que substituia o resultado por
        # -stop sempre que mae_close cruzava. Isso modelava o stop DO CLOSE
        # como se ele saisse exatamente no limite -- que e' precisamente o
        # que ele NAO faz. As tres perdas reais do replay de 25 pregoes
        # (-615, -590, -565 brutos contra um limite de 500) saem no CLOSE da
        # barra que cruzou, nao em -500. O numero antigo media o regime
        # CONTINUO e o rotulava como o atual, entao nunca separou os dois
        # regimes que esta sessao precisa comparar.
        #
        #   sem stop     -> close em h (Rota A pura)
        #   stop close   -> close da PRIMEIRA barra com excursao_close >= S
        #                   (o que o GestorDeRisco faz hoje, preco real)
        #   stop continuo-> ~ -S na impressao que cruza, assim que o
        #                   high/low da barra atinge o limite
        S = stop_catastrofico_pontos
        cruz_close = excursao_close[excursao_close >= S]
        bateu_close = len(cruz_close) > 0
        if bateu_close:
            # sai no close da barra que cruzou: pnl = -excursao daquela barra
            excursao_no_cruz = float(cruz_close.iloc[0])
            pnl_stop_close = -excursao_no_cruz
        else:
            excursao_no_cruz = float("nan")
            pnl_stop_close = pnl_final
        # O stop continuo cruza sempre numa barra <= a do close (a excursao
        # intrabar de uma barra e' >= a excursao no close dela, por
        # construcao), entao nao ha caso de o close disparar e o continuo
        # nao. Saida modelada em exatamente -S: OTIMISTA pela granularidade
        # do tick (uma impressao pode pular o limite). Limitacao registrada,
        # nao corrigida aqui -- high/low de barra nao carrega a sequencia de
        # impressoes necessaria para medir esse pulo.
        bateu_intrabar = bool(mae_intrabar >= S)
        pnl_stop_continuo = -S if bateu_intrabar else pnl_final

        linhas.append({
            "dia": dia, "lado": L, "entrada": entrada,
            "mae_close": mae_close, "mae_intrabar": mae_intrabar,
            "mfe_close": mfe_close,
            "pnl_final_h": pnl_final,
            "teria_batido_stop": bateu_close,
            "teria_batido_stop_intrabar": bateu_intrabar,
            # MARGINAIS: as operacoes que o stop continuo mata e o atual
            # nao. Sao elas que decidem o veredito -- se a maioria termina
            # positiva, o stop continuo esta cortando a cauda que paga a
            # conta, exatamente o modo de falha ja conhecido para alvo fixo.
            "marginal_so_intrabar": bateu_intrabar and not bateu_close,
            # Excesso de granularidade: quanto o close passou do limite na
            # barra que cruzou. E' o numero de CONFORMIDADE -- 615 contra
            # 500 e' um excesso de 115.
            "excesso_close": (excursao_no_cruz - S) if bateu_close else float("nan"),
            "pnl_stop_close": pnl_stop_close,
            "pnl_stop_continuo": pnl_stop_continuo,
        })

    r = pd.DataFrame(linhas)
    if r.empty:
        raise SystemExit("nenhuma janela completa (todos os triggers "
                         "ficaram no fim do dia) -- amostra insuficiente")

    n = len(r)
    n_batido = int(r["teria_batido_stop"].sum())
    n_batido_intrabar = int(r["teria_batido_stop_intrabar"].sum())
    marginais = r[r["marginal_so_intrabar"]]
    n_marginais = len(marginais)
    n_marginais_pos = int((marginais["pnl_final_h"] > 0).sum())
    excesso = r["excesso_close"].dropna()

    def _stats_lado(sub: pd.DataFrame) -> dict[str, Any]:
        if sub.empty:
            return {"n": 0, "pnl_bruto_medio": float("nan"),
                   "mae_close_mediana": float("nan"),
                   "mfe_close_mediana": float("nan"),
                   "pct_batido_stop": float("nan"),
                   "n_batido_stop": 0,
                   "n_batido_stop_intrabar": 0,
                   "pct_batido_stop_intrabar": float("nan"),
                   "n_marginais": 0,
                   "n_marginais_positivas": 0}
        marginais_lado = sub[sub["marginal_so_intrabar"]]
        return {
            "n": len(sub),
            "pnl_bruto_medio": sub["pnl_final_h"].mean(),
            "mae_close_mediana": sub["mae_close"].median(),
            # Contagem por lado no limiar (2026-08-31): o EA roda
            # venda-apenas, entao a frequencia AGREGADA nao e' a que decide
            # -- a venda ja bate mais no close (6,2% contra 4,0%) e as tres
            # perdas alem do limite no replay sao todas de venda.
            "n_batido_stop": int(sub["teria_batido_stop"].sum()),
            "n_batido_stop_intrabar": int(sub["teria_batido_stop_intrabar"].sum()),
            "pct_batido_stop_intrabar": sub["teria_batido_stop_intrabar"].mean(),
            "n_marginais": len(marginais_lado),
            "n_marginais_positivas": int((marginais_lado["pnl_final_h"] > 0).sum()),
            # 2026-08-27, lacuna real achada rodando o MAE de novo com mais
            # dado: o MFE agregado (compra+venda misturados) nao serve para
            # congelar o par da Rota B, que precisa do MFE ESPECIFICO do
            # lado com edge (venda) -- sem isso, o lado de compra (sem
            # edge, MFE tipicamente menor) diluiria a mediana usada para
            # escolher o alvo.
            "mfe_close_mediana": sub["mfe_close"].median(),
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
        "mfe_close_media": r["mfe_close"].mean(),
        "mfe_close_mediana": r["mfe_close"].median(),
        "mfe_close_p10": r["mfe_close"].quantile(0.1),
        "mfe_close_p90": r["mfe_close"].quantile(0.9),
        "n_teria_batido_stop": n_batido,
        "pct_teria_batido_stop": n_batido / n,
        "n_teria_batido_stop_intrabar": n_batido_intrabar,
        "pct_teria_batido_stop_intrabar": n_batido_intrabar / n,
        # Conformidade: quanto o close passou do limite quando cruzou.
        "excesso_close_medio": excesso.mean() if len(excesso) else float("nan"),
        "excesso_close_mediana": excesso.median() if len(excesso) else float("nan"),
        "excesso_close_max": excesso.max() if len(excesso) else float("nan"),
        # Os tres regimes (ver comentario no loop). pnl_medio_com_stop_
        # hipotetico foi REMOVIDO de proposito: modelava o stop do close
        # saindo em -S, que e' o comportamento do stop CONTINUO -- ler
        # aquele numero como "o stop de hoje" era o erro que esta versao
        # existe para consertar.
        "pnl_medio_sem_stop": r["pnl_final_h"].mean(),
        "pnl_medio_stop_close": r["pnl_stop_close"].mean(),
        "pnl_medio_stop_continuo": r["pnl_stop_continuo"].mean(),
        # As marginais: o conjunto que o continuo mata a mais.
        "n_marginais": n_marginais,
        "pnl_marginais_medio": (marginais["pnl_final_h"].mean()
                                if n_marginais else float("nan")),
        "pnl_marginais_mediana": (marginais["pnl_final_h"].median()
                                  if n_marginais else float("nan")),
        "n_marginais_positivas": n_marginais_pos,
        "pct_marginais_positivas": (n_marginais_pos / n_marginais
                                    if n_marginais else float("nan")),
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
        "## MFE_close (Maximum Favorable Excursion — preparacao para "
        "Rota B, payoff fixo)\n",
        "Complemento simetrico do MAE: quanto de lucro estava disponivel "
        "dentro da janela, se um alvo fixo tivesse sido usado em vez da "
        "saida por tempo. NAO decide sozinho um alvo -- e' insumo para "
        "um pre-registro proprio, nunca escolha de alvo por seleção apos "
        "ver o resultado (mesma disciplina de sempre).\n",
        f"- media: {resumo['mfe_close_media']:.1f} pts",
        f"- mediana: {resumo['mfe_close_mediana']:.1f} pts",
        f"- p10: {resumo['mfe_close_p10']:.1f} pts",
        f"- p90: {resumo['mfe_close_p90']:.1f} pts\n",
        f"## FREQUENCIA: quantas operacoes batem o stop "
        f"({stop_catastrofico_pontos:.0f} pts) em cada regime\n",
        f"- stop no CLOSE (o que roda hoje): {n_batido} de {n} "
        f"({resumo['pct_teria_batido_stop']:.1%})",
        f"- stop CONTINUO (o proposto): {n_batido_intrabar} de {n} "
        f"({resumo['pct_teria_batido_stop_intrabar']:.1%})",
        f"- MARGINAIS (so' o continuo mata): {n_marginais}\n",
        "Se o continuo dispara muito mais que o close, o guarda de CAUDA "
        "vira stop TATICO -- outro mecanismo, com outro criterio de "
        "aceite. E' esta razao, nao o P&L, que decide se a mudanca e' "
        "conformidade ou desenho novo.\n",
        "## CONFORMIDADE: quanto o close passa do limite quando cruza\n",
        f"- excesso medio: {resumo['excesso_close_medio']:.1f} pts",
        f"- excesso mediana: {resumo['excesso_close_mediana']:.1f} pts",
        f"- excesso MAXIMO: {resumo['excesso_close_max']:.1f} pts\n",
        "O stop de hoje sai no close da barra que cruzou, nao no limite: "
        "este excesso E' a falha de granularidade, medida. Um excesso de "
        "115 pts significa uma perda de 615 num limite de 500.\n",
        "## OS TRES REGIMES DE SAIDA (pnl bruto medio por operacao)\n",
        f"- sem stop (Rota A pura, close em h): "
        f"{resumo['pnl_medio_sem_stop']:+.1f} pts",
        f"- stop no CLOSE (hoje, preco real da barra que cruzou): "
        f"{resumo['pnl_medio_stop_close']:+.1f} pts",
        f"- stop CONTINUO (proposto, ~ -{stop_catastrofico_pontos:.0f} "
        f"na impressao que cruza): {resumo['pnl_medio_stop_continuo']:+.1f} pts\n",
        "ERRATA (2026-08-31): versoes anteriores deste relatorio tinham UM "
        "numero, 'pnl medio COM o stop hipotetico', que substituia o "
        "resultado por -stop sempre que o MAE_close cruzava. Isso modela o "
        "stop saindo EXATAMENTE no limite -- que e' o comportamento do "
        "regime CONTINUO, nao do que roda hoje. Aquele numero media o "
        "regime proposto e o rotulava como o atual; os dois regimes nunca "
        "tinham sido separados. Removido.\n",
        "O continuo e' OTIMISTA por uma granularidade de tick: modela "
        "saida exata em -stop, mas uma impressao pode pular o limite. "
        "High/low de barra nao carrega a sequencia de impressoes "
        "necessaria para medir esse pulo -- limitacao registrada.\n",
        "## O VEREDITO: as operacoes MARGINAIS\n",
        "As que tocam o limite intrabar mas NAO no close -- as que o stop "
        "continuo mata e o atual deixa correr. Se a maioria delas termina "
        "POSITIVA, o continuo esta cortando a cauda que paga a conta "
        "(mesmo modo de falha ja conhecido do alvo fixo num sinal de ~43% "
        "de acerto que ganha por magnitude).\n",
        f"- n marginais: {n_marginais}",
        f"- pnl final medio delas (se deixadas correr): "
        f"{resumo['pnl_marginais_medio']:+.1f} pts",
        f"- pnl final mediana: {resumo['pnl_marginais_mediana']:+.1f} pts",
        f"- terminaram POSITIVAS: {n_marginais_pos} de {n_marginais} "
        f"({resumo['pct_marginais_positivas']:.1%})\n",
        "\n## Quebra por lado (compra vs venda)\n",
        "threshold_entrada simetrico para compra e venda pode esconder "
        "uma assimetria real de edge -- um lado pode carregar o sinal "
        "inteiro, o outro pode ser diluidor puro do resultado combinado.\n",
        "| lado | n | pnl bruto medio | MAE_close mediana | "
        "MFE_close mediana | bate no close | bate continuo | "
        "marginais (positivas) |",
        "|---|---|---|---|---|---|---|---|",
        f"| compra | {resumo['stats_compra']['n']} | "
        f"{resumo['stats_compra']['pnl_bruto_medio']:+.1f} | "
        f"{resumo['stats_compra']['mae_close_mediana']:.1f} | "
        f"{resumo['stats_compra']['mfe_close_mediana']:.1f} | "
        f"{resumo['stats_compra']['n_batido_stop']} "
        f"({resumo['stats_compra']['pct_batido_stop']:.1%}) | "
        f"{resumo['stats_compra']['n_batido_stop_intrabar']} "
        f"({resumo['stats_compra']['pct_batido_stop_intrabar']:.1%}) | "
        f"{resumo['stats_compra']['n_marginais']} "
        f"({resumo['stats_compra']['n_marginais_positivas']}) |",
        f"| venda | {resumo['stats_venda']['n']} | "
        f"{resumo['stats_venda']['pnl_bruto_medio']:+.1f} | "
        f"{resumo['stats_venda']['mae_close_mediana']:.1f} | "
        f"{resumo['stats_venda']['mfe_close_mediana']:.1f} | "
        f"{resumo['stats_venda']['n_batido_stop']} "
        f"({resumo['stats_venda']['pct_batido_stop']:.1%}) | "
        f"{resumo['stats_venda']['n_batido_stop_intrabar']} "
        f"({resumo['stats_venda']['pct_batido_stop_intrabar']:.1%}) | "
        f"{resumo['stats_venda']['n_marginais']} "
        f"({resumo['stats_venda']['n_marginais_positivas']}) |",
        "\nO EA roda VENDA-APENAS: a linha que decide o pre-registro e' a "
        "da venda, nao o agregado. As tres perdas alem do limite no replay "
        "de 25 pregoes sao todas de venda.",
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
