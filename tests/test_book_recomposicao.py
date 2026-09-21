"""Recomposicao no livro v3: livro reconstruido POR POSICAO.

A v2 deu zero recargas em 8 dias: DELETE chega com offer_id, preco e
quantidade ZERADOS (so' side e position). A remocao na DLL e' posicional.
E o historico tem todo evento em PAR (V1 e V2 disparando juntos).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from profittape.research import book_recomposicao as br

NS = 1_000_000_000
ADD, EDIT, DELETE, DELETE_FROM = 0, 1, 2, 3


def _escrever(raiz: Path, dia: dt.date, df: pd.DataFrame, sym: str = "WINFUT") -> None:
    d = raiz / "book_offer" / f"dt={dia.isoformat()}" / f"sym={sym}"
    d.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), d / "part-0000.parquet")


def _ev(ts: int, acao: int, lado: int, pos: int, preco: float = 0.0, qtd: int = 0,
        agente: int = 0, oid: int = 0) -> dict:
    # DELETE/DELETE_FROM como no dado real: SEM offer_id, preco, quantidade.
    if acao in (DELETE, DELETE_FROM):
        preco, qtd, agente, oid = 0.0, 0, 0, 0
    return {"ts_recv_ns": ts, "action": acao, "side": lado, "position": pos,
            "offer_id": oid, "price": preco, "quantidade": qtd, "agente": agente}


def test_delete_resolve_a_oferta_pela_posicao() -> None:
    """A em 0; B entra em 0 e empurra A para 1; DELETE em 1 remove A."""
    df = pd.DataFrame([_ev(1, ADD, 0, 0, 140000.0, 10, 7, 1),
                       _ev(2, ADD, 0, 0, 140005.0, 20, 9, 2),
                       _ev(3, DELETE, 0, 1)])
    ev, cont = br.reconstruir(df, log_a_cada=0)
    saida = ev[~ev["entrada"]].iloc[0]
    assert (saida["price"], saida["quantidade"], saida["agente"]) == (140000.0, 10, 7)
    assert cont["saidas_atribuidas"] == 1 and cont["saidas_desconhecidas"] == 0


def test_delete_de_oferta_nunca_vista_conta_como_desconhecida() -> None:
    """O atFullBook e' descartado na origem: o livro inicial nao existe."""
    df = pd.DataFrame([_ev(1, ADD, 0, 3, 140000.0, 10, 7, 1),   # posicao 3: 0-2 desconhecidas
                       _ev(2, DELETE, 0, 0),                     # remove um desconhecido
                       _ev(3, DELETE, 0, 2)])                    # agora A esta' em 2
    ev, cont = br.reconstruir(df, log_a_cada=0)
    assert cont["saidas_desconhecidas"] == 1 and cont["saidas_atribuidas"] == 1
    assert ev[~ev["entrada"]].iloc[0]["agente"] == 7
    assert cont["fracao_saidas_desconhecidas"] == 0.5


def test_edit_troca_a_quantidade_na_posicao() -> None:
    df = pd.DataFrame([_ev(1, ADD, 1, 0, 140000.0, 10, 7, 1),
                       {**_ev(2, EDIT, 1, 0), "quantidade": 4},
                       _ev(3, DELETE, 1, 0)])
    ev, _ = br.reconstruir(df, log_a_cada=0)
    assert ev[~ev["entrada"]].iloc[0]["quantidade"] == 4


def test_delete_from_trunca_e_nao_vira_saida() -> None:
    df = pd.DataFrame([_ev(1, ADD, 0, 0, 1.0, 1, 1, 1), _ev(2, ADD, 0, 1, 2.0, 1, 1, 2),
                       _ev(3, ADD, 0, 2, 3.0, 1, 1, 3), _ev(4, DELETE_FROM, 0, 1)])
    _, cont = br.reconstruir(df, log_a_cada=0)
    assert cont["removidas_por_delete_from"] == 2 and cont["saidas_atribuidas"] == 0


def test_dia_dobrado_e_desfeito_e_dia_normal_nao_e_tocado() -> None:
    base = [_ev(1, ADD, 0, 0, 140000.0, 10, 7, 1), _ev(2, ADD, 0, 1, 140005.0, 5, 9, 2),
            _ev(3, DELETE, 0, 0)]
    dobrado = []
    for e in base:                                     # cada evento em PAR (V1+V2)
        dobrado += [e, {**e, "ts_recv_ns": e["ts_recv_ns"] + 1}]
    out, info = br.desdobrar(pd.DataFrame(dobrado))
    assert info["dia_dobrado"] is True and info["linhas_removidas"] == 3 and len(out) == 3
    # dia ja' capturado com a correcao: nada muda
    out2, info2 = br.desdobrar(pd.DataFrame(base))
    assert info2["dia_dobrado"] is False and len(out2) == 3


def test_sem_desdobrar_o_livro_fica_corrompido() -> None:
    """Prova de que o desdobramento e' NECESSARIO: com o par aplicado, o
    DELETE remove a COPIA e a oferta fantasma fica no livro, deslocando
    todas as posicoes seguintes."""
    base = [_ev(1, ADD, 0, 0, 140000.0, 10, 7, 1), _ev(2, DELETE, 0, 0),
            _ev(3, ADD, 0, 0, 140005.0, 20, 9, 2), _ev(4, DELETE, 0, 1)]
    dobrado = []
    for e in base:
        dobrado += [e, {**e, "ts_recv_ns": e["ts_recv_ns"] + 1}]
    ev_ok, _ = br.reconstruir(br.desdobrar(pd.DataFrame(dobrado))[0], log_a_cada=0)
    ev_ruim, _ = br.reconstruir(pd.DataFrame(dobrado), log_a_cada=0)
    ok = ev_ok[~ev_ok["entrada"]]["agente"].tolist()
    ruim = ev_ruim[~ev_ruim["entrada"]]["agente"].tolist()
    assert ok == [7]                     # o 2o DELETE aponta para posicao vazia
    assert ruim != ok                    # com o par, a atribuicao sai errada


def test_nivel_defendido_aparece_contra_o_baseline(tmp_path: Path) -> None:
    """Fluxo com ofertas variadas e CINCO niveis defendidos: o mesmo agente
    repoe o mesmo tamanho no mesmo preco, sempre na posicao 0."""
    dia = dt.date(2026, 9, 11)
    rng = np.random.default_rng(3)
    t0 = int(pd.Timestamp(f"{dia} 12:00:00", tz="UTC").value)
    linhas = []
    ts = t0
    for _ in range(20_000):                            # ruido: entra e sai na posicao 0
        ts += 10_000_000
        lado = int(rng.integers(0, 2))
        linhas.append(_ev(ts, ADD, lado, 0, 140000.0 + rng.integers(-40, 40) * 5.0,
                          int(rng.choice([1, 2, 5, 10])), int(rng.integers(1, 40))))
        ts += 5_000_000
        linhas.append(_ev(ts, DELETE, lado, 0))
    for k in range(5):                                 # 5 niveis defendidos
        nivel = 140000.0 + (k - 2) * 25.0
        ts += 60 * NS
        for _ in range(30):
            linhas.append(_ev(ts, ADD, 0, 0, nivel, 137, 7))
            ts += NS
            linhas.append(_ev(ts, DELETE, 0, 0))
            ts += NS
    _escrever(tmp_path, dia, pd.DataFrame(linhas))
    r = br.medir_dia(tmp_path, "WINFUT", dia)
    assert r["dia_dobrado"] is False
    assert r["cadeia_max"] >= 25
    assert r["por_limiar"]["20"] >= 5
    assert r["razao_por_limiar"]["20"] > 2.0, r["razao_por_limiar"]


def test_agregado_e_saida(tmp_path: Path) -> None:
    dia = dt.date(2026, 9, 14)
    linhas = [_ev(1, ADD, 0, 0, 140000.0, 50, 7), _ev(2, DELETE, 0, 0),
              _ev(3, ADD, 0, 0, 140000.0, 50, 7)]
    _escrever(tmp_path, dia, pd.DataFrame(linhas))
    r = br.descrever(tmp_path, "WINFUT", [dia], saida=tmp_path / "s")
    assert (tmp_path / "s" / "book_recomposicao.json").exists()
    a = r["agregado"]
    assert a["dias"] == 1 and "fracao_saidas_desconhecidas_p50" in a and "dias_dobrados" in a


def test_sem_book_recusa(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="nenhum dia"):
        br.descrever(tmp_path, "WINFUT", [dt.date(2026, 9, 10)])
