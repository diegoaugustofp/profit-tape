"""
Absorcao de barra: implementa o pre-registro CONGELADO em 2026-08-31.

Nenhuma escolha aqui e' livre. Cortes, janela, K, horizonte, criterio e
regra de parada vieram congelados. Se algum numero precisar mudar, o
caminho e' pre-registro NOVO — nao edicao deste arquivo.

O EVENTO
--------
Conjuncao de tres condicoes, nunca um numero unico:

    |desloc_norm| <= 0,25     resultado nulo (o preco voltou)
    z_amplitude   >= 0,50     alcance  (o preco chegou a andar)
    z_vol_agr     >= 0,50     esforco  (alguem agrediu)

A conjuncao e' deliberada. Combinar os tres numa formula repetiria o
erro do `absorcao_dir`, em que `imbalance - desloc_norm` escondia dois
casos OPOSTOS sob o mesmo valor extremo.

A DIRECAO NAO PODE VIR DO `imbalance`
-------------------------------------
Medido nos eventos: |imbalance| mediano 0,014 contra 0,085 no geral, e
NENHUM evento passa de 0,05.

Isso tem mecanismo, nao e' acidente de amostra: **absorcao equilibra o
fluxo por definicao**. Se o passivo absorve tudo que o agressor manda,
os dois lados registram volume parecido. O campo que mediria o lado e'
justamente o que a absorcao neutraliza.

Por isso a direcao vem do CONTEXTO, medido antes da barra.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog

from .remanescente import _bootstrap_bloco, _uma_amostra_contra_zero
from .trials import limiar_deflacionado

log = structlog.get_logger(__name__)

# --- TUDO ABAIXO E' CONGELADO (pre-registro 2026-08-31) ---
MAX_DESLOC_NORM = 0.25
MIN_Z_AMPLITUDE = 0.50
MIN_Z_VOL_AGR = 0.50
JANELA_Z = 50            # barras, para amplitude/volume/range medio
JANELA_CONTEXTO = 6      # ~30 min no 5m, do relato do operador
K_CONTEXTO = 3.0         # reduzido de 5 por RESTRICAO DE AMOSTRA
HORIZONTE = 2            # barras
N_MINIMO = 30
# ----------------------------------------------------------


def preparar(barras: pd.DataFrame) -> pd.DataFrame:
    """
    Deriva as colunas do evento e do contexto.

    ANTI-LOOKAHEAD: todas as janelas terminam em `t` (conhecidas no
    fechamento da barra) e o contexto usa `shift(1)` para tras. O retorno
    e' medido DEPOIS de `t`. Sem essa separacao, o teste mediria a
    propria barra de entrada.
    """
    d = barras.copy()
    if "dia" not in d.columns:
        d["dia"] = pd.to_datetime(d["ts_close"], unit="ns", utc=True).dt.date
    # BLOCO CONTIGUO: janela movel nao atravessa BURACO na amostra.
    #
    # Achado em 2026-09-03 ao rodar o combinado das duas partes de 2026.
    # O dump concatena 02/01-30/04 com 01/06-23/07, e MAIO nao esta la'.
    # O `.ntsl` calculou sobre o grafico CONTINUO (abril -> maio ->
    # junho); o Python le' o arquivo (abril -> junho). Nas primeiras 50
    # barras de junho, a janela do Python pegava ABRIL enquanto a do NTSL
    # pegou MAIO.
    #
    # Divergencia medida: `z_amplitude` saltou de 4,89e-06 (parte 1
    # sozinha) para 6,20 no combinado.
    #
    # E' o mesmo principio da purga de dia: referencia movel nao pode
    # cruzar descontinuidade. Aqui a descontinuidade e' de AMOSTRA, nao
    # de pregao.
    dias_unicos = pd.to_datetime(pd.Series(sorted({str(x) for x in d["dia"]})))
    dia_serie = pd.to_datetime(d["dia"].astype(str))
    salto = dia_serie.diff().dt.days.fillna(0)
    # Fim de semana longo/feriado chega a ~5 dias; acima disso e' buraco
    # de amostra, nao calendario.
    d["_bloco"] = (salto > 10).cumsum()
    del dias_unicos

    d["amplitude_pts"] = d["high"] - d["low"]
    if "vol_agr" not in d.columns:
        d["vol_agr"] = d["vol_buy"] + d["vol_sell"]

    for col, origem in (("z_amplitude", "amplitude_pts"), ("z_vol_agr", "vol_agr")):
        # `.shift(1)`: a referencia sao as 50 barras ANTERIORES, e a barra
        # atual NAO entra nela.
        #
        # ERRATA de 2026-09-01. O pre-registro dizia "vs 50 barras", sem
        # especificar se a propria barra entrava, e as duas
        # implementacoes resolveram para lados opostos: o `.ntsl` percorre
        # `for nIndex := 1 to JanelaZ` (so' anteriores) e aqui o
        # `rolling()` incluia a atual. Divergencia medida em dado real:
        # ate 19,9 no z da amplitude.
        #
        # A definicao do `.ntsl` e' a correta, e por mecanismo:
        # "atipica em relacao ao normal recente" compara contra a
        # HISTORIA, e incluir a propria barra na referencia atenua
        # justamente o que se quer detectar -- a barra grande infla a
        # propria media e o proprio desvio.
        por_bloco = d.groupby("_bloco")[origem]
        media = por_bloco.rolling(JANELA_Z).mean().reset_index(0, drop=True)
        desvio = por_bloco.rolling(JANELA_Z).std().reset_index(0, drop=True)
        media = media.groupby(d["_bloco"]).shift(1)
        desvio = desvio.groupby(d["_bloco"]).shift(1)
        d[col] = (d[origem] - media) / desvio.where(desvio > 0)

    # range medio com shift(1): o range da propria barra nao pode entrar
    # na referencia que a julga.
    d["range_medio"] = (
        d.groupby("_bloco")["amplitude_pts"].rolling(JANELA_Z).mean()
        .reset_index(0, drop=True).groupby(d["_bloco"]).shift(1))
    # PURGA ESTRUTURAL NO CONTEXTO (errata de 2026-09-02).
    #
    # `mov_contexto` e' uma DIFERENCA DE PRECO, e sem `groupby("dia")` ela
    # atravessava a virada do pregao — medindo o GAP NOTURNO em vez da
    # perna intradiaria.
    #
    # Medido no dump de maio: |mov_contexto| tinha mediana 3,58 nas seis
    # primeiras barras contra 0,80 no resto, e o habilitador exige 3,0.
    # Ele disparava quase automaticamente na abertura: 10 dos 24 eventos
    # (42%) caiam nas 6 primeiras barras, que sao 5% do pregao. Taxa de
    # 20% ali contra 0,7% no restante.
    #
    # Achado pelo operador, na inspecao visual de 14/05: "uma barra forte
    # que INICIA o movimento depois de uma sequencia de barras fracas" —
    # justamente o oposto de absorcao.
    #
    # A purga vale SO' aqui: `z_amplitude`, `z_vol_agr` e `range_medio`
    # sao grandezas INTRABARRA (amplitude e volume), que o gap nao
    # corrompe. Purgar as tres custaria as 50 primeiras barras de cada
    # pregao — 46% da amostra — sem corrigir defeito nenhum.
    por_dia = d.groupby("dia")["close"]
    d["mov_contexto"] = (
        (por_dia.shift(1) - por_dia.shift(1 + JANELA_CONTEXTO))
        / d["range_medio"])
    return d


def marcar_eventos(d: pd.DataFrame) -> pd.DataFrame:
    """Adiciona `evento` (conjuncao), `contexto_ok` e `lado`."""
    d = d.copy()
    d["evento"] = (
        (d["desloc_norm"].abs() <= MAX_DESLOC_NORM)
        & (d["z_amplitude"] >= MIN_Z_AMPLITUDE)
        & (d["z_vol_agr"] >= MIN_Z_VOL_AGR)
    ).fillna(False)
    d["contexto_ok"] = (d["mov_contexto"].abs() >= K_CONTEXTO).fillna(False)
    # CONTRARIA ao movimento: subiu muito e travou -> vies de BAIXA.
    d["lado"] = -np.sign(d["mov_contexto"]).fillna(0).astype(int)
    return d


def retornos(d: pd.DataFrame, mascara: pd.Series) -> pd.DataFrame:
    """
    Retorno de `HORIZONTE` barras no sentido do vies, BRUTO.

    Purga estrutural: a janela nunca atravessa o pregao. Um retorno que
    cruza a virada mede o gap noturno, nao o efeito da barra.
    """
    # Arrays em vez de `.at`: o pandas nao expressa estaticamente o dtype
    # de uma celula, entao cada `float(d.at[...])` vira um Union amplo que
    # o mypy rejeita. Mesma solucao ja usada em mae.py e remanescente_tape.
    pos = np.flatnonzero((mascara & (d["lado"] != 0)).to_numpy())
    fechamento = d["close"].to_numpy(dtype=float)
    lados = d["lado"].to_numpy(dtype=np.int64)
    contexto = d["mov_contexto"].to_numpy(dtype=float)
    dias = d["dia"].to_numpy()

    linhas = []
    for i in pos:
        fim = i + HORIZONTE
        if fim >= len(d) or dias[fim] != dias[i]:
            continue
        lado = int(lados[i])
        linhas.append({
            "dia": dias[i],
            "lado": lado,
            "retorno": (fechamento[fim] - fechamento[i]) * lado,
            "mov_contexto": contexto[i],
        })
    return pd.DataFrame(linhas)


def _avaliar(r: pd.DataFrame, rotulo: str, limiar_z: float,
             semente: int) -> dict[str, Any]:
    p: dict[str, Any] = {"grupo": rotulo, "n": len(r)}
    p["n_suficiente"] = len(r) >= N_MINIMO
    v = r["retorno"].to_numpy() if len(r) else np.array([])
    est = _uma_amostra_contra_zero(v)
    boot = (_bootstrap_bloco(r, "retorno", 2000, semente) if len(r) >= 2
            else {"ic95_baixo": float("nan"), "ic95_alto": float("nan")})
    ic_exclui_zero = bool(
        not math.isnan(boot["ic95_baixo"])
        and (boot["ic95_alto"] < 0 or boot["ic95_baixo"] > 0))
    p["media"] = est["media"]
    p["t"] = est["t"]
    p["ic95_baixo"] = boot["ic95_baixo"]
    p["ic95_alto"] = boot["ic95_alto"]
    p["sig"] = bool(p["n_suficiente"] and not math.isnan(est["t"])
                    and abs(est["t"]) >= limiar_z and ic_exclui_zero)
    return p


def avaliar_tudo(d: pd.DataFrame, limiar_z: float,
                 semente: int = 20260831) -> list[dict[str, Any]]:
    """
    Os dois lados, mais os DOIS CONTROLES pre-registrados.

    Os controles sao diagnostico, nao criterio. Existem para responder
    "a conjuncao acrescenta algo?": se o contexto sozinho, ou o evento
    sozinho, produzir o mesmo numero, entao a hipotese especifica —
    absorcao APOS movimento — nao esta sendo testada por nada.
    """
    principal = d["evento"] & d["contexto_ok"]
    fora = []
    r = retornos(d, principal)
    for lado, rotulo in ((-1, "evento+contexto BAIXA"), (1, "evento+contexto ALTA")):
        fora.append(_avaliar(r[r["lado"] == lado] if len(r) else r,
                             rotulo, limiar_z, semente))
    fora.append(_avaliar(retornos(d, d["contexto_ok"] & ~d["evento"]),
                         "CONTROLE contexto sem evento", limiar_z, semente))
    fora.append(_avaliar(retornos(d, d["evento"] & ~d["contexto_ok"]),
                         "CONTROLE evento sem contexto", limiar_z, semente))
    return fora


def decidir(pontos: list[dict[str, Any]]) -> tuple[str, str]:
    """Criterio congelado. Controles NAO entram no veredito."""
    lados = [p for p in pontos if p["grupo"].startswith("evento+contexto")]
    sig = [p for p in lados if p["sig"]]
    if not sig:
        if not any(p["n_suficiente"] for p in lados):
            return "INCONCLUSIVO", (
                f"n < {N_MINIMO} nos dois lados: reportado, nao interpretado")
        return "CONTRA", (
            "nenhum lado produz retorno distinguivel de zero: a barra de "
            "absorcao, apos movimento, nao antecipa reversao neste sinal")
    negativos = [p for p in sig if p["media"] < 0]
    if negativos and len(negativos) == len(sig):
        return "INVERTIDO", (
            "retorno significativamente NEGATIVO: a leitura de absorcao "
            "esta ao contrario. Achado genuino, registrar")
    if negativos:
        return "INCONCLUSIVO", "lados significativos com sinais opostos"
    quais = ", ".join(p["grupo"] for p in sig)
    return "FAVORAVEL", f"retorno positivo e significativo em: {quais}"


def gerar_ruido(n_dias: int = 120, barras_por_dia: int = 108,
                negocios_por_barra: int = 200, tick: float = 5.0,
                semente: int = 20260831) -> pd.DataFrame:
    """
    Barras de TEMPO sobre passeio aleatorio, com caminho intrabarra real.

    O caminho precisa ser CONTINUO na grade de tick: o evento condiciona
    em `desloc_norm`, que depende de onde o preco esteve DENTRO da barra.
    Sortear OHLC por fora produziria barras impossiveis, e o portao
    estaria testando outra geometria.
    """
    rng = np.random.default_rng(semente)
    linhas = []
    preco = 140_000.0
    for d in range(n_dias):
        for _ in range(barras_por_dia):
            # Numero de NEGOCIOS varia por barra, e o volume sai dele.
            #
            # A primeira versao sorteava o volume INDEPENDENTE do caminho
            # do preco. Medido: corr(amplitude, volume) = +0,012 no ruido
            # contra +0,892 no real. Como o evento exige amplitude E
            # volume altos ao mesmo tempo, no ruido isso virava o produto
            # de duas probabilidades independentes -- 3 eventos em 60
            # dias, contra ~2,5 por pregao no real.
            #
            # Nao era so' falta de amostra: um ruido com geometria errada
            # testa OUTRO estimador. Aqui o numero de negocios da barra e'
            # sorteado e determina ao mesmo tempo quantos passos o preco
            # da' (logo a amplitude) e o volume -- que e' a dependencia
            # real do mercado.
            n_neg = max(20, int(rng.gamma(4.0, negocios_por_barra / 4.0)))
            passos = rng.choice([-tick, tick], size=n_neg)
            caminho = preco + np.cumsum(passos)
            qtd = float(n_neg * rng.gamma(20.0, 5.0))
            linhas.append({
                "dia": pd.Timestamp("2026-01-01").date() + pd.Timedelta(days=d),
                "open": preco, "high": float(caminho.max()),
                "low": float(caminho.min()), "close": float(caminho[-1]),
                "vol_agr": qtd,
            })
            preco = float(caminho[-1])
    b = pd.DataFrame(linhas)
    amplitude = b["high"] - b["low"]
    b["desloc_norm"] = ((b["close"] - b["open"]) / amplitude).where(amplitude > 0, 0.0)
    return b


def portao_de_honestidade(limiar_z: float, n_dias: int = 120,
                          semente: int = 20260831) -> dict[str, Any]:
    """
    Exigencia do pre-registro: veredito CONTRA sobre ruido puro.

    Aqui o portao NAO e' confirmacao de teorema (diferente da Rota B): o
    estimador SELECIONA barras por condicoes sobre elas mesmas, e
    selecao sempre merece suspeita de vies. Se reprovar, o desenho esta
    errado — nao o codigo.
    """
    d = marcar_eventos(preparar(gerar_ruido(n_dias=n_dias, semente=semente)))
    pontos = avaliar_tudo(d, limiar_z, semente=semente)
    veredito, motivo = decidir(pontos)
    lados = [p for p in pontos if p["grupo"].startswith("evento+contexto")]
    curtos = [p["grupo"] for p in lados if not p["n_suficiente"]]
    if curtos:
        raise SystemExit(
            f"amostra de ruido insuficiente em {curtos} (n < {N_MINIMO}).\n"
            "  Um portao que nao consegue passar nao e' portao: aumente "
            "`n_dias`."
        )
    return {"passou": veredito == "CONTRA", "veredito": veredito,
            "motivo": motivo, "pontos": pontos, "barras": len(d)}


def rodar(features_parquet: Path, saida_dir: Path,
          n_dias_ruido: int = 120, semente: int = 20260831) -> dict[str, Any]:
    """Ordem obrigatoria: portao (bloqueante), depois dado real."""
    limiar_z = limiar_deflacionado(2)

    portao = portao_de_honestidade(limiar_z, n_dias=n_dias_ruido,
                                   semente=semente)
    log.info("absorcao_barra.portao", veredito=portao["veredito"])
    if not portao["passou"]:
        raise SystemExit(
            f"PORTAO REPROVOU (veredito {portao['veredito']} sobre ruido "
            f"puro): {portao['motivo']}\n"
            "O estimador seleciona barras por condicoes sobre elas mesmas; "
            "reprovar aqui indica vies de selecao no DESENHO. Nao "
            "interprete dado real."
        )

    d = marcar_eventos(preparar(pd.read_parquet(features_parquet)))
    pontos = avaliar_tudo(d, limiar_z, semente=semente)
    veredito, motivo = decidir(pontos)

    saida_dir.mkdir(parents=True, exist_ok=True)
    tabela = pd.DataFrame(pontos)
    tabela.to_csv(saida_dir / "absorcao_barra.csv", index=False)
    return {
        "portao": {k: portao[k] for k in ("passou", "veredito")},
        "limiar_deflacionado": round(limiar_z, 3),
        "barras": len(d),
        "eventos": int((d["evento"] & d["contexto_ok"]).sum()),
        "veredito": veredito,
        "motivo": motivo,
        "tabela": tabela,
    }
