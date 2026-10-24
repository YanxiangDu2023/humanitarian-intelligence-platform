import pytest

from humanitarian_intelligence.etl.world_bank import normalize_observations


def test_normalize_observations_skips_missing_values() -> None:
    payload = [
        {"page": 1, "pages": 1},
        [
            {
                "country": {"value": "Jordan"},
                "countryiso3code": "JOR",
                "indicator": {
                    "id": "SE.PRM.ENRR",
                    "value": "School enrollment, primary (% gross)",
                },
                "date": "2022",
                "value": 92.5,
            },
            {
                "country": {"value": "Jordan"},
                "countryiso3code": "JOR",
                "indicator": {"id": "SE.PRM.ENRR", "value": "Primary enrolment"},
                "date": "2021",
                "value": None,
            },
        ],
    ]

    result = normalize_observations(payload)

    assert len(result) == 1
    assert result[0].country_iso3 == "JOR"
    assert result[0].observation_year == 2022
    assert result[0].observation_value == 92.5


def test_normalize_observations_rejects_unexpected_shape() -> None:
    with pytest.raises(ValueError, match="Unexpected World Bank response shape"):
        normalize_observations({"message": "rate limited"})

