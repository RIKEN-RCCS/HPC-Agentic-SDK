"""Entry point for rebuilding a facility's docs index:

    python -m hpc_mcp.ingest rikyu
    python -m hpc_mcp.ingest rikyu --no-embed

Registers every facility (via importing hpc_mcp) before delegating to
hpc_agent_core.rag.ingest.main(), which reads the facility slug positional
argument itself.
"""
import hpc_mcp  # noqa: F401 -- import for its side effect: registers every facility
from hpc_agent_core.rag.ingest import main

if __name__ == "__main__":
    main()
