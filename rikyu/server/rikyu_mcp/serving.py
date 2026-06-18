"""Shared CLI entry point for the MCP servers."""
import argparse

from mcp.server.fastmcp import FastMCP


def serve(mcp: FastMCP) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", default="stdio",
                        choices=["stdio", "streamable-http"])
    args, _ = parser.parse_known_args()
    mcp.run(transport=args.transport)
