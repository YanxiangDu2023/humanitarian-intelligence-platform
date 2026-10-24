from collections.abc import Iterator
from datetime import UTC, datetime
from hashlib import sha256
from secrets import compare_digest
from typing import Annotated

import psycopg
import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from psycopg import Connection
from psycopg.rows import dict_row
from pydantic import BaseModel

from humanitarian_intelligence.ai import (
    CountryBriefGenerationError,
    CountryBriefResponse,
    OpenAICountryBriefGenerator,
    ground_country_brief,
)
from humanitarian_intelligence.config import get_settings


class HealthResponse(BaseModel):
    status: str
    database: str


class CountryResponse(BaseModel):
    country_iso3: str
    country_name: str


class IndicatorResponse(BaseModel):
    indicator_code: str
    indicator_name: str
    unit: str | None
    source_name: str


class ComparisonResponse(CountryResponse, IndicatorResponse):
    observation_value: float
    observation_year: int
    data_age_years: int
    freshness_status: str


class TrendResponse(CountryResponse, IndicatorResponse):
    observation_value: float
    observation_year: int


class AnalysisIndicator(IndicatorResponse):
    latest_value: float
    latest_year: int
    first_value: float
    first_year: int
    absolute_change: float
    percent_change: float | None
    data_age_years: int
    freshness_status: str
    observation_count: int
    available_years: list[int]
    value_rank_descending: int
    cohort_size: int
    cohort_median_value: float
    difference_from_cohort_median: float


class AnalysisDataGap(BaseModel):
    indicator_code: str
    issue: str
    detail: str


class CountryAnalysisResponse(CountryResponse):
    indicators: list[AnalysisIndicator]
    data_gaps: list[AnalysisDataGap]
    methodology_notes: list[str]


class CountryBriefRequest(BaseModel):
    country_iso3: str


EXPECTED_INDICATOR_CODES = {
    "ED_SE_LPV_PRIM",
    "ED_SE_LPV_PRIM_LD",
    "ED_SE_LPV_PRIM_SD",
    "SE.PRM.ENRR",
    "SE.SEC.ENRR",
    "SE.XPD.TOTL.GD.ZS",
    "IT.NET.USER.ZS",
    "SP.POP.TOTL",
}


app = FastAPI(
    title="Humanitarian Intelligence API",
    description="Traceable country-indicator comparisons from public data sources.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(get_settings().allowed_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def get_connection() -> Iterator[Connection]:
    settings = get_settings()
    with psycopg.connect(settings.resolved_database_url, row_factory=dict_row) as connection:
        yield connection


DatabaseConnection = Annotated[Connection, Depends(get_connection)]


def get_country_brief_generator() -> OpenAICountryBriefGenerator:
    try:
        return OpenAICountryBriefGenerator(get_settings())
    except CountryBriefGenerationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


CountryBriefGenerator = Annotated[
    OpenAICountryBriefGenerator, Depends(get_country_brief_generator)
]


def require_ai_generation_key(
    x_admin_key: Annotated[str | None, Header()] = None,
) -> None:
    configured_key = get_settings().ai_generation_key
    if configured_key is None:
        return
    if x_admin_key is None or not compare_digest(
        x_admin_key,
        configured_key.get_secret_value(),
    ):
        raise HTTPException(status_code=403, detail="AI generation is restricted")


AIGenerationAccess = Annotated[None, Depends(require_ai_generation_key)]


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health(connection: DatabaseConnection) -> HealthResponse:
    row = connection.execute("SELECT current_database() AS database").fetchone()
    return HealthResponse(status="ok", database=row["database"])


@app.get("/api/v1/countries", response_model=list[CountryResponse], tags=["catalogue"])
def list_countries(connection: DatabaseConnection) -> list[CountryResponse]:
    rows = connection.execute(
        """
        SELECT DISTINCT country_iso3, country_name
        FROM gold.country_comparison
        ORDER BY country_name
        """
    ).fetchall()
    return [CountryResponse.model_validate(row) for row in rows]


@app.get("/api/v1/indicators", response_model=list[IndicatorResponse], tags=["catalogue"])
def list_indicators(connection: DatabaseConnection) -> list[IndicatorResponse]:
    rows = connection.execute(
        """
        SELECT DISTINCT indicator_code, indicator_name, unit, source_name
        FROM gold.country_comparison
        ORDER BY indicator_name
        """
    ).fetchall()
    return [IndicatorResponse.model_validate(row) for row in rows]


@app.get(
    "/api/v1/comparisons/{indicator_code}",
    response_model=list[ComparisonResponse],
    tags=["comparisons"],
)
def compare_countries(
    indicator_code: str,
    connection: DatabaseConnection,
    country: Annotated[list[str] | None, Query(description="Optional ISO3 country filter")] = None,
) -> list[ComparisonResponse]:
    normalized_indicator = indicator_code.upper()
    parameters: list[object] = [normalized_indicator]
    country_filter = ""

    if country:
        normalized_countries = [code.upper() for code in country]
        country_filter = "AND country_iso3 = ANY(%s)"
        parameters.append(normalized_countries)

    rows = connection.execute(
        f"""
        SELECT
            country_iso3,
            country_name,
            indicator_code,
            indicator_name,
            observation_value,
            observation_year,
            unit,
            source_name,
            data_age_years,
            freshness_status
        FROM gold.country_comparison
        WHERE indicator_code = %s
          {country_filter}
        ORDER BY observation_value DESC, country_name
        """,
        parameters,
    ).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="No comparison data found")
    return [ComparisonResponse.model_validate(row) for row in rows]


@app.get(
    "/api/v1/countries/{country_iso3}/indicators",
    response_model=list[ComparisonResponse],
    tags=["comparisons"],
)
def get_country_indicators(
    country_iso3: str,
    connection: DatabaseConnection,
) -> list[ComparisonResponse]:
    rows = connection.execute(
        """
        SELECT
            country_iso3,
            country_name,
            indicator_code,
            indicator_name,
            observation_value,
            observation_year,
            unit,
            source_name,
            data_age_years,
            freshness_status
        FROM gold.country_comparison
        WHERE country_iso3 = %s
        ORDER BY indicator_name
        """,
        (country_iso3.upper(),),
    ).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="Country not found")
    return [ComparisonResponse.model_validate(row) for row in rows]


@app.get(
    "/api/v1/analysis/countries/{country_iso3}",
    response_model=CountryAnalysisResponse,
    tags=["analysis"],
)
def get_country_analysis(
    country_iso3: str,
    connection: DatabaseConnection,
) -> CountryAnalysisResponse:
    normalized_country = country_iso3.upper()
    if len(normalized_country) != 3 or not normalized_country.isalpha():
        raise HTTPException(status_code=422, detail="Country must use a three-letter ISO3 code")

    rows = connection.execute(
        """
        WITH ranked AS (
            SELECT
                comparison.*,
                RANK() OVER (
                    PARTITION BY comparison.indicator_code
                    ORDER BY comparison.observation_value DESC
                ) AS value_rank_descending,
                COUNT(*) OVER (
                    PARTITION BY comparison.indicator_code
                ) AS cohort_size
            FROM gold.country_comparison AS comparison
        ),
        cohort_stats AS (
            SELECT
                indicator_code,
                PERCENTILE_CONT(0.5) WITHIN GROUP (
                    ORDER BY observation_value
                ) AS cohort_median_value
            FROM gold.country_comparison
            GROUP BY indicator_code
        ),
        series AS (
            SELECT
                country_iso3,
                indicator_code,
                source_name,
                COUNT(*) AS observation_count,
                ARRAY_AGG(observation_year ORDER BY observation_year) AS available_years
            FROM silver.country_indicators
            WHERE
                (source_name = 'world_bank_indicators' AND sex_code = 'ALL')
                OR (source_name = 'unicef_education_fls' AND sex_code = '_T')
            GROUP BY country_iso3, indicator_code, source_name
        )
        SELECT
            ranked.country_iso3,
            ranked.country_name,
            ranked.indicator_code,
            ranked.indicator_name,
            ranked.observation_value AS latest_value,
            ranked.observation_year AS latest_year,
            ranked.unit,
            ranked.source_name,
            ranked.data_age_years,
            ranked.freshness_status,
            summary.first_value,
            summary.first_year,
            summary.absolute_change,
            summary.percent_change,
            series.observation_count,
            series.available_years,
            ranked.value_rank_descending,
            ranked.cohort_size,
            cohort_stats.cohort_median_value,
            ranked.observation_value - cohort_stats.cohort_median_value
                AS difference_from_cohort_median
        FROM ranked
        INNER JOIN gold.country_indicator_summary AS summary
            ON summary.country_iso3 = ranked.country_iso3
            AND summary.indicator_code = ranked.indicator_code
            AND summary.source_name = ranked.source_name
            AND summary.sex_code = ranked.sex_code
        INNER JOIN series
            ON series.country_iso3 = ranked.country_iso3
            AND series.indicator_code = ranked.indicator_code
            AND series.source_name = ranked.source_name
        INNER JOIN cohort_stats
            ON cohort_stats.indicator_code = ranked.indicator_code
        WHERE ranked.country_iso3 = %s
        ORDER BY ranked.indicator_name
        """,
        (normalized_country,),
    ).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="Country not found")

    present_codes = {str(row["indicator_code"]) for row in rows}
    data_gaps = [
        AnalysisDataGap(
            indicator_code=indicator_code,
            issue="missing_indicator",
            detail="No observation is available for this country and indicator.",
        )
        for indicator_code in sorted(EXPECTED_INDICATOR_CODES - present_codes)
    ]
    for row in rows:
        if int(row["observation_count"]) == 1:
            data_gaps.append(
                AnalysisDataGap(
                    indicator_code=str(row["indicator_code"]),
                    issue="single_observation",
                    detail=(
                        f"Only one observation is available, for {row['latest_year']}; "
                        "a historical trend cannot be inferred."
                    ),
                )
            )

    return CountryAnalysisResponse(
        country_iso3=str(rows[0]["country_iso3"]),
        country_name=str(rows[0]["country_name"]),
        indicators=[AnalysisIndicator.model_validate(row) for row in rows],
        data_gaps=data_gaps,
        methodology_notes=[
            "Ranks order raw indicator values from highest to lowest; a higher value is not always better.",
            "Comparisons preserve each country's latest available year, which may differ across countries.",
            "UNICEF learning indicators are survey snapshots and must not be interpreted as annual series.",
        ],
    )


@app.post(
    "/api/v1/ai/country-brief",
    response_model=CountryBriefResponse,
    tags=["ai"],
)
def create_country_brief(
    request: CountryBriefRequest,
    connection: DatabaseConnection,
    generator: CountryBriefGenerator,
    _access: AIGenerationAccess,
) -> CountryBriefResponse:
    analysis = get_country_analysis(request.country_iso3, connection)
    try:
        draft = generator.generate(analysis.model_dump_json())
        generated_at = datetime.now(UTC)
        brief = ground_country_brief(
            draft,
            country_iso3=analysis.country_iso3,
            country_name=analysis.country_name,
            model=generator.model,
            indicators=list(analysis.indicators),
            data_gaps=list(analysis.data_gaps),
            methodology_notes=analysis.methodology_notes,
        )
        brief.generated_at = generated_at
        evidence_sha256 = sha256(analysis.model_dump_json().encode("utf-8")).hexdigest()
        connection.execute(
            """
            INSERT INTO gold.ai_country_briefs (
                country_iso3,
                country_name,
                model,
                evidence_sha256,
                brief,
                generated_at
            )
            VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            """,
            (
                brief.country_iso3,
                brief.country_name,
                brief.model,
                evidence_sha256,
                brief.model_dump_json(exclude={"cached"}),
                generated_at,
            ),
        )
        return brief
    except CountryBriefGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get(
    "/api/v1/ai/country-brief/{country_iso3}",
    response_model=CountryBriefResponse,
    tags=["ai"],
)
def get_latest_country_brief(
    country_iso3: str,
    connection: DatabaseConnection,
) -> CountryBriefResponse:
    normalized_country = country_iso3.upper()
    if len(normalized_country) != 3 or not normalized_country.isalpha():
        raise HTTPException(status_code=422, detail="Country must use a three-letter ISO3 code")

    row = connection.execute(
        """
        SELECT brief, generated_at
        FROM gold.ai_country_briefs
        WHERE country_iso3 = %s
        ORDER BY generated_at DESC
        LIMIT 1
        """,
        (normalized_country,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="No saved AI brief found")

    brief = CountryBriefResponse.model_validate(row["brief"])
    brief.generated_at = row["generated_at"]
    brief.cached = True
    return brief


@app.get(
    "/api/v1/trends/{indicator_code}",
    response_model=list[TrendResponse],
    tags=["trends"],
)
def get_indicator_trends(
    indicator_code: str,
    connection: DatabaseConnection,
    country: Annotated[
        list[str],
        Query(min_length=1, max_length=3, description="One to three ISO3 country codes"),
    ],
    start_year: Annotated[int | None, Query(ge=1900, le=2100)] = None,
    end_year: Annotated[int | None, Query(ge=1900, le=2100)] = None,
) -> list[TrendResponse]:
    if start_year is not None and end_year is not None and start_year > end_year:
        raise HTTPException(status_code=422, detail="start_year must not be after end_year")

    normalized_countries = list(dict.fromkeys(code.upper() for code in country))
    if any(len(code) != 3 or not code.isalpha() for code in normalized_countries):
        raise HTTPException(status_code=422, detail="Countries must use three-letter ISO3 codes")

    parameters: list[object] = [indicator_code.upper(), normalized_countries]
    year_filters = ""
    if start_year is not None:
        year_filters += "AND indicators.observation_year >= %s"
        parameters.append(start_year)
    if end_year is not None:
        year_filters += " AND indicators.observation_year <= %s"
        parameters.append(end_year)

    rows = connection.execute(
        f"""
        WITH canonical_countries AS (
            SELECT
                country_iso3,
                COALESCE(
                    MAX(country_name) FILTER (
                        WHERE source_name = 'world_bank_indicators'
                    ),
                    MAX(country_name)
                ) AS country_name
            FROM silver.country_indicators
            GROUP BY country_iso3
        )
        SELECT
            indicators.country_iso3,
            canonical_countries.country_name,
            indicators.indicator_code,
            indicators.indicator_name,
            indicators.observation_value,
            indicators.observation_year,
            COALESCE(
                indicators.unit,
                CASE
                    WHEN indicators.indicator_code = 'SP.POP.TOTL' THEN 'people'
                    WHEN indicators.indicator_code IN (
                        'SE.PRM.ENRR',
                        'SE.SEC.ENRR',
                        'SE.XPD.TOTL.GD.ZS',
                        'IT.NET.USER.ZS'
                    ) THEN CHR(37)
                END
            ) AS unit,
            indicators.source_name
        FROM silver.country_indicators AS indicators
        INNER JOIN canonical_countries
            ON canonical_countries.country_iso3 = indicators.country_iso3
        WHERE indicators.indicator_code = %s
          AND indicators.country_iso3 = ANY(%s)
          AND (
              (indicators.source_name = 'world_bank_indicators'
                  AND indicators.sex_code = 'ALL')
              OR (indicators.source_name = 'unicef_education_fls'
                  AND indicators.sex_code = '_T')
          )
          {year_filters}
        ORDER BY indicators.country_iso3, indicators.observation_year
        """,
        parameters,
    ).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="No trend data found")
    return [TrendResponse.model_validate(row) for row in rows]


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "humanitarian_intelligence.api:app",
        host=settings.api_host,
        port=settings.api_port,
    )
