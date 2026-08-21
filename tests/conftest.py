from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture
def tmp_raiz(tmp_path: Path) -> Path:
    d = tmp_path / "raw"
    d.mkdir()
    return d
