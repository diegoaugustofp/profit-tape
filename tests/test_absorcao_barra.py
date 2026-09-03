"""
Testes do pre-registro de absorcao de barra (congelado 2026-08-31).

Os valores congelados sao verificados como CONSTANTES: se alguem mudar
um corte sem pre-registro novo, o teste falha e diz por que.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from profittape.research import absorcao_barra as ab


def _barras(n: int = 300, semente: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(semente)
    preco = 140_000.0
    linhas = []
    for _ in range(n):
        amp = rng.gamma(4.0, 40.0)
        o = preco
        c = o + rng.normal(0, amp / 3)
        h = max(o, c) + rng.gamma(2.0, amp / 6)
        low = min(o, c) - rng.gamma(2.0, amp / 6)
        linhas.append({"dia": pd.Timestamp("2026-08-24").date(),
                       "open": o, "high": h, "low": low, "close": c,
                       "vol_agr": (h - low) * rng.gamma(20.0, 5.0)})
        preco = c
    b = pd.DataFrame(linhas)
    a = b["high"] - b["low"]
    b["desloc_norm"] = ((b["close"] - b["open"]) / a).where(a > 0, 0.0)
    return b


def test_parametros_congelados_nao_mudam_sem_pre_registro() -> None:
    """
    Guarda os numeros do pre-registro. Mudar qualquer um exige
    pre-registro NOVO, nao edicao do modulo -- e um teste que falha e'
    mais barato que descobrir a mudanca tres rodadas depois.
    """
    assert ab.MAX_DESLOC_NORM == 0.25
    assert ab.MIN_Z_AMPLITUDE == 0.50
    assert ab.MIN_Z_VOL_AGR == 0.50
    assert ab.JANELA_CONTEXTO == 6      # ~30 min, do relato do operador
    assert ab.K_CONTEXTO == 3.0         # reduzido de 5 por amostra
    assert ab.HORIZONTE == 2
    assert ab.N_MINIMO == 30


def test_o_evento_e_conjuncao_das_TRES_condicoes() -> None:
    """
    Nenhuma condicao sozinha basta. Combinar as tres num numero unico
    repetiria o erro do `absorcao_dir`, em que a subtracao escondia dois
    casos OPOSTOS sob o mesmo valor extremo.
    """
    d = ab.marcar_eventos(ab.preparar(_barras()))
    v = d.dropna(subset=["z_amplitude", "z_vol_agr"])
    assert (v.loc[v["evento"], "desloc_norm"].abs() <= ab.MAX_DESLOC_NORM).all()
    assert (v.loc[v["evento"], "z_amplitude"] >= ab.MIN_Z_AMPLITUDE).all()
    assert (v.loc[v["evento"], "z_vol_agr"] >= ab.MIN_Z_VOL_AGR).all()
    # e cada condicao isolada aceita mais barras que a conjuncao
    so_desloc = (v["desloc_norm"].abs() <= ab.MAX_DESLOC_NORM).sum()
    assert so_desloc > v["evento"].sum()


def test_lado_e_CONTRARIO_ao_movimento() -> None:
    """Subiu muito e travou -> viés de BAIXA. E' a hipotese de reversao."""
    d = pd.DataFrame({"mov_contexto": [5.0, -5.0, 0.0]})
    d["desloc_norm"] = 0.0
    d["z_amplitude"] = 1.0
    d["z_vol_agr"] = 1.0
    r = ab.marcar_eventos(d)
    assert list(r["lado"]) == [-1, 1, 0]


def test_janela_nao_atravessa_o_pregao() -> None:
    """
    Purga estrutural: retorno que cruza a virada mede o gap noturno, nao
    o efeito da barra.
    """
    d = pd.DataFrame({
        "dia": [pd.Timestamp("2026-08-24").date()] * 2
               + [pd.Timestamp("2026-08-25").date()] * 2,
        "close": [100.0, 110.0, 120.0, 130.0],
        "lado": [1, 1, 1, 1],
        "mov_contexto": [5.0] * 4,
    })
    r = ab.retornos(d, pd.Series([True, True, False, False]))
    assert len(r) == 0, "nenhuma janela de 2 barras cabe dentro do dia 24"


def test_sem_lookahead_no_contexto() -> None:
    """
    `mov_contexto` usa shift(1) para tras: a propria barra nao entra no
    contexto que a habilita. Sem isso, o teste mediria a barra de entrada.
    """
    d = ab.preparar(_barras(n=120))
    i = 100
    esperado = ((d["close"].iloc[i - 1] - d["close"].iloc[i - 1 - ab.JANELA_CONTEXTO])
                / d["range_medio"].iloc[i])
    assert d["mov_contexto"].iloc[i] == pytest.approx(esperado)


def test_range_medio_nao_inclui_a_propria_barra() -> None:
    d = ab.preparar(_barras(n=120))
    i = 100
    esperado = (d["amplitude_pts"].iloc[i - ab.JANELA_Z:i]).mean()
    assert d["range_medio"].iloc[i] == pytest.approx(esperado)


def test_decidir_contra_quando_nada_e_significativo() -> None:
    pontos = [{"grupo": "evento+contexto BAIXA", "n": 50, "n_suficiente": True,
               "media": 1.0, "sig": False},
              {"grupo": "evento+contexto ALTA", "n": 50, "n_suficiente": True,
               "media": 1.0, "sig": False}]
    v, _ = ab.decidir(pontos)
    assert v == "CONTRA"


def test_controles_nao_entram_no_veredito() -> None:
    """Sao diagnostico: respondem 'a conjuncao acrescenta algo?'."""
    pontos = [
        {"grupo": "evento+contexto BAIXA", "n": 50, "n_suficiente": True,
         "media": 1.0, "sig": False},
        {"grupo": "evento+contexto ALTA", "n": 50, "n_suficiente": True,
         "media": 1.0, "sig": False},
        {"grupo": "CONTROLE contexto sem evento", "n": 900,
         "n_suficiente": True, "media": 50.0, "sig": True},
    ]
    v, _ = ab.decidir(pontos)
    assert v == "CONTRA", "controle significativo nao pode virar FAVORAVEL"


def test_decidir_invertido() -> None:
    pontos = [{"grupo": "evento+contexto BAIXA", "n": 50, "n_suficiente": True,
               "media": -20.0, "sig": True},
              {"grupo": "evento+contexto ALTA", "n": 50, "n_suficiente": True,
               "media": 1.0, "sig": False}]
    v, m = ab.decidir(pontos)
    assert v == "INVERTIDO" and "ao contrario" in m


def test_ruido_tem_amplitude_e_volume_CORRELACIONADOS() -> None:
    """
    Defeito real do primeiro gerador: volume sorteado INDEPENDENTE do
    caminho do preco dava corr +0,012 contra +0,892 do real. Como o
    evento exige amplitude E volume altos ao mesmo tempo, o ruido
    produzia 25x menos eventos -- e testava outra geometria.
    """
    d = ab.preparar(ab.gerar_ruido(n_dias=30)).dropna(
        subset=["amplitude_pts", "vol_agr"])
    r = float(np.corrcoef(d["amplitude_pts"], d["vol_agr"])[0, 1])
    assert r > 0.4, f"amplitude e volume precisam andar juntos, deu {r:.3f}"


def _ntsl() -> str:
    from pathlib import Path as _P
    return (_P(__file__).resolve().parents[1] / "ntsl"
            / "absorcao_barra.ntsl").read_text(encoding="utf-8")


def test_o_ntsl_usa_as_MESMAS_constantes_congeladas() -> None:
    """
    O `.ntsl` e o Python sao dois lados da MESMA definicao congelada, e
    ate 2026-08-31 nada amarrava os dois lados de nada neste projeto --
    foi assim que o parser passou a exigir um campo que o indicador nunca
    emitiu, com a suite inteira verde.

    Se alguem ajustar um corte no grafico "so' para ver", este teste
    falha e diz que os dois lados divergiram.
    """
    t = _ntsl()
    esperado = {
        "MaxDeslocNorm": ab.MAX_DESLOC_NORM,
        "MinZAmplitude": ab.MIN_Z_AMPLITUDE,
        "MinZVolAgr": ab.MIN_Z_VOL_AGR,
        "JanelaZ": ab.JANELA_Z,
        "JanelaContexto": ab.JANELA_CONTEXTO,
        "KContexto": ab.K_CONTEXTO,
    }
    for nome, valor in esperado.items():
        import re
        m = re.search(rf"{nome}\(([^)]+)\)", t)
        assert m, f"`{nome}` nao aparece como input do .ntsl"
        assert float(m.group(1)) == float(valor), (
            f"{nome}: .ntsl tem {m.group(1)}, Python tem {valor}. "
            "A definicao e' CONGELADA -- mude nos DOIS lados, com "
            "pre-registro novo."
        )


def test_o_ntsl_nao_depende_de_AgressionVol() -> None:
    """
    `AgressionVolBuy/Sell` e' retido por UMA SEMANA (medido: zero em
    2.001 barras fora da janela, sem erro nenhum). O evento novo precisa
    so' do volume TOTAL de agressao, que tem historico profundo -- e e'
    por isso que da' para inspecionar anos de grafico.
    """
    t = _ntsl()
    # So' o CODIGO conta: o cabecalho CITA a funcao ao explicar por que
    # nao a usa, e proibir a mencao apagaria a explicacao. Foi o proprio
    # teste que falhou primeiro, por essa razao.
    codigo = "\n".join(linha for linha in t.splitlines()
                       if not linha.lstrip().startswith("//"))
    assert "AgressionVolBuy" not in codigo
    assert "AgressionVolSell" not in codigo
    assert "QuantityVol(False, True)" in codigo


def test_o_ntsl_espera_o_aquecimento_das_DUAS_janelas() -> None:
    """
    Precisa das 50 barras da referencia MAIS as 6 do contexto. Marcar
    barra no aquecimento produziria evento a partir de janela
    incompleta, e no grafico ele pareceria um evento normal.
    """
    t = _ntsl()
    assert "CurrentBar > JanelaZ + JanelaContexto" in t


def test_z_compara_contra_as_barras_ANTERIORES_e_nao_inclui_a_atual() -> None:
    """
    ERRATA de 2026-09-01, achada pela conferencia contra o `.ntsl`.

    O pre-registro dizia "vs 50 barras" sem especificar se a propria
    barra entrava, e as duas implementacoes resolveram para lados
    OPOSTOS: o `.ntsl` percorre so' as anteriores, o `rolling()` incluia
    a atual. Divergencia em dado real: ate 19,9 no z da amplitude.

    A do `.ntsl` e' a correta por MECANISMO: "atipica em relacao ao
    normal recente" compara contra a HISTORIA, e incluir a propria barra
    atenua o que se quer detectar -- a barra grande infla a propria
    media e o proprio desvio.
    """
    d = ab.preparar(_barras(n=120))
    i = 100
    anteriores = d["amplitude_pts"].iloc[i - ab.JANELA_Z:i]
    esperado = ((d["amplitude_pts"].iloc[i] - anteriores.mean())
                / anteriores.std())
    assert d["z_amplitude"].iloc[i] == pytest.approx(esperado)

    ant_vol = d["vol_agr"].iloc[i - ab.JANELA_Z:i]
    esperado_vol = (d["vol_agr"].iloc[i] - ant_vol.mean()) / ant_vol.std()
    assert d["z_vol_agr"].iloc[i] == pytest.approx(esperado_vol)


def test_barra_extrema_tem_z_MAIOR_com_a_definicao_certa() -> None:
    """
    Consequencia direta, e o motivo de a diferenca importar: uma barra
    muito atipica, incluida na propria referencia, infla media e desvio e
    sai com z MENOR. Excluindo-a, o z reflete o quanto ela destoa.
    """
    b = _barras(n=120, semente=9)
    b.loc[100, "high"] = b.loc[100, "low"] + 100_000     # barra absurda
    a = b["high"] - b["low"]
    b["desloc_norm"] = ((b["close"] - b["open"]) / a).where(a > 0, 0.0)
    d = ab.preparar(b)

    anteriores = d["amplitude_pts"].iloc[50:100]
    z_certo = (d["amplitude_pts"].iloc[100] - anteriores.mean()) / anteriores.std()
    com_atual = d["amplitude_pts"].iloc[51:101]
    z_errado = (d["amplitude_pts"].iloc[100] - com_atual.mean()) / com_atual.std()

    assert d["z_amplitude"].iloc[100] == pytest.approx(z_certo)
    assert z_certo > z_errado, "excluir a barra atual tem que dar z maior"


def test_contexto_NAO_atravessa_a_virada_do_pregao() -> None:
    """
    ERRATA de 2026-09-02, achada pelo operador na inspecao visual de
    14/05: "uma barra forte que INICIA o movimento depois de uma
    sequencia de barras fracas" -- o oposto de absorcao.

    `mov_contexto` e' uma DIFERENCA DE PRECO e atravessava a virada,
    medindo o GAP NOTURNO. Medido no dump de maio: |mov_contexto| tinha
    mediana 3,58 nas 6 primeiras barras contra 0,80 no resto, com o
    habilitador em 3,0 -- 42% dos eventos caiam em 5% do pregao.
    """
    n = 60
    dias = ([pd.Timestamp("2026-08-24").date()] * (n // 2)
            + [pd.Timestamp("2026-08-25").date()] * (n // 2))
    # gap ENORME entre os dois dias
    preco = [100_000.0] * (n // 2) + [200_000.0] * (n // 2)
    b = pd.DataFrame({"dia": dias, "open": preco, "close": preco,
                      "high": [p + 100 for p in preco],
                      "low": [p - 100 for p in preco],
                      "vol_agr": 50_000.0, "desloc_norm": 0.0})
    d = ab.preparar(b)
    primeiras = d[d["dia"] == pd.Timestamp("2026-08-25").date()].head(
        ab.JANELA_CONTEXTO)
    assert primeiras["mov_contexto"].isna().all(), (
        "as primeiras barras do dia nao podem ter contexto: ele viria do "
        "pregao anterior, medindo o gap")


def test_purga_vale_SO_no_contexto_e_nao_nos_z() -> None:
    """
    `z_amplitude` e `z_vol_agr` sao grandezas INTRABARRA -- o gap nao as
    corrompe. Purgar as tres custaria as 50 primeiras barras de cada
    pregao (46% da amostra) sem corrigir defeito nenhum.
    """
    b = _barras(n=200)
    b.loc[100:, "dia"] = pd.Timestamp("2026-08-28").date()
    d = ab.preparar(b)
    depois_da_virada = d.iloc[100:160]
    assert depois_da_virada["z_amplitude"].notna().any(), (
        "os z nao devem ser purgados na virada: amplitude e volume sao "
        "intrabarra")


def test_o_ntsl_TAMBEM_purga_o_contexto_na_virada() -> None:
    """
    Pego ao responder "o que fazer agora": eu corrigi a purga no Python
    (v1.72) e NAO no `.ntsl`. O indicador continuaria pintando as barras
    de gap enquanto o estimador as ignora — recriando exatamente a
    divergencia que a errata do `z` tinha acabado de eliminar.

    O teste que compara os dois lados so' olhava CONSTANTES, nao
    comportamento. Este olha a guarda.
    """
    t = _ntsl()
    codigo = "\n".join(linha for linha in t.splitlines()
                       if not linha.lstrip().startswith("//"))
    # O acesso posicional e' LIDO NO TOPO, em atribuicao simples, e a
    # condicao usa a variavel. Ler `Date[...]` dentro do `if` disparava
    # "acessos a contextos posicionais dentro de escopos condicionais
    # possuem comportamento indefinido" -- a guarda podia nao funcionar.
    assert "sDataContexto := Date[1 + JanelaContexto]" in codigo, (
        "o acesso posicional tem que ser lido no topo, em atribuicao")
    assert "sDataContexto = Date" in codigo, (
        "o .ntsl precisa recusar contexto que comece em outro pregao, "
        "como o Python faz com groupby('dia')")
    assert "if (sRangeMedio > 0) and (Date[" not in codigo, (
        "acesso posicional NAO pode voltar para dentro da condicao")


def test_o_ntsl_avisa_se_a_periodicidade_estiver_errada() -> None:
    """
    Erro real (2026-09-02): o grafico estava em 1M com os parametros de
    5M. O indicador calcula tudo normalmente e devolve numeros
    PLAUSIVEIS para o timeframe errado -- falha silenciosa.

    `JanelaContexto = 6` vira 6 minutos em vez de 30; `JanelaZ = 50` vira
    50 minutos em vez de 4 horas. As razoes (`|desloc_norm|`) e os
    z-scores transferem; as JANELAS nao.
    """
    codigo = "\n".join(linha for linha in _ntsl().splitlines()
                       if not linha.lstrip().startswith("//"))
    assert "RS_BarsPerDay" in codigo, (
        "o .ntsl precisa checar a periodicidade do grafico")
    assert "BarsPorDiaEsperado(288)" in codigo, (
        "288 = 1440/5, a periodicidade que o pre-registro congelou")


def test_janela_movel_NAO_atravessa_buraco_na_amostra() -> None:
    """
    Achado em 2026-09-03 ao rodar o combinado das duas partes de 2026. O
    dump concatena 02/01-30/04 com 01/06-23/07, e MAIO nao esta la'.

    O `.ntsl` calculou sobre o grafico CONTINUO (abril -> maio -> junho);
    o Python le' o arquivo (abril -> junho). Nas primeiras 50 barras de
    junho a janela do Python pegava ABRIL enquanto a do NTSL pegou MAIO.
    `z_amplitude` divergiu ate **6,20**, contra 4,89e-06 na parte 1
    sozinha.

    Mesmo principio da purga de dia: referencia movel nao cruza
    descontinuidade. Aqui a descontinuidade e' de AMOSTRA.
    """
    linhas = []
    for bloco, (ini, n) in enumerate((("2026-01-02", 120), ("2026-06-01", 120))):
        for i in range(n):
            dia = (pd.Timestamp(ini) + pd.Timedelta(days=i // 60)).date()
            linhas.append({
                "dia": dia, "open": 100.0,
                # amplitude MUITO diferente entre os blocos: se a janela
                # atravessasse, o z do bloco 2 sairia gigante
                "high": 110.0 + bloco * 50, "low": 90.0, "close": 105.0,
                "vol_agr": 1000.0 + bloco * 500, "desloc_norm": 0.3,
            })
    d = ab.preparar(pd.DataFrame(linhas))

    assert d["_bloco"].nunique() == 2, "o buraco de 30 dias tem que criar bloco"
    bloco2 = d[d["_bloco"] == 1]
    assert bloco2["z_amplitude"].head(ab.JANELA_Z).isna().all(), (
        "as primeiras barras do bloco novo nao podem ter z: a janela "
        "usaria dados do bloco anterior")


def test_fim_de_semana_e_feriado_NAO_criam_bloco() -> None:
    """
    Se um fim de semana longo virasse buraco, cada semana perderia 50
    barras e a amostra sumiria. O corte e' 10 dias.
    """
    linhas = []
    for salto in (0, 3, 4, 8):        # sabado/domingo, feriado, semana curta
        base = pd.Timestamp("2026-03-02") + pd.Timedelta(days=salto)
        for _ in range(5):
            linhas.append({"dia": base.date(), "open": 100.0, "high": 110.0,
                           "low": 90.0, "close": 105.0, "vol_agr": 1000.0,
                           "desloc_norm": 0.3})
    d = ab.preparar(pd.DataFrame(linhas))
    assert d["_bloco"].nunique() == 1, (
        "saltos de calendario normais nao podem fragmentar a amostra")
