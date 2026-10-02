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
    pq.write_table(pa.table({"ts_ns": ts.astype("int64"), "ts_recv_ns": recv.astype("int64"),
                             "price": np.full(ts.size, 190440.0)}), pasta / "parte-0.parquet")


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
                     close=190900, vwap=190000, sd=400, z=2.25, dist=900,
                     alvo_px=191100, stop_px=190450, hhmm=905))
    ev.append(_linha(_brt_ns(9, 5, 2), "ea.vwapvp.entrada", nome="ea_vwapvp", lado=1,
                     preco=190905, preco_negocio=190905, alvo_px=191100, stop_px=190450))
    ev.append(_linha(_brt_ns(9, 12, 0), "ea.vwapvp.saida", nome="ea_vwapvp", lado=1,
                     entrada=190905, saida=190440, pnl_bruto=-465, pnl_liquido=-476,
                     duracao_s=418.0, motivo="stop", alvo_px=191100, stop_px=190450))
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
    # vwap_vp: D = close do sinal (190900); stop 450; saida 190440 -> gap 10; entrada 5; custo 11
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
    assert "zero por construção" in html                   # ignição simulada com fill do tape
    assert a["ops_com_fill_do_tape"] == 2 and a["custo_atraso_est"] == pytest.approx(0.0)
    assert vv["custo_atraso_saida_est"] == pytest.approx(0.0)
    assert ig["custo_atraso_saida_est"] is None
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


# --------------------------------------------------- v4.13: retroativo e custo do atraso
def _tape_com_atraso_uniforme() -> D.Tape:
    """Preco: 190000 ate' 09:20:00, cai 10 pts/s ate' 189700 (09:20:30) e fica.
    Entrega atrasada 30 s para os eventos de 09:20:00 a 09:25:00."""
    s0 = _brt_ns(9, 0)
    ts = s0 + np.arange(0, 2401) * NS
    seg = (ts - _brt_ns(9, 20)) // NS
    px = np.where(seg < 0, 190000.0, np.maximum(189700.0, 190000.0 - 10.0 * seg))
    recv = ts + int(0.05 * NS)
    atrasado = (ts >= _brt_ns(9, 20)) & (ts < _brt_ns(9, 25))
    recv[atrasado] = ts[atrasado] + 30 * NS
    return D.Tape(ts.astype("int64"), recv.astype("int64"), px)


def test_custo_contrafactual_do_atraso_conferido_a_mao() -> None:
    """Gatilho do stop no evento 09:20:10 (preco 189900); o EA o processa as 09:20:40
    (atraso 30 s) quando o mercado ja' esta' em 189700: um comprado perde 200 pts a mais.
    Vendido (espelho): precos subindo -> mesma conta com o sinal trocado."""
    tape = _tape_com_atraso_uniforme()
    assert tape.preco_em(_brt_ns(9, 20, 10)) == 189900.0
    assert tape.preco_em(_brt_ns(9, 20, 40)) == 189700.0
    assert tape.preco_em(_brt_ns(8, 0)) is None
    op = {"lado": 1, "motivo": "stop", "saida_tape": 189900.0, "t_saida": _brt_ns(9, 20, 40),
          "t_entrada": None, "atraso_saida_s": tape.atraso_na_hora(_brt_ns(9, 20, 40))}
    assert op["atraso_saida_s"] == pytest.approx(30.0)
    D.custo_atraso(tape, op)
    assert op["custo_atraso_saida_est"] == pytest.approx(200.0)
    # alvo = ordem limite no livro: atraso nao pesa
    alvo = dict(op, motivo="alvo")
    D.custo_atraso(tape, alvo)
    assert alvo["custo_atraso_saida_est"] is None
    # feed mudo (atraso None): nao inventa custo
    mudo = dict(op, atraso_saida_s=None)
    D.custo_atraso(tape, mudo)
    assert mudo["custo_atraso_saida_est"] is None
    # entrada: comprado que so' entra 30 s depois de o preco ter caido 300 -> mercado
    # andou a favor (preco menor): custo negativo (ganho) de 200 em relacao a 09:20:10
    ent = {"lado": 1, "motivo": "tempo", "saida_tape": None, "t_saida": _brt_ns(9, 30),
           "t_entrada": _brt_ns(9, 20, 40), "atraso_entrada_s": 30.0,
           "atraso_saida_s": None}
    D.custo_atraso(tape, ent)
    assert ent["custo_atraso_entrada_est"] == pytest.approx((189700.0 - 189900.0) * 1)


def test_ler_log_varios_uma_passada_igual_a_dia_a_dia(tmp_path: Path) -> None:
    f = tmp_path / "log.jsonl"
    d1, d2 = DIA, DIA + dt.timedelta(days=3)           # sexta e segunda
    f.write_text("\n".join([_linha(_brt_ns(10, 0, 0, d1), "a"), _linha(_brt_ns(10, 0, 0, d2), "b"),
                            _linha(_brt_ns(10, 5, 0, d2), "c"), "lixo"]), encoding="utf-8")
    por_dia, ruins = D.ler_log_varios(f, {d1, d2, d1 + dt.timedelta(days=1)})
    assert [e["event"] for e in por_dia[d1]] == ["a"]
    assert [e["event"] for e in por_dia[d2]] == ["b", "c"]
    assert por_dia[d1 + dt.timedelta(days=1)] == [] and ruins == 0
    assert [e["event"] for e in D.ler_log(f, d2)[0]] == ["b", "c"]


def test_tape_antigo_sem_coluna_de_preco_e_sem_recv(tmp_path: Path) -> None:
    pasta = tmp_path / "trade" / f"dt={DIA.isoformat()}" / "sym=WINFUT"
    pasta.mkdir(parents=True)
    ts = _brt_ns(9, 0) + np.arange(10) * NS
    pq.write_table(pa.table({"ts_ns": ts, "ts_recv_ns": ts + 1000}), pasta / "a.parquet")
    tape, motivo = D.ler_tape(tmp_path, "WINFUT", DIA)
    assert tape is not None and motivo is None and tape.preco_em(ts[3]) is None
    pq.write_table(pa.table({"ts_ns": ts}), pasta / "a.parquet")       # dia antigo, sem recv
    tape, motivo = D.ler_tape(tmp_path, "WINFUT", DIA)
    assert tape is None and "ilegivel" in str(motivo)


def test_retroativo_pula_fim_de_semana_e_dia_sem_dados(tmp_path: Path) -> None:
    from profittape.cli import app

    log = tmp_path / "log.jsonl"
    _log_do_dia(log)
    _tape_sintetico(tmp_path / "curated")
    pasta = tmp_path / "diario"
    r = CliRunner().invoke(app, ["diario-operacional", "--de", "2026-10-02", "--ate", "2026-10-05",
                                 "--log", str(log), "--curated", str(tmp_path / "curated"),
                                 "--pasta", str(pasta)])
    assert r.exit_code == 0, r.output
    assert "diario 2026-10-02: 3 operacao(oes)" in r.output
    assert "2026-10-05: sem dados" in r.output and "2026-10-03" not in r.output   # sabado fora
    assert "1 dia(s) gerado(s)" in r.output
    assert (pasta / "diario_2026-10-02.html").exists()
    assert not (pasta / "diario_2026-10-05.html").exists()
    r2 = CliRunner().invoke(app, ["diario-operacional", "--de", "2026-10-02", "--dia", "2026-10-02",
                                  "--log", str(log), "--pasta", str(pasta)])
    assert r2.exit_code != 0
    assert "feed mudo" in (pasta / "diario_2026-10-02.html").read_text(encoding="utf-8")



# ------------------------------- v4.14: o que os dados reais de 30/09 e 01/10 mostraram
def _escreve_tape(curated: Path, ts: np.ndarray, recv: np.ndarray, px: float = 190440.0) -> None:
    pasta = curated / "trade" / f"dt={DIA.isoformat()}" / "sym=WINFUT"
    pasta.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table({"ts_ns": ts.astype("int64"), "ts_recv_ns": recv.astype("int64"),
                             "price": np.full(ts.size, px)}), pasta / "a.parquet")


def test_regressao_30_09_relogio_local_atrasado_nao_derruba_o_html(tmp_path: Path) -> None:
    """30/09: mediana de ts_recv-ts = -1,02 s (relogio local atras da bolsa). A escala log do
    grafico recebia 1+v <= 0 e o HTML quebrava DEPOIS de o CSV ser gravado (dias.csv com o
    dia, sem pagina e sem indice). Agora: o desvio e' estimado, o atraso sai corrigido, e o
    grafico nunca recebe valor negativo."""
    ts = _brt_ns(9, 0) + np.arange(0, 2401) * NS
    _escreve_tape(tmp_path / "curated", ts, ts - int(1.02 * NS))
    log = tmp_path / "log.jsonl"
    _log_do_dia(log)
    d = D.montar(DIA, log, tmp_path / "curated")
    t = d["tape"]
    assert t["offset_relogio_s"] == pytest.approx(-1.02, abs=1e-6)
    assert t["atraso_p50"] == pytest.approx(0.0, abs=1e-6) and t["atraso_max"] < 0.01
    assert d["incidentes"] == []
    html = H.renderizar(d)                       # nao pode levantar ValueError: math domain error
    assert "Relógio local atrasado" in html and "<svg" in html
    assert all(o.get("atraso_saida_s") is None or o["atraso_saida_s"] >= -1e-6
               for o in d["operacoes"])


def test_offset_so_corrige_relogio_atrasado_e_nao_esconde_parada(tmp_path: Path) -> None:
    tape = _tape_com_atraso_uniforme()                 # piso 0,05 s positivo + 30 s de atraso
    assert tape.offset == 0.0 and tape.lag.max() == pytest.approx(30.0)
    ts = _brt_ns(9, 0) + np.arange(0, 600) * NS
    recv = ts - int(0.3 * NS)
    recv[300:] += 120 * NS                            # parada de 120 s depois do desvio
    t2 = D.Tape(ts.astype("int64"), recv.astype("int64"))
    assert t2.offset == pytest.approx(-0.3, abs=1e-6) and t2.lag.max() == pytest.approx(120.0)


def test_buraco_e_classificado_entrega_atrasada_ou_sem_negocios(tmp_path: Path) -> None:
    """Dois buracos de chegada de 100 s: (1) o mercado negociou e a entrega parou; (2) nao
    houve negocio nenhum na bolsa (leilao, como 30/09 09:30:05, 136 s)."""
    s0 = _brt_ns(9, 0)
    ts = np.concatenate([s0 + np.arange(0, 100) * NS,          # 09:00:00-09:01:39
                         s0 + np.arange(100, 200) * NS,        # (1) negociou 09:01:40-09:03:19
                         s0 + np.arange(400, 500) * NS])       # (2) volta 09:06:40
    recv = ts.copy()
    recv[100:200] = s0 + 200 * NS + np.arange(0, 100) * int(0.01 * NS)   # (1) chegam 09:03:20
    t = D.Tape(ts.astype("int64"), (recv + int(0.05 * NS)).astype("int64"))
    classes = {b["inicio"]: b["classe"] for b in t.buracos(DIA)}
    assert classes["09:01:39"] == "entrega atrasada"
    assert classes["09:03:21"] == "sem negocios (leilao/parada)"
    assert [b["negocios_no_intervalo"] for b in t.buracos(DIA)][1] == 0


def test_custo_contrafactual_nao_conta_duas_vezes_o_atraso_do_fill_do_livro() -> None:
    """Fill do LIVRO no instante do processamento: o atraso ja' esta' em `fill`/`entrada_slip`
    (medido). So' fill do tape recebe a estimativa contrafactual."""
    tape = _tape_com_atraso_uniforme()
    base = {"lado": 1, "motivo": "stop", "saida_tape": 189900.0, "t_saida": _brt_ns(9, 20, 40),
            "t_entrada": None, "atraso_saida_s": 30.0}
    livro = dict(base, fill_origem="livro")
    D.custo_atraso(tape, livro)
    assert livro["custo_atraso_saida_est"] is None and livro["custo_atraso_entrada_est"] is None
    d_tape = dict(base, fill_origem="tape")
    D.custo_atraso(tape, d_tape)
    assert d_tape["custo_atraso_saida_est"] == pytest.approx(200.0)


def test_nao_executou_e_descartados_ficam_fora_dos_totais(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    _log_do_dia(log)
    extra = [
        _linha(_brt_ns(10, 44, 59), "ea.123.operacao_fechada", nome="123", desfecho="nao_executou",
               pnl_pts=None, ordens={}),
        _linha(_brt_ns(9, 15, 9), "ea.micro.saida", nome="ea_microprice", lado=1, motivo="alvo",
               entrada=190000.0, saida=190020.0, pnl_bruto=20.0, pnl_liquido=11.0, duracao_s=3.1),
        _linha(_brt_ns(9, 15, 26), "ea.micro.saida", nome="ea_microprice_passiva", lado=1,
               motivo="stop", pnl_bruto=-8.0, pnl_liquido=-19.0),
    ]
    with log.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(extra) + "\n")
    d = D.montar(DIA, log, tmp_path / "sem_tape")
    assert {o["ea"] for o in d["operacoes"]} == {"ea_ignicao", "ea_vwapvp", "ea_123_vb"}
    assert {o["ea"] for o in d["ops_descartadas"]} == {"ea_microprice", "ea_microprice_passiva"}
    assert [x["ea"] for x in d["nao_executadas"]] == ["123"]
    html = H.renderizar(d)
    assert "EAs descartados ainda em execução" in html and "ea_microprice: 1 ops, +11 pts" in html
    assert "Sinais sem execução" in html
    pasta = tmp_path / "diario"
    D.gravar_csv(d, pasta)
    ops = pd.read_csv(pasta / "operacoes.csv")
    assert len(ops) == 5 and int(ops["descartado"].sum()) == 2          # 3 ativas + 2 descartadas
    dia = pd.read_csv(pasta / "dias.csv").iloc[0]
    assert dia["operacoes"] == 3 and dia["n_descartados"] == 2 and dia["sinais_sem_execucao"] == 1
    assert dia["pnl_descartados"] == pytest.approx(11 - 19)
    # opcao do operador: descartar so' um
    d2 = D.montar(DIA, log, tmp_path / "sem_tape", descartados=("ea_microprice",))
    assert {o["ea"] for o in d2["ops_descartadas"]} == {"ea_microprice"}


def test_cli_uma_falha_nao_derruba_o_intervalo_e_nao_deixa_csv_pela_metade(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from profittape import diario_html
    from profittape.cli import app

    log = tmp_path / "log.jsonl"
    _log_do_dia(log)
    _tape_sintetico(tmp_path / "curated")

    def quebra(dados: dict) -> str:                 # simula o crash de 30/09 na renderizacao
        raise ValueError("math domain error")
    monkeypatch.setattr(diario_html, "renderizar", quebra)
    pasta = tmp_path / "diario"
    r = CliRunner().invoke(app, ["diario-operacional", "--de", "2026-10-02", "--ate", "2026-10-05",
                                 "--log", str(log), "--curated", str(tmp_path / "curated"),
                                 "--pasta", str(pasta)])
    assert r.exit_code == 1
    assert "2026-10-02: FALHOU (ValueError: math domain error)" in r.output
    assert "2026-10-05: sem dados" in r.output and "1 dia(s) FALHARAM" in r.output
    # nada pela metade: sem CSV do dia que falhou e sem pagina
    assert not (pasta / "operacoes.csv").exists() and not (pasta / "dias.csv").exists()
    assert not (pasta / "diario_2026-10-02.html").exists()
    # um dia so': a excecao aparece inteira (traceback), nao e' engolida
    r1 = CliRunner().invoke(app, ["diario-operacional", "--dia", "2026-10-02", "--log", str(log),
                                  "--curated", str(tmp_path / "curated"), "--pasta", str(pasta)])
    assert r1.exit_code != 0 and isinstance(r1.exception, ValueError)
