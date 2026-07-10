"""MCP server for searching the R-CCS Cloud documentation guide.

Read-only and needs no SSH access. The generic docs-search tools
(search_docs / list_doc_sections / read_doc_section) live in
`hpc_agent_core.docs_server`; this module only imports the machine's config
(registering its settings), names the FastMCP instance, and serves it.
"""
from mcp.server.fastmcp import FastMCP

from hpc_agent_core.docs_server import build
from hpc_agent_core.serving import serve
from cloud_mcp import config  # noqa: F401 -- registers settings via configure()

mcp = FastMCP("rccs-cloud-docs")
build(mcp)


def main():
    serve(mcp)


if __name__ == "__main__":
    main()
