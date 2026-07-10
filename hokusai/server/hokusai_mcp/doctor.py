"""Health checks for the HOKUSAI plugin — a thin wrapper over
hpc_agent_core.doctor. Checks config, SSH + Slurm, the bundled guide, the
docs index, and the embedding endpoint.

    python -m hokusai_mcp.doctor
"""
import sys

from hokusai_mcp import config  # noqa: F401 -- registers settings via configure().
from hpc_agent_core.doctor import main as _core_main


def main() -> int:
    # HBW2 is Slurm; `sinfo --version` prints "slurm <version>".
    return _core_main(scheduler_probe="sinfo --version", scheduler_name="slurm")


if __name__ == "__main__":
    sys.exit(main())
