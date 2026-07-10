"""MCP server for the R-CCS Cloud, modeled on the IRI Facility API.

Tool groups mirror the IRI resource groups (facility, status, account,
compute, filesystem); each operation runs on the R-CCS Cloud login node over
SSH via `hpc_agent_core.middleware`. Coverage of the full API is tracked in
IRI_CHECKLIST.md at the repo root.

Tools are thin verbs — a short call into `cloud_mcp.compute` (the scheduler
backend) or `hpc_agent_core.middleware` (the SSH layer). Workflow knowledge
(when to pick which partition, how to read a failed job) lives in the skills
under plugins/rccs-cloud/skills/, not in long docstrings here.
"""
import shlex
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from hpc_agent_core.middleware import (
    download_file,
    quote_path,
    run_command,
    upload_file,
)
from hpc_agent_core.models import CompressionType, Job, JobSpec
from hpc_agent_core.serving import serve
from cloud_mcp import compute, config  # noqa: F401 -- config registers settings via configure()

mcp = FastMCP("rccs-cloud-hpc")

RESOURCE_ID = "rccs-cloud"


def _check_resource(resource_id: str) -> None:
    if resource_id != RESOURCE_ID:
        raise ValueError(f"Unknown resource '{resource_id}'; this server manages '{RESOURCE_ID}'")


# === facility ================================================================

@mcp.tool()
def get_facility() -> dict:
    """Describe the R-CCS Cloud facility: partitions, modules, storage, conventions.

    Static reference data (no SSH round-trip). The R-CCS Cloud is a
    heterogeneous cluster with partition families spanning CPU-only, NVIDIA
    GPU, AMD GPU, and Intel GPU hardware; each partition has its own required
    system module. For *live* occupancy ("will a job start soon") use
    get_resources instead. (IRI: GET /facility)
    """
    return config.load_cluster_config()


# === status ==================================================================

@mcp.tool()
def get_resources() -> list[dict]:
    """List compute resources and their live state. (IRI: GET /status/resources)

    Returns the R-CCS Cloud resource with a per-partition node-state summary
    (allocated/idle/other/total) from a live `sinfo` call — not the static
    facility data. Idle nodes can start a job immediately.
    """
    return [_resource_detail()]


@mcp.tool()
def get_resource(resource_id: str = RESOURCE_ID) -> dict:
    """Get detailed live state for a single resource. (IRI: GET /status/resources/{resource_id})

    Includes per-partition node counts plus any drained/draining nodes and
    their reasons (from `sinfo -R`).
    """
    _check_resource(resource_id)
    return _resource_detail(include_drain=True)


def _resource_detail(include_drain: bool = False) -> dict:
    resource: dict = {
        "id": RESOURCE_ID,
        "type": "compute",
        "description": "RIKEN R-CCS Cloud (heterogeneous: A64FX, x86_64, aarch64, NVIDIA/AMD/Intel GPUs)",
        "partitions": compute.get_live_resources(),
    }
    if include_drain:
        resource["drained_nodes"] = compute.get_drained_nodes()
    return resource


# === account =================================================================

def _parse_projects(output: str) -> list[dict]:
    projects = []
    for line in output.strip().splitlines():
        parts = line.split("|")
        if len(parts) < 18 or parts[0] == "Cluster":
            continue
        projects.append({
            "id": parts[1],
            "cluster": parts[0],
            "user": parts[2],
            "qos": parts[17] or None,
        })
    return projects


@mcp.tool()
def get_projects() -> list[dict]:
    """List projects (Slurm accounts) the current user belongs to.
    (IRI: GET /account/projects)

    Each project's id is the account name usable in JobAttributes.account.
    The R-CCS Cloud does not require an account — jobs submitted without one
    use the user's default Slurm account.
    """
    output = run_command("sacctmgr show associations user=$USER --parsable2 --noheader")
    return _parse_projects(output)


@mcp.tool()
def get_project(project_id: str) -> dict:
    """Get details for a single project (Slurm account).
    (IRI: GET /account/projects/{id})
    """
    for p in get_projects():
        if p["id"] == project_id:
            return p
    raise ValueError(f"Project '{project_id}' not found for current user")


# === compute =================================================================

@mcp.tool()
def submit_job(spec: JobSpec, resource_id: str = RESOURCE_ID) -> dict:
    """Submit a job described by a JobSpec. (IRI: POST /compute/job/{resource_id})

    Show the user the spec (or describe it) before submitting, unless they
    asked to just run it. The spec is rendered as an sbatch script (kept
    under ~/agent/jobs/ on the cluster for auditability) and submitted;
    returns {job_id, script_path}.

    R-CCS Cloud notes:
    - attributes.queue_name picks the partition and thus the hardware family.
    - `source /etc/profile` is emitted automatically; do not add it to executable.
    - Put module loads at the start of executable, e.g.
      'module load system/genoa mpi/openmpi-x86_64 && srun ./app'.
    - resources.gpus requests --gpus=<n>; omit it for qc-gh200 / ng-dgx-m[0-3].
    """
    _check_resource(resource_id)
    return compute.submit(spec)


@mcp.tool()
def get_job_status(job_id: str, resource_id: str = RESOURCE_ID) -> Job:
    """Get the normalized status of one job. (IRI: GET /compute/status/{rid}/{job_id})

    state is the normalized IRI state (queued/active/completed/failed/
    canceled); meta_data.native_state is Slurm's. For a queued job, message
    explains the wait. Job stdout defaults to <workdir>/slurm-<job_id>.out —
    read it with fs_tail or fs_view.
    """
    _check_resource(resource_id)
    jobs = compute.get_statuses([job_id])
    if not jobs:
        raise ValueError(f"Job {job_id} not found")
    return jobs[0]


@mcp.tool()
def get_job_statuses(job_ids: list[str], resource_id: str = RESOURCE_ID) -> list[Job]:
    """Statuses for several jobs at once, or the current user's recent jobs
    (last ~2 days) when job_ids is empty. (IRI: POST /compute/status/{resource_id})
    """
    _check_resource(resource_id)
    if job_ids:
        return compute.get_statuses(job_ids)
    return compute.get_recent_statuses()


@mcp.tool()
def update_job(
    job_id: str,
    time_limit: str | None = None,
    name: str | None = None,
    partition: str | None = None,
    account: str | None = None,
    reservation: str | None = None,
    resource_id: str = RESOURCE_ID,
) -> Job:
    """Update a queued or running job. (IRI: PUT /compute/job/{resource_id}/{job_id})

    Only supplied fields change.
    time_limit: new wall time as HH:MM:SS or D-HH:MM:SS (works on running jobs too).
    partition, account, reservation: only valid while the job is still queued.
    """
    _check_resource(resource_id)
    mapping = {
        "TimeLimit": time_limit,
        "Name": name,
        "Partition": partition,
        "Account": account,
        "Reservation": reservation,
    }
    updates = " ".join(f"{k}={shlex.quote(v)}" for k, v in mapping.items() if v is not None)
    if not updates:
        raise ValueError("No fields to update — supply at least one argument")
    run_command(f"scontrol update job {shlex.quote(job_id)} {updates}")
    jobs = compute.get_statuses([job_id])
    if not jobs:
        raise ValueError(f"Job {job_id} not found after update")
    return jobs[0]


@mcp.tool()
def cancel_job(job_id: str, resource_id: str = RESOURCE_ID) -> Job | str:
    """Cancel a queued or running job and report its resulting state.
    (IRI: DELETE /compute/cancel/{resource_id}/{job_id}) Confirm with the
    user before cancelling.
    """
    _check_resource(resource_id)
    return compute.cancel(job_id)


# === filesystem ==============================================================
# Paths are relative to the home directory unless absolute.

@mcp.tool()
def fs_ls(path: str = ".", show_hidden: bool = False) -> str:
    """List a directory on the cluster. (IRI: GET /filesystem/ls)"""
    flags = "-la" if show_hidden else "-l"
    return run_command(f"ls {flags} {quote_path(path)}")


@mcp.tool()
def fs_stat(path: str) -> str:
    """Stat a file or directory on the cluster. (IRI: GET /filesystem/stat)"""
    return run_command(f"stat {quote_path(path)}")


@mcp.tool()
def fs_view(path: str) -> str:
    """Read a whole text file on the cluster (output capped at 200 KB).
    (IRI: GET /filesystem/view) For large files use fs_head/fs_tail.
    """
    return run_command(f"cat {quote_path(path)}")


@mcp.tool()
def fs_head(path: str, lines: int = 50) -> str:
    """Read the first lines of a file on the cluster. (IRI: GET /filesystem/head)"""
    return run_command(f"head -n {int(lines)} {quote_path(path)}")


@mcp.tool()
def fs_tail(path: str, lines: int = 50) -> str:
    """Read the last lines of a file on the cluster — e.g. a job's
    slurm-<job_id>.out. (IRI: GET /filesystem/tail)
    """
    return run_command(f"tail -n {int(lines)} {quote_path(path)}")


@mcp.tool()
def fs_mkdir(path: str) -> str:
    """Create a directory (and parents) on the cluster. (IRI: POST /filesystem/mkdir)"""
    quoted = quote_path(path)
    return run_command(f"mkdir -p {quoted} && echo created: $(realpath {quoted})")


@mcp.tool()
def fs_upload(path: str, local_path: str) -> dict:
    """Upload a local file to the cluster. (IRI: POST /filesystem/upload — deviation)

    Transfers local_path -> path on the cluster via rsync (scp fallback if
    rsync < 3.0), creating remote parent directories. No size limit. Returns
    {remote_path, bytes, sha256, verified, transport}. Deliberately diverges
    from IRI's multipart shape — see IRI_CHECKLIST.md.
    """
    return upload_file(Path(local_path), path)


@mcp.tool()
def fs_download(path: str, local_path: str | None = None) -> dict:
    """Download a file from the cluster to local disk. (IRI: GET /filesystem/download — deviation)

    Transfers path -> local_path via rsync (scp fallback if rsync < 3.0). No
    size limit. local_path defaults to the filename in the current working
    directory. Returns {local_path, bytes, sha256, verified, transport}.
    Deliberately diverges from IRI's base64-in-body shape — see IRI_CHECKLIST.md.
    """
    dest = Path(local_path) if local_path else Path.cwd() / Path(path).name
    return download_file(path, dest)


@mcp.tool()
def fs_checksum(path: str) -> str:
    """SHA-256 checksum of a file on the cluster. (IRI: GET /filesystem/checksum)"""
    return run_command(f"sha256sum {quote_path(path)}")


@mcp.tool()
def fs_cp(src: str, dst: str) -> str:
    """Copy a file or directory on the cluster. (IRI: POST /filesystem/cp)"""
    return run_command(f"cp -r {quote_path(src)} {quote_path(dst)} && echo ok")


@mcp.tool()
def fs_mv(src: str, dst: str) -> str:
    """Move or rename a file or directory on the cluster. (IRI: POST /filesystem/mv)

    Destructive — the source path no longer exists afterwards.
    """
    return run_command(f"mv {quote_path(src)} {quote_path(dst)} && echo ok")


@mcp.tool()
def fs_chmod(path: str, mode: str) -> str:
    """Change file permissions on the cluster. (IRI: PUT /filesystem/chmod)

    mode is an octal string, e.g. '755' or '644'.
    """
    return run_command(f"chmod {shlex.quote(mode)} {quote_path(path)} && echo ok")


@mcp.tool()
def fs_chown(path: str, owner: str = "", group: str = "") -> str:
    """Change file ownership on the cluster. (IRI: PUT /filesystem/chown)

    Supply owner, group, or both. Normal users can only change group to one
    they belong to; changing owner requires root.
    """
    if not owner and not group:
        raise ValueError("Provide at least one of owner or group")
    spec = owner + (":" + group if group else "")
    return run_command(f"chown {shlex.quote(spec)} {quote_path(path)} && echo ok")


@mcp.tool()
def fs_symlink(path: str, link_path: str) -> str:
    """Create a symbolic link on the cluster. (IRI: POST /filesystem/symlink)

    path is the target; link_path is the new symlink to create.
    """
    return run_command(f"ln -s {quote_path(path)} {quote_path(link_path)} && echo ok")


_COMPRESSION_FLAGS = {
    CompressionType.NONE: "",
    CompressionType.GZIP: "z",
    CompressionType.BZIP2: "j",
    CompressionType.XZ: "J",
}


@mcp.tool()
def fs_compress(
    target_path: str,
    path: str | None = None,
    match_pattern: str | None = None,
    dereference: bool = False,
    compression: CompressionType = CompressionType.GZIP,
) -> str:
    """Create an archive on the cluster. (IRI: POST /filesystem/compress)

    target_path: path of the archive to create.
    path: source file or directory (defaults to current directory).
    match_pattern: regex passed to `find -regex` to filter files.
    dereference: follow symlinks (-h).
    compression: gzip (default), bzip2, xz, or none.
    """
    flag = _COMPRESSION_FLAGS[compression]
    deref = "h" if dereference else ""
    tar_flags = f"-{deref}c{flag}f"
    src = quote_path(path or ".")
    if match_pattern:
        pattern = shlex.quote(match_pattern)
        cmd = (
            f"find {src} -regex {pattern} -print0 | "
            f"tar {tar_flags} {quote_path(target_path)} --null -T -"
        )
    else:
        cmd = f"tar {tar_flags} {quote_path(target_path)} {src}"
    return run_command(cmd + " && echo ok")


@mcp.tool()
def fs_extract(
    path: str,
    target_path: str,
    compression: CompressionType = CompressionType.GZIP,
) -> str:
    """Extract an archive on the cluster. (IRI: POST /filesystem/extract)

    path: archive file to extract.
    target_path: directory to extract into (created if absent).
    compression: gzip (default), bzip2, xz, or none.
    """
    flag = _COMPRESSION_FLAGS[compression]
    tar_flags = f"-x{flag}f"
    return run_command(
        f"mkdir -p {quote_path(target_path)} && "
        f"tar {tar_flags} {quote_path(path)} -C {quote_path(target_path)} && echo ok"
    )


# === extensions (not part of the IRI API) ====================================

@mcp.tool()
def run_command_on_cluster(command: str) -> str:
    """Run an arbitrary shell command on the R-CCS Cloud login node (extension —
    not an IRI endpoint).

    Before calling this, show the user the exact command and a one-line
    explanation, then call it — skip the preview only if the user explicitly
    asked to just run something. Runs under a login shell from the home
    directory; returns stdout. Do not run heavy computation on the login
    node — submit a job instead.
    """
    return run_command(command)


def main():
    serve(mcp)


if __name__ == "__main__":
    main()
