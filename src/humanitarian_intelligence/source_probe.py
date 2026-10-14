import argparse
import csv
import io
import ssl
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

UNICEF_DATA_URL = (
    "https://sdmx.data.unicef.org/ws/public/sdmxapi/rest/data/"
    "UNICEF,EDUCATION_FLS,1.0/{country_query}..?"
)
WORLD_BANK_DATA_URL = (
    "https://api.worldbank.org/v2/country/{country_query}/indicator/{indicator}"
)

DEFAULT_COUNTRIES = (
    "ARG",
    "AUS",
    "BRA",
    "DEU",
    "FRA",
    "GBR",
    "ITA",
    "JPN",
    "KOR",
    "MEX",
    "RUS",
    "SAU",
    "TUR",
    "USA",
    "ZAF",
    "JOR",
    "KEN",
)
COUNTRY_NAMES = {
    "ARG": "Argentina",
    "AUS": "Australia",
    "BRA": "Brazil",
    "DEU": "Germany",
    "FRA": "France",
    "GBR": "United Kingdom",
    "ITA": "Italy",
    "JPN": "Japan",
    "JOR": "Jordan",
    "KEN": "Kenya",
    "KOR": "Korea, Rep.",
    "MEX": "Mexico",
    "RUS": "Russian Federation",
    "SAU": "Saudi Arabia",
    "TUR": "Turkiye",
    "USA": "United States",
    "ZAF": "South Africa",
}
DEFAULT_START_YEAR = 2018
DEFAULT_END_YEAR = 2026
WORLD_BANK_CANDIDATES = {
    "SE.PRM.ENRR": "School enrollment, primary (% gross)",
    "SE.SEC.ENRR": "School enrollment, secondary (% gross)",
    "SE.XPD.TOTL.GD.ZS": "Government expenditure on education (% of GDP)",
    "IT.NET.USER.ZS": "Individuals using the Internet (% of population)",
    "SP.POP.TOTL": "Population, total",
}


@dataclass(frozen=True)
class Observation:
    source: str
    country_code: str
    country_name: str
    indicator_code: str
    indicator_name: str
    year: int
    value: float
    unit: str | None
    sex_code: str | None = None
    sex_name: str | None = None


@dataclass(frozen=True)
class SeriesProfile:
    source: str
    country_code: str
    country_name: str
    indicator_code: str
    indicator_name: str
    unit: str | None
    sex_values: tuple[str, ...]
    observed_years: tuple[int, ...]
    years_without_observation: tuple[int, ...]
    observation_count: int


@dataclass(frozen=True)
class ExpectedSeries:
    source: str
    country_code: str
    country_name: str
    indicator_code: str
    indicator_name: str


def _csv_rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def parse_unicef_rows(code_csv: str, label_csv: str) -> list[Observation]:
    coded = _csv_rows(code_csv)
    labelled = _csv_rows(label_csv)
    if len(coded) != len(labelled):
        raise ValueError("UNICEF code and label responses contain different row counts")

    observations: list[Observation] = []
    for code_row, label_row in zip(coded, labelled, strict=True):
        if code_row["TIME_PERIOD"] != label_row["TIME_PERIOD"]:
            raise ValueError("UNICEF code and label responses are not aligned by year")
        if code_row["OBS_VALUE"] != label_row["OBS_VALUE"]:
            raise ValueError("UNICEF code and label responses are not aligned by value")
        observations.append(
            Observation(
                source="UNICEF Data Warehouse",
                country_code=code_row["REF_AREA"],
                country_name=label_row["Geographic area"],
                indicator_code=code_row["INDICATOR"],
                indicator_name=label_row["Indicator"],
                year=int(code_row["TIME_PERIOD"]),
                value=float(code_row["OBS_VALUE"]),
                unit=label_row.get("Unit of measure") or code_row.get("UNIT_MEASURE"),
                sex_code=code_row.get("SEX"),
                sex_name=label_row.get("Sex"),
            )
        )
    return observations


def parse_world_bank_payload(payload: Any) -> list[Observation]:
    if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], list):
        raise ValueError("Unexpected World Bank response shape")

    observations: list[Observation] = []
    for row in payload[1]:
        if row.get("value") is None or not row.get("countryiso3code"):
            continue
        observations.append(
            Observation(
                source="World Bank Indicators",
                country_code=str(row["countryiso3code"]),
                country_name=str(row["country"]["value"]),
                indicator_code=str(row["indicator"]["id"]),
                indicator_name=str(row["indicator"]["value"]),
                year=int(row["date"]),
                value=float(row["value"]),
                unit=None,
            )
        )
    return observations


def fetch_unicef(
    client: httpx.Client,
    countries: tuple[str, ...],
    start_year: int,
    end_year: int,
) -> list[Observation]:
    endpoint = UNICEF_DATA_URL.format(country_query="+".join(countries))
    common_params = {"startPeriod": start_year, "endPeriod": end_year}

    code_response = client.get(endpoint, params={**common_params, "format": "csvfile"})
    code_response.raise_for_status()
    label_response = client.get(
        endpoint,
        params={**common_params, "format": "csv", "labels": "name"},
    )
    label_response.raise_for_status()
    return parse_unicef_rows(code_response.text, label_response.text)


def fetch_world_bank(
    client: httpx.Client,
    countries: tuple[str, ...],
    indicators: tuple[str, ...],
    start_year: int,
    end_year: int,
) -> list[Observation]:
    observations: list[Observation] = []
    country_query = ";".join(countries)
    for indicator in indicators:
        endpoint = WORLD_BANK_DATA_URL.format(
            country_query=country_query,
            indicator=indicator,
        )
        response = client.get(
            endpoint,
            params={
                "date": f"{start_year}:{end_year}",
                "format": "json",
                "per_page": 20000,
            },
        )
        response.raise_for_status()
        observations.extend(parse_world_bank_payload(response.json()))
    return observations


def build_profiles(
    observations: list[Observation],
    start_year: int,
    end_year: int,
    expected_series: tuple[ExpectedSeries, ...] = (),
) -> list[SeriesProfile]:
    grouped: dict[tuple[str, str, str], list[Observation]] = defaultdict(list)
    metadata: dict[tuple[str, str, str], tuple[str, str]] = {}
    for observation in observations:
        key = (observation.source, observation.country_code, observation.indicator_code)
        grouped[key].append(observation)
        metadata[key] = (observation.country_name, observation.indicator_name)
    for expected in expected_series:
        key = (expected.source, expected.country_code, expected.indicator_code)
        metadata[key] = (expected.country_name, expected.indicator_name)

    expected_years = set(range(start_year, end_year + 1))
    profiles: list[SeriesProfile] = []
    for key, names in metadata.items():
        source, country_code, indicator_code = key
        country_name, indicator_name = names
        rows = grouped.get(key, [])
        observed_years = {row.year for row in rows}
        profiles.append(
            SeriesProfile(
                source=source,
                country_code=country_code,
                country_name=country_name,
                indicator_code=indicator_code,
                indicator_name=indicator_name,
                unit=next((row.unit for row in rows if row.unit), None),
                sex_values=tuple(
                    sorted({row.sex_name for row in rows if row.sex_name})
                ),
                observed_years=tuple(sorted(observed_years)),
                years_without_observation=tuple(sorted(expected_years - observed_years)),
                observation_count=len(rows),
            )
        )
    return sorted(
        profiles,
        key=lambda item: (item.source, item.indicator_code, item.country_code),
    )


def render_markdown(
    profiles: list[SeriesProfile],
    generated_at: datetime,
    start_year: int,
    end_year: int,
) -> str:
    sources = sorted({profile.source for profile in profiles})
    lines = [
        "# Phase 1 Data Source Feasibility Report",
        "",
        f"Generated at: {generated_at.astimezone(UTC).isoformat(timespec='seconds')}",
        f"Requested window: {start_year}–{end_year}",
        "",
        "This report profiles public API observations for the 17-country Phase 1 cohort. A year",
        "without an observation is not automatically a data-quality error: survey-based",
        "indicators are not necessarily produced annually.",
        "",
        "## Summary",
        "",
        "| Source | Series profiles | Observations |",
        "| --- | ---: | ---: |",
    ]
    for source in sources:
        source_profiles = [profile for profile in profiles if profile.source == source]
        lines.append(
            f"| {source} | {len(source_profiles)} | "
            f"{sum(profile.observation_count for profile in source_profiles)} |"
        )

    lines.extend(["", "## Series coverage", ""])
    for source in sources:
        lines.extend(
            [
                f"### {source}",
                "",
                (
                    "| Country | Indicator | Unit | Sex values | Observed years | "
                    "Years without observation | Rows |"
                ),
                "| --- | --- | --- | --- | --- | --- | ---: |",
            ]
        )
        for profile in (item for item in profiles if item.source == source):
            observed = ", ".join(map(str, profile.observed_years)) or "None"
            absent = ", ".join(map(str, profile.years_without_observation)) or "None"
            sex_values = ", ".join(profile.sex_values) or "Not provided"
            unit = profile.unit or "See source metadata"
            lines.append(
                f"| {profile.country_name} (`{profile.country_code}`) | "
                f"{profile.indicator_name} (`{profile.indicator_code}`) | {unit} | "
                f"{sex_values} | {observed} | {absent} | {profile.observation_count} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Initial assessment",
            "",
            "- UNICEF provides child-specific learning indicators and sex disaggregation, but the",
            "  selected survey-derived series are not annual.",
            "- World Bank provides broader and generally more continuous country context, although",
            "  availability differs by indicator and country.",
            "- The production data model must preserve source-specific dimensions while exposing a",
            "  shared country/indicator/year/value contract for comparison.",
            "- Indicator selection should be finalized only after reviewing this coverage table.",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Profile Phase 1 public data sources")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/data_source_feasibility.md"),
    )
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.start_year > args.end_year:
        raise SystemExit("--start-year must be less than or equal to --end-year")

    with httpx.Client(
        timeout=40,
        follow_redirects=True,
        verify=ssl.create_default_context(),
    ) as client:
        observations = fetch_unicef(
            client,
            DEFAULT_COUNTRIES,
            args.start_year,
            args.end_year,
        )
        observations.extend(
            fetch_world_bank(
                client,
                DEFAULT_COUNTRIES,
                tuple(WORLD_BANK_CANDIDATES),
                args.start_year,
                args.end_year,
            )
        )

    expected_world_bank_series = tuple(
        ExpectedSeries(
            source="World Bank Indicators",
            country_code=country_code,
            country_name=COUNTRY_NAMES[country_code],
            indicator_code=indicator_code,
            indicator_name=indicator_name,
        )
        for country_code in DEFAULT_COUNTRIES
        for indicator_code, indicator_name in WORLD_BANK_CANDIDATES.items()
    )
    profiles = build_profiles(
        observations,
        args.start_year,
        args.end_year,
        expected_series=expected_world_bank_series,
    )
    report = render_markdown(profiles, datetime.now(UTC), args.start_year, args.end_year)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"Wrote {args.output} from {len(observations)} observations.")


if __name__ == "__main__":
    main()
