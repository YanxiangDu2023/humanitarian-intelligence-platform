CREATE TABLE IF NOT EXISTS gold.ai_country_briefs (
    brief_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    country_iso3 CHAR(3) NOT NULL,
    country_name TEXT NOT NULL,
    model TEXT NOT NULL,
    evidence_sha256 CHAR(64) NOT NULL,
    brief JSONB NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_country_briefs_country_generated
    ON gold.ai_country_briefs (country_iso3, generated_at DESC);
