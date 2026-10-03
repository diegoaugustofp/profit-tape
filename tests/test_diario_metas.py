"""Metas de avaliacao por EA no indice do diario (v4.15)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from profittape import diario_metas as M

RAIZ = Path(__file__).resolve().parents[1] / "docs" / "eas"


def test_toda_meta_do_registro_ainda_esta_na_ficha() -> None:
    """Guarda de deriva: se a ficha mudar a regra e o trecho sumir, o teste falha e a meta
    velha nao fica no indice em silencio."""
    metas = M.carregar_metas(RAIZ / "metas.yaml")
    assert len(metas) >= 5
    for m in metas:
        ficha = RAIZ / m["ficha"]
        assert ficha.exists(), f"{m['ea']}: ficha {m['ficha']} nao existe"
        texto = ficha.read_text(encoding="utf-8")
        assert m["trechos"], f"{m['ea']}: sem trecho literal da ficha"
        for tr in m["trechos"]:
            assert tr in texto, f"{m['ea']}: trecho sumiu de {m['ficha']}: {tr!r}"
        ns = [x["n"] for x in m.get("metas") or []]
        assert ns == sorted(ns)


def test_status_da_ficha_sem_markdown_e_preservando_nomes() -> None:
    s = M.status_da_ficha(RAIZ, "ignicao.md", max_chars=2000)
    assert s.startswith("F5") and "ea/service_ignicao.py" in s and "**" not in s and "`" not in s
    assert M.status_da_ficha(RAIZ, "nao_existe.md") == "ficha nao_existe.md nao encontrada"


def _ops() -> pd.DataFrame:
    linhas = []

    def add(dia: str, ea: str, hora: str, motivo: str, pnl: float, slip: float | None = None,
            desc: bool = False) -> None:
        linhas.append({"dia": dia, "ea": ea, "hora_saida": hora, "motivo": motivo,
                       "pnl_liquido": pnl, "slippage_ordens_pts": slip, "descartado": desc})
    add("2026-09-26", "ea_ignicao", "10:00:00", "stop", -500)      # antes do forward: nao conta
    add("2026-09-29", "ea_ignicao", "10:00:00", "alvo", 520)
    add("2026-09-30", "ea_ignicao", "10:00:00", "tempo", 40)       # tempo nao decide
    add("2026-09-30", "ea_ignicao", "11:00:00", "stop", -534)
    add("2026-10-01", "ea_ignicao", "09:58:46", "stop", -599)
    add("2026-09-30", "123 (E4)", "10:00:00", "alvo", 120, 4.0)
    add("2026-10-01", "123 (E4)", "10:00:00", "stop", -80, 8.0)
    add("2026-10-01", "123 (E4)", "11:00:00", "desfecho", 0, None)  # sem ordens: nao conta
    add("2026-10-01", "ea_vwapvp_continuacao", "12:00:00", "alvo", 300)
    add("2026-10-02", "ea_vwapvp_continuacao", "12:00:00", "stop", -600)
    add("2026-10-02", "ea_vwapvp_continuacao", "14:00:00", "stop", -700)
    add("2026-10-01", "ea_microprice", "09:15:09", "alvo", 11, desc=True)
    return pd.DataFrame(linhas)


def _dias() -> pd.DataFrame:
    return pd.DataFrame({"dia": ["2026-09-26", "2026-09-29", "2026-09-30", "2026-10-01",
                                 "2026-10-02"]})


def _entrada(ea: str) -> dict:
    return next(m for m in M.carregar_metas(RAIZ / "metas.yaml") if m["ea"] == ea)


def test_progresso_da_ignicao_conta_so_decididos_desde_o_inicio_do_forward() -> None:
    p = M.progresso(_entrada("ea_ignicao"), _ops(), _dias())
    assert p["n"] == 3                                   # alvo 29/09, stop 30/09, stop 01/10
    assert p["proximo"]["n"] == 68 and p["faltam"] == 65
    assert p["pregoes"] == 4                             # 29/09, 30/09, 01/10, 02/10
    assert p["ritmo_obs"] == pytest.approx(0.75) and p["ritmo_ficha"] == 1.07
    # 65 / 0,75 = 86,7 -> 87 pregoes uteis depois de 02/10 (sexta)
    assert p["faltam_pregoes"] == 87 and p["previsao"].weekday() < 5
    assert p["previsao"] > dt.date(2026, 10, 2) and p["prazo"] == dt.date(2027, 3, 28)
    assert "slippage_medio" not in p and "media" not in p        # sem veredito parcial


def test_progresso_do_123_conta_so_operacoes_com_ordens_e_marcos_em_ordem() -> None:
    p = M.progresso(_entrada("123 (E4)"), _ops(), _dias())
    assert p["n"] == 2 and p["proximo"]["n"] == 50 and p["faltam"] == 48
    assert p["slippage_medio"] == pytest.approx(6.0)
    assert [m["n"] for m in p["metas"]] == [50, 100, 200] and p["atingidas"] == []
    # com 60 contadas: o proximo marco passa a ser 100 e o de 50 aparece como atingido
    extra = pd.DataFrame([{"dia": "2026-10-02", "ea": "123 (E4)", "hora_saida": f"{h:02d}:00:00",
                           "motivo": "alvo", "pnl_liquido": 1.0, "slippage_ordens_pts": 3.0,
                           "descartado": False} for h in range(9, 67)])
    for k in range(58):
        extra.loc[k, "hora_saida"] = f"10:{k:02d}:00"
    p2 = M.progresso(_entrada("123 (E4)"), pd.concat([_ops(), extra], ignore_index=True), _dias())
    assert p2["n"] == 60 and p2["proximo"]["n"] == 100 and [m["n"] for m in p2["atingidas"]] == [50]


def test_progresso_do_vwapvp_traz_media_e_drawdown_da_regra_de_morte() -> None:
    p = M.progresso(_entrada("ea_vwapvp_continuacao"), _ops(), _dias())
    assert p["n"] == 3 and p["proximo"]["n"] == 40 and p["faltam"] == 37
    assert p["media"] == pytest.approx((300 - 600 - 700) / 3)
    # curva: +300, -300, -1000 -> pico 300 -> vale -1000 => drawdown 1300
    assert p["drawdown"] == pytest.approx(1300.0)
    assert p["morte"]["dd_pts"] == 7000 and p["morte"]["n_media_negativa"] == 40


def test_descartados_nao_contam_e_ea_sem_meta_numerica() -> None:
    p = M.progresso(_entrada("ea_microprice"), _ops(), _dias())
    assert p["n"] == 0 and p["proximo"] is None and p["faltam"] is None
    z = M.progresso(_entrada("z_agf_win"), _ops(), _dias())
    assert z["n"] == 0 and z["metas"] == [] and z["previsao"] is None


def test_previsao_pula_fim_de_semana() -> None:
    sexta = dt.date(2026, 10, 2)
    assert M._dias_uteis_apos(sexta, 1) == dt.date(2026, 10, 5)
    assert M._dias_uteis_apos(sexta, 6) == dt.date(2026, 10, 12)


# ------------------------------------------------ fonte CSV (deepscalper Fase 2, offline)
def _livro(tmp_path: Path, dias: int = 18, por_dia: int = 4, extra_dup: bool = True) -> Path:
    """Livro do forward: 1 linha por evento, chave (dia, ts_open), com as colunas de RESULTADO
    que o diario nao pode ler."""
    linhas = []
    for d in range(dias):
        dia = (dt.date(2026, 8, 28) + dt.timedelta(days=d)).isoformat()
        for k in range(por_dia):
            linhas.append({"dia": dia, "ts_open": 1_000 + k, "bar_id": k, "lado_previsto": 1,
                           "conf": 0.7, "label": 1, "acerto": "SEGREDO",
                           "pnl_liquido_proxy": -99.0})
    if extra_dup:
        linhas.append(dict(linhas[0]))                        # re-escorado: nao duplica
    pasta = tmp_path / "data" / "research" / "fase2"
    pasta.mkdir(parents=True)
    pd.DataFrame(linhas).to_csv(pasta / "forward_eventos.csv", index=False)
    return tmp_path


def test_deepscalper_conta_eventos_do_livro_sem_ler_o_placar(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A ficha manda NAO olhar o placar antes de n = 150: o diario so' carrega dia/ts_open."""
    raiz = _livro(tmp_path)
    capturado: dict = {}
    original = pd.read_csv

    def espiao(*a: object, **k: object) -> pd.DataFrame:
        capturado.update(k)
        return original(*a, **k)
    monkeypatch.setattr(M.pd, "read_csv", espiao)
    ent = _entrada("deepscalper (Fase 2, offline)")
    p = M.progresso(ent, pd.DataFrame(), pd.DataFrame(), raiz)
    uc = capturado["usecols"]
    assert uc("dia") and uc("ts_open") and not uc("acerto") and not uc("pnl_liquido_proxy")
    assert p["n"] == 72 and p["pregoes"] == 18                    # 18 dias x 4 (duplicata fora)
    assert p["ritmo_obs"] == pytest.approx(4.0) and p["ritmo_ficha"] == 4.6
    assert [m["n"] for m in p["atingidas"]] == [50] and p["proximo"]["n"] == 150
    assert p["faltam"] == 78 and p["faltam_pregoes"] == 20        # 78 / 4,0 = 19,5 -> 20
    assert p["previsao"] > dt.date.fromisoformat(p["ultimo_dia"])
    assert not (set(p) & {"acerto", "pnl", "media", "slippage_medio", "drawdown"})
    assert "SEGREDO" not in repr(p)


def test_deepscalper_respeita_o_desde_e_nao_quebra_sem_o_livro(tmp_path: Path) -> None:
    ent = dict(_entrada("deepscalper (Fase 2, offline)"))
    raiz = _livro(tmp_path, dias=10, por_dia=2, extra_dup=False)
    ent["desde"] = "2026-09-02"                                    # 28/08 + 5 dias
    assert M.progresso(ent, pd.DataFrame(), pd.DataFrame(), raiz)["n"] == 2 * 5
    ausente = M.progresso(ent, pd.DataFrame(), pd.DataFrame(), tmp_path / "vazio")
    assert ausente["n"] == 0 and "livro nao encontrado" in ausente["fonte_problema"]
    assert ausente["proximo"]["n"] == 50 and ausente["previsao"] is None
    ruim = tmp_path / "ruim"
    (ruim / "data" / "research" / "fase2").mkdir(parents=True)
    (ruim / "data" / "research" / "fase2" / "forward_eventos.csv").write_text(
        "coluna_qualquer\n1\n", encoding="utf-8")
    assert "ilegivel" in M.progresso(ent, pd.DataFrame(), pd.DataFrame(), ruim)["fonte_problema"]


def test_toda_ficha_de_docs_eas_tem_destino_no_diario() -> None:
    """Guarda de omissao: o deepscalper ficou fora do diario da v4.15 a v4.19 por nao estar no
    metas.yaml. Agora toda ficha ou tem EA em `eas:` ou esta' em `fichas_sem_ea:` com o motivo."""
    metas = M.carregar_metas(RAIZ / "metas.yaml")
    sem_ea = M.carregar_fichas_sem_ea(RAIZ / "metas.yaml")
    com_ea = {m["ficha"] for m in metas}
    sem = {x["ficha"] for x in sem_ea}
    todas = set(M.todas_as_fichas(RAIZ))
    assert len(todas) >= 12
    orfas = todas - com_ea - sem
    assert not orfas, f"fichas sem destino no diario (metas.yaml): {sorted(orfas)}"
    assert not (com_ea & sem), f"ficha em `eas` E em `fichas_sem_ea`: {sorted(com_ea & sem)}"
    fantasmas = (com_ea | sem) - todas
    assert not fantasmas, f"metas.yaml cita ficha que nao existe: {sorted(fantasmas)}"
    assert all(x.get("motivo") for x in sem_ea)


def test_o_123_simulado_e_o_real_tem_entradas_separadas_no_registro() -> None:
    metas = {m["ea"]: m for m in M.carregar_metas(RAIZ / "metas.yaml")}
    assert "123 (E4)" in metas and "123 (dry_run)" in metas
    assert metas["123 (dry_run)"]["metas"] == []                    # a meta de slippage e' do E4
    assert metas["123 (E4)"]["metas"][0]["n"] == 50
    assert metas["z_agf_win"].get("captura")                         # nao finge que conta zero

