"""Health checks for the R-CCS Cloud plugin.

    python -m cloud_mcp.doctor

Thin wrapper over `hpc_agent_core.doctor`: it checks the config file, SSH
access to the login node, Slurm availability, the bundled guide, the docs
index, and the embedding endpoint. Importing config first registers the
machine's settings via configure().
"""
import sys

from hpc_agent_core.doctor import main as _core_main
from cloud_mcp import config  # noqa: F401 -- registers settings via configure()


def main() -> int:
    return _core_main(scheduler_probe="sinfo --version", scheduler_name="slurm")


if __name__ == "__main__":
    sys.exit(main())
