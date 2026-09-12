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
from ctypes import pointer
from dataclasses import dataclass, field
from typing import Any

import structlog

from ..config import Credenciais
from ..domain.enums import AtivacaoResult, ConnState, LoginResult, RoteamentoResult
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
    check_exports_ea_contas,
    load_dll,
)
from ..profitdll.types import (
    TConnectorAccountIdentifier,
    TConnectorAccountIdentifierOut,
)

log = structlog.get_logger(__name__)

_LOGIN_ERROS = {
    LoginResult.INVALID: "login invalido",
    LoginResult.INVALID_PASS: "senha invalida",
    LoginResult.BLOCKED_PASS: "senha bloqueada",
    LoginResult.EXPIRED_PASS: "senha expirada",
    LoginResult.UNKNOWN_ERR: "erro interno de login (LOGIN_UNKNOWN_ERR)",
}


@dataclass
class SubcontaEncontrada:
    """Uma subconta de roteamento. A DLL NAO CRIA subconta (so' funcoes
    Get* existem no manual) -- criar e' pela XP/Nelogica. Isto so'
    descobre o que ja' existe, para o E5 validar a config de cada EA
    antes de subir (docs/EA_ARQUITETURA 4.2)."""

    corretora_id: int
    account_id: str
    sub_account_id: str


@dataclass
class ContaEncontrada:
    corretora_id: int
    corretora_nome: str
    account_id: str
    titular: str
    subcontas: list[SubcontaEncontrada] = field(default_factory=list)


@dataclass
class _Coletor:
    """Guarda o resultado dos callbacks. Precisa sobreviver ate' o fim da
    funcao (ctypes nao segura referencia sozinho — ver aviso em bindings.py)."""
    contas: list[ContaEncontrada] = field(default_factory=list)
    # BUG REAL corrigido (2026-08-26): antes, "conectado" virava True so'
    # com tipo=LOGIN valor=CONNECTED -- o PRIMEIRO dos 4 sinais de conexao
    # documentados no manual, nao "tudo pronto". GetAccount() depende do
    # ROTEAMENTO com a CORRETORA conectada (RoteamentoResult.
    # BROKER_CONNECTED=5), nao so' do login basico. client.py (record) ja'
    # fazia isso certo para market data (checa tipo==MARKET_DATA, nao
    # tipo==LOGIN) -- contas.py copiou o padrao errado.
    pronto_para_contas: bool = False
    erro_estado: str | None = None


def listar_subcontas(dll: Any, corretora_id: int, account_id: str) -> list[SubcontaEncontrada]:
    """
    Enumera as subcontas de UMA conta, via GetSubAccountCount +
    GetSubAccounts. Segue o padrao do `main.py` oficial da Nelogica:
    contar primeiro, alocar o array do tamanho certo, preencher.

    READ-ONLY. Se a DLL nao expuser as funcoes (versao antiga) ou a
    contagem vier negativa (codigo de erro NL), devolve lista VAZIA --
    conta sem subconta e' o caso normal hoje, nao e' erro. Quem precisa
    de uma subconta especifica (E5) e' que deve reclamar se nao achar.
    """
    if not (hasattr(dll, "GetSubAccountCount") and hasattr(dll, "GetSubAccounts")):
        log.info("ea_contas.subcontas_nao_suportadas", corretora_id=corretora_id,
                 nota="esta DLL nao expoe GetSubAccountCount/GetSubAccounts")
        return []

    mestre = TConnectorAccountIdentifier(
        version=0, broker_id=int(corretora_id), account_id=account_id,
        sub_account_id=None, reserved=0,
    )
    n = int(dll.GetSubAccountCount(pointer(mestre)))
    if n <= 0:
        # n<0 e' codigo de erro NL; n==0 e' "nao tem subconta". Os dois
        # levam ao mesmo lugar aqui (lista vazia), mas logam diferente
        # para nao esconder um erro real atras de "conta sem subconta".
        if n < 0:
            log.warning("ea_contas.subcontas_erro", corretora_id=corretora_id,
                        account_id=account_id, retorno=n)
        return []

    buf = (TConnectorAccountIdentifierOut * n)()
    for item in buf:
        item.version = 0
    devolvidas = int(dll.GetSubAccounts(pointer(mestre), 0, 0, n, buf))
    if devolvidas < 0:
        log.warning("ea_contas.subcontas_erro_enumerar", corretora_id=corretora_id,
                    account_id=account_id, retorno=devolvidas)
        return []

    achadas: list[SubcontaEncontrada] = []
    for i in range(min(devolvidas, n)):
        sub = buf[i]
        sub_id = str(sub.sub_account_id or "")
        if not sub_id:
            continue
        achadas.append(SubcontaEncontrada(
            corretora_id=int(sub.broker_id),
            account_id=str(sub.account_id or account_id),
            sub_account_id=sub_id,
        ))
        log.info("ea_contas.subconta_recebida", corretora_id=int(sub.broker_id),
                 account_id=str(sub.account_id or account_id), sub_account_id=sub_id)
    return achadas


def listar_contas(cred: Credenciais, timeout_s: float = 15.0,
                  dll_injetada: Any | None = None) -> list[ContaEncontrada]:
    """
    Conecta, chama GetAccount(), espera ate' timeout_s por respostas do
    AccountCallback, desconecta, devolve o que achou.

    dll_injetada: para teste (FakeProfitDLL); em uso real, None carrega a
    DLL de verdade via cred.dll_path.
    """
    coletor = _Coletor()
    dll = dll_injetada if dll_injetada is not None else load_dll(cred.dll_path)

    def _on_state(tipo: int, valor: int) -> None:
        # Log de TODA transicao de estado, nao so' sucesso/erro -- material
        # forense para um eventual chamado com a XP (o manual nao detalha
        # POR QUE cada erro acontece, so' o codigo).
        log.info("ea_contas.estado", tipo=tipo, valor=valor)

        if tipo == ConnState.LOGIN:
            if valor in _LOGIN_ERROS:
                coletor.erro_estado = f"login: {_LOGIN_ERROS[LoginResult(valor)]} (codigo {valor})"

        elif tipo == ConnState.ROTEAMENTO:
            if valor == RoteamentoResult.BROKER_CONNECTED:
                coletor.pronto_para_contas = True
            elif coletor.pronto_para_contas and valor in (
                RoteamentoResult.DISCONNECTED, RoteamentoResult.BROKER_DISCONNECTED,
            ):
                # Regressao APOS ja ter conectado -- a sessao caiu sozinha,
                # nao e' um erro nosso de configuracao.
                coletor.erro_estado = (
                    f"roteamento caiu DEPOIS de conectar (codigo {valor}) -- "
                    f"sessao invalidada pelo servidor, nao pela nossa config."
                )

        elif tipo == ConnState.ATIVACAO and valor == AtivacaoResult.INVALID:
            # BUG REAL corrigido (2026-08-26): o codigo antigo so' tratava
            # "valor < 0" como erro -- mas TODOS os codigos de erro
            # documentados no manual (LOGIN_INVALID=1, ROTEAMENTO_
            # DISCONNECTED=0, ATIVACAO_INVALID=1, etc.) sao NAO-NEGATIVOS.
            # "valor < 0" NUNCA disparava para nenhum estado real -- a
            # deteccao de erro estava, na pratica, morta desde sempre.
            coletor.erro_estado = (
                "ATIVACAO INVALIDADA (CONNECTION_ACTIVATE_INVALID) apos a "
                "sessao ter sido aceita inicialmente -- reportar a XP: a "
                "chave de ativacao pode nao ter permissao de roteamento/"
                "operacoes habilitada para esta conta."
            )

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
        if coletor.pronto_para_contas:
            # Checagem que faltava (encontrada 2026-08-26 investigando
            # NL_INTERNAL_ERROR): confere que esta versao da DLL EXPOE
            # GetAccount antes de chamar -- so' AGORA, nao antes de saber
            # que a conexao teve sucesso, para nao falsear testes que
            # verificam outros caminhos de erro (retorno/timeout) que
            # nunca chegam ate' aqui de qualquer forma.
            ausentes = check_exports_ea_contas(dll)
            if ausentes:
                raise SystemExit(
                    f"Esta DLL nao expoe {ausentes} -- versao incompativel "
                    f"com o modulo ea/. Confira o caminho em PROFIT_DLL_PATH."
                )
            dll.GetAccount()
            break
        time.sleep(0.2)
    else:
        raise SystemExit(
            f"Roteamento/corretora nao conectou em {timeout_s}s. Rede lenta? "
            f"Servidor Nelogica fora do ar? Confira o log acima para o "
            f"ultimo estado reportado."
        )

    # Espera as contas chegarem (callback assincrono) -- GetAccount() nao
    # bloqueia. CONTINUA observando erro_estado durante a espera: visto na
    # pratica (2026-08-26) a sessao pode ser invalidada DEPOIS de
    # GetAccount() ja ter sido chamado (tudo conectou, GetAccount foi
    # chamado, ~2.5s depois ATIVACAO_INVALIDA e nenhuma conta chegou) --
    # sem isso, o operador so' veria "nenhuma conta retornada", sem saber
    # que a sessao caiu sozinha logo depois.
    t1 = time.monotonic()
    while time.monotonic() - t1 < 3.0:
        if coletor.erro_estado:
            raise SystemExit(
                f"A sessao caiu enquanto esperava as contas chegarem: "
                f"{coletor.erro_estado}"
            )
        if coletor.contas:
            break
        time.sleep(0.1)

    # Dedup por (corretora_id, account_id) -- observado na pratica
    # (2026-08-26): o AccountCallback pode disparar mais de uma vez para a
    # MESMA conta (nao e' erro nosso, e' como a DLL entrega); sem isso, o
    # operador via a mesma conta duas vezes na lista, parecendo duas
    # contas distintas quando era so' uma.
    vistas: set[tuple[int, str]] = set()
    unicas: list[ContaEncontrada] = []
    for c in coletor.contas:
        chave = (c.corretora_id, c.account_id)
        if chave not in vistas:
            vistas.add(chave)
            unicas.append(c)

    # Subcontas (E5.2): uma consulta por conta UNICA, depois do dedup --
    # antes do dedup rodaria 2x para a mesma conta a toa. Feito ANTES do
    # DLLFinalize (a DLL precisa estar viva), mas DEPOIS de ter a lista
    # limpa. Falha aqui NAO derruba a listagem de contas: subconta e'
    # informacao adicional, a conta em si ja' foi descoberta com sucesso.
    for c in unicas:
        try:
            c.subcontas = listar_subcontas(dll, c.corretora_id, c.account_id)
        except Exception as exc:
            log.warning("ea_contas.subcontas_falharam", corretora_id=c.corretora_id,
                        account_id=c.account_id, erro=repr(exc))

    dll.DLLFinalize()
    return unicas
