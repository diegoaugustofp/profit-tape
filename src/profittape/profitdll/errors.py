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
}


def describe(code: int) -> str:
    return _ERRORS.get(code, f"codigo desconhecido {code}")


def check(code: int, contexto: str) -> None:
    """Levanta se o retorno nao for OK. Codigo positivo tambem e' sucesso."""
    if code < NL_OK:
        raise SubscriptionFailed(f"{contexto}: {describe(code)}")
