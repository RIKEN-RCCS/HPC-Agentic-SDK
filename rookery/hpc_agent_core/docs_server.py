"""Generic MCP tools for searching a facility's bundled documentation guide.

Read-only and needs no SSH access. Uses the pre-built packaged index at
config.docs_index_dir(facility) (chunks.json + optional embeddings.npy);
queries are embedded against that facility's configured serving
infrastructure when available, with automatic fallback to keyword search.

These tools are deliberately *not* behind require_facility_configuration:
the index ships with the package, so searching a facility's guide is how an
agent helps someone who has not configured access yet. Gating them made
the <slug>-reference and <slug>-configuring skills circular.

Per PORTING.md, a chunk only carries a "Source: ..." line when the facility
registered a docs_cite_url — most facilities leave it blank (no live site
worth citing), in which case results never mention a URL at all. This is a
deliberate per-facility policy, not a bug: don't add a URL back in here
without checking config.docs_cite_url(facility) first.

server/hpc_mcp/docs_server.py imports every facilities/*/facility.py (to
register them), constructs MCPServer("hpc-docs"), and calls build(mcp) below
before serve(mcp) — one process, every facility.
"""
from functools import lru_cache

from hpc_agent_core.mcp_server import MCPServer

from hpc_agent_core import config
from hpc_agent_core.rag.embed import get_client
from hpc_agent_core.rag.store import DocsIndex


@lru_cache(maxsize=None)
def _index(facility: str) -> DocsIndex:
    fac = config.get_facility(facility)
    # Cache the immutable packaged corpus, not its credential-bearing client.
    # search_docs refreshes the client below so a key added/rotated in the
    # user config takes effect without restarting this MCP server.
    return DocsIndex(config.docs_index_dir(fac), embed_client=None)


def _format(result: dict) -> str:
    header = f"## {result['breadcrumb']}\n"
    if result.get("url"):
        header += f"Source: {result['url']}\n"
    return header + f"\n{result['text']}"


def build(mcp: MCPServer) -> MCPServer:
    """Register the docs-search tools on an existing MCPServer instance."""

    @mcp.tool()
    def search_docs(facility: str, query: str, top_k: int = 4) -> str:
        """Search one facility's bundled documentation guide.

        facility must be one of the slugs returned by get_facilities() (on
        the hpc-mcp server) — call that first if you don't already know
        which facility you're working with.

        Always call this first before answering any facility-specific
        question — job submission, modules, storage, login procedure, or
        any other cluster-specific detail. Do not rely on prior knowledge or
        the orientation facts embedded in skills — those are fallback aids,
        not authoritative.

        If a result carries no "Source:" line, that's deliberate (see this
        module's docstring) — do not invent or guess a URL to send the user
        to.

        If this tool errors or returns no results, fall back to the inline
        facts in the active skill and note that docs were unavailable.

        When results begin with `[search_method: bm25]`, inform the user
        that keyword search was used because the embedding server could not
        be reached. Results may miss semantically relevant sections that
        don't share exact keywords with the query.

        Args:
            facility: Facility slug, e.g. "rikyu".
            query: Natural-language question or keywords.
            top_k: Number of sections to return.
        """
        results = _index(facility).search(
            query, top_k=top_k, embed_client=get_client(facility),
        )
        if not results:
            return "No matching documentation sections found."
        sections = "\n\n---\n\n".join(_format(r) for r in results)
        if results[0]["method"] == "bm25":
            return f"[search_method: bm25]\n\n{sections}"
        return sections

    @mcp.tool()
    def list_doc_sections(facility: str) -> str:
        """List every section of a facility's bundled guide (table of
        contents). facility must be one of the slugs from get_facilities()."""
        return "\n".join(f"- {c['breadcrumb']}" for c in _index(facility).chunks)

    @mcp.tool()
    def read_doc_section(facility: str, breadcrumb: str) -> str:
        """Read one section of a facility's guide in full, by its breadcrumb.

        Args:
            facility: Facility slug, e.g. "rikyu".
            breadcrumb: Section path as shown by list_doc_sections or
                search_docs, e.g. 'Running jobs'. Partial matches work.
        """
        needle = breadcrumb.lower()
        matches = [c for c in _index(facility).chunks if needle in c["breadcrumb"].lower()]
        if not matches:
            return f"No section matching '{breadcrumb}'. Use list_doc_sections to see all sections."
        return "\n\n---\n\n".join(_format(c) for c in matches)

    return mcp
