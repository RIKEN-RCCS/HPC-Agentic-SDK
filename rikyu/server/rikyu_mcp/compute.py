"""RIKYU's SchedulerBackend — see PORTING.md §6.

RIKYU is Slurm, single GPU vendor (NVIDIA), a job-total `--gpus=N` GPU
request style, and Slurm derives node count from the GPU count (no job
script in the RIKYU user guide ever sets --nodes explicitly). Accounting
(sacct/sacctmgr) is available. This is exactly the first row of PORTING.md
§6's table, and hpc-agent-core's own SlurmBackend docstring lists Rikyu by
name as a verified `has_accounting=True, gpu_request_style="gpus_total"`
machine — no override of nodes_always_explicit or gpu_vendor_map is needed.
"""
from hpc_agent_core.compute.slurm import SlurmBackend
from rikyu_mcp import config  # noqa: F401 -- registers via configure(); this
# module must not rely on being imported after config by whoever imports it.

backend = SlurmBackend(
    has_accounting=True,
    gpu_request_style="gpus_total",
    jobs_dir="agent/jobs",   # the default; RIKYU has no reason to override it
)

submit = backend.submit
get_statuses = backend.get_statuses
get_recent_statuses = backend.get_recent_statuses
cancel = backend.cancel
render_script = backend.render_script
get_live_resources = backend.get_live_resources
get_drained_nodes = backend.get_drained_nodes
