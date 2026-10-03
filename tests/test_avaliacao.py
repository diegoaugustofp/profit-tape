"""Avaliacao por EA (v4.18): drawdown, capital, carimbos, historico da ficha, pagina.
Numeros conferidos a mao antes de virarem assert."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from profittape.avaliacao import metricas as M
from profittape.avaliacao.fichas import carimbos, historico_da_ficha
from profittape.avaliacao.pagina_ea import gerar_paginas_ea, renderizar_pagina_ea, slug

RAIZ = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------ fronteira
def test_avaliacao_so_le_arquivos_e_nao_importa_ea_record_dll_pipeline_storage() -> None:
    """A avaliacao nao herda os defeitos do codigo que julga e pode sair do repositorio:
    so' pode importar a si mesma e o render/registro do diario."""
    permitido = ("profittape.avaliacao", "profittape.diario_html", "profittape.diario_metas")
    pasta = RAIZ / "src" / "profittape" / "avaliacao"
    arquivos = sorted(pasta.glob("*.py"))
    assert len(arquivos) >= 4
    for f in arquivos:
        arvore = ast.parse(f.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.ImportFrom):
                if no.level:                     # relativo: resolve contra profittape.avaliacao
                    base = ["profittape", "avaliacao"][: 2 - (no.level - 1)]
                    mod = ".".join(base + ([no.module] if no.module else []))
                else:
                    mod = no.module or ""
            elif isinstance(no, ast.Import):
                mod = no.names[0].name
            else:
                continue
            if mod.startswith("profittape"):
                assert mod.startswith(permitido), f"{f.name}: importa {mod}"


# ------------------------------------------------------------------- metricas
def test_drawdown_conferido_a_mao() -> None:
    """pnl [100,-50,-80,30,200,-300,40] -> acumulado 100,50,-30,0,200,-100,-60.
    Picos: 100 (vale -30, dd 130) e 200 (vale -100, dd 300). Maximo 300: pico apos a op 5
    (200), vale apos a op 6 (-100), 1 operacao do pico ao vale. Atual: 200 - (-60) = 260;
    nao recuperado."""
    dd = M.drawdown([100, -50, -80, 30, 200, -300, 40])
    assert dd["max_pts"] == 300 and dd["k_pico"] == 5 and dd["k_vale"] == 6
    assert dd["ops_pico_ao_vale"] == 1 and dd["atual_pts"] == 260
    assert dd["recuperado"] is False and dd["k_rec"] is None and dd["final_pts"] == -60
    # recuperado: depois do vale volta ao pico
    r = M.drawdown([100, -50, -80, 30, 200, -300, 40, 300])      # ...-60 + 300 = 240 >= 200
    assert r["recuperado"] and r["k_rec"] == 8 and r["atual_pts"] == 0
    # curva que so' perde: o pico e' o ponto inicial zero
    p = M.drawdown([-10, -20, -5])
    assert p["max_pts"] == 35 and p["k_pico"] == 0 and p["k_vale"] == 3
    # sem drawdown e sem operacoes
    assert M.drawdown([10, 20])["max_pts"] == 0 and M.drawdown([])["max_pts"] == 0


def test_resumo_payoff_e_fator_de_lucro() -> None:
    r = M.resumo(pd.DataFrame({"pnl_liquido": [300.0, -100.0, 500.0, -200.0, 0.0]}))
    assert (r["n"], r["ganhos"], r["perdas"]) == (5, 2, 2)
    assert r["pnl_pts"] == 500 and r["media_pts"] == 100 and r["pct_ganho"] == 40
    assert r["payoff"] == pytest.approx(400 / 150)           # ganho medio 400 / perda media 150
    assert r["fator_de_lucro"] == pytest.approx(800 / 300)
    assert M.resumo(pd.DataFrame({"pnl_liquido": [10.0, 20.0]}))["fator_de_lucro"] is None


def test_capital_tres_leituras_e_subestimativa_do_supervisor() -> None:
    """vwap_vp: pior stop 1.699 pts, drawdown 1.300 pts, pior perda 700; R$ 0,20/pt, 1
    contrato, 2%, margem R$ 100. Regra dos 2%: 1.699*0,20/0,02 = 16.990. Sobreviver: 100 +
    260 + 339,8 = 699,8 (pior = max(700, 1.699) = 1.699 pts = 339,8). Folga: 100 + 520 + 339,8."""
    c = M.capital(mdd_pts=1300, pior_perda_pts=700, pior_stop_pts=1699, valor_ponto=0.20,
                  contratos=1, risco_max_pct=0.02, margem_por_contrato=100,
                  recomendado_projeto=5000, capital_inicial=20000)
    assert c["regra_2pct"] == pytest.approx(16990.0)
    assert c["mdd_brl"] == pytest.approx(260.0) and c["pior_stop_brl"] == pytest.approx(339.8)
    assert c["sobreviver"] == pytest.approx(699.8) and c["com_folga"] == pytest.approx(959.8)
    assert c["projeto_subestima"] is True and c["margem_informada"] is True
    ok = M.capital(mdd_pts=0, pior_perda_pts=0, pior_stop_pts=530, valor_ponto=0.20, contratos=1,
                   risco_max_pct=0.02, margem_por_contrato=None, recomendado_projeto=5300,
                   capital_inicial=20000)
    assert ok["regra_2pct"] == pytest.approx(5300.0)           # bate com o log: 530 pts => 5.300
    assert ok["projeto_subestima"] is False and ok["margem_informada"] is False
    sem_stop = M.capital(mdd_pts=100, pior_perda_pts=50, pior_stop_pts=None, valor_ponto=0.20,
                         contratos=1, risco_max_pct=0.02, margem_por_contrato=None,
                         recomendado_projeto=None, capital_inicial=20000)
    assert sem_stop["regra_2pct"] is None and sem_stop["projeto_subestima"] is False


def test_curva_de_capital() -> None:
    c = M.curva_de_capital([100, -50], 20000, 0.20, 2)
    assert c.tolist() == [20000.0, 20040.0, 20020.0]            # 100*0,2*2 = 40; -50*0,2*2 = -20


# ------------------------------------------------------------------- carimbos
def _ops_com_carimbo() -> pd.DataFrame:
    return pd.DataFrame({
        "dia": ["2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02"],
        "hora_saida": ["10:00:00"] * 4, "pnl_liquido": [100.0, -50.0, 30.0, 70.0],
        "config_sha": ["aaa", "aaa", "bbb", "bbb"],
        "codigo": ["entregue-v4.01", "entregue-v4.01", "entregue-v4.01", "entregue-v4.09"]})


def test_carimbos_detectam_mudanca_de_config_sha_e_contagem_nova() -> None:
    c = carimbos(_ops_com_carimbo())
    assert c["mudou"] is True and c["desde_ultimo"] == "2026-10-01" and c["n_no_atual"] == 2
    # uma linha por PAR (sha, codigo): o sha bbb rodou sob duas tags de codigo
    assert [(x["config_sha"], x["codigo"], x["n"]) for x in c["linhas"]] == [
        ("aaa", "entregue-v4.01", 2), ("bbb", "entregue-v4.01", 1), ("bbb", "entregue-v4.09", 1)]
    # so' o codigo mudou (mesmo sha): nao e' contagem nova
    mesmo = _ops_com_carimbo().assign(config_sha="aaa")
    assert carimbos(mesmo)["mudou"] is False
    # CSV de antes da v4.18: sem colunas de carimbo
    antigo = _ops_com_carimbo().drop(columns=["config_sha", "codigo"])
    assert carimbos(antigo) == {"linhas": [], "mudou": False, "sem_carimbo": 4,
                                "desde_ultimo": None, "n_no_atual": None}


def test_historico_da_ficha_vem_do_git_e_nao_falha_sem_git(tmp_path: Path) -> None:
    def git(*a: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t",
                        *a], check=True, capture_output=True)
    git("init", "-q")
    f = tmp_path / "ignicao.md"
    f.write_text("v1", encoding="utf-8")
    git("add", "."), git("commit", "-q", "-m", "ficha criada (v3.68)")
    f.write_text("v2", encoding="utf-8")
    git("commit", "-qam", "forward ligado em 28/09")
    h = historico_da_ficha(tmp_path, "ignicao.md")
    assert [x["assunto"] for x in h] == ["forward ligado em 28/09", "ficha criada (v3.68)"]
    assert len(h[0]["data"]) == 10 and len(h[0]["hash"]) >= 7
    assert historico_da_ficha(tmp_path, "nao_existe.md") == []
    assert historico_da_ficha(tmp_path / "pasta_inexistente", "x.md") == []


# --------------------------------------------------------------------- pagina
def _csvs(pasta: Path) -> None:
    linhas = []

    def add(dia: str, hora: str, motivo: str, pnl: float, **kw: object) -> None:
        linhas.append({"dia": dia, "ea": "ea_vwapvp_continuacao", "descartado": False,
                       "hora_saida": hora, "motivo": motivo, "pnl_liquido": pnl,
                       "stop_pts": 1699.0, "config_sha": "a171e12aa9c0",
                       "codigo": "entregue-v4.01", **kw})
    add("2026-10-01", "12:01:26", "alvo", 319.0, ideal=328.0, entrada_slip=0.0, gap=-1.0,
        fill=0.0, custo=11.0, residuo=0.0)
    add("2026-10-02", "16:26:01", "alvo", 699.0, ideal=710.0, entrada_slip=0.0, gap=0.0, fill=0.0,
        custo=11.0, residuo=0.0)
    add("2026-10-02", "17:09:46", "stop", -1700.0, ideal=-1699.0, entrada_slip=0.0, gap=0.0,
        fill=0.0, custo=11.0, residuo=0.0)
    pd.DataFrame(linhas).to_csv(pasta / "operacoes.csv", index=False)
    pd.DataFrame({"dia": ["2026-10-01", "2026-10-02"]}).to_csv(pasta / "dias.csv", index=False)
    pd.DataFrame([{"dia": "2026-10-02", "ea": "ea_vwapvp_continuacao",
                   "capital_recomendado": 5000.0, "contratos": 1, "ticker": "WINFUT",
                   "capital_em_conta": 20000.0}]).to_csv(pasta / "eas_config.csv", index=False)


def test_pagina_do_ea_tem_resumo_drawdown_capital_evolucao_e_ficha(tmp_path: Path) -> None:
    from profittape.diario_metas import carregar_conta, carregar_metas

    _csvs(tmp_path)
    metas = carregar_metas(RAIZ / "docs/eas/metas.yaml")
    conta = carregar_conta(RAIZ / "docs/eas/metas.yaml")
    mapa = gerar_paginas_ea(tmp_path, metas, conta, RAIZ / "docs/eas")
    assert mapa == {"ea_vwapvp_continuacao": "ea_vwapvp_continuacao.html"}
    html = (tmp_path / mapa["ea_vwapvp_continuacao"]).read_text(encoding="utf-8")
    for trecho in ("Resumo dos resultados", "Drawdown máximo", "Capital necessário",
                   "Evolução do capital", "Evolução da ficha", "<svg", "href='index.html'"):
        assert trecho in html, trecho
    # P&L = 319 + 699 - 1700 = -682; drawdown: pico 1.018 -> vale -682 = 1.700; R$ 340,00
    assert "-682" in html and "R$ 340" in html and "1.700" in html
    assert "ainda não recuperado" in html
    # supervisor pede 5.000; pela regra dos 2% com o pior stop (1.699 pts) seriam 16.990
    assert "O supervisor subestima este EA" in html and "16.990" in html
    assert "Margem por contrato não informada" in html            # metas.yaml deixa null
    assert "O config_sha mudou" not in html and "Um único config_sha" in html
    assert "a171e12aa9c0" in html
    # a ficha do vwap_vp NAO proibe veredito parcial; a da ignicao proibe
    assert "A ficha proíbe olhar resultado" not in html


def test_pagina_da_ignicao_avisa_que_os_numeros_sao_descritivos(tmp_path: Path) -> None:
    from profittape.diario_metas import carregar_conta, carregar_metas

    ops = pd.DataFrame({"dia": ["2026-09-30", "2026-10-01"], "ea": "ea_ignicao",
                        "descartado": False, "hora_saida": "10:00:00", "motivo": ["alvo", "stop"],
                        "pnl_liquido": [821.0, -599.0], "stop_pts": 530.0})
    dias = pd.DataFrame({"dia": ["2026-09-30", "2026-10-01"]})
    metas = {m["ea"]: m for m in carregar_metas(RAIZ / "docs/eas/metas.yaml")}
    html = renderizar_pagina_ea("ea_ignicao", ops, ops, dias, metas["ea_ignicao"],
                                carregar_conta(RAIZ / "docs/eas/metas.yaml"), 5300.0,
                                RAIZ / "docs/eas")
    assert "A ficha proíbe olhar resultado antes da meta" in html and "descritivos" in html
    assert "n = 68" in html and "O supervisor subestima" not in html      # 5.300 = regra dos 2%
    assert "sem carimbo" in html or "operações sem carimbo" in html


def test_slug_e_ea_descartado_na_pagina(tmp_path: Path) -> None:
    assert slug("123 (E4)") == "123_e4" and slug("ea_ignicao") == "ea_ignicao"
    from profittape.avaliacao.pagina_ea import nome_arquivo
    assert nome_arquivo("123 (E4)") == "ea_123_e4.html"
    assert nome_arquivo("ea_ignicao") == "ea_ignicao.html"
    assert nome_arquivo("z_agf_win") == "ea_z_agf_win.html"
    ops = pd.DataFrame({"dia": ["2026-10-01"], "ea": "ea_microprice", "descartado": True,
                        "hora_saida": "09:15:09", "motivo": "alvo", "pnl_liquido": 11.0})
    html = renderizar_pagina_ea("ea_microprice", ops, ops, pd.DataFrame({"dia": ["2026-10-01"]}),
                                None, {"capital_inicial": 20000, "valor_ponto": 0.2,
                                       "risco_max_pct": 0.02, "margem_por_contrato": None,
                                       "contratos": 1}, None, None)
    assert "EA descartado (ficha)" in html and "sem ficha registrada" in html
    assert "Histórico da ficha indisponível" in html and np.isfinite(11.0)
