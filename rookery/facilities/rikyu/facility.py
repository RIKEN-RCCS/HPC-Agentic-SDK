"""RIKYU (RIKEN AI4S / GB200) registration — see PORTING.md.

RIKYU is Slurm, single GPU vendor (NVIDIA), a job-total `--gpus=N` GPU
request style, and Slurm derives node count from the GPU count (no job
script in the RIKYU user guide ever sets --nodes explicitly). Accounting
(sacct/sacctmgr) is available — the first row of PORTING.md's dialect
table, and hpc_agent_core.compute.slurm.SlurmBackend's own docstring lists
Rikyu by name as a verified `has_accounting=True,
gpu_request_style="gpus_total"` facility — no override of
nodes_always_explicit or gpu_vendor_map is needed.

RIKYU only accepts a fixed set of per-job GPU counts (see rikyu_config.json's
job_resources.supported_gpu_counts) and has exactly one partition, "gpu" —
both facility-specific enough to live here as SchedulerBackend hook
overrides rather than in the generic server.

A user in more than one RIKYU project must also name which project to
charge; see _default_account() below. HBW2's facility.py solves the same
problem with similar-looking code — that duplication is deliberate (see
PORTING.md, "Where does this go?"): the two differ in their env var, their
config keys, and when the account is mandatory, and spelling each out
plainly here beats a shared abstraction that hides those differences.
"""
import os
from pathlib import Path

from hpc_agent_core import config
from hpc_agent_core.compute.slurm import SlurmBackend
from hpc_agent_core.models import JobSpec
from facilities.registry import register_backend

SLUG = "rikyu"

FACILITY = config.register_facility(
    slug=SLUG,
    display_name="RIKYU (RIKEN AI4S / GB200)",
    description="RIKEN AI4S GB200 GPU cluster (400 nodes, single 'gpu' "
                 "partition), Slurm with accounting, job-total GPU request.",
    default_host="login.rikyu.r-ccs.riken.jp",
    data_dir=Path(__file__).parent / "data",
    embed_base_url="http://llm.ai.r-ccs.riken.jp:11434/v1",  # shared RIKEN R-CCS endpoint
    embed_model="bge-m3:567m",
    docs_cite_url="",  # RIKYU is in Early Access; leave blank per PORTING.md
    config_example={"ssh": {"host": "rikyu"}},
    setup_help=(
        "RIKYU accepts key-based SSH only. Generate a key if you don't have\n"
        "one (Ed25519 recommended; ECDSA P-521 or RSA >=2048 also accepted)\n"
        "and register the public key through RIKYU's Open OnDemand web portal\n"
        "on its 'SSH Public Key' page before the first login. Then add a\n"
        "'rikyu' alias to ~/.ssh/config pointing at\n"
        "login.rikyu.r-ccs.riken.jp, or set ssh.host to\n"
        "user@login.rikyu.r-ccs.riken.jp.\n"
        "If you belong to more than one RIKYU project, also add\n"
        "\"defaults\": {\"account\": \"<project>\"} — otherwise sbatch rejects\n"
        "jobs that don't name one. get_projects lists the projects you can\n"
        "charge once the connection works.\n"
        "Running on a RIKYU front-end node instead of a laptop? Use\n"
        "\"host\": \"localhost\" and no SSH key is needed at all."
    ),
)


def _default_account() -> str | None:
    """The RIKYU project to charge when a job doesn't name one.

    Resolved RIKYU_ACCOUNT > the user config's `defaults.account`. Unlike
    HBW2 this is *conditionally* required, not always: a user in exactly
    one project may omit --account entirely and sbatch picks it. A user in
    several gets a hard rejection instead ("You belong to multiple
    projects, so the project to be charged must be specified explicitly" —
    observed live), which is why the default is worth resolving here.
    """
    cfg = config.file_config(SLUG)
    return (os.environ.get(f"{FACILITY.env_prefix}_ACCOUNT")
            or (cfg.get("defaults") or {}).get("account"))


class RikyuBackend(SlurmBackend):
    def apply_defaults(self, spec: JobSpec) -> None:
        """RIKYU has exactly one partition, so a blank queue_name always
        means "gpu"; a configured project is filled in when the caller
        didn't name one.

        Deliberately does *not* raise when no account can be resolved —
        that's the difference from HBW2. Being in a single project is a
        perfectly valid RIKYU setup where sbatch supplies the account
        itself, so refusing to submit would break those users. A
        multi-project user with nothing configured still gets sbatch's own
        rejection, which names the problem clearly enough.
        """
        if not spec.attributes.queue_name:
            spec.attributes.queue_name = "gpu"
        if spec.attributes.account is None:
            spec.attributes.account = _default_account()

    def validate_spec(self, spec: JobSpec) -> None:
        """RIKYU only accepts these GPU counts per job (Job Resources guide
        page) — everything else about the resource ceiling (node count, CPU
        cores, memory) follows deterministically from this count, so a bad
        count is worth catching before submission rather than as a
        confusing sbatch-time rejection."""
        if spec.attributes.queue_name != "gpu":
            raise ValueError(
                "RIKYU has exactly one partition, 'gpu'. Set "
                "spec.attributes.queue_name to 'gpu' or leave it blank so "
                "apply_defaults can supply it."
            )

        gpus = spec.resources.gpus or spec.resources.gpu_cores_per_process
        if not gpus:
            return
        facts = config.load_facts(SLUG)["job_resources"]
        supported = facts["supported_gpu_counts"]
        if gpus not in supported:
            raise ValueError(
                f"RIKYU only accepts these GPU counts per job: {supported}. Got {gpus}."
            )
        limits = next(row for row in facts["table"] if row["gpus"] == gpus)
        resources = spec.resources
        if ("node_count" in resources.model_fields_set
                and resources.node_count != limits["nodes"]):
            raise ValueError(
                f"RIKYU derives {limits['nodes']} node(s) from a {gpus}-GPU "
                f"request, but node_count={resources.node_count} was set. "
                "Use that derived node count or omit node_count and let Slurm "
                "place the job."
            )
        if resources.cpu_cores_per_process:
            tasks_per_node = resources.processes_per_node
            if resources.process_count:
                tasks_per_node = (
                    resources.process_count + limits["nodes"] - 1
                ) // limits["nodes"]
            cores_per_node = resources.cpu_cores_per_process * tasks_per_node
            if cores_per_node > limits["max_cpu_cores_per_node"]:
                raise ValueError(
                    f"A {gpus}-GPU RIKYU job allows at most "
                    f"{limits['max_cpu_cores_per_node']} CPU cores per node; "
                    f"this spec requests {cores_per_node}. Reduce "
                    "cpu_cores_per_process or processes_per_node."
                )
        if resources.memory:
            max_bytes = limits["max_mem_per_node_gb"] * 1024**3
            if resources.memory > max_bytes:
                raise ValueError(
                    f"A {gpus}-GPU RIKYU job allows at most "
                    f"{limits['max_mem_per_node_gb']} GiB per node. Reduce "
                    "resources.memory or request more GPUs."
                )


BACKEND = RikyuBackend(
    facility=SLUG,
    has_accounting=True,
    gpu_request_style="gpus_total",
    jobs_dir="agent/jobs",  # the default; RIKYU has no reason to override it
)
register_backend(SLUG, BACKEND)
