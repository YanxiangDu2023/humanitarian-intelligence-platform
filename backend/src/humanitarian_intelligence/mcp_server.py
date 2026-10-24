import ssl
from collections.abc import Sequence
from typing import Any

import httpx
import truststore
from mcp.server import MCPServer

from humanitarian_intelligence.config import get_settings

mcp = MCPServer("Humanitarian Intelligence")


def _normalize_iso3(country_iso3: str) -> str:
    normalized = country_iso3.strip().upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise ValueError("Country must use a three-letter ISO3 code")
    return normalized


def _normalize_countries(countries: Sequence[str], *, maximum: int | None = None) -> list[str]:
    normalized = list(dict.fromkeys(_normalize_iso3(country) for country in countries))
    if not normalized:
        raise ValueError("At least one country is required")
    if maximum is not None and len(normalized) > maximum:
        raise ValueError(f"At most {maximum} countries are allowed")
    return normalized


def _normalize_indicator(indicator_code: str) -> str:
    normalized = indicator_code.strip().upper()
    if not normalized:
        raise ValueError("Indicator code is required")
    return normalized


async def _get_json(
    path: str,
    params: Sequence[tuple[str, str | int]] | None = None,
) -> Any:
    settings = get_settings()
    async with httpx.AsyncClient(
        base_url=settings.mcp_api_base_url.rstrip("/"),
        timeout=settings.http_timeout_seconds,
        follow_redirects=True,
        verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
    ) as client:
        response = await client.get(path, params=params)

    if response.is_error:
        detail: object = response.text
        try:
            payload = response.json()
            if isinstance(payload, dict):
                detail = payload.get("detail", payload)
        except ValueError:
            pass
        raise RuntimeError(f"Humanitarian API returned HTTP {response.status_code}: {detail}")
    return response.json()


def _expect_list(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise RuntimeError("Humanitarian API returned an unexpected list response")
    return payload


def _expect_object(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TypeError("Humanitarian API returned an unexpected object response")
    return payload


@mcp.tool()
async def list_countries() -> list[dict[str, Any]]:
    """List the countries available in the verified comparison cohort."""
    return _expect_list(await _get_json("/api/v1/countries"))


@mcp.tool()
async def list_indicators() -> list[dict[str, Any]]:
    """List available indicators with their units and public data sources."""
    return _expect_list(await _get_json("/api/v1/indicators"))


@mcp.tool()
async def get_country_profile(country_iso3: str) -> list[dict[str, Any]]:
    """Get the latest verified indicator values for one ISO3 country code."""
    country = _normalize_iso3(country_iso3)
    return _expect_list(await _get_json(f"/api/v1/countries/{country}/indicators"))


@mcp.tool()
async def compare_indicator(
    indicator_code: str,
    countries: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Compare one indicator across all countries or an optional ISO3 country selection."""
    indicator = _normalize_indicator(indicator_code)
    params: list[tuple[str, str | int]] | None = None
    if countries:
        params = [("country", country) for country in _normalize_countries(countries)]
    return _expect_list(await _get_json(f"/api/v1/comparisons/{indicator}", params=params))


@mcp.tool()
async def get_indicator_trends(
    indicator_code: str,
    countries: list[str],
    start_year: int | None = None,
    end_year: int | None = None,
) -> list[dict[str, Any]]:
    """Get historical observations for one indicator and one to three ISO3 countries."""
    indicator = _normalize_indicator(indicator_code)
    selected = _normalize_countries(countries, maximum=3)
    if start_year is not None and end_year is not None and start_year > end_year:
        raise ValueError("start_year must not be after end_year")

    params: list[tuple[str, str | int]] = [("country", country) for country in selected]
    if start_year is not None:
        params.append(("start_year", start_year))
    if end_year is not None:
        params.append(("end_year", end_year))
    return _expect_list(await _get_json(f"/api/v1/trends/{indicator}", params=params))


@mcp.tool()
async def get_saved_ai_brief(country_iso3: str) -> dict[str, Any]:
    """Read the latest saved, evidence-grounded AI brief without generating new content."""
    country = _normalize_iso3(country_iso3)
    return _expect_object(await _get_json(f"/api/v1/ai/country-brief/{country}"))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
