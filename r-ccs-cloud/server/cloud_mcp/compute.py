"""JobSpec → Slurm translation and status parsing (IRI compute backend)."""
import shlex
import time
from datetime import datetime

from cloud_mcp.middleware import run_command, write_remote_file
from cloud_mcp.models import Job, JobSpec, JobState, JobStatus, map_slurm_state

_SACCT_FIELDS = "JobID,JobName,Partition,State,Elapsed,Start,End,ExitCode,NodeList,WorkDir"


def _duration_to_hms(duration: int | str) -> str:
    """Convert IRI duration (int seconds or HH:MM:SS string) to sbatch HH:MM:SS."""
    if isinstance(duration, str):
        return duration
    h, rem = divmod(int(duration), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _to_epoch(s: str) -> float | None:
    """Parse a sacct datetime string (ISO-like) to epoch seconds."""
    if not s or s in ("Unknown", "N/A", "None", ""):
        return None
    try:
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        return None


def _parse_exit_code(s: str) -> int | None:
    """Parse sacct ExitCode field '0:0' → 0."""
    try:
        return int(s.split(":")[0])
    except (ValueError, IndexError):
        return None


def render_script(spec: JobSpec) -> str:
    """Render a JobSpec as an R-CCS Cloud sbatch script.

    Automatically emits `source /etc/profile` in the script body — required
    on R-CCS Cloud for the module system to be available. Do not add it to
    spec.executable; it is always present here.
    """
    res = spec.resources
    attr = spec.attributes

    lines = [
        "#!/bin/bash",
        f"#SBATCH --job-name={spec.name}",
        f"#SBATCH --partition={attr.queue_name}",
        f"#SBATCH --nodes={res.node_count}",
        f"#SBATCH --time={_duration_to_hms(attr.duration)}",
    ]

    # GPU: --gpus=<n> (R-CCS Cloud extension); not used for qc-gh200 / ng-dgx
    gpus = res.gpus if res.gpus is not None else res.gpu_cores_per_process
    if gpus:
        lines.append(f"#SBATCH --gpus={gpus}")

    lines.append(f"#SBATCH --ntasks-per-node={res.processes_per_node}")

    if res.process_count:
        lines.append(f"#SBATCH --ntasks={res.process_count}")
    if res.cpu_cores_per_process:
        lines.append(f"#SBATCH --cpus-per-task={res.cpu_cores_per_process}")
    if res.exclusive_node_use:
        lines.append("#SBATCH --exclusive")
    if res.memory:
        mb = max(1, res.memory // (1024 * 1024))
        lines.append(f"#SBATCH --mem={mb}M")

    if attr.account:
        lines.append(f"#SBATCH --account={attr.account}")
    if attr.reservation_id:
        lines.append(f"#SBATCH --reservation={attr.reservation_id}")
    if spec.directory:
        lines.append(f"#SBATCH --chdir={spec.directory}")
    if spec.stdin_path:
        lines.append(f"#SBATCH --input={spec.stdin_path}")
    if spec.stdout_path:
        lines.append(f"#SBATCH --output={spec.stdout_path}")
    if spec.stderr_path:
        lines.append(f"#SBATCH --error={spec.stderr_path}")

    for key, val in attr.custom_attributes.items():
        lines.append(f"#SBATCH --{key}={val}")

    lines.append("")
    # R-CCS Cloud requires source /etc/profile before any module commands.
    lines.append("source /etc/profile")
    lines.append("")

    for key, value in spec.environment.items():
        lines.append(f"export {key}={shlex.quote(value)}")

    if spec.pre_launch:
        lines.append(spec.pre_launch)

    command = spec.executable
    if spec.arguments:
        command += " " + " ".join(shlex.quote(a) for a in spec.arguments)

    if spec.container:
        c = spec.container
        sing_flags = []
        if gpus:
            sing_flags.append("--nv")
        for m in c.volume_mounts:
            bind = f"{m.source}:{m.target}" + (":ro" if m.read_only else "")
            sing_flags.append(f"--bind {shlex.quote(bind)}")
        sing_flags.append(f'"{c.image}"')
        command = "singularity exec " + " ".join(sing_flags) + " bash -c " + shlex.quote(command)

    if spec.launcher:
        command = spec.launcher + " " + command
    lines.append(command)

    if spec.post_launch:
        lines.append(spec.post_launch)

    lines.append("")
    return "\n".join(lines)


def submit(spec: JobSpec) -> dict:
    """Write the rendered script on the cluster and sbatch it.

    Returns {job_id, script_path}. Intentional deviation from IRI's
    TaskSubmitResponse: our SSH execution is synchronous so there is no
    async task to poll — sbatch returns the job ID directly.
    """
    stamp = time.strftime("%Y%m%d-%H%M%S")
    script_path = write_remote_file(
        f".rccs-cloud/jobs/{spec.name}-{stamp}.sh", render_script(spec)
    )
    output = run_command(f"sbatch --parsable {shlex.quote(script_path)}")
    job_id = output.strip().splitlines()[-1].split(";")[0] if output.strip() else ""
    if not job_id.isdigit():
        raise RuntimeError(f"sbatch failed: {output}")
    return {"job_id": job_id, "script_path": script_path}


def _parse_sacct(output: str) -> list[Job]:
    jobs = []
    for line in output.strip().splitlines():
        parts = line.split("|")
        if len(parts) < 10 or parts[0] == "JobID":
            continue
        if "." in parts[0]:  # skip job steps (e.g. 15614.batch)
            continue

        native_state = parts[3]
        state = map_slurm_state(native_state)
        start_epoch = _to_epoch(parts[5])
        end_epoch = _to_epoch(parts[6])
        status_time = end_epoch if end_epoch else start_epoch

        jobs.append(Job(
            id=parts[0],
            status=JobStatus(
                state=state,
                time=status_time,
                exit_code=_parse_exit_code(parts[7]),
                meta_data={
                    "native_state": native_state,
                    "name": parts[1],
                    "partition": parts[2],
                    "elapsed": parts[4],
                    "start_time": parts[5],
                    "end_time": parts[6],
                    "nodes": parts[8],
                    "workdir": parts[9],
                },
            ),
        ))
    return jobs


def _attach_reasons(jobs: list[Job]) -> list[Job]:
    """For queued/held jobs, attach the squeue wait reason as status.message."""
    waiting = [j for j in jobs if j.status and j.status.state in (JobState.QUEUED, JobState.HELD)]
    if not waiting:
        return jobs
    ids = ",".join(j.id for j in waiting)
    output = run_command(f"squeue --jobs={ids} --format='%i|%R' --noheader")
    reasons = dict(
        line.split("|", 1) for line in output.strip().splitlines() if "|" in line
    )
    for job in jobs:
        if job.status and job.id in reasons:
            job.status.message = reasons[job.id].strip()
    return jobs


def get_statuses(job_ids: list[str]) -> list[Job]:
    """Fetch normalized statuses for one or more jobs."""
    ids = ",".join(shlex.quote(j) for j in job_ids)
    output = run_command(
        f"sacct --jobs={ids} --format={_SACCT_FIELDS} --parsable2 --noheader"
    )
    return _attach_reasons(_parse_sacct(output))


def get_recent_statuses(since: str = "now-2days") -> list[Job]:
    """Statuses of the current user's jobs since the given time."""
    output = run_command(
        f"sacct --starttime={shlex.quote(since)} --format={_SACCT_FIELDS} "
        f"--parsable2 --noheader"
    )
    return _attach_reasons(_parse_sacct(output))


def cancel(job_id: str) -> Job | str:
    """scancel, then report the job's state."""
    run_command(f"scancel {shlex.quote(job_id)}")
    jobs = get_statuses([job_id])
    return jobs[0] if jobs else f"scancel sent; job {job_id} not found in sacct"
