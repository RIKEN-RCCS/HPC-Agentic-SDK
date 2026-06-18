# RikyuAgent

Claude Code plugin for the RIKEN **AI4S** supercomputer — submit and monitor Slurm jobs, manage files on the cluster, and search the official documentation, all from the agent.

AI4S is a GPU-first system: 216 NVIDIA Grace + GB200 nodes (4 GPUs each, aarch64).

## Install

In Claude Code:

```
/plugin marketplace add RIKEN-RCCS/Rikyu-Agent
/plugin install rikyu@rikyu-marketplace
/reload-plugins
```

Then run `/ai4s-demo` to verify the connection end-to-end.

## Configuration

Settings live in `~/.rikyu/config.json`:

```json
{
  "ssh": {"host": "rikyu"}
}
```

`ssh.host` is a `~/.ssh/config` alias or `user@hostname` (key-based auth required). The env var `RIKYU_HOST` overrides the file.

For documentation search, add your API key for the shared RIKEN embedding service:

```json
{
  "ssh": {"host": "rikyu"},
  "embedding": {"api_key": "..."}
}
```

The env var `RCCS_EMBED_API_KEY` sets the key. With it, docs search uses semantic (vector) matching; without it — or off the RIKEN network — it falls back to BM25 keyword search over the same content.
