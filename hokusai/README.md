# HokusaiAgent

Claude Code plugin for the RIKEN **HOKUSAI BigWaterfall2 (HBW2)** supercomputer — submit and monitor Slurm jobs, manage files on the cluster, and search the official documentation, all from the agent.

HBW2 is a CPU-first system: the 312-node Massively Parallel Computer (MPC) and the large-memory server (LMC) do most of the work, with a small 4-node H100 GPU server for postprocessing.

## Install

In Claude Code:

```
/plugin marketplace add RIKEN-RCCS/Hokusai-Agent
/plugin install hokusai@hokusai-marketplace
/reload-plugins
```

Then run `/hokusai-demo` to verify the connection end-to-end.

## Configuration

Settings live in `~/.hokusai/config.json`:

```json
{
  "ssh": {"host": "hokusai"},
  "account": "RB999999"
}
```

- `ssh.host` is a `~/.ssh/config` alias or `user@hostname` (key-based auth required; register your key on the [HBW2 Portal](https://hokusai.riken.jp/hbw2/)). `hokusai.riken.jp` round-robins to `hokusai1..4`. The env var `HOKUSAI_HOST` overrides the file.
- `account` is your project ID (e.g. `RB999999`), required for job execution. A JobSpec can override it per job. `HOKUSAI_ACCOUNT` overrides the file.

For documentation search, add your API key for the shared RIKEN embedding service:

```json
{
  "ssh": {"host": "hokusai"},
  "account": "RB999999",
  "embedding": {"api_key": "..."}
}
```

The env var `RCCS_EMBED_API_KEY` sets the key. With it, docs search uses semantic (vector) matching; without it — or off the RIKEN network — it falls back to BM25 keyword search over the same content.
