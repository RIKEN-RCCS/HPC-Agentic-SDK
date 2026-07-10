"""HBW2's MCP tool surface, grouped around the IRI Facility API.

This is the one piece hpc-agent-core does not provide generically — each
tool is a short pass-through to `compute.py` (the SlurmBackend) or to
`hpc_agent_core.middleware` (the SSH layer). See IRI_CHECKLIST.md for which
IRI endpoints are implemented, deferred, or extended.

Two standing invariants (PORTING.md §10) shape this file:
  * Nothing above module scope touches the network or reads config eagerly —
    the server must never fail to start just because config is missing.
    `middleware`/`compute` are already lazy; we don't defeat that here.
  * "Show before you run": before submit_job / run_command_on_cluster
    actually executes, the agent shows the user the JobSpec (see
    render_job_script) or the exact command and a one-line explanation,
    unless the user said to just run it. That is a behavioral rule the
    skills enforce; the tool docstrings restate it.
"""
from mcp.server.fastmcp import FastMCP

from hpc_agent_core.middleware import (
    download_file,
    quote_path,
    run_command,
    upload_file,
)
from hpc_agent_core.models import CompressionType, Job, JobSpec
from hpc_agent_core.serving import serve
from hokusai_mcp import compute, config

mcp = FastMCP("hokusai-hpc")


# ---------------------------------------------------------------------------
# Facility & resources (IRI: GET /facility, GET /resources)
# ---------------------------------------------------------------------------

@mcp.tool()
def get_facility() -> dict:
    """Static HBW2 facility facts: subsystems (MPC/LMC/GPU), partitions and
    their limits, storage tiers, the module/MPI story, and the GPU dialect.
    (IRI: GET /facility)

    This is the stable hardware description. For "will a job start soon"
    use get_resources, which reads the live scheduler."""
    return config.load_cluster_config()


@mcp.tool()
def get_resources() -> list[dict]:
    """Live per-partition node occupancy (allocated / idle / other / total)
    via the scheduler — the "where will my job start soonest" view, as
    opposed to get_facility's static description. (IRI: GET /resources)"""
    return compute.get_live_resources()


@mcp.tool()
def get_resource(partition: str) -> dict:
    """Live occupancy for one partition by name (e.g. 'mpc', 'gpu').
    (IRI: GET /resources/{id})"""
    for res in compute.get_live_resources():
        if res["partition"] == partition:
            return res
    raise ValueError(
        f"Partition {partition!r} not found in live resources. "
        f"Call get_facility for the list of partitions."
    )


@mcp.tool()
def get_drained_nodes() -> list[dict]:
    """Nodes currently drained/down and the reason — useful when capacity
    looks lower than get_facility implies. (extension of GET /resources)"""
    return compute.get_drained_nodes()


# ---------------------------------------------------------------------------
# Projects / accounting (IRI: GET /projects, GET /projects/{id})
# ---------------------------------------------------------------------------

@mcp.tool()
def get_projects() -> list[dict]:
    """The projects (Slurm accounts) the current user may charge, with their
    allowed partitions/QOS, plus the fair-share standing that governs when
    queued jobs start. (IRI: GET /projects)

    HBW2 has real Slurm accounting, so this reads it live (sacctmgr +
    sshare). The remaining core-time balance moves continuously — read it
    here rather than assuming a cached value. A user names one of these
    accounts per job (submit_job's spec.attributes.account), or sets a
    default in ~/.hpc-agent/hokusai.json under defaults.account."""
    assoc = run_command(
        "sacctmgr --noheader --parsable2 show associations "
        "where user=$USER format=Account,Partition,QOS"
    )
    projects: dict[str, dict] = {}
    for line in assoc.strip().splitlines():
        parts = line.split("|")
        if len(parts) < 1 or not parts[0]:
            continue
        acct = parts[0]
        entry = projects.setdefault(
            acct, {"account": acct, "partitions": set(), "qos": set()}
        )
        if len(parts) > 1 and parts[1]:
            entry["partitions"].add(parts[1])
        if len(parts) > 2 and parts[2]:
            entry["qos"].update(q for q in parts[2].split(",") if q)

    share = run_command("sshare -U --parsable2 --noheader "
                        "--format=Account,FairShare,RawUsage")
    fairshare: dict[str, dict] = {}
    for line in share.strip().splitlines():
        parts = line.split("|")
        if len(parts) >= 3 and parts[0]:
            fairshare[parts[0].strip()] = {
                "fairshare": parts[1].strip(),
                "raw_usage": parts[2].strip(),
            }

    result = []
    for acct, entry in sorted(projects.items()):
        result.append({
            "account": acct,
            "partitions": sorted(entry["partitions"]),
            "qos": sorted(entry["qos"]),
            **fairshare.get(acct, {}),
        })
    return result


@mcp.tool()
def get_project(account: str) -> dict:
    """One project's associations and fair-share standing by account ID
    (e.g. 'RB99999'). (IRI: GET /projects/{id})"""
    for proj in get_projects():
        if proj["account"] == account:
            return proj
    raise ValueError(
        f"Account {account!r} is not one the current user can charge. "
        f"Call get_projects to see the available accounts."
    )


# ---------------------------------------------------------------------------
# Jobs (IRI: POST/GET/DELETE/PATCH /compute/jobs)
# ---------------------------------------------------------------------------

def _apply_defaults(spec: JobSpec) -> JobSpec:
    """Fill HBW2's machine defaults into a spec the caller left partial:
    the default partition (mpc) and the default project/account. HBW2
    requires an account on every job, so if none can be resolved this raises
    a clear error rather than submitting a job the scheduler will reject."""
    if not spec.attributes.queue_name:
        spec.attributes.queue_name = config.default_partition()
    if spec.attributes.account is None:
        spec.attributes.account = config.default_account()
    if not spec.attributes.account:
        raise ValueError(
            "No project named. Every HBW2 job is billed to a project, so "
            "--account is mandatory. Set spec.attributes.account to a project "
            "ID (RIKEN 'RB...' or HPCI 'HP...'), or configure a default under "
            "defaults.account in ~/.hpc-agent/hokusai.json. Use get_projects "
            "to see which accounts you may charge."
        )
    return spec


@mcp.tool()
def render_job_script(spec: JobSpec) -> str:
    """Render the sbatch script for a JobSpec *without* submitting it, with
    HBW2 defaults applied. Use this to show the user exactly what will run
    before calling submit_job (the "show before you run" rule)."""
    return compute.render_script(_apply_defaults(spec))


@mcp.tool()
def submit_job(spec: JobSpec) -> dict:
    """Submit a batch job. Returns {job_id, script_path}. (IRI: POST /compute/jobs)

    HBW2 defaults are applied first (partition -> mpc, account -> the user's
    default project). Describe the job in resource terms — node_count,
    processes_per_node (MPI ranks/node), cpu_cores_per_process (threads/rank),
    memory, duration, queue_name, account — and this assembles the sbatch
    script. Launch MPI with launcher='srun'; set OMP_NUM_THREADS in
    environment to match cpu_cores_per_process for threaded code.

    Before calling this, show the user the spec (or render_job_script's
    output) and a one-line explanation, unless they asked to just run it."""
    return compute.submit(_apply_defaults(spec))


@mcp.tool()
def get_job_status(job_id: str) -> Job:
    """Normalized status of one job. (IRI: GET /compute/jobs/{id})"""
    jobs = compute.get_statuses([job_id])
    if not jobs:
        raise ValueError(f"Job {job_id} not found")
    return jobs[0]


@mcp.tool()
def get_job_statuses(job_ids: list[str]) -> list[Job]:
    """Status of several jobs, or — with an empty list — the current user's
    recent jobs (last ~2 days via accounting). (IRI: GET /compute/jobs)"""
    return compute.get_statuses(job_ids) if job_ids else compute.get_recent_statuses()


@mcp.tool()
def cancel_job(job_id: str) -> Job | str:
    """Cancel a job (scancel) and report its resulting state.
    (IRI: DELETE /compute/jobs/{id})"""
    return compute.cancel(job_id)


@mcp.tool()
def update_job(job_id: str, hold: bool | None = None,
               time_limit: str | None = None) -> Job:
    """Modify a queued/running job via scontrol, then report its state.
    (IRI: PATCH /compute/jobs/{id})

    hold=True holds a pending job; hold=False releases it. time_limit
    (HH:MM:SS or D-HH:MM:SS) changes the wall-time limit (subject to the
    partition maximum and your permissions)."""
    if hold is True:
        run_command(f"scontrol hold {quote_path(job_id)}")
    elif hold is False:
        run_command(f"scontrol release {quote_path(job_id)}")
    if time_limit:
        run_command(f"scontrol update JobId={quote_path(job_id)} "
                    f"TimeLimit={quote_path(time_limit)}")
    return get_job_status(job_id)


@mcp.tool()
def read_job_output(job_id: str, tail_lines: int | None = None) -> str:
    """Read a job's console output — the `slurm-<jobid>.out` file in the
    directory it was launched from. (extension — not an IRI endpoint)

    tail_lines, if set, returns only the last N lines (handy for a long or
    still-running job). Looks the workdir up from the job's status; falls
    back to the home directory if the scheduler no longer reports one."""
    jobs = compute.get_statuses([job_id])
    workdir = ""
    if jobs and jobs[0].status and jobs[0].status.meta_data:
        workdir = jobs[0].status.meta_data.get("workdir", "") or ""
    path = f"{workdir.rstrip('/')}/slurm-{job_id}.out" if workdir else f"~/slurm-{job_id}.out"
    reader = f"tail -n {int(tail_lines)}" if tail_lines else "cat"
    return run_command(f"{reader} {quote_path(path)}")


# ---------------------------------------------------------------------------
# Filesystem (IRI: /storage operations)
# ---------------------------------------------------------------------------

@mcp.tool()
def fs_ls(path: str = ".", all_entries: bool = True) -> str:
    """List a directory (long form, ISO timestamps). all_entries=True
    includes dotfiles. (IRI: GET /storage listing)"""
    flags = "-la" if all_entries else "-l"
    return run_command(f"ls {flags} --time-style=long-iso {quote_path(path)}")


@mcp.tool()
def fs_stat(path: str) -> str:
    """Detailed metadata for a path (type, size, perms, owner, times)."""
    return run_command(f"stat {quote_path(path)}")


@mcp.tool()
def fs_view(path: str) -> str:
    """Print a text file in full (truncated if very large)."""
    return run_command(f"cat {quote_path(path)}")


@mcp.tool()
def fs_head(path: str, lines: int = 40) -> str:
    """First N lines of a file."""
    return run_command(f"head -n {int(lines)} {quote_path(path)}")


@mcp.tool()
def fs_tail(path: str, lines: int = 40) -> str:
    """Last N lines of a file (e.g. tailing a job's output)."""
    return run_command(f"tail -n {int(lines)} {quote_path(path)}")


@mcp.tool()
def fs_mkdir(path: str) -> str:
    """Create a directory, including parents (mkdir -p)."""
    run_command(f"mkdir -p {quote_path(path)}")
    return f"Created {path}"


@mcp.tool()
def fs_upload(local_path: str, remote_path: str) -> dict:
    """Upload a local file to the cluster (rsync/scp), verifying the
    checksum end-to-end. (IRI: PUT /storage)"""
    return upload_file(local_path, remote_path)


@mcp.tool()
def fs_download(remote_path: str, local_path: str) -> dict:
    """Download a file from the cluster to the local machine (rsync/scp),
    verifying the checksum end-to-end. (IRI: GET /storage content)"""
    return download_file(remote_path, local_path)


@mcp.tool()
def fs_checksum(path: str, algorithm: str = "sha256") -> str:
    """Checksum of a remote file. algorithm: 'sha256' (default) or 'md5'."""
    tool = {"sha256": "sha256sum", "md5": "md5sum"}.get(algorithm)
    if not tool:
        raise ValueError("algorithm must be 'sha256' or 'md5'")
    return run_command(f"{tool} {quote_path(path)}")


@mcp.tool()
def fs_cp(source: str, dest: str, recursive: bool = False) -> str:
    """Copy a file (recursive=True for directories)."""
    flag = "-r " if recursive else ""
    run_command(f"cp {flag}{quote_path(source)} {quote_path(dest)}")
    return f"Copied {source} -> {dest}"


@mcp.tool()
def fs_mv(source: str, dest: str) -> str:
    """Move or rename a path."""
    run_command(f"mv {quote_path(source)} {quote_path(dest)}")
    return f"Moved {source} -> {dest}"


@mcp.tool()
def fs_chmod(path: str, mode: str) -> str:
    """Change permissions (mode like '755' or 'u+x'). recursion is not
    applied — pass a directory only if you mean just that directory."""
    run_command(f"chmod {quote_path(mode)} {quote_path(path)}")
    return f"chmod {mode} {path}"


@mcp.tool()
def fs_chown(path: str, owner: str) -> str:
    """Change ownership (owner like 'user' or 'user:group'). Usually only
    works within your own group; the cluster may reject it otherwise."""
    run_command(f"chown {quote_path(owner)} {quote_path(path)}")
    return f"chown {owner} {path}"


@mcp.tool()
def fs_symlink(target: str, link_path: str) -> str:
    """Create a symbolic link at link_path pointing to target."""
    run_command(f"ln -s {quote_path(target)} {quote_path(link_path)}")
    return f"Linked {link_path} -> {target}"


@mcp.tool()
def fs_compress(paths: list[str], archive: str,
                compression: CompressionType = CompressionType.GZIP) -> str:
    """Create a tar archive of one or more paths. compression: none, gzip
    (default), bzip2, or xz."""
    flag = {
        CompressionType.NONE: "-cf",
        CompressionType.GZIP: "-czf",
        CompressionType.BZIP2: "-cjf",
        CompressionType.XZ: "-cJf",
    }[compression]
    quoted = " ".join(quote_path(p) for p in paths)
    run_command(f"tar {flag} {quote_path(archive)} {quoted}")
    return f"Created archive {archive}"


@mcp.tool()
def fs_extract(archive: str, dest: str = ".") -> str:
    """Extract a tar archive into dest (compression auto-detected)."""
    run_command(f"mkdir -p {quote_path(dest)} && "
                f"tar -xf {quote_path(archive)} -C {quote_path(dest)}")
    return f"Extracted {archive} -> {dest}"


# ---------------------------------------------------------------------------
# Escape hatch
# ---------------------------------------------------------------------------

@mcp.tool()
def run_command_on_cluster(command: str) -> str:
    """Run an arbitrary shell command on the login node (extension — not an
    IRI endpoint). Before calling this, show the user the exact command and
    a one-line explanation of what it does, then call it — skip the preview
    only if the user explicitly asked to just run something.

    Do not run heavy computation on the login node (it is shared and lightly
    resourced) — submit a job instead. Compute nodes have no direct internet
    route; a job that must fetch something reaches the web through the
    front-end proxy at http://$SLURM_SUBMIT_HOST:3128."""
    return run_command(command)


def main():
    serve(mcp)


if __name__ == "__main__":
    main()
