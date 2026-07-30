"""PJMBackend — pjsub/pjstat/pjdel/pjalter implementation for Fugaku.

Fugaku is scheduled by Fujitsu's PJM ("Job Operation Software"), not Slurm or
Grid Engine, so per hpc-agent-core's PORTING.md §6 explicit fallback, this
subclasses SchedulerBackend directly rather than forcing a fit — the same
approach IreneAgent's BridgeBackend and Miyabi-Agent's PBSBackend took for
their own non-Slurm/non-GridEngine dialects.

Facts below were confirmed two ways: (1) RIKEN's official "user-guide-use"
Sphinx docs (job execution, MPI, and layered-storage sections), and (2) live
commands run directly against a real Fugaku login node during this port
(whoami/groups, pjstat --help, pjacl --rg small/large, storage layout) — see
this repo's AGENTS.md "Validation status" section for exactly what was and
wasn't exercised with a real submitted job.

Distinctive Fugaku facts this backend encodes:
- A project group is mandatory on every submission (#PJM -g <groupname>);
  the shared "fugaku" group every account belongs to is explicitly denied
  job submission (confirmed live via `pjacl --rg small`: "pjsub + deny
  g(fugaku)") — never hardcoded, see config.default_group().
- Fugaku (A64FX) has no GPUs — resources.gpus/gpu_cores_per_process are
  rejected rather than silently ignored.
- pjsub has no flag to override stdout/stderr paths at all (confirmed by
  the absence of any -o/-e/--out/--err entry in the official pjsub option
  tables) — output always lands at "<jobname>.<jobid>.out"/".err" in the
  submission directory. spec.stdout_path/stderr_path are rejected with a
  clear error rather than silently ignored.
- Second-layer storage volumes (e.g. "/vol0004") must be declared via
  #PJM -x PJM_LLIO_GFSCACHE=<volume> whenever a job needs more than $HOME —
  per-project, so resolved via config.default_gfscache_volume(), never
  hardcoded.
- pjstat's live table has no exit-code column; a finished job's EXT/EXIT
  state means the scheduler considers it done, not that the application
  succeeded — callers must check the job's .out/.err file, same caveat
  Miyabi's PBSBackend documents for its own history view.
"""
from __future__ import annotations

import re
import shlex
import time

from hpc_agent_core.compute.base import SchedulerBackend, duration_to_hms, render_body
from hpc_agent_core.middleware import run_command, write_remote_file
from hpc_agent_core.models import Job, JobSpec, JobState, JobStatus
from fugaku_mcp import config  # noqa: F401 -- registers via configure(); this
# module must not rely on being imported after config by whoever imports it.

_jobs_dir = "agent/jobs"  # PORTING.md §10: bias agent-created files into one
# visible directory, matching SlurmBackend's default and every other port.

# Job model (MD) and status (ST) codes, verbatim from
# JobExecution/DisplayingJobStatus.rst.txt.
_MD_CODES = "NM|ST|BU|MW"
_ST_CODES = "ACC|CCL|ERR|EXT|HLD|QUE|RJT|RNA|RNE|RNO|RNP|RSM|RUN|SPD|SPP"

_STATE_MAP = {
    "ACC": JobState.QUEUED,     # ACCEPT: submission accepted, not yet running
    "QUE": JobState.QUEUED,     # QUEUED: waiting for execution order
    "HLD": JobState.HELD,       # HOLD: fixed in submitted state
    "SPD": JobState.HELD,       # SUSPENDED
    "SPP": JobState.HELD,       # SUSPEND: suspend processing
    "RNP": JobState.ACTIVE,     # RUNNING-P: prologue running
    "RUN": JobState.ACTIVE,     # RUNNING: executing
    "RNA": JobState.ACTIVE,     # RUNNING-A: resources acquired
    "RNE": JobState.ACTIVE,     # RUNNING-E: epilogue running
    "RNO": JobState.ACTIVE,     # RUNOUT: terminating
    "RSM": JobState.ACTIVE,     # RESUME: resume processing
    "EXT": JobState.COMPLETED,  # EXIT: finished — see module docstring's caveat
    "CCL": JobState.CANCELED,   # CANCEL: canceled by user/admin
    "ERR": JobState.FAILED,     # ERROR: canceled by job-management error
    "RJT": JobState.FAILED,     # REJECT: acceptance rejected
}

# Anchored on the MD/ST vocabularies (small, fixed sets) rather than fixed
# column widths, since START_DATE ("11/17 09:01:41") embeds a space and
# would otherwise misalign a plain whitespace split. Columns after ST, per
# the documented header
# "JOB_ID JOB_NAME MD ST USER START_DATE ELAPSE_LIM NODE_REQUIRE VNODE CORE V_MEM":
_PJSTAT_LINE_RE = re.compile(
    rf"^(?P<job_id>\d+)\s+(?P<job_name>\S+)\s+(?P<md>{_MD_CODES})\s+"
    rf"(?P<st>{_ST_CODES})\s+(?P<user>\S+)\s+(?P<rest>.*)$"
)


def _parse_pjstat_line(line: str) -> Job | None:
    m = _PJSTAT_LINE_RE.match(line.strip())
    if not m:
        return None
    rest = m.group("rest").split()
    # rest is [START_DATE (2 tokens, or "-")] ELAPSE_LIM NODE_REQUIRE VNODE CORE V_MEM
    if len(rest) >= 7:
        start_date, elapse_lim, node_require, vnode, core, vmem = (
            f"{rest[0]} {rest[1]}", rest[2], rest[3], rest[4], rest[5], rest[6]
        )
    elif len(rest) == 6:
        start_date, elapse_lim, node_require, vnode, core, vmem = (
            rest[0], rest[1], rest[2], rest[3], rest[4], rest[5]
        )
    else:
        start_date = elapse_lim = node_require = vnode = core = vmem = ""

    native = m.group("st")
    message = None
    if native == "EXT":
        message = ("Job finished (EXIT); pjstat does not report application exit "
                   "status here — check the job's <name>.<id>.out/.err file to "
                   "confirm success.")
    return Job(
        id=m.group("job_id"),
        status=JobStatus(
            state=_STATE_MAP.get(native, JobState.UNKNOWN),
            message=message,
            meta_data={
                "scheduler": "pjm",
                "native_state": native,
                "job_model": m.group("md"),
                "name": m.group("job_name"),
                "user": m.group("user"),
                "start_date": start_date,
                "elapse_limit": elapse_lim,
                "node_require": node_require,
                "vnode": vnode,
                "core": core,
                "v_mem": vmem,
            },
        ),
    )


def _run_optional(cmd: str) -> str:
    """Run a command, returning "" instead of raising on non-zero exit.

    pjstat/pjstat --history routinely exit non-zero (or print nothing) when
    there's simply nothing to show (e.g. no jobs queued) — this restores
    the tolerant behavior other non-Slurm backends in this family use for
    the same reason (Irene's BridgeBackend, the Grid Engine backend).
    """
    try:
        return run_command(cmd)
    except RuntimeError:
        return ""


def _parse_pjsub_job_id(output: str) -> str:
    """"[INFO] PJM 0000 pjsub Job 9714 submitted." -> "9714"."""
    m = re.search(r"[Jj]ob\s+(\d+)\s+submitted", output)
    return m.group(1) if m else ""


def _tasks(spec: JobSpec) -> int:
    res = spec.resources
    return res.process_count or max(1, res.node_count * res.processes_per_node)


class PJMBackend(SchedulerBackend):
    name = "pjm"

    def __init__(self, jobs_dir: str = _jobs_dir):
        self._jobs_dir = jobs_dir

    def _header(self, spec: JobSpec) -> list[str]:
        attrs, res = spec.attributes, spec.resources

        if res.gpus or res.gpu_cores_per_process:
            raise ValueError(
                "Fugaku's compute nodes (A64FX) have no GPUs — leave "
                "resources.gpus and resources.gpu_cores_per_process unset."
            )
        if spec.stdout_path or spec.stderr_path:
            raise ValueError(
                "Fugaku's pjsub has no flag to override stdout/stderr paths — "
                "job output always goes to '<jobname>.<jobid>.out' / '.err' in "
                "the submission directory. Leave stdout_path/stderr_path unset."
            )

        queue = attrs.queue_name
        if not queue:
            raise ValueError(
                "Fugaku requires spec.attributes.queue_name — a PJM resource "
                "group such as 'small', 'large', 'int', or a 'spot-*' variant. "
                "Call get_facility or search_docs to see the groups available "
                "to this account."
            )

        group = attrs.account or config.default_group()
        if not group:
            raise ValueError(
                "Fugaku requires a project group for every job (pjsub -g "
                "<groupname>). Set spec.attributes.account explicitly, or "
                "configure a default via defaults.group in "
                "~/.hpc-agent/fugaku.json (or the FUGAKU_GROUP env var). The "
                "shared 'fugaku' group cannot submit jobs — run "
                "run_command_on_cluster('id') to see the real project groups "
                "this account belongs to."
            )

        lines = [
            "#!/bin/bash",
            f'#PJM --name "{spec.name}"',
            f'#PJM -L "rscgrp={queue}"',
            f'#PJM -L "node={res.node_count}"',
            f'#PJM -L "elapse={duration_to_hms(attrs.duration)}"',
            f"#PJM -g {group}",
        ]

        gfscache = attrs.custom_attributes.get("gfscache_volume") or config.default_gfscache_volume()
        if gfscache:
            lines.append(f"#PJM -x PJM_LLIO_GFSCACHE={gfscache}")

        if res.processes_per_node and res.processes_per_node > 1:
            lines.append(f'#PJM --mpi "max-proc-per-node={res.processes_per_node}"')

        for key, val in attrs.custom_attributes.items():
            if key == "gfscache_volume":
                continue
            lines.append(f"#PJM {key} {val}" if key.startswith("-") else f"#PJM --{key} {val}")

        return lines

    def render_script(self, spec: JobSpec) -> str:
        """Render a JobSpec as a pjsub batch script.

        MPI launch is only added when the job requests more than one task —
        Fugaku's own basic single-node sample script (JobExecution/Overview)
        runs the executable directly with no mpiexec at all; only the
        hybrid-parallel samples use "mpiexec -n <N>".
        """
        header_lines = self._header(spec)
        if spec.directory:
            header_lines.append(f"cd {shlex.quote(spec.directory)}")

        tasks = _tasks(spec)
        launcher = spec.launcher or (f"mpiexec -n {tasks}" if tasks > 1 else None)
        effective_spec = spec if launcher == spec.launcher else spec.model_copy(update={"launcher": launcher})

        return "\n".join(header_lines) + render_body(effective_spec, gpu_requested=False)

    def submit(self, spec: JobSpec) -> dict:
        """Write the rendered script on Fugaku and submit it with pjsub.

        PJM runs a job relative to whatever directory pjsub itself was
        invoked from (there is no --chdir-style flag), and
        hpc_agent_core.middleware.run_command always executes from $HOME —
        so this explicitly `cd`s into self._jobs_dir before calling pjsub,
        making that directory the job's execution directory too. Without
        this, output would land loose in $HOME instead of alongside the
        script under ~/agent/jobs/ (PORTING.md §10's bias to one visible
        directory).

        --no-check-directory is required here: pjsub's "data area" check
        (confirmed live) only accepts a real group data volume
        (/vol0n0m/data/<groupname>/) as a submission directory — $HOME and
        everything under it, including ~/agent/jobs/, is a *different* area
        type ("home area") and always fails that check otherwise
        ("The current directory is not a data area."). RIKEN's own docs
        cover this same case (JobExecution/JobExecConsiderpoints) and point
        to disabling the check as the way to submit from a home directory.
        """
        stamp = time.strftime("%Y%m%d-%H%M%S")
        script_path = write_remote_file(
            f"{self._jobs_dir}/{spec.name}-{stamp}.sh", self.render_script(spec)
        )
        output = run_command(
            f"cd {shlex.quote(self._jobs_dir)} && pjsub --no-check-directory {shlex.quote(script_path)}"
        )
        job_id = _parse_pjsub_job_id(output)
        if not job_id:
            raise RuntimeError(f"pjsub did not return a job id: {output}")
        return {"job_id": job_id, "script_path": script_path, "submission_output": output.strip()}

    def get_statuses(self, job_ids: list[str]) -> list[Job]:
        """pjstat <ids> for live jobs, falling back to pjstat --history for
        anything not found live (a job that already finished)."""
        if not job_ids:
            return []
        ids = " ".join(shlex.quote(j) for j in job_ids)
        live: dict[str, Job] = {}
        for line in _run_optional(f"pjstat {ids}").splitlines():
            job = _parse_pjstat_line(line)
            if job:
                live[job.id] = job

        missing = [jid for jid in job_ids if jid not in live]
        if missing:
            # Fugaku retains up to 90 days of finished-job history (per the
            # official guide's UsageRules section).
            for line in _run_optional("pjstat --history day=90").splitlines():
                job = _parse_pjstat_line(line)
                if job and job.id in missing:
                    live[job.id] = job

        return [
            live.get(jid, Job(id=jid, status=JobStatus(state=JobState.UNKNOWN, meta_data={"scheduler": "pjm"})))
            for jid in job_ids
        ]

    def get_recent_statuses(self, since: str = "now-2days") -> list[Job]:
        """Merge the current user's live queue (plain `pjstat`) with recent
        history (`pjstat --history day=N`, parsed from `since` when it looks
        like "now-Ndays", else 2). Live entries win over history for the
        same id (handles a job that just transitioned)."""
        days = 2
        m = re.match(r"now-(\d+)days?$", since)
        if m:
            days = int(m.group(1))

        jobs: dict[str, Job] = {}
        for line in _run_optional(f"pjstat --history day={days}").splitlines():
            job = _parse_pjstat_line(line)
            if job:
                jobs[job.id] = job
        for line in _run_optional("pjstat").splitlines():
            job = _parse_pjstat_line(line)
            if job:
                jobs[job.id] = job
        return list(jobs.values())

    def cancel(self, job_id: str) -> Job | str:
        """pjdel, then re-query status."""
        try:
            run_command(f"pjdel {shlex.quote(job_id)}")
        except RuntimeError as exc:
            return Job(id=job_id, status=JobStatus(state=JobState.UNKNOWN, message=str(exc), meta_data={"scheduler": "pjm"}))
        jobs = self.get_statuses([job_id])
        return jobs[0] if jobs else Job(
            id=job_id,
            status=JobStatus(state=JobState.CANCELED, message=f"pjdel {job_id} accepted", meta_data={"scheduler": "pjm"}),
        )

    def alter(self, job_id: str, duration: int | str) -> Job:
        """pjalter — only elapse-time changes on a still-queued/held job are
        supported here (see hpc_server.update_job); pjalter can change other
        resource fields too, but only this one is exposed, matching Irene's
        precedent of a deliberately partial update_job."""
        run_command(f'pjalter -L "elapse={duration_to_hms(duration)}" {shlex.quote(job_id)}')
        jobs = self.get_statuses([job_id])
        if not jobs:
            raise ValueError(f"Job {job_id} not found after pjalter")
        return jobs[0]


backend = PJMBackend()

# hpc_server.py calls these:
submit = backend.submit
get_statuses = backend.get_statuses
get_recent_statuses = backend.get_recent_statuses
cancel = backend.cancel
render_script = backend.render_script
alter = backend.alter
