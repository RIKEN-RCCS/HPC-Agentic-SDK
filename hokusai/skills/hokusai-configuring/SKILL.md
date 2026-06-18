---
name: hokusai-configuring
description: Use when the user wants to set up, configure, or troubleshoot HokusaiAgent — SSH access to the HOKUSAI BigWaterfall2 (HBW2) front-end, the default project/account, the optional embedding endpoint for docs search, or the ~/.hokusai/config.json file. Also use when hokusai tools fail with connection or account errors.
---

# Configuring HokusaiAgent

Settings live in `~/.hokusai/config.json` (env vars `HOKUSAI_HOST`,
`HOKUSAI_ACCOUNT`, `HOKUSAI_EMBED_API_KEY` override it; the embedding key also
falls back to the shared `RCCS_EMBED_API_KEY` — see below):

```json
{
  "ssh": {"host": "hokusai"},
  "account": "RB999999",
  "embedding": {"api_key": "..."}
}
```

## Guided setup — interview the user, then write the file

Read the existing `~/.hokusai/config.json` first (if any) and only ask about
what's missing or being changed.

1. **SSH** — ask how they reach the HBW2 front-end:
   - An alias in `~/.ssh/config` (recommended) → `"host": "<alias>"`.
   - Otherwise username + hostname → `"host": "user@hokusai.riken.jp"`,
     and offer to add a proper alias block to `~/.ssh/config` instead.
     (`hokusai.riken.jp` round-robins to `hokusai1..4.riken.jp`.)
   - Verify with: `ssh -o BatchMode=yes <host> 'echo ok'` (BatchMode matters —
     the MCP server cannot answer password prompts; key-based auth is required.
     Public keys are registered on the HBW2 Portal: https://hokusai.riken.jp/hbw2/).
2. **Default account/project** — HBW2 requires `--account <projectID>` for every
   job. Ask for the project ID (e.g. `RB999999` for RIKEN projects) and store it
   as `"account"`. A JobSpec can still override it per job. If the user has only
   one project, `listcpu` on the front-end shows it.
3. **Embedding API key** (optional — improves docs search). Docs search uses a
   shared RIKEN embedding service (BGE-M3 at `http://llm.ai.r-ccs.riken.jp:11434/v1`).
   The endpoint and model are fixed; the only setting is the `api_key`. Ask the
   user for it and store it under `embedding.api_key`. Without it, search falls
   back to BM25 keyword matching (still useful). The committed index already has
   vectors, so no rebuild is needed — the key just unlocks semantic *query* matching.
   - **Shared key across R-CCS plugins**: this is the *same* endpoint other RIKEN
     R-CCS plugins use (e.g. the AI4S plugin). If the user runs more than one, they
     can `export RCCS_EMBED_API_KEY=<key>` once instead of putting the key in each
     plugin's config — both `HOKUSAI_EMBED_API_KEY` and the config file still take
     precedence over it when set.
4. **Write the file**, then `chmod 600 ~/.hokusai/config.json` — it may hold an
   API key. Never commit it or echo the key back in conversation.
5. **Validate** with the doctor (checks config, SSH, Slurm, embedding, index):
   ```bash
   "$CLAUDE_PLUGIN_ROOT"/server/run.sh hokusai_mcp.doctor
   ```
   (From a checkout of the repo: `server/run.sh hokusai_mcp.doctor`.)

## Notes

- Settings are read per-call, so account and embedding changes apply
  immediately; an SSH host change needs the hokusai-hpc server restarted
  (reconnect MCP servers or restart Claude Code).
- The embedding endpoint is shared RIKEN infrastructure and is reachable from
  the RIKEN network. Off-network (or without a key), docs search transparently
  uses BM25 keyword matching over the same content — no configuration needed.
- The endpoint and model (`bge-m3:567m`) are **not** user-configurable: the
  committed `embeddings.npy` is tied to that exact model.
