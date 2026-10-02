"""Diario operacional (v4.12). Os numeros da decomposicao sao os do episodio
real de 02/10 (ignicao: COMPRA @190455, stop 189920, saida simulada ~189807)
e foram conferidos a mao antes de virarem assert."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from typer.testing import CliRunner

from profittape import diario as D
from profittape import diario_html as H

NS = 1_000_000_000
TZ = ZoneInfo("America/Sao_Paulo")
DIA = dt.date(2026, 10, 2)


def _brt_ns(hh: int, mm: int, ss: float = 0.0, dia: dt.date = DIA) -> int:
    base = dt.datetime(dia.year, dia.month, dia.day, hh, mm, tzinfo=TZ)
    return int(base.timestamp()) * NS + int(ss * NS)


def _iso(t_ns: int) -> str:
    d = dt.datetime.fromtimestamp(t_ns // NS, tz=dt.UTC)
    return d.strftime("%Y-%m-%dT%H:%M:%S") + f".{(t_ns % NS) // 1000:06d}Z"


# ------------------------------------------------------------ decomposicao
def test_decomposicao_do_episodio_de_02_10_conferida_a_mao() -> None:
    """D=190450, fill 190455, stop 189920 (530), tape no gatilho 189915, fill de
    saida 189807, custo 4. ref=-535; ideal=-530; gap=+5; fill=108; entrada=5.
    -530 -5 -108 -5 -4 = -652 = pnl_liquido."""
    r = D.decompor(lado=1, d=190450, entrada=190455, saida=189807, saida_tape=189915,
                   motivo="stop", alvo_px=190980, stop_px=189920,
                   pnl_bruto=-648, pnl_liquido=-652)
    assert (r["ideal"], r["entrada_slip"], r["gap"], r["fill"], r["custo"]) == (
        -530, 5, 5, 108, 4)
    assert r["residuo"] == 0 and r["stop_pts"] == 530
    assert r["stop_real_sobre_programado"] == pytest.approx(648 / 530)


def test_decomposicao_vendido_no_alvo_e_saida_por_tempo() -> None:
    """Vendido: D=189950, fill 189945 (piora 5), alvo 189420 (530), tape no
    gatilho 189415 (5 ALEM do alvo, a favor), fill de saida 189420 (5 pior).
    ref=+535; ideal=+530; gap=-5 (melhor que a barreira); fill=+5; custo 4:
    530 +5 -5 -5 -4 = 521."""
    r = D.decompor(lado=-1, d=189950, entrada=189945, saida=189420, saida_tape=189415,
                   motivo="alvo", alvo_px=189420, stop_px=190480,
                   pnl_bruto=525, pnl_liquido=521)
    assert (r["ideal"], r["gap"], r["fill"], r["entrada_slip"]) == (530, -5, 5, 5)
    assert r["residuo"] == 0 and r["stop_real_sobre_programado"] is None
    # saida por tempo: ideal = o proprio movimento; gap 0
    t = D.decompor(lado=1, d=100, entrada=102, saida=140, saida_tape=140, motivo="tempo",
                   alvo_px=130, stop_px=70, pnl_bruto=38, pnl_liquido=27)
    assert t["ideal"] == 40 and t["gap"] == 0 and t["residuo"] == 0


# --------------------------------------------------------------------- log
def _linha(t_ns: int, event: str, level: str = "info", **kw: object) -> str:
    return json.dumps({"event": event, "level": level, "timestamp": _iso(t_ns), **kw})


def test_ler_log_usa_o_dia_de_brasilia(tmp_path: Path) -> None:
    f = tmp_path / "log.jsonl"
    f.write_text("\n".join([
        _linha(_brt_ns(23, 59, 59, DIA - dt.timedelta(days=1)), "a"),   # 02/10 02:59:59Z: dia 01
        _linha(_brt_ns(0, 0), "b"),                                     # 03:00Z: dia 02
        _linha(_brt_ns(23, 59, 59), "c"),
        _linha(_brt_ns(0, 0, 0, DIA + dt.timedelta(days=1)), "d"),      # dia 03
        "lixo que nao e' json",
        "{quebrado",
        json.dumps({"event": "sem_timestamp"}),
    ]), encoding="utf-8")
    ev, ruins = D.ler_log(f, DIA)
    assert [e["event"] for e in ev] == ["b", "c"] and ruins == 2


# ------------------------------------------------------------------- tape
def _tape_sintetico(curated: Path, estagnar: bool = True) -> None:
    """09:00-09:40 BRT, um negocio por segundo; atraso 0,05 s, exceto o stall:
    os eventos de 09:20:15 a 09:24:14 chegam todos entre 09:24:15 e 09:24:17,4."""
    ts = _brt_ns(9, 0) + np.arange(0, 2401) * NS
    recv = ts + int(0.05 * NS)
    if estagnar:
        ini, fim = _brt_ns(9, 20, 15), _brt_ns(9, 24, 15)
        m = (ts >= ini) & (ts < fim)
        recv[m] = fim + np.arange(int(m.sum())) * int(0.01 * NS)
    pasta = curated / "trade" / f"dt={DIA.isoformat()}" / "sym=WINFUT"
    pasta.mkdir(parents=True)
    pq.write_table(pa.table({"ts_ns": ts.astype("int64"), "ts_recv_ns": recv.astype("int64")}),
                   pasta / "parte-0.parquet")


def test_tape_incidente_buraco_e_atraso_na_hora(tmp_path: Path) -> None:
    _tape_sintetico(tmp_path)
    tape = D.carregar_tape(tmp_path, "WINFUT", DIA)
    assert tape is not None and tape.n == 2401
    inc = tape.incidentes()
    assert len(inc) == 1 and inc[0]["inicio"] == "09:20" and inc[0]["fim"] == "09:24"
    assert inc[0]["minutos"] == 5 and inc[0]["pico_s"] == pytest.approx(240.0)
    bur = tape.buracos(DIA)
    assert len(bur) == 1 and bur[0]["inicio"] == "09:20:14"
    assert bur[0]["duracao_s"] == pytest.approx(240.95, abs=0.01)
    # fora do stall: ~0,05 s; dentro do stall: nada chegou a +-1 s -> None (feed mudo);
    # na drenagem: atraso enorme
    assert tape.atraso_na_hora(_brt_ns(9, 10)) == pytest.approx(0.05, abs=1e-6)
    assert tape.atraso_na_hora(_brt_ns(9, 20, 30)) is None
    assert tape.atraso_na_hora(_brt_ns(9, 24, 16)) > 100
    assert D.carregar_tape(tmp_path, "WDOFUT", DIA) is None


# --------------------------------------------------------------- ponta a ponta
def _log_do_dia(f: Path) -> None:
    ev: list[str] = []
    t = _brt_ns(9, 0)
    for k in range(90):                                   # heartbeat a cada 30 s, com buraco
        if 40 <= k < 44:
            continue
        ev.append(_linha(t + k * 30 * NS, "recorder.heartbeat", linhas=1000 * k + (k > 50) * 9e5,
                         fila=5 if k < 10 else 200, fila_pico=300, descartados=0,
                         sem_evento_ha_s=0.4, uptime_min=k / 2))
    ev.append(_linha(_brt_ns(9, 20, 10.1), "ea.ign.entrada", nome="ea_ignicao", lado=1,
                     mov_pts=500, referencia=189950, preco_deteccao=190450, fill=190455,
                     fill_origem="tape", desliz=5, atraso_s=0.4, ancora=None,
                     alvo=190980, stop=189920))
    ev.append(_linha(_brt_ns(9, 20, 24.2), "ea.ign.saida", nome="ea_ignicao", lado=1,
                     motivo="stop", ancora=None, preco_deteccao=190450, entrada=190455,
                     saida=189807, saida_tape=189915, desliz_entrada=5, desliz_saida=108,
                     pnl_bruto=-648, pnl_liquido=-652, duracao_s=14.0, fill_origem="tape"))
    ev.append(_linha(_brt_ns(9, 5, 1), "ea.vwapvp.sinal", nome="ea_vwapvp", lado=1,
                     close=100900, vwap=100000, sd=400, z=2.25, dist=900,
                     alvo_px=101100, stop_px=100450, hhmm=905))
    ev.append(_linha(_brt_ns(9, 5, 2), "ea.vwapvp.entrada", nome="ea_vwapvp", lado=1,
                     preco=100905, preco_negocio=100905, alvo_px=101100, stop_px=100450))
    ev.append(_linha(_brt_ns(9, 12, 0), "ea.vwapvp.saida", nome="ea_vwapvp", lado=1,
                     entrada=100905, saida=100440, pnl_bruto=-465, pnl_liquido=-476,
                     duracao_s=418.0, motivo="stop", alvo_px=101100, stop_px=100450))
    ev.append(_linha(_brt_ns(9, 30), "ea.123.operacao_fechada", nome="ea_123_vb",
                     desfecho="alvo", pnl_pts=120.0, lado="compra",
                     ordens={"entrada": {"slippage_pts": 5.0, "latencia_fill_ms": 180.0},
                             "alvo": {"slippage_pts": 0.0, "latencia_fill_ms": 95.0}}))
    for k in range(3):
        ev.append(_linha(_brt_ns(9, 1, k), "ea.cancel_todas_recusado", level="error"))
    ev.append(_linha(_brt_ns(9, 2), "profitdll.estado", tipo=2, valor=6))
    f.write_text("\n".join(ev) + "\n", encoding="utf-8")


def test_montar_gravar_e_renderizar_ponta_a_ponta(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    _log_do_dia(log)
    _tape_sintetico(tmp_path / "curated")
    d = D.montar(DIA, log, tmp_path / "curated", "WINFUT", notas="- 09:21 grafico 15s ok")
    ops = {o["ea"]: o for o in d["operacoes"]}
    assert set(ops) == {"ea_ignicao", "ea_vwapvp", "ea_123_vb"}
    ig, vv, c123 = ops["ea_ignicao"], ops["ea_vwapvp"], ops["ea_123_vb"]
    assert ig["residuo"] == 0 and ig["gap"] == 5 and ig["fill"] == 108
    assert ig["atraso_saida_s"] is None            # 09:20:24 cai dentro do stall: feed mudo
    assert ig["atraso_entrada_s"] == pytest.approx(0.05, abs=1e-6)
    # vwap_vp: D = close do sinal (100900); stop 450; saida 100440 -> gap 10; entrada 5; custo 11
    assert (vv["stop_pts"], vv["gap"], vv["entrada_slip"], vv["custo"], vv["fill"]) == (
        450, 10, 5, 11, 0) and vv["residuo"] == 0
    assert c123["slippage_ordens_pts"] == 5.0 and c123["latencia_fill_max_ms"] == 180.0
    a = d["atribuicao"]
    assert a["operacoes_decompostas"] == 2 and a["stops"] == 2
    assert a["ops_com_atraso_na_saida"] == 1                     # so' a da ignicao (feed mudo)
    assert a["soma"]["pnl_liquido"] == pytest.approx(-652 - 476)
    assert d["saude"]["intervalos_acima_45s"] >= 1 and d["saude"]["descartados"] == 0
    assert d["ocorrencias"][0] == {"nivel": "error", "evento": "ea.cancel_todas_recusado",
                                   "n": 3, "primeiro": "09:01:00", "ultimo": "09:01:02"}
    assert d["estados_dll"] == [{"hora": "09:02:00", "tipo": 2, "valor": 6}]
    assert len(d["incidentes"]) == 1 and len(d["buracos"]) == 1

    pasta = tmp_path / "diario"
    for _ in range(2):                                            # idempotente por dia
        D.gravar_csv(d, pasta)
    assert len(pd.read_csv(pasta / "operacoes.csv")) == 3
    assert len(pd.read_csv(pasta / "incidentes.csv")) == 2        # 1 incidente + 1 buraco
    assert len(pd.read_csv(pasta / "dias.csv")) == 1

    html = H.renderizar(d)
    assert "Diário operacional" in html and "feed mudo" in html and "ea_ignicao" in html
    assert "1,22" in html and "09:21 grafico 15s ok" in html and "<svg" in html
    (pasta / f"diario_{DIA.isoformat()}.html").write_text(html, encoding="utf-8")
    assert f"diario_{DIA.isoformat()}.html" in H.renderizar_indice(pasta)


def test_sem_tape_avisa_e_nao_quebra(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    _log_do_dia(log)
    d = D.montar(DIA, log, tmp_path / "curated_inexistente")
    assert any("sem tape curado" in x for x in d["avisos"])
    assert d["tape"] is None and d["incidentes"] == [] and d["buracos"] == []
    assert all(o.get("atraso_saida_s") is None for o in d["operacoes"])
    html = H.renderizar(d)
    assert "sem tape curado" in html and "feed mudo" not in html


def test_formatacao_ptbr_e_escape() -> None:
    assert H._n(1234.5, 1) == "1.234,5"
    assert H._n(-652, 0, True) == '<span class="neg">-652</span>'
    assert H._n(None) == '<span class="mudo">—</span>'
    assert H._e("<script>") == "&lt;script&gt;"
    assert [H._lado(v) for v in (1, -1, "compra", "VENDA", None)] == [
        "compra", "venda", "compra", "venda", ""]


def test_notas_e_cli(tmp_path: Path) -> None:
    from profittape.cli import app

    log = tmp_path / "log.jsonl"
    _log_do_dia(log)
    _tape_sintetico(tmp_path / "curated")
    pasta = tmp_path / "diario"
    r = CliRunner().invoke(app, ["diario-operacional", "--dia", DIA.isoformat(), "--log", str(log),
                                 "--curated", str(tmp_path / "curated"), "--pasta", str(pasta),
                                 "--nota", "alarme falso: grafico de 15 s confirma"])
    assert r.exit_code == 0, r.output
    assert "3 operacao(oes)" in r.output and "1 incidente(s) de atraso" in r.output
    html = (pasta / f"diario_{DIA.isoformat()}.html").read_text(encoding="utf-8")
    assert "alarme falso: grafico de 15 s confirma" in html
    assert (pasta / "index.html").exists() and (pasta / "notas" / f"{DIA}.md").exists()
    r2 = CliRunner().invoke(app, ["diario-operacional", "--dia", DIA.isoformat(), "--log",
                                  str(tmp_path / "nao_existe.jsonl"), "--pasta", str(pasta)])
    assert r2.exit_code != 0
