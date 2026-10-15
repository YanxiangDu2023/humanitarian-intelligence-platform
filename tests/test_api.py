from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from humanitarian_intelligence.ai import BriefFindingDraft, CountryBriefDraft
from humanitarian_intelligence.api import app, get_connection, get_country_brief_generator

COMPARISON_ROW = {
    "country_iso3": "KEN",
    "country_name": "Kenya",
    "indicator_code": "SE.PRM.ENRR",
    "indicator_name": "School enrollment, primary (% gross)",
    "observation_value": 101.5,
    "observation_year": 2023,
    "unit": "%",
    "source_name": "world_bank_indicators",
    "data_age_years": 3,
    "freshness_status": "recent",
}

TREND_ROW = {
    "country_iso3": "KEN",
    "country_name": "Kenya",
    "indicator_code": "IT.NET.USER.ZS",
    "indicator_name": "Individuals using the Internet (% of population)",
    "observation_value": 29.5,
    "observation_year": 2020,
    "unit": "%",
    "source_name": "world_bank_indicators",
}

ANALYSIS_ROW = {
    "country_iso3": "KEN",
    "country_name": "Kenya",
    "indicator_code": "IT.NET.USER.ZS",
    "indicator_name": "Individuals using the Internet (% of population)",
    "latest_value": 35.0,
    "latest_year": 2024,
    "first_value": 19.5,
    "first_year": 2018,
    "absolute_change": 15.5,
    "percent_change": 79.487,
    "unit": "%",
    "source_name": "world_bank_indicators",
    "data_age_years": 2,
    "freshness_status": "current",
    "observation_count": 7,
    "available_years": [2018, 2019, 2020, 2021, 2022, 2023, 2024],
    "value_rank_descending": 15,
    "cohort_size": 17,
    "cohort_median_value": 89.0,
    "difference_from_cohort_median": -54.0,
}


def client_with_rows(rows: list[dict[str, object]]) -> TestClient:
    connection = MagicMock()
    connection.execute.return_value.fetchall.return_value = rows

    def override_connection() -> Iterator[MagicMock]:
        yield connection

    app.dependency_overrides[get_connection] = override_connection
    return TestClient(app)


def test_lists_countries() -> None:
    client = client_with_rows([{"country_iso3": "KEN", "country_name": "Kenya"}])

    response = client.get("/api/v1/countries")

    assert response.status_code == 200
    assert response.json() == [{"country_iso3": "KEN", "country_name": "Kenya"}]
    app.dependency_overrides.clear()


def test_compares_an_indicator() -> None:
    client = client_with_rows([COMPARISON_ROW])

    response = client.get("/api/v1/comparisons/SE.PRM.ENRR?country=ken")

    assert response.status_code == 200
    assert response.json()[0]["observation_value"] == 101.5
    app.dependency_overrides.clear()


def test_missing_comparison_returns_404() -> None:
    client = client_with_rows([])

    response = client.get("/api/v1/comparisons/UNKNOWN")

    assert response.status_code == 404
    assert response.json() == {"detail": "No comparison data found"}
    app.dependency_overrides.clear()


def test_returns_historical_trends() -> None:
    client = client_with_rows([TREND_ROW])

    response = client.get(
        "/api/v1/trends/IT.NET.USER.ZS?country=ken&country=jor&start_year=2018&end_year=2025"
    )

    assert response.status_code == 200
    assert response.json() == [TREND_ROW]
    app.dependency_overrides.clear()


def test_trends_reject_more_than_three_countries() -> None:
    client = client_with_rows([TREND_ROW])

    response = client.get(
        "/api/v1/trends/IT.NET.USER.ZS?country=KEN&country=JOR&country=ZAF&country=USA"
    )

    assert response.status_code == 422
    app.dependency_overrides.clear()


def test_trends_reject_reverse_year_range() -> None:
    client = client_with_rows([TREND_ROW])

    response = client.get(
        "/api/v1/trends/IT.NET.USER.ZS?country=KEN&start_year=2025&end_year=2018"
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "start_year must not be after end_year"}
    app.dependency_overrides.clear()


def test_returns_country_analysis_package() -> None:
    client = client_with_rows([ANALYSIS_ROW])

    response = client.get("/api/v1/analysis/countries/ken")

    assert response.status_code == 200
    payload = response.json()
    assert payload["country_iso3"] == "KEN"
    assert payload["indicators"][0]["available_years"] == [
        2018,
        2019,
        2020,
        2021,
        2022,
        2023,
        2024,
    ]
    assert payload["indicators"][0]["value_rank_descending"] == 15
    assert len(payload["data_gaps"]) == 7
    assert payload["data_gaps"][0]["issue"] == "missing_indicator"
    app.dependency_overrides.clear()


def test_country_analysis_marks_single_observation_as_gap() -> None:
    row = ANALYSIS_ROW | {
        "indicator_code": "ED_SE_LPV_PRIM",
        "indicator_name": "Learning Poverty Rate",
        "latest_value": 79.29,
        "latest_year": 2023,
        "first_value": 79.29,
        "first_year": 2023,
        "absolute_change": 0.0,
        "percent_change": 0.0,
        "source_name": "unicef_education_fls",
        "freshness_status": "survey_snapshot",
        "observation_count": 1,
        "available_years": [2023],
    }
    client = client_with_rows([row])

    response = client.get("/api/v1/analysis/countries/KEN")

    assert response.status_code == 200
    gaps = response.json()["data_gaps"]
    assert any(gap["issue"] == "single_observation" for gap in gaps)
    app.dependency_overrides.clear()


def test_country_analysis_rejects_invalid_iso3() -> None:
    client = client_with_rows([ANALYSIS_ROW])

    response = client.get("/api/v1/analysis/countries/KE")

    assert response.status_code == 422
    assert response.json() == {"detail": "Country must use a three-letter ISO3 code"}
    app.dependency_overrides.clear()


def test_creates_grounded_country_brief() -> None:
    generator = MagicMock()
    generator.model = "test-model"
    generator.generate.return_value = CountryBriefDraft(
        executive_summary="Digital access remains a comparative constraint.",
        strengths=[],
        risks=[
            BriefFindingDraft(
                title="Digital access gap",
                analysis="Internet access trails the comparison cohort.",
                indicator_codes=["IT.NET.USER.ZS"],
            )
        ],
    )
    client = client_with_rows([ANALYSIS_ROW])
    app.dependency_overrides[get_country_brief_generator] = lambda: generator

    response = client.post(
        "/api/v1/ai/country-brief",
        json={"country_iso3": "KEN"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "test-model"
    assert payload["risks"][0]["evidence"][0]["value"] == 35.0
    assert payload["risks"][0]["evidence"][0]["year"] == 2024
    assert payload["generated_at"] is not None
    assert payload["cached"] is False
    generator.generate.assert_called_once()
    assert any(
        "INSERT INTO gold.ai_country_briefs" in call.args[0]
        for call in client.app.dependency_overrides[get_connection]().__next__().execute.call_args_list
    )
    app.dependency_overrides.clear()


def test_returns_latest_saved_country_brief() -> None:
    generated_at = datetime(2026, 10, 15, 8, 0, tzinfo=UTC)
    saved_brief = {
        "country_iso3": "KEN",
        "country_name": "Kenya",
        "model": "gpt-6-luna",
        "executive_summary": "Digital access remains constrained.",
        "strengths": [],
        "risks": [],
        "data_limitations": ["A limited series is available."],
        "methodology_notes": ["Use reported values carefully."],
        "generated_at": generated_at.isoformat(),
    }
    connection = MagicMock()
    connection.execute.return_value.fetchone.return_value = {
        "brief": saved_brief,
        "generated_at": generated_at,
    }

    def override_connection() -> Iterator[MagicMock]:
        yield connection

    app.dependency_overrides[get_connection] = override_connection
    client = TestClient(app)

    response = client.get("/api/v1/ai/country-brief/ken")

    assert response.status_code == 200
    assert response.json()["cached"] is True
    assert response.json()["model"] == "gpt-6-luna"
    app.dependency_overrides.clear()


def test_missing_saved_country_brief_returns_404() -> None:
    connection = MagicMock()
    connection.execute.return_value.fetchone.return_value = None

    def override_connection() -> Iterator[MagicMock]:
        yield connection

    app.dependency_overrides[get_connection] = override_connection
    client = TestClient(app)

    response = client.get("/api/v1/ai/country-brief/KEN")

    assert response.status_code == 404
    assert response.json() == {"detail": "No saved AI brief found"}
    app.dependency_overrides.clear()
