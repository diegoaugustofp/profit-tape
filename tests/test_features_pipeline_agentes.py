"""--agentes fixos no pipeline de features (forward da Fase 2)."""

from __future__ import annotations

import inspect

from profittape.features import pipeline


def test_gerar_aceita_agentes_fixos() -> None:
    assert "agentes_fixos" in inspect.signature(pipeline.gerar).parameters
