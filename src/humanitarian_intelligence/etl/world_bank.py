import hashlib
import json
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import httpx
from psycopg import Connection
from psycopg.types.json import Jsonb

SOURCE_NAME = "world_bank_indicators"
BASE_URL = "https://api.worldbank.org/v2"


@dataclass(frozen=True)
class IndicatorObservation:
    country_iso3: str
    country_name: str
    indicator_code: str
    indicator_name: str
    observation_year: int
    observation_value: float


def normalize_observations(payload: Any) -> list[IndicatorObservation]:
    if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], list):
        raise ValueError("Unexpected World Bank response shape")

    observations: list[IndicatorObservation] = []
    for row in payload[1]:
        value = row.get("value")
        country_iso3 = row.get("countryiso3code")
        if value is None or not country_iso3:
            continue
        observations.append(
            IndicatorObservation(
                country_iso3=str(country_iso3),
                country_name=str(row["country"]["value"]),
                indicator_code=str(row["indicator"]["id"]),
                indicator_name=str(row["indicator"]["value"]),
                observation_year=int(row["date"]),
                observation_value=float(value),
            )
        )
    return observations


def fetch_indicator(
    client: httpx.Client,
    countries: tuple[str, ...],
    indicator: str,
    start_year: int,
    end_year: int,
) -> tuple[str, dict[str, Any], Any]:
    country_path = ";".join(countries)
    endpoint = f"{BASE_URL}/country/{country_path}/indicator/{indicator}"
    params: dict[str, Any] = {
        "date": f"{start_year}:{end_year}",
        "format": "json",
        "per_page": 20000,
    }
    response = client.get(endpoint, params=params)
    response.raise_for_status()
    return endpoint, params, response.json()


def _payload_hash(payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _store_bronze_response(
    connection: Connection,
    run_id: UUID,
    endpoint: str,
    params: dict[str, Any],
    payload: Any,
) -> int:
    result = connection.execute(
        """
        INSERT INTO bronze.api_responses (
            run_id, source_name, endpoint, request_params, payload, payload_sha256
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (source_name, payload_sha256)
        DO UPDATE SET endpoint = EXCLUDED.endpoint
        RETURNING response_id
        """,
        (run_id, SOURCE_NAME, endpoint, Jsonb(params), Jsonb(payload), _payload_hash(payload)),
    ).fetchone()
    if result is None:
        raise RuntimeError("Bronze response could not be stored")
    return int(result[0])


def _upsert_silver(
    connection: Connection,
    source_response_id: int,
    observations: list[IndicatorObservation],
) -> int:
    for item in observations:
        connection.execute(
            """
            INSERT INTO silver.country_indicators (
                country_iso3, country_name, indicator_code, indicator_name,
                observation_year, observation_value, source_name, source_response_id,
                unit, sex_code, sex_name
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (
                country_iso3, indicator_code, observation_year, source_name, sex_code
            )
            DO UPDATE SET
                country_name = EXCLUDED.country_name,
                indicator_name = EXCLUDED.indicator_name,
                observation_value = EXCLUDED.observation_value,
                source_response_id = EXCLUDED.source_response_id,
                loaded_at = NOW()
            """,
            (
                item.country_iso3,
                item.country_name,
                item.indicator_code,
                item.indicator_name,
                item.observation_year,
                item.observation_value,
                SOURCE_NAME,
                source_response_id,
                None,
                "ALL",
                "All",
            ),
        )
    return len(observations)


def _refresh_gold(connection: Connection) -> None:
    connection.execute(
        """
        INSERT INTO gold.country_indicator_summary (
            country_iso3, country_name, indicator_code, indicator_name,
            first_year, first_value, latest_year, latest_value,
            absolute_change, percent_change, source_name, unit, sex_code, sex_name
        )
        WITH ranked AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY country_iso3, indicator_code, source_name, sex_code
                       ORDER BY observation_year ASC
                   ) AS first_rank,
                   ROW_NUMBER() OVER (
                       PARTITION BY country_iso3, indicator_code, source_name, sex_code
                       ORDER BY observation_year DESC
                   ) AS latest_rank
            FROM silver.country_indicators
            WHERE source_name = %s
        ),
        paired AS (
            SELECT
                country_iso3,
                MAX(country_name) AS country_name,
                indicator_code,
                MAX(indicator_name) AS indicator_name,
                source_name,
                MAX(unit) AS unit,
                sex_code,
                MAX(sex_name) AS sex_name,
                MAX(observation_year) FILTER (WHERE first_rank = 1) AS first_year,
                MAX(observation_value) FILTER (WHERE first_rank = 1) AS first_value,
                MAX(observation_year) FILTER (WHERE latest_rank = 1) AS latest_year,
                MAX(observation_value) FILTER (WHERE latest_rank = 1) AS latest_value
            FROM ranked
            GROUP BY country_iso3, indicator_code, source_name, sex_code
        )
        SELECT
            country_iso3, country_name, indicator_code, indicator_name,
            first_year, first_value, latest_year, latest_value,
            latest_value - first_value,
            CASE WHEN first_value = 0 THEN NULL
                 ELSE ((latest_value - first_value) / ABS(first_value)) * 100
            END,
            source_name, unit, sex_code, sex_name
        FROM paired
        ON CONFLICT (country_iso3, indicator_code, source_name, sex_code)
        DO UPDATE SET
            country_name = EXCLUDED.country_name,
            indicator_name = EXCLUDED.indicator_name,
            first_year = EXCLUDED.first_year,
            first_value = EXCLUDED.first_value,
            latest_year = EXCLUDED.latest_year,
            latest_value = EXCLUDED.latest_value,
            absolute_change = EXCLUDED.absolute_change,
            percent_change = EXCLUDED.percent_change,
            refreshed_at = NOW()
        """,
        (SOURCE_NAME,),
    )


def run_pipeline(
    connection: Connection,
    countries: tuple[str, ...],
    indicators: tuple[str, ...],
    start_year: int,
    end_year: int,
    timeout_seconds: float,
) -> UUID:
    run_id = uuid4()
    connection.execute(
        "INSERT INTO meta.pipeline_runs (run_id, pipeline_name, status) VALUES (%s, %s, 'running')",
        (run_id, SOURCE_NAME),
    )
    connection.commit()

    extracted = 0
    loaded = 0
    try:
        with httpx.Client(
            timeout=timeout_seconds,
            verify=ssl.create_default_context(),
        ) as client:
            for indicator in indicators:
                endpoint, params, payload = fetch_indicator(
                    client, countries, indicator, start_year, end_year
                )
                observations = normalize_observations(payload)
                extracted += len(observations)
                response_id = _store_bronze_response(
                    connection, run_id, endpoint, params, payload
                )
                loaded += _upsert_silver(connection, response_id, observations)

        _refresh_gold(connection)
        connection.execute(
            """
            UPDATE meta.pipeline_runs
            SET status = 'succeeded', finished_at = %s,
                rows_extracted = %s, rows_loaded = %s
            WHERE run_id = %s
            """,
            (datetime.now(UTC), extracted, loaded, run_id),
        )
        connection.commit()
        return run_id
    except Exception as exc:
        connection.rollback()
        connection.execute(
            """
            UPDATE meta.pipeline_runs
            SET status = 'failed', finished_at = %s, error_message = %s,
                rows_extracted = %s, rows_loaded = %s
            WHERE run_id = %s
            """,
            (datetime.now(UTC), str(exc)[:2000], extracted, loaded, run_id),
        )
        connection.commit()
        raise

