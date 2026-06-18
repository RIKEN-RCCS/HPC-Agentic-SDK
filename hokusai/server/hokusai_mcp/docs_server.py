"""MCP server for searching the HOKUSAI BigWaterfall2 (HBW2) guide.

Read-only and needs no SSH access. Uses the pre-built index in data/docs_index
(built from data/hokusai_guide.md, an original orientation guide). Search is BM25
keyword matching by default; if an embedding endpoint is configured and the index
has vectors, semantic search is used instead, with fallback to keyword search.
"""
from functools import lru_cache

from mcp.server.fastmcp import FastMCP

from hokusai_mcp import config
from hokusai_mcp.rag.store import DocsIndex
from hokusai_mcp.serving import serve

mcp = FastMCP("hokusai-docs")


@lru_cache(maxsize=1)
def _index() -> DocsIndex:
    return DocsIndex(config.DOCS_INDEX_DIR)


def _format(result: dict) -> str:
    return (f"## {result['breadcrumb']}\n"
            f"Source: {result['url']}\n\n"
            f"{result['text']}")


@mcp.tool()
def search_docs(query: str, top_k: int = 4) -> str:
    """Search the HOKUSAI BigWaterfall2 (HBW2) documentation guide.

    Use this before answering questions about HBW2 specifics: partitions,
    job submission, projects/accounts, storage, login procedure. Returns the
    most relevant documentation sections with their source URLs.

    Args:
        query: Natural-language question or keywords.
        top_k: Number of sections to return.
    """
    results = _index().search(query, top_k=top_k)
    if not results:
        return "No matching documentation sections found."
    return "\n\n---\n\n".join(_format(r) for r in results)


@mcp.tool()
def list_doc_sections() -> str:
    """List every section of the HBW2 guide (table of contents)."""
    lines = [f"- {c['breadcrumb']}  ({c['url']})" for c in _index().chunks]
    return "\n".join(lines)


@mcp.tool()
def read_doc_section(breadcrumb: str) -> str:
    """Read one documentation section in full by its breadcrumb.

    Args:
        breadcrumb: Section path as shown by list_doc_sections or search_docs,
            e.g. 'Welcome > Usage > Submit a batch job'. Partial matches work.
    """
    needle = breadcrumb.lower()
    matches = [c for c in _index().chunks if needle in c["breadcrumb"].lower()]
    if not matches:
        return f"No section matching '{breadcrumb}'. Use list_doc_sections to see all sections."
    return "\n\n---\n\n".join(_format(c) for c in matches)


def main():
    serve(mcp)


if __name__ == "__main__":
    main()
