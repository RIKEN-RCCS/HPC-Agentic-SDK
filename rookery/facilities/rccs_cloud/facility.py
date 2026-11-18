"""R-CCS Cloud registration — see PORTING.md.

The R-CCS Cloud is a Slurm cluster with accounting enabled (`sacct` works).
Its GPU dialect is the one combination that a single "style" enum can't
express and that hpc_agent_core.compute.slurm.SlurmBackend documents by
name:

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
`#SBATCH` header (PORTING.md: override the single method that differs,
reusing the base helpers). Everything else — submit, status parsing,
cancel, live resources — is the generic backend unchanged.

Unlike RIKYU, there's no single sensible default partition to fill in for a
blank queue_name (the whole point of this facility is choosing among CPU/
NVIDIA/AMD/Intel GPU partitions), so default_queue_name/validate_spec are
left at the base class's no-ops.
"""
from pathlib import Path

from hpc_agent_core import config
from hpc_agent_core.compute.base import render_body
from hpc_agent_core.compute.slurm import SlurmBackend
from facilities.registry import register_backend

SLUG = "rccs-cloud"

FACILITY = config.register_facility(
    slug=SLUG,
    display_name="R-CCS Cloud",
    description="RIKEN R-CCS Cloud: heterogeneous ~20-partition cluster "
                 "(CPU-only, NVIDIA/AMD/Intel GPU), Slurm with accounting, "
                 "job-total GPU request with always-explicit --nodes.",
    default_host="rccs-cloud",
    data_dir=Path(__file__).parent / "data",
    embed_base_url="http://llm.ai.r-ccs.riken.jp:11434/v1",  # shared RIKEN R-CCS endpoint
    embed_model="bge-m3:567m",
    docs_cite_url="",  # the guide is our own words; no live site we're confident to cite
    # Both kept verbatim from the original repo's data/ (that repo's package
    # was named cloud_mcp, not rccs_cloud_mcp, so the filenames don't match
    # the slug-derived default).
    facts_filename="cloud_config.json",
    docs_filename="cloud_guide.md",
    config_example={"ssh": {"host": "rccs-cloud"}},
    setup_help=(
        "The R-CCS Cloud accepts key-based SSH only. Add an 'rccs-cloud'\n"
        "alias to ~/.ssh/config pointing at login.cloud.r-ccs.riken.jp with\n"
        "your key, or set ssh.host to user@login.cloud.r-ccs.riken.jp.\n"
        "No project account is needed — jobs without one use your default\n"
        "Slurm account.\n"
        "Running on an R-CCS Cloud front-end node instead of a laptop? Use\n"
        "\"host\": \"localhost\" and no SSH key is needed at all."
    ),
)


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


BACKEND = CloudSlurmBackend(
    facility=SLUG,
    has_accounting=True,
    gpu_request_style="gpus_total",
    nodes_always_explicit=True,
    no_gpu_flag_prefixes=frozenset({"qc-gh200", "ng-dgx-m"}),
    # jobs_dir defaults to "agent/jobs" -> ~/agent/jobs on the cluster, per
    # the "bias agent files into one visible directory" invariant.
)
register_backend(SLUG, BACKEND)
