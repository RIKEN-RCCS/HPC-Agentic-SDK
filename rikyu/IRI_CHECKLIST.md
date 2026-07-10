# IRI Facility API coverage — RIKYU

Endpoint-by-endpoint coverage decisions for `server/rikyu_mcp/hpc_server.py`
against the IRI (Integrated Research Infrastructure) Facility API. This is
genuinely machine-specific (what's sensible on RIKYU may not be on another
machine) and intentionally lives here rather than in `hpc-agent-core`.

## Compute

| IRI endpoint | Tool | Status |
|---|---|---|
| `POST /compute/job` | `submit_job` | Implemented. Defaults `queue_name` to `"gpu"` (RIKYU's only partition) and validates the GPU count against RIKYU's supported set (1/2/3/4/8/12/16) before submission. |
| `GET /compute/job/{id}` | `get_job_status` | Implemented (via `sacct`, since RIKYU has accounting). |
| `GET /compute/jobs` | `get_job_statuses` | Implemented; empty `job_ids` returns the current user's jobs from roughly the last two days. |
| `DELETE /compute/job/{id}` | `cancel_job` | Implemented (`scancel`, then re-reads status via `sacct`). |
| `PUT /compute/job/{id}` | `update_job` | Implemented as a generic `scontrol update` field/value pass-through (e.g. extending `TimeLimit`). Not schema-validated beyond what Slurm itself enforces — Slurm will reject a field it doesn't recognize or a change the user isn't permitted to make. |

## Filesystem

All of `fs_ls`, `fs_stat`, `fs_view`, `fs_head`, `fs_tail`, `fs_mkdir`,
`fs_upload`, `fs_download`, `fs_checksum`, `fs_cp`, `fs_mv`, `fs_chmod`,
`fs_chown`, `fs_symlink`, `fs_compress`, `fs_extract` are implemented as
thin wrappers over `hpc_agent_core.middleware` (`run_command`,
`quote_path`, `upload_file`, `download_file`) or direct shell one-liners.
No RIKYU-specific filesystem behavior beyond what Lustre/xfs's own
permissions already enforce (e.g. `fs_chown` will fail for a non-owner the
same way it would over plain SSH).

## Facility / resources

| IRI endpoint | Tool | Status |
|---|---|---|
| `GET /facility` | `get_facility` | Implemented — returns the full bundled `rikyu_config.json` (partitions, job-resource table, storage, modules, Spack). Static. |
| `GET /resources` | `get_resources` | Implemented — **live** occupancy via `sinfo` (`hpc_agent_core`'s `SlurmBackend.get_live_resources()`), not static config. RIKYU has exactly one resource, the `gpu` partition, but its allocated/idle node counts change constantly, hence live. (Corrected 2026-07-10: an earlier revision of this port returned static config here instead — a real gap, since "will my job start soon" needs live data — caught by `hpc-agent-core`'s `PORTING.md` after this port surfaced the missing example.) |
| `GET /resources/{name}` | `get_resource` | Implemented, same live basis as above. |

## Projects / accounting

| IRI endpoint | Tool | Status |
|---|---|---|
| `GET /projects`, `GET /projects/{id}` | — | **Deferred.** RIKYU's job scripts never set `--account` (confirmed absent from every example in the source user guide), and current usage/balance is exposed only through a web billing portal linked from Open OnDemand, not a CLI/API this plugin can query. There is no `sacctmgr`-based project/allocation query documented for RIKYU to wrap. Revisit if RIKYU later exposes project accounting via CLI. |

## Extensions (no IRI counterpart)

| Tool | Why it exists |
|---|---|
| `run_command_on_cluster` | Arbitrary login-node command, for anything the structured tools above don't cover (e.g. `sinfo`, `spack find -x`, `id` to find a group name). Documented as "show before you run," same as `submit_job`. |
| `get_drained_nodes` | Nodes currently drained/down and why, via `sinfo -R` (`hpc_agent_core`'s `SlurmBackend.get_drained_nodes()`). Directly useful for "why won't my job start" triage alongside `get_resources`. |

## Not implemented

- **Interactive jobs** (`salloc`/`srun --pty`): inherently need a live
  terminal session, which doesn't fit this agent's request/response tool
  model. The `rikyu-submitting-jobs` skill tells the user to run these
  themselves for debugging, and points at `run_command_on_cluster` for
  short one-off checks instead.
