# Agentic SDK for High Performance Computing

A market place of claude code skills and MCP servers useful for HPC development
using agentic tools.

## Install

In Claude Code:

```
/plugin marketplace add RIKEN-RCCS/HPC-Agentic-SDK
```

Then install individual skills via the Discover tab or:

```
/plugin install RAPTOR
```

## Skills

| Skill | Description |
|-------|-------------|
| [RAPTOR](./raptor/) | Profile and alter floating-point precision in C, C++, and Fortran using RAPTOR |
| [Tadashi](./tadashi/) | Check whether loop transformations are mathematically safe using polyhedral analysis |
| [make-vibe](./make-vibe/) | Expose Makefile targets as MCP tools for building and running code on local or remote HPC systems |
| [r-ccs-cloud](./r-ccs-cloud/) | Reference for R-CCS cloud HPC systems: resources, modules, SLURM scripts, and login details |
| [OpenACC](./openacc/) | Automatically insert OpenACC directives into Fortran code using a verified template library for reliable GPU parallelization |

## Overnight agent

[claude_fairy](https://pypi.org/project/claude-fairy/) runs Claude Code headlessly on a schedule — waking at 1am, working through your `PLAN.md`, and writing a report by morning. The plugins above are its toolbox for HPC work.

```bash
# Install the plugins first
/plugin marketplace add RIKEN-RCCS/HPC-Agentic-SDK
/plugin install make-vibe
/plugin install r-ccs-cloud

# Then initialize and start the fairy in your project
uvx --from claude-fairy cfairy init
uvx --from claude-fairy cfairy daemon
```

Edit `PLAN.md` with your tasks. The fairy will use the installed plugins each night to build, run, and optimize on the cluster.
