---
name: rccs-cloud-configuring
description: Use when the user wants to set up, configure, or troubleshoot RCCS-CloudAgent — SSH access to the R-CCS Cloud login node, the embedding endpoint for docs search (RAG), or the ~/.rccs-cloud/config.json file. Also use when rccs-cloud tools fail with connection or embedding errors.
---

# Configuring RCCS-CloudAgent

Settings live in `~/.rccs-cloud/config.json` (env vars `RCCS_CLOUD_HOST`,
`RCCS_CLOUD_EMBED_API_KEY` override it; the embedding key also falls back to the
shared `RCCS_EMBED_API_KEY` — see below):

```json
{
  "ssh": {"host": "rccs-cloud"},
  "embedding": {"api_key": "..."}
}
```

## Guided setup — interview the user, then write the file

Read the existing `~/.rccs-cloud/config.json` first (if any) and only ask about
what's missing or being changed.

1. **SSH** — ask how they reach the R-CCS Cloud login node:
   - An alias in `~/.ssh/config` (recommended) → `"host": "<alias>"`.
   - Otherwise username + hostname → `"host": "user@login.cloud.r-ccs.riken.jp"`,
     and offer to add a proper alias block to `~/.ssh/config` instead.
   - Verify with: `ssh -o BatchMode=yes <host> 'echo ok'` (BatchMode matters —
     the MCP server cannot answer password prompts; key-based auth is required).
2. **Embedding API key** (optional — skippable, BM25 fallback works). Docs search
   uses a shared RIKEN BGE-M3 endpoint; the endpoint and model are fixed
   constants (the committed embeddings are tied to that model), so the only
   setting is the `api_key`. Store it under `embedding.api_key`.
   - **Shared key across R-CCS plugins**: this is the *same* endpoint the Hokusai
     and Rikyu plugins use. If the user runs more than one, they can
     `export RCCS_EMBED_API_KEY=<key>` once instead of putting the key in each
     plugin's config — `RCCS_CLOUD_EMBED_API_KEY` and the config file still take
     precedence when set.
3. **Write the file**, then `chmod 600 ~/.rccs-cloud/config.json` — it may hold an
   API key. Never commit it or echo the key back in conversation.
4. **Validate** with the doctor (checks config, SSH, Slurm, endpoint, index):
   ```bash
   uv tool run --quiet --from git+https://github.com/RIKEN-RCCS/RCCS-CloudAgent.git@main#subdirectory=server rccs-cloud-doctor
   ```
   (From a checkout: `server/run.sh cloud_mcp.doctor` also works.)
5. **If the embedding endpoint was added or changed**, rebuild the docs index:
   ```bash
   server/run.sh cloud_mcp.rag.ingest
   ```
   Then run the doctor again — it should report "chunks with embeddings".

## Notes

- The embedding key is read per-query; an SSH host change needs the
  rccs-cloud-hpc server restarted (reconnect MCP servers or restart Claude Code).
- The embedding endpoint is shared RIKEN R-CCS infrastructure and must be reachable
  from where the docs server runs. Off-network or without a key, docs search
  transparently falls back to BM25 keyword search.
