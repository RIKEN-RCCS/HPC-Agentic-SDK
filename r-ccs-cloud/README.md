# RCCS-CloudAgent

Claude Code and Codex plugin for the RIKEN **R-CCS Cloud** — submit and monitor Slurm jobs, manage files on the cluster, and search the built-in documentation, all from the agent.

R-CCS Cloud is a heterogeneous research testbed: ~20 Slurm partitions spanning CPU-only (A64FX, EPYC, Xeon), NVIDIA GPU, AMD GPU, and Intel GPU hardware. Partition selection determines everything — the hardware family, the required modules, and the job flags.

## Install

### Prerequisite: uv

The plugin starts its MCP servers with `uv tool run` from this repository's
`main` branch, so `uv` must be installed and available on your PATH before
Claude Code or Codex starts the plugin.

Common install options:

```bash
brew install uv
```

or:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

After installing uv, restart Claude Code or Codex so the plugin process inherits
the updated PATH.

### Claude Code

Install in Claude Code:

```
/plugin marketplace add william-dawson/RCCS-CloudAgent
/plugin install rccs-cloud@rccs-cloud-marketplace
/reload-plugins
```

### Codex

Install in Codex:

```
codex plugin marketplace add william-dawson/RCCS-CloudAgent
```

Then open `/plugins`, install `rccs-cloud`, start a new thread, and run
`/rccs-cloud-demo` to verify the connection end-to-end.

## Configuration

Settings live in `~/.rccs-cloud/config.json`:

```json
{
  "ssh": {"host": "rccs-cloud"}
}
```

`ssh.host` is a `~/.ssh/config` alias or `user@hostname` (key-based auth required). The env var `RCCS_CLOUD_HOST` overrides the file.

For documentation search, add your API key for the shared RIKEN embedding service:

```json
{
  "ssh": {"host": "rccs-cloud"},
  "embedding": {"api_key": "..."}
}
```

The env var `RCCS_EMBED_API_KEY` sets the key. With it, docs search uses semantic (vector) matching; without it — or off the RIKEN network — it falls back to BM25 keyword search over the same content.
