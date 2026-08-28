"""
UNICO ponto de contato com a ProfitDLL.

======================================================================
      SE A SUA VERSAO DA DLL FOR DIFERENTE, CORRIJA AQUI E SO AQUI.
======================================================================

As assinaturas abaixo seguem a documentacao publica da ProfitDLL e valem para
as versoes que expoem `DLLInitializeMarketLogin` + callbacks V2. Elas MUDAM
entre versoes: campos sao acrescentados no fim da lista de argumentos, e um
argumento a mais ou a menos em WINFUNCTYPE corrompe a pilha — o sintoma e'
crash do processo ou valor absurdo em campo numerico, nunca uma excecao
Python limpa.

Antes de rodar em producao: confira cada assinatura contra o manual da sua
versao e rode `profit-tape doctor`, que valida os exports presentes na DLL.

Por que WINFUNCTYPE e nao CFUNCTYPE: a interface e' stdcall. Em x86-64 as duas
convergem, mas em terminal 32 bits a diferenca e' fatal.

Por que as referencias dos callbacks sao guardadas no cliente: ctypes nao
mantem referencia forte ao objeto de callback. Se o Python coletar o objeto
enquanto a DLL ainda tem o ponteiro, o proximo evento executa memoria liberada.
"""

from __future__ import annotations

import sys
from ctypes import (
    CFUNCTYPE,
    c_char,
    c_double,
    c_int,
    c_int64,
    c_uint,
    c_void_p,
    c_wchar_p,
)
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    from ctypes import WINFUNCTYPE
else:
    # Fora do Windows, `WINFUNCTYPE` nem existe em ctypes. Cair para CFUNCTYPE
    # mantem o modulo IMPORTAVEL, o que permite rodar a suite inteira em CI
    # Linux com a DLL falsa. Nenhuma DLL real e' carregada nesse caminho —
    # `load_dll` recusa plataforma nao-Windows explicitamente.
    WINFUNCTYPE = CFUNCTYPE

from .errors import DLLNotFound
from .types import TAssetIDRec

# --------------------------------------------------------------------------
# Assinaturas de callback
# --------------------------------------------------------------------------

TStateCallback = WINFUNCTYPE(None, c_int, c_int)

TNewTradeCallback = WINFUNCTYPE(
    None,
    TAssetIDRec,   # ativo
    c_wchar_p,     # data "DD/MM/YYYY HH:NN:SS.ZZZ"
    c_uint,        # numero do negocio
    c_double,      # preco
    c_double,      # volume financeiro
    c_int,         # quantidade
    c_int,         # agente comprador
    c_int,         # agente vendedor
    c_int,         # tipo do negocio
    c_char,        # flag de edicao
)

TNewDailyCallback = WINFUNCTYPE(
    None,
    TAssetIDRec,
    c_wchar_p,     # data
    c_double, c_double, c_double, c_double,   # open, high, low, close
    c_double, c_double, c_double, c_double,   # vol financeiro, ajuste, max lim, min lim
    c_double, c_double,                       # vol compra, vol venda
    c_int, c_int, c_int, c_int, c_int, c_int, # qtd, negocios, contratos abertos, ...
)

# V1 x V2 (manual, secao de tipos): as assinaturas sao identicas EXCETO nQtd —
# Integer (32 bits) no V1, Int64 no V2. Os slots do DLLInitializeMarketLogin
# sao os tipos V1; o V2 so entra pelos setters SetOfferBookCallbackV2 /
# SetPriceBookCallbackV2, que "sobrepoem a callback definida pelo
# DLLInitialize*" (texto do manual).
#
# Incidente que gravou essa licao (2026-08-21): callbacks V2 registrados nos
# slots V1 do init. Sintomas DIFERENTES por callback: offer book ficou MUDO
# (subscribe OK, zero eventos em 14 min de pregao); price book "funcionou",
# mas lendo Int64 de um slot onde o Delphi escreve 32 bits — quantidade com
# bits altos potencialmente sujos. Silencio e corrupcao silenciosa, nenhum
# crash: e' assim que erro de ABI se manifesta.

TOfferBookCallbackV1 = WINFUNCTYPE(
    None,
    TAssetIDRec,
    c_int,         # action
    c_int,         # position
    c_int,         # side
    c_int,         # quantidade — Integer no V1
    c_int,         # agente
    c_int64,       # offer id
    c_double,      # preco
    c_char, c_char, c_char, c_char, c_char,   # has price/qtd/date/id/agent
    c_wchar_p,     # data
    c_void_p,      # array sell
    c_void_p,      # array buy
)

TOfferBookCallbackV2 = WINFUNCTYPE(
    None,
    TAssetIDRec,
    c_int,         # action
    c_int,         # position
    c_int,         # side
    c_int64,       # quantidade
    c_int,         # agente
    c_int64,       # offer id
    c_double,      # preco
    c_char,        # has price
    c_char,        # has quantity
    c_char,        # has date
    c_char,        # has offer id
    c_char,        # has agent
    c_wchar_p,     # data
    c_void_p,      # array sell (nao usamos: reconstruimos do delta)
    c_void_p,      # array buy
)

TPriceBookCallbackV1 = WINFUNCTYPE(
    None,
    TAssetIDRec,
    c_int,         # action
    c_int,         # position
    c_int,         # side
    c_int,         # quantidade — Integer no V1
    c_int,         # numero de ofertas no nivel
    c_double,      # preco
    c_void_p,
    c_void_p,
)

TPriceBookCallbackV2 = WINFUNCTYPE(
    None,
    TAssetIDRec,
    c_int,         # action
    c_int,         # position
    c_int,         # side
    c_int64,       # quantidade
    c_int,         # numero de ofertas no nivel
    c_double,      # preco
    c_void_p,
    c_void_p,
)

TTinyBookCallback = WINFUNCTYPE(
    None,
    TAssetIDRec,
    c_double,      # preco
    c_int,         # quantidade
    c_int,         # side
)

TProgressCallback = WINFUNCTYPE(None, TAssetIDRec, c_int)

THistoryTradeCallback = WINFUNCTYPE(
    None,
    TAssetIDRec,
    c_wchar_p,
    c_uint,
    c_double,
    c_double,
    c_int,
    c_int,
    c_int,
    c_int,
)

# --------------------------------------------------------------------------
# Callbacks EXCLUSIVOS do login completo (DLLInitializeLogin, roteamento).
# O record nunca usa estes — so' o utilitario de diagnostico ea/contas.py
# (GetAccount) precisa deles, e so' passa no-ops para os que nao usa.
# --------------------------------------------------------------------------

TAccountCallback = WINFUNCTYPE(
    None,
    c_int,      # nCorretora
    c_wchar_p,  # CorretoraNomeCompleto
    c_wchar_p,  # AccountID
    c_wchar_p,  # NomeTitular
)

TOrderChangeCallback = WINFUNCTYPE(
    None,
    TAssetIDRec,  # rAssetID
    c_int,        # nCorretora
    c_int,        # nQtd
    c_int,        # nTradedQtd
    c_int,        # nLeavesQtd
    c_int,        # nSide
    c_double,     # dPrice
    c_double,     # dStopPrice
    c_double,     # dAvgPrice
    c_int64,      # nProfitID
    c_wchar_p,    # TipoOrdem
    c_wchar_p,    # Conta
    c_wchar_p,    # Titular
    c_wchar_p,    # ClOrdID
    c_wchar_p,    # Status
    c_wchar_p,    # Date
    c_wchar_p,    # TextMessage
)

THistoryCallback = WINFUNCTYPE(
    None,
    TAssetIDRec,  # rAssetID
    c_int,        # nCorretora
    c_int,        # nQtd
    c_int,        # nTradedQtd
    c_int,        # nLeavesQtd
    c_int,        # nSide
    c_double,     # dPrice
    c_double,     # dStopPrice
    c_double,     # dAvgPrice
    c_int64,      # nProfitID
    c_wchar_p,    # TipoOrdem
    c_wchar_p,    # Conta
    c_wchar_p,    # Titular
    c_wchar_p,    # ClOrdID
    c_wchar_p,    # Status
    c_wchar_p,    # Date
)


def load_dll(path: str | Path) -> Any:
    """
    Carrega a DLL e declara os prototipos das funcoes que usamos.

    Erro classico aqui: DLL de 64 bits com Python de 32 bits (ou vice-versa).
    O OSError do Windows nesse caso e' enigmatico, entao traduzimos.
    """
    if sys.platform != "win32":  # pragma: no cover
        raise DLLNotFound(
            "A ProfitDLL so existe para Windows. Em Linux/macOS use "
            "FakeProfitDLL (tests/fakes) para exercitar o pipeline."
        )

    # Ignorar tipo aqui, justificado: WinDLL so existe no ctypes real do
    # Windows -- inexistente no stub usado ao rodar mypy fora do Windows
    # (CI Linux). A guarda `sys.platform != "win32": raise` acima ja
    # impede este import de rodar de verdade fora do Windows -- o mypy
    # nao entende esse padrao de exclusao de plataforma aqui, so' o
    # runtime. Import tardio: nao existe fora do Windows.
    from ctypes import WinDLL  # type: ignore[attr-defined]

    p = Path(path)
    if not p.exists():
        raise DLLNotFound(f"DLL nao encontrada em {p}")

    try:
        dll = WinDLL(str(p))
    except OSError as exc:  # pragma: no cover
        bits = 64 if sys.maxsize > 2**32 else 32
        raise DLLNotFound(
            f"Falha ao carregar {p}. A causa quase sempre e' incompatibilidade "
            f"de arquitetura: este Python e' de {bits} bits e a DLL provavelmente "
            f"nao. Detalhe do sistema: {exc}"
        ) from exc

    _declare(dll)
    return dll


def _declare(dll: Any) -> None:
    """Declara argtypes/restype. Sem isso, ctypes trunca ponteiros em 64 bits."""
    dll.DLLInitializeMarketLogin.argtypes = [
        c_wchar_p, c_wchar_p, c_wchar_p,
        TStateCallback,
        TNewTradeCallback,
        TNewDailyCallback,
        TPriceBookCallbackV1,      # slots do init sao V1 — ver nota acima
        TOfferBookCallbackV1,
        THistoryTradeCallback,
        TProgressCallback,
        TTinyBookCallback,
    ]
    dll.DLLInitializeMarketLogin.restype = c_int

    # Login COMPLETO (roteamento) — so' declarado se o export existir; DLLs
    # mais antigas/so'-market-data podem nao ter. Usado exclusivamente pelo
    # utilitario de diagnostico (ea/contas.py), nunca pelo record.
    if hasattr(dll, "DLLInitializeLogin"):
        dll.DLLInitializeLogin.argtypes = [
            c_wchar_p, c_wchar_p, c_wchar_p,
            TStateCallback,
            THistoryCallback,
            TOrderChangeCallback,
            TAccountCallback,
            TNewTradeCallback,
            TNewDailyCallback,
            TPriceBookCallbackV1,
            TOfferBookCallbackV1,
            THistoryTradeCallback,
            TProgressCallback,
            TTinyBookCallback,
        ]
        dll.DLLInitializeLogin.restype = c_int

    if hasattr(dll, "GetAccount"):
        dll.GetAccount.argtypes = []
        dll.GetAccount.restype = c_int

    # ----------------------------------------------------------------------
    # Envio de ordem (modulo ea/execucao.py) — funcoes LEGADAS planas.
    # O manual as marca "obsoleta em favor da nova funcao SendOrder" (V2,
    # struct TConnectorSendOrder com records aninhados + versionamento).
    # DECISAO DE DESIGN (2026-08-26): para a PRIMEIRA ordem que este projeto
    # envia na vida, menos partes moveis > future-proofing — argumentos
    # planos sao verificaveis 1:1 contra o manual, struct aninhada via
    # ctypes e' exatamente o tipo de layout-de-memoria que corrompe em
    # silencio. Migracao para SendOrder V2 registrada como evolucao futura.
    #
    # ARMADILHA REAL do manual: a ordem dos argumentos de SendZeroPosition*
    # e' DIFERENTE das Send*Order — pwcSenha vem em 5o (depois de Ticker/
    # Bolsa), nao em 3o. Conferido caractere a caractere no manual.
    # ----------------------------------------------------------------------
    if hasattr(dll, "SendMarketBuyOrder"):
        for nome in ("SendMarketBuyOrder", "SendMarketSellOrder"):
            fn = getattr(dll, nome)
            fn.argtypes = [c_wchar_p, c_wchar_p, c_wchar_p,   # conta, corretora, senha
                           c_wchar_p, c_wchar_p,              # ticker, bolsa
                           c_int]                             # quantidade
            fn.restype = c_int64
        for nome in ("SendBuyOrder", "SendSellOrder"):
            fn = getattr(dll, nome)
            fn.argtypes = [c_wchar_p, c_wchar_p, c_wchar_p,
                           c_wchar_p, c_wchar_p,
                           c_double,                          # preco limite
                           c_int]
            fn.restype = c_int64
        dll.SendZeroPositionAtMarket.argtypes = [
            c_wchar_p, c_wchar_p,          # conta, corretora
            c_wchar_p, c_wchar_p,          # ticker, bolsa
            c_wchar_p,                     # senha (5o lugar — ver aviso acima)
        ]
        dll.SendZeroPositionAtMarket.restype = c_int64

    for nome in ("SubscribeTicker", "UnsubscribeTicker",
                 "SubscribeOfferBook", "UnsubscribeOfferBook",
                 "SubscribePriceBook", "UnsubscribePriceBook"):
        fn = getattr(dll, nome)
        fn.argtypes = [c_wchar_p, c_wchar_p]
        fn.restype = c_int

    dll.GetHistoryTrades.argtypes = [c_wchar_p, c_wchar_p, c_wchar_p, c_wchar_p]
    dll.GetHistoryTrades.restype = c_int

    dll.DLLFinalize.argtypes = []
    dll.DLLFinalize.restype = c_int

    # Opcional em versoes antigas — nao falhar se ausente.
    if hasattr(dll, "SetServerAndPort"):
        dll.SetServerAndPort.argtypes = [c_wchar_p, c_wchar_p]
        dll.SetServerAndPort.restype = c_int

    # Resolucao de nome de corretora. GetProcAddress e' case-sensitive e a
    # grafia do sufixo (ById/ByID) varia entre versoes — declaramos a que
    # existir. Retorno PWideChar: c_wchar_p copia a string na conversao.
    # Setters V2 (o caminho moderno do offer book order-by-order).
    for nome, tipo in (("SetOfferBookCallbackV2", TOfferBookCallbackV2),
                       ("SetPriceBookCallbackV2", TPriceBookCallbackV2)):
        if hasattr(dll, nome):
            fn = getattr(dll, nome)
            fn.argtypes = [tipo]
            fn.restype = c_int

    for nome in ("GetAgentNameByID", "GetAgentNameById",
                 "GetAgentShortNameByID", "GetAgentShortNameById"):
        if hasattr(dll, nome):
            fn = getattr(dll, nome)
            fn.argtypes = [c_int]
            fn.restype = c_wchar_p


EXPORTS_OBRIGATORIOS = (
    "DLLInitializeMarketLogin",
    "DLLFinalize",
    "SubscribeTicker",
    "SubscribeOfferBook",
    "SubscribePriceBook",
    "GetHistoryTrades",
)

# Escopo SEPARADO do record: o modulo ea/ precisa de roteamento, que o
# record nunca usa. Nao misturar nas duas listas -- forcaria o `doctor`
# do record a exigir funcoes de ordem que uma DLL so-market-data
# legitimamente nao tem.
#
# E dividido em DOIS, nao um so' -- contas.py so' LE contas (nunca envia
# ordem); exigir Send*Order ali seria um requisito falso (bug pego ao
# escrever o teste: o fake de contas.py corretamente nao implementa
# Send*Order, porque nao precisa).
EXPORTS_OBRIGATORIOS_EA_CONTAS = (
    "DLLInitializeLogin",
    "GetAccount",
)
EXPORTS_OBRIGATORIOS_EA_ORDEM = (
    "SendMarketBuyOrder",
    "SendMarketSellOrder",
    "SendZeroPositionAtMarket",
)


def check_exports(dll: Any) -> list[str]:
    """Devolve a lista de exports obrigatorios AUSENTES. Usado por `doctor`."""
    return [nome for nome in EXPORTS_OBRIGATORIOS if not hasattr(dll, nome)]


def check_exports_ea_contas(dll: Any) -> list[str]:
    """
    Mesma ideia de check_exports, mas para o que ea/contas.py precisa
    (login completo + leitura de conta) -- NUNCA verificado antes de hoje
    (2026-08-26, gap real encontrado ao investigar NL_INTERNAL_ERROR em
    DLLInitializeLogin). Nao explica o erro por si so' (e' um codigo de
    retorno de uma funcao que EXISTE e roda, nao um AttributeError de
    funcao ausente) -- mas e' uma defesa legitima contra versao de DLL
    divergente que faltava.
    """
    return [nome for nome in EXPORTS_OBRIGATORIOS_EA_CONTAS if not hasattr(dll, nome)]


def check_exports_ea_ordem(dll: Any) -> list[str]:
    """Mesma ideia, para o que ea/execucao.py precisa (envio de ordem)."""
    return [nome for nome in EXPORTS_OBRIGATORIOS_EA_ORDEM if not hasattr(dll, nome)]
