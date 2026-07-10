# IRI Facility API coverage checklist

Tracks how far `rccs-cloud-hpc` covers the [IRI Facility API](https://api.alcf.anl.gov/)
(ALCF implementation, spec at api.alcf.anl.gov/openapi.json — not committed;
fetch it when needed). Each IRI endpoint maps to an MCP tool executed on the
R-CCS Cloud login node over SSH via `hpc_agent_core.middleware`.

**The verdicts below are specific to the R-CCS Cloud.** When porting to a new
machine, re-decide every row against what *that* machine can do.

Legend: ✅ implemented · 🔜 planned · ❌ deferred (with reason)

## facility

| IRI endpoint | Tool | Status | Notes |
|---|---|---|---|
| GET /facility | `get_facility` | ✅ | Static data from `data/cloud_config.json` |
| GET /facility/sites | — | ❌ | Single-site deployment |
| GET /facility/sites/{site_id} | — | ❌ | Same |

## status

| IRI endpoint | Tool | Status | Notes |
|---|---|---|---|
| GET /status/resources | `get_resources` | ✅ | One resource (`rccs-cloud`) with per-partition node summary from live `sinfo` (via `compute.get_live_resources`) |
| GET /status/resources/{resource_id} | `get_resource` | ✅ | Per-partition counts + drained nodes with reasons (`sinfo -R`, via `compute.get_drained_nodes`) |
| GET /status/incidents · /events (+ {id}) | — | ❌ | No incident/event data source; closest signal is drained nodes |

## account

| IRI endpoint | Tool | Status | Notes |
|---|---|---|---|
| GET /account/projects | `get_projects` | ✅ | `sacctmgr show associations user=$USER` |
| GET /account/projects/{id} | `get_project` | ✅ | Filter over `get_projects` |
| GET /account/capabilities (+ {id}) | — | ❌ | No equivalent concept exposed |
| GET .../project_allocations · user_allocations (+ {id}) | — | ❌ | R-CCS Cloud exposes no per-project/user core-time budgets |

## compute

| IRI endpoint | Tool | Status | Notes |
|---|---|---|---|
| POST /compute/job/{resource_id} | `submit_job` | ✅ | JobSpec → sbatch script (kept in `~/agent/jobs/`); returns `{job_id, script_path}` |
| PUT /compute/job/{rid}/{job_id} | `update_job` | ✅ | `scontrol update job` |
| GET /compute/status/{rid}/{job_id} | `get_job_status` | ✅ | Note: sacct lags submit ~1–2 s (see AGENTS.md / monitoring skill) |
| POST /compute/status/{rid} | `get_job_statuses` | ✅ | Batch; empty list = current user's last ~2 days |
| DELETE /compute/cancel/{rid}/{job_id} | `cancel_job` | ✅ | scancel + post-cancel state report |

## filesystem

| IRI endpoint | Tool | Status | Notes |
|---|---|---|---|
| GET /filesystem/ls | `fs_ls` | ✅ | |
| GET /filesystem/stat | `fs_stat` | ✅ | |
| GET /filesystem/view | `fs_view` | ✅ | 200 KB cap; text only |
| GET /filesystem/head | `fs_head` | ✅ | |
| GET /filesystem/tail | `fs_tail` | ✅ | Primary way to read job output |
| GET /filesystem/checksum | `fs_checksum` | ✅ | `sha256sum` |
| POST /filesystem/mkdir | `fs_mkdir` | ✅ | |
| POST /filesystem/upload | `fs_upload` | ⚠️ deviation | `fs_upload(path, local_path)` transfers local→remote via rsync (scp fallback if rsync < 3.0); returns `{remote_path, bytes, sha256, verified, transport}`. Diverges from IRI's multipart body, which would route file bytes through the MCP tool input. |
| GET /filesystem/download | `fs_download` | ⚠️ deviation | `fs_download(path, local_path=None)` transfers remote→local via rsync (scp fallback); returns metadata. Diverges from IRI's base64-in-body shape, which fails past ~12 KB through the model context. |
| POST /filesystem/mv | `fs_mv` | ✅ | |
| POST /filesystem/cp | `fs_cp` | ✅ | |
| PUT /filesystem/chmod | `fs_chmod` | ✅ | |
| PUT /filesystem/chown | `fs_chown` | ✅ | |
| POST /filesystem/symlink | `fs_symlink` | ✅ | |
| POST /filesystem/compress | `fs_compress` | ✅ | tar with gzip/bzip2/xz/none + match_pattern |
| POST /filesystem/extract | `fs_extract` | ✅ | |
| GET /filesystem/file | — | 🔜 | `fs_view` covers this; add as an alias if needed |
| DELETE /filesystem/rm | — | ❌ | Deliberately omitted (destructive) |

## task

| IRI endpoint | Tool | Status | Notes |
|---|---|---|---|
| GET /task/{id} · DELETE /task/{id} · GET /task | — | ❌ | SSH execution is synchronous; no async task layer needed |

## Extensions (no IRI counterpart)

| Tool | Notes |
|---|---|
| `run_command_on_cluster` | Arbitrary login-node command. Show the command before running unless the user said to just run it. Not for heavy computation — submit a job. |

---

## Known deviations from the IRI/PSI-J schemas

- **`ResourceSpec.gpus`** is an R-CCS Cloud extension (absent from upstream
  PSI/J) mapping to `--gpus=<n>`; not emitted for qc-gh200 / ng-dgx-m[0-3].
  `gpu_cores_per_process` (the PSI/J standard) is honored as a fallback.
- **`JobAttributes.duration`** accepts both integer seconds and an
  `HH:MM:SS` / `D-HH:MM:SS` string; default partition is `genoa`; `account` is
  optional on the R-CCS Cloud.
- **`submit_job` return value**: IRI returns an async `TaskSubmitResponse`
  `{task_id, task_uri}`. SSH execution here is synchronous, so we return
  `{job_id, script_path}` directly — an intentional deviation.
- **`resource_id`** is accepted and validated in compute tools, but there is a
  single resource: `rccs-cloud`.
