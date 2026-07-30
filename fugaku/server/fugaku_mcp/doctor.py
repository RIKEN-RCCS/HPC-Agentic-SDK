"""Health checks for Fugaku Agent.

    python -m fugaku_mcp.doctor

Defines its own SSH+scheduler check rather than calling
hpc_agent_core.doctor.main() directly: that helper's check_ssh() runs one
scheduler_probe command and expects its output to *start with* the
scheduler's name (e.g. "slurm 24.05.8") — fine for `sinfo --version`, but
none of PJM's commands support --version/-h at all (confirmed live:
`pjsub --version` and `pjsub -h` both fail with "PJM 0001 Unknown option").
Per hpc_agent_core.doctor's own docstring, this is the expected way to
diverge: reuse the independently-callable check_* functions that fit
(config, guide, docs index, embedding), write a local replacement for the
one that doesn't (ssh+scheduler) — same approach Irene's doctor.py took for
Bridge. The PJM-commands-on-PATH loop itself now comes from
hpc_agent_core.doctor.check_commands_on_path(), promoted there after this
and Irene's Bridge check independently reimplemented the same ~15 lines.
"""
import sys

from hpc_agent_core.doctor import (
    OK,
    FAIL,
    check_commands_on_path,
    check_config_file,
    check_docs_guide_bundled,
    check_docs_index,
    check_embedding,
)
from hpc_agent_core.middleware import is_local_host, run_command
from fugaku_mcp import config  # noqa: F401 -- registers via configure()

_PJM_COMMANDS = {"pjsub", "pjstat", "pjdel", "pjalter"}


def check_ssh_and_pjm() -> bool:
    host = config.ssh_host()
    label = f"local ({host})" if is_local_host(host) else f"ssh ({host})"
    try:
        output = run_command("echo fugaku-doctor-ok && hostname")
    except Exception as e:
        print(f"{FAIL} {label}: {e}")
        return False
    if "fugaku-doctor-ok" not in output:
        print(f"{FAIL} {label}: unexpected response: {output[:200]}")
        return False
    print(f"{OK} {label}: connected to {output.strip().splitlines()[-1]}")
    return check_commands_on_path(_PJM_COMMANDS, "PJM commands")


def main() -> int:
    results = [
        check_config_file(),
        check_ssh_and_pjm(),
        check_docs_guide_bundled(),
        check_docs_index(),
        check_embedding(),
    ]
    if all(results):
        print("\nAll checks passed.")
        return 0
    print("\nSome checks FAILED — see above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
