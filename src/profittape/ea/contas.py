"""
Utilitario de diagnostico: conecta com login COMPLETO (DLLInitializeLogin)
e lista as contas de roteamento (GetAccount -> AccountCallback).

READ-ONLY por natureza: GetAccount so' consulta, nunca envia ordem nem
modifica nada. O objetivo unico e' descobrir os pwcIDAccount de demo e
real para preencher ROTEAMENTO_ID_ACCOUNT_DEMO/REAL no .env
(RoteamentoConfig, ver config.py).

QUANDO RODAR: de preferencia FORA do horario de pregao, com o record
PARADO. Este e' o primeiro teste do "Caminho recomendado" em
docs/EA_ARQUITETURA.md -- confirma que o login completo funciona sozinho,
ANTES de qualquer teste de concorrencia com a captura ao vivo (essa
pergunta continua em aberto, nao e' resolvida por esta ferramenta).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import structlog

from ..config import Credenciais
from ..profitdll.bindings import (
    TAccountCallback,
    THistoryCallback,
    THistoryTradeCallback,
    TNewDailyCallback,
    TNewTradeCallback,
    TOfferBookCallbackV1,
    TOrderChangeCallback,
    TPriceBookCallbackV1,
    TProgressCallback,
    TStateCallback,
    TTinyBookCallback,
    load_dll,
)

log = structlog.get_logger(__name__)


@dataclass
class ContaEncontrada:
    corretora_id: int
    corretora_nome: str
    account_id: str
    titular: str


@dataclass
class _Coletor:
    """Guarda o resultado dos callbacks. Precisa sobreviver ate' o fim da
    funcao (ctypes nao segura referencia sozinho — ver aviso em bindings.py)."""
    contas: list[ContaEncontrada] = field(default_factory=list)
    conectado: bool = False
    erro_estado: str | None = None


def listar_contas(cred: Credenciais, timeout_s: float = 15.0,
                  dll_injetada: object | None = None) -> list[ContaEncontrada]:
    """
    Conecta, chama GetAccount(), espera ate' timeout_s por respostas do
    AccountCallback, desconecta, devolve o que achou.

    dll_injetada: para teste (FakeProfitDLL); em uso real, None carrega a
    DLL de verdade via cred.dll_path.
    """
    coletor = _Coletor()
    dll = dll_injetada if dll_injetada is not None else load_dll(cred.dll_path)

    def _on_state(tipo: int, valor: int) -> None:
        log.info("ea_contas.estado", tipo=tipo, valor=valor)
        if tipo == 0 and valor == 0:
            coletor.conectado = True
        elif valor < 0:
            coletor.erro_estado = f"tipo={tipo} valor={valor}"

    def _on_account(n_corretora: int, corretora_nome, account_id, titular) -> None:
        coletor.contas.append(ContaEncontrada(
            corretora_id=n_corretora,
            corretora_nome=corretora_nome or "",
            account_id=account_id or "",
            titular=titular or "",
        ))
        log.info("ea_contas.conta_recebida", corretora_id=n_corretora,
                 corretora=corretora_nome, account_id=account_id)

    # Callbacks que nao nos interessam aqui: no-ops, mas PRECISAM existir —
    # a assinatura de DLLInitializeLogin exige um ponteiro valido em cada
    # posicao, nao aceita None no meio da lista posicional em todas as
    # versoes. Guardamos as referencias no coletor* (via closures) para nao
    # serem coletadas pelo GC antes do fim da funcao.
    cb_state = TStateCallback(_on_state)
    cb_account = TAccountCallback(_on_account)
    cb_history = THistoryCallback(lambda *a: None)
    cb_order_change = TOrderChangeCallback(lambda *a: None)
    cb_new_trade = TNewTradeCallback(lambda *a: None)
    cb_new_daily = TNewDailyCallback(lambda *a: None)
    cb_price_book = TPriceBookCallbackV1(lambda *a: None)
    cb_offer_book = TOfferBookCallbackV1(lambda *a: None)
    cb_history_trade = THistoryTradeCallback(lambda *a: None)
    cb_progress = TProgressCallback(lambda *a: None)
    cb_tiny_book = TTinyBookCallback(lambda *a: None)

    log.info("ea_contas.conectando", user=cred.user[:3] + "***" if cred.user else "")
    ret = dll.DLLInitializeLogin(
        cred.activation_key, cred.user, cred.password,
        cb_state, cb_history, cb_order_change, cb_account,
        cb_new_trade, cb_new_daily, cb_price_book, cb_offer_book,
        cb_history_trade, cb_progress, cb_tiny_book,
    )
    if ret != 0:
        raise SystemExit(
            f"DLLInitializeLogin devolveu {ret} (nao-zero = erro). Confira "
            f"credenciais em .env (PROFIT_ACTIVATION_KEY/USER/PASSWORD)."
        )

    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        if coletor.erro_estado:
            raise SystemExit(f"Estado de erro reportado: {coletor.erro_estado}")
        if coletor.conectado:
            dll.GetAccount()
            break
        time.sleep(0.2)
    else:
        raise SystemExit(
            f"Nao conectou em {timeout_s}s. Rede lenta? Servidor Nelogade "
            f"fora do ar? Confira o log acima para o ultimo estado reportado."
        )

    # Espera as contas chegarem (callback assincrono) -- GetAccount() nao
    # bloqueia, o(s) AccountCallback(s) chegam depois, em thread da DLL.
    time.sleep(3.0)

    dll.DLLFinalize()
    return coletor.contas
