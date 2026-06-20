# Agentic SDK for High Performance Computing

A market place of claude code skills and MCP servers useful for HPC development
using agentic tools.

## Install

In Claude Code:

```
/plugin marketplace add RIKEN-RCCS/HPC-Agentic-SDK
/plugin install RAPTOR 
```

This installs all plugins needed for HPC code tuning workflows.

### Codex

Codex can install plugins from this repository through the plugin marketplace:

```bash
codex plugin marketplace add RIKEN-RCCS/HPC-Agentic-SDK
```

Then open `/plugins` in Codex and install the plugins you need.

## Plugins

### Optimization tools

| Plugin | Description |
|--------|-------------|
| [RAPTOR](./raptor/) | Profile and alter floating-point precision in C, C++, and Fortran using RAPTOR |
| [Tadashi](./tadashi/) | Check whether loop transformations are mathematically safe using polyhedral analysis |
| [make-vibe](./make-vibe/) | Expose Makefile targets as MCP tools for building and running code on local or remote HPC systems |
| [OpenACC](./openacc/) | Automatically insert OpenACC directives into Fortran code using a verified template library for reliable GPU parallelization |

### RIKEN R-CCS facility agents

Full cluster agents for job submission, monitoring, and filesystem operations via the [IRI Facility API](https://api.alcf.anl.gov/). Install one if you work on the corresponding machine.

| Plugin | Machine | Description |
|--------|---------|-------------|
| [hokusai](./hokusai/) | HOKUSAI BigWaterfall2 (HBW2, x86_64) | Submit and monitor Slurm jobs, manage files, search the HBW2 User's Guide |
| [rikyu](./rikyu/) | AI4S (NVIDIA GB200, aarch64) | Submit and monitor Slurm jobs, manage files, search the AI4S documentation |
| [rccs-cloud](./r-ccs-cloud/) | R-CCS Cloud (~20 partitions: A64FX, x86_64, NVIDIA/AMD/Intel GPUs) | Submit and monitor Slurm jobs, manage files, search the built-in documentation |

```
/plugin install hokusai
/plugin install rikyu
/plugin install rccs-cloud
```

## Overnight agent

[claude_fairy](https://pypi.org/project/claude-fairy/) runs Claude Code headlessly on a schedule — waking at 1am, working through your `PLAN.md`, and writing a report by morning. The plugins above are its toolbox for HPC work.

```bash
# Install the plugins first
/plugin marketplace add RIKEN-RCCS/HPC-Agentic-SDK
/plugin install make-vibe
/plugin install rccs-cloud

# Then initialize and start the fairy in your project
uvx --from claude-fairy cfairy init
uvx --from claude-fairy cfairy daemon
```

Edit `PLAN.md` with your tasks. The fairy will use the installed plugins each night to build, run, and optimize on the cluster.
