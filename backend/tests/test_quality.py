from humanitarian_intelligence.quality import QualityResult


def test_quality_result_is_valid_without_issues() -> None:
    result = QualityResult(
        total_checks=136,
        passed_checks=136,
        missing_checks=0,
        out_of_range_checks=0,
    )

    assert result.is_valid


def test_quality_result_is_invalid_with_missing_data() -> None:
    result = QualityResult(
        total_checks=136,
        passed_checks=135,
        missing_checks=1,
        out_of_range_checks=0,
    )

    assert not result.is_valid
