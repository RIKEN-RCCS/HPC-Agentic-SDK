"""Configuration for the rikyu MCP servers.

Settings come from, in order of precedence:
  1. Environment variables (RIKYU_*)
  2. The user config file ~/.rikyu/config.json (path override: RIKYU_CONFIG)
  3. Defaults

The config file is created with the help of the `configuring` skill:

    {
      "ssh": {"host": "rikyu"},
      "embedding": {"api_key": "..."}
    }

`ssh.host` is an alias from ~/.ssh/config or a plain user@hostname; key-based
auth is assumed (no credentials are stored here). The embedding endpoint and
model are hardcoded constants (EMBED_BASE_URL / EMBED_MODEL) — changing them
requires a full re-ingest of the docs index.
"""
import json
import os
from contextlib import ExitStack
from functools import lru_cache
from importlib import resources
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("RIKYU_CONFIG", "~/.rikyu/config.json")).expanduser()


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
    """SSH destination for the AI4S login node (alias or user@hostname)."""
    return (os.environ.get("RIKYU_HOST")
            or _file_config().get("ssh", {}).get("host")
            or "rikyu")


EMBED_BASE_URL = "http://llm.ai.r-ccs.riken.jp:11434/v1"
EMBED_MODEL = "bge-m3:567m"


def embed_api_key() -> str:
    """API key for the embedding endpoint (the only user-configurable embedding setting).

    Resolved in order: RIKYU_EMBED_API_KEY, then RCCS_EMBED_API_KEY, then
    embedding.api_key in the config file. RCCS_EMBED_API_KEY is a shared fallback:
    the embedding endpoint is common RIKEN R-CCS infrastructure, so a user running
    several R-CCS plugins (e.g. this and the HOKUSAI plugin) can export the one key
    once instead of repeating it in each plugin's config. Empty string means no
    auth header is sent.
    """
    file = _file_config().get("embedding", {})
    return (os.environ.get("RIKYU_EMBED_API_KEY")
            or os.environ.get("RCCS_EMBED_API_KEY")
            or file.get("api_key") or "")


# --- Static data ------------------------------------------------------------

_RESOURCE_STACK = ExitStack()


def _bundled_data_dir() -> Path:
    """Filesystem path to package data, including zip-safe extraction fallback."""
    data = resources.files("rikyu_mcp") / "data"
    return _RESOURCE_STACK.enter_context(resources.as_file(data))


_DATA_DIR = _bundled_data_dir()

DOCS_INDEX_DIR = Path(os.environ.get("RIKYU_DOCS_INDEX", _DATA_DIR / "docs_index"))
DOCS_REPO_URL = "https://github.com/RIKEN-RCCS/ai4s_early_access"
DOCS_SITE_BASE = "https://riken-rccs.github.io/ai4s_early_access/en/"


@lru_cache(maxsize=1)
def load_cluster_config() -> dict:
    """Load the static AI4S cluster description (partitions, modules, storage)."""
    path = Path(os.environ.get("RIKYU_CLUSTER_CONFIG", _DATA_DIR / "ai4s_config.json"))
    with open(path) as f:
        return json.load(f)
