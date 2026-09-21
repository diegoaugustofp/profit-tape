"""Diario de sinais: uma linha por SINAL, inclusive os descartados."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd
import pytest

from profittape.ea.ciclo_123 import CicloDeOrdens123
from profittape.ea.diario import DiarioDeSinais
from profittape.ea.semente import IndicadorMME
from profittape.ea.sinal_123 import SinalPreco123
from profittape.ea.vagas import VagasPorTicker
from profittape.research.diario_relatorio import relatorio
from tests.test_ea_ciclo_123 import P15, T0900, _b

NS = 1_000_000_000


def _ciclo(tmp_path: Path, **kw: object) -> tuple[CicloDeOrdens123, DiarioDeSinais]:
    d = DiarioDeSinais(tmp_path, "ea_t", {"codigo": "vX", "yaml_sha256": "abc"})
    c = CicloDeOrdens123(SinalPreco123(IndicadorMME(80, 139000.0)), diario=d,
                         infra_extra=lambda: {"corretora_pronta": True, "dia_completo": True},
                         **kw)  # type: ignore[arg-type]
    return c, d


def _armar(c: CicloDeOrdens123) -> None:
    c.on_barra(_b(0, 140000.0, 140100.0, 139900.0, 140050.0))
    c.on_barra(_b(1, 140050.0, 140080.0, 139800.0, 140000.0))
    c.on_barra(_b(2, 140000.0, 140050.0, 139900.0, 140020.0))


def _linhas(tmp_path: Path) -> list[dict]:
    arq = list(tmp_path.glob("diario_ea_t_*.jsonl"))
    assert len(arq) == 1
    return [json.loads(x) for x in arq[0].read_text(encoding="utf-8").splitlines()]


def test_operacao_executada_entra_no_diario(tmp_path: Path) -> None:
    c, d = _ciclo(tmp_path)
    _armar(c)
    t = T0900 + 3 * P15
    c.on_trade(t + NS, 140060.0)
    c.on_trade(t + 2 * NS, 140320.0)
    ln = _linhas(tmp_path)
    assert len(ln) == 1 and ln[0]["desfecho"] == "executou"
    assert ln[0]["desfecho_operacao"] == "alvo" and ln[0]["pnl_pts"] == 255.0
    assert ln[0]["ea"] == "ea_t" and ln[0]["carimbo"]["yaml_sha256"] == "abc"
    assert ln[0]["ordens"]["entrada"]["slippage_pts"] == 5.0
    assert d.resumo()["por_desfecho"] == {"executou": 1}


def test_descartes_por_vaga_posicao_e_pendente(tmp_path: Path) -> None:
    v = VagasPorTicker()
    assert v.tentar_ocupar("WINFUT", "outro")
    c, _d = _ciclo(tmp_path, vagas=v, symbol="WINFUT", nome="ea_t")
    _armar(c)                                   # sem vaga
    assert c.sinais_sem_vaga == 1
    v.liberar("WINFUT", "outro")
    c.on_barra(_b(3, 140020.0, 140060.0, 139700.0, 140000.0))
    c.on_barra(_b(4, 140000.0, 140050.0, 139900.0, 140030.0))
    c.on_barra(_b(5, 140030.0, 140050.0, 139950.0, 140040.0))   # arma
    assert c.estado == "entrada_pendente"
    c.on_barra(_b(6, 140040.0, 140070.0, 139800.0, 140000.0))
    c.on_barra(_b(7, 140000.0, 140050.0, 139900.0, 140030.0))
    c.on_barra(_b(8, 140030.0, 140060.0, 139950.0, 140040.0))   # pendente
    assert c.ignorados_pendente == 1
    ln = _linhas(tmp_path)
    desfechos = [x["desfecho"] for x in ln]
    assert "sem_vaga" in desfechos and "pendente" in desfechos
    sv = next(x for x in ln if x["desfecho"] == "sem_vaga")
    assert sv["motivo"]["dono_da_vaga"] == "outro"
    assert sv["infra"]["corretora_pronta"] is True
    assert sv["candidato"]["entrada"] == 140055.0 and sv["pnl_pts"] is None


def test_gate_separa_rejeitado_de_indefinido(tmp_path: Path) -> None:
    class GateFalso:
        def __init__(self, ultimo: dict) -> None:
            self.ultimo = ultimo

        def permite(self, c: object, b: object) -> bool:
            return False

    gate_ok = GateFalso({"vol_total": 100, "mediana": 50, "confiavel": True})
    c, _d = _ciclo(tmp_path, gate=gate_ok)
    _armar(c)
    c2, _ = _ciclo(tmp_path, gate=GateFalso({"vol_total": 100, "mediana": None,
                                             "confiavel": False}))
    _armar(c2)
    desfechos = [x["desfecho"] for x in _linhas(tmp_path)]
    assert desfechos == ["rejeitado_gate", "gate_indefinido"]


def test_relatorio_conta_custo_das_regras_e_curva(tmp_path: Path) -> None:
    v = VagasPorTicker()
    v.tentar_ocupar("WINFUT", "outro")
    c, _ = _ciclo(tmp_path, vagas=v, symbol="WINFUT", nome="ea_t")
    _armar(c)                                            # sem_vaga
    v.liberar("WINFUT", "outro")
    c.on_barra(_b(3, 140020.0, 140060.0, 139700.0, 140000.0))
    c.on_barra(_b(4, 140000.0, 140050.0, 139900.0, 140030.0))   # t: padrao 2-3-4
    c.on_trade(T0900 + 5 * P15 + NS, 140100.0)           # dentro de t+1: fill
    c.on_trade(T0900 + 5 * P15 + 2 * NS, 140500.0)       # alvo
    r = relatorio(tmp_path, "ea_t")
    assert r["sinais"] == 2
    assert r["custo_das_regras"]["descartados"] == 1
    assert r["custo_das_regras"]["por_regra"]["sem_vaga"] == 1
    cv = r["curva_e_drawdown_pts"]
    assert cv["operacoes"] == 1 and cv["pnl_total_pts"] > 0 and cv["drawdown_max_pts"] == 0.0
    assert r["execucao"]["entrada"]["n"] == 1
    assert r["infra"]["sinais_em_dia_incompleto"] == 0


def test_arquivo_pelo_dia_do_sinal_nao_pelo_relogio(tmp_path: Path) -> None:
    c, _ = _ciclo(tmp_path)
    _armar(c)
    c.on_trade(T0900 + 4 * P15, 140000.0)                # nao executou
    dia = pd.Timestamp(T0900, unit="ns", tz="UTC").tz_convert("America/Sao_Paulo").date()
    assert (tmp_path / f"diario_ea_t_{dia.isoformat()}.jsonl").exists()
    assert dia != dt.date.today()                        # o dia do sinal, nao hoje


def test_relatorio_sem_arquivo(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="nenhum"):
        relatorio(tmp_path, "nao_existe")


class _GateContador:
    """Gate que PASSA o 1o sinal (para o EA armar) e reprova os demais pelo
    volume. Conta chamadas para provar que a avaliacao dos bloqueados nao
    mexe nos contadores reais."""

    def __init__(self) -> None:
        self.permite_chamadas = 0
        self.avaliar_chamadas = 0
        self.registradas = 0
        self.ultimo: dict = {}

    def permite(self, c: object, b: object) -> bool:
        self.permite_chamadas += 1
        self.ultimo = {"vol_total": 10, "mediana": 50, "confiavel": True}
        return True

    def avaliar(self, c: object, b: object) -> tuple[bool, dict]:
        self.avaliar_chamadas += 1
        return False, {"vol_total": 900, "mediana": 50, "confiavel": True}

    def registrar_barra(self, b: object) -> None:
        self.registradas += 1


def test_sinal_bloqueado_por_posicao_passa_pelo_gate_sem_mexer_nos_contadores(
        tmp_path: Path) -> None:
    """2026-09-21: em 18/09, 5 de 7 sinais foram bloqueados por posicao
    aberta SEM o gate julga-los -- o custo do gate saia subestimado. E o
    registrar_barra nao era chamado nesses ramos."""
    gate = _GateContador()
    c, _d = _ciclo(tmp_path, gate=gate)
    _armar(c)                                         # 1o sinal: gate passa, arma
    assert c.estado == "entrada_pendente" and gate.permite_chamadas == 1
    registradas_antes = gate.registradas
    c.on_barra(_b(3, 140020.0, 140060.0, 139700.0, 140000.0))
    c.on_barra(_b(4, 140000.0, 140050.0, 139900.0, 140030.0))
    c.on_barra(_b(5, 140030.0, 140050.0, 139950.0, 140040.0))   # sinal com EA ocupado
    assert c.ignorados_pendente == 1
    assert gate.permite_chamadas == 1                 # contador REAL intocado
    assert gate.avaliar_chamadas == 1 and c.rejeitados_gate == 0
    assert gate.registradas == registradas_antes + 3  # toda barra alimenta o perfil
    bloqueado = next(x for x in _linhas(tmp_path) if x["desfecho"] == "pendente")
    assert bloqueado["motivo"]["gate_passaria"] is False
    assert bloqueado["motivo"]["gate"]["vol_total"] == 900


def test_relatorio_mostra_o_custo_do_gate_sobre_todos_os_sinais(tmp_path: Path) -> None:
    gate = _GateContador()
    c, _d = _ciclo(tmp_path, gate=gate)
    _armar(c)
    for k in range(3, 9, 3):                          # dois sinais com o EA ocupado
        c.on_barra(_b(k, 140020.0, 140060.0, 139700.0, 140000.0))
        c.on_barra(_b(k + 1, 140000.0, 140050.0, 139900.0, 140030.0))
        c.on_barra(_b(k + 2, 140030.0, 140050.0, 139950.0, 140040.0))
    r = relatorio(tmp_path, "ea_t")
    gt = r["custo_das_regras"]["gate_sobre_todos_os_sinais"]
    assert gt["bloqueados_que_o_gate_reprovaria"] == 2
    assert gt["bloqueados_sem_julgamento"] == 0
    assert gt["reprovados_de_fato"] == 0
    # o sinal que ARMOU ainda nao fechou a operacao, entao nao tem linha no
    # diario (so' entra ao fechar); a base sao os 2 bloqueados, e o gate
    # barraria os 2
    assert gt["fracao_que_o_gate_barra"] == 1.0
