"""The tool table in docs/api.md names exactly the server's tools and routes."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from mcp import Client

from br_elections_mcp.api import create_api
from br_elections_mcp.core import Core
from br_elections_mcp.mcp_server import create_mcp_server

ROOT = Path(__file__).resolve().parent.parent
API_GUIDE = ROOT / "docs/api.md"

# A table row that opens with a tool name in backticks, then its REST routes in the next cell.
_TOOL_ROW = re.compile(r"^\| `([a-z_]+)` \| ([^|]+) \|", re.MULTILINE)
_ROUTE = re.compile(r"`GET (/[^`]+)`")

pytestmark = pytest.mark.anyio


def _table(path: Path) -> dict[str, set[str]]:
    return {
        tool: set(_ROUTE.findall(routes)) for tool, routes in _TOOL_ROW.findall(path.read_text())
    }


async def test_tool_table_lists_every_mcp_tool_and_no_other(core: Core):
    async with Client(create_mcp_server(core)) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}

    assert set(_table(API_GUIDE)) == tools


def test_tool_table_lists_every_rest_route_once_and_no_other(core: Core):
    routes = [route for tool_routes in _table(API_GUIDE).values() for route in tool_routes]

    assert sorted(routes) == sorted(create_api(core).openapi()["paths"])
