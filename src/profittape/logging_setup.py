"""
Log estruturado: legivel (colorido) no console, JSON de verdade em arquivo.

BUG REAL CORRIGIDO (2026-08-24): a versao anterior tinha UM processor final
(ConsoleRenderer) compartilhado entre console e arquivo via logging.
FileHandler — o --log-file recebia o MESMO texto formatado do console, nunca
JSON, apesar do nome '.jsonl' e do docstring prometerem JSON. Passou
despercebido porque nada no projeto ate' agora PARSEAVA o arquivo de volta —
so' apareceu ao escrever o watchdog (vigia.py), que le o log programaticamente
e falharia silenciosamente (json.loads levantando em toda linha, reportando
"record nunca iniciou" mesmo com tudo funcionando).

Correcao: dois logging.Handler no root logger, cada um com seu proprio
structlog.stdlib.ProcessorFormatter — console usa ConsoleRenderer (legivel,
colorido se for tty), arquivo usa JSONRenderer (uma linha JSON valida por
evento, parseavel por qualquer ferramenta, inclusive nosso proprio vigia).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import structlog

_PROCESSORS_COMUNS = [
    structlog.contextvars.merge_contextvars,
    structlog.processors.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
]


def configurar(nivel: str = "INFO", arquivo: Path | None = None) -> None:
    nivel_num = getattr(logging, nivel.upper(), logging.INFO)

    structlog.configure(
        processors=[
            *_PROCESSORS_COMUNS,
            # Guarda o event dict no LogRecord em vez de renderizar aqui —
            # cada Handler decide como renderizar (console x arquivo).
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(nivel_num),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    root = logging.getLogger()
    root.setLevel(nivel_num)
    root.handlers.clear()  # configurar() pode ser chamado 2x (CLI + testes)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(structlog.stdlib.ProcessorFormatter(
        processor=structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty()),
        foreign_pre_chain=_PROCESSORS_COMUNS,
    ))
    root.addHandler(console)

    if arquivo is not None:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(arquivo, encoding="utf-8")
        handler.setFormatter(structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=_PROCESSORS_COMUNS,
        ))
        root.addHandler(handler)

        # Anuncia o caminho ABSOLUTO resolvido, sempre — mesmo se `arquivo`
        # foi passado relativo. Incidente real (2026-08-25): --log-file
        # relativo, rodado de um diretorio de trabalho inesperado (schtasks,
        # ou um terminal aberto em outro lugar por engano), escreveu o log
        # num lugar que ninguem olhou depois. Mesmo padrao ja usado para
        # destinos de dado (curate.destino, backfill_dia.destino,
        # recorder.destino) — agora tambem para QUALQUER --log-file, de
        # qualquer comando, presente ou futuro, sem precisar caçar cada
        # default relativo um por um.
        structlog.get_logger("profittape.logging_setup").info(
            "log.destino", arquivo=str(arquivo.resolve())
        )
