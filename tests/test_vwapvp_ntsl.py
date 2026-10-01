"""Conferencia NTSL x Python do replay VWAP+VP (docs/eas/vwap_vp.md).

O que estes testes PROVAM: que o parser le o formato do Profit (pt-BR,
data 1AnoMesDia, hora de abertura), que a juncao casa barra a barra e que
o recalculo do Python e' consistente consigo mesmo (dump fabricado das
proprias series -> zero diferenca). O que NAO provam: que o `.ntsl`
calcula igual -- isso so' o dump real do grafico mede.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from typer.testing import CliRunner

from profittape.research.vwapvp_replay import ParametrosReplay
from profittape.tools import vwapvp_ntsl as vn
from profittape.tools.ntsl_equivalencia import _data_easylanguage
from tests.test_ea_vwap_vp_f2 import _curated_dois_dias


def _ptbr(x: float, casas: int = 8) -> str:
    """Numero como o Profit escreve: 157.722,86300000."""
    s = f"{x:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _dump_de(py, dias: list[dt.date]) -> str:
    linhas = []
    for _, r in py[py["chave_data"].isin(dias)].iterrows():
        campos = [str(vn.data_easylanguage(r["chave_data"])), f"{int(r['chave_hora']):04d}",
                  f"{int(r['chave_hora']):04d}"]
        for c in vn.CAMPOS[3:]:
            campos.append(_ptbr(float(r[c])))
        linhas.append("lixo do console " + vn.PREFIXO + "|".join(campos))
    return "\n".join(["linha sem prefixo", *linhas, "outra linha"])


def test_data_easylanguage_ida_e_volta() -> None:
    d = dt.date(2026, 9, 25)
    assert vn.data_easylanguage(d) == 1260925
    assert dt.date(*_data_easylanguage(1260925)) == d


def test_dump_fabricado_das_proprias_series_da_zero_diferenca(tmp_path: Path) -> None:
    cur = _curated_dois_dias(tmp_path)
    cache = tmp_path / "cache"
    dias = [dt.date(2026, 9, 25)]
    py = vn._series_python(cur, "WINFUT", dias, ParametrosReplay(), cache, aquecimento=1)
    dump = tmp_path / "console.txt"
    dump.write_text(_dump_de(py, dias), encoding="utf-8")

    r = vn.comparar(dump, cur, "WINFUT", cache_dir=cache, aquecimento_dias=1)
    assert "erro" not in r
    assert r["barras_casadas"] == int((py["chave_data"] == dias[0]).sum()) > 100
    assert r["meta"]["malformadas"] == 0 and r["meta"]["duplicadas"] == 0
    for c, d in r["exatas"].items():
        assert d["exatas_1e-6"] == d["n"], (c, d)
        assert d["max"] < 1e-6, c
    assert r["agressao"]["razao_compra_mediana"] == pytest.approx(1.0)
    assert not r["rolagem_detectada"] and r["dias_parciais_no_tape"] == {}
    # vwap por negocio x por barra: sao coisas diferentes, o gap tem que existir
    assert r["vwap_negocio_x_barra"]["max_pts"] > 0
    assert "barras_que_trocam_veredicto_z2" in r["vwap_negocio_x_barra"]
    # a barra que abre as 18:20 entra como 0 na absorcao (call de fechamento)
    ult = py[(py["chave_data"] == dias[0]) & (py["chave_hora"] >= 1820)]
    assert len(ult) == 1 and float(ult["absorcao_comp"].iloc[0]) == 0.0
    assert float(ult["absorcao_vend"].iloc[0]) == 0.0
    assert any("EXATAS" in x for x in vn.formatar(r))


def test_dump_parcial_e_dia_truncado_sao_reportados(tmp_path: Path) -> None:
    cur = _curated_dois_dias(tmp_path)
    cache = tmp_path / "cache"
    dias = [dt.date(2026, 9, 25)]
    py = vn._series_python(cur, "WINFUT", dias, ParametrosReplay(), cache, aquecimento=1)
    texto = _dump_de(py, dias)
    # o grafico tem 3 barras a mais que o tape (tape truncado): nao casam
    primeira = texto.splitlines()[1]              # a barra das 09:00
    assert "|0900|0900|" in primeira
    for h in ("1830", "1835", "1840"):
        texto += "\n" + primeira.replace("|0900|0900|", f"|{h}|{h}|", 1)
    dump = tmp_path / "console.txt"
    dump.write_text(texto, encoding="utf-8")
    r = vn.comparar(dump, cur, "WINFUT", cache_dir=cache, aquecimento_dias=1)
    assert r["dias_parciais_no_tape"] == {"2026-09-25": {"grafico": r["barras_casadas"] + 3,
                                                        "tape": r["barras_casadas"]}}
    assert any("ATENCAO" in x for x in vn.formatar(r))


def test_dump_recusa_agressao_zerada_e_formato_estranho(tmp_path: Path) -> None:
    ruim = tmp_path / "ruim.txt"
    ruim.write_text(vn.PREFIXO + "|".join(["1260925", "0900", "0900"] + ["0"] * 18) + "\n",
                    encoding="utf-8")
    with pytest.raises(SystemExit, match="zerados"):
        vn.carregar_dump(ruim)
    curto = tmp_path / "curto.txt"
    curto.write_text(vn.PREFIXO + "1260925|0900|0900|1|2\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="outra versao"):
        vn.carregar_dump(curto)


def test_gerar_ntsl_niveis_tem_um_if_por_dia_com_referencia(tmp_path: Path) -> None:
    cur = _curated_dois_dias(tmp_path)
    texto = vn.gerar_ntsl_niveis(cur, "WINFUT", cache_dir=tmp_path / "cache")
    assert texto.count("if sData = ") == 1                  # so' 25/09 tem referencia (24/09)
    assert "if sData = 1260925 then begin sVAH := " in texto
    assert "// ref 2026-09-24" in texto
    assert "sVAHant := sVAH[1];" in texto and "Plot3(sPOC)" in texto


def test_cli_ntsl_equivalencia_e_niveis(tmp_path: Path) -> None:
    from profittape.cli import app

    cur = _curated_dois_dias(tmp_path)
    dias = [dt.date(2026, 9, 25)]
    py = vn._series_python(cur, "WINFUT", dias, ParametrosReplay(), None, aquecimento=1)
    dump = tmp_path / "console.txt"
    dump.write_text(_dump_de(py, dias), encoding="utf-8")
    runner = CliRunner()
    r = runner.invoke(app, ["vwapvp-ntsl-equivalencia", "--log", str(dump), "--curated", str(cur),
                            "--saida", str(tmp_path / "casadas.csv")])
    assert r.exit_code == 0, r.output
    assert "EXATAS" in r.output and (tmp_path / "casadas.csv").exists()
    saida = tmp_path / "niveis.ntsl"
    r = runner.invoke(app, ["vwapvp-ntsl-niveis", "--curated", str(cur), "--saida", str(saida)])
    assert r.exit_code == 0, r.output
    assert saida.exists() and "1 dias com referencia" in r.output
