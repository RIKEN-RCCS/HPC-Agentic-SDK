"""Entry point for the unified docs-search MCP server.

Registers every facility (via importing hpc_mcp), then delegates to
hpc_agent_core.docs_server.build() for the actual search_docs/
list_doc_sections/read_doc_section tools — see that module for their
facility-parametrized implementation.
"""
import hpc_mcp  # noqa: F401 -- import for its side effect: registers every facility
from hpc_agent_core.docs_server import build
from hpc_agent_core.mcp_server import MCPServer
from hpc_agent_core.serving import serve

mcp = build(MCPServer("hpc-docs-mcp"))


def main():
    serve(mcp)


if __name__ == "__main__":
    main()
