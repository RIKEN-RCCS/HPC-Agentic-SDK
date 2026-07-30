---
name: rikyu-configuring
description: Use when the user wants to set up, configure, or troubleshoot RikyuAgent — SSH access to the Rikyu cluster, the embedding endpoint for docs search (RAG), or the ~/.hpc-agent/rikyu.json file. Also use when rikyu tools fail with connection or embedding errors.
---

# Configuring RikyuAgent

Settings live in `~/.hpc-agent/rikyu.json` (the common directory shared by
every hpc-agent-core plugin; env vars `RIKYU_HOST`, `RIKYU_EMBED_API_KEY`
override it; the embedding key also falls back to the shared
`RCCS_EMBED_API_KEY` — see below). A legacy `~/.rikyu/config.json` is still
read if it's the only config present, but write new configs to the common
location:

```json
{
  "ssh": {"host": "rikyu"},
  "embedding": {"api_key": "..."}
}
```

## Guided setup — interview the user, then write the file

Read the existing `~/.hpc-agent/rikyu.json` first (falling back to the
legacy `~/.rikyu/config.json` if that's the only one present) and only ask
about what's missing or being changed.

1. **SSH** — ask how they reach the Rikyu login node:
   - An alias in `~/.ssh/config` (recommended) → `"host": "<alias>"`.
   - Otherwise username + hostname → `"host": "user@login.rikyu.r-ccs.riken.jp"`,
     and offer to add a proper alias block to `~/.ssh/config` instead.
   - If the key isn't registered yet, they'll need to generate one (Ed25519
     recommended; ECDSA P-521 or RSA ≥2048-bit also accepted) and register
     the public key through Rikyu's Open OnDemand web portal ("SSH Public
     Key" page) before the first login — point them to that portal by name,
     not a URL, since it isn't one we should be linking to here.
   - **Running the agent session directly on a Rikyu front-end/login node**
     (not a personal laptop)? Use `"host": "localhost"` instead — no SSH key
     needed at all. Skip the verification step below for this case; there's
     nothing to probe.
   - Verify with: `ssh -o BatchMode=yes <host> 'echo ok'` (BatchMode matters —
     the MCP server cannot answer password prompts; key-based auth is required).
     Not applicable for `"host": "localhost"` — see above.
2. **Embedding API key** (optional — skippable, BM25 fallback works). Docs search
   uses a shared RIKEN BGE-M3 endpoint; the endpoint and model are fixed
   constants (the committed embeddings are tied to that model), so the only
   setting is the `api_key`. Store it under `embedding.api_key`.
   - **Shared key across R-CCS plugins**: this is the *same* endpoint other RIKEN
     R-CCS plugins use (e.g. the HOKUSAI plugin). If the user runs more than one,
     they can `export RCCS_EMBED_API_KEY=<key>` once instead of putting the key in
     each plugin's config — `RIKYU_EMBED_API_KEY` and the config file still take
     precedence over it when set.
3. **Write the file** to `~/.hpc-agent/rikyu.json` (`mkdir -p ~/.hpc-agent`
   first if it doesn't exist yet), then `chmod 600 ~/.hpc-agent/rikyu.json`
   — it may hold an API key. Never commit it or echo the key back in
   conversation.
4. **Validate** with the doctor (checks config, SSH, Slurm, endpoint, index):
   ```bash
   uv tool run --quiet --from git+https://github.com/RIKEN-RCCS/Rikyu-Agent.git@main#subdirectory=server rikyu-doctor
   ```
   (From a checkout of the repo: `server/run.sh rikyu_mcp.doctor` also works.)
5. **If the embedding endpoint was added or changed**, rebuild the docs index
   so it gains vector embeddings:
   ```bash
   server/run.sh rikyu_mcp.ingest
   ```
   Then run the doctor again — it should report "chunks with embeddings".

## Notes

- The embedding key and SSH host are both read fresh on every tool call, so
  a config file edit (including switching `ssh.host` to/from `"localhost"`)
  applies immediately — no server restart needed. A rebuilt docs index still
  needs the rikyu-docs server restarted to be picked up (that index is
  loaded once and cached in memory).
- The embedding endpoint is the shared RIKEN R-CCS service and must be reachable
  from where the docs server runs (your machine / the RIKEN network). Off-network
  or without a key, docs search transparently falls back to BM25 keyword search.
