"""MCP server for searching the R-CCS Cloud documentation guide.

Read-only and needs no SSH access. Uses the pre-built packaged index in
cloud_mcp/data/docs_index (built from cloud_mcp/data/cloud_guide.md, an
original guide to the R-CCS Cloud). Search is BM25 keyword matching by
default; if an embedding endpoint is configured and the index has vectors,
semantic search is used instead, with fallback to keyword search.
"""
from functools import lru_cache

from mcp.server.fastmcp import FastMCP

from cloud_mcp import config
from cloud_mcp.rag.store import DocsIndex
from cloud_mcp.serving import serve

mcp = FastMCP("rccs-cloud-docs")


@lru_cache(maxsize=1)
def _index() -> DocsIndex:
    return DocsIndex(config.DOCS_INDEX_DIR)


def _format(result: dict) -> str:
    return (f"## {result['breadcrumb']}\n"
            f"Source: {result['url']}\n\n"
            f"{result['text']}")


@mcp.tool()
def search_docs(query: str, top_k: int = 4) -> str:
    """Search the R-CCS Cloud documentation guide.

    Always call this first before answering any question about R-CCS Cloud
    specifics: partitions, module loading, job submission, hardware details,
    storage, login procedure, or any machine-specific detail. Do not rely on
    prior knowledge or the orientation facts embedded in skills — those are
    fallback aids, not authoritative. The guide is the source of truth.

    If this tool errors or returns no results, fall back to the inline facts in
    the active skill and note that docs were unavailable.

    When results begin with `[search_method: bm25]`, inform the user that
    keyword search was used because the embedding server could not be reached.
    Results may miss semantically relevant sections that don't share exact
    keywords with the query.

    Args:
        query: Natural-language question or keywords.
        top_k: Number of sections to return.
    """
    results = _index().search(query, top_k=top_k)
    if not results:
        return "No matching documentation sections found."
    sections = "\n\n---\n\n".join(_format(r) for r in results)
    if results[0]["method"] == "bm25":
        return f"[search_method: bm25]\n\n{sections}"
    return sections


@mcp.tool()
def list_doc_sections() -> str:
    """List every section of the R-CCS Cloud guide (table of contents)."""
    lines = [f"- {c['breadcrumb']}  ({c['url']})" for c in _index().chunks]
    return "\n".join(lines)


@mcp.tool()
def read_doc_section(breadcrumb: str) -> str:
    """Read one documentation section in full by its breadcrumb.

    Args:
        breadcrumb: Section path as shown by list_doc_sections or search_docs,
            e.g. 'R-CCS Cloud > Module Loading'. Partial matches work.
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
