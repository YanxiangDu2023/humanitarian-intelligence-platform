CREATE SCHEMA IF NOT EXISTS meta;
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

CREATE TABLE IF NOT EXISTS meta.pipeline_runs (
    run_id UUID PRIMARY KEY,
    pipeline_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    rows_extracted INTEGER NOT NULL DEFAULT 0,
    rows_loaded INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS bronze.api_responses (
    response_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES meta.pipeline_runs(run_id),
    source_name TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    request_params JSONB NOT NULL,
    payload JSONB NOT NULL,
    payload_sha256 TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_name, payload_sha256)
);

CREATE TABLE IF NOT EXISTS silver.country_indicators (
    country_iso3 CHAR(3) NOT NULL,
    country_name TEXT NOT NULL,
    indicator_code TEXT NOT NULL,
    indicator_name TEXT NOT NULL,
    observation_year INTEGER NOT NULL CHECK (observation_year BETWEEN 1900 AND 2100),
    observation_value DOUBLE PRECISION NOT NULL,
    source_name TEXT NOT NULL,
    source_response_id BIGINT NOT NULL REFERENCES bronze.api_responses(response_id),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (country_iso3, indicator_code, observation_year, source_name)
);

CREATE TABLE IF NOT EXISTS gold.country_indicator_summary (
    country_iso3 CHAR(3) NOT NULL,
    country_name TEXT NOT NULL,
    indicator_code TEXT NOT NULL,
    indicator_name TEXT NOT NULL,
    first_year INTEGER NOT NULL,
    first_value DOUBLE PRECISION NOT NULL,
    latest_year INTEGER NOT NULL,
    latest_value DOUBLE PRECISION NOT NULL,
    absolute_change DOUBLE PRECISION NOT NULL,
    percent_change DOUBLE PRECISION,
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (country_iso3, indicator_code)
);

CREATE INDEX IF NOT EXISTS idx_silver_indicators_year
    ON silver.country_indicators (observation_year);

CREATE INDEX IF NOT EXISTS idx_bronze_api_responses_run
    ON bronze.api_responses (run_id);

