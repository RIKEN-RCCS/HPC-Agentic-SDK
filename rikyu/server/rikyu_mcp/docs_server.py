"""RIKYU documentation-search MCP server — thin wrapper over hpc_agent_core.

Read-only, needs no SSH access. All the actual logic lives in
hpc_agent_core.docs_server.build(); this module just registers RIKYU's
settings (importing rikyu_mcp.config for its side effect) and serves.
"""
from mcp.server.fastmcp import FastMCP

from hpc_agent_core.docs_server import build
from hpc_agent_core.serving import serve
from rikyu_mcp import config  # noqa: F401 -- registers via configure()

mcp = FastMCP("rikyu-docs")
build(mcp)


def main():
    serve(mcp)


if __name__ == "__main__":
    main()
