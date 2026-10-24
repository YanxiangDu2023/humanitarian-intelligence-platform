from datetime import UTC, datetime

import pytest

from humanitarian_intelligence.source_probe import (
    ExpectedSeries,
    Observation,
    build_profiles,
    parse_unicef_rows,
    parse_world_bank_payload,
    render_markdown,
)


def test_parse_unicef_rows_combines_codes_and_labels() -> None:
    code_csv = (
        "REF_AREA,INDICATOR,SEX,UNIT_MULTIPLIER,UNIT_MEASURE,TIME_PERIOD,"
        "OBS_VALUE,SOWC_FLAG_A\n"
        "JOR,ED_SE_LPV_PRIM,F,,PCNT,2021,57.9,"
    )
    label_csv = (
        "Geographic area,Indicator,Sex,Unit multiplier,Unit of measure,TIME_PERIOD,"
        "OBS_VALUE,SOWC flag A\n"
        "Jordan,Learning Poverty Rate,Female,,%,2021,57.9,"
    )

    result = parse_unicef_rows(code_csv, label_csv)

    assert result == [
        Observation(
            source="UNICEF Data Warehouse",
            country_code="JOR",
            country_name="Jordan",
            indicator_code="ED_SE_LPV_PRIM",
            indicator_name="Learning Poverty Rate",
            year=2021,
            value=57.9,
            unit="%",
            sex_code="F",
            sex_name="Female",
        )
    ]


def test_parse_unicef_rows_rejects_misaligned_responses() -> None:
    code_csv = "REF_AREA,INDICATOR,SEX,TIME_PERIOD,OBS_VALUE\nJOR,X,F,2021,1"
    label_csv = (
        "Geographic area,Indicator,Sex,TIME_PERIOD,OBS_VALUE\n"
        "Jordan,Example,Female,2022,1"
    )

    with pytest.raises(ValueError, match="not aligned by year"):
        parse_unicef_rows(code_csv, label_csv)


def test_world_bank_profile_and_report_show_coverage_gaps() -> None:
    payload = [
        {"page": 1},
        [
            {
                "country": {"value": "Kenya"},
                "countryiso3code": "KEN",
                "indicator": {"id": "SE.PRM.ENRR", "value": "Primary enrollment"},
                "date": "2020",
                "value": 99.0,
            },
            {
                "country": {"value": "Kenya"},
                "countryiso3code": "KEN",
                "indicator": {"id": "SE.PRM.ENRR", "value": "Primary enrollment"},
                "date": "2021",
                "value": None,
            },
        ],
    ]

    profiles = build_profiles(parse_world_bank_payload(payload), 2020, 2021)
    report = render_markdown(
        profiles,
        generated_at=datetime(2026, 10, 13, tzinfo=UTC),
        start_year=2020,
        end_year=2021,
    )

    assert profiles[0].observed_years == (2020,)
    assert profiles[0].years_without_observation == (2021,)
    assert "Primary enrollment (`SE.PRM.ENRR`)" in report
    assert "2021" in report


def test_profile_includes_completely_missing_expected_series() -> None:
    expected = ExpectedSeries(
        source="World Bank Indicators",
        country_code="KEN",
        country_name="Kenya",
        indicator_code="SE.PRM.CMPT.ZS",
        indicator_name="Primary completion rate",
    )

    profiles = build_profiles([], 2020, 2022, expected_series=(expected,))

    assert profiles[0].observation_count == 0
    assert profiles[0].observed_years == ()
    assert profiles[0].years_without_observation == (2020, 2021, 2022)
