"""Log estruturado: legivel no console, JSON em arquivo."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import structlog


def configurar(nivel: str = "INFO", arquivo: Path | None = None) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=nivel)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty()),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, nivel.upper(), logging.INFO)
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    if arquivo is not None:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(arquivo, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        logging.getLogger().addHandler(handler)
