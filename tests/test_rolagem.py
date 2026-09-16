"""Rolagem: calendario, distancia em pregoes e a descricao (zero trial)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from profittape.research.rolagem import (
    datas_de_vencimento,
    descrever,
    marcar_distancia,
    quarta_mais_proxima_do_15,
)
from tests.test_eas_preco import _dia, _dump


def test_quarta_mais_proxima_do_15() -> None:
    # 2026-02-15 e' um domingo -> a quarta mais proxima e' 18/02 (3 dias)
    # contra 11/02 (4 dias)
    assert quarta_mais_proxima_do_15(2026, 2) == dt.date(2026, 2, 18)
    # 2026-04-15 e' quarta: e' ela mesma
    assert quarta_mais_proxima_do_15(2026, 4) == dt.date(2026, 4, 15)
    # 2026-06-15 e' segunda -> quarta 17/06 (2 dias) contra 10/06 (5)
    assert quarta_mais_proxima_do_15(2026, 6) == dt.date(2026, 6, 17)
    for ano in (2015, 2020, 2026):
        for mes in (2, 4, 6, 8, 10, 12):
            d = quarta_mais_proxima_do_15(ano, mes)
            assert d.weekday() == 2 and abs((d - dt.date(ano, mes, 15)).days) <= 3


def test_datas_de_vencimento_so_meses_pares_na_janela() -> None:
    v = datas_de_vencimento(dt.date(2026, 1, 1), dt.date(2026, 12, 31))
    assert len(v) == 6 and all(d.month % 2 == 0 for d in v)
    assert v == sorted(v)


def test_distancia_em_pregoes_e_feriado_no_vencimento() -> None:
    # pregoes de 5 dias uteis; vencimento no 3o
    dias = [dt.date(2026, 4, 13) + dt.timedelta(days=k) for k in range(5)]
    m = marcar_distancia(dias, [dt.date(2026, 4, 15)])
    assert dict(zip(m["dia"], m["d"], strict=True))[dt.date(2026, 4, 15)] == 0
    assert dict(zip(m["dia"], m["d"], strict=True))[dt.date(2026, 4, 14)] == -1
    assert dict(zip(m["dia"], m["d"], strict=True))[dt.date(2026, 4, 17)] == 2
    # vencimento caindo em dia sem pregao -> usa o proximo pregao
    sem_15 = [d for d in dias if d != dt.date(2026, 4, 15)]
    m2 = marcar_distancia(sem_15, [dt.date(2026, 4, 15)])
    assert dict(zip(m2["dia"], m2["d"], strict=True))[dt.date(2026, 4, 16)] == 0


def test_descricao_acusa_volume_maior_perto_do_vencimento(tmp_path: Path) -> None:
    """Dias de abril de 2026; o vencimento e' 15/04 (quarta). Volume 3x nos
    tres pregoes anteriores -- a descricao tem que mostrar isso."""
    barras, cb = [], 1
    for dia in range(1, 29):
        d = dt.date(2026, 4, dia)
        if d.weekday() >= 5:
            continue
        data = 1260400 + dia
        bloco = _dia(data, cb)
        perto = dt.date(2026, 4, 13) <= d <= dt.date(2026, 4, 15)
        for b in bloco:
            b["vol_total"] = 3000 if perto else 1000
        cb += 37
        barras += bloco
    r = descrever(_dump(tmp_path, barras), tmp_path / "s")
    assert (tmp_path / "s" / "rolagem.json").exists()
    assert "2026-04-15" in r["vencimentos"]
    assert r["por_d"]["0"]["vol_vs_normal"] == 3.0
    assert r["por_d"]["-1"]["vol_vs_normal"] == 3.0
    assert r["por_d"]["-5"]["vol_vs_normal"] == 1.0          # fora da concentracao
    # a descricao NAO reporta retorno com sinal (so' magnitude)
    assert all("retorno_p50" not in e for e in r["por_d"].values() if e)
    assert "perfil_horario_fracao_do_volume" in r
