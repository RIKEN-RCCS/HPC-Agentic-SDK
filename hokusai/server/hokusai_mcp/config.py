"""HOKUSAI BigWaterfall2 (HBW2) settings, registered with hpc-agent-core.

This module calls `hpc_agent_core.config.configure(...)` once, at import
time, before any other hpc_agent_core module touches config. Every other
module in this package (`compute`, `hpc_server`, `docs_server`, `doctor`)
imports this module first so the registration has already happened.

Settings resolve in order: environment variable > the user's config file >
the default registered here. The user config file lives at the common
`~/.hpc-agent/hokusai.json` (see hpc_agent_core.config for the exact
resolution, including the legacy `~/.hokusai/config.json` fallback).
"""
import json
import os
from functools import lru_cache

from hpc_agent_core import config as _core

_core.configure(
    env_prefix="HOKUSAI",            # -> HOKUSAI_HOST, HOKUSAI_CONFIG, HOKUSAI_EMBED_API_KEY
    default_host="hokusai",           # ssh.host fallback: an alias in ~/.ssh/config, or user@hostname
    package="hokusai_mcp",            # matches this package's actual name
    embed_base_url="http://llm.ai.r-ccs.riken.jp:11434/v1",  # shared RIKEN R-CCS endpoint
    embed_model="bge-m3:567m",
    docs_cite_url="",                 # blank: the HBW2 portal is an auth-gated site, not a stable public docs URL (PORTING.md §3)
    # No computer_defaults: HBW2 login nodes work with the shared defaults
    # (bash login-shell template, bash submitter, python3, key-based SSH).
)

# Re-export the registered values/functions the rest of the package imports
# from here (kept for readability at call sites):
ssh_host = _core.ssh_host
embed_api_key = _core.embed_api_key
CONFIG_PATH = _core.config_path()
DATA_DIR = _core.data_dir()


@lru_cache(maxsize=1)
def load_cluster_config() -> dict:
    """HBW2's static facts (partitions, subsystems, storage, modules, GPU
    dialect) — bundled package data, not the user's config file."""
    with open(DATA_DIR / "hokusai_config.json") as f:
        return json.load(f)


def _user_config() -> dict:
    """The user's config file parsed, or {} if absent/malformed. Read at
    call time (never at import) so a missing config never blocks startup."""
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def default_account() -> str | None:
    """The project/account to charge when a job doesn't name one.

    HBW2 requires `--account` on every job, but the project ID is a
    per-user choice, so it belongs in the user's config (or an env var),
    not in the bundled cluster facts. Resolves HOKUSAI_ACCOUNT, then the
    config file's `defaults.account`, then the pre-migration top-level
    `account` key (the old README's example config was `{"ssh": ...,
    "account": "RB999999"}` — without this fallback, anyone with an
    existing config file from before this schema changed would silently
    lose their default and start hitting the "name a project" error on
    every submit_job), then None.
    """
    user_config = _user_config()
    return (os.environ.get("HOKUSAI_ACCOUNT")
            or (user_config.get("defaults") or {}).get("account")
            or user_config.get("account"))


def default_partition() -> str:
    """The partition to use when a job doesn't name one (mpc by default)."""
    return load_cluster_config().get("defaults", {}).get("partition", "mpc")
