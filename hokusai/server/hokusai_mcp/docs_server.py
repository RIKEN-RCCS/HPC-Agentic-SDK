"""MCP server for searching HBW2's bundled guide — a thin wrapper over
hpc_agent_core.docs_server. Read-only; needs no SSH access."""
from mcp.server.fastmcp import FastMCP

from hpc_agent_core.docs_server import build
from hpc_agent_core.serving import serve
from hokusai_mcp import config  # noqa: F401 -- registers settings via configure().

mcp = FastMCP("hokusai-docs")
build(mcp)


def main():
    serve(mcp)


if __name__ == "__main__":
    main()
