"""
Config do EA de IGNICAO (WIN) -- fast-track, 2026-09-25 (v3.68).

A regra e' a TESTADA em `research/ignicao.py` (v3.67), com os numeros
escolhidos pela regra CEGA do `--so-taxa` e o veredito favoravel na
amostra combinada (44 pregoes, p_alvo 0,702, IC 0,560-0,813). Ficha:
docs/eas/ignicao.md. Mudar qualquer numero = ficha nova, contagem nova.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import RiscoConfig


class EAIgnicaoConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: Literal["ignicao"] = "ignicao"
    nome: str | None = None
    symbol: str = "WINFUT"
    dry_run: bool = True

    # --- evento (research/ignicao.py) ------------------------------------
    limiar_pts: float = Field(500.0, gt=0)     # WIN anda isto...
    janela_s: float = Field(60.0, gt=0)        # ...contra o negocio de >= janela atras
    refratario_s: float = Field(1800.0, ge=0)  # nova ignicao so' depois disto
    inicio_hhmm: int = 915                     # 1a deteccao em inicio + janela
    fim_hhmm: int = 1700                       # ultima deteccao (exclusivo)

    # --- saida: barreira a partir do preco de DETECCAO --------------------
    alvo_pts: float = Field(530.0, gt=0)
    stop_pts: float = Field(530.0, gt=0)
    tempo_max_s: float = Field(3600.0, gt=0)   # sem barreira ate' aqui: sai a mercado
    zerar_ate_hhmm: int = 1800                 # zera o que estiver aberto

    # --- risco do dia ----------------------------------------------------
    max_operacoes_dia: int = Field(4, ge=1)
    tamanho_posicao: int = Field(1, ge=1)      # o estudo e' de 1 contrato
    # Informativo (supervisor): capital que sustenta o stop de fato usado.
    risco: RiscoConfig = RiscoConfig()

    # --- contabilidade (NAO altera sinal) --------------------------------
    # Taxas por ida e volta, 1 contrato (nota de 24/09: R$ 0,81 ~ 4 pts).
    # O spread NAO entra aqui: o fill simulado ja' paga o topo.
    custo_pontos_estimado: float = 4.0

    # --- so' REGISTRO: nao entra na decisao ------------------------------
    # Horarios de agenda (HHMM) e a janela depois deles, em minutos. 51%
    # das ignicoes do estudo cairam ai; 10:30 teve 10/11 alvos (n pequeno,
    # achado depois de olhar) -- o forward confirma ou desmente.
    ancoras_hhmm: list[int] = [930, 1000, 1030, 1500]
    ancora_janela_min: int = 5

    @model_validator(mode="after")
    def _coerente(self) -> EAIgnicaoConfig:
        for nome in ("inicio_hhmm", "fim_hhmm", "zerar_ate_hhmm"):
            v = getattr(self, nome)
            if not (0 <= v // 100 <= 23 and 0 <= v % 100 <= 59):
                raise ValueError(f"{nome}={v} nao e' HHMM valido")
        if self.fim_hhmm <= self.inicio_hhmm:
            raise ValueError("fim_hhmm precisa ser depois de inicio_hhmm")
        if self.zerar_ate_hhmm < self.fim_hhmm:
            raise ValueError("zerar_ate_hhmm antes de fim_hhmm: entraria sem poder ficar")
        return self

    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True, default=str)
                              .encode()).hexdigest()[:12]
