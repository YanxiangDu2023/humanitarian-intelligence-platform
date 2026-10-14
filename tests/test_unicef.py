import pytest

from humanitarian_intelligence.etl.unicef import normalize_observations


def test_normalize_observations_preserves_sex_and_unit() -> None:
    code_csv = (
        "REF_AREA,INDICATOR,SEX,UNIT_MEASURE,TIME_PERIOD,OBS_VALUE\n"
        "JOR,ED_SE_LPV_PRIM,F,PCNT,2021,57.9\n"
        "JOR,NOT_SELECTED,T,PCNT,2021,12.0"
    )
    label_csv = (
        "Geographic area,Indicator,Sex,Unit of measure,TIME_PERIOD,OBS_VALUE\n"
        "Jordan,Learning Poverty Rate,Female,%,2021,57.9\n"
        "Jordan,Other indicator,Total,%,2021,12.0"
    )

    result = normalize_observations(
        code_csv,
        label_csv,
        ("ED_SE_LPV_PRIM",),
    )

    assert len(result) == 1
    assert result[0].country_iso3 == "JOR"
    assert result[0].indicator_code == "ED_SE_LPV_PRIM"
    assert result[0].sex_code == "F"
    assert result[0].sex_name == "Female"
    assert result[0].unit == "%"
    assert result[0].observation_value == 57.9


def test_normalize_observations_rejects_misaligned_responses() -> None:
    code_csv = "REF_AREA,INDICATOR,SEX,TIME_PERIOD,OBS_VALUE\nJOR,X,F,2021,1"
    label_csv = (
        "Geographic area,Indicator,Sex,TIME_PERIOD,OBS_VALUE\n"
        "Jordan,Example,Female,2022,1"
    )

    with pytest.raises(ValueError, match="not aligned by year"):
        normalize_observations(code_csv, label_csv, ("X",))
