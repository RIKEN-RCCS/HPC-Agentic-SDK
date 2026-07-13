# RIKYU Agent

A Claude Code / Codex plugin for the [Supercomputer RIKYU](https://docs.r-ccs.riken.jp/rikyu/en/),
a RIKEN Center for Computational Science (R-CCS) system built for
AI-accelerated scientific discovery — 400 nodes of NVIDIA GB200 NVL4
(1,600 B200 GPUs total). It lets an agent submit and monitor Slurm jobs,
manage files, and search RIKYU's documentation, over SSH.

Built as a thin machine-specific "skin" on top of
[`hpc-agent-core`](https://pypi.org/project/hpc-agent-core/) — see
[hpc-agent-core's `PORTING.md`](https://github.com/william-dawson/hpc-agent-core/blob/main/PORTING.md)
for the general porting guide this repo follows, and
[`AGENTS.md`](AGENTS.md) for the design rules and cluster facts an agent
working on this repo should know.

## Configure

Settings live in `~/.hpc-agent/rikyu.json` (the common directory shared by
every hpc-agent-core plugin):

```json
{
  "ssh": {"host": "rikyu"}
}
```

- `ssh.host` is a `~/.ssh/config` alias or `user@login.rikyu.r-ccs.riken.jp`
  (key-based auth required — register your key via Open OnDemand's "SSH
  Public Key" app first), or `"localhost"` if the agent is running directly
  on a Rikyu front-end node (no SSH needed at all). `RIKYU_HOST` overrides
  the file.
- A legacy `~/.rikyu/config.json` is still read if it's the only config
  present.

For documentation search, add your API key for the shared RIKEN embedding
service:

```json
{
  "ssh": {"host": "rikyu"},
  "embedding": {"api_key": "..."}
}
```

`RIKYU_EMBED_API_KEY` (or the shared `RCCS_EMBED_API_KEY`) sets the key.
With it, docs search uses semantic (vector) matching; without it — or off
the RIKEN network — it falls back to BM25 keyword search over the same
content. The `rikyu-configuring` skill walks through this interactively.

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
/plugin marketplace add RIKEN-RCCS/Rikyu-Agent
/plugin install rikyu@rikyu-marketplace
/reload-plugins
```

### Codex

```
codex plugin marketplace add RIKEN-RCCS/Rikyu-Agent
```

Then open `/plugins`, install `rikyu`, start a new thread, and run
`/rikyu-demo` to verify the connection end-to-end.

### Manual (any MCP-compatible client)

Both options below only register the MCP servers — copy `plugins/rikyu/skills/`
into wherever your client loads skills from too (this varies by client).

#### Option A — Using Hatch!

[Hatch!](https://github.com/CrackingShells/Hatch) registers MCP servers on any
supported host from a single command. Install it once, then configure both
servers — replace `<host>` with your target platform (`claude-code`, `codex`,
`cursor`, `vscode`, `claude-desktop`, `kiro`, `gemini`, `lmstudio`, or any other
[supported host](https://github.com/CrackingShells/Hatch#supported-mcp-hosts)):

```bash
pip install hatch-xclam

hatch mcp configure rikyu-hpc --host <host> \
  --command uv \
  --args "tool run --quiet --from git+https://github.com/RIKEN-RCCS/Rikyu-Agent.git@main#subdirectory=server rikyu-hpc-mcp"

hatch mcp configure rikyu-docs --host <host> \
  --command uv \
  --args "tool run --quiet --from git+https://github.com/RIKEN-RCCS/Rikyu-Agent.git@main#subdirectory=server rikyu-docs-mcp"
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
    "rikyu-hpc": {
      "command": "uv",
      "args": ["tool", "run", "--quiet", "--from", "git+https://github.com/RIKEN-RCCS/Rikyu-Agent.git@main#subdirectory=server", "rikyu-hpc-mcp"],
      "env": {}
    },
    "rikyu-docs": {
      "command": "uv",
      "args": ["tool", "run", "--quiet", "--from", "git+https://github.com/RIKEN-RCCS/Rikyu-Agent.git@main#subdirectory=server", "rikyu-docs-mcp"],
      "env": {}
    }
  }
}
```

## Verify

```bash
uv tool run --quiet --from git+https://github.com/RIKEN-RCCS/Rikyu-Agent.git@main#subdirectory=server rikyu-doctor
```

All lines should read `✓` except possibly embedding (falls back to keyword
search outside RIKEN's network — not blocking).

## Development

```
cd server
uv run python -m rikyu_mcp.doctor          # health check
uv run python tests/smoke.py               # read-only MCP stdio test
uv run python tests/smoke.py --job         # + submits a real 1-GPU job
```

Rebuilding the docs index after editing `rikyu_guide.md`:

```
cd server
uv run python -m rikyu_mcp.ingest
```

Commit the resulting `rikyu_mcp/data/docs_index/` (chunks.json, and
embeddings.npy if an embedding API key was configured at ingest time).
