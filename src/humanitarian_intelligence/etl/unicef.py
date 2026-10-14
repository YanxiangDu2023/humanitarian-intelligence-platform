import csv
import hashlib
import io
import json
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import httpx
from psycopg import Connection
from psycopg.types.json import Jsonb

SOURCE_NAME = "unicef_education_fls"
DATA_URL = (
    "https://sdmx.data.unicef.org/ws/public/sdmxapi/rest/data/"
    "UNICEF,EDUCATION_FLS,1.0/{country_query}..?"
)


@dataclass(frozen=True)
class UNICEFObservation:
    country_iso3: str
    country_name: str
    indicator_code: str
    indicator_name: str
    observation_year: int
    observation_value: float
    unit: str | None
    sex_code: str
    sex_name: str | None


def _csv_rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def normalize_observations(
    code_csv: str,
    label_csv: str,
    indicators: tuple[str, ...],
) -> list[UNICEFObservation]:
    coded = _csv_rows(code_csv)
    labelled = _csv_rows(label_csv)
    if len(coded) != len(labelled):
        raise ValueError("UNICEF code and label responses contain different row counts")

    selected = set(indicators)
    observations: list[UNICEFObservation] = []
    for code_row, label_row in zip(coded, labelled, strict=True):
        if code_row["TIME_PERIOD"] != label_row["TIME_PERIOD"]:
            raise ValueError("UNICEF code and label responses are not aligned by year")
        if code_row["OBS_VALUE"] != label_row["OBS_VALUE"]:
            raise ValueError("UNICEF code and label responses are not aligned by value")
        if code_row["INDICATOR"] not in selected or not code_row["OBS_VALUE"]:
            continue
        observations.append(
            UNICEFObservation(
                country_iso3=code_row["REF_AREA"],
                country_name=label_row["Geographic area"],
                indicator_code=code_row["INDICATOR"],
                indicator_name=label_row["Indicator"],
                observation_year=int(code_row["TIME_PERIOD"]),
                observation_value=float(code_row["OBS_VALUE"]),
                unit=label_row.get("Unit of measure") or code_row.get("UNIT_MEASURE"),
                sex_code=code_row.get("SEX") or "ALL",
                sex_name=label_row.get("Sex") or None,
            )
        )
    return observations


def fetch_observations(
    client: httpx.Client,
    countries: tuple[str, ...],
    indicators: tuple[str, ...],
    start_year: int,
    end_year: int,
) -> tuple[str, dict[str, Any], dict[str, str], list[UNICEFObservation]]:
    endpoint = DATA_URL.format(country_query="+".join(countries))
    period_params = {"startPeriod": start_year, "endPeriod": end_year}
    code_params = {**period_params, "format": "csvfile"}
    label_params = {**period_params, "format": "csv", "labels": "name"}

    code_response = client.get(endpoint, params=code_params)
    code_response.raise_for_status()
    label_response = client.get(endpoint, params=label_params)
    label_response.raise_for_status()

    payload = {
        "coded_csv": code_response.text,
        "labelled_csv": label_response.text,
    }
    request_params = {
        "countries": list(countries),
        "indicators": list(indicators),
        "coded_request": code_params,
        "labelled_request": label_params,
    }
    observations = normalize_observations(
        code_response.text,
        label_response.text,
        indicators,
    )
    return endpoint, request_params, payload, observations


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
    observations: list[UNICEFObservation],
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
                unit = EXCLUDED.unit,
                sex_name = EXCLUDED.sex_name,
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
                item.unit,
                item.sex_code,
                item.sex_name,
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
            unit = EXCLUDED.unit,
            sex_name = EXCLUDED.sex_name,
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
            follow_redirects=True,
            verify=ssl.create_default_context(),
        ) as client:
            endpoint, params, payload, observations = fetch_observations(
                client,
                countries,
                indicators,
                start_year,
                end_year,
            )
        extracted = len(observations)
        response_id = _store_bronze_response(connection, run_id, endpoint, params, payload)
        loaded = _upsert_silver(connection, response_id, observations)
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
