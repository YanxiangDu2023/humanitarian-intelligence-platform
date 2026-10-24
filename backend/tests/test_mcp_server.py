from typing import Any

import pytest
from mcp import Client

from humanitarian_intelligence import mcp_server


@pytest.mark.anyio
async def test_exposes_only_read_only_tools() -> None:
    async with Client(mcp_server.mcp) as client:
        result = await client.list_tools()

    assert {tool.name for tool in result.tools} == {
        "compare_indicator",
        "get_country_profile",
        "get_indicator_trends",
        "get_saved_ai_brief",
        "list_countries",
        "list_indicators",
    }


@pytest.mark.anyio
async def test_lists_countries_through_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_json(
        path: str,
        params: list[tuple[str, str | int]] | None = None,
    ) -> Any:
        assert path == "/api/v1/countries"
        assert params is None
        return [{"country_iso3": "KEN", "country_name": "Kenya"}]

    monkeypatch.setattr(mcp_server, "_get_json", fake_get_json)

    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool("list_countries", {})

    assert result.structured_content == {
        "result": [{"country_iso3": "KEN", "country_name": "Kenya"}]
    }


@pytest.mark.anyio
async def test_compares_selected_countries(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_json(
        path: str,
        params: list[tuple[str, str | int]] | None = None,
    ) -> Any:
        assert path == "/api/v1/comparisons/ED_SE_LPV_PRIM"
        assert params == [("country", "JPN"), ("country", "KEN")]
        return [{"country_iso3": "JPN", "observation_value": 1.8}]

    monkeypatch.setattr(mcp_server, "_get_json", fake_get_json)

    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool(
            "compare_indicator",
            {
                "indicator_code": "ed_se_lpv_prim",
                "countries": ["jpn", "ken", "JPN"],
            },
        )

    assert result.structured_content == {
        "result": [{"country_iso3": "JPN", "observation_value": 1.8}]
    }


@pytest.mark.anyio
async def test_trends_reject_more_than_three_countries() -> None:
    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool(
            "get_indicator_trends",
            {
                "indicator_code": "IT.NET.USER.ZS",
                "countries": ["KEN", "JOR", "ZAF", "JPN"],
            },
        )

    assert result.is_error
    with pytest.raises(ValueError, match="At most 3 countries are allowed"):
        mcp_server._normalize_countries(["KEN", "JOR", "ZAF", "JPN"], maximum=3)


@pytest.mark.anyio
async def test_reads_saved_brief_without_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_json(
        path: str,
        params: list[tuple[str, str | int]] | None = None,
    ) -> Any:
        assert path == "/api/v1/ai/country-brief/JPN"
        assert params is None
        return {"country_iso3": "JPN", "cached": True}

    monkeypatch.setattr(mcp_server, "_get_json", fake_get_json)

    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool("get_saved_ai_brief", {"country_iso3": "jpn"})

    assert result.structured_content == {"country_iso3": "JPN", "cached": True}
