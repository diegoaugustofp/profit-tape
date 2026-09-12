"""
Estruturas ctypes espelhando os tipos do ProfitDLL.

Delphi usa PWideChar (UTF-16) em toda a interface, por isso c_wchar_p em todo
lugar. Trocar por c_char_p devolve lixo silenciosamente — nao ha excecao, so
dado errado.
"""

from __future__ import annotations

from ctypes import Structure, c_double, c_int, c_int32, c_int64, c_ubyte, c_wchar, c_wchar_p


class TAssetIDRec(Structure):
    """Identificador de ativo passado por valor em todos os callbacks."""

    _fields_ = (
        ("ticker", c_wchar_p),
        ("bolsa", c_wchar_p),
        ("feed", c_int),
    )

    def as_tuple(self) -> tuple[str, str]:
        """(symbol, exchange), ja normalizado contra ponteiro nulo."""
        return (self.ticker or "", self.bolsa or "")


# ---------------------------------------------------------------------------
# Familia V2 (structs), usada so' por GetPositionV2 (E3, 2026-09-11).
#
# CONFIRMADO CONTRA `profitTypes.py` E `profit_dll.py`, exemplos oficiais
# da Nelogica (recebidos do operador em 2026-09-11) -- campo a campo,
# tipo a tipo, identico. Antes disso, tinha sido reconstruido so' a partir
# do texto do manual (Manual_ProfitDLL_pt_br.md), sem acesso a DLL real
# para conferir; a 1a consulta real (2026-09-11, 20:00) veio com
# `open_side` fora do esperado, e a comparacao com o exemplo oficial
# revelou a causa: os campos `Byte` do Delphi (Version, OpenSide,
# FeedType, PositionType) sao SEM SINAL -- `c_ubyte`, nao `c_byte`. O byte
# lido (0xc8) e' 200 sem sinal, nao -56; a leitura errada nao mudava a
# conclusao (200 tambem esta' fora de {0,1,2}), mas o tipo estava errado
# e importaria para uma posicao aberta de verdade.
#
# Por isso `consultar_posicao()` (client.py) ainda FAZ um teste de
# sanidade nos valores lidos (lado em {1,2} quando ha' posicao aberta,
# quantidade num intervalo razoavel) antes de qualquer decisao de
# reconciliacao -- confirmado para posicao ZERADA; posicao ABERTA
# (open_side realmente valendo 1 ou 2) ainda nao foi testada contra a
# DLL real.
# ---------------------------------------------------------------------------
class TConnectorAccountIdentifier(Structure):
    """BrokerID e' Integer (nao string) -- diferente do par (corretora,
    conta) como strings usado nas funcoes de ordem legadas. Converter com
    int(corretora) na hora de preencher."""

    _fields_ = (
        ("version", c_ubyte),
        ("broker_id", c_int32),
        ("account_id", c_wchar_p),
        ("sub_account_id", c_wchar_p),
        ("reserved", c_int64),
    )


class TConnectorAccountIdentifierOut(Structure):
    """
    Versao de SAIDA do identificador de conta: a DLL PREENCHE os buffers,
    entao os campos de texto sao array fixo (`c_wchar * 100`), nao
    ponteiro -- quem aloca somos nos. Usada por `GetSubAccounts`.

    Confirmada campo a campo contra `profitTypes.py` oficial da Nelogica
    (2026-09-11). O tamanho 100 tambem vem de la'; os campos
    `*IDLength` dizem quanto do buffer foi de fato preenchido.
    """

    _fields_ = (
        ("version", c_ubyte),
        ("broker_id", c_int32),
        ("account_id", c_wchar * 100),
        ("account_id_length", c_int32),
        ("sub_account_id", c_wchar * 100),
        ("sub_account_id_length", c_int32),
        ("reserved", c_int64),
    )


class TConnectorAssetIdentifier(Structure):
    _fields_ = (
        ("version", c_ubyte),
        ("ticker", c_wchar_p),
        ("exchange", c_wchar_p),
        ("feed_type", c_ubyte),
    )


class TConnectorTradingAccountPosition(Structure):
    """
    `version=1` exige preencher `position_type` (TConnectorPositionType:
    1=DayTrade, 2=Consolidated) ANTES de chamar GetPositionV2 -- e' campo
    de ENTRADA apesar de vir depois dos campos de saida no record (o
    manual descreve nessa ordem; a struct ctypes segue a mesma ordem).
    Campos de saida (open_quantity em diante) sao preenchidos pela DLL.
    """

    _fields_ = (
        ("version", c_ubyte),
        ("account_id", TConnectorAccountIdentifier),
        ("asset_id", TConnectorAssetIdentifier),
        ("open_quantity", c_int64),
        ("open_average_price", c_double),
        ("open_side", c_ubyte),               # 0=desconhecida 1=comprada 2=vendida
        ("daily_average_sell_price", c_double),
        ("daily_sell_quantity", c_int64),
        ("daily_average_buy_price", c_double),
        ("daily_buy_quantity", c_int64),
        ("daily_quantity_d1", c_int64),
        ("daily_quantity_d2", c_int64),
        ("daily_quantity_d3", c_int64),
        ("daily_quantity_blocked", c_int64),
        ("daily_quantity_pending", c_int64),
        ("daily_quantity_alloc", c_int64),
        ("daily_quantity_provision", c_int64),
        ("daily_quantity", c_int64),
        ("daily_quantity_available", c_int64),
        ("position_type", c_ubyte),            # ENTRADA (ver docstring)
        ("event_id", c_int64),
    )
