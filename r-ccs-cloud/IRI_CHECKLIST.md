# IRI Facility API coverage checklist

Tracks how far `rccs-cloud-hpc` covers the [IRI Facility API](https://api.alcf.anl.gov/)
(ALCF implementation, spec at api.alcf.anl.gov/openapi.json — not committed; fetch
it when needed, see AGENTS.md). Each IRI endpoint maps to an MCP tool executed on
R-CCS Cloud over SSH via remotemanager.

**The verdicts below are specific to R-CCS Cloud.** When porting to a new machine,
re-decide every row against what *that* machine can do.

Legend: ✅ implemented · 🔜 planned next · ❌ deferred (with reason)

## facility

| IRI endpoint | Tool | Status | Notes |
|---|---|---|---|
| GET /facility | `get_facility` | ✅ | Static data from `server/cloud_mcp/data/cloud_config.json` |
| GET /facility/sites | — | ❌ | Single-site deployment; fold into `get_facility` if ever needed |
| GET /facility/sites/{site_id} | — | ❌ | Same |

## status

| IRI endpoint | Tool | Status | Notes |
|---|---|---|---|
| GET /status/resources | `get_resources` | ✅ | One resource (`rccs-cloud`) with per-partition node summary from sinfo |
| GET /status/resources/{resource_id} | `get_resource` | ✅ | Per-partition node counts + drained nodes with reasons (`sinfo -R`) |
| GET /status/incidents | — | ❌ | No incident data source; closest signal is drained nodes (`sinfo -R`) |
| GET /status/incidents/{id} | — | ❌ | Same |
| GET /status/events | — | ❌ | Same |
| GET /status/events/{id} | — | ❌ | Same |

## account

| IRI endpoint | Tool | Status | Notes |
|---|---|---|---|
| GET /account/capabilities | — | ❌ | No equivalent concept exposed |
| GET /account/capabilities/{id} | — | ❌ | Same |
| GET /account/projects | `get_projects` | ✅ | `sacctmgr show associations user=$USER` |
| GET /account/projects/{id} | `get_project` | ✅ | Filter over `get_projects` |
| GET .../project_allocations | — | ❌ | R-CCS Cloud does not expose per-project core-time budgets (unlike HOKUSAI HBW2's `listcpu`) |
| GET .../project_allocations/{id} | — | ❌ | Same |
| GET .../user_allocations | — | ❌ | Same |
| GET .../user_allocations/{id} | — | ❌ | Same |

## compute

| IRI endpoint | Tool | Status | Notes |
|---|---|---|---|
| POST /compute/job/{resource_id} | `submit_job` | ✅ | JobSpec → sbatch script (kept in `~/.rccs-cloud/jobs/`); returns `{job_id, script_path}` |
| PUT /compute/job/{rid}/{job_id} | `update_job` | ✅ | `scontrol update job` |
| GET /compute/status/{rid}/{job_id} | `get_job_status` | ✅ | |
| POST /compute/status/{rid} | `get_job_statuses` | ✅ | Batch; empty list = current user's last 2 days |
| DELETE /compute/cancel/{rid}/{job_id} | `cancel_job` | ✅ | scancel + post-cancel state report |

## filesystem

| IRI endpoint | Tool | Status | Notes |
|---|---|---|---|
| GET /filesystem/ls | `fs_ls` | ✅ | |
| GET /filesystem/stat | `fs_stat` | ✅ | |
| GET /filesystem/file | — | 🔜 | IRI generic file read; `fs_view` covers this; add as alias |
| GET /filesystem/view | `fs_view` | ✅ | 200KB cap; text only |
| GET /filesystem/head | `fs_head` | ✅ | |
| GET /filesystem/tail | `fs_tail` | ✅ | Primary way to read job output |
| POST /filesystem/mkdir | `fs_mkdir` | ✅ | |
| POST /filesystem/upload | `fs_upload` | ✅ | Text or base64 binary; 5 MB cap |
| GET /filesystem/download | `fs_download` | ✅ | Base64-encoded; 5 MB cap |
| GET /filesystem/checksum | `fs_checksum` | ✅ | `sha256sum` |
| POST /filesystem/mv | `fs_mv` | ✅ | |
| POST /filesystem/cp | `fs_cp` | ✅ | |
| DELETE /filesystem/rm | — | ❌ | Deliberately omitted (destructive) |
| PUT /filesystem/chmod | `fs_chmod` | ✅ | |
| PUT /filesystem/chown | `fs_chown` | ✅ | |
| POST /filesystem/symlink | `fs_symlink` | ✅ | |
| POST /filesystem/compress | `fs_compress` | ✅ | tar with gzip/bzip2/xz/none + match_pattern |
| POST /filesystem/extract | `fs_extract` | ✅ | |

## task

| IRI endpoint | Tool | Status | Notes |
|---|---|---|---|
| GET /task/{task_id} | — | ❌ | SSH execution is synchronous; no async task layer needed |
| DELETE /task/{task_id} | — | ❌ | Same |
| GET /task | — | ❌ | Same |

---

## Known deviations from the IRI/PSI-J schemas

### ResourceSpec

| Field | IRI | Ours | Action |
|---|---|---|---|
| `node_count` | present | present ✅ | — |
| `processes_per_node` | present | present ✅ | — |
| `process_count` | present | present ✅ | — |
| `cpu_cores_per_process` | present | present ✅ | — |
| `gpu_cores_per_process` | present (PSI/J standard) | present ✅ (fallback) | Used as fallback when `gpus` unset |
| `gpus` | absent (R-CCS Cloud extension) | present | Maps to `--gpus=<n>`; not emitted for qc-gh200/ng-dgx |
| `exclusive_node_use` | present | present ✅ | Maps to `--exclusive` |
| `memory` | present (bytes) | present ✅ | Maps to `--mem` (bytes → MB) |

### JobAttributes

| Field | IRI | Ours | Action |
|---|---|---|---|
| `duration` | integer seconds | HH:MM:SS string or int seconds ✅ | Both accepted |
| `queue_name` | present | present ✅ | Default: `genoa` |
| `account` | present | present ✅ | Optional on R-CCS Cloud |
| `reservation_id` | present | present ✅ | Maps to `--reservation` |

### submit_job return value

IRI returns `TaskSubmitResponse {task_id, task_uri}` (async task model).
Our SSH execution is synchronous — we return `{job_id, script_path}` directly.
This is an intentional deviation.

### resource_id

Accepted and validated in all compute/filesystem tools but there is a single
resource: `rccs-cloud`.
