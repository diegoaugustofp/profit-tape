"""Rolagem, pergunta A: persistencia do fluxo liquido por corretora no instrumento de roll."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from profittape.research import rolagem_persistencia as rp


def _trades(linhas: list[tuple[int, int, int]]) -> pd.DataFrame:
    """(comprador, vendedor, quantidade)."""
    return pd.DataFrame({"ts_ns": range(len(linhas)), "price": 30.0,
                         "quantidade": [q for _, _, q in linhas],
                         "agente_comprador": [c for c, _, _ in linhas],
                         "agente_vendedor": [v for _, v, _ in linhas], "trade_type": 2})


def test_liquido_exclui_cross_da_mesma_corretora() -> None:
    t = _trades([(1, 2, 10), (1, 1, 999), (3, 1, 4)])
    liq = rp.liquido_por_agente(t)
    assert liq.to_dict() == {1: 10 - 4, 2: -10, 3: 4}    # o cross 1x1 de 999 nao entra


def test_s_a_mao_com_exemplo_pequeno() -> None:
    # agente1: min(10,4)=4 mesmo sinal (+4); agente2: min(5,8)=5 oposto (-5);
    # agente3: min(3,3)=3 oposto (-3)
    v = np.array([[10.0, -5.0, 3.0], [4.0, 8.0, -3.0]])
    assert rp.estatistica_s(v) == pytest.approx(4 - 5 - 3)


def test_s_soma_as_transicoes() -> None:
    v = np.array([[5.0], [5.0], [-5.0]])
    assert rp.estatistica_s(v) == pytest.approx(5 - 5)    # (+) depois (-)


def _magnitudes_correlacionadas(n_ag: int, n_dias: int, rng: np.random.Generator) -> np.ndarray:
    escala = np.exp(rng.normal(0, 1.5, n_ag))                  # corretora grande e' grande todo dia
    mags = escala * np.exp(rng.normal(0, 0.3, (n_dias, n_ag)))
    return mags * rng.choice([-1.0, 1.0], size=(n_dias, n_ag))  # sinais INDEPENDENTES


def test_tamanho_do_teste_com_magnitudes_correlacionadas_e_sinais_independentes() -> None:
    """O verificador que faltou na v4.28: sem persistencia, rejeita ~alfa, nao muito mais."""
    rng = np.random.default_rng(1)
    rej = sum(rp.testar(_magnitudes_correlacionadas(30, 3, rng), 500,
                        int(rng.integers(1 << 30)))["p"] < 0.05 for _ in range(300))
    assert rej / 300 < 0.10


def test_persistencia_plantada_e_achada() -> None:
    rng = np.random.default_rng(2)
    base = _magnitudes_correlacionadas(30, 3, rng)
    plantada = rp._plantar(base, 1.0, rng)
    r = rp.testar(plantada, 2000)
    assert r["p"] < 0.01 and r["z"] > 2


def test_poder_cresce_com_a_fracao() -> None:
    rng = np.random.default_rng(3)
    v = _magnitudes_correlacionadas(30, 3, rng)
    p = rp.poder(v, fracoes=(0.0, 1.0), repeticoes=60, n_sorteios=300)
    assert p["0.00"] < 0.15 and p["1.00"] > 0.9


def test_permutacao_entre_corretoras_seria_enviesada() -> None:
    """Documenta POR QUE o nulo e' a inversao de sinal: a permutacao inventa sinal."""
    rng = np.random.default_rng(4)
    escala = np.exp(rng.normal(0, 1.5, 30))
    sg = rng.choice([-1.0, 1.0], size=(2, 30))                 # sem persistencia
    v = escala * np.exp(rng.normal(0, 0.3, (2, 30))) * sg
    obs = []
    nulo_perm = []
    for _ in range(400):
        w = escala * np.exp(rng.normal(0, 0.3, (2, 30))) * rng.choice([-1.0, 1.0], size=(2, 30))
        obs.append(rp.estatistica_s(w))
        nulo_perm.append(rp.estatistica_s(np.vstack([w[0], rng.permutation(w[1])])))
    # a permutacao subestima a dispersao: p enganosamente pequeno
    assert np.std(obs) > np.std(nulo_perm)
    assert v.shape == (2, 30)


def test_descrever_roda_ponta_a_ponta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d1, d2 = dt.date(2026, 9, 28), dt.date(2026, 9, 29)
    tabelas = {d1: _trades([(1, 2, 10), (3, 4, 5), (2, 3, 2)]),
               d2: _trades([(1, 2, 8), (3, 4, 6), (5, 1, 1)])}
    curated = tmp_path / "curated"
    for d in tabelas:
        (curated / "trade" / f"dt={d.isoformat()}" / "sym=WD1V26X26").mkdir(parents=True)
    monkeypatch.setattr(rp, "_carregar_dia",
                        lambda pasta, sym: tabelas[dt.date.fromisoformat(pasta.name[3:])])
    r = rp.descrever(curated, "WD1V26X26", [d1, d2, dt.date(2026, 9, 30)], 500, False,
                     tmp_path / "saida")
    assert r["dias"] == ["2026-09-28", "2026-09-29"]          # 30/09 sem dado: ignorado
    assert len(r["transicoes"]) == 1 and r["transicoes"][0]["S"] > 0
    assert (tmp_path / "saida" / "rolagem_persistencia.json").exists()


def test_dia_unico_nao_gera_transicao(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d1 = dt.date(2026, 9, 28)
    curated = tmp_path / "curated"
    (curated / "trade" / f"dt={d1.isoformat()}" / "sym=WD1V26X26").mkdir(parents=True)
    monkeypatch.setattr(rp, "_carregar_dia", lambda pasta, sym: _trades([(1, 2, 3)]))
    r = rp.descrever(curated, "WD1V26X26", [d1], 100, False, tmp_path / "s")
    assert "transicoes" not in r


# ---------------------------------------------------------------- modo primario (v4.31)

def _montar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
            dias_roll: dict[dt.date, pd.DataFrame], dias_extra: list[dt.date]) -> Path:
    """curated com o roll nos `dias_roll` e um simbolo qualquer nos `dias_extra` (calendario)."""
    curated = tmp_path / "curated"
    for d in dias_roll:
        (curated / "trade" / f"dt={d.isoformat()}" / "sym=WD1V26X26").mkdir(parents=True)
    for d in dias_extra:
        (curated / "trade" / f"dt={d.isoformat()}" / "sym=WINFUT").mkdir(parents=True)
    monkeypatch.setattr(rp, "_carregar_dia",
                        lambda pasta, sym: dias_roll[dt.date.fromisoformat(pasta.name[3:])])
    return curated


def _dia_grande(rng: np.random.Generator, sinais: np.ndarray | None = None,
                n_ag: int = 30) -> pd.DataFrame:
    """Um pregao do roll: cada corretora compra ou vende um lote contra uma contraparte fixa."""
    mags = np.exp(rng.normal(3, 1.2, n_ag)).round().astype(int) + 1
    sg = rng.choice([-1, 1], n_ag) if sinais is None else sinais
    linhas = []
    for a in range(n_ag):
        contra = 100 + a
        linhas.append((a, contra, int(mags[a])) if sg[a] > 0 else (contra, a, int(mags[a])))
    return _trades(linhas)


D = [dt.date(2026, 10, 9), dt.date(2026, 10, 13), dt.date(2026, 10, 14)]


def test_primaria_persistencia_plantada_e_detectada(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rng = np.random.default_rng(10)
    sg = rng.choice([-1, 1], 30)
    dias = {d: _dia_grande(rng, sg) for d in D}               # mesmo sinal todos os dias
    curated = _montar(tmp_path, monkeypatch, dias, [dt.date(2026, 10, 8)])
    r = rp.avaliar_primaria(curated, "WD1V26X26", D[-1], 2000, tmp_path / "s", 120)
    assert r["janela"] == [d.isoformat() for d in D]
    assert r["portao"]["aprovado"] is True
    assert r["veredito"] == "persistencia_detectada" and "resultado" in r
    assert (tmp_path / "s" / "primaria_WD1V26X26_2026-10-14.json").exists()


def test_primaria_sem_persistencia_com_portao_aprovado(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rng = np.random.default_rng(11)
    dias = {d: _dia_grande(rng) for d in D}                   # sinais independentes
    curated = _montar(tmp_path, monkeypatch, dias, [])
    r = rp.avaliar_primaria(curated, "WD1V26X26", D[-1], 2000, tmp_path / "s", 120)
    assert r["portao"]["aprovado"] is True
    assert r["veredito"] in ("sem_persistencia_detectavel", "persistencia_detectada")
    assert "resultado" in r


def _dia_so_tres(rng: np.random.Generator) -> pd.DataFrame:
    """So' 3 corretoras negociando entre si: poucos graus de liberdade, sem poder."""
    linhas = []
    for _ in range(12):
        c, v = rng.choice(3, 2, replace=False)
        linhas.append((int(c), int(v), int(rng.integers(1, 50))))
    return _trades(linhas)


def test_primaria_portao_reprovado_nao_expoe_o_resultado(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rng = np.random.default_rng(12)
    dias = {d: _dia_so_tres(rng) for d in D}
    curated = _montar(tmp_path, monkeypatch, dias, [])
    r = rp.avaliar_primaria(curated, "WD1V26X26", D[-1], 500, tmp_path / "s", 120)
    assert r["portao"]["aprovado"] is False
    assert r["veredito"] == "inconclusivo_por_desenho"
    assert "resultado" not in r and "descritivo_nao_interpretar" in r


def _dia_soma_zero(rng: np.random.Generator, p: np.ndarray) -> pd.Series:
    b = rng.choice(len(p), 800, p=p)
    s = rng.choice(len(p), 800, p=p)
    ok = b != s
    q = np.maximum(1, np.exp(rng.normal(2.5, 1.4, int(ok.sum()))).round())
    return rp.liquido_por_agente(pd.DataFrame({
        "agente_comprador": b[ok], "agente_vendedor": s[ok], "quantidade": q}))


def test_tamanho_em_mercado_de_soma_zero() -> None:
    """Cada negocio tem comprador e vendedor (soma zero); sem persistencia, nao rejeita demais.
    Medido em 2026-10-04 com 400 repeticoes: 5,8% a 6,8% em cinco desenhos."""
    rng = np.random.default_rng(21)
    rej = 0
    for _ in range(150):
        w = np.exp(rng.normal(0, 1.5, 27))
        p = w / w.sum()
        v = rp.alinhar([_dia_soma_zero(rng, p) for _ in range(3)])
        rej += rp.testar(v, 400, int(rng.integers(1 << 30)))["p"] < 0.05
    assert rej / 150 < 0.12


def test_primaria_dia_vazio_no_roll_nao_desliza_a_janela(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """D-1 sem negocios no roll, mas com pregao no calendario: inconclusivo, nao usa D-3."""
    rng = np.random.default_rng(13)
    dias = {D[0]: _dia_grande(rng), D[2]: _dia_grande(rng)}
    curated = _montar(tmp_path, monkeypatch, dias, [D[1], dt.date(2026, 10, 8)])
    monkeypatch.setattr(rp, "_carregar_dia",
                        lambda pasta, sym: dias.get(dt.date.fromisoformat(pasta.name[3:]),
                                                    pd.DataFrame()))
    (curated / "trade" / f"dt={D[1].isoformat()}" / "sym=WD1V26X26").mkdir(parents=True)
    r = rp.avaliar_primaria(curated, "WD1V26X26", D[-1], 300, tmp_path / "s", 60)
    assert r["janela"] == [d.isoformat() for d in D]
    assert r["veredito"] == "inconclusivo_por_desenho"
    assert D[1].isoformat() in r["motivo"] and r["portao"] == {"avaliado": False}


def test_primaria_exige_o_ultimo_pregao_no_calendario(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rng = np.random.default_rng(14)
    dias = {D[0]: _dia_grande(rng), D[1]: _dia_grande(rng)}
    curated = _montar(tmp_path, monkeypatch, dias, [])
    with pytest.raises(ValueError, match="falta backfill/curate"):
        rp.avaliar_primaria(curated, "WD1V26X26", D[-1], 100, tmp_path / "s", 30)


def test_primaria_exige_tres_pregoes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rng = np.random.default_rng(15)
    dias = {D[1]: _dia_grande(rng), D[2]: _dia_grande(rng)}
    curated = _montar(tmp_path, monkeypatch, dias, [])
    with pytest.raises(ValueError, match="precisa de 3"):
        rp.avaliar_primaria(curated, "WD1V26X26", D[-1], 100, tmp_path / "s", 30)


def test_primaria_grava_carimbo_e_o_hash_muda_com_o_mecanismo(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Carimbo de versao (skill forward, regra 2): eventos de mecanismos diferentes nao se somam."""
    rng = np.random.default_rng(17)
    dias = {d: _dia_grande(rng) for d in D}
    curated = _montar(tmp_path, monkeypatch, dias, [])
    a = rp.avaliar_primaria(curated, "WD1V26X26", D[-1], 300, tmp_path / "s", 40)
    b = rp.avaliar_primaria(curated, "WD1V26X26", D[-1], 300, tmp_path / "s", 40)
    c = rp.avaliar_primaria(curated, "WD1V26X26", D[-1], 600, tmp_path / "s", 40)
    assert isinstance(a["carimbo"]["codigo"], str) and a["carimbo"]["codigo"]
    assert a["carimbo"]["limiares_sha"] == b["carimbo"]["limiares_sha"]
    assert a["carimbo"]["limiares_sha"] != c["carimbo"]["limiares_sha"]


def test_hash_dos_limiares_depende_dos_limiares_da_ficha(
        monkeypatch: pytest.MonkeyPatch) -> None:
    base = rp._sha_limiares(20000, 500)
    monkeypatch.setattr(rp, "PORTAO_PODER_MIN", 0.60)
    assert rp._sha_limiares(20000, 500) != base


def test_modo_livre_mantem_o_comportamento_antigo(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Retrocompatibilidade: `descrever` devolve as mesmas chaves de antes (+ `modo`)."""
    rng = np.random.default_rng(16)
    dias = {d: _dia_grande(rng) for d in D}
    curated = _montar(tmp_path, monkeypatch, dias, [])
    r = rp.descrever(curated, "WD1V26X26", D, 300, False, tmp_path / "s")
    assert {"roll", "dias", "por_dia", "n_sorteios", "transicoes", "conjunto"} <= set(r)
    assert r["modo"] == "livre" and "veredito" not in r
    assert (tmp_path / "s" / "rolagem_persistencia.json").exists()


def test_cli_primaria_recusa_janela_livre_e_exige_d(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from profittape.cli import app
    runner = CliRunner()
    r1 = runner.invoke(app, ["rolagem-persistencia", "--primaria", "--de", "2026-10-01",
                             "--curated", str(tmp_path)])
    assert r1.exit_code == 2
    r2 = runner.invoke(app, ["rolagem-persistencia", "--primaria", "--curated", str(tmp_path)])
    assert r2.exit_code == 2
    r3 = runner.invoke(app, ["rolagem-persistencia", "--de", "2026-10-01",
                             "--curated", str(tmp_path)])
    assert r3.exit_code == 2                                   # modo livre sem --ate
    r4 = runner.invoke(app, ["rolagem-persistencia", "--primaria", "--ultimo-pregao",
                             "2026-10-14", "--curated", str(tmp_path)])
    assert r4.exit_code == 2                                   # D sem dado: erro, nao desliza
