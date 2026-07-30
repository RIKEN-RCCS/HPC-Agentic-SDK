"""Fugaku's MCP tool surface — the IRI-grouped submit/status/cancel,
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
from fugaku_mcp import compute, config

mcp = MCPServer("fugaku-hpc")

RESOURCE_ID = "fugaku"

_COMPRESSION_FLAGS = {
    CompressionType.NONE: "",
    CompressionType.GZIP: "z",
    CompressionType.BZIP2: "j",
    CompressionType.XZ: "J",
}


def _check_resource(resource_id: str) -> None:
    if resource_id != RESOURCE_ID:
        raise ValueError(f"Unknown resource '{resource_id}'; this server manages '{RESOURCE_ID}'")


# === facility ================================================================

@mcp.tool()
def get_facility() -> dict:
    """Static Fugaku facts: PJM resource groups, storage tiers, modules,
    and login conventions. (IRI: GET /facility)

    Fugaku is a CPU-only system (A64FX, no GPUs). Every job needs a PJM
    resource group (attributes.queue_name — e.g. 'small', 'large', 'int')
    and a project group (attributes.account, PJM's "-g").
    """
    return config.load_cluster_config()


# === status ===================================================================

@mcp.tool()
def get_resources() -> list[dict]:
    """List compute resources and their live state. (IRI: GET /resources)"""
    return [_resource_detail()]


@mcp.tool()
def get_resource(resource_id: str = RESOURCE_ID) -> dict:
    """Get detailed state for a single resource. (IRI: GET /resources/{resource_id})"""
    _check_resource(resource_id)
    return _resource_detail()


def _resource_detail() -> dict:
    # pjstat --rsc returned only a header row (no occupancy rows) for every
    # account/flag combination tried while porting this plugin — it may
    # simply not be populated for this account/deployment. Rather than
    # fabricate a parser for a shape that was never actually observed, this
    # returns the raw command output for the agent to read directly;
    # get_facility (static resource-group limits from pjacl) is the more
    # reliable source for node/time-limit questions. See IRI_CHECKLIST.md.
    rsc = compute._run_optional("pjstat --rsc")
    showrsc = compute._run_optional("pjshowrsc")
    return {
        "id": RESOURCE_ID,
        "type": "compute",
        "description": "RIKEN Fugaku (A64FX, Tofu interconnect, PJM scheduler; CPU-only, no GPUs)",
        "raw_pjstat_rsc": rsc,
        "raw_pjshowrsc": showrsc,
    }


# === compute ==================================================================

@mcp.tool()
def submit_job(spec: JobSpec, resource_id: str = RESOURCE_ID) -> dict:
    """Submit a job described by a JobSpec. (IRI: POST /compute/job/{resource_id})

    The spec is rendered as a pjsub script (kept under ~/agent/jobs/ on the
    cluster for auditability) and submitted. Fugaku notes: attributes.queue_name
    is required (a PJM resource group such as 'small', 'large', or 'int');
    attributes.account is required (a project group — PJM's "-g"; falls back to
    a configured default, see the fugaku-configuring skill); Fugaku has no GPUs
    (resources.gpus/gpu_cores_per_process must stay unset); pjsub has no
    stdout/stderr path override, so stdout_path/stderr_path must stay unset —
    output always lands at '<name>.<job_id>.out'/'.err' in the submission
    directory. Describe MPI work with resources.node_count and
    resources.processes_per_node; a launcher of "mpiexec -n <N>" is added
    automatically whenever more than one task is requested. Show the user the
    spec (or the rendered script) before submitting, unless they asked to just
    run it.
    """
    _check_resource(resource_id)
    return compute.submit(spec)


@mcp.tool()
def get_job_status(job_id: str, resource_id: str = RESOURCE_ID) -> Job:
    """Get the normalized status of one job. (IRI: GET /compute/status/...)

    state is the normalized IRI state (QUEUED/HELD/ACTIVE/COMPLETED/FAILED/
    CANCELED); native_state is PJM's own two/three-letter code (e.g. RUN,
    QUE, EXT). A COMPLETED (EXT) job's message notes that pjstat does not
    expose an application exit code — read the job's .out/.err file to
    confirm real success.
    """
    _check_resource(resource_id)
    jobs = compute.get_statuses([job_id])
    if not jobs:
        raise ValueError(f"Job {job_id} not found")
    return jobs[0]


@mcp.tool()
def get_job_statuses(job_ids: list[str], resource_id: str = RESOURCE_ID) -> list[Job]:
    """Get statuses for several jobs at once, or recent jobs when job_ids is
    empty (merges the live queue with up to 90 days of PJM history).
    (IRI: POST /compute/status/{resource_id})
    """
    _check_resource(resource_id)
    return compute.get_statuses(job_ids) if job_ids else compute.get_recent_statuses()


@mcp.tool()
def update_job(job_id: str, time_limit: str | None = None, resource_id: str = RESOURCE_ID) -> Job:
    """Update a queued or held job. (IRI: PUT /compute/job/{resource_id}/{job_id})

    Only a new elapse time limit is supported (pjalter -L "elapse=..."),
    matching what pjalter reliably changes for a still-queued job — other
    fields (resource group, node count, project group) are not supported
    here; cancel and resubmit instead.
    """
    _check_resource(resource_id)
    if not time_limit:
        raise ValueError("No fields to update — supply time_limit (HH:MM:SS or D-HH:MM:SS)")
    return compute.alter(job_id, time_limit)


@mcp.tool()
def cancel_job(job_id: str, resource_id: str = RESOURCE_ID) -> Job | str:
    """Cancel a queued or running job and report its resulting state.
    (IRI: DELETE /compute/cancel/{resource_id}/{job_id})
    """
    _check_resource(resource_id)
    return compute.cancel(job_id)


# === filesystem ================================================================
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
    """Read a whole text file on the cluster. (IRI: GET /filesystem/view)
    For large files use fs_head/fs_tail.
    """
    return run_command(f"cat {quote_path(path)}")


@mcp.tool()
def fs_head(path: str, lines: int = 50) -> str:
    """Read the first lines of a file on the cluster. (IRI: GET /filesystem/head)"""
    return run_command(f"head -n {int(lines)} {quote_path(path)}")


@mcp.tool()
def fs_tail(path: str, lines: int = 50) -> str:
    """Read the last lines of a file on the cluster — e.g. a job's
    <name>.<job_id>.out. (IRI: GET /filesystem/tail)
    """
    return run_command(f"tail -n {int(lines)} {quote_path(path)}")


@mcp.tool()
def fs_mkdir(path: str) -> str:
    """Create a directory (and parents) on the cluster. (IRI: POST /filesystem/mkdir)"""
    quoted = quote_path(path)
    return run_command(f"mkdir -p {quoted} && echo created: $(realpath {quoted})")


@mcp.tool()
def fs_upload(path: str, local_path: str) -> dict:
    """Upload a local file to the cluster. (IRI: POST /filesystem/upload)

    Transfers local_path -> path on the cluster via rsync or scp. Creates
    remote parent directories as needed. Returns
    {remote_path, bytes, sha256, verified, transport}.
    """
    return middleware.upload_file(Path(local_path), path)


@mcp.tool()
def fs_checksum(path: str) -> str:
    """SHA-256 checksum of a file on the cluster. (IRI: GET /filesystem/checksum)"""
    return run_command(f"sha256sum {quote_path(path)}")


@mcp.tool()
def fs_download(path: str, local_path: str | None = None) -> dict:
    """Download a file from the cluster to local disk.
    (IRI: GET /filesystem/download deviation)

    Transfers path -> local_path via rsync or scp. local_path defaults to
    the filename in the current working directory. Returns
    {local_path, bytes, sha256, verified, transport}. Deliberately deviates
    from the IRI base64 shape — see IRI_CHECKLIST.md.
    """
    dest = Path(local_path) if local_path else Path.cwd() / Path(path).name
    return middleware.download_file(path, dest)


@mcp.tool()
def fs_cp(src: str, dst: str) -> str:
    """Copy a file or directory on the cluster. (IRI: POST /filesystem/cp)"""
    return run_command(f"cp -r {quote_path(src)} {quote_path(dst)} && echo ok")


@mcp.tool()
def fs_mv(src: str, dst: str) -> str:
    """Move or rename a file or directory on the cluster. (IRI: POST /filesystem/mv)

    Destructive — the source path will no longer exist after this call.
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
    match_pattern: regex passed to find -regex to filter files.
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


# === extensions (not part of the IRI API) =====================================

@mcp.tool()
def run_command_on_cluster(command: str) -> str:
    """Run an arbitrary shell command on the Fugaku login node (extension —
    not an IRI endpoint).

    Use only when no dedicated tool fits, e.g. 'module avail' to list
    software, 'id' to see which project groups this account belongs to,
    'pjacl --rg small' for a resource group's node/time limits, or
    'pjstat --limit' for concurrent-job quotas. Runs under a login shell
    from the home directory; returns stdout+stderr. Do not run heavy
    computation on the login node — submit a job instead. Before calling
    this, show the user the exact command and a one-line explanation of
    what it does, unless they asked to just run it.
    """
    return run_command(command)


def main():
    serve(mcp)


if __name__ == "__main__":
    main()
