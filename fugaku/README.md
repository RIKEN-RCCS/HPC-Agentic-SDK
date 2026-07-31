# Fugaku Agent

Fugaku Agent is a Claude Code / Codex plugin for the RIKEN Fugaku
supercomputer (A64FX, CPU-only, Tofu interconnect). It submits and monitors
PJM (`pjsub`/`pjstat`/`pjdel`) jobs, manages files on the cluster, and
searches a bundled Fugaku guide. It is a thin machine-specific skin over
[hpc-agent-core](https://pypi.org/project/hpc-agent-core/) — see
[hpc-agent-core's `PORTING.md`](https://github.com/william-dawson/hpc-agent-core/blob/main/PORTING.md)
for the general porting guide this repo follows, and
[`AGENTS.md`](AGENTS.md) for the design rules and cluster facts an agent
working on this repo should know.

> **Relationship to [RIKEN-RCCS/fugaku-mcp](https://github.com/RIKEN-RCCS/fugaku-mcp):**
> that project is the official Fugaku MCP server, built and maintained by
> the Fugaku operations team. This repository is an independent,
> **unofficial** community port built on the shared `hpc-agent-core`
> framework — not a competing or replacement effort. Prefer
> `RIKEN-RCCS/fugaku-mcp` where it covers what you need; reach for this repo
> when you specifically want its more experimental feature set or its
> Claude Code / Codex plugin (skills + marketplace) packaging.

## Configure

Settings live in `~/.hpc-agent/fugaku.json` (the common directory shared by
every hpc-agent-core plugin):

```json
{
  "ssh": {"host": "fugaku"},
  "defaults": {"group": "ra000009", "gfscache_volume": "/vol0004"}
}
```

- `ssh.host` is a `~/.ssh/config` alias or `user@login.fugaku.r-ccs.riken.jp`
  (public-key auth only — register your key via the Fugaku website User
  Portal first), or `"localhost"` if the agent runs directly on a Fugaku
  login node (no SSH needed at all). `FUGAKU_HOST` overrides it.
- `defaults.group` is the project group charged when a job doesn't set
  `attributes.account` explicitly — PJM's mandatory `-g <groupname>`. The
  shared `fugaku` group every account belongs to cannot submit jobs; find
  your real groups with `id`. `FUGAKU_GROUP` overrides it.
- `defaults.gfscache_volume` is the second-layer storage volume (e.g.
  `/vol0004`) declared via `#PJM -x PJM_LLIO_GFSCACHE=`, needed whenever a
  job's work lives outside `$HOME`. `FUGAKU_GFSCACHE` overrides it.
- The `fugaku-configuring` skill walks through this interactively.

Docs search uses the shared RIKEN R-CCS embedding endpoint when reachable,
falling back to BM25 keyword search otherwise.

## Install

### Prerequisite: uv

The plugin starts its MCP servers with `uv tool run` from this repository's
`main` branch, so [`uv`](https://docs.astral.sh/uv/) must be installed and
on your `PATH` before Claude Code or Codex starts the plugin:

```bash
brew install uv        # or: curl -LsSf https://astral.sh/uv/install.sh | sh
```

Restart Claude Code or Codex after installing uv so the plugin process
inherits the updated `PATH`.

### Claude Code

```
/plugin marketplace add RIKEN-RCCS/Fugaku-Agent
/plugin install fugaku@fugaku-marketplace
/reload-plugins
```

### Codex

```
codex plugin marketplace add RIKEN-RCCS/Fugaku-Agent
```

Then open `/plugins`, install `fugaku`, start a new thread, and run
`/fugaku-demo` to verify the connection end-to-end.

### Manual (any MCP-compatible client)

Both options below only register the MCP servers — copy
`plugins/fugaku/skills/` into wherever your client loads skills from too
(this varies by client, so don't go into depth here).

#### Option A — Using Hatch!

[Hatch!](https://github.com/CrackingShells/Hatch) registers MCP servers on
any supported host from a single command. Install it once, then configure
both servers — replace `<host>` with your target platform
(`claude-code`, `codex`, `cursor`, `vscode`, `claude-desktop`, `kiro`,
`gemini`, `lmstudio`, or any other
[supported host](https://github.com/CrackingShells/Hatch#supported-mcp-hosts)):

```bash
pip install hatch-xclam

hatch mcp configure fugaku-hpc --host <host> \
  --command uv \
  --args "tool run --quiet --from git+https://github.com/RIKEN-RCCS/Fugaku-Agent.git@main#subdirectory=server fugaku-hpc-mcp"

hatch mcp configure fugaku-docs --host <host> \
  --command uv \
  --args "tool run --quiet --from git+https://github.com/RIKEN-RCCS/Fugaku-Agent.git@main#subdirectory=server fugaku-docs-mcp"
```

To replicate the same configuration to additional hosts:

```bash
hatch mcp sync --from-host <host> --to-host cursor,vscode
```

#### Option B — Edit `.mcp.json` directly

```json
{
  "mcpServers": {
    "fugaku-hpc": {
      "command": "uv",
      "args": ["tool", "run", "--quiet", "--from", "git+https://github.com/RIKEN-RCCS/Fugaku-Agent.git@main#subdirectory=server", "fugaku-hpc-mcp"],
      "env": {}
    },
    "fugaku-docs": {
      "command": "uv",
      "args": ["tool", "run", "--quiet", "--from", "git+https://github.com/RIKEN-RCCS/Fugaku-Agent.git@main#subdirectory=server", "fugaku-docs-mcp"],
      "env": {}
    }
  }
}
```

## Verify

```bash
uv tool run --quiet --from git+https://github.com/RIKEN-RCCS/Fugaku-Agent.git@main#subdirectory=server fugaku-doctor
```

All lines should read `✓` except possibly embedding, which falls back to
keyword search off the RIKEN network — not blocking.

## Development

```bash
cd server
uv run python -m fugaku_mcp.doctor
uv run python tests/smoke.py
uv run python tests/smoke.py --job
```

`tests/smoke.py --job` submits a real job on the `small` resource group and
consumes allocation time. Rebuild the docs index after editing the guide:

```bash
uv run python -m hpc_agent_core.rag.ingest
```

## License

AGPL-3.0-or-later — see [LICENSE](LICENSE).
