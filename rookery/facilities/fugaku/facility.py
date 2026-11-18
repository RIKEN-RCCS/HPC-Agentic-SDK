"""Fugaku (RIKEN R-CCS) registration — see PORTING.md.

Fugaku is the first onboarded facility that isn't Slurm. It's scheduled by
Fujitsu's PJM (pjsub/pjstat/pjdel/pjalter), so it takes PORTING.md §6's
explicit fallback: `compute.py` here subclasses `SchedulerBackend` directly
rather than forcing a fit onto `SlurmBackend`.

That backend lives in this facility's own directory, not in
`hpc_agent_core/compute/`, because Fugaku is currently the only PJM machine
onboarded. If a second Fujitsu/PJM facility appears, the dialect half
(pjstat parsing, state mapping, the `#PJM` header) is worth promoting to
core the way `gridengine.py` was — but promoting one machine's backend
speculatively would just be guessing at what the second one needs.

Two settings are per-user rather than cluster facts, so they come from the
user's own config file (§5a) and are resolved in apply_defaults():

1. **A project group is mandatory on every job** (`#PJM -g <group>`). The
   shared "fugaku" group that every account belongs to is explicitly denied
   job submission, so there is no usable fallback — an unset group is a
   hard error here, as on HBW2.
2. **The second-layer storage volume** (`PJM_LLIO_GFSCACHE`) is assigned
   per project and is required whenever a job touches anything outside
   $HOME. Optional: omitted cleanly for jobs that stay in $HOME.
"""
import os
from pathlib import Path

from hpc_agent_core import config
from hpc_agent_core.models import JobSpec
from facilities.fugaku.compute import PJMBackend
from facilities.registry import register_backend

SLUG = "fugaku"

FACILITY = config.register_facility(
    slug=SLUG,
    display_name="Fugaku",
    description="RIKEN R-CCS Fugaku: 158,976-node A64FX (Arm SVE) system, "
                 "Fujitsu PJM scheduler, no GPUs. A project group is mandatory "
                 "on every job.",
    default_host="fugaku",
    data_dir=Path(__file__).parent / "data",
    embed_base_url="http://llm.ai.r-ccs.riken.jp:11434/v1",  # shared RIKEN R-CCS endpoint
    embed_model="bge-m3:567m",
    docs_cite_url="",  # no confirmed-stable public URL to cite
    config_example={
        "ssh": {"host": "fugaku"},
        "defaults": {"group": "hp000000", "gfscache_volume": "/vol0004"},
    },
    setup_help=(
        "Fugaku accepts key-based SSH only, through RIKEN's login gateway.\n"
        "Add a 'fugaku' alias to ~/.ssh/config pointing at your login node,\n"
        "or set ssh.host to user@login.fugaku.r-ccs.riken.jp.\n"
        "Set defaults.group to your project group: every Fugaku job needs\n"
        "one (#PJM -g), and the shared 'fugaku' group every account belongs\n"
        "to is denied job submission, so there is no usable fallback. Run\n"
        "`id` on the login node to see your real project groups.\n"
        "Set defaults.gfscache_volume (e.g. /vol0004) if your work touches\n"
        "second-layer storage outside $HOME, including Spack — it is\n"
        "assigned per project. Leave it out for jobs that stay in $HOME."
    ),
)


def _default_group() -> str | None:
    """The project group charged when a job doesn't name one.

    FUGAKU_GROUP > defaults.group. Unlike RIKYU's optional account, this is
    mandatory (see apply_defaults) because Fugaku's shared group cannot
    submit.
    """
    cfg = config.file_config(SLUG)
    return (os.environ.get(f"{FACILITY.env_prefix}_GROUP")
            or (cfg.get("defaults") or {}).get("group"))


def _default_gfscache_volume() -> str | None:
    """The second-layer storage volume a job declares it will touch.

    FUGAKU_GFSCACHE > defaults.gfscache_volume. Optional: omitted entirely
    for jobs that never leave $HOME.
    """
    cfg = config.file_config(SLUG)
    return (os.environ.get(f"{FACILITY.env_prefix}_GFSCACHE")
            or (cfg.get("defaults") or {}).get("gfscache_volume"))


class FugakuBackend(PJMBackend):
    def apply_defaults(self, spec: JobSpec) -> None:
        """Fill in the project group and storage volume from the user's
        config, and fail clearly if the mandatory group is missing."""
        # No queue_name default on purpose: PJM resource groups differ per
        # project, and which ones an account may use is only knowable from
        # `pjacl --rg <name>` for that account. Guessing "small" would be
        # wrong for some projects, so an unset queue_name stays unset and
        # the backend's own error names the fix.
        if spec.attributes.account is None:
            spec.attributes.account = _default_group()
        if not spec.attributes.account:
            raise ValueError(
                "Fugaku requires a project group on every job (pjsub -g "
                "<groupname>). Set spec.attributes.account, or configure a "
                f"default under defaults.group in {config.config_path(SLUG)} "
                f"(or the {FACILITY.env_prefix}_GROUP env var). The shared "
                "'fugaku' group cannot submit jobs — run "
                "run_command_on_cluster with 'id' to see the real project "
                "groups this account belongs to."
            )
        if "gfscache_volume" not in spec.attributes.custom_attributes:
            volume = _default_gfscache_volume()
            if volume:
                spec.attributes.custom_attributes["gfscache_volume"] = volume

    def validate_spec(self, spec: JobSpec) -> None:
        """Reject what Fugaku cannot do, rather than letting pjsub say it
        confusingly (or, worse, silently dropping the request).

        Both of these are checked in the backend's _header() too, since a
        rendered script must never be wrong — this just surfaces them at
        the same point every other facility surfaces its constraints.
        """
        if not spec.attributes.queue_name:
            raise ValueError(
                "Fugaku requires spec.attributes.queue_name — a PJM resource "
                "group such as 'small', 'large', or 'int'. There is no safe "
                "default: which groups an account may use differs per project. "
                "Use get_facility to see the documented groups, or run "
                "`pjacl --rg <name>` on the login node to confirm what this "
                "account can actually submit to."
            )
        volume = spec.attributes.custom_attributes.get("gfscache_volume", "")
        if "," in volume:
            raise ValueError(
                f"PJM_LLIO_GFSCACHE must name a single volume, not {volume!r}. "
                "A comma-separated value is accepted by pjsub and then fails "
                "the pre-execution gate check minutes later — the job ends in "
                "state ERR with REASON 'GATE CHECK', no output file and no "
                "exit code, which is very hard to diagnose after the fact "
                "(verified live). Use one volume, e.g. '/vol0004'. The syntax "
                "for declaring several volumes is not documented in the "
                "bundled guide or pjsub --help; confirm it with RIKEN rather "
                "than guessing a separator."
            )
        if spec.resources.gpus or spec.resources.gpu_cores_per_process:
            raise ValueError(
                "Fugaku's compute nodes (A64FX) have no GPUs — leave "
                "resources.gpus and resources.gpu_cores_per_process unset."
            )
        if spec.stdout_path or spec.stderr_path:
            raise ValueError(
                "pjsub has no option to redirect stdout/stderr. Output always "
                "lands at '<jobname>.<jobid>.out' and '.err' in the job's "
                "submission directory — leave stdout_path/stderr_path unset "
                "and set spec.directory instead."
            )


BACKEND = FugakuBackend(facility=SLUG)
register_backend(SLUG, BACKEND)
