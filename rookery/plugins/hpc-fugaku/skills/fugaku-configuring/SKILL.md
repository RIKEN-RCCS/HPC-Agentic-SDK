---
name: fugaku-configuring
description: Use when the user wants to set up, configure, or troubleshoot Fugaku — SSH access, the embedding endpoint for docs search (RAG), or the ~/.hpc-agent/fugaku.json file. Also use when fugaku tools fail with connection or embedding errors.
---

# Configuring Fugaku

Settings live in `~/.hpc-agent/fugaku.json` (the common directory
shared by every facility this plugin serves — one file per facility). Env
vars `FUGAKU_HOST` and `FUGAKU_EMBED_API_KEY` override the
file; the embedding key also falls back to a shared `RCCS_EMBED_API_KEY`
env var if several facilities share the same endpoint.

The file this facility needs (add `"embedding": {"api_key": "..."}` too if
docs search should use vector rather than keyword matching):

```json
{
  "ssh": {
    "host": "fugaku"
  },
  "defaults": {
    "group": "hp000000",
    "gfscache_volume": "/vol0004"
  }
}
```

## What must be true before it can connect

Fugaku accepts key-based SSH only, through RIKEN's login gateway.
Add a 'fugaku' alias to ~/.ssh/config pointing at your login node,
or set ssh.host to user@login.fugaku.r-ccs.riken.jp.
Set defaults.group to your project group: every Fugaku job needs
one (#PJM -g), and the shared 'fugaku' group every account belongs
to is denied job submission, so there is no usable fallback. Run
`id` on the login node to see your real project groups.
Set defaults.gfscache_volume (e.g. /vol0004) if your work touches
second-layer storage outside $HOME, including Spack — it is
assigned per project. Leave it out for jobs that stay in $HOME.

## Guided setup — interview the user, then write the file

Read the existing `~/.hpc-agent/fugaku.json` first and only ask
about what's missing or being changed.

1. **SSH** — ask how they reach this facility's login node:

   - An alias in `~/.ssh/config` (recommended) → `"host": "<alias>"`,
     pointing at your Fugaku login node via RIKEN's login gateway.
   - **Key-based SSH only.**

**Also set `defaults.group`** — Fugaku needs a second key that most
facilities don't:

```json
{
  "ssh": { "host": "fugaku" },
  "defaults": { "group": "hp000000", "gfscache_volume": "/vol0004" }
}
```

- `defaults.group` is the project group charged on every job (`#PJM -g`).
  **Mandatory**: the shared `fugaku` group that every account belongs to is
  explicitly denied job submission, so there is no usable fallback. Run
  `id` on the login node to see the account's real project groups.
  `FUGAKU_GROUP` overrides the file.
- `defaults.gfscache_volume` (e.g. `/vol0004`) declares the second-layer
  storage volume a job will touch. Required whenever work goes outside
  `$HOME`, including anything under Spack; omit it for jobs that stay in
  `$HOME`. `FUGAKU_GFSCACHE` overrides the file.
- **Resolve the group's data area at setup time.** Run `accountd -E` on
  the login node once the connection works: it lists each project group's
  `/vol0X0X/data/<group>/` path and quota. That output is the checked
  answer for which volume `gfscache_volume` should name, and jobs should
  run from that data area, not `$HOME` (see `fugaku-submitting-jobs`).

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
3. **Write the file** to `~/.hpc-agent/fugaku.json` (`mkdir -p
   ~/.hpc-agent` first if needed), then `chmod 600` it — it may hold an API
   key. Never commit it or echo the key back in conversation.
4. **Validate**:
   ```bash
   uv tool run --quiet --from 'git+https://github.com/RIKEN-RCCS/HPC-Agentic-SDK.git@main#subdirectory=rookery' hpc-doctor fugaku
   ```
   (From a checkout of this repo: `.venv/bin/python -m hpc_mcp.doctor
   fugaku` also works.)
5. **If the embedding endpoint was added or changed**, rebuild this
   facility's docs index:
   ```bash
   uv tool run --quiet --from 'git+https://github.com/RIKEN-RCCS/HPC-Agentic-SDK.git@main#subdirectory=rookery' python -m hpc_mcp.ingest fugaku
   ```
   Then run the doctor again — it should report "chunks with embeddings".

## Notes

- Settings are read fresh on every tool call, so a config file edit
  (including switching `ssh.host` to/from `"localhost"`) applies
  immediately — no server restart needed. A rebuilt docs index still needs
  the `hpc-docs` server restarted to be picked up.
- Off-network or without a key, docs search transparently falls back to
  BM25 keyword search over the same content — the plugin still works.
