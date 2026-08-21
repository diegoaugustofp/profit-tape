-- Schema TimescaleDB para o dado capturado.
--
-- QUANDO USAR ISTO, E QUANDO NAO USAR
-- ------------------------------------
-- Parquet particionado ja resolve backtest e pesquisa: DuckDB le direto, com
-- filtro por particao, sem servidor. Carregar tudo no Postgres NAO e' o padrao
-- — e' opcional, e faz sentido em tres casos:
--   * consulta ad-hoc concorrente por varias ferramentas;
--   * junção com as tabelas de trades/strategies que ja existem no seu schema;
--   * agregacao continua mantida pelo proprio banco.
-- Para varredura sequencial de bilhoes de ticks, o Parquet ganha do Postgres.

CREATE SCHEMA IF NOT EXISTS raw;

-- --------------------------------------------------------------------------
-- Tape
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.trades (
    ts                  TIMESTAMPTZ      NOT NULL,
    ts_recv             TIMESTAMPTZ      NOT NULL,
    symbol              TEXT             NOT NULL,
    exchange            TEXT             NOT NULL,
    trade_id            BIGINT           NOT NULL,
    price               DOUBLE PRECISION NOT NULL,
    volume_financeiro   DOUBLE PRECISION,
    quantidade          BIGINT           NOT NULL,
    agente_comprador    INTEGER,
    agente_vendedor     INTEGER,
    trade_type          SMALLINT         NOT NULL,

    -- Coluna gerada: o sinal do agressor, ja com leilao/RLP/balcao zerados.
    -- Fica no banco de proposito — assim toda consulta usa a MESMA definicao,
    -- em vez de cada notebook reinventar (e divergir) a sua.
    agressao            SMALLINT GENERATED ALWAYS AS (
        CASE trade_type WHEN 2 THEN 1 WHEN 3 THEN -1 ELSE 0 END
    ) STORED,

    latencia_ms         DOUBLE PRECISION GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM (ts_recv - ts)) * 1000
    ) STORED,

    -- Reentrega no reconnect duplica negocio. A chave natural evita isso.
    CONSTRAINT trades_pk PRIMARY KEY (symbol, trade_id, ts)
);

SELECT create_hypertable('raw.trades', 'ts',
                         chunk_time_interval => INTERVAL '1 day',
                         if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS trades_symbol_ts   ON raw.trades (symbol, ts DESC);
-- Indice parcial: consulta de fluxo por corretora quase sempre restringe a
-- agressao continua. Indexar so essas linhas encolhe o indice bastante.
CREATE INDEX IF NOT EXISTS trades_agente_comp ON raw.trades (agente_comprador, ts DESC)
    WHERE trade_type IN (2, 3);
CREATE INDEX IF NOT EXISTS trades_agente_vend ON raw.trades (agente_vendedor, ts DESC)
    WHERE trade_type IN (2, 3);

ALTER TABLE raw.trades SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol',
    timescaledb.compress_orderby   = 'ts DESC'
);
SELECT add_compression_policy('raw.trades', INTERVAL '7 days', if_not_exists => TRUE);

-- --------------------------------------------------------------------------
-- Offer book (deltas)
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.book_offer (
    ts          TIMESTAMPTZ      NOT NULL,
    ts_recv     TIMESTAMPTZ      NOT NULL,
    symbol      TEXT             NOT NULL,
    exchange    TEXT             NOT NULL,
    action      SMALLINT         NOT NULL,
    side        SMALLINT         NOT NULL,
    position    INTEGER,
    offer_id    BIGINT,
    price       DOUBLE PRECISION,
    quantidade  BIGINT,
    agente      INTEGER,
    has_price   BOOLEAN,
    has_qtd     BOOLEAN
);

SELECT create_hypertable('raw.book_offer', 'ts',
                         chunk_time_interval => INTERVAL '1 day',
                         if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS book_offer_symbol_ts ON raw.book_offer (symbol, ts DESC);

ALTER TABLE raw.book_offer SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol',
    timescaledb.compress_orderby   = 'ts DESC'
);
SELECT add_compression_policy('raw.book_offer', INTERVAL '3 days', if_not_exists => TRUE);

-- --------------------------------------------------------------------------
-- Agregacao continua: fluxo agressor por minuto
-- --------------------------------------------------------------------------
-- Primeiro bloco de construcao para OFI. NAO e' o OFI de Cont/Kukanov/Stoikov,
-- que precisa de variacao de FILA no book — este e' o proxy baseado em trades.
-- A distincao importa: chamar os dois de "OFI" e' a fonte de metade da confusao
-- na literatura de varejo sobre o tema.
CREATE MATERIALIZED VIEW IF NOT EXISTS raw.fluxo_1m
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 minute', ts) AS bucket,
    symbol,
    SUM(quantidade * agressao)                             AS delta_qtd,
    SUM(quantidade) FILTER (WHERE agressao <> 0)           AS qtd_continua,
    SUM(quantidade) FILTER (WHERE trade_type = 32)         AS qtd_rlp,
    SUM(quantidade) FILTER (WHERE trade_type = 4)          AS qtd_leilao,
    COUNT(*)                                               AS n_negocios,
    first(price, ts)                                       AS abertura,
    max(price)                                             AS maxima,
    min(price)                                             AS minima,
    last(price, ts)                                        AS fechamento
FROM raw.trades
GROUP BY bucket, symbol
WITH NO DATA;

SELECT add_continuous_aggregate_policy('raw.fluxo_1m',
    start_offset  => INTERVAL '3 days',
    end_offset    => INTERVAL '1 minute',
    schedule_interval => INTERVAL '5 minutes',
    if_not_exists => TRUE);
