---
name: ai4s-configuring
description: Use when the user wants to set up, configure, or troubleshoot RikyuAgent — SSH access to the AI4S cluster, the embedding endpoint for docs search (RAG), or the ~/.rikyu/config.json file. Also use when rikyu tools fail with connection or embedding errors.
---

# Configuring RikyuAgent

Settings live in `~/.rikyu/config.json` (env vars `RIKYU_HOST`,
`RIKYU_EMBED_API_KEY` override it; the embedding key also falls back to the
shared `RCCS_EMBED_API_KEY` — see below):

```json
{
  "ssh": {"host": "rikyu"},
  "embedding": {"api_key": "..."}
}
```

## Guided setup — interview the user, then write the file

Read the existing `~/.rikyu/config.json` first (if any) and only ask about
what's missing or being changed.

1. **SSH** — ask how they reach the AI4S login node:
   - An alias in `~/.ssh/config` (recommended) → `"host": "<alias>"`.
   - Otherwise username + hostname → `"host": "user@login01.ai.r-ccs.riken.jp"`,
     and offer to add a proper alias block to `~/.ssh/config` instead.
   - Verify with: `ssh -o BatchMode=yes <host> 'echo ok'` (BatchMode matters —
     the MCP server cannot answer password prompts; key-based auth is required).
2. **Embedding API key** (optional — skippable, BM25 fallback works). Docs search
   uses a shared RIKEN BGE-M3 endpoint; the endpoint and model are fixed
   constants (the committed embeddings are tied to that model), so the only
   setting is the `api_key`. Store it under `embedding.api_key`.
   - **Shared key across R-CCS plugins**: this is the *same* endpoint other RIKEN
     R-CCS plugins use (e.g. the HOKUSAI plugin). If the user runs more than one,
     they can `export RCCS_EMBED_API_KEY=<key>` once instead of putting the key in
     each plugin's config — `RIKYU_EMBED_API_KEY` and the config file still take
     precedence over it when set.
3. **Write the file**, then `chmod 600 ~/.rikyu/config.json` — it may hold an
   API key. Never commit it or echo the key back in conversation.
4. **Validate** with the doctor (checks config, SSH, Slurm, endpoint, index):
   ```bash
   uv tool run --quiet --from git+https://github.com/RIKEN-RCCS/Rikyu-Agent.git@main#subdirectory=server rikyu-doctor
   ```
   (From a checkout of the repo: `server/run.sh rikyu_mcp.doctor` also works.)
5. **If the embedding endpoint was added or changed**, rebuild the docs index
   so it gains vector embeddings:
   ```bash
   server/run.sh rikyu_mcp.rag.ingest
   ```
   Then run the doctor again — it should report "chunks with embeddings".

## Notes

- The embedding key is read per-query, so docs search picks up a changed key
  immediately; an SSH host change needs the rikyu-hpc server restarted
  (reconnect MCP servers or restart Claude Code). A rebuilt docs index also
  needs the rikyu-docs server restarted to be picked up.
- The embedding endpoint is the shared RIKEN R-CCS service and must be reachable
  from where the docs server runs (your machine / the RIKEN network). Off-network
  or without a key, docs search transparently falls back to BM25 keyword search.
