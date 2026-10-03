"""Estados que a ProfitDLL entrega em `TStateCallback(nConnStateType, nResult)`, com o texto
do manual (v4.0.0.42). O diario mostra o NOME e a DESCRICAO em vez de dois inteiros."""

from __future__ import annotations

TIPOS: dict[int, str] = {
    0: "LOGIN (servidor de login)",
    1: "ROTEAMENTO",
    2: "MARKET DATA",
    3: "MARKET LOGIN (ativacao)",
}

# (tipo, valor) -> (nome, descricao). `grave` marca o que merece destaque.
_E: dict[tuple[int, int], tuple[str, str]] = {
    (0, 0): ("LOGIN_CONNECTED", "Servidor de login conectado"),
    (0, 1): ("LOGIN_INVALID", "Login e' invalido"),
    (0, 2): ("LOGIN_INVALID_PASS", "Senha invalida"),
    (0, 3): ("LOGIN_BLOCKED_PASS", "Senha bloqueada"),
    (0, 4): ("LOGIN_EXPIRED_PASS", "Senha expirada"),
    (0, 200): ("LOGIN_UNKNOWN_ERR", "Erro interno de login"),
    (1, 0): ("ROTEAMENTO_DISCONNECTED", "Roteamento desconectado"),
    (1, 1): ("ROTEAMENTO_CONNECTING", "Conectando ao servidor de roteamento"),
    (1, 2): ("ROTEAMENTO_CONNECTED", "Conectado ao servidor de roteamento"),
    (1, 3): ("ROTEAMENTO_BROKER_DISCONNECTED", "Corretora desconectada"),
    (1, 4): ("ROTEAMENTO_BROKER_CONNECTING", "Conectando a corretora"),
    (1, 5): ("ROTEAMENTO_BROKER_CONNECTED", "Corretora conectada"),
    (2, 0): ("MARKET_DISCONNECTED", "Desconectado do servidor de market data"),
    (2, 1): ("MARKET_CONNECTING", "Conectando ao servidor de market data"),
    (2, 2): ("MARKET_WAITING", "Esperando conexao"),
    (2, 3): ("MARKET_NOT_LOGGED", "Nao logado ao servidor de market data"),
    (2, 4): ("MARKET_CONNECTED", "Conectado ao market data"),
    (2, 5): ("MARKET_PERFORMANCE_WARNING",
             "Conectado, mas o servidor reportou degradacao de performance"),
    (2, 6): ("MARKET_PARTIAL_CONNECTED",
             "Conectado, mas a ENTREGA LOCAL dos callbacks de market data esta' PARADA: o feed do "
             "servidor esta' OK e o cliente nao esta' consumindo os callbacks (aviso critico: "
             "callbacks atrasados ou perdidos ate' voltar ao estado 4)"),
    (3, 0): ("CONNECTION_ACTIVATE_VALID", "Ativacao valida"),
    (3, 1): ("CONNECTION_ACTIVATE_INVALID", "Ativacao invalida"),
}
GRAVES = {(2, 5), (2, 6), (0, 1), (0, 2), (0, 3), (0, 4), (0, 200)}


def descrever(tipo: object, valor: object) -> tuple[str, str, str, bool]:
    """(tipo_txt, nome, descricao, grave). Desconhecido nao levanta: mostra o numero."""
    try:
        t, v = int(str(tipo)), int(str(valor))
    except ValueError:
        return str(tipo), str(valor), "estado fora do manual", False
    nome, desc = _E.get((t, v), (f"valor {v}", "valor fora do manual"))
    return TIPOS.get(t, f"tipo {t}"), nome, desc, (t, v) in GRAVES
