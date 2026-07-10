"""Scheduler wiring for the R-CCS Cloud.

The R-CCS Cloud is a Slurm cluster with accounting enabled (`sacct` works).
Its GPU dialect, per the R-CCS Cloud guide, is the one combination that a
single "style" enum can't express and that `hpc_agent_core.compute.slurm`
documents by name:

- GPUs are requested with the job-total flag ``--gpus=<n>`` (gpu_request_style
  = "gpus_total"), but ...
- ``--nodes`` is **always emitted explicitly** (nodes_always_explicit=True) —
  Slurm here does not derive node placement from the GPU count, and ...
- the unified CPU+GPU superchip partitions (``qc-gh200`` and the ``ng-dgx-m*``
  family) take **no** GPU flag at all — the GPU is always present, so
  ``--gpus``/``--gres`` would be wrong to emit (no_gpu_flag_prefixes).

The one thing the generic backend cannot know is machine-specific: **every
R-CCS Cloud batch script must `source /etc/profile` before any `module`
command**, and the batch shebang is a non-login shell, so nothing sources it
for us. We subclass SlurmBackend to inject that one line right after the
`#SBATCH` header (PORTING.md §6: override the single method that differs,
reusing the base helpers). Everything else — submit, status parsing,
cancel, live resources — is the generic backend unchanged.
"""
from hpc_agent_core.compute.base import render_body
from hpc_agent_core.compute.slurm import SlurmBackend
from cloud_mcp import config  # noqa: F401 -- import for its configure() side effect,
# so `import cloud_mcp.compute` in isolation (a test, a REPL) has config
# registered before anything here talks to the cluster.


class CloudSlurmBackend(SlurmBackend):
    """SlurmBackend that emits `source /etc/profile` before the job body.

    Required on the R-CCS Cloud: `module` is only defined after
    `/etc/profile` runs, and a batch script's `#!/bin/bash` is not a login
    shell, so module loads in `executable` would otherwise fail with
    "module: command not found". The generic backend deliberately stays
    machine-neutral and does not emit this, so we add it here.
    """

    def render_script(self, spec) -> str:
        res = spec.resources
        gpu_requested = bool(res.gpus or res.gpu_cores_per_process)
        vendor_flag = self._resolve_gpu_vendor_flag(spec.attributes.queue_name)
        header = "\n".join(self._header(spec))
        # render_body starts with a blank line, so this reads as:
        #   <#SBATCH header>
        #   source /etc/profile
        #   <exports / executable / ...>
        return header + "\nsource /etc/profile" + render_body(spec, gpu_requested, vendor_flag)


backend = CloudSlurmBackend(
    has_accounting=True,
    gpu_request_style="gpus_total",
    nodes_always_explicit=True,
    no_gpu_flag_prefixes=frozenset({"qc-gh200", "ng-dgx-m"}),
    # jobs_dir defaults to "agent/jobs" -> ~/agent/jobs on the cluster, per
    # the "bias agent files into one visible directory" invariant.
)

# hpc_server.py calls these:
submit = backend.submit
get_statuses = backend.get_statuses
get_recent_statuses = backend.get_recent_statuses
cancel = backend.cancel
render_script = backend.render_script
get_live_resources = backend.get_live_resources
get_drained_nodes = backend.get_drained_nodes
