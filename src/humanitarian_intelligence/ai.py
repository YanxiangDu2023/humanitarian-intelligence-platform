import re
from typing import Protocol

from openai import AuthenticationError, OpenAI, OpenAIError, PermissionDeniedError, RateLimitError
from pydantic import BaseModel

from humanitarian_intelligence.config import Settings


class BriefFindingDraft(BaseModel):
    title: str
    analysis: str
    indicator_codes: list[str]


class CountryBriefDraft(BaseModel):
    executive_summary: str
    strengths: list[BriefFindingDraft]
    risks: list[BriefFindingDraft]


class EvidenceCitation(BaseModel):
    indicator_code: str
    indicator_name: str
    value: float
    year: int
    unit: str | None
    source_name: str
    value_rank_descending: int
    cohort_size: int


class GroundedFinding(BaseModel):
    title: str
    analysis: str
    evidence: list[EvidenceCitation]


class CountryBriefResponse(BaseModel):
    country_iso3: str
    country_name: str
    model: str
    executive_summary: str
    strengths: list[GroundedFinding]
    risks: list[GroundedFinding]
    data_limitations: list[str]
    methodology_notes: list[str]


class CountryBriefGenerationError(RuntimeError):
    pass


class IndicatorEvidence(Protocol):
    indicator_code: str
    indicator_name: str
    latest_value: float
    latest_year: int
    unit: str | None
    source_name: str
    value_rank_descending: int
    cohort_size: int


class DataGapEvidence(Protocol):
    detail: str


class OpenAICountryBriefGenerator:
    def __init__(self, settings: Settings) -> None:
        if settings.openai_api_key is None:
            raise CountryBriefGenerationError("OPENAI_API_KEY is not configured")
        self.model = settings.openai_model
        self.client = OpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.http_timeout_seconds,
        )

    def generate(self, evidence_json: str) -> CountryBriefDraft:
        try:
            response = self.client.responses.parse(
                model=self.model,
                reasoning={"effort": "medium"},
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You write concise, neutral humanitarian country briefs from a "
                            "closed evidence package. Use only the supplied evidence. Do not add "
                            "causes, forecasts, policy recommendations, or external facts. Do not "
                            "write digits or numeric values in prose; the application will attach "
                            "verified values separately. Every finding must cite one to three exact "
                            "indicator_code values from the evidence. Raw-value rank is descriptive: "
                            "a higher value is not always better. Treat survey snapshots as single "
                            "observations, not trends."
                        ),
                    },
                    {"role": "user", "content": evidence_json},
                ],
                text_format=CountryBriefDraft,
            )
        except AuthenticationError as exc:
            raise CountryBriefGenerationError("OpenAI API authentication failed") from exc
        except PermissionDeniedError as exc:
            raise CountryBriefGenerationError(
                "The OpenAI project cannot access the configured model"
            ) from exc
        except RateLimitError as exc:
            if exc.code == "credit_balance_exhausted":
                raise CountryBriefGenerationError(
                    "OpenAI API credit balance is exhausted"
                ) from exc
            raise CountryBriefGenerationError("OpenAI API rate limit was exceeded") from exc
        except OpenAIError as exc:
            raise CountryBriefGenerationError("OpenAI request failed") from exc

        if response.output_parsed is None:
            raise CountryBriefGenerationError("OpenAI returned no structured country brief")
        return response.output_parsed


def ground_country_brief(
    draft: CountryBriefDraft,
    *,
    country_iso3: str,
    country_name: str,
    model: str,
    indicators: list[IndicatorEvidence],
    data_gaps: list[DataGapEvidence],
    methodology_notes: list[str],
) -> CountryBriefResponse:
    authored_text = [draft.executive_summary]
    authored_text.extend(finding.title for finding in draft.strengths + draft.risks)
    authored_text.extend(finding.analysis for finding in draft.strengths + draft.risks)
    if any(re.search(r"\d", text) for text in authored_text):
        raise CountryBriefGenerationError("AI prose contained an unverified numeric claim")

    evidence_by_code = {str(indicator.indicator_code): indicator for indicator in indicators}

    def ground_findings(findings: list[BriefFindingDraft]) -> list[GroundedFinding]:
        grounded: list[GroundedFinding] = []
        for finding in findings:
            codes = list(dict.fromkeys(code.upper() for code in finding.indicator_codes))
            if not codes or len(codes) > 3:
                raise CountryBriefGenerationError(
                    "Each AI finding must cite between one and three indicators"
                )
            unknown_codes = [code for code in codes if code not in evidence_by_code]
            if unknown_codes:
                raise CountryBriefGenerationError("AI cited an indicator outside the evidence")

            citations = []
            for code in codes:
                indicator = evidence_by_code[code]
                citations.append(
                    EvidenceCitation(
                        indicator_code=code,
                        indicator_name=str(indicator.indicator_name),
                        value=float(indicator.latest_value),
                        year=int(indicator.latest_year),
                        unit=indicator.unit,
                        source_name=str(indicator.source_name),
                        value_rank_descending=int(indicator.value_rank_descending),
                        cohort_size=int(indicator.cohort_size),
                    )
                )
            grounded.append(
                GroundedFinding(
                    title=finding.title,
                    analysis=finding.analysis,
                    evidence=citations,
                )
            )
        return grounded

    limitations = [str(gap.detail) for gap in data_gaps]
    if not limitations:
        limitations = ["No missing indicators or single-observation gaps were detected."]

    return CountryBriefResponse(
        country_iso3=country_iso3,
        country_name=country_name,
        model=model,
        executive_summary=draft.executive_summary,
        strengths=ground_findings(draft.strengths),
        risks=ground_findings(draft.risks),
        data_limitations=limitations,
        methodology_notes=methodology_notes,
    )
