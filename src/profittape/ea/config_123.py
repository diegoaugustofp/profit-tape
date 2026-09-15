"""
Config do EA 123 (passo 7). `tipo: "123"` no YAML e' o que a esteira usa
para escolher este servico em vez do EAService de fluxo. `extra="forbid"`:
campo desconhecido e' recusado -- inclusive um `filtro_fluxo` com
conteudo antes de existir ficha para ele (EAS_DE_PRECO.md 6).

Os campos que o RegistroDeEAs le de qualquer EA (symbol, nome, dry_run,
tamanho_posicao, risco) tem os MESMOS nomes do EAConfig, de proposito.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from .config import RiscoConfig


class EA123Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: Literal["123"]
    nome: str | None = None
    symbol: str = "WINFUT"
    periodo_barra_s: int = 900
    fim_sessao_hhmm: int = 1830
    zeragem_hhmm: int = 1730
    slack_limite_pts: float = 50.0
    tamanho_posicao: int = 1
    custo_pontos_estimado: float = 11.0
    dry_run: bool = True                   # NUNCA False sem decisao explicita
    usar_conta_real: bool = False          # ignorado pela esteira (sempre demo)
    semente_parquet: str = "data/research/eas_preco/p123_2026/barras_123.parquet"
    curated: str = "data/curated"
    feriados: list[str] = []
    registro_dir: str | None = "data/forward/ea_123"
    filtro_fluxo: dict[str, Any] | None = None   # a PORTA. So' null tem ficha.
    risco: RiscoConfig = RiscoConfig()           # informativo (4.9)
    d_mediano_pts_informativo: float = 600.0     # da ficha 5.1, para o capital

    @classmethod
    def from_yaml(cls, caminho: Path) -> EA123Config:
        import yaml
        return cls(**yaml.safe_load(caminho.read_text(encoding="utf-8")))

    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True, default=str)
                              .encode()).hexdigest()[:12]

    def capital_recomendado_informativo(self) -> float:
        """D mediano x R$/pt / risco por operacao -- calculado e reportado,
        nunca usado para restringir (decisao 4.9)."""
        return round(self.d_mediano_pts_informativo * self.tamanho_posicao
                     * self.risco.valor_ponto_reais / self.risco.risco_max_pct, 0)


def carregar_config_ea(caminho: Path) -> Any:
    """`tipo: "123"` -> EA123Config; senao EAConfig (fluxo)."""
    import yaml

    from .config import EAConfig
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    if isinstance(dados, dict) and dados.get("tipo") == "123":
        return EA123Config(**dados)
    return EAConfig(**dados)
