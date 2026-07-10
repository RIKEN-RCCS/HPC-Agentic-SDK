"""Settings for the R-CCS Cloud MCP plugin.

This module is a thin registration layer over `hpc_agent_core.config`: it
calls `configure(...)` once, at import time, before any other
`hpc_agent_core` module that reads config is used, then re-exports the
registered values for readability at call sites.

Settings resolve in order: environment variable > the user config file >
the registered default. The user config file lives at the common location
`~/.hpc-agent/rccs_cloud.json` (see `hpc_agent_core.config.config_path()`).
The legacy per-machine path `~/.rccs-cloud/config.json` is still honored if
it is the only one that exists, so anyone who configured an earlier build of
this plugin keeps working without changes.

Example config file:

    {
      "ssh": {"host": "rccs-cloud"},
      "embedding": {"api_key": "..."}
    }

`ssh.host` is a `~/.ssh/config` alias or a plain `user@hostname`; key-based
auth is assumed (no credentials are stored here). The embedding endpoint and
model are fixed per machine (the committed docs-index vectors are tied to the
model) — only the API key is user-configurable.
"""
import json
from functools import lru_cache

from hpc_agent_core import config as _core

_core.configure(
    env_prefix="RCCS_CLOUD",            # -> RCCS_CLOUD_HOST, RCCS_CLOUD_CONFIG, RCCS_CLOUD_EMBED_API_KEY
    default_host="rccs-cloud",           # ssh.host fallback: an alias in ~/.ssh/config, or user@hostname
    package="cloud_mcp",                 # matches this package's actual name (for bundled data)
    embed_base_url="http://llm.ai.r-ccs.riken.jp:11434/v1",  # shared RIKEN R-CCS endpoint
    embed_model="bge-m3:567m",
    docs_cite_url="",                    # blank: the guide is our own words; no live site we're confident to cite
    config_dir_name=".rccs-cloud",       # legacy path ~/.rccs-cloud/config.json, kept working for existing users
    # No computer_defaults: the login node works with the shared bash
    # login-shell defaults (see hpc_agent_core.config._BASE_COMPUTER_DEFAULTS).
)

# Re-export the registered functions/values the rest of the package imports
# from here (kept for readability — these are just the core's registered API):
ssh_host = _core.ssh_host
embed_api_key = _core.embed_api_key
CONFIG_PATH = _core.config_path()
EMBED_BASE_URL = _core.embed_base_url()
EMBED_MODEL = _core.embed_model()
DATA_DIR = _core.data_dir()


@lru_cache(maxsize=1)
def load_cluster_config() -> dict:
    """The R-CCS Cloud's static facts (partitions, modules, storage) —
    bundled package data, not the user's config file."""
    with open(DATA_DIR / "cloud_config.json") as f:
        return json.load(f)
