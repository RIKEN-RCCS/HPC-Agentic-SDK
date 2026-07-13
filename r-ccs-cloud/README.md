# RCCS-CloudAgent

Claude Code and Codex plugin for the RIKEN **R-CCS Cloud** — submit and monitor
Slurm jobs, manage files on the cluster, and search a built-in documentation
guide, all from the agent.

The R-CCS Cloud is a heterogeneous research testbed: ~20 Slurm partitions
spanning CPU-only (A64FX, EPYC, Xeon), NVIDIA GPU, AMD GPU, and Intel GPU
hardware. Partition selection determines everything — the hardware family, the
required modules, and the GPU flags.

This plugin is a thin machine-specific skin over
[hpc-agent-core](https://github.com/william-dawson/hpc-agent-core): the shared
SSH middleware, PSI/J-style job models, Slurm backend, docs-search pipeline, and
health checks live in that package, and this repo supplies only the R-CCS
Cloud's facts, wiring, skills, and packaging.

## Configure

Settings live in `~/.hpc-agent/rccs_cloud.json` (the common directory shared by
every hpc-agent-core plugin):

```json
{
  "ssh": {"host": "rccs-cloud"}
}
```

`ssh.host` is a `~/.ssh/config` alias or `user@hostname` (key-based auth
required), or `"localhost"` if the agent is running directly on an R-CCS
Cloud front-end node (no SSH needed at all). `RCCS_CLOUD_HOST` overrides the
file. A legacy `~/.rccs-cloud/config.json` is still read if it's the only
config present.

For documentation search, add your API key for the shared RIKEN embedding
service:

```json
{
  "ssh": {"host": "rccs-cloud"},
  "embedding": {"api_key": "..."}
}
```

`RCCS_CLOUD_EMBED_API_KEY` (or the shared `RCCS_EMBED_API_KEY`) sets the key.
With it, docs search uses semantic (vector) matching; without it — or off the
RIKEN network — it falls back to BM25 keyword search over the same content.

The `rccs-cloud-configuring` skill walks through this interactively.

## Install

### Prerequisite: uv

The plugin starts its MCP servers with `uv tool run` from this repository's
`main` branch, so [`uv`](https://docs.astral.sh/uv/) must be installed and on
your `PATH` before Claude Code or Codex starts the plugin:

```bash
brew install uv        # or: curl -LsSf https://astral.sh/uv/install.sh | sh
```

Restart Claude Code or Codex after installing uv so the plugin process inherits
the updated `PATH`.

### Claude Code

```
/plugin marketplace add william-dawson/RCCS-CloudAgent
/plugin install rccs-cloud@rccs-cloud-marketplace
/reload-plugins
```

### Codex

```
codex plugin marketplace add william-dawson/RCCS-CloudAgent
```

Then open `/plugins`, install `rccs-cloud`, start a new thread, and run
`/rccs-cloud-demo` to verify the connection end-to-end.

### Manual (any MCP-compatible client)

Both options below only register the MCP servers — copy `plugins/rccs-cloud/skills/`
into wherever your client loads skills from too (this varies by client).

#### Option A — Using Hatch!

[Hatch!](https://github.com/CrackingShells/Hatch) registers MCP servers on any
supported host from a single command. Install it once, then configure both
servers — replace `<host>` with your target platform (`claude-code`, `codex`,
`cursor`, `vscode`, `claude-desktop`, `kiro`, `gemini`, `lmstudio`, or any other
[supported host](https://github.com/CrackingShells/Hatch#supported-mcp-hosts)):

```bash
pip install hatch-xclam

hatch mcp configure rccs-cloud-hpc --host <host> \
  --command uv \
  --args "tool run --quiet --from git+https://github.com/william-dawson/RCCS-CloudAgent.git@main#subdirectory=server rccs-cloud-hpc-mcp"

hatch mcp configure rccs-cloud-docs --host <host> \
  --command uv \
  --args "tool run --quiet --from git+https://github.com/william-dawson/RCCS-CloudAgent.git@main#subdirectory=server rccs-cloud-docs-mcp"
```

To replicate the same configuration to additional hosts:

```bash
hatch mcp sync --from-host <host> --to-host cursor,vscode
```

#### Option B — Edit `.mcp.json` directly

Create or edit `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "rccs-cloud-hpc": {
      "command": "uv",
      "args": ["tool", "run", "--quiet", "--from", "git+https://github.com/william-dawson/RCCS-CloudAgent.git@main#subdirectory=server", "rccs-cloud-hpc-mcp"],
      "env": {}
    },
    "rccs-cloud-docs": {
      "command": "uv",
      "args": ["tool", "run", "--quiet", "--from", "git+https://github.com/william-dawson/RCCS-CloudAgent.git@main#subdirectory=server", "rccs-cloud-docs-mcp"],
      "env": {}
    }
  }
}
```

## Verify

```bash
uv tool run --quiet --from git+https://github.com/william-dawson/RCCS-CloudAgent.git@main#subdirectory=server rccs-cloud-doctor
```

The doctor checks the config file, SSH access, Slurm, the bundled guide, the
docs index, and the embedding endpoint.

## Development

```bash
cd server
uv run python -m cloud_mcp.doctor        # config, SSH, Slurm, guide, index, embedding
uv run python tests/smoke.py             # live read-only test over MCP stdio
uv run python tests/smoke.py --job       # + submits a real tiny CPU job
uv run python -m cloud_mcp.ingest        # rebuild the docs index after editing the guide
```

See [AGENTS.md](AGENTS.md) for the design rules, cluster facts, and repo map,
and [hpc-agent-core's `PORTING.md`](https://github.com/william-dawson/hpc-agent-core/blob/main/PORTING.md)
for the general porting process this repo follows.
