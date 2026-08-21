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
    -2147483647: "Erro interno da DLL",
    -2147483646: "Login nao efetuado",
    -2147483645: "Login invalido",
    -2147483644: "DLL ja inicializada",
    -2147483643: "Ticker invalido",
    -2147483642: "Sem permissao para o ativo",
    -2147483640: "Falta de parametro obrigatorio",
    -2147483639: "Parametro invalido",
    -2147483637: "DLL nao inicializada",
    # Confirmado no manual (2026-08-21): GetHistoryTrades so' aceita
    # 'data inicial' dentro dos ultimos 30 dias corridos a partir de hoje.
    # Nao e' restricao de conta/conexao — e' limite documentado da funcao.
    # Ver docs/OPERACAO.md para o que isso implica no backfill.
    -2147483602: "Periodo de historico excede o limite permitido "
                 "(data inicial com mais de 30 dias) — GetHistoryTrades "
                 "so' cobre os ultimos ~30 dias corridos a partir de hoje",
}


_NL_BASE = -2147483648  # 0x80000000


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
