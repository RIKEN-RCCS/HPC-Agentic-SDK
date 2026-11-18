"""Entry point for the unified health check: `hpc-doctor [facility]`.

Registers every facility (via importing hpc_mcp), then runs
hpc_agent_core.doctor.main() — every registered facility by default, or
just one if a slug is given on the command line.
"""
import sys

import hpc_mcp  # noqa: F401 -- import for its side effect: registers every facility
from hpc_agent_core.doctor import main as _main


def main() -> int:
    facility = sys.argv[1] if len(sys.argv) > 1 else None
    return _main(facility)


if __name__ == "__main__":
    sys.exit(main())
