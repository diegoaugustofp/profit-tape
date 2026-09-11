"""
Estruturas ctypes espelhando os tipos do ProfitDLL.

Delphi usa PWideChar (UTF-16) em toda a interface, por isso c_wchar_p em todo
lugar. Trocar por c_char_p devolve lixo silenciosamente — nao ha excecao, so
dado errado.
"""

from __future__ import annotations

from ctypes import Structure, c_byte, c_double, c_int, c_int32, c_int64, c_wchar_p


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
# NAO VERIFICADO CONTRA A DLL REAL -- construido a partir do manual
# (Manual_ProfitDLL_pt_br.md, secoes "TConnectorAccountIdentifier",
# "TConnectorAssetIdentifier", "TConnectorTradingAccountPosition",
# "GetPositionV2"), no ambiente Linux deste sandbox, sem acesso a DLL real
# para testar layout de bytes byte a byte. Alinhamento assumido NATURAL
# (ctypes default, sem _pack_), que e' o padrao de record Delphi nao
# marcado como `packed` -- o manual nao diz `packed`, entao esta e' a
# leitura mais provavel, mas fica registrada como suposicao.
#
# Por isso `consultar_posicao()` (client.py) FAZ um teste de sanidade nos
# valores lidos (lado em {0,1,2}, quantidade num intervalo razoavel) antes
# de qualquer decisao de reconciliacao -- se o layout estiver errado, os
# numeros tendem a vir absurdos, e a checagem BARRA a acao em vez de agir
# sobre lixo. Primeira consulta real deve ser so' leitura (sem auto-zerar)
# para validar contra o que aparece no Profit.
# ---------------------------------------------------------------------------
class TConnectorAccountIdentifier(Structure):
    """BrokerID e' Integer (nao string) -- diferente do par (corretora,
    conta) como strings usado nas funcoes de ordem legadas. Converter com
    int(corretora) na hora de preencher."""

    _fields_ = (
        ("version", c_byte),
        ("broker_id", c_int32),
        ("account_id", c_wchar_p),
        ("sub_account_id", c_wchar_p),
        ("reserved", c_int64),
    )


class TConnectorAssetIdentifier(Structure):
    _fields_ = (
        ("version", c_byte),
        ("ticker", c_wchar_p),
        ("exchange", c_wchar_p),
        ("feed_type", c_byte),
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
        ("version", c_byte),
        ("account_id", TConnectorAccountIdentifier),
        ("asset_id", TConnectorAssetIdentifier),
        ("open_quantity", c_int64),
        ("open_average_price", c_double),
        ("open_side", c_byte),               # 0=desconhecida 1=comprada 2=vendida
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
        ("position_type", c_byte),            # ENTRADA (ver docstring)
        ("event_id", c_int64),
    )
