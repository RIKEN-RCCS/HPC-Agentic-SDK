"""Fugaku settings, registered with hpc-agent-core.

This module calls `hpc_agent_core.config.configure(...)` once, at import
time, before any other hpc_agent_core module touches config. Every other
module in this package (`compute`, `hpc_server`, `docs_server`, `doctor`)
imports this module first so the registration has already happened.

Settings resolve in order: environment variable > the user's config file >
the default registered here. The user config file lives at the common
`~/.hpc-agent/fugaku.json` (see hpc_agent_core.config for the exact
resolution, including the legacy `~/.fugaku/config.json` fallback):

    {
      "ssh": {"host": "fugaku"},
      "defaults": {"group": "ra000009", "gfscache_volume": "/vol0004"}
    }

Every Fugaku job submission requires a project group ("-g <groupname>",
enforced by pjsub itself with PJM 0071 if omitted or unauthorized — the
shared "fugaku" group all accounts belong to cannot submit jobs). This is
genuinely per-user/per-project policy, so it is never hardcoded here —
resolved via default_group() below, same pattern as Miyabi's default_group()
for PBS's -W group_list.
"""
import json
import os
from functools import lru_cache

from hpc_agent_core import config as _core

_core.configure(
    env_prefix="FUGAKU",                 # -> FUGAKU_HOST, FUGAKU_CONFIG, FUGAKU_EMBED_API_KEY
    default_host="fugaku",                # ssh.host fallback: an alias in ~/.ssh/config, or user@login.fugaku.r-ccs.riken.jp
    package="fugaku_mcp",                 # matches this package's actual name
    embed_base_url="http://llm.ai.r-ccs.riken.jp:11434/v1",  # shared RIKEN R-CCS endpoint (same as Rikyu-Agent)
    embed_model="bge-m3:567m",
    docs_cite_url="",                     # left blank per PORTING.md §3 — no confirmed-stable public URL to cite
)

# Re-export what the rest of the package imports from here — these are just
# the registered functions/values, kept for readability at call sites:
ssh_host = _core.ssh_host
embed_api_key = _core.embed_api_key
CONFIG_PATH = _core.config_path()
DATA_DIR = _core.data_dir()


@lru_cache(maxsize=1)
def load_cluster_config() -> dict:
    """Fugaku's static facts (resource groups, storage, modules) — bundled
    package data, not the user's config file."""
    with open(DATA_DIR / "fugaku_config.json") as f:
        return json.load(f)


def _user_config() -> dict:
    """The user's config file parsed, or {} if absent/malformed. Read at
    call time (never at import) so a missing config never blocks startup."""
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def default_group() -> str | None:
    """The project group ("-g <groupname>") charged when a job doesn't set
    attributes.account explicitly. Resolved: FUGAKU_GROUP env var, then
    defaults.group in the config file, else None — in which case submit_job
    raises a clear error rather than letting pjsub reject the job with the
    opaque "PJM 0071 Group not authorized" message."""
    return (os.environ.get("FUGAKU_GROUP")
            or (_user_config().get("defaults") or {}).get("group"))


def default_gfscache_volume() -> str | None:
    """The second-layer storage volume (e.g. "/vol0004") a job's
    #PJM -x PJM_LLIO_GFSCACHE= declares it will touch. Required by pjsub
    whenever a job's working directory sits outside $HOME, or when using
    Spack (also under /vol0004) — see LayeredStorageAndLLIO/SelectAvailableVolumes
    in the bundled guide. Per-project (assigned by RIKEN), so never
    hardcoded: FUGAKU_GFSCACHE env var, then defaults.gfscache_volume in the
    config file, else None (the flag is simply omitted; fine for jobs that
    stay under $HOME)."""
    return (os.environ.get("FUGAKU_GFSCACHE")
            or (_user_config().get("defaults") or {}).get("gfscache_volume"))
