"""The unified MCP tool surface — one copy of every tool, shared by every
registered facility.

Every tool takes an explicit `facility` argument (the slug from
get_facilities(), e.g. "rikyu") as its first parameter and dispatches to
that facility's registered SchedulerBackend (facilities.registry) and
config.Facility (hpc_agent_core.config) — there is no per-facility copy of
this file. An unknown facility slug raises a ValueError listing every valid
slug (see config.get_facility / facilities.registry.get_backend), so a
wrong or guessed name fails loudly rather than silently reaching the wrong
cluster.

Tool groups mirror the IRI Facility API resource groups (facility, status,
account, compute, filesystem); see IRI_CHECKLIST.md at the repo root for
coverage. Tools are thin verbs — workflow knowledge (when to pick which
facility, how to read a failed job) lives in plugins/hpc/skills/, not in
long docstrings here.
"""
import shlex
from functools import wraps
from pathlib import Path

import hpc_mcp  # noqa: F401 -- import for its side effect: registers every facility
from hpc_agent_core.mcp_server import MCPServer

from hpc_agent_core import config, middleware
from hpc_agent_core.middleware import (
    download_file,
    quote_path,
    run_command,
    upload_file,
)
from hpc_agent_core.models import CompressionType, Job, JobSpec
from hpc_agent_core.serving import serve
from facilities.registry import get_backend

mcp = MCPServer("hpc-mcp")

_TAR_FLAGS = {
    CompressionType.NONE: "cf",
    CompressionType.GZIP: "czf",
    CompressionType.BZIP2: "cjf",
    CompressionType.XZ: "cJf",
}


# ---------------------------------------------------------------------------
# Facility / resource info
# ---------------------------------------------------------------------------

def _require_facility_configuration(facility: str) -> None:
    """Require an explicit, usable SSH destination before a tool dispatches.

    Registered default hosts describe a facility; they are not evidence that
    this user has configured access to it.  Checking here makes an absent,
    malformed, or incomplete config fail with the same actionable setup
    directions before a backend can return a misleading capability result.
    Remote operations subsequently perform their normal SSH call, which
    turns a bad host/key into the same setup guidance with the SSH detail.
    """
    config.require_facility_configuration(facility)


def _configured_facility_tool(func):
    """Decorate every facility-scoped MCP tool with the common guard."""
    @wraps(func)
    def wrapped(facility: str, *args, **kwargs):
        _require_facility_configuration(facility)
        return func(facility, *args, **kwargs)
    return wrapped

@mcp.tool()
def get_facilities() -> list[dict]:
    """List every facility this server knows about — call this first
    whenever you don't already know the exact facility slug to pass to
    every other tool here. Every other tool's `facility` argument must be
    one of the `slug` values returned here; passing anything else raises a
    clear error listing the valid slugs, but it's cheaper to just check
    first."""
    listing = [
        {"slug": f.slug, "display_name": f.display_name, "description": f.description}
        for f in config.list_facilities()
    ]
    # A facility whose module failed to import is skipped at startup so it
    # can't deny the server to everyone else — but it must not vanish
    # silently, or a user asking "why can't I see machine X" gets no answer.
    for slug, error in hpc_mcp.FAILED_FACILITIES.items():
        listing.append({
            "slug": slug,
            "display_name": f"{slug} (unavailable)",
            "description": f"This facility failed to load and cannot be used: {error}. "
                            "Report it to whoever maintains this deployment.",
            "unavailable": True,
        })
    return listing


@mcp.tool()
# Not gated: reads this facility's packaged facts JSON and opens no
# connection, so it must answer before the user has configured SSH —
# that is how an agent orients someone who has not set up yet.
def get_facility(facility: str) -> dict:
    """Static facts for one facility: partitions, the resource-limit table,
    storage tiers, modules, and Spack. (IRI: GET /api/v1/facility)

    Args:
        facility: Facility slug, e.g. "rikyu". See get_facilities().
    """
    return config.load_facts(facility)


@mcp.tool()
@_configured_facility_tool
def get_resources(facility: str) -> list[dict]:
    """Live occupancy for one facility's compute partitions ("resources" in
    IRI terms) — allocated/idle/other/total node counts, i.e. "will a job
    start soon". A live query, unlike get_facility's static data.
    (IRI: GET /api/v1/status/resources)
    """
    return get_backend(facility).get_live_resources()


@mcp.tool()
@_configured_facility_tool
def get_resource(facility: str, name: str) -> dict:
    """Live occupancy for one named partition. (IRI: GET /api/v1/status/resources/{resource_id})"""
    for p in get_backend(facility).get_live_resources():
        if p["partition"] == name:
            return p
    raise ValueError(f"No resource named {name!r} on facility {facility!r}")


@mcp.tool()
@_configured_facility_tool
def get_drained_nodes(facility: str) -> list[dict]:
    """Nodes currently drained/down and why (extension — not an IRI
    endpoint, but directly useful for "why won't my job start")."""
    return get_backend(facility).get_drained_nodes()


@mcp.tool()
@_configured_facility_tool
def get_projects(facility: str) -> list[dict]:
    """Projects (scheduler accounts) the current user may charge on this
    facility, each with the partitions and QOS it allows.
    (IRI: GET /api/v1/account/projects)

    Each entry's `account` is what goes in a JobSpec's
    `attributes.account`. Some facilities return more than the bare
    associations — e.g. a facility with fair-share scheduling also reports
    the standing that governs when a queued job actually starts. Requires
    per-project accounting; a facility without it raises a clear error.
    """
    return get_backend(facility).get_projects()


@mcp.tool()
@_configured_facility_tool
def get_project(facility: str, account: str) -> dict:
    """Details for a single project/account.
    (IRI: GET /api/v1/account/projects/{project_id})"""
    for p in get_backend(facility).get_projects():
        if p["account"] == account:
            return p
    raise ValueError(
        f"Account {account!r} is not one the current user can charge on facility "
        f"{facility!r}. Call get_projects to see the available accounts."
    )


@mcp.tool()
@_configured_facility_tool
def get_project_allocations(facility: str, project_id: str) -> dict:
    """A project's allocation limits — the account-wide ceilings shared by
    everyone under it.
    (IRI: GET /api/v1/account/projects/{project_id}/project_allocations)

    On Slurm: GrpTRESMins caps cumulative core-time, GrpTRESRunMins caps
    concurrently-running core-time. Either may be empty on a site that
    doesn't enforce that limit — that's not an error.
    """
    return get_backend(facility).get_project_allocations(project_id)


@mcp.tool()
@_configured_facility_tool
def get_user_allocations(facility: str, project_id: str) -> dict:
    """The current user's allocation share within a project — the per-user
    slice of get_project_allocations' account-wide ceiling.
    (IRI: GET /api/v1/account/projects/{project_id}/project_allocations/{id}/user_allocations)
    """
    return get_backend(facility).get_user_allocations(project_id)


# ---------------------------------------------------------------------------
# Job submit / status / cancel / update
# ---------------------------------------------------------------------------

@mcp.tool()
# Not gated: apply_defaults/validate_spec/render_script are pure local
# work for every facility (asserted in tests/conformance.py), so this
# stays useful before SSH is configured.
def render_job_script(facility: str, spec: JobSpec) -> str:
    """Render the batch script for a JobSpec *without* submitting it, with
    that facility's defaults already applied. Use this to show the user
    exactly what will run before calling submit_job (the "show before you
    run" rule) — it costs nothing and touches no scheduler.
    (Extension — no IRI counterpart.)
    """
    backend = get_backend(facility)
    backend.apply_defaults(spec)
    backend.validate_spec(spec)
    return backend.render_script(spec)


@mcp.tool()
@_configured_facility_tool
def submit_job(facility: str, spec: JobSpec) -> dict:
    """Submit a job to a facility's scheduler. Show the user the spec
    before submitting unless they asked to just run it — use
    render_job_script for an exact preview.

    Facility defaults are filled in first: a facility with one obvious
    partition supplies it when spec.attributes.queue_name is blank, and a
    facility that requires a project/account supplies the user's configured
    default (raising a clear, actionable error if none can be resolved).
    (IRI: POST /api/v1/compute/job/{resource_id})

    Args:
        facility: Facility slug, e.g. "rikyu". See get_facilities().
        spec: The job to submit.
    """
    backend = get_backend(facility)
    backend.apply_defaults(spec)
    backend.validate_spec(spec)
    return backend.submit(spec)


@mcp.tool()
@_configured_facility_tool
def get_job_status(facility: str, job_id: str) -> Job:
    """Status of a single job. (IRI: GET /api/v1/compute/status/{resource_id}/{job_id})"""
    jobs = get_backend(facility).get_statuses([job_id])
    if not jobs:
        raise ValueError(f"Job {job_id} not found on facility {facility!r}")
    return jobs[0]


@mcp.tool()
@_configured_facility_tool
def get_job_statuses(facility: str, job_ids: list[str]) -> list[Job]:
    """Status of several jobs, or — if job_ids is empty — every job the
    current user has touched in roughly the last two days (on a facility
    with Slurm accounting; otherwise just the live queue).
    (IRI: POST /api/v1/compute/status/{resource_id})"""
    backend = get_backend(facility)
    return backend.get_statuses(job_ids) if job_ids else backend.get_recent_statuses()


@mcp.tool()
@_configured_facility_tool
def cancel_job(facility: str, job_id: str) -> Job | str:
    """Cancel a queued or running job. Confirm with the user before
    cancelling. (IRI: DELETE /api/v1/compute/cancel/{resource_id}/{job_id})"""
    return get_backend(facility).cancel(job_id)


@mcp.tool()
@_configured_facility_tool
def update_job(facility: str, job_id: str, spec: JobSpec) -> Job:
    """Apply a JobSpec to an already-submitted job; return its new state.
    (IRI: PUT /api/v1/compute/job/{resource_id}/{job_id})

    Only the fields you actually set are applied, and only those a
    scheduler can change after submission — typically the job name, wall
    time, partition, account, reservation and node count. Anything else you
    set is reported back in the returned status message as not applied,
    rather than silently ignored.

    Only affects jobs still queued or running, and is subject to the
    scheduler's own permission rules (some fields can only be lowered, not
    raised, by a non-admin).
    """
    return get_backend(facility).update(job_id, spec)


@mcp.tool()
@_configured_facility_tool
def run_command_on_cluster(facility: str, command: str) -> str:
    """Run an arbitrary shell command on a facility's login node.

    **Extension, and the most consequential one here.** IRI has no such
    endpoint, almost certainly on purpose: this bypasses every other tool's
    structure — submit_job's validation and defaults, fs_rm's refusal list,
    the whole typed surface. Prefer the specific tool whenever one fits,
    and reach for this only for things no tool covers (`module avail`,
    quota checks, attaching to a running job for diagnostics).

    Before calling this, sketch the proposed work, show the exact command(s)
    and what each will do, state whether they change anything, then ask for
    explicit permission and wait for the user's answer. Permission covers
    only the commands shown; preview and ask again before adding or
    materially changing one.

    Prefer several short, focused calls over one long command joined with
    many `;`, `&&`, or `||` operators. Inspect each result before continuing
    so a failed assumption cannot cascade into later steps. A short pipeline
    that performs one coherent check is fine. Each call starts a fresh login
    shell in `$HOME`, so `cd`, loaded modules, variables, and activated
    environments do not persist between calls.

    Afterward, summarize what actually ran, the important results, and any
    state that changed; do not merely paste raw output. Do not run heavy
    computation on the login node — submit a job instead.
    """
    return run_command(facility, command)


# ---------------------------------------------------------------------------
# Filesystem operations
# ---------------------------------------------------------------------------

@mcp.tool()
@_configured_facility_tool
def fs_ls(facility: str, path: str = ".", show_hidden: bool = True) -> str:
    """List a directory's contents (long form). (IRI: GET /api/v1/filesystem/ls/{resource_id})"""
    flags = "-la" if show_hidden else "-l"
    return run_command(facility, f"ls {flags} {quote_path(path)}")


@mcp.tool()
@_configured_facility_tool
def fs_stat(facility: str, path: str) -> str:
    """File/directory metadata: size, permissions, timestamps, owner. (IRI: GET /api/v1/filesystem/stat/{resource_id})"""
    return run_command(facility, f"stat {quote_path(path)}")


@mcp.tool()
@_configured_facility_tool
def fs_view(facility: str, path: str) -> str:
    """Read a whole text file's contents. (IRI: GET /api/v1/filesystem/view/{resource_id})"""
    return run_command(facility, f"cat {quote_path(path)}")


@mcp.tool()
@_configured_facility_tool
def fs_head(facility: str, path: str, lines: int = 20) -> str:
    """Read the first N lines of a file. (IRI: GET /api/v1/filesystem/head/{resource_id})"""
    return run_command(facility, f"head -n {int(lines)} {quote_path(path)}")


@mcp.tool()
@_configured_facility_tool
def fs_tail(facility: str, path: str, lines: int = 20) -> str:
    """Read the last N lines of a file — useful for checking a running
    job's stdout/stderr. (IRI: GET /api/v1/filesystem/tail/{resource_id})"""
    return run_command(facility, f"tail -n {int(lines)} {quote_path(path)}")


@mcp.tool()
@_configured_facility_tool
def fs_mkdir(facility: str, path: str) -> str:
    """Create a directory, including parents as needed. (IRI: POST /api/v1/filesystem/mkdir/{resource_id})"""
    return run_command(facility, f"mkdir -p {quote_path(path)}")


@mcp.tool()
@_configured_facility_tool
def fs_upload(facility: str, local_path: str, remote_path: str) -> dict:
    """Upload a local file to a facility via rsync (falling back to scp),
    with a SHA-256 verification of the transfer. (IRI: POST /api/v1/filesystem/upload/{resource_id} — deviation: rsync/scp)

    Stage uploads under `~/agent/work/...` (the agent's visible scratch
    area), never in the home-directory root."""
    return upload_file(facility, Path(local_path), remote_path)


@mcp.tool()
@_configured_facility_tool
def fs_download(facility: str, remote_path: str, local_path: str | None = None) -> dict:
    """Download a file from a facility via rsync (falling back to scp),
    with a SHA-256 verification of the transfer. (IRI: GET /api/v1/filesystem/download/{resource_id} — deviation: rsync/scp)

    local_path defaults to the same filename in the current working
    directory.
    """
    dest = Path(local_path) if local_path else Path.cwd() / Path(remote_path).name
    return download_file(facility, remote_path, dest)


#: Paths fs_rm refuses outright, after normalisation. Deleting any of these
#: is far more likely to be a mistake (an unset variable, a stray default,
#: a glob that expanded to nothing) than an intent, and the cost of being
#: wrong is unrecoverable — there is no trash on these filesystems.
_RM_REFUSED = {"", ".", "..", "/", "~", "*", "$HOME"}


@mcp.tool()
@_configured_facility_tool
def fs_rm(facility: str, path: str, recursive: bool = False) -> str:
    """Delete a file, or (with recursive=True) a directory tree, on the
    cluster. (IRI: DELETE /api/v1/filesystem/rm/{resource_id})

    **Destructive and not recoverable — these filesystems have no trash.
    Confirm the exact path with the user before calling this, every time,
    even if they asked for a deletion in general terms.**

    recursive is required to remove a directory: without it this is a plain
    `rm`, which fails on a directory rather than silently taking the tree
    with it. The IRI spec takes only a path; this extra flag is a
    deliberate deviation so "delete this file" can never become "delete
    this whole tree" through a typo.

    Refuses a handful of paths outright (the home directory itself, `/`,
    `.`, `..`, a bare glob) — deleting those is almost always an accident.
    That guard catches mistakes made *through this tool*; it is not a
    security boundary, because `run_command_on_cluster` can run `rm`
    directly. Treat the confirmation above as the real protection.
    """
    normalized = middleware.norm_path(path).strip().rstrip("/")
    if normalized in _RM_REFUSED or path.strip() in _RM_REFUSED:
        raise ValueError(
            f"Refusing to delete {path!r}: that resolves to the home directory "
            "or a filesystem root. Name the specific file or subdirectory to "
            "remove."
        )
    flag = "-r " if recursive else ""
    quoted = quote_path(path)
    return run_command(
        facility,
        f"rm {flag}-- {quoted} && echo removed: {quoted}",
    )


@mcp.tool()
@_configured_facility_tool
def fs_checksum(facility: str, path: str) -> str:
    """SHA-256 checksum of a remote file. (IRI: GET /api/v1/filesystem/checksum/{resource_id})"""
    return run_command(facility, f"sha256sum {quote_path(path)}")


@mcp.tool()
@_configured_facility_tool
def fs_cp(facility: str, source: str, dest: str, recursive: bool = False) -> str:
    """Copy a file or (with recursive=True) a directory tree on the
    cluster. (IRI: POST /api/v1/filesystem/cp/{resource_id})"""
    flag = "-r " if recursive else ""
    return run_command(facility, f"cp {flag}{quote_path(source)} {quote_path(dest)}")


@mcp.tool()
@_configured_facility_tool
def fs_mv(facility: str, source: str, dest: str) -> str:
    """Move or rename a file/directory on the cluster. (IRI: POST /api/v1/filesystem/mv/{resource_id})"""
    return run_command(facility, f"mv {quote_path(source)} {quote_path(dest)}")


@mcp.tool()
@_configured_facility_tool
def fs_chmod(facility: str, path: str, mode: str) -> str:
    """Change a file/directory's permissions, e.g. mode="755". (IRI: PUT /api/v1/filesystem/chmod/{resource_id})"""
    return run_command(facility, f"chmod {shlex.quote(mode)} {quote_path(path)}")


@mcp.tool()
@_configured_facility_tool
def fs_chown(facility: str, path: str, owner: str) -> str:
    """Change a file/directory's owner (and optionally group, as
    "user:group"). Most users can only chown within their own group's
    permissions — the scheduler's filesystem still enforces the actual ACL.
    (IRI: PUT /api/v1/filesystem/chown/{resource_id})"""
    return run_command(facility, f"chown {shlex.quote(owner)} {quote_path(path)}")


@mcp.tool()
@_configured_facility_tool
def fs_symlink(facility: str, target: str, link_name: str) -> str:
    """Create a symbolic link at link_name pointing to target. (IRI: POST /api/v1/filesystem/symlink/{resource_id})"""
    return run_command(facility, f"ln -s {quote_path(target)} {quote_path(link_name)}")


@mcp.tool()
@_configured_facility_tool
def fs_compress(facility: str, paths: list[str], archive_path: str,
                 compression: CompressionType = CompressionType.GZIP,
                 match_pattern: str | None = None,
                 dereference: bool = False) -> str:
    """Create a tar archive from one or more remote paths.
    (IRI: POST /api/v1/filesystem/compress/{resource_id})

    match_pattern: a regex passed to `find -regex` to archive only the
        matching files beneath `paths`, instead of everything.
    dereference: follow symlinks (tar -h) rather than storing the links.
    """
    deref = "h" if dereference else ""
    flag = f"-{deref}{_TAR_FLAGS[compression]}"
    quoted_paths = " ".join(quote_path(p) for p in paths)
    if match_pattern:
        cmd = (f"find {quoted_paths} -regex {shlex.quote(match_pattern)} -print0 | "
               f"tar {flag} {quote_path(archive_path)} --null -T -")
    else:
        cmd = f"tar {flag} {quote_path(archive_path)} {quoted_paths}"
    return run_command(facility, cmd)


@mcp.tool()
@_configured_facility_tool
def fs_extract(facility: str, archive_path: str, dest_dir: str = ".") -> str:
    """Extract an archive on the cluster into dest_dir (created if needed).
    Compression format is auto-detected by tar. (IRI: POST /api/v1/filesystem/extract/{resource_id})"""
    return run_command(
        facility,
        f"mkdir -p {quote_path(dest_dir)} && tar -xf {quote_path(archive_path)} -C {quote_path(dest_dir)}",
    )


def main():
    serve(mcp)


if __name__ == "__main__":
    main()
