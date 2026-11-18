"""Remote-execution layer: all cluster interaction funnels through here.

Built on remotemanager's Computer.cmd (a direct SSH exec, ~0.6s per call).
Three conventions are enforced in one place:

- Commands run under a login shell (the scheduler's own configuration is
  usually only visible through the login environment; a bare non-login
  shell often can't find it).
- The working directory is the user's home, so relative paths behave the
  way users expect.
- Commands and file contents travel base64-encoded, so arbitrary quoting
  survives the SSH layer intact.
- Non-zero exit codes raise RuntimeError so FastMCP surfaces a clean tool
  error; callers never need to parse error text from the return value.

Every function here takes an explicit `facility` (a config.Facility or its
slug) as its first argument — this one process serves every onboarded
facility, so there is no process-wide "the" cluster to talk to. Nothing in
this module touches config or SSH at import time — get_frontend() is built
lazily, on first use, inside a tool call. This is a deliberate invariant:
the MCP server must never fail to start because one facility's config is
missing or malformed; only an individual tool call that actually needs SSH
for that facility should fail, with a clear message pointing at the
configuring skill.

Extending this: a facility cannot edit this file. get_frontend()'s
Computer() construction (login-shell template, bash submitter, python3) is
a fixed default; if a facility genuinely needs different connection
parameters, set them via config.register_facility(computer_defaults=...) —
see config.COMPUTER_OPTION_NAMES for the full set.
"""
import base64
import contextlib
import hashlib
import re
import shlex
import sys
from pathlib import Path

from remotemanager import Computer

from hpc_agent_core import config
from hpc_agent_core.config import Facility

# Cap what a single call can pour into the MCP context.
OUTPUT_LIMIT_BYTES = 200_000

#: Hosts remotemanager's URL.is_local treats as local (no ssh at all, per
#: URL.ssh returning ""). Kept here too so doctor.py and facilities can
#: label output correctly without importing remotemanager directly.
LOCAL_HOSTS_PREFIX = "127."
LOCAL_HOST = "localhost"


def is_local_host(host: str) -> bool:
    """True if host resolves to a purely local connection (no SSH at all).

    Mirrors remotemanager.connection.url.URL.is_local's exact check
    (host == "localhost" or host.startswith("127.")) without importing
    URL directly — this is a plain string check, not a live connection
    property, so duplicating the two-line condition is simpler than
    constructing a Computer just to ask it.
    """
    return host == LOCAL_HOST or host.startswith(LOCAL_HOSTS_PREFIX)


def norm_path(path: str) -> str:
    """Normalize a leading home-directory shorthand to a relative path.

    run_command sets CWD to $HOME, so relative paths already resolve there.
    Scheduler directives are not shell-evaluated, while shell renderers may
    quote paths and suppress expansion.  Therefore accept the conventional
    home forms (``~``, ``$HOME``, and ``${HOME}``) and turn them into paths
    relative to that known working directory instead of emitting a literal
    dollar sign or tilde.
    """
    if path in ("~", "$HOME", "${HOME}"):
        return "."
    for prefix in ("~/", "$HOME/", "${HOME}/"):
        if path.startswith(prefix):
            return path[len(prefix):]
    return path


def quote_path(path: str) -> str:
    """shlex.quote a remote path after normalizing a leading ~."""
    return shlex.quote(norm_path(path))


def get_frontend(facility: "Facility | str") -> Computer:
    """The Computer targeting `facility`'s login node (or the local host, if
    config.ssh_host(facility) is "localhost"/"127.*" — remotemanager's
    URL.is_local already routes that case to a bare local shell with no ssh
    subprocess at all; no transport-layer change is needed here for it).

    Deliberately NOT cached (it was, via @lru_cache, until this was found to
    be pure staleness risk for no benefit — Computer.cmd() already does a
    fresh SSH exec per call with no persistent connection state on the
    object, so caching only meant a config file edit wasn't picked up until
    the whole MCP server restarted). Reconstructing it is cheap: two config
    reads plus a plain constructor call, negligible next to the network
    round-trip callers make immediately after.

    Every remotemanager.Computer constructor option is supported here, not
    just the four (template/host/submitter/python) every facility happened
    to share so far — see config.COMPUTER_OPTION_NAMES and
    config.computer_kwargs(). A facility that needs something different
    (a non-bash shell, a longer timeout, a specific keyfile, ...) sets it
    via register_facility(computer_defaults=...); it does not need to touch
    this function.
    """
    fac = config.resolve(facility)
    return Computer(host=config.ssh_host(fac), **config.computer_kwargs(fac))


#: Substrings that mean "we never got a shell on the cluster", as opposed to
#: "a command ran there and failed".
#:
#: Deliberately narrow. An earlier, looser version matched a bare
#: "permission denied", which turned Slurm's own "Access/permission denied
#: for job 9041823" — a perfectly clear scheduler error — into a wall of SSH
#: setup directions. Every entry here must be text only ssh itself produces:
#: ssh's auth failure always carries the parenthesised method list
#: ("Permission denied (publickey)"), which a scheduler message doesn't.
#: The reliable signal is the exit code below; these are the backstop.
_UNREACHABLE_MARKERS = (
    "permission denied (",
    "could not resolve hostname",
    "name or service not known",
    "no route to host",
    "connection refused",
    "connection timed out",
    "host key verification failed",
    "network is unreachable",
    "ssh: ",
)


#: ssh(1) exits 255 for its own failures (bad host, refused key, DNS, ...),
#: reserving 0-254 for the remote command's own status. Checked in addition
#: to the text markers because remotemanager does not always surface ssh's
#: stderr — a wrong host can arrive here as exit 255 with empty output, and
#: matching on text alone then yields a bare "command exited with code 255"
#: with nothing for a new user to act on. A remote command can technically
#: exit 255 itself; that costs an over-helpful message, which is the right
#: side to err on.
_SSH_FAILURE_RETURNCODE = 255


def _looks_unreachable(detail: str, returncode: int | None = None) -> bool:
    if returncode == _SSH_FAILURE_RETURNCODE:
        return True
    text = (detail or "").lower()
    return any(marker in text for marker in _UNREACHABLE_MARKERS)


def _unreachable_message(fac, detail: str) -> str:
    """Setup directions for a facility we couldn't reach.

    A configured-but-broken facility gets the same actionable directions as
    a never-configured one, with its own error appended — the fix is the
    same (correct the host/key in the config file), and a bare SSH error
    tells a new user nothing about where the setting even lives.
    """
    configured = config.config_path(fac).exists()
    problem = (
        f"Facility {fac.slug!r} ({fac.display_name}) is configured at "
        f"{config.config_path(fac)}, but the connection failed — the settings "
        f"there are probably wrong or the key isn't registered yet."
        if configured else ""
    )
    return config.setup_instructions(fac, problem=problem, ssh_error=detail)


def run_command(facility: "Facility | str", cmd: str) -> str:
    """Run a shell command on `facility`'s login node; return stdout.

    Raises RuntimeError on non-zero exit so callers receive a clean MCP tool
    error rather than having to parse error text from the output. When the
    failure is "we never reached the cluster" rather than "a command failed
    there", the error carries this facility's full setup directions — see
    config.setup_instructions().
    Output beyond OUTPUT_LIMIT_BYTES is truncated with a marker.
    """
    fac = config.resolve(facility)
    payload = 'cd "$HOME" && ' + cmd
    encoded = base64.b64encode(payload.encode()).decode()
    # remotemanager may print progress to stdout, which would corrupt the
    # MCP stdio transport — divert anything it emits.
    with contextlib.redirect_stdout(sys.stderr):
        try:
            result = get_frontend(fac).cmd(
                f"echo {encoded} | base64 -d | bash -l", raise_errors=False,
            )
        except Exception as exc:
            raise RuntimeError(_unreachable_message(fac, str(exc))) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        if (_looks_unreachable(detail, result.returncode)
                or not config.config_path(fac).exists()):
            raise RuntimeError(_unreachable_message(
                fac, detail or f"ssh exited {result.returncode}"))
        raise RuntimeError(detail or f"command exited with code {result.returncode}")
    output = result.stdout or ""
    if len(output) > OUTPUT_LIMIT_BYTES:
        output = (output[:OUTPUT_LIMIT_BYTES]
                  + f"\n[output truncated at {OUTPUT_LIMIT_BYTES} bytes]")
    return output


#: Directories grep_files skips by default — VCS metadata and the usual
#: dependency/venv/build dirs, mirroring what a local Grep tool excludes.
_GREP_DEFAULT_EXCLUDES = [".git", ".svn", ".hg", "node_modules", "__pycache__",
                          ".venv", "venv", ".mypy_cache", ".pytest_cache"]

#: A glob pattern is embedded in the remote shell command unquoted (it must
#: undergo real glob expansion, so it can't be shlex.quote()'d like a normal
#: argument) — so it's validated against this allowlist first instead.
#: Deliberately excludes shell metacharacters (;|&`$(){}<> etc. beyond the
#: brace-expansion {,} pair) that would otherwise let a pattern smuggle in
#: a second command.
_GLOB_SAFE_RE = re.compile(r"^[A-Za-z0-9_./*?\[\]{},!+@-]+$")


def grep_files(facility: "Facility | str", pattern: str, path: str = ".", *,
                glob: str | None = None, case_insensitive: bool = False,
                max_results: int = 200) -> str:
    """Search file contents on `facility`'s cluster, recursively, for a
    regex — remote analogue of a local Grep tool. Returns grep-style
    "path:line:text" output, one match per line, capped at max_results
    (truncated with a marker if there are more).

    Binary files and common VCS/dependency directories are skipped by
    default (see _GREP_DEFAULT_EXCLUDES). `glob` filters which filenames
    are searched (e.g. "*.py"); `pattern` is a POSIX extended-ish regex,
    exactly what `grep -rn` accepts.

    `pattern` is passed through shlex.quote — unlike glob_files's pattern,
    it never needs to be interpreted by the shell itself, only by grep, so
    it can be safely quoted as an opaque argument with no character
    restriction.
    """
    exclude_flags = " ".join(f"--exclude-dir={shlex.quote(d)}" for d in _GREP_DEFAULT_EXCLUDES)
    include_flag = f"--include={shlex.quote(glob)}" if glob else ""
    ci_flag = "-i" if case_insensitive else ""
    cmd = (
        f"grep -rnI {exclude_flags} {include_flag} {ci_flag} "
        f"-- {shlex.quote(pattern)} {quote_path(path)}; "
        # grep exits 1 for "no matches" — a normal, non-error outcome here,
        # not something run_command should raise on. Exit 2+ is a real
        # error (bad regex, unreadable path, ...) and should still raise.
        "ec=$?; [ $ec -le 1 ] && exit 0; exit $ec"
    )
    output = run_command(facility, cmd)
    lines = output.splitlines()
    if len(lines) > max_results:
        lines = lines[:max_results] + [f"[truncated at {max_results} results]"]
    return "\n".join(lines)


def glob_files(facility: "Facility | str", pattern: str, path: str = ".") -> str:
    """Find files under `path` on `facility`'s cluster matching a shell glob
    pattern — remote analogue of a local Glob tool. Supports `**` for
    recursive matching (bash's globstar) and standard wildcards (`*`, `?`,
    `[...]`, `{...}`). Returns one path per line, relative to `path`,
    sorted; empty string if nothing matches (not an error).

    `pattern` must pass _GLOB_SAFE_RE — it's embedded in the remote shell
    command so the shell's own glob engine can expand it, which rules out
    shlex.quote() (that would suppress expansion entirely, matching the
    pattern as a literal filename instead). The allowlist keeps this to
    genuine glob syntax, rejecting anything that could smuggle in a second
    shell command.
    """
    if not _GLOB_SAFE_RE.match(pattern):
        raise ValueError(
            f"glob pattern {pattern!r} contains characters outside what's "
            "allowed for a glob (letters, digits, / . * ? [ ] { } , ! + @ -)"
        )
    cmd = (
        f"cd {quote_path(path)} && "
        f"shopt -s globstar nullglob && "
        f"for f in {pattern}; do printf '%s\\n' \"$f\"; done | sort"
    )
    return run_command(facility, cmd)


def write_remote_file(facility: "Facility | str", path: str, content: str | bytes) -> str:
    """Write a file on `facility`'s cluster, creating parent directories.

    Relative paths resolve against the home directory. Returns the absolute
    path of the written file; raises on failure.
    """
    path = norm_path(path)
    raw = content if isinstance(content, bytes) else content.encode()
    encoded = base64.b64encode(raw).decode()
    quoted = shlex.quote(path)
    output = run_command(
        facility,
        f'mkdir -p "$(dirname {quoted})" && '
        f"echo {encoded} | base64 -d > {quoted} && realpath {quoted}"
    )
    abs_path = output.strip().splitlines()[-1] if output.strip() else ""
    if not abs_path.startswith("/"):
        raise RuntimeError(f"Failed to write {path}: {output}")
    return abs_path


# ---------------------------------------------------------------------------
# File transfer (local ↔ remote)
# ---------------------------------------------------------------------------

def _make_transport(facility: "Facility | str"):
    """Return a fresh rsync transport for `facility`, falling back to scp if
    rsync < 3.0.

    remotemanager's rsync transport defaults to flags "auvh" (+ --checksum),
    where "u" is rsync's --update: skip the copy whenever the destination
    file's mtime is newer than the source's. fs_upload/fs_download are
    explicit, one-shot "make this path equal to that path" operations, not a
    two-way sync — if the agent (or a running job) has touched the remote
    file more recently than the local one, --update makes rsync silently
    skip the transfer instead of overwriting it, which is the opposite of
    what an explicit push/pull call means. Content-based staleness is still
    covered by --checksum (kept via the checksum=True default) and by the
    sha256 verification below; only the mtime-based skip is dropped.
    """
    from remotemanager.transport.rsync import rsync
    from remotemanager.transport.scp import scp as Scp
    c = get_frontend(facility)
    try:
        return rsync(url=c, flags="avh")
    except RuntimeError:
        return Scp(url=c)


def _sha256_local(path: Path) -> str:
    """SHA-256 of a local file, streamed in 1 MB chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(facility: "Facility | str", remote_path: str, local_dest: Path) -> dict:
    """Pull remote_path from `facility` to local_dest via rsync or scp;
    return transfer metadata."""
    local_dest = Path(local_dest)
    local_dest.parent.mkdir(parents=True, exist_ok=True)

    remote_sha = run_command(facility, f"sha256sum {quote_path(remote_path)}").split()[0]

    remote_name = Path(remote_path).name
    transport = _make_transport(facility)
    transport.queue_for_pull(
        files=remote_name,
        remote=str(Path(remote_path).parent),
        local=str(local_dest.parent),
    )
    with contextlib.redirect_stdout(sys.stderr):
        transport.transfer()

    landed = local_dest.parent / remote_name
    if landed != local_dest:
        landed.rename(local_dest)

    local_sha = _sha256_local(local_dest)
    if remote_sha != local_sha:
        raise RuntimeError(
            f"Download of {remote_path} landed at {local_dest} but content "
            f"doesn't match (remote sha256 {remote_sha}, local sha256 "
            f"{local_sha}). The remote file may have changed between the "
            "checksum and the transfer."
        )
    return {
        "local_path": str(local_dest),
        "bytes": local_dest.stat().st_size,
        "sha256": local_sha,
        "verified": True,
        "transport": type(transport).__name__,
    }


def upload_file(facility: "Facility | str", local_path: Path, remote_path: str) -> dict:
    """Push local_path to remote_path on `facility` via rsync or scp; return
    transfer metadata."""
    local_path = Path(local_path)
    if not local_path.exists():
        raise FileNotFoundError(str(local_path))

    local_sha = _sha256_local(local_path)
    remote_path = norm_path(remote_path)

    run_command(facility, f"mkdir -p {quote_path(str(Path(remote_path).parent))}")

    transport = _make_transport(facility)
    transport.queue_for_push(
        files=local_path.name,
        local=str(local_path.parent),
        remote=str(Path(remote_path).parent),
    )
    with contextlib.redirect_stdout(sys.stderr):
        transport.transfer()

    landed = str(Path(remote_path).parent / local_path.name)
    if landed != remote_path:
        run_command(facility, f"mv {quote_path(landed)} {quote_path(remote_path)}")

    remote_sha = run_command(facility, f"sha256sum {quote_path(remote_path)}").split()[0]
    if remote_sha != local_sha:
        raise RuntimeError(
            f"Upload of {local_path} to {remote_path} completed but content "
            f"doesn't match (local sha256 {local_sha}, remote sha256 "
            f"{remote_sha}). The remote file may have been modified "
            "concurrently, or the transfer was silently skipped."
        )
    return {
        "remote_path": remote_path,
        "bytes": local_path.stat().st_size,
        "sha256": local_sha,
        "verified": True,
        "transport": type(transport).__name__,
    }
