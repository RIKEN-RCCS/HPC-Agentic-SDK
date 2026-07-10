"""RIKYU settings registration — see PORTING.md §5.

Calls hpc_agent_core.config.configure() once, at import time, before any
other hpc_agent_core module is used. Every other rikyu_mcp module imports
this module first (even if only for its side effect) so the registration
has already happened by the time middleware/compute/docs_server run.
"""
import json
from functools import lru_cache

from hpc_agent_core import config as _core

_core.configure(
    env_prefix="RIKYU",                 # -> RIKYU_HOST, RIKYU_CONFIG, RIKYU_EMBED_API_KEY
    default_host="login.rikyu.r-ccs.riken.jp",
    package="rikyu_mcp",
    embed_base_url="http://llm.ai.r-ccs.riken.jp:11434/v1",  # shared RIKEN R-CCS endpoint
    embed_model="bge-m3:567m",
    docs_cite_url="",                    # RIKYU is in Early Access; leave blank per PORTING.md §3
)

# Re-exported for readability at call sites — these are just the registered
# functions/values, not new definitions.
ssh_host = _core.ssh_host
embed_api_key = _core.embed_api_key
CONFIG_PATH = _core.config_path()
DATA_DIR = _core.data_dir()


@lru_cache(maxsize=1)
def load_cluster_config() -> dict:
    """RIKYU's static facts (partitions, job-resource table, storage,
    modules, spack) — bundled package data, not the user's config file."""
    with open(DATA_DIR / "rikyu_config.json") as f:
        return json.load(f)
