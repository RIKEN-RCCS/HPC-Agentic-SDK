---
name: hokusai-configuring
description: Configure the HOKUSAI BigWaterfall2 (HBW2) plugin — set the SSH host, the default project to charge, and verify connectivity. Use when the plugin is first installed, when tool calls report "Plugin not configured", or when jobs fail with "No project named".
---

# Configuring the HOKUSAI (HBW2) plugin

HBW2 is reached over SSH with **key-based auth only**. Before the plugin can
do anything on the cluster, two things must be true: your SSH key is
registered, and the plugin knows which host to reach and which project to bill.

## 1. Register your SSH key (one time, off-agent)

Public-key auth is the only way onto HBW2 — there are no password prompts.
Register your public key through the portal at
`https://hokusai.riken.jp/hbw2/` before the first login. Confirm you can
`ssh hokusai.riken.jp` yourself, or set up an SSH alias (e.g. `hokusai`) in
`~/.ssh/config` pointing at `hokusai.riken.jp` with your key.

## 2. Write the config file

The plugin reads `~/.hpc-agent/hokusai.json`. Create it with:

```json
{
  "ssh": { "host": "hokusai" },
  "defaults": { "account": "RB99999" }
}
```

- `ssh.host` — an alias from `~/.ssh/config`, or `user@hokusai.riken.jp`.
  Defaults to `hokusai` if omitted.
- `defaults.account` — the project ID to bill when a job doesn't name one.
  **Every HBW2 job must be billed to a project**, so set this (or pass an
  account per job) or submissions will error. RIKEN project IDs start `RB`;
  HPCI-derived ones start `HP`. Use `get_projects` to see which accounts you
  may charge.

Overrides: `HOKUSAI_HOST`, `HOKUSAI_ACCOUNT`, and `HOKUSAI_CONFIG` (a full
path to an alternate config file) take precedence over the file.

## 3. Verify

Run the doctor to check config, SSH + Slurm, the bundled guide, the docs
index, and the embedding endpoint:

```bash
hokusai-doctor        # or: python -m hokusai_mcp.doctor
```

The SSH and Slurm checks must pass. The embedding endpoint is optional — if
it's unreachable (e.g. you're off the RIKEN network), docs search falls back
to keyword (BM25) search, which still works.
