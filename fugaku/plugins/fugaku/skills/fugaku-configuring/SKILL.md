---
name: fugaku-configuring
description: Configure Fugaku Agent — SSH access to the Fugaku login node, the default project group, and the LLIO storage volume. Use for first-time setup or connection/group failures.
---

# Configure Fugaku Agent

Create `~/.hpc-agent/fugaku.json`:

```json
{
  "ssh": {"host": "fugaku"},
  "defaults": {"group": "ra000009", "gfscache_volume": "/vol0004"}
}
```

- `ssh.host` is a `~/.ssh/config` alias (recommended — set up public-key
  auth per the Fugaku User Portal first) or `user@login.fugaku.r-ccs.riken.jp`.
  `FUGAKU_HOST` overrides it.
- `defaults.group` is the project group charged when a job doesn't set
  `attributes.account` explicitly (PJM's mandatory `-g`). Find your real
  groups with `run_command_on_cluster("id")` — the shared `fugaku` group
  cannot submit jobs. `FUGAKU_GROUP` overrides it. If neither is set,
  `submit_job` raises a clear error rather than letting `pjsub` reject the
  job with an opaque "PJM 0071" message.
- `defaults.gfscache_volume` is the second-layer storage volume (e.g.
  `/vol0004`) declared via `#PJM -x PJM_LLIO_GFSCACHE=`, required whenever a
  job's work lives outside `$HOME` (including Spack). `FUGAKU_GFSCACHE`
  overrides it. Leave unset if your jobs only ever touch `$HOME`.

Verify with:

```bash
./server/run.sh fugaku_mcp.doctor
```

A healthy setup reports SSH connectivity and that `pjsub`/`pjstat`/`pjdel`/
`pjalter` are all on `PATH`. Public-key registration itself happens on the
Fugaku website's User Portal, not through this plugin.
