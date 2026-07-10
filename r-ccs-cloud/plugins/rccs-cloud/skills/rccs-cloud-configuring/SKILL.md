---
name: rccs-cloud-configuring
description: Use when the user wants to set up, configure, or troubleshoot the R-CCS Cloud plugin — SSH access to the login node, the embedding endpoint for docs search (RAG), or the ~/.hpc-agent/rccs_cloud.json config file. Also use when rccs-cloud tools fail with connection or embedding errors.
---

# Configuring the R-CCS Cloud plugin

Settings live in `~/.hpc-agent/rccs_cloud.json` (the common directory shared by
every hpc-agent-core plugin — one file per machine). Environment variables
`RCCS_CLOUD_HOST` and `RCCS_CLOUD_EMBED_API_KEY` override the file; the
embedding key also falls back to the shared `RCCS_EMBED_API_KEY` (see below).

```json
{
  "ssh": {"host": "rccs-cloud"},
  "embedding": {"api_key": "..."}
}
```

> A legacy path `~/.rccs-cloud/config.json` is still read if it is the *only*
> config that exists, so an earlier setup keeps working. New setups should use
> `~/.hpc-agent/rccs_cloud.json`.

## Guided setup — interview the user, then write the file

Read the existing config first (if any) and only ask about what's missing or
being changed.

1. **SSH** — ask how they reach the R-CCS Cloud login node
   (`login.cloud.r-ccs.riken.jp`):
   - An alias in `~/.ssh/config` (recommended) → `"host": "<alias>"`.
   - Otherwise username + hostname → `"host": "user@login.cloud.r-ccs.riken.jp"`,
     and offer to add a proper alias block to `~/.ssh/config`.
   - Verify with `ssh -o BatchMode=yes <host> 'echo ok'` — BatchMode matters,
     since the MCP server cannot answer a password prompt; key-based auth is required.
2. **Embedding API key** (optional — skippable, BM25 fallback works). Docs
   search uses a shared RIKEN BGE-M3 endpoint; the endpoint and model are fixed
   constants (the committed embeddings are tied to that model), so the only
   setting is `api_key`. Store it under `embedding.api_key`.
   - **Shared key across R-CCS plugins**: this is the *same* endpoint the other
     R-CCS plugins use. If the user runs more than one, they can
     `export RCCS_EMBED_API_KEY=<key>` once instead of repeating it in each
     plugin's config; `RCCS_CLOUD_EMBED_API_KEY` and the config file still take
     precedence.
3. **Write the file**, then `chmod 600 ~/.hpc-agent/rccs_cloud.json` — it may
   hold an API key. Never commit it or echo the key back in conversation.
4. **Validate** with the doctor (checks config, SSH, Slurm, guide, index, endpoint):
   ```bash
   uv tool run --quiet --from git+https://github.com/william-dawson/RCCS-CloudAgent.git@main#subdirectory=server rccs-cloud-doctor
   ```
   (From a checkout: `server/run.sh cloud_mcp.doctor` also works.)

## Notes

- The embedding key is read per-query; an SSH host change needs the
  rccs-cloud-hpc server reconnected (or Claude Code / Codex restarted).
- Off-network or without a key, docs search transparently falls back to BM25
  keyword search over the same content — the plugin still works.
- The MCP servers never fail to start on a missing/malformed config: you only
  see the error when a tool actually needs SSH, with a pointer back to this skill.
