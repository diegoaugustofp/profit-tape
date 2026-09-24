"""Erros da camada ProfitDLL."""

from __future__ import annotations


class ProfitDLLError(RuntimeError):
    """Base."""


class DLLNotFound(ProfitDLLError):
    """Caminho da DLL invalido ou arquitetura incompativel (32 vs 64 bits)."""


class LoginFailed(ProfitDLLError):
    """Credencial recusada ou chave de ativacao invalida."""


class SubscriptionFailed(ProfitDLLError):
    """SubscribeTicker/OfferBook devolveu codigo de erro."""


# Codigos de retorno documentados. Confirme contra o manual da sua versao.
NL_OK = 0
_ERRORS: dict[int, str] = {
    # TABELA OFICIAL do manual (conferida em 2026-09-23, secao "Codigos de
    # erro"). A anterior estava ERRADA de -2147483646 em diante -- traduzia
    # NL_INVALID_ARGS como "Login invalido" e inventou "DLL ja inicializada",
    # "Ticker invalido" e "DLL nao inicializada" em codigos que sao outra
    # coisa. Isso ja' me levou a um diagnostico errado (22-23/09, na recusa
    # do SendCancelOrders).
    -2147483647: "NL_INTERNAL_ERROR: erro interno",
    -2147483646: "NL_NOT_INITIALIZED: nao inicializado",
    -2147483645: "NL_INVALID_ARGS: argumentos invalidos",
    -2147483644: "NL_WAITING_SERVER: aguardando dados do servidor",
    -2147483643: "NL_NO_LOGIN: nenhum login encontrado",
    -2147483642: "NL_NO_LICENSE: nenhuma licenca encontrada",
    -2147483639: "NL_OUT_OF_RANGE: count do parametro maior que o array",
    -2147483638: "NL_MARKET_ONLY: nao possui roteamento",
    -2147483637: "NL_NO_POSITION: nao possui posicao",
    -2147483636: "NL_NOT_FOUND: recurso nao encontrado",
    -2147483635: "NL_VERSION_NOT_SUPPORTED: versao do recurso nao suportada",
    -2147483634: "NL_OCO_NO_RULES: OCO sem nenhuma regra",
    -2147483633: "NL_EXCHANGE_UNKNOWN: bolsa desconhecida",
    -2147483632: "NL_NO_OCO_DEFINED: nenhuma OCO encontrada para a ordem",
    -2147483631: "NL_INVALID_SERIE: (level + offset + factor) invalido",
    -2147483630: "NL_LICENSE_NOT_ALLOWED: recurso nao liberado na licenca",
    -2147483629: "NL_NOT_HARD_LOGOUT: nao esta em HardLogout",
    -2147483628: "NL_SERIE_NO_HISTORY: serie sem historico no servidor",
    -2147483627: "NL_ASSET_NO_DATA: ativo sem TData carregado",
    -2147483626: "NL_SERIE_NO_DATA: serie sem dados (count = 0)",
    -2147483625: "NL_HAS_STRATEGY_RUNNING: existe uma estrategia rodando",
    -2147483624: "NL_SERIE_NO_MORE_HISTORY: nao ha' mais dados para a serie",
    -2147483623: "NL_SERIE_MAX_COUNT: serie no limite de dados",
    -2147483622: "NL_DUPLICATE_RESOURCE: recurso duplicado",
    -2147483621: "NL_UNSIGNED_CONTRACT: contrato nao assinado",
    -2147483620: "NL_NO_PASSWORD: nenhuma senha informada",
    -2147483619: "NL_NO_USER: nenhum usuario informado no login",
    -2147483618: "NL_FILE_ALREADY_EXISTS: arquivo ja' existe",
    -2147483617: "NL_INVALID_TICKER: ativo e' invalido",
    -2147483616: "NL_NOT_MASTER_ACCOUNT: conta nao e' master",
    -2147483602: ("NL_HISTORY_PERIOD_LIMIT: periodo de historico excede o limite "
                  "(data inicial com mais de 30 dias) — GetHistoryTrades "
                  "so' aceita os ultimos 30 dias corridos"),
}


_NL_BASE = -2147483648  # 0x80000000


def normalizar_retorno(valor: int) -> int:
    """
    Converte um retorno lido como 64 bits de volta para int32 COM SINAL.

    POR QUE ISTO EXISTE (bug real, 2026-09-24): as funcoes de ordem sao
    declaradas com `restype = c_int64` porque devolvem ID de ordem, que e'
    grande. Mas os CODIGOS DE ERRO sao de 32 bits: `NL_INVALID_ARGS` e'
    `0x80000003`, que como int32 assinado e' -2147483645 e como int64
    positivo e' +2147483651.

    Consequencia no pregao de 24/09: `SendCancelOrders` devolveu erro, o
    teste `if r < 0` NAO disparou (o valor chegou positivo), e o codigo
    concluiu `cancel_todas_ok=True` para uma chamada que FALHOU. O EA
    entrou em laco de "tentar de novo" e encheu o log de warnings.

    Regra: valores no intervalo [0x80000000, 0xFFFFFFFF] sao codigos NL
    de erro mal lidos e viram negativos. IDs de ordem reais (como
    26091112112953, medido no E2) sao MAIORES que 0xFFFFFFFF e passam
    intactos, assim como qualquer retorno pequeno e positivo.
    """
    if 0x80000000 <= valor <= 0xFFFFFFFF:
        return valor - 0x100000000
    return valor


def describe(code: int) -> str:
    if code in _ERRORS:
        return _ERRORS[code]
    # Codigo fora da tabela: dar tudo que ajuda a acha-lo no manual. Os NL_*
    # sao sequenciais a partir da base, entao o OFFSET e' o indice na lista
    # de constantes da sua versao da documentacao.
    offset = code - _NL_BASE
    return (f"codigo desconhecido {code} (hex {code & 0xFFFFFFFF:#010x}, "
            f"NL base+{offset}) — procure o {offset}o codigo NL_ no manual "
            f"da sua versao e acrescente-o em profitdll/errors.py")


def check(code: int, contexto: str) -> None:
    """Levanta se o retorno nao for OK. Codigo positivo tambem e' sucesso."""
    if code < NL_OK:
        raise SubscriptionFailed(f"{contexto}: {describe(code)}")
