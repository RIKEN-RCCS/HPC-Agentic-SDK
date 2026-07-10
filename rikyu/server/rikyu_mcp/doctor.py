"""RIKYU health checks — thin wrapper over hpc_agent_core.doctor.

    python -m rikyu_mcp.doctor
"""
import sys

from hpc_agent_core.doctor import main as _core_main
from rikyu_mcp import config  # noqa: F401 -- registers via configure()


def main() -> int:
    return _core_main(scheduler_probe="sinfo --version", scheduler_name="slurm")


if __name__ == "__main__":
    sys.exit(main())
