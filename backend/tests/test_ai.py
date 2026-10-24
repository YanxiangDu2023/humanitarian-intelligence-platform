from types import SimpleNamespace

import pytest

from humanitarian_intelligence.ai import (
    BriefFindingDraft,
    CountryBriefDraft,
    CountryBriefGenerationError,
    ground_country_brief,
)

INDICATOR = SimpleNamespace(
    indicator_code="IT.NET.USER.ZS",
    indicator_name="Individuals using the Internet (% of population)",
    latest_value=34.976,
    latest_year=2024,
    unit="%",
    source_name="world_bank_indicators",
    value_rank_descending=17,
    cohort_size=17,
)


def test_grounds_ai_findings_with_verified_evidence() -> None:
    draft = CountryBriefDraft(
        executive_summary="Digital access remains a major comparative constraint.",
        strengths=[],
        risks=[
            BriefFindingDraft(
                title="Limited digital access",
                analysis="Internet access trails the comparison cohort.",
                indicator_codes=["IT.NET.USER.ZS"],
            )
        ],
    )

    brief = ground_country_brief(
        draft,
        country_iso3="KEN",
        country_name="Kenya",
        model="test-model",
        indicators=[INDICATOR],
        data_gaps=[],
        methodology_notes=["Ranks describe raw values."],
    )

    evidence = brief.risks[0].evidence[0]
    assert evidence.value == 34.976
    assert evidence.year == 2024
    assert evidence.source_name == "world_bank_indicators"


def test_rejects_numeric_claims_in_ai_prose() -> None:
    draft = CountryBriefDraft(
        executive_summary="Internet access is 99 percent.",
        strengths=[],
        risks=[],
    )

    with pytest.raises(CountryBriefGenerationError, match="numeric claim"):
        ground_country_brief(
            draft,
            country_iso3="KEN",
            country_name="Kenya",
            model="test-model",
            indicators=[INDICATOR],
            data_gaps=[],
            methodology_notes=[],
        )


def test_rejects_indicator_outside_evidence_package() -> None:
    draft = CountryBriefDraft(
        executive_summary="Digital access remains constrained.",
        strengths=[],
        risks=[
            BriefFindingDraft(
                title="Unsupported claim",
                analysis="An unsupported indicator is cited.",
                indicator_codes=["UNKNOWN"],
            )
        ],
    )

    with pytest.raises(CountryBriefGenerationError, match="outside the evidence"):
        ground_country_brief(
            draft,
            country_iso3="KEN",
            country_name="Kenya",
            model="test-model",
            indicators=[INDICATOR],
            data_gaps=[],
            methodology_notes=[],
        )
