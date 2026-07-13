# HOKUSAI BigWaterfall2 (HBW2) Agent

A Claude Code / Codex plugin for **HOKUSAI BigWaterfall2 (HBW2)**, the RIKEN
R-CCS CPU-first Slurm cluster (312-node MPC, 2-node large-memory LMC, and a
small 4-node H100 GPU server). It lets an agent submit and monitor Slurm
jobs, manage files, and search HBW2's documentation, over SSH.

Built as a thin machine-specific "skin" on top of
[`hpc-agent-core`](https://pypi.org/project/hpc-agent-core/) — see
[hpc-agent-core's `PORTING.md`](https://github.com/william-dawson/hpc-agent-core/blob/main/PORTING.md)
for the general porting guide this repo follows, and
[`AGENTS.md`](AGENTS.md) for the design rules and cluster facts an agent
working on this repo should know.

## Configure

Settings live in `~/.hpc-agent/hokusai.json` (the common directory shared by
every hpc-agent-core plugin):

```json
{
  "ssh": { "host": "hokusai" },
  "defaults": { "account": "RB99999" }
}
```

- `ssh.host` — an alias in `~/.ssh/config` or `user@hokusai.riken.jp`
  (register your SSH key via the portal `https://hokusai.riken.jp/hbw2/`
  first; auth is key-only), or `"localhost"` if the agent runs directly on
  an HBW2 front-end node (no SSH needed at all). `HOKUSAI_HOST` overrides
  the file.
- `defaults.account` — the project charged when a job names none;
  **mandatory** on HBW2 (`RB…` RIKEN or `HP…` HPCI). `HOKUSAI_ACCOUNT`
  overrides the file.
- A legacy `~/.hokusai/config.json` is still read if it's the only config
  present.

For documentation search, add your API key for the shared RIKEN embedding
service:

```json
{
  "ssh": { "host": "hokusai" },
  "defaults": { "account": "RB99999" },
  "embedding": { "api_key": "..." }
}
```

`HOKUSAI_EMBED_API_KEY` (or the shared `RCCS_EMBED_API_KEY`) sets the key.
With it, docs search uses semantic (vector) matching; without it — or off
the RIKEN network — it falls back to BM25 keyword search over the same
content. The `hokusai-configuring` skill walks through this interactively.

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
/plugin marketplace add RIKEN-RCCS/Hokusai-Agent
/plugin install hokusai@hokusai-marketplace
/reload-plugins
```

### Codex

```
codex plugin marketplace add RIKEN-RCCS/Hokusai-Agent
```

Then open `/plugins`, install `hokusai`, start a new thread, and run
`/hokusai-demo` to verify the connection end-to-end.

### Manual (any MCP-compatible client)

Both options below only register the MCP servers — copy `plugins/hokusai/skills/`
into wherever your client loads skills from too (this varies by client).

#### Option A — Using Hatch!

[Hatch!](https://github.com/CrackingShells/Hatch) registers MCP servers on any
supported host from a single command. Install it once, then configure both
servers — replace `<host>` with your target platform (`claude-code`, `codex`,
`cursor`, `vscode`, `claude-desktop`, `kiro`, `gemini`, `lmstudio`, or any other
[supported host](https://github.com/CrackingShells/Hatch#supported-mcp-hosts)):

```bash
pip install hatch-xclam

hatch mcp configure hokusai-hpc --host <host> \
  --command uv \
  --args "tool run --quiet --from git+https://github.com/RIKEN-RCCS/Hokusai-Agent.git@main#subdirectory=server hokusai-hpc-mcp"

hatch mcp configure hokusai-docs --host <host> \
  --command uv \
  --args "tool run --quiet --from git+https://github.com/RIKEN-RCCS/Hokusai-Agent.git@main#subdirectory=server hokusai-docs-mcp"
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
    "hokusai-hpc": {
      "command": "uv",
      "args": ["tool", "run", "--quiet", "--from", "git+https://github.com/RIKEN-RCCS/Hokusai-Agent.git@main#subdirectory=server", "hokusai-hpc-mcp"],
      "env": {}
    },
    "hokusai-docs": {
      "command": "uv",
      "args": ["tool", "run", "--quiet", "--from", "git+https://github.com/RIKEN-RCCS/Hokusai-Agent.git@main#subdirectory=server", "hokusai-docs-mcp"],
      "env": {}
    }
  }
}
```

## Verify

```bash
uv tool run --quiet --from git+https://github.com/RIKEN-RCCS/Hokusai-Agent.git@main#subdirectory=server hokusai-doctor
```

All lines should read `✓` except possibly embedding (falls back to keyword
search outside RIKEN's network — not blocking).

## Development

```
cd server
uv run python -m hokusai_mcp.doctor        # health check
uv run python tests/smoke.py               # read-only MCP stdio test
uv run python tests/smoke.py --job         # + submits a real tiny job
```

Rebuilding the docs index after editing `hokusai_guide.md`:

```
cd server
uv run python -m hokusai_mcp.ingest
```

Commit the resulting `hokusai_mcp/data/docs_index/` (chunks.json, and
embeddings.npy if an embedding API key was configured at ingest time).
