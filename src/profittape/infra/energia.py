"""
Manter a maquina ACORDADA enquanto o record roda (2026-09-19, incidente real).

INCIDENTE (18/09): o notebook do operador entrou em *Modern Standby* as
16:08 (evento Kernel-Power 172, "Adaptive Connected Standby"), DESLIGOU a
rede (Wi-Fi Intel Netwtw10 para o estado D3), acordou as 16:34 por
"Austerity Battery Drain Budget Exceeded" e VOLTOU a dormir as 16:34:22.
O processo inteiro parou: 26 min sem heartbeat, a DLL reconectando depois,
e ~50 min de tape de WINFUT faltando -- 35 barras em vez de 38.

Configurar o plano de energia do Windows ajuda, mas pode ser desfeito por
uma atualizacao ou por outro programa sem aviso. O jeito robusto e' o
PROPRIO processo pedir: `SetThreadExecutionState`, com
`ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED`.

Por que ES_DISPLAY_REQUIRED tambem: no *Modern Standby* a entrada em
espera e' disparada pelo DESLIGAMENTO DA TELA por inatividade; manter so'
o sistema nao basta. Custo aceito: a tela fica ligada (pode ser escurecida
na mao). Nao impede fechar a tampa nem apertar o botao de energia -- isso
e' acao do operador.

Fora do Windows (testes, sandbox) e' no-op.
"""

from __future__ import annotations

import sys

import structlog

log = structlog.get_logger(__name__)

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


def manter_acordado() -> bool:
    """Pede ao Windows para nao entrar em espera enquanto o processo vive.
    Devolve True se o pedido foi aceito."""
    if sys.platform != "win32":
        return False
    import ctypes

    flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
    anterior = ctypes.windll.kernel32.SetThreadExecutionState(flags)
    ok = bool(anterior)
    if ok:
        log.warning("energia.mantendo_acordado",
                    nota=("o Windows nao vai entrar em espera enquanto o record rodar "
                          "(Modern Standby derrubou a rede em 18/09); a TELA fica ligada"))
    else:
        log.error("energia.pedido_recusado",
                  nota=("SetThreadExecutionState falhou -- a maquina PODE dormir durante o "
                        "pregao. Configure o plano de energia: 'nunca suspender' na tomada"))
    return ok


def liberar() -> None:
    """Devolve ao Windows o controle normal de energia."""
    if sys.platform != "win32":
        return
    import ctypes

    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
