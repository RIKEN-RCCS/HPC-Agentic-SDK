"""Exercise both MCP servers from the installed Rookery package without SSH."""

import asyncio
import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
ROOKERY = ROOT / "rookery"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


async def call(session, name, arguments=None):
    result = await session.call_tool(name, arguments)
    assert not result.is_error, (name, arguments, result.content)
    return result


async def main():
    facilities = set(read_json(ROOKERY / "UPSTREAM.json")["facilities"])
    expected_plugins = {"hpc", *(f"hpc-{slug}" for slug in facilities)}
    bundled = {f.name for f in (ROOKERY / "plugins").iterdir() if f.is_dir()}
    assert bundled == expected_plugins, bundled
    for path in (".agents/plugins/marketplace.json", ".claude-plugin/marketplace.json"):
        entries = read_json(ROOT / path)["plugins"]
        rookery_entries = {
            entry["name"] for entry in entries
            if f"./rookery/plugins/{entry['name']}" == (
                entry["source"] if isinstance(entry["source"], str) else entry["source"].get("path")
            )
        }
        assert rookery_entries == expected_plugins, (path, rookery_entries)

    async with stdio_client(StdioServerParameters(command="hpc-mcp")) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            result = await call(session, "get_facilities")
            listing = result.structured_content["result"]
            assert {entry["slug"] for entry in listing} == facilities, listing
            assert all(not entry.get("unavailable") for entry in listing), listing
            for slug in sorted(facilities):
                await call(session, "get_facility", {"facility": slug})
            unavailable = await session.call_tool("get_facility", {"facility": "not-bundled"})
            assert unavailable.is_error, unavailable

    async with stdio_client(StdioServerParameters(command="hpc-docs-mcp")) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            for slug in sorted(facilities):
                result = await call(session, "list_doc_sections", {"facility": slug})
                assert any(block.type == "text" and block.text.strip() for block in result.content), slug

    print(f"Verified both MCP servers and bundled guides for {', '.join(sorted(facilities))}.")


if __name__ == "__main__":
    asyncio.run(main())
