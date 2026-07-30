"""Fugaku documentation-search MCP server — thin wrapper over hpc_agent_core.

Read-only, needs no SSH access. All the actual logic lives in
hpc_agent_core.docs_server.build(); this module just registers Fugaku's
settings (importing fugaku_mcp.config for its side effect) and serves.
"""
from hpc_agent_core.mcp_server import MCPServer

from hpc_agent_core.docs_server import build
from hpc_agent_core.serving import serve
from fugaku_mcp import config  # noqa: F401 -- registers via configure()

mcp = MCPServer("fugaku-docs")
build(mcp)


def main():
    serve(mcp)


if __name__ == "__main__":
    main()
