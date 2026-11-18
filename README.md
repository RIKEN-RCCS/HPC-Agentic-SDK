# HPC Agentic SDK

HPC Agentic SDK is a collection of skills and MCP servers for developing, benchmarking, and tuning high-performance computing software with Claude Code, Codex, OpenCode, and Pi. Install the tools you need for your code and the facility plugins for the machines you use.

## Available plugins

### Development and performance

| Plugin | What it does |
| --- | --- |
| [RAPTOR](./raptor/) | Profile and tune floating-point precision in C, C++, and Fortran |
| [Tadashi](./tadashi/) | Check whether loop transformations are mathematically safe using polyhedral analysis |
| [OpenACC](./openacc/) | Add OpenACC directives to Fortran using verified templates |
| [BenchKit](./benchkit/) | Build and run HPC benchmarks with BenchKit |
| [Benchpark](./benchpark/) | Define reproducible HPC benchmarks with Spack and Ramble |
| [Hot Memory](./hot-memory/) | Measure per-kernel working sets, memory traffic, and FLOPs in MPI applications |
| [Nsight Profiling](./nsight-profiling/) | Profile GPU and MPI applications with NVIDIA Nsight Systems and Compute |
| [HeCBench Kernel Matching](./hecbench/) | Find representative HeCBench kernels by computational motif |
| [Bootstrap](./bootstrap/) | Set up a Claude Code project with HPC skills and workflow instructions |

### Facility plugins

Each facility plugin provides skills and MCP tools for submitting and monitoring jobs, managing files, and searching the facility guide.

| Plugin | Facility | Scheduler |
| --- | --- | --- |
| [`fugaku`](./fugaku/) | Fugaku | PJM |
| [`hokusai`](./hokusai/) | HOKUSAI BigWaterfall2 | Slurm |
| [`rccs-cloud`](./r-ccs-cloud/) | R-CCS Cloud | Slurm |
| [`rikyu`](./rikyu/) | RIKYU, the RIKEN AI4S GB200 system | Slurm |

The Fugaku plugin is an unofficial community port. For the MCP server maintained by the Fugaku operations team, see [RIKEN-RCCS/fugaku-mcp](https://github.com/RIKEN-RCCS/fugaku-mcp).

## Install

### Claude Code

Inside Claude Code, add the marketplace and install the plugins you want. For example:

```text
/plugin marketplace add RIKEN-RCCS/HPC-Agentic-SDK
/plugin install RAPTOR
/plugin install rikyu
```

### Codex

Add the marketplace from your terminal:

```sh
codex plugin marketplace add RIKEN-RCCS/HPC-Agentic-SDK
```

Open `/plugins` in Codex and choose the plugins you want.

### OpenCode and Pi

Install the Git package for your client.

**OpenCode 2.3 or newer**

```sh
opencode plugin add 'github:RIKEN-RCCS/HPC-Agentic-SDK#main'
```

**Pi 1.5.2 or newer with built-in MCP enabled**

```sh
pi install git:github.com/RIKEN-RCCS/HPC-Agentic-SDK@main
```

Start a session and run `/hpc-sdk` to see the available plugins. Set your selection by name:

```text
/hpc-sdk set raptor,rikyu
```

Your client saves the selection for later sessions. Run `/hpc-sdk set` with the full list whenever you want to change it, or `/hpc-sdk clear` to unload the SDK plugins.

### Other MCP clients

Open [this repository](https://github.com/RIKEN-RCCS/HPC-Agentic-SDK) in your AI client, or clone it and open the checkout. Then ask your agent:

> Install all the skills and MCP servers from this repository that my client supports.

The agent can use the [marketplace catalog](./.agents/plugins/marketplace.json) to find each plugin, then register its `skills/` directory and any stdio servers in `.mcp.json` using the client’s native configuration. After installation, follow [Configure](#configure) for the HPC systems you use.

## Configure

Facility plugins require [`uv`](https://docs.astral.sh/uv/) and access to the corresponding system. Follow the facility README to configure SSH and any credentials needed for documentation search. Facility settings live under `~/.hpc-agent/`.

Once configured, try a read-only request such as “Show me which queues are available on RIKYU.”

The Tadashi MCP server requires Docker.

## Overnight workflows

[claude_fairy](https://pypi.org/project/claude-fairy/) runs Claude Code on a schedule and works through tasks in `PLAN.md`. Install the SDK plugins your project needs, then initialize the scheduler from your project directory:

```sh
uvx --from claude-fairy cfairy init
uvx --from claude-fairy cfairy daemon
```

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the plugin layout and marketplace registration.
