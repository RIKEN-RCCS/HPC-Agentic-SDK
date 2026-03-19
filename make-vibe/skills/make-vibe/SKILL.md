# make-vibe Skills Guide

The user wants you to use make-vibe to manage compilation and performance testing
of this code on a remote HPC system (or locally). make-vibe exposes Makefile
targets as MCP tools that you call instead of running `make` directly. Each
tool call syncs the code to the remote machine, executes the target, and returns
the output.

## How It Works

make-vibe reads two config files from the project directory and a Makefile:

- `config.json` — connection settings (host, submitter, remote directory)
- `config.sh` — job script template with tunable parameters
- `Makefile` — targets annotated with `# @env:` become MCP tools

Each Makefile target becomes a tool named `make_<target>` (e.g. `make_build`,
`make_run`). The parameters available on each tool come from two sources:

1. **Template parameters** — placeholders in `config.sh` like `#MPI:default=1#`.
   These become integer parameters (e.g. `mpi=4`).
2. **Environment parameters** — `# @env: VAR - description` comments above a
   Makefile target. These become string parameters (e.g. `cflags="-O3"`).

## The Config Files

### `config.json`

```json
{
  "template_file": "config.sh",
  "host": "login.mycluster.example.com",
  "ssh_insert": "",
  "submitter": "sbatch",
  "remote_dir": "mcp_remote",
  "project_dir": "."
}
```

`submitter` controls execution mode:
- `"bash"` — run locally on this machine
- `"sbatch"` — submit a new SLURM job per tool call (batch mode)

### `config.sh`

A job script template. Parameters the agent can control are written as
`#PARAM:default=N#`. Document them with `# RM > PARAM: description` so they
appear in tool descriptions.

```bash
#!/bin/bash
#SBATCH --partition=compute
# RM > NODES: Number of nodes to request (max 16)
#SBATCH --nodes=#NODES:default=1#
# RM > MPI: Number of MPI ranks per node
#SBATCH --ntasks-per-node=#MPI:default=48#
#SBATCH -t 1:00:00

module load mpi
export MPIRUN="mpirun"
```

### Makefile annotations

```makefile
# @env: CFLAGS - Compiler optimization flags
build:
    $(CC) $(CFLAGS) -o app app.c

# @env: N - Problem size
run:
    ./app
```

## Your Workflow

1. Call `make_build` (with any relevant `cflags` or other env params) to
   compile the code after making changes.
2. Call `make_run` (with template params like `mpi`, `nodes` and env params
   like `n`) to execute and get performance output.
3. Read the returned stdout/stderr to assess results, then iterate.

Never run `make` commands directly — always go through the MCP tools.
