"""
Logica do `ntsl/ignicao_forward.ntsl` portada para Python, linha a linha,
e conferida contra o EA (`replay_trades`) no mesmo tape sintetico.

O que isto prova: a MAQUINA DE ESTADOS em barras (referencia N barras
atras, refratario e tempo em barras, saida tempo->alvo->stop->18:00,
ignicao ignorada com posicao aberta) reproduz o EA quando a barra e' de
segundos -- e NAO reproduz com barra de 1 minuto (a licao do M1).
O que isto NAO prova: que o NTSL compila e roda igual. Isso so' o Profit
mostra; o log IGN|/SAI| do indicador existe para conferir.
Mudou o `.ntsl`? Mude `_ntsl` aqui junto (skill engenharia, 3.2).
"""

from __future__ import annotations

import numpy as np
import pytest

from profittape.ea.config_ignicao import EAIgnicaoConfig
from profittape.ea.service_ignicao import replay_trades
from profittape.ea.sinal_ignicao import ns_do_dia_brt
from tests.test_ea_ignicao import _tape_com_ignicoes

S = 1_000_000_000


def _barras(ts: np.ndarray, px: np.ndarray, seg: int) -> list[tuple[int, float, float, float]]:
    chave = ts // (seg * S)
    corte = np.flatnonzero(np.diff(chave)) + 1
    ini = np.concatenate([[0], corte])
    fim = np.concatenate([corte, [len(ts)]])
    return [(int(chave[a]) * seg * S, float(px[a:b].max()), float(px[a:b].min()),
             float(px[b - 1])) for a, b in zip(ini, fim, strict=True)]


def _hhmm(ts: int) -> int:
    s = ns_do_dia_brt(ts) // S
    return (s // 3600) * 100 + (s % 3600) // 60


def _ntsl(bs: list[tuple[int, float, float, float]], seg: int,
          cfg: EAIgnicaoConfig) -> tuple[list[tuple[int, int]], list[str]]:
    """Copia do bloco begin..end do .ntsl (mesmos nomes, mesma ordem)."""
    n_jan = 60 // seg
    pos_lado = pos_preco = pos_barras = refrat = ops = 0.0
    entradas: list[tuple[int, int]] = []
    saidas: list[str] = []
    for k, (t, hi, lo, cl) in enumerate(bs):
        hora = _hhmm(t)
        if pos_lado != 0:                                   # 1. saida
            pos_barras += 1
            alvo = pos_preco + pos_lado * cfg.alvo_pts
            stop = pos_preco - pos_lado * cfg.stop_pts
            motivo = ""
            if pos_barras * seg > cfg.tempo_max_s:
                motivo = "tempo"
            elif pos_lado > 0:
                if hi >= alvo and lo <= stop:
                    motivo = "ambiguo"
                elif hi >= alvo:
                    motivo = "alvo"
                elif lo <= stop:
                    motivo = "stop"
            else:
                if lo <= alvo and hi >= stop:
                    motivo = "ambiguo"
                elif lo <= alvo:
                    motivo = "alvo"
                elif hi >= stop:
                    motivo = "stop"
            if not motivo and hora >= cfg.zerar_ate_hhmm:
                motivo = "fim_do_dia"
            if motivo:
                saidas.append(motivo)
                pos_lado = 0
        if refrat > 0:                                      # 2. deteccao
            refrat -= 1
        lado = 0
        if k >= n_jan and 916 <= hora < cfg.fim_hhmm and refrat <= 0:
            ref = bs[k - n_jan][3]
            if hi - ref >= cfg.limiar_pts:
                lado = 1
            if ref - lo >= cfg.limiar_pts and (lado == 0 or cl < ref):
                lado = -1
        if lado:
            refrat = cfg.refratario_s / seg
            if pos_lado == 0 and ops < cfg.max_operacoes_dia:
                pos_lado, pos_preco, pos_barras = lado, ref + lado * cfg.limiar_pts, 0
                ops += 1
                entradas.append((t, lado))
    return entradas, saidas


def _comparar(seed: int, seg: int) -> tuple[int, int, int, int]:
    cfg = EAIgnicaoConfig(max_operacoes_dia=99, zerar_ate_hhmm=2359)
    ts, px = _tape_com_ignicoes(seed)
    ops = replay_trades(cfg, zip(ts.tolist(), px.tolist(), strict=True)).operacoes
    ent, sai = _ntsl(_barras(ts, px, seg), seg, cfg)
    casadas = sum(any(t <= o["ts_deteccao"] < t + seg * S and lado == o["lado"]
                      for t, lado in ent) for o in ops)
    # "encerramento" = fim do REPLAY com posicao aberta; o NTSL so' nao sai
    mot = sum(o["motivo"] == m for o, m in zip(ops, sai, strict=False))
    return len(ops), len(ent), casadas, mot


@pytest.mark.parametrize("seg", [1, 5])
@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5, 6])
def test_barra_de_segundos_reproduz_o_ea(seed: int, seg: int) -> None:
    n_ea, n_ntsl, casadas, mot = _comparar(seed, seg)
    assert n_ntsl == n_ea == casadas
    encerrou = 1 if seed == 5 else 0          # semente 5 termina posicionada
    assert mot == n_ea - encerrou


def test_barra_de_minuto_nao_reproduz() -> None:
    """Controle: o mesmo codigo em barra de 60 s PERDE a regra (27/52 no
    conjunto das 6 sementes). Se isto passar a casar tudo, o teste acima
    deixou de medir alguma coisa."""
    tot_ea = tot_casadas = 0
    for seed in range(1, 7):
        n_ea, _, casadas, _ = _comparar(seed, 60)
        tot_ea += n_ea
        tot_casadas += casadas
    assert tot_ea == 52
    assert tot_casadas < 0.7 * tot_ea
