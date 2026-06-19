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

You can also install individual skills from this repository directly into Codex
when you only need a skill and not the full plugin wrapper or MCP server.

For a project-local install:

```bash
mkdir -p .codex/skills
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo RIKEN-RCCS/HPC-Agentic-SDK \
  --path openacc/skills/openacc \
  --dest "$PWD/.codex/skills"
CODEX_HOME="$PWD/.codex" codex
```

Replace `openacc/skills/openacc` with the skill path you want from this repository.
You can pass multiple `--path` values to install several skills at once.

For a global install, omit `--dest` and start Codex normally.

## Plugins

### Optimization tools

| Plugin | Description |
|--------|-------------|
| [RAPTOR](./raptor/) | Profile and alter floating-point precision in C, C++, and Fortran using RAPTOR |
| [Tadashi](./tadashi/) | Check whether loop transformations are mathematically safe using polyhedral analysis |
| [make-vibe](./make-vibe/) | Expose Makefile targets as MCP tools for building and running code on local or remote HPC systems |
| [r-ccs-cloud](./r-ccs-cloud/) | Reference for R-CCS cloud HPC systems: resources, modules, SLURM scripts, and login details |
| [OpenACC](./openacc/) | Automatically insert OpenACC directives into Fortran code using a verified template library for reliable GPU parallelization |

### RIKEN R-CCS facility agents

Full cluster agents for job submission, monitoring, and filesystem operations via the [IRI Facility API](https://api.alcf.anl.gov/). Install one if you work on the corresponding machine.

| Plugin | Machine | Description |
|--------|---------|-------------|
| [Hokusai Agent](https://github.com/RIKEN-RCCS/Hokusai-Agent) | HOKUSAI BigWaterfall2 (HBW2, x86_64) | Submit and monitor Slurm jobs, manage files, search the HBW2 User's Guide |
| [Rikyu Agent](https://github.com/RIKEN-RCCS/Rikyu-Agent) | AI4S (NVIDIA GB200, aarch64) | Submit and monitor Slurm jobs, manage files, search the AI4S documentation |

```
/plugin install hokusai
/plugin install rikyu
```

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
