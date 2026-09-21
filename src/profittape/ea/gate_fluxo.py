"""
A PORTA DE VOLUME do EA de preco (passo 5 do F5, EAS_DE_PRECO.md 5.4 e 6).

Interface, nao conteudo. `GateDeFluxo.permite(candidato, barra_t)` fica
entre "o sinal de preco armou" e "manda a ordem". `SemFiltro` e' o
default e o unico conteudo hoje: deixa passar tudo.

Por que e' um GATE e nao um termo do sinal: o sinal de preco continua
identico ao que os 10 anos testaram; o gate so' escolhe quais dos
mesmos candidatos viram ordem. Quando uma feature de fluxo passar pela
disciplina (ficha propria, amostra que os testes nao tocaram -- a que o
passo 6 grava), ela vira uma implementacao daqui e um bloco preenchido
em `filtro_fluxo:` no YAML. Carimbo novo, contagem nova.
"""

from __future__ import annotations

from typing import Any, Protocol

from .sinal import BarraFechada
from .sinal_123 import Candidato123


class GateDeFluxo(Protocol):
    def permite(self, candidato: Candidato123, barra_t: BarraFechada) -> bool: ...


class SemFiltro:
    """Default. Nenhum conteudo."""

    def permite(self, candidato: Candidato123, barra_t: BarraFechada) -> bool:
        return True

    def avaliar(self, candidato: Candidato123,
                barra_t: BarraFechada) -> tuple[bool, dict[str, Any]]:
        return True, {}


class GateVolumeBaixo:
    """
    Ficha 12 (EAS_DE_PRECO.md): passa o candidato cuja barra t fechou com
    vol_total ABAIXO da mediana do horario nos 20 pregoes anteriores.
    Gate INDEFINIDO (barra nao confiavel, ou sem 20 pregoes de perfil no
    horario) = nao passa, contado separado em `indefinidos`. Depois de
    decidir, a barra t entra no perfil (vale amanha).
    """

    def __init__(self, perfil: Any, hoje: Any) -> None:
        self.perfil = perfil
        self.hoje = hoje                  # callable -> date do pregao corrente
        self.indefinidos = 0
        self.avaliados = 0
        self.ultimo: dict[str, Any] = {}

    def avaliar(self, candidato: Candidato123,
                barra_t: BarraFechada) -> tuple[bool, dict[str, Any]]:
        """A decisao SEM efeito colateral (nao mexe em contador nem em
        `ultimo`). Usada para os sinais que chegam com posicao aberta: o
        gate e' avaliado e REGISTRADO no diario, sem inflar os contadores do
        EA -- antes, esses sinais nem passavam pelo gate e o custo do gate
        saia subestimado no relatorio (2026-09-21)."""
        import datetime as dt
        from zoneinfo import ZoneInfo
        t = dt.datetime.fromtimestamp(barra_t.ts_open_ns / 1e9, tz=ZoneInfo("America/Sao_Paulo"))
        dia, hhmm = t.date(), t.hour * 100 + t.minute
        med = self.perfil.mediana(hhmm, dia)
        visto = {"hhmm": hhmm, "vol_total": barra_t.vol_total, "mediana": med,
                 "confiavel": barra_t.volume_confiavel}
        if not barra_t.volume_confiavel or med is None:
            return False, visto
        return bool(barra_t.vol_total < med), visto

    def permite(self, candidato: Candidato123, barra_t: BarraFechada) -> bool:
        passou, visto = self.avaliar(candidato, barra_t)
        self.avaliados += 1
        self.ultimo = visto
        if not visto["confiavel"] or visto["mediana"] is None:
            self.indefinidos += 1
        return passou

    def registrar_barra(self, barra: BarraFechada) -> None:
        """Toda barra fechada (com ou sem candidato) alimenta o perfil."""
        import datetime as dt
        from zoneinfo import ZoneInfo
        t = dt.datetime.fromtimestamp(barra.ts_open_ns / 1e9, tz=ZoneInfo("America/Sao_Paulo"))
        self.perfil.registrar(t.date(), t.hour * 100 + t.minute, float(barra.vol_total),
                              barra.volume_confiavel)


def construir_gate(cfg: dict[str, Any] | None, perfil: Any = None, hoje: Any = None) -> GateDeFluxo:
    """`filtro_fluxo: null` -> SemFiltro. `{tipo: volume_baixo}` (ficha 12,
    2026-09-15) -> GateVolumeBaixo com o perfil dado. Qualquer outra coisa e'
    recusada ate' existir ficha (extra=forbid na config)."""
    if cfg is None:
        return SemFiltro()
    if cfg.get("tipo") == "volume_baixo":
        if perfil is None:
            raise ValueError("filtro_fluxo volume_baixo exige um PerfilVolumeHorario")
        return GateVolumeBaixo(perfil, hoje)
    raise ValueError(f"filtro_fluxo={cfg!r}: nenhum gate com esse tipo tem ficha congelada; "
                     "aceitos: null, {tipo: volume_baixo} (EAS_DE_PRECO.md 6 e 12)")
