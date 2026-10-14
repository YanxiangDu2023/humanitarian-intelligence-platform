ALTER TABLE silver.country_indicators
    ADD COLUMN IF NOT EXISTS unit TEXT,
    ADD COLUMN IF NOT EXISTS sex_code TEXT NOT NULL DEFAULT 'ALL',
    ADD COLUMN IF NOT EXISTS sex_name TEXT;

ALTER TABLE silver.country_indicators
    DROP CONSTRAINT IF EXISTS country_indicators_pkey;

ALTER TABLE silver.country_indicators
    ADD PRIMARY KEY (
        country_iso3, indicator_code, observation_year, source_name, sex_code
    );

ALTER TABLE gold.country_indicator_summary
    ADD COLUMN IF NOT EXISTS source_name TEXT NOT NULL DEFAULT 'world_bank_indicators',
    ADD COLUMN IF NOT EXISTS unit TEXT,
    ADD COLUMN IF NOT EXISTS sex_code TEXT NOT NULL DEFAULT 'ALL',
    ADD COLUMN IF NOT EXISTS sex_name TEXT;

ALTER TABLE gold.country_indicator_summary
    DROP CONSTRAINT IF EXISTS country_indicator_summary_pkey;

ALTER TABLE gold.country_indicator_summary
    ADD PRIMARY KEY (country_iso3, indicator_code, source_name, sex_code);
