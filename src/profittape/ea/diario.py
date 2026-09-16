"""
DIARIO DE SINAIS (2026-09-16, decisao do operador).

Uma linha JSONL por SINAL, nao por operacao. Todo candidato armado entra,
inclusive o que NAO virou ordem -- e' essa metade que nao existe em lugar
nenhum fora do EA (o Profit registra o que EXECUTOU, nao o que foi
DECIDIDO) e e' ela que responde:

  - quanto o modo exclusivo custou (`sem_vaga`);
  - quanto o gate custou (`rejeitado_gate`, `gate_indefinido`);
  - quantos sinais a regra de uma posicao por vez descartou
    (`posicao_aberta`, `pendente`);
  - o que teria sido o resultado dos descartados -- REPORTADO, nunca
    usado para decidir (seria escolher a regra depois de ver).

DESFECHOS (campo `desfecho`):
    executou          virou ordem e a operacao fechou (traz ordens, P&L)
    nao_executou      stop de entrada cancelada no fim de t+1
    rejeitado_gate    o gate de fluxo reprovou (traz a mediana e o volume)
    gate_indefinido   barra nao confiavel ou sem 20 pregoes de perfil
    sem_vaga          modo exclusivo: outro EA estava posicionado
    posicao_aberta    ja' havia posicao deste EA
    pendente          ja' havia ordem de entrada viva deste EA
    erro / zeragem / reconciliado  (desfechos da propria operacao)

FORMATO: um arquivo por dia, `<dir>/diario_<ea>_<AAAA-MM-DD>.jsonl`,
append de uma linha por sinal, com carimbo (tag + sha256 do yaml). O
arquivo de OPERACOES (`sinais_123_*.jsonl`) continua existindo e e' um
subconjunto: quem quer so' o que executou usa ele; quem quer o custo das
regras usa o diario.

O nome do dia vem do ts do SINAL (nao de `date.today()`): um processo que
atravessa a meia-noite, ou um replay, escreve no arquivo do dia certo.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import structlog

log = structlog.get_logger(__name__)
_TZ = ZoneInfo("America/Sao_Paulo")
_NS = 1_000_000_000

DESFECHOS_DESCARTE = frozenset({
    "rejeitado_gate", "gate_indefinido", "sem_vaga", "posicao_aberta", "pendente",
})


class DiarioDeSinais:
    def __init__(self, diretorio: Path, ea: str, carimbo: dict[str, Any]) -> None:
        self.dir = diretorio
        self.ea = ea
        self.carimbo = carimbo
        self.gravados = 0
        self.por_desfecho: dict[str, int] = {}
        self.dir.mkdir(parents=True, exist_ok=True)

    def _arquivo(self, dia: dt.date) -> Path:
        return self.dir / f"diario_{self.ea}_{dia.isoformat()}.jsonl"

    @staticmethod
    def _dia_do_sinal(candidato: Any) -> dt.date:
        ts = getattr(candidato, "valido_ate_ns", 0) or 0
        if ts:
            return dt.datetime.fromtimestamp(ts / _NS, tz=_TZ).date()
        return dt.datetime.now(_TZ).date()

    def _escrever(self, dia: dt.date, linha: dict[str, Any]) -> None:
        with self._arquivo(dia).open("a", encoding="utf-8") as f:
            f.write(json.dumps(linha, default=str, ensure_ascii=False) + "\n")
        self.gravados += 1
        d = str(linha.get("desfecho"))
        self.por_desfecho[d] = self.por_desfecho.get(d, 0) + 1

    def descartado(self, candidato: Any, desfecho: str, motivo: dict[str, Any] | None = None,
                   infra: dict[str, Any] | None = None) -> None:
        """Sinal que NAO virou ordem. `motivo` carrega o que a regra viu
        (volume e mediana do gate, dono da vaga, estado do ciclo)."""
        dia = self._dia_do_sinal(candidato)
        self._escrever(dia, {
            "gravado_em": dt.datetime.now(_TZ).isoformat(timespec="seconds"),
            "ea": self.ea, "carimbo": self.carimbo, "desfecho": desfecho,
            "candidato": candidato.resumo(), "motivo": motivo or {}, "infra": infra or {},
            "ordens": {}, "pnl_pts": None,
        })
        log.info("ea.diario.descartado", ea=self.ea, desfecho=desfecho,
                 **candidato.resumo())

    def operacao(self, op: Any) -> None:
        """Sinal que virou ordem: a operacao fechada inteira."""
        dia = self._dia_do_sinal(op.candidato)
        resumo = op.resumo()
        desfecho = "executou" if op.entrada.fill is not None else str(resumo.get("desfecho"))
        self._escrever(dia, {
            "gravado_em": dt.datetime.now(_TZ).isoformat(timespec="seconds"),
            "ea": self.ea, "carimbo": self.carimbo, "desfecho": desfecho,
            "desfecho_operacao": resumo.get("desfecho"), "motivo": {},
            **{k: v for k, v in resumo.items() if k != "desfecho"},
        })

    def resumo(self) -> dict[str, Any]:
        descartados = sum(n for d, n in self.por_desfecho.items() if d in DESFECHOS_DESCARTE)
        return {"gravados": self.gravados, "descartados": descartados,
                "por_desfecho": dict(sorted(self.por_desfecho.items()))}
