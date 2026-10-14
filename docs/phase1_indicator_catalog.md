# Phase 1 Indicator Catalogue

This catalogue contains indicators selected after a 2018–2026 feasibility check across the
G20 country set, with Jordan and Kenya retained for humanitarian comparison. The production
cohort contains the 17 countries for which the selected UNICEF learning indicators returned
observations and the retained World Bank context indicators were usable.

Countries: Argentina (`ARG`), Australia (`AUS`), Brazil (`BRA`), Germany (`DEU`), France
(`FRA`), United Kingdom (`GBR`), Italy (`ITA`), Japan (`JPN`), South Korea (`KOR`), Mexico
(`MEX`), Russia (`RUS`), Saudi Arabia (`SAU`), Turkiye (`TUR`), United States (`USA`), South
Africa (`ZAF`), Jordan (`JOR`), and Kenya (`KEN`).

## UNICEF Data Warehouse

Dataflow: `UNICEF,EDUCATION_FLS,1.0`

| Code | Indicator | Unit | Jordan | Kenya | Intended use |
| --- | --- | --- | --- | --- | --- |
| `ED_SE_LPV_PRIM` | Learning Poverty Rate | % | 2021 | 2023 | Country snapshot |
| `ED_SE_LPV_PRIM_LD` | Learning Deprivation | % | 2021 | 2023 | Country snapshot |
| `ED_SE_LPV_PRIM_SD` | Schooling Deprivation | % | 2021 | 2023 | Country snapshot |

All three UNICEF indicators include Female, Male, and Total observations for the selected
countries. They must not be presented as annual time series or as same-year comparisons.

## World Bank Indicators

| Code | Indicator | Jordan coverage | Kenya coverage | Intended use |
| --- | --- | --- | --- | --- |
| `SE.PRM.ENRR` | School enrollment, primary (% gross) | 2018–2024 | 2018–2023 | Trend |
| `SE.SEC.ENRR` | School enrollment, secondary (% gross) | 2018–2024 | 2021–2023 | Limited trend |
| `SE.XPD.TOTL.GD.ZS` | Government expenditure on education (% of GDP) | 2018–2024 | 2018–2024 | Trend/context |
| `IT.NET.USER.ZS` | Individuals using the Internet (% of population) | 2018–2024 | 2018–2024 | Digital context |
| `SP.POP.TOTL` | Population, total | 2018–2025 | 2018–2025 | Country context |

## Excluded after profiling

`SE.PRM.CMPT.ZS` (primary completion rate) was excluded because the API returned no Kenya
observations in the requested window. A missing source series must not be filled or inferred
by an LLM.

## Interpretation rules

- Preserve source indicator codes, units, sex dimensions, and retrieval timestamps.
- Show the actual observation year beside every UNICEF value.
- Do not interpolate missing years in Phase 1.
- Do not compare UNICEF values as if Jordan 2021 and Kenya 2023 were measured in the same year.
- Treat World Bank gross enrolment values according to the source definition; values may
  exceed 100 percent.
