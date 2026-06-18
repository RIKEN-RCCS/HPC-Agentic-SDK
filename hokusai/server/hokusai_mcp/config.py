"""Configuration for the hokusai MCP servers.

Settings come from, in order of precedence:
  1. Environment variables (HOKUSAI_*)
  2. The user config file ~/.hokusai/config.json (path override: HOKUSAI_CONFIG)
  3. Defaults

The config file is created with the help of the `configuring` skill:

    {
      "ssh": {"host": "hokusai"},
      "account": "RB999999",
      "embedding": {"base_url": "...", "model": "...", "api_key": "..."}
    }

`ssh.host` is an alias from ~/.ssh/config or a plain user@hostname; key-based
auth is assumed (no credentials are stored here). `account` is the default
Slurm project ID (e.g. RB999999) charged for jobs that don't set one explicitly.

Documentation search uses a shared RIKEN embedding endpoint (EMBED_BASE_URL /
EMBED_MODEL — hardcoded constants, since the committed embeddings.npy is tied to
that exact model). The only user-facing embedding setting is `api_key`; without
it (or if the endpoint is unreachable) search falls back to BM25 keyword search.
"""
import json
import os
from functools import lru_cache
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("HOKUSAI_CONFIG", "~/.hokusai/config.json")).expanduser()


def _file_config() -> dict:
    """The parsed config file, or {} if absent. Raises on malformed JSON."""
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Malformed config file {CONFIG_PATH}: {e}") from e


def ssh_host() -> str:
    """SSH destination for the HBW2 front-end (alias or user@hostname)."""
    return (os.environ.get("HOKUSAI_HOST")
            or _file_config().get("ssh", {}).get("host")
            or "hokusai")


def default_account() -> str | None:
    """Default Slurm project ID (e.g. RB999999) for jobs that don't set one.

    Job execution on HBW2 requires --account; this provides a fallback when a
    JobSpec leaves attributes.account unset. Override via HOKUSAI_ACCOUNT.
    """
    return (os.environ.get("HOKUSAI_ACCOUNT")
            or _file_config().get("account")
            or None)


# --- Embedding endpoint (shared RIKEN infrastructure) -----------------------
# Endpoint and model are hardcoded constants: the committed embeddings.npy is
# tied to this exact model, so changing the model at query time would silently
# produce wrong cosine-similarity results. The only user-facing setting is the
# API key. With no key (or endpoint unreachable), docs search falls back to BM25.

EMBED_BASE_URL = "http://llm.ai.r-ccs.riken.jp:11434/v1"
EMBED_MODEL = "bge-m3:567m"


def embed_api_key() -> str:
    """API key for the embedding endpoint (the only user-configurable embedding setting).

    Resolved in order: HOKUSAI_EMBED_API_KEY, then RCCS_EMBED_API_KEY, then
    embedding.api_key in the config file. RCCS_EMBED_API_KEY is a shared fallback:
    the embedding endpoint is common RIKEN R-CCS infrastructure, so a user running
    several R-CCS plugins (e.g. this and the AI4S plugin) can export the one key
    once instead of repeating it in each plugin's config. Empty string means no
    auth header is sent.
    """
    file = _file_config().get("embedding", {})
    return (os.environ.get("HOKUSAI_EMBED_API_KEY")
            or os.environ.get("RCCS_EMBED_API_KEY")
            or file.get("api_key") or "")


# --- Static data ------------------------------------------------------------

# Prefer CLAUDE_PLUGIN_ROOT (set by the Claude Code plugin system at runtime)
# so data is found regardless of install layout. Fall back to __file__-relative
# for development runs directly from the source tree.
_DATA_DIR = (
    Path(os.environ["CLAUDE_PLUGIN_ROOT"]) / "data"
    if "CLAUDE_PLUGIN_ROOT" in os.environ
    else Path(__file__).resolve().parent.parent.parent / "data"
)

DOCS_INDEX_DIR = Path(os.environ.get("HOKUSAI_DOCS_INDEX", _DATA_DIR / "docs_index"))
# The documentation source is our own original guide (data/hokusai_guide.md) —
# facts in our own words, not a copy of the vendor manual — so it is committed
# and the index can be freely distributed. `rag.ingest` chunks it by heading.
DOCS_SOURCE = Path(os.environ.get("HOKUSAI_DOCS_SOURCE", _DATA_DIR / "hokusai_guide.md"))
DOCS_SITE_BASE = "https://hokusai.riken.jp/hbw2/"


@lru_cache(maxsize=1)
def load_cluster_config() -> dict:
    """Load the static HBW2 description (partitions, modules, storage)."""
    path = Path(os.environ.get("HOKUSAI_CLUSTER_CONFIG", _DATA_DIR / "hokusai_config.json"))
    with open(path) as f:
        return json.load(f)
