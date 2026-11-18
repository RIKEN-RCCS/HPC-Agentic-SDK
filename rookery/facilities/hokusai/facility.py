"""HOKUSAI BigWaterfall2 (HBW2) registration — see PORTING.md.

HBW2 is Slurm with accounting on (every job is billed to a project under a
fair-share budget, so sacct/sacctmgr/sshare are available), requests GPUs
with the job-total `--gpus=N` flag, has a single GPU vendor (NVIDIA H100 ->
`--nv` for containers), and lets Slurm derive node count from the GPU count
(so `--nodes` is only emitted when the caller asks for more than one node).
That's the first row of PORTING.md §6's dialect table — every other knob
keeps its default.

Two things make HBW2 the first facility to need extension points beyond a
plain SlurmBackend construction:

1. **`--account` is mandatory on every job**, and the project ID is a
   *per-user* choice, not a bundled cluster fact — so apply_defaults()
   reads it from the user's own config file (or an env var) and raises a
   clear, actionable error when none can be resolved, rather than letting
   sbatch reject the job with its own opaque message.
2. **Fair-share standing governs when a queued job starts**, so
   get_projects() reports it alongside the plain associations the base
   SlurmBackend already returns.
"""
import os
from pathlib import Path

from hpc_agent_core import config
from hpc_agent_core.compute.slurm import SlurmBackend
from hpc_agent_core.middleware import run_command
from hpc_agent_core.models import JobSpec
from facilities.registry import register_backend

SLUG = "hokusai"

FACILITY = config.register_facility(
    slug=SLUG,
    display_name="HOKUSAI BigWaterfall2 (HBW2)",
    description="RIKEN HOKUSAI BigWaterfall2: CPU-first Slurm cluster "
                 "(312-node MPC partition, plus large-memory and NVIDIA H100 "
                 "GPU subsystems). Requires a project account on every job.",
    default_host="hokusai",
    data_dir=Path(__file__).parent / "data",
    embed_base_url="http://llm.ai.r-ccs.riken.jp:11434/v1",  # shared RIKEN R-CCS endpoint
    embed_model="bge-m3:567m",
    docs_cite_url="",  # the HBW2 portal is auth-gated, not a stable public docs URL
    config_example={
        "ssh": {"host": "hokusai"},
        "defaults": {"account": "RB99999"},
    },
    setup_help=(
        "HBW2 accepts key-based SSH only — there are no password prompts.\n"
        "Register your public key at https://hokusai.riken.jp/hbw2/ before the\n"
        "first login, then either add a 'hokusai' alias to ~/.ssh/config\n"
        "pointing at hokusai.riken.jp, or set ssh.host to user@hokusai.riken.jp.\n"
        "Set defaults.account to the project to bill: every HBW2 job requires\n"
        "one (RIKEN IDs start RB, HPCI-derived ones start HP).\n"
        "Running on an HBW2 front-end node instead of a laptop? Use\n"
        "\"host\": \"localhost\" and no SSH key is needed at all."
    ),
)


def _default_account() -> str | None:
    """The project/account to charge when a job doesn't name one.

    Resolved HOKUSAI_ACCOUNT > the user config's `defaults.account` > the
    pre-migration top-level `account` key. That last fallback matters: an
    older HBW2 README's example config was `{"ssh": ..., "account":
    "RB999999"}`, and dropping it would silently strip the default from
    anyone with a config file predating the `defaults` object, leaving them
    hitting the "name a project" error on every submit.
    """
    cfg = config.file_config(SLUG)
    return (os.environ.get(f"{FACILITY.env_prefix}_ACCOUNT")
            or (cfg.get("defaults") or {}).get("account")
            or cfg.get("account"))


class HokusaiBackend(SlurmBackend):
    def apply_defaults(self, spec: JobSpec) -> None:
        """Fill in HBW2's default partition and the user's default project.

        HBW2 requires an account on every job, so a spec with no account
        and no configured default fails here with a message naming the fix,
        rather than reaching sbatch.
        """
        if not spec.attributes.queue_name:
            spec.attributes.queue_name = (
                config.load_facts(SLUG).get("defaults", {}).get("partition", "mpc")
            )
        if spec.attributes.account is None:
            spec.attributes.account = _default_account()
        if not spec.attributes.account:
            raise ValueError(
                "No project named. Every HBW2 job is billed to a project, so "
                "--account is mandatory. Set spec.attributes.account to a "
                "project ID (RIKEN 'RB...' or HPCI 'HP...'), or configure a "
                f"default under defaults.account in {config.config_path(SLUG)}. "
                "Use get_projects to see which accounts you may charge."
            )

    def get_projects(self) -> list[dict]:
        """The base associations, plus each account's fair-share standing.

        On HBW2 the fair-share number is the thing that actually explains
        when a queued job will start, so it's worth the second round trip.
        It moves continuously — read it live rather than assuming a cached
        value.
        """
        projects = super().get_projects()
        share = run_command(
            self.facility,
            "sshare -U --parsable2 --noheader --format=Account,FairShare,RawUsage",
        )
        fairshare: dict[str, dict] = {}
        for line in share.strip().splitlines():
            parts = line.split("|")
            if len(parts) >= 3 and parts[0].strip():
                fairshare[parts[0].strip()] = {
                    "fairshare": parts[1].strip(),
                    "raw_usage": parts[2].strip(),
                }
        return [{**p, **fairshare.get(p["account"], {})} for p in projects]


BACKEND = HokusaiBackend(
    facility=SLUG,
    has_accounting=True,
    gpu_request_style="gpus_total",
    # jobs_dir defaults to "agent/jobs" -> ~/agent/jobs, per the visible-
    # directory bias; no reason to override it on HBW2.
)
register_backend(SLUG, BACKEND)
