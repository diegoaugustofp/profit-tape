"""
Alertas via Telegram — visibilidade remota do record sem precisar abrir o
notebook. Token/chat_id vivem em config/alertas.yaml (gitignored, como o
recorder.yaml — NUNCA versionar).

Design: falha ao enviar alerta NAO pode derrubar o record (rede caiu, bot
mal configurado etc). Toda chamada e' best-effort: loga o erro e segue.
Alertar e' cortesia, gravar o pregao e' o trabalho.
"""

from __future__ import annotations

import contextlib
import json
import queue
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
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


# ----------------------------------------------------------------------
# Avisos do EA (armou / encerrou) -- v4.04
# ----------------------------------------------------------------------
# POR QUE ASSINCRONO: `enviar()` e' HTTP sincrono com timeout de 10 s. Os
# avisos do record (iniciou/caiu/encerrou) rodam na thread principal, onde
# 10 s parados nao custam nada. Os do EA nasceriam na thread do EABridge,
# que consome o tape: Telegram lento seguraria o EA ate' 10 s por aviso --
# a fila do bridge encheria e DESCARTARIA trades, e a gestao do stop/alvo
# do 123 ficaria cega nesse intervalo. Trocar decisao de trade por
# notificacao e' o problema pequeno virando grande (docstring do topo).
#
# Por isso: fila limitada + uma thread so' para enviar. `avisar_ea` nunca
# bloqueia e nunca levanta; fila cheia descarta e conta.
#
# POR QUE GLOBAL: os cinco EAs (fluxo, 123, microprice, ignicao, vwap_vp)
# sao construidos pelo RegistroDeEAs e tambem pelo replay/CLI. Ligado so'
# pelo record (`ligar_avisos_ea`), o replay e os testes ficam em silencio
# sem precisar passar nada por cinco construtores.


class NotificadorAssincrono:
    def __init__(self, cfg: ConfigAlertas, maxsize: int = 100,
                 envio: Callable[[str, ConfigAlertas | None], bool] | None = None) -> None:
        self.cfg = cfg
        self._envio = envio or enviar
        self._fila: queue.Queue[str | None] = queue.Queue(maxsize=maxsize)
        self.enfileirados = 0
        self.descartados = 0
        self.enviados = 0
        self.falhas = 0
        self._thread = threading.Thread(target=self._laco, name="alertas-ea", daemon=True)
        self._thread.start()

    def avisar(self, texto: str) -> None:
        try:
            self._fila.put_nowait(texto)
            self.enfileirados += 1
        except queue.Full:
            self.descartados += 1
            log.warning("alertas.ea_fila_cheia", descartados=self.descartados)

    def _laco(self) -> None:
        while True:
            texto = self._fila.get()
            if texto is None:
                return
            try:
                ok = self._envio(texto, self.cfg)
            except Exception:
                ok = False
                log.exception("alertas.ea_envio_excecao")
            if ok:
                self.enviados += 1
            else:
                self.falhas += 1

    def parar(self, timeout_s: float = 15.0) -> None:
        """Drena o que ja' esta' na fila (os avisos de zeragem do fim do dia
        saem antes do 'record encerrado') com teto de tempo: Telegram fora
        do ar nao segura o encerramento do record."""
        with contextlib.suppress(queue.Full):
            self._fila.put(None, timeout=timeout_s)
        self._thread.join(timeout=timeout_s)
        log.info("alertas.ea_resumo", enfileirados=self.enfileirados,
                 enviados=self.enviados, falhas=self.falhas,
                 descartados=self.descartados, drenou=not self._thread.is_alive())


_notificador_ea: NotificadorAssincrono | None = None


def ligar_avisos_ea(cfg: ConfigAlertas | None) -> None:
    """Chamado pelo record. Sem config, fica desligado (no-op)."""
    global _notificador_ea
    desligar_avisos_ea()
    if cfg is not None:
        _notificador_ea = NotificadorAssincrono(cfg)


def desligar_avisos_ea(timeout_s: float = 15.0) -> None:
    global _notificador_ea
    n, _notificador_ea = _notificador_ea, None
    if n is not None:
        n.parar(timeout_s=timeout_s)


def avisar_ea(texto: str) -> None:
    """HOT PATH do EA: nao bloqueia, nao levanta."""
    n = _notificador_ea
    if n is None:
        return
    try:
        n.avisar(texto)
    except Exception:
        log.exception("alertas.ea_avisar_falhou")


def _lado_txt(lado: object) -> str:
    if lado in ("compra", "venda"):
        return str(lado).upper()
    try:
        return "COMPRA" if float(lado) > 0 else "VENDA"  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(lado)


def _modo(dry_run: bool) -> str:
    return "[SIMULADO]" if dry_run else "[REAL]"


def _px(v: object) -> str:
    return "-" if v is None else f"{float(v):.0f}"  # type: ignore[arg-type]


def ea_armou(nome: str, lado: object, preco: float | None, *, dry_run: bool,
             alvo: float | None = None, stop: float | None = None,
             detalhe: str = "") -> None:
    """Sinal armado: ordem de entrada enviada (123: stop pendente; demais:
    entrada a mercado). Formata aqui para os cinco EAs falarem igual."""
    try:
        txt = (f"🎯 {_modo(dry_run)} {nome} armou {_lado_txt(lado)} @ {_px(preco)}"
               f" | alvo {_px(alvo)} | stop {_px(stop)}")
        if detalhe:
            txt += f" | {detalhe}"
        avisar_ea(txt)
    except Exception:
        log.exception("alertas.ea_formatar_falhou", nome=nome)


def ea_encerrou(nome: str, motivo: str, pnl_pts: object, *, dry_run: bool,
                pnl_dia: float | None = None) -> None:
    """Operacao/sinal encerrado: saida (alvo, stop, tempo, zeragem) ou
    entrada que nao executou. `pnl_pts` None = sem fill (nada a apurar)."""
    try:
        pnl = None if pnl_pts is None else float(pnl_pts)  # type: ignore[arg-type]
        if pnl is None:
            icone, res = "⚪", "sem P&L"
        else:
            icone = "🟢" if pnl > 0 else ("🔴" if pnl < 0 else "⚪")
            res = f"{pnl:+.1f} pts"
        txt = f"{icone} {_modo(dry_run)} {nome} encerrou ({motivo}) {res}"
        if pnl_dia is not None:
            txt += f" | dia {pnl_dia:+.1f} pts"
        avisar_ea(txt)
    except Exception:
        log.exception("alertas.ea_formatar_falhou", nome=nome)
