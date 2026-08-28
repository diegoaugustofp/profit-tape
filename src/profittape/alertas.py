"""
Alertas via Telegram — visibilidade remota do record sem precisar abrir o
notebook. Token/chat_id vivem em config/alertas.yaml (gitignored, como o
recorder.yaml — NUNCA versionar).

Design: falha ao enviar alerta NAO pode derrubar o record (rede caiu, bot
mal configurado etc). Toda chamada e' best-effort: loga o erro e segue.
Alertar e' cortesia, gravar o pregao e' o trabalho.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

_API = "https://api.telegram.org/bot{token}/sendMessage"


class ConfigAlertas:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id

    @classmethod
    def carregar(cls, caminho: Path) -> ConfigAlertas | None:
        """None se o arquivo nao existir ou estiver incompleto — alertas
        ficam DESLIGADOS por padrao, nunca travam um record sem config."""
        if not caminho.exists():
            return None
        import yaml  # mesmo parser que RecorderConfig ja usa
        dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
        token = dados.get("telegram", {}).get("bot_token")
        chat_id = dados.get("telegram", {}).get("chat_id")
        if not token or not chat_id:
            return None
        return cls(bot_token=str(token), chat_id=str(chat_id))


def enviar(mensagem: str, cfg: ConfigAlertas | None, timeout_s: float = 10.0) -> bool:
    """
    Best-effort: devolve False e LOGA em vez de levantar. Alerta que falha
    silenciosamente e' aceitavel (o operador so' perde uma notificacao); um
    alerta que derruba o record por causa de uma API externa fora do ar
    seria trocar um problema pequeno por um grande.
    """
    if cfg is None:
        return False
    url = _API.format(token=cfg.bot_token)
    payload = json.dumps({"chat_id": cfg.chat_id, "text": mensagem}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            ok = bool(resp.status == 200)
            if not ok:
                log.warning("alertas.envio_falhou", status=resp.status)
            return ok
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        log.warning("alertas.envio_falhou", erro=str(exc))
        return False
