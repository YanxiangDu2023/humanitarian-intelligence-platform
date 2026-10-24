CREATE SCHEMA IF NOT EXISTS quality;

CREATE OR REPLACE VIEW gold.country_comparison AS
WITH canonical_countries AS (
    SELECT
        country_iso3,
        COALESCE(
            MAX(country_name) FILTER (WHERE source_name = 'world_bank_indicators'),
            MAX(country_name)
        ) AS country_name
    FROM gold.country_indicator_summary
    GROUP BY country_iso3
)
SELECT
    summary.country_iso3,
    canonical_countries.country_name,
    summary.indicator_code,
    summary.indicator_name,
    summary.latest_value AS observation_value,
    summary.latest_year AS observation_year,
    COALESCE(
        summary.unit,
        CASE
            WHEN summary.indicator_code = 'SP.POP.TOTL' THEN 'people'
            WHEN summary.indicator_code IN (
                'SE.PRM.ENRR',
                'SE.SEC.ENRR',
                'SE.XPD.TOTL.GD.ZS',
                'IT.NET.USER.ZS'
            ) THEN '%'
        END
    ) AS unit,
    summary.source_name,
    summary.sex_code,
    COALESCE(
        summary.sex_name,
        CASE WHEN summary.sex_code = 'ALL' THEN 'All' END
    ) AS sex_name,
    EXTRACT(YEAR FROM CURRENT_DATE)::INTEGER - summary.latest_year AS data_age_years,
    CASE
        WHEN summary.source_name = 'unicef_education_fls' THEN 'survey_snapshot'
        WHEN summary.latest_year >= EXTRACT(YEAR FROM CURRENT_DATE)::INTEGER - 2 THEN 'current'
        WHEN summary.latest_year >= EXTRACT(YEAR FROM CURRENT_DATE)::INTEGER - 4 THEN 'aging'
        ELSE 'stale'
    END AS freshness_status
FROM gold.country_indicator_summary AS summary
INNER JOIN canonical_countries
    ON canonical_countries.country_iso3 = summary.country_iso3
WHERE
    (summary.source_name = 'world_bank_indicators' AND summary.sex_code = 'ALL')
    OR (summary.source_name = 'unicef_education_fls' AND summary.sex_code = '_T');

CREATE OR REPLACE VIEW quality.country_indicator_checks AS
WITH countries AS (
    SELECT
        country_iso3,
        COALESCE(
            MAX(country_name) FILTER (WHERE source_name = 'world_bank_indicators'),
            MAX(country_name)
        ) AS country_name
    FROM silver.country_indicators
    GROUP BY country_iso3
),
expected_indicators (source_name, indicator_code) AS (
    VALUES
        ('unicef_education_fls', 'ED_SE_LPV_PRIM'),
        ('unicef_education_fls', 'ED_SE_LPV_PRIM_LD'),
        ('unicef_education_fls', 'ED_SE_LPV_PRIM_SD'),
        ('world_bank_indicators', 'SE.PRM.ENRR'),
        ('world_bank_indicators', 'SE.SEC.ENRR'),
        ('world_bank_indicators', 'SE.XPD.TOTL.GD.ZS'),
        ('world_bank_indicators', 'IT.NET.USER.ZS'),
        ('world_bank_indicators', 'SP.POP.TOTL')
),
expected AS (
    SELECT
        countries.country_iso3,
        countries.country_name,
        expected_indicators.source_name,
        expected_indicators.indicator_code
    FROM countries
    CROSS JOIN expected_indicators
)
SELECT
    expected.country_iso3,
    expected.country_name,
    expected.source_name,
    expected.indicator_code,
    comparison.observation_year,
    comparison.observation_value,
    comparison.unit,
    comparison.freshness_status,
    CASE
        WHEN comparison.indicator_code IS NULL THEN 'missing'
        WHEN expected.indicator_code = 'SP.POP.TOTL'
             AND comparison.observation_value <= 0 THEN 'out_of_range'
        WHEN expected.indicator_code IN (
            'ED_SE_LPV_PRIM',
            'ED_SE_LPV_PRIM_LD',
            'ED_SE_LPV_PRIM_SD',
            'SE.XPD.TOTL.GD.ZS',
            'IT.NET.USER.ZS'
        ) AND comparison.observation_value NOT BETWEEN 0 AND 100 THEN 'out_of_range'
        WHEN expected.indicator_code IN ('SE.PRM.ENRR', 'SE.SEC.ENRR')
             AND comparison.observation_value NOT BETWEEN 0 AND 200 THEN 'out_of_range'
        ELSE 'pass'
    END AS quality_status
FROM expected
LEFT JOIN gold.country_comparison AS comparison
    ON comparison.country_iso3 = expected.country_iso3
    AND comparison.source_name = expected.source_name
    AND comparison.indicator_code = expected.indicator_code;
