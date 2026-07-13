"""Build the docs index from the bundled guide.

    python -m hokusai_mcp.ingest              # chunks + embeddings (needs an API key)
    python -m hokusai_mcp.ingest --no-embed   # keyword-only index

Thin wrapper over `hpc_agent_core.rag.ingest`: importing config first
registers the machine's settings (guide path, embedding endpoint, docs_cite_url)
before the generic ingest reads them. End users never need this — the built
index is committed as package data; re-run it only after editing the guide.

(`python -m hpc_agent_core.rag.ingest` directly does NOT work — it has no
way to know which machine's settings to use without this import happening
first in the same process.)
"""
from hpc_agent_core.rag.ingest import main
from hokusai_mcp import config  # noqa: F401 -- registers settings via configure()

if __name__ == "__main__":
    main()
