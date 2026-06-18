"""Remote-execution layer: all cluster interaction funnels through here.

Built on remotemanager's Computer.cmd (a direct SSH exec, ~0.6s per call).
Three conventions are enforced in one place:

- Commands run under a login shell (Slurm on HBW2 resolves its configuration
  through the login environment; a bare non-login shell cannot find it).
- The working directory is the user's home, so relative paths behave the way
  users expect.
- Commands and file contents travel base64-encoded, so arbitrary quoting
  survives the SSH layer intact.
- Non-zero exit codes raise RuntimeError so FastMCP surfaces a clean tool
  error; callers never need to parse error text from the return value.
"""
import base64
import contextlib
import shlex
import sys
from functools import lru_cache


def norm_path(path: str) -> str:
    """Strip a leading ~ so remote paths resolve under the home directory.

    run_command sets CWD to $HOME, so relative paths already resolve there.
    shlex.quote wraps in single quotes which suppresses tilde expansion, so
    ~/foo must become foo before quoting; bare ~ becomes '.'.
    """
    if path == "~":
        return "."
    if path.startswith("~/"):
        return path[2:]
    return path


def quote_path(path: str) -> str:
    """shlex.quote a remote path after normalizing a leading ~."""
    return shlex.quote(norm_path(path))

from remotemanager import Computer

from hokusai_mcp import config

# Cap what a single call can pour into the MCP context.
OUTPUT_LIMIT_BYTES = 200_000


@lru_cache(maxsize=1)
def get_frontend() -> Computer:
    """The (cached) Computer targeting the HBW2 front-end (login) node."""
    return Computer(
        template="#!/bin/bash -l",
        host=config.ssh_host(),
        submitter="bash",
        python="python3",
    )


def run_command(cmd: str) -> str:
    """Run a shell command on the login node; return stdout.

    Raises RuntimeError on non-zero exit so callers receive a clean MCP tool
    error rather than having to parse error text from the output.
    Output beyond OUTPUT_LIMIT_BYTES is truncated with a marker.
    """
    payload = 'cd "$HOME" && ' + cmd
    encoded = base64.b64encode(payload.encode()).decode()
    # remotemanager may print progress to stdout, which would corrupt the
    # MCP stdio transport — divert anything it emits.
    with contextlib.redirect_stdout(sys.stderr):
        try:
            result = get_frontend().cmd(
                f"echo {encoded} | base64 -d | bash -l", raise_errors=False,
            )
        except Exception as exc:
            if not config.CONFIG_PATH.exists():
                raise RuntimeError(
                    "Plugin not configured — run the 'hokusai-configuring' skill to "
                    f"create {config.CONFIG_PATH}."
                ) from exc
            raise
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        if not config.CONFIG_PATH.exists():
            raise RuntimeError(
                "Plugin not configured — run the 'hokusai-configuring' skill to "
                f"create {config.CONFIG_PATH}."
                + (f" SSH error: {detail}" if detail else "")
            )
        raise RuntimeError(detail or f"command exited with code {result.returncode}")
    output = result.stdout or ""
    if len(output) > OUTPUT_LIMIT_BYTES:
        output = (output[:OUTPUT_LIMIT_BYTES]
                  + f"\n[output truncated at {OUTPUT_LIMIT_BYTES} bytes]")
    return output


def write_remote_file(path: str, content: str | bytes) -> str:
    """Write a file on the cluster, creating parent directories.

    Relative paths resolve against the home directory. Returns the absolute
    path of the written file; raises on failure.
    """
    path = norm_path(path)
    raw = content if isinstance(content, bytes) else content.encode()
    encoded = base64.b64encode(raw).decode()
    quoted = shlex.quote(path)
    output = run_command(
        f'mkdir -p "$(dirname {quoted})" && '
        f"echo {encoded} | base64 -d > {quoted} && realpath {quoted}"
    )
    abs_path = output.strip().splitlines()[-1] if output.strip() else ""
    if not abs_path.startswith("/"):
        raise RuntimeError(f"Failed to write {path}: {output}")
    return abs_path
