"""RIKYU's MCP tool surface — the IRI-grouped submit/status/cancel,
filesystem, and facility/resource tools. Mostly a thin pass-through to
compute.py and hpc_agent_core.middleware; see PORTING.md §7 and this repo's
IRI_CHECKLIST.md for what's implemented, deferred, or extended beyond spec.
"""
import shlex
from pathlib import Path

from hpc_agent_core.mcp_server import MCPServer

from hpc_agent_core import middleware
from hpc_agent_core.middleware import quote_path, run_command
from hpc_agent_core.models import CompressionType, Job, JobSpec
from hpc_agent_core.serving import serve
from rikyu_mcp import compute, config

mcp = MCPServer("rikyu-hpc")

_TAR_FLAGS = {
    CompressionType.NONE: "cf",
    CompressionType.GZIP: "czf",
    CompressionType.BZIP2: "cjf",
    CompressionType.XZ: "cJf",
}


# ---------------------------------------------------------------------------
# Facility / resource info
# ---------------------------------------------------------------------------

@mcp.tool()
def get_facility() -> dict:
    """Static RIKYU facility facts: the gpu partition, the GPU-count ->
    node/CPU/memory table, storage tiers, modules, and Spack. (IRI: GET /facility)"""
    return config.load_cluster_config()


@mcp.tool()
def get_resources() -> list[dict]:
    """Live occupancy for RIKYU's compute partitions ("resources" in IRI
    terms) via sinfo — allocated/idle/other/total node counts, i.e. "will a
    job start soon". RIKYU has exactly one partition, "gpu", covering all
    400 nodes, but the occupancy numbers themselves change constantly, so
    this is a live query (hpc_agent_core's SlurmBackend.get_live_resources),
    not the static rikyu_config.json get_facility reads from.
    (IRI: GET /resources)
    """
    return compute.get_live_resources()


@mcp.tool()
def get_resource(name: str) -> dict:
    """Live occupancy for one named partition. (IRI: GET /resources/{name})"""
    for p in compute.get_live_resources():
        if p["partition"] == name:
            return p
    raise ValueError(f"No resource named {name!r} — RIKYU's only partition is 'gpu'")


@mcp.tool()
def get_drained_nodes() -> list[dict]:
    """Nodes currently drained/down and why, via sinfo -R (extension — not
    an IRI endpoint, but directly useful for "why won't my job start")."""
    return compute.get_drained_nodes()


# ---------------------------------------------------------------------------
# Job submit / status / cancel / update
# ---------------------------------------------------------------------------

def _validate_gpu_count(spec: JobSpec) -> None:
    """RIKYU only accepts these GPU counts per job (Job Resources guide
    page) — everything else about the resource ceiling (node count, CPU
    cores, memory) follows deterministically from this count, so a bad
    count is worth catching before submission rather than as a confusing
    sbatch-time rejection."""
    gpus = spec.resources.gpus or spec.resources.gpu_cores_per_process
    if not gpus:
        return
    supported = config.load_cluster_config()["job_resources"]["supported_gpu_counts"]
    if gpus not in supported:
        raise ValueError(
            f"RIKYU only accepts these GPU counts per job: {supported}. Got {gpus}."
        )


@mcp.tool()
def submit_job(spec: JobSpec) -> dict:
    """Submit a job to RIKYU's Slurm scheduler. Show the user the spec
    before submitting unless they asked to just run it (mirrors
    run_command_on_cluster's rule below). If spec.attributes.queue_name is
    left blank, it defaults to RIKYU's only partition, "gpu". (IRI: POST /compute/job)
    """
    if not spec.attributes.queue_name:
        spec.attributes.queue_name = "gpu"
    _validate_gpu_count(spec)
    return compute.submit(spec)


@mcp.tool()
def get_job_status(job_id: str) -> Job:
    """Status of a single job. (IRI: GET /compute/job/{job_id})"""
    jobs = compute.get_statuses([job_id])
    if not jobs:
        raise ValueError(f"Job {job_id} not found")
    return jobs[0]


@mcp.tool()
def get_job_statuses(job_ids: list[str]) -> list[Job]:
    """Status of several jobs, or — if job_ids is empty — every job the
    current user has touched in roughly the last two days (RIKYU has Slurm
    accounting, so this includes finished jobs, not just the live queue).
    (IRI: GET /compute/jobs)"""
    return compute.get_statuses(job_ids) if job_ids else compute.get_recent_statuses()


@mcp.tool()
def cancel_job(job_id: str) -> Job | str:
    """Cancel a queued or running job via scancel. (IRI: DELETE /compute/job/{job_id})"""
    return compute.cancel(job_id)


@mcp.tool()
def update_job(job_id: str, updates: dict[str, str]) -> str:
    """Modify an already-submitted job's Slurm attributes via `scontrol
    update`, e.g. {"TimeLimit": "02:00:00"} to extend the wall time. Only
    affects jobs still queued or running, and is subject to Slurm's own
    permission rules (some fields can only be lowered, not raised, by a
    non-admin). (IRI: PUT /compute/job/{job_id})
    """
    assignments = " ".join(f"{k}={shlex.quote(v)}" for k, v in updates.items())
    return run_command(f"scontrol update JobId={shlex.quote(job_id)} {assignments}")


@mcp.tool()
def run_command_on_cluster(command: str) -> str:
    """Run an arbitrary shell command on the login node (extension — not an
    IRI endpoint). Before calling this, show the user the exact command (or
    script) and a one-line explanation of what it does, then call it — skip
    the preview only if the user explicitly asked to just run something. Do
    not run heavy computation on the login node — submit a job instead.
    """
    return run_command(command)


# ---------------------------------------------------------------------------
# Filesystem operations
# ---------------------------------------------------------------------------

@mcp.tool()
def fs_ls(path: str = ".") -> str:
    """List a directory's contents (long form). (IRI: GET /filesystem/ls)"""
    return run_command(f"ls -la {quote_path(path)}")


@mcp.tool()
def fs_stat(path: str) -> str:
    """File/directory metadata: size, permissions, timestamps, owner. (IRI: GET /filesystem/stat)"""
    return run_command(f"stat {quote_path(path)}")


@mcp.tool()
def fs_view(path: str) -> str:
    """Read a whole text file's contents. (IRI: GET /filesystem/view)"""
    return run_command(f"cat {quote_path(path)}")


@mcp.tool()
def fs_head(path: str, lines: int = 20) -> str:
    """Read the first N lines of a file. (IRI: GET /filesystem/head)"""
    return run_command(f"head -n {int(lines)} {quote_path(path)}")


@mcp.tool()
def fs_tail(path: str, lines: int = 20) -> str:
    """Read the last N lines of a file — useful for checking a running
    job's stdout/stderr. (IRI: GET /filesystem/tail)"""
    return run_command(f"tail -n {int(lines)} {quote_path(path)}")


@mcp.tool()
def fs_mkdir(path: str) -> str:
    """Create a directory, including parents as needed. (IRI: POST /filesystem/mkdir)"""
    return run_command(f"mkdir -p {quote_path(path)}")


@mcp.tool()
def fs_upload(local_path: str, remote_path: str) -> dict:
    """Upload a local file to RIKYU via rsync (falling back to scp), with a
    SHA-256 verification of the transfer. (IRI: POST /filesystem/upload)"""
    return middleware.upload_file(Path(local_path), remote_path)


@mcp.tool()
def fs_download(remote_path: str, local_path: str) -> dict:
    """Download a file from RIKYU via rsync (falling back to scp), with a
    SHA-256 verification of the transfer. (IRI: GET /filesystem/download)"""
    return middleware.download_file(remote_path, Path(local_path))


@mcp.tool()
def fs_checksum(path: str) -> str:
    """SHA-256 checksum of a remote file. (IRI: GET /filesystem/checksum)"""
    return run_command(f"sha256sum {quote_path(path)}")


@mcp.tool()
def fs_cp(source: str, dest: str, recursive: bool = False) -> str:
    """Copy a file or (with recursive=True) a directory tree on the
    cluster. (IRI: POST /filesystem/cp)"""
    flag = "-r " if recursive else ""
    return run_command(f"cp {flag}{quote_path(source)} {quote_path(dest)}")


@mcp.tool()
def fs_mv(source: str, dest: str) -> str:
    """Move or rename a file/directory on the cluster. (IRI: POST /filesystem/mv)"""
    return run_command(f"mv {quote_path(source)} {quote_path(dest)}")


@mcp.tool()
def fs_chmod(path: str, mode: str) -> str:
    """Change a file/directory's permissions, e.g. mode="755". (IRI: POST /filesystem/chmod)"""
    return run_command(f"chmod {shlex.quote(mode)} {quote_path(path)}")


@mcp.tool()
def fs_chown(path: str, owner: str) -> str:
    """Change a file/directory's owner (and optionally group, as
    "user:group"). Most users can only chown within their own group's
    permissions — Slurm/Lustre still enforces the actual ACL. (IRI: POST /filesystem/chown)"""
    return run_command(f"chown {shlex.quote(owner)} {quote_path(path)}")


@mcp.tool()
def fs_symlink(target: str, link_name: str) -> str:
    """Create a symbolic link at link_name pointing to target. (IRI: POST /filesystem/symlink)"""
    return run_command(f"ln -s {quote_path(target)} {quote_path(link_name)}")


@mcp.tool()
def fs_compress(paths: list[str], archive_path: str,
                 compression: CompressionType = CompressionType.GZIP) -> str:
    """Create a tar archive from one or more remote paths. (IRI: POST /filesystem/compress)"""
    flag = _TAR_FLAGS[compression]
    quoted_paths = " ".join(quote_path(p) for p in paths)
    return run_command(f"tar -{flag} {quote_path(archive_path)} {quoted_paths}")


@mcp.tool()
def fs_extract(archive_path: str, dest_dir: str = ".") -> str:
    """Extract an archive on the cluster into dest_dir (created if needed).
    Compression format is auto-detected by tar. (IRI: POST /filesystem/extract)"""
    return run_command(f"mkdir -p {quote_path(dest_dir)} && tar -xf {quote_path(archive_path)} -C {quote_path(dest_dir)}")


def main():
    serve(mcp)


if __name__ == "__main__":
    main()
