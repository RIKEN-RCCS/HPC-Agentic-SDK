---
name: hokusai-configuring
description: Use when the user wants to set up, configure, or troubleshoot HOKUSAI BigWaterfall2 (HBW2) — SSH access, the embedding endpoint for docs search (RAG), or the ~/.hpc-agent/hokusai.json file. Also use when hokusai tools fail with connection or embedding errors.
---

# Configuring HOKUSAI BigWaterfall2 (HBW2)

Settings live in `~/.hpc-agent/hokusai.json` (the common directory
shared by every facility this plugin serves — one file per facility). Env
vars `HOKUSAI_HOST` and `HOKUSAI_EMBED_API_KEY` override the
file; the embedding key also falls back to a shared `RCCS_EMBED_API_KEY`
env var if several facilities share the same endpoint.

The file this facility needs (add `"embedding": {"api_key": "..."}` too if
docs search should use vector rather than keyword matching):

```json
{
  "ssh": {
    "host": "hokusai"
  },
  "defaults": {
    "account": "RB99999"
  }
}
```

## What must be true before it can connect

HBW2 accepts key-based SSH only — there are no password prompts.
Register your public key at https://hokusai.riken.jp/hbw2/ before the
first login, then either add a 'hokusai' alias to ~/.ssh/config
pointing at hokusai.riken.jp, or set ssh.host to user@hokusai.riken.jp.
Set defaults.account to the project to bill: every HBW2 job requires
one (RIKEN IDs start RB, HPCI-derived ones start HP).
Running on an HBW2 front-end node instead of a laptop? Use
"host": "localhost" and no SSH key is needed at all.

## Guided setup — interview the user, then write the file

Read the existing `~/.hpc-agent/hokusai.json` first and only ask
about what's missing or being changed.

1. **SSH** — ask how they reach this facility's login node:

   - An alias in `~/.ssh/config` (recommended) → `"host": "<alias>"`,
     pointing at `hokusai.riken.jp`.
   - **Key-based auth is the only way onto HBW2** — there are no password
     prompts. If the key isn't registered yet, register the public key
     through the HBW2 portal at `https://hokusai.riken.jp/hbw2/` before the
     first login.

**Also set `defaults.account`** — this facility needs a second key that
most don't:

```json
{
  "ssh": { "host": "hokusai" },
  "defaults": { "account": "RB99999" }
}
```

**Every HBW2 job must be billed to a project**, so set this (or pass an
account per job) or submissions will error with a message telling you to.
RIKEN project IDs start `RB`; HPCI-derived ones start `HP`. Use
`get_projects(facility="hokusai")` to see which accounts you may charge.
`HOKUSAI_ACCOUNT` overrides the file. A legacy top-level `"account"`
key (from an older config example) is still honored if `defaults.account`
is absent, so an existing config keeps working unchanged.

   - **Running the agent session directly on this facility's own
     front-end/login node** (not a personal laptop)? Use
     `"host": "localhost"` instead — no SSH key needed. Skip the
     verification step below for this case; there's nothing to probe.
   - Verify with: `ssh -o BatchMode=yes <host> 'echo ok'` (BatchMode
     matters — the server cannot answer a password prompt; key-based auth
     is required). Not applicable for `"host": "localhost"`.
   - **Enable SSH multiplexing unless the user explicitly opts out.** This
     lets repeated agent operations reuse one authenticated connection rather
     than making the login node authenticate every call. Recommend an SSH
     alias and, after showing the exact change and receiving confirmation,
     add a narrowly scoped block to `~/.ssh/config` without overwriting any
     unrelated entries:
     ```sshconfig
     Host <alias>
       ControlMaster auto
       ControlPath ~/.ssh/controlmasters/%C
       ControlPersist 30m
     ```
     Create `~/.ssh/controlmasters` with mode `0700`, then open the initial
     master in the user's own terminal with `ssh -MNf <alias>`. Set
     `ssh.host` to that same alias. `ControlMaster no` is an intentional
     opt-out; do not add or change multiplexing settings when it is present.
2. **Embedding API key** (optional — skippable; BM25 keyword search still
   works without it). Store it under `embedding.api_key`.
3. **Write the file** to `~/.hpc-agent/hokusai.json` (`mkdir -p
   ~/.hpc-agent` first if needed), then `chmod 600` it — it may hold an API
   key. Never commit it or echo the key back in conversation.
4. **Validate**:
   ```bash
   uv tool run --quiet --from 'git+https://github.com/RIKEN-RCCS/HPC-Agentic-SDK.git@main#subdirectory=rookery' hpc-doctor hokusai
   ```
   (From a checkout of this repo: `.venv/bin/python -m hpc_mcp.doctor
   hokusai` also works.)
5. **If the embedding endpoint was added or changed**, rebuild this
   facility's docs index:
   ```bash
   uv tool run --quiet --from 'git+https://github.com/RIKEN-RCCS/HPC-Agentic-SDK.git@main#subdirectory=rookery' python -m hpc_mcp.ingest hokusai
   ```
   Then run the doctor again — it should report "chunks with embeddings".

## Notes

- Settings are read fresh on every tool call, so a config file edit
  (including switching `ssh.host` to/from `"localhost"`) applies
  immediately — no server restart needed. A rebuilt docs index still needs
  the `hpc-docs` server restarted to be picked up.
- Off-network or without a key, docs search transparently falls back to
  BM25 keyword search over the same content — the plugin still works.
