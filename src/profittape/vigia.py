"""
Watchdog externo: roda a cada poucos minutos (schtasks proprio, NAO dentro do
record) e cobre o que os alertas internos do service.py NAO cobrem — o record
nunca ter iniciado. Um processo morto nao pode alertar sobre si mesmo; por
isso isto e' um segundo processo, independente, olhando de fora.

Le o log JSONL do dia (--log-file do record) e decide:
  1. Depois do horario esperado de abertura, existe pelo menos 1 linha
     'recorder.subscrito' de HOJE? Se nao -> record nunca iniciou.
  2. O ultimo 'recorder.heartbeat' esta ha' mais que --limite-parado min?
     Se sim, dentro da janela de pregao -> processo travou/morreu.
  3. Alguma linha recente de fila_critica / ARQUIVOS_NAO_CONFIAVEIS que o
     hook interno ja' teria tentado enviar? Reenviada aqui so' se o envio
     original falhou (rede caiu no momento) — deduplicada pelo estado.

Estado (logs/vigia_estado.json, gitignored) evita alertar a MESMA condicao
repetidas vezes a cada 5 min — cooldown por tipo de alerta.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import structlog

from .alertas import ConfigAlertas, enviar

log = structlog.get_logger(__name__)

_COOLDOWN_S = {
    "nao_iniciou": 30 * 60,      # a cada 30min enquanto nao iniciar
    "travado": 15 * 60,
    "fila_critica": 20 * 60,
    "nao_confiavel": 60 * 60,    # e' grave mas nao muda a cada 5min
}


def _carregar_estado(caminho: Path) -> dict[str, Any]:
    if caminho.exists():
        return cast(dict[str, Any], json.loads(caminho.read_text(encoding="utf-8")))
    return {}


def _salvar_estado(caminho: Path, estado: dict[str, Any]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(estado, indent=2), encoding="utf-8")


def _pode_alertar(estado: dict[str, Any], chave: str) -> bool:
    ultimo = estado.get(chave)
    if ultimo is None:
        return True
    return bool((time.time() - ultimo) >= _COOLDOWN_S.get(chave, 900))


def _ler_linhas_de_hoje(log_file: Path) -> list[dict[str, Any]]:
    """Linhas JSON do dia corrente. Arquivo ausente/vazio = lista vazia
    (nao e' erro — pode ser antes do primeiro heartbeat de hoje)."""
    if not log_file.exists():
        return []
    hoje = datetime.now().strftime("%Y-%m-%d")
    linhas = []
    with log_file.open(encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                d = json.loads(linha)
            except json.JSONDecodeError:
                continue
            ts = d.get("timestamp", "")
            if ts.startswith(hoje):
                linhas.append(d)
    return linhas


def checar(log_file: Path, alertas_cfg: Path, estado_arquivo: Path,
          abertura_local: str = "09:05", fechamento_local: str = "18:35",
          limite_parado_min: float = 6.0) -> str:
    """
    Devolve uma string de veredito ('ok' | a condicao alertada) para uso em
    teste e para o operador ver no terminal ao rodar manualmente.
    """
    cfg = ConfigAlertas.carregar(alertas_cfg)
    estado = _carregar_estado(estado_arquivo)
    agora = datetime.now()
    hhmm = agora.strftime("%H:%M")

    dentro_do_pregao = abertura_local <= hhmm <= fechamento_local
    if not dentro_do_pregao:
        return "fora_do_pregao"

    linhas = _ler_linhas_de_hoje(log_file)
    iniciou = any(d.get("event") == "recorder.subscrito" for d in linhas)

    if not iniciou:
        if _pode_alertar(estado, "nao_iniciou"):
            enviar(f"🔴 record NAO iniciou hoje (ja' sao {hhmm}). Verifique o "
                  f"schtasks e o notebook.", cfg)
            estado["nao_iniciou"] = time.time()
            _salvar_estado(estado_arquivo, estado)
        return "nao_iniciou"

    heartbeats = [d for d in linhas if d.get("event") == "recorder.heartbeat"]
    if heartbeats:
        ultimo = heartbeats[-1]
        ts_evento = datetime.fromisoformat(ultimo["timestamp"].replace("Z", "+00:00"))
        idade_min = (datetime.now(ts_evento.tzinfo) - ts_evento).total_seconds() / 60
        if idade_min > limite_parado_min:
            if _pode_alertar(estado, "travado"):
                enviar(f"🔴 record sem heartbeat ha' {idade_min:.0f} min "
                      f"(esperado a cada poucos min) — processo pode ter "
                      f"travado ou morrido.", cfg)
                estado["travado"] = time.time()
                _salvar_estado(estado_arquivo, estado)
            return "travado"

    fila_critica = [d for d in linhas if d.get("event") == "recorder.fila_critica"]
    if fila_critica and _pode_alertar(estado, "fila_critica"):
        enviar(f"🟠 fila critica detectada no log de hoje ({len(fila_critica)}x) "
              f"— confirme se o alerta em tempo real chegou.", cfg)
        estado["fila_critica"] = time.time()
        _salvar_estado(estado_arquivo, estado)

    nao_confiavel = [d for d in linhas
                     if d.get("event") == "recorder.ARQUIVOS_NAO_CONFIAVEIS"]
    if nao_confiavel and _pode_alertar(estado, "nao_confiavel"):
        enviar("🔴 arquivos NAO verificados detectados no log de hoje — "
              "confirme se o alerta em tempo real chegou.", cfg)
        estado["nao_confiavel"] = time.time()
        _salvar_estado(estado_arquivo, estado)

    return "ok"
