"""
Testes do estimador do pre-registro 3 da Rota B.

O teste central e' o de calibracao: o estimador tem que devolver
`CONTRA` sobre ruido puro. Isso nao e' esperanca — e' o teorema da
parada opcional, e o teste verifica se o CODIGO corresponde a ele.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from profittape.research.preenchimento import preparar_tape
from profittape.research.remanescente_tape import (
    _com_dia,
    _remanescentes_tape,
    checagem_de_prevoo,
    decidir,
)

S = 1_000_000_000


def _barras(n: int = 8, z: list[float] | None = None) -> pd.DataFrame:
    """Barras sinteticas com ts_close espacado de 60s."""
    z = z if z is not None else [0.0] * n
    base = pd.Timestamp("2026-08-24", tz="UTC").value + 13 * 3600 * S
    return pd.DataFrame({
        "bar_id": range(n),
        "ts_close": [base + (i + 1) * 60 * S for i in range(n)],
        "close": [100_000.0] * n,
        "z_teste": z,
        "dia": [pd.Timestamp("2026-08-24").date()] * n,
    })


def _tape_precos(precos: list[float], t0: int, passo_s: int = 1) -> pd.DataFrame:
    return preparar_tape(pd.DataFrame({
        "ts_ns": [t0 + i * passo_s * S for i in range(len(precos))],
        "price": precos,
        "trade_type": 2,
    }))


def test_operacao_que_nao_toca_e_excluida() -> None:
    """Nao ha grupo de comparacao: e' uma amostra contra zero."""
    barras = _barras(z=[0, 2.0, 0, 0, 0, 0, 0, 0])
    base = int(barras["ts_close"].iloc[1])
    tape = _tape_precos([100_000.0] * 200, base + 1)
    r = _remanescentes_tape(barras, tape, "z_teste", 3, 1.4,
                            "contrarian", "venda", 40.0)
    assert len(r) == 0


def test_remanescente_e_medido_a_partir_de_F() -> None:
    """
    Venda a 100.000, stop a +40. O tape sobe a 100.045 (overshoot de 5) e
    volta para 100.010 no fim da janela.

    remanescente = (close_fim - F) * lado = (100010 - 100045) * (-1) = +35

    Medir a partir do NIVEL daria (100010-100040)*(-1) = +30: e' o limite
    'otimista' anulado em 2026-08-29c, que ignora o overshoot real.
    """
    barras = _barras(z=[0, 2.0, 0, 0, 0, 0, 0, 0])
    barras.loc[4, "close"] = 100_010.0          # fim da janela (t+3)
    base = int(barras["ts_close"].iloc[1])
    tape = _tape_precos([100_020.0, 100_045.0, 100_010.0], base + 1, passo_s=10)

    r = _remanescentes_tape(barras, tape, "z_teste", 3, 1.4,
                            "contrarian", "venda", 40.0)
    assert len(r) == 1
    assert r["F"].iloc[0] == 100_045.0
    assert r["overshoot"].iloc[0] == pytest.approx(5.0)
    assert r["remanescente"].iloc[0] == pytest.approx(35.0)


def test_janela_nunca_atravessa_o_pregao() -> None:
    """Purga estrutural: se t+h cai em outro dia, a operacao e' descartada."""
    barras = _barras(n=4, z=[0, 2.0, 0, 0])
    barras.loc[3, "dia"] = pd.Timestamp("2026-08-25").date()
    base = int(barras["ts_close"].iloc[1])
    tape = _tape_precos([100_050.0] * 10, base + 1)
    r = _remanescentes_tape(barras, tape, "z_teste", 3, 1.4,
                            "contrarian", "venda", 40.0)
    assert len(r) == 0


def test_prevoo_separa_os_dois_lados() -> None:
    """
    A reconciliacao existe para responder se '336 gatilhos' eram
    compra+venda somados. Ela so' serve se as contagens vierem separadas.
    """
    barras = _barras(n=10, z=[0, 2.0, -2.0, 0, 0, 2.0, 0, 0, 0, 0])
    p = checagem_de_prevoo(barras, "z_teste", 3, 1.4, "contrarian", "venda")
    assert p["validos_compra"] + p["validos_venda"] == p["validos_ambos"]
    assert p["usados_neste_teste"] == p["validos_venda"]
    assert p["gatilhos_brutos"] >= p["validos_ambos"]


def test_com_dia_nao_sobrescreve_coluna_existente() -> None:
    b = _barras(n=3)
    marcado = b.assign(dia="SENTINELA")
    assert list(_com_dia(marcado)["dia"]) == ["SENTINELA"] * 3


def test_decidir_contra_quando_nada_e_significativo() -> None:
    pontos = [{"x": x, "n": 100, "n_suficiente": True, "media": 0.5,
               "t": 0.2, "sig": False} for x in (40, 60, 80)]
    veredito, _ = decidir(pontos)
    assert veredito == "CONTRA"


def test_decidir_exige_monotonicidade() -> None:
    """
    A grade e' aninhada, mas isso garante que o `n` cai com X — NAO que a
    media siga direcao alguma. Por isso a monotonicidade e' criterio de
    verdade e nao formalidade.
    """
    pontos = [
        {"x": 40, "n": 100, "n_suficiente": True, "media": -10.0, "t": -5.0,
         "sig": True},
        {"x": 60, "n": 90, "n_suficiente": True, "media": +8.0, "t": 1.0,
         "sig": False},   # positivo acima de X* quebra a monotonicidade
    ]
    veredito, motivo = decidir(pontos)
    assert veredito == "INCONCLUSIVO" and "monotonico" in motivo


def test_decidir_favoravel_com_monotonicidade() -> None:
    pontos = [
        {"x": 40, "n": 100, "n_suficiente": True, "media": -10.0, "t": -5.0,
         "sig": True},
        {"x": 60, "n": 90, "n_suficiente": True, "media": -12.0, "t": -4.0,
         "sig": True},
    ]
    veredito, motivo = decidir(pontos)
    assert veredito == "FAVORAVEL" and "CANDIDATO" in motivo


def test_decidir_invertido() -> None:
    pontos = [{"x": 40, "n": 100, "n_suficiente": True, "media": 15.0,
               "t": 4.0, "sig": True}]
    veredito, motivo = decidir(pontos)
    assert veredito == "INVERTIDO" and "piramide" in motivo


def test_estimador_e_calibrado_sobre_ruido_puro() -> None:
    """
    O TESTE CENTRAL. `F` e' o preco do primeiro negocio a cruzar — tempo
    de parada legitimo — entao pelo teorema da parada opcional o
    remanescente medio tem que ser zero sob martingal.

    Os dois estimadores anteriores falhavam aqui: t ~ -25 (29a) e +30
    pontos com t entre 8 e 13 (29c). Ambos selecionavam num extremo de
    barra, que so' e' conhecido no fechamento e nao e' tempo de parada.
    """
    rng = np.random.default_rng(7)
    n_barras, negocios_por_barra = 600, 200
    precos_bar, ts_bar = [], []

    t = 0
    preco = 100_000.0
    tape_precos: list[float] = []
    tape_ts: list[int] = []
    for _ in range(n_barras):
        passos = rng.choice([-5.0, 5.0], size=negocios_por_barra)
        caminho = preco + np.cumsum(passos)
        tape_precos.extend(caminho.tolist())
        tape_ts.extend((t + np.arange(1, negocios_por_barra + 1) * 1_000_000
                        ).tolist())
        t = tape_ts[-1]
        preco = float(caminho[-1])
        precos_bar.append(preco)
        ts_bar.append(t)

    barras = pd.DataFrame({
        "bar_id": range(n_barras), "ts_close": ts_bar, "close": precos_bar,
        "z_teste": rng.normal(size=n_barras),
        "dia": [pd.Timestamp("2026-08-24").date()] * n_barras,
    })
    tape = preparar_tape(pd.DataFrame({
        "ts_ns": tape_ts, "price": tape_precos, "trade_type": 2}))

    r = _remanescentes_tape(barras, tape, "z_teste", 3, 1.0,
                            "contrarian", "venda", 60.0)
    assert len(r) >= 30, f"amostra pequena demais: {len(r)}"
    v = r["remanescente"].to_numpy()
    t_stat = v.mean() / (v.std(ddof=1) / np.sqrt(len(v)))
    assert abs(t_stat) < 3.0, f"vies: media={v.mean():.2f} t={t_stat:.2f}"


def test_descobre_volume_barra_do_resumo_json(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """
    Fonte exata. O `volume_barra` era so' impresso na tela ao gerar as
    features; quem fosse usar o parquet dias depois dependia do scroll de
    um terminal antigo. Parametro que define o dado viaja com o dado.
    """
    import json

    from profittape.research.remanescente_tape import descobrir_volume_barra

    arq = tmp_path / "features.parquet"
    arq.write_bytes(b"")
    (tmp_path / "resumo.json").write_text(
        json.dumps({"symbol": "WINFUT", "volume_barra": 7400}),
        encoding="utf-8")
    valor, origem = descobrir_volume_barra(arq, pd.DataFrame())
    assert valor == 7400 and "exato" in origem


def test_infere_volume_barra_de_vol_agr(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """
    Sem resumo.json, o minimo de `vol_agr` e' o estimador mais proximo
    por cima: uma barra so' fecha quando a agressao acumulada CRUZA o
    limiar, entao todo vol_agr >= limiar.
    """
    from profittape.research.remanescente_tape import descobrir_volume_barra

    arq = tmp_path / "features.parquet"
    limiar = 4000
    rng = np.random.default_rng(2)
    # cada barra fecha no limiar mais o excesso do ultimo negocio
    barras = pd.DataFrame({"vol_agr": limiar + rng.integers(0, 250, size=500)})
    valor, origem = descobrir_volume_barra(arq, barras)
    assert valor >= limiar
    assert valor - limiar < 250, "estimativa longe demais do limiar real"
    assert "aproximado" in origem


def test_sem_resumo_e_sem_vol_agr_pede_o_parametro(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from profittape.research.remanescente_tape import descobrir_volume_barra

    with pytest.raises(SystemExit, match="volume-barra"):
        descobrir_volume_barra(tmp_path / "features.parquet", pd.DataFrame())


def test_ruido_escala_a_quantidade_pelo_volume_barra() -> None:
    """
    Bug real (2026-08-30): o gerador fixava 20.000 negocios de 1 contrato
    por pregao. Com o `volume_barra` real do WINFUT (119.504), o dia
    inteiro somava 20.000 de volume e NENHUMA barra fechava — tudo virava
    parcial, era descartado, e o groupby vazio estourava dentro de
    `flow.calcular` com um erro do pandas que nao dizia nada sobre a
    causa.

    Duas escalas independentes: o numero de NEGOCIOS controla a geometria
    do preco; a QUANTIDADE por negocio faz a barra fechar onde deve.
    """
    from profittape.features import bars
    from profittape.research.remanescente_tape import gerar_ruido

    vb = 119_504
    ruido = gerar_ruido(volume_barra=vb, n_dias=3, barras_por_dia=20)
    barrado, _ = bars.atribuir_barras(ruido, vb)
    assert not barrado.empty, "nenhuma barra fechou"
    fechadas = barrado["bar_id"].nunique()
    assert fechadas >= 3 * 15, f"poucas barras: {fechadas}"
    # geometria preservada: ~200 negocios por barra
    assert 150 <= len(barrado) / fechadas <= 260


def test_flow_avisa_quando_nenhuma_barra_fecha() -> None:
    """
    O erro do pandas ("Cannot set a DataFrame with multiple columns")
    nao dizia nada sobre a causa. Agora diz.
    """
    from profittape.features import flow

    vazio = pd.DataFrame({
        "bar_id": pd.Series(dtype="int64"),
        "ts_ns": pd.Series(dtype="int64"),
        "price": pd.Series(dtype="float64"),
        "quantidade": pd.Series(dtype="int64"),
        "trade_type": pd.Series(dtype="int64"),
        "agente_comprador": pd.Series(dtype="int64"),
        "agente_vendedor": pd.Series(dtype="int64"),
    })
    with pytest.raises(ValueError, match="volume_barra"):
        flow.calcular(vazio, agentes=[], tick=5.0)


def _cenario_dois_dias() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Dois pregoes com 8 barras cada; entrada na barra 1 de cada dia."""
    barras_linhas, tape_linhas = [], []
    for d, dia_txt in enumerate(("2026-08-24", "2026-08-25")):
        base = pd.Timestamp(dia_txt, tz="UTC").value + 13 * 3600 * S
        for i in range(8):
            barras_linhas.append({
                "bar_id": d * 8 + i,
                "ts_close": base + (i + 1) * 60 * S,
                "close": 100_000.0,
                "z_teste": 2.0 if i == 1 else 0.0,
                "dia": pd.Timestamp(dia_txt).date(),
            })
        # Um negocio por segundo cobrindo os 8 minutos das barras: um
        # tape mais curto que a janela faria o toque nunca acontecer, e o
        # teste passaria a medir a fixture em vez do codigo.
        for k in range(8 * 60):
            tape_linhas.append({
                "ts_ns": base + k * S,
                "price": 100_000.0 + (60.0 if k > 130 else 0.0),
                "quantidade": 1, "trade_type": 2,
            })
    return pd.DataFrame(barras_linhas), pd.DataFrame(tape_linhas)


def test_apenas_dia_evita_falso_negativo_no_streaming() -> None:
    """
    No streaming o tape so' tem UM pregao. Sem o filtro `apenas_dia`, as
    entradas dos outros dias nao encontrariam o toque e sairiam como
    "nunca tocou" — falso negativo SILENCIOSO, que reduziria o `n` de
    todos os pontos sem erro nenhum.
    """
    barras, tape_bruto = _cenario_dois_dias()
    tape = preparar_tape(tape_bruto)

    todos = _remanescentes_tape(barras, tape, "z_teste", 3, 1.4,
                                "contrarian", "venda", 40.0)
    assert len(todos) == 2, "uma entrada por pregao"

    so_24 = _remanescentes_tape(barras, tape, "z_teste", 3, 1.4,
                                "contrarian", "venda", 40.0,
                                apenas_dia=pd.Timestamp("2026-08-24").date())
    assert len(so_24) == 1
    assert so_24["dia"].iloc[0] == pd.Timestamp("2026-08-24").date()


def test_streaming_e_memoria_dao_o_mesmo_resultado(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """
    O streaming existe por memoria: 81 MILHOES de negocios estouraram a
    maquina do operador. Mas otimizacao que muda a resposta nao e'
    otimizacao — os dois caminhos tem que coincidir.

    O carregamento por dia e' substituido para o teste exercitar a LOGICA
    de streaming, e nao o layout de parquet do pyarrow (que ja' tem
    testes proprios em outro lugar).
    """
    from pathlib import Path as _Path

    from profittape.research import remanescente_tape as mod

    barras, tape_bruto = _cenario_dois_dias()
    dias = ["2026-08-24", "2026-08-25"]

    def _dias_falsos(_raiz, _symbol):  # type: ignore[no-untyped-def]
        return [_Path(f"dt={d}") for d in dias]

    def _carregar_falso(pasta, _symbol):  # type: ignore[no-untyped-def]
        alvo = pd.Timestamp(pasta.name.removeprefix("dt=")).date()
        sel = tape_bruto[pd.to_datetime(tape_bruto["ts_ns"], unit="ns").dt.date
                         == alvo]
        return sel.reset_index(drop=True)

    monkeypatch.setattr("profittape.features.pipeline._dias_do_symbol",
                        _dias_falsos)
    monkeypatch.setattr("profittape.features.pipeline._carregar_dia",
                        _carregar_falso)

    em_memoria = _remanescentes_tape(barras, preparar_tape(tape_bruto),
                                     "z_teste", 3, 1.4, "contrarian",
                                     "venda", 40.0)
    streaming = mod._remanescentes_streaming(
        barras, _Path("."), "TESTE", "z_teste", 3, 1.4, "contrarian",
        "venda", (40.0,), True)[40.0]

    assert len(em_memoria) == len(streaming) == 2
    assert (sorted(em_memoria["remanescente"])
            == sorted(streaming["remanescente"]))
