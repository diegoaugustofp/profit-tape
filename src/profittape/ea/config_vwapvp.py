"""
Config do EA VWAP + VP, regra CONTINUACAO A TARDE (fast-track, 2026-10-01).

`tipo: "vwap_vp"` no YAML e' o que `carregar_config_ea` usa para escolher
este servico. `extra="forbid"`: campo desconhecido falha ALTO na carga.

A REGRA (a mesma de `REGRAS_CANDIDATAS["continuacao_tarde"]`, simulada em
46 dias: n=88, +47 pts/trade, IC95 [-23, +116], DD -3.647 — ver
docs/eas/vwap_vp.md):

    sinal   barra M5 fechada, abertura em [janela_inicio, janela_fim),
            |z_close| >= z_banda  com  z = (close - VWAP) / SD  (VWAP de
            sessao por NEGOCIO, desvio ponderado por volume, todos os
            negocios -- `ea/vwap_sessao.py`, batido no grafico)
    lado    a FAVOR do estirao: compra acima de +z, venda abaixo de -z
    alvo    entrada +- alvo_sd x SD(sinal)
    stop    entrada -+ stop_frac_dist x |close - VWAP|(sinal)
    tempo   tempo_max_s apos a entrada
    zera    tudo em zeragem_hhmm

O que NAO esta' aqui, de proposito: VP de ontem (a clausula de nivel nao
se combina com a banda -- 1 e 16 episodios em 46 dias), absorcao (nao
entrou na regra simulada), corte por hora dentro da tarde (olhar os 88
pela terceira vez seria o overfit que a disciplina nomeia). Essas
variantes sao avaliadas OFFLINE nos dados do forward, a partir do log de
sinais que o servico emite.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import RiscoConfig


class EAVwapVpConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: Literal["vwap_vp"]
    nome: str | None = None
    symbol: str = "WINFUT"
    tick: float = 5.0

    # --- barra e sinal ----------------------------------------------------
    periodo_barra_s: int = Field(300, ge=60)
    fim_sessao_hhmm: int = 1830
    z_banda: float = Field(2.0, gt=0)
    janela_inicio_hhmm: int = 1100          # abertura da barra de sinal (so' tarde)
    janela_fim_hhmm: int = 1700
    lado_permitido: Literal["ambos", "compra", "venda"] = "ambos"

    # --- saida ------------------------------------------------------------
    alvo_sd: float = Field(0.5, gt=0)
    stop_frac_dist: float = Field(0.5, gt=0)
    tempo_max_s: float = Field(3600.0, gt=0)
    zeragem_hhmm: int = 1800

    # --- cadencia e limites do dia ---------------------------------------
    cooldown_s: float = Field(1800.0, ge=0)   # desde o ULTIMO SINAL operado (= episodio)
    max_operacoes_dia: int = Field(6, ge=1)
    max_perdas_seguidas: int = Field(3, ge=1)
    perda_max_dia_pontos: float = Field(1200.0, gt=0)   # ~2 stops; pior dia da amostra -766

    tamanho_posicao: int = 1
    custo_pontos_estimado: float = 11.0
    dry_run: bool = True                   # NUNCA False sem decisao explicita
    usar_conta_real: bool = False          # ignorado pela esteira (sempre demo)
    risco: RiscoConfig = RiscoConfig()     # informativo (supervisor)

    @model_validator(mode="after")
    def _coerente(self) -> EAVwapVpConfig:
        if self.janela_fim_hhmm <= self.janela_inicio_hhmm:
            raise ValueError("janela_fim_hhmm precisa ser depois de janela_inicio_hhmm")
        if self.zeragem_hhmm < self.janela_fim_hhmm:
            raise ValueError("zeragem_hhmm nao pode ser antes de janela_fim_hhmm")
        if 3600 % self.periodo_barra_s != 0:
            raise ValueError("periodo_barra_s precisa dividir uma hora (barra_tempo)")
        return self

    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True, default=str)
                              .encode()).hexdigest()[:12]
