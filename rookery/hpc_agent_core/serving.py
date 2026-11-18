"""Shared CLI entry point for the MCP servers."""
import argparse

from hpc_agent_core.mcp_server import MCPServer


def serve(mcp: MCPServer) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", default="stdio",
                        choices=["stdio", "streamable-http"])
    args, _ = parser.parse_known_args()
    mcp.run(transport=args.transport)
