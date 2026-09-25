"""
Config do EA de MICROPRICE / QUEUE IMBALANCE (fast-track, 2026-09-24).

`tipo: "microprice"` no YAML e' o que `carregar_config_ea` usa para
escolher este servico. `extra="forbid"`, mesma razao do EAConfig: campo
desconhecido falha ALTO na carga, nunca e' ignorado em silencio.

POR QUE O LIMIAR E' DE IMBALANCE, NAO DE "X TICKS"
---------------------------------------------------
Com I = (Vb - Va)/(Vb + Va), a formula do microprice se reescreve como

    microprice = mid + I * spread / 2

Conferido a mao: bid 100000 x300, ask 100005 x100 ->
(100005*300 + 100000*100)/400 = 100003,75 = 100002,5 + 0,5*2,5.

Logo |microprice - mid| <= spread/2. No WIN o spread mediano e' 1 tick
(5 pts; p90 1,5 tick, medido no inventario DeepScalper), entao o
microprice NUNCA se afasta do mid mais que 2,5 pts, nem do ultimo
negocio mais que 1 tick. Um limiar "desvio > X ticks" com X >= 1 so'
dispararia com spread largo -- justamente o livro fino e instavel.
O limiar certo e' sobre I, que e' a mesma informacao sem esse teto.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import RiscoConfig


class EAMicropriceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: Literal["microprice"]
    nome: str | None = None
    symbol: str = "WINFUT"
    tick: float = 5.0                      # WIN: 5 pts

    # --- gatilho (sobre I em [-1, +1]) ---------------------------------
    limiar_entrada: float = Field(0.6, gt=0.0, lt=1.0)
    # Sai quando I*lado <= -limiar_saida. 0.0 = sai assim que o
    # desbalanco deixa de estar a favor (neutro ou contra).
    limiar_saida: float = Field(0.0, ge=0.0, lt=1.0)
    persistencia_ms: int = Field(300, ge=0)   # I tem que ficar do lado por X ms
    # Saida por desbalanco tambem exige persistencia (v3.64). 0 = sai na
    # primeira avaliacao invertida -- o comportamento do v3.63, que no
    # replay de 24/09 fechou 8 de 12 operacoes em 0,39 s medio: com I
    # avaliado a cada 50 ms, uma piscada fechava a posicao pagando spread.
    persistencia_saida_ms: int = Field(0, ge=0)
    lado_permitido: Literal["ambos", "compra", "venda"] = "ambos"

    # --- filtros de qualidade do topo ----------------------------------
    spread_max_ticks: int = Field(1, ge=1)
    qtd_min_topo: int = Field(20, ge=0)    # qtd_bid + qtd_ask minima
    livro_max_idade_ms: int = Field(5000, ge=1)

    # --- execucao da ENTRADA (v3.64) -----------------------------------
    # taker  : paga o lado oposto (nasce em -1 spread).
    # passiva: limitada no PROPRIO lado (compra no bid, venda no ask).
    #   Fill PESSIMISTA so' com o topo: compra em P executa quando o ask
    #   chega a P (vendedor agrediu) ou o bid cai abaixo de P (nivel
    #   consumido -- assume que estavamos no fim da fila). Nao cancela
    #   quando o I inverte, so' por validade: cancelar na inversao, no
    #   replay sem latencia, evitaria justamente os fills adversos.
    #   Saida continua taker. Nesta versao so' existe em dry_run/replay.
    entrada: Literal["taker", "passiva"] = "taker"
    passiva_validade_ms: int = Field(2000, ge=1)

    # --- saida -----------------------------------------------------------
    alvo_ticks: int = Field(3, ge=1)
    stop_ticks: int = Field(3, ge=1)
    tempo_max_s: float = Field(30.0, gt=0)

    # --- cadencia e limites do dia --------------------------------------
    avaliacao_ms: int = Field(50, ge=1)
    cooldown_s: float = Field(2.0, ge=0)
    janela_inicio_hhmm: int = 915
    janela_fim_hhmm: int = 1720            # depois disto: nao entra, e zera
    max_operacoes_dia: int = Field(200, ge=1)
    max_perdas_seguidas: int = Field(8, ge=1)
    perda_max_dia_pontos: float = Field(300.0, gt=0)

    # --- sonda: o sinal preve o mid? (independe de execucao) ------------
    sonda_horizontes_s: list[float] = [1.0, 5.0, 30.0]
    # Novo gatilho do MESMO lado dentro deste intervalo nao conta (v3.64):
    # I oscilando em torno do limiar gera varias bordas no mesmo episodio,
    # e contar todas superestima o n. 0 = conta toda borda (v3.63).
    sonda_refratario_s: float = Field(0.0, ge=0)

    tamanho_posicao: int = 1
    # Por operacao (ida e volta, 1 contrato), ALEM do spread. Default 11
    # e' a convencao antiga do projeto; a nota real do operador (25/09:
    # R$ 1,62 de taxas em 2 idas e voltas, IRRF de 1% excluido) da' ~4.
    custo_pontos_estimado: float = 11.0
    dry_run: bool = True                   # NUNCA False sem decisao explicita
    usar_conta_real: bool = False          # ignorado pela esteira (sempre demo)
    risco: RiscoConfig = RiscoConfig()     # informativo (supervisor)

    @model_validator(mode="after")
    def _coerente(self) -> EAMicropriceConfig:
        if self.janela_fim_hhmm <= self.janela_inicio_hhmm:
            raise ValueError("janela_fim_hhmm precisa ser depois de janela_inicio_hhmm")
        if not self.sonda_horizontes_s or any(h <= 0 for h in self.sonda_horizontes_s):
            raise ValueError("sonda_horizontes_s precisa de horizontes positivos")
        if self.entrada == "passiva" and not self.dry_run:
            raise ValueError("entrada: passiva so' existe em dry_run/replay nesta versao "
                             "(o executor da esteira envia ordem a mercado)")
        return self

    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True, default=str)
                              .encode()).hexdigest()[:12]
