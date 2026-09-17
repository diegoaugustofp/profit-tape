"""
Registro do sinal do 123 (passo 6 do F5): cada operacao fechada vira uma
linha JSONL, carimbada, com o candidato, o fluxo da barra t e da barra do
GATILHO (t+1), as ordens (nivel, fill, slippage, latencias), o desfecho e
o P&L. E' o F1 da porta de volume: a amostra que nenhum teste tocou.

JSONL e nao parquet porque e' append de UMA linha por operacao, no meio
do pregao, sem reabrir arquivo grande. Um arquivo por dia:
`<dir>/sinais_123_<YYYY-MM-DD>.jsonl`. Quem analisar le com pandas
(`pd.read_json(lines=True)`).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)


class RegistroDeSinais123:
    def __init__(self, diretorio: Path, carimbo: dict[str, Any]) -> None:
        self.dir = diretorio
        self.carimbo = carimbo
        self.gravados = 0
        self.dir.mkdir(parents=True, exist_ok=True)

    def _arquivo(self, dia: dt.date | None = None) -> Path:
        # dia do SINAL, nao `today()` -- no replay e' o dia replicado, e um
        # processo que atravessa a meia-noite nao espalha o dia em dois.
        return self.dir / f"sinais_123_{(dia or dt.date.today()).isoformat()}.jsonl"

    @staticmethod
    def _dia_do_sinal(op: Any) -> dt.date | None:
        ts = getattr(op.candidato, "valido_ate_ns", 0) or 0
        if not ts:
            return None
        import datetime as _dt
        from zoneinfo import ZoneInfo
        return _dt.datetime.fromtimestamp(ts / 1e9, tz=ZoneInfo("America/Sao_Paulo")).date()

    def gravar(self, op: Any) -> None:
        linha = {"gravado_em": dt.datetime.now().isoformat(timespec="seconds"),
                 "carimbo": self.carimbo, **op.resumo()}
        arq = self._arquivo(self._dia_do_sinal(op))
        with arq.open("a", encoding="utf-8") as f:
            f.write(json.dumps(linha, default=str, ensure_ascii=False) + "\n")
        self.gravados += 1
        log.info("ea.123.sinal_gravado", arquivo=str(arq), total=self.gravados)
