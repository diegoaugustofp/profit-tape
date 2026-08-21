"""
Schemas Arrow.

Tipos escolhidos com dois compromissos em mente:

1. Timestamp em int64 nanossegundos, NAO em `timestamp[ns]` do Arrow. Motivo:
   evita conversao implicita de fuso na leitura, que e' a origem classica de
   bug em dado intradiario. Quem le converte explicitamente e sabe o que fez.
2. `symbol` e `exchange` como dictionary. Sao poucos valores distintos
   repetidos milhoes de vezes — dictionary encoding derruba o arquivo em
   ordem de grandeza sem custo de leitura.
"""

from __future__ import annotations

import pyarrow as pa

from .enums import Stream

_SYM = pa.dictionary(pa.int16(), pa.string())

TRADE_SCHEMA = pa.schema(
    [
        pa.field("ts_ns", pa.int64(), nullable=False),
        pa.field("ts_recv_ns", pa.int64(), nullable=False),
        pa.field("symbol", _SYM, nullable=False),
        pa.field("exchange", _SYM, nullable=False),
        pa.field("trade_id", pa.int64()),
        pa.field("price", pa.float64()),
        pa.field("volume_financeiro", pa.float64()),
        pa.field("quantidade", pa.int64()),
        pa.field("agente_comprador", pa.int32()),
        pa.field("agente_vendedor", pa.int32()),
        pa.field("trade_type", pa.int16()),
        pa.field("is_edit", pa.bool_()),
    ]
)

BOOK_OFFER_SCHEMA = pa.schema(
    [
        pa.field("ts_ns", pa.int64(), nullable=False),
        pa.field("ts_recv_ns", pa.int64(), nullable=False),
        pa.field("symbol", _SYM, nullable=False),
        pa.field("exchange", _SYM, nullable=False),
        pa.field("action", pa.int8()),
        pa.field("side", pa.int8()),
        pa.field("position", pa.int32()),
        pa.field("offer_id", pa.int64()),
        pa.field("price", pa.float64()),
        pa.field("quantidade", pa.int64()),
        pa.field("agente", pa.int32()),
        pa.field("has_price", pa.bool_()),
        pa.field("has_qtd", pa.bool_()),
        pa.field("has_date", pa.bool_()),
    ]
)

BOOK_PRICE_SCHEMA = pa.schema(
    [
        pa.field("ts_ns", pa.int64(), nullable=False),
        pa.field("ts_recv_ns", pa.int64(), nullable=False),
        pa.field("symbol", _SYM, nullable=False),
        pa.field("exchange", _SYM, nullable=False),
        pa.field("action", pa.int8()),
        pa.field("side", pa.int8()),
        pa.field("position", pa.int32()),
        pa.field("price", pa.float64()),
        pa.field("quantidade", pa.int64()),
        pa.field("n_ofertas", pa.int32()),
    ]
)

TINY_BOOK_SCHEMA = pa.schema(
    [
        pa.field("ts_recv_ns", pa.int64(), nullable=False),
        pa.field("symbol", _SYM, nullable=False),
        pa.field("exchange", _SYM, nullable=False),
        pa.field("side", pa.int8()),
        pa.field("price", pa.float64()),
        pa.field("quantidade", pa.int64()),
    ]
)

SCHEMAS: dict[Stream, pa.Schema] = {
    Stream.TRADE: TRADE_SCHEMA,
    Stream.BOOK_OFFER: BOOK_OFFER_SCHEMA,
    Stream.BOOK_PRICE: BOOK_PRICE_SCHEMA,
    Stream.TINY_BOOK: TINY_BOOK_SCHEMA,
}


def schema_for(stream: Stream) -> pa.Schema:
    return SCHEMAS[stream]
