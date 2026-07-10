"""HBW2's scheduler backend: a config-driven Slurm backend from hpc-agent-core.

HBW2 is Slurm with accounting on (every job is billed to a project under a
fair-share budget, so sacct/sacctmgr are available for status and history),
requests GPUs with the job-total `--gpus=N` flag, has a single GPU vendor
(NVIDIA H100 -> `--nv` for containers), and lets Slurm derive node count
from the GPU count (so `--nodes` is only emitted when the caller asks for
more than one node). That is exactly the first row of PORTING.md §6's table:

    SlurmBackend(has_accounting=True, gpu_request_style="gpus_total")

all the other knobs keep their defaults (single vendor "--nv",
nodes_always_explicit=False derived for "gpus_total", no suppressed-GPU-flag
partitions).
"""
from hpc_agent_core.compute.slurm import SlurmBackend
from hokusai_mcp import config  # noqa: F401 -- imported for its configure() side effect.
# Import config even though nothing below references it directly: SlurmBackend's
# constructor doesn't need config yet, but this module must not depend on being
# imported *after* config by whoever imports it (importing hokusai_mcp.compute
# in isolation — a test or REPL — would otherwise crash the first time anything
# here actually talks to the cluster, since configure() would never have run).

backend = SlurmBackend(
    has_accounting=True,
    gpu_request_style="gpus_total",
    # jobs_dir defaults to "agent/jobs" — the ~/agent/ visible-directory bias
    # (PORTING.md §10); no reason to override it on HBW2.
)

# hpc_server.py calls these:
submit = backend.submit
get_statuses = backend.get_statuses
get_recent_statuses = backend.get_recent_statuses
cancel = backend.cancel
render_script = backend.render_script
get_live_resources = backend.get_live_resources
get_drained_nodes = backend.get_drained_nodes
