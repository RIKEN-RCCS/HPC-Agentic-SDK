"""Health checks for the HokusaiAgent configuration.

    python -m hokusai_mcp.doctor

Checks the config file, SSH access to the cluster, Slurm availability, the
embedding endpoint, and the docs index. Exits nonzero if a required check
fails (the embedding endpoint is optional — docs search falls back to BM25).
"""
import json
import sys

from hokusai_mcp import config

OK, WARN, FAIL = "✓", "!", "✗"


def check_config_file() -> bool:
    if not config.CONFIG_PATH.exists():
        print(f"{WARN} config file: {config.CONFIG_PATH} not found "
              f"(using env vars / defaults — the 'configuring' skill can create it)")
        return True
    try:
        config._file_config()
    except RuntimeError as e:
        print(f"{FAIL} config file: {e}")
        return False
    print(f"{OK} config file: {config.CONFIG_PATH}")
    return True


def check_ssh() -> bool:
    from hokusai_mcp.middleware import run_command
    host = config.ssh_host()
    try:
        output = run_command("echo hokusai-ok && hostname")
    except Exception as e:
        print(f"{FAIL} ssh ({host}): {e}")
        return False
    if "hokusai-ok" not in output:
        print(f"{FAIL} ssh ({host}): unexpected response: {output[:200]}")
        return False
    print(f"{OK} ssh ({host}): connected to {output.strip().splitlines()[-1]}")

    slurm = run_command("sinfo --version")
    if slurm.startswith("slurm"):
        print(f"{OK} slurm: {slurm.strip()}")
        return True
    print(f"{FAIL} slurm: {slurm.strip()[:200]}")
    return False


def check_embedding() -> bool:
    """Probe the shared embedding endpoint. Optional — without an API key (or
    if the endpoint is unreachable) docs search falls back to BM25, so a failure
    here is a warning, not a hard failure."""
    if not config.embed_api_key():
        print(f"{WARN} embedding: no API key set — docs search uses BM25 keyword "
              f"matching (set embedding.api_key to enable semantic search)")
        return True
    from hokusai_mcp.rag.embed import get_client
    try:
        vector = get_client().embed(["connectivity probe"])[0]
    except Exception as e:
        print(f"{WARN} embedding ({config.EMBED_MODEL} @ {config.EMBED_BASE_URL}): {e} "
              f"— falling back to BM25")
        return True
    print(f"{OK} embedding: {config.EMBED_MODEL} @ {config.EMBED_BASE_URL} (dim {len(vector)})")
    return True


def check_docs_index() -> bool:
    chunks_path = config.DOCS_INDEX_DIR / "chunks.json"
    if not chunks_path.exists():
        print(f"{FAIL} docs index: {chunks_path} missing — run: python -m hokusai_mcp.rag.ingest")
        return False
    with open(chunks_path) as f:
        n_chunks = len(json.load(f))
    emb_path = config.DOCS_INDEX_DIR / "embeddings.npy"
    if not emb_path.exists():
        print(f"{OK} docs index: {n_chunks} chunks (BM25 keyword search — the HBW2 default)")
        return True
    import numpy as np
    n_vectors = np.load(emb_path).shape[0]
    if n_vectors != n_chunks:
        print(f"{FAIL} docs index: {n_chunks} chunks but {n_vectors} embeddings — "
              f"rebuild with: python -m hokusai_mcp.rag.ingest --embed")
        return False
    print(f"{OK} docs index: {n_chunks} chunks with embeddings")
    return True


def main() -> int:
    results = [
        check_config_file(),
        check_ssh(),
        check_embedding(),
        check_docs_index(),
    ]
    if all(results):
        print("\nAll checks passed.")
        return 0
    print("\nSome checks FAILED — see above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
