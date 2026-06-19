# IRI Facility API coverage checklist

Tracks how far `rikyu-hpc` covers the [IRI Facility API](https://api.alcf.anl.gov/)
(ALCF implementation, spec at api.alcf.anl.gov/openapi.json — not committed; fetch
it when needed, see AGENTS.md). Each IRI endpoint maps to an MCP
tool executed on AI4S over SSH via remotemanager — there is no REST service;
we emulate the API's shape and semantics.

**The verdicts below are specific to AI4S.** When porting to a new machine,
re-decide every row against what *that* machine can do — the same endpoint can be
implementable on one machine and not another (e.g. the `project_allocations`
endpoints are deferred here, but implementable on a machine with core-time
accounting like HOKUSAI BigWaterfall2's `listcpu`).

Legend: ✅ implemented · 🔜 planned next · ❌ deferred (with reason)

## facility

| IRI endpoint | Tool | Status | Notes |
|---|---|---|---|
| GET /facility | `get_facility` | ✅ | Static data from `server/rikyu_mcp/data/ai4s_config.json` |
| GET /facility/sites | — | ❌ | Single-site deployment; fold into `get_facility` if ever needed |
| GET /facility/sites/{site_id} | — | ❌ | Same |

## status

| IRI endpoint | Tool | Status | Notes |
|---|---|---|---|
| GET /status/resources | `get_resources` | ✅ | One resource (`ai4s`) with per-partition node summary from sinfo |
| GET /status/resources/{resource_id} | `get_resource` | ✅ | Per-partition node counts + drained nodes with reasons (`sinfo -R`) |
| GET /status/incidents | — | ❌ | No incident data source on AI4S; closest signal is drained nodes / maintenance reservations (`scontrol show reservation`) |
| GET /status/incidents/{id} | — | ❌ | Same |
| GET /status/events | — | ❌ | Same |
| GET /status/events/{id} | — | ❌ | Same |

## account

| IRI endpoint | Tool | Status | Notes |
|---|---|---|---|
| GET /account/capabilities | — | ❌ | No equivalent concept exposed on AI4S |
| GET /account/capabilities/{id} | — | ❌ | Same |
| GET /account/projects | `get_projects` | ✅ | `sacctmgr show associations user=$USER` |
| GET /account/projects/{id} | `get_project` | ✅ | Filter over `get_projects` |
| GET .../project_allocations | — | ❌ | AI4S early access has no allocation accounting yet |
| GET .../project_allocations/{id} | — | ❌ | Same |
| GET .../user_allocations | — | ❌ | Same |
| GET .../user_allocations/{id} | — | ❌ | Same |

## compute

| IRI endpoint | Tool | Status | Notes |
|---|---|---|---|
| POST /compute/job/{resource_id} | `submit_job` | ✅ | JobSpec → sbatch script (kept in `~/.rikyu/jobs/`); returns `{job_id, script_path}` — see deviation note below |
| PUT /compute/job/{rid}/{job_id} | `update_job` | ✅ | `scontrol update job`; time_limit works on running jobs; partition/account/reservation queued-only |
| GET /compute/status/{rid}/{job_id} | `get_job_status` | ✅ | Returns our `JobStatus` directly — see deviation note below |
| POST /compute/status/{rid} | `get_job_statuses` | ✅ | Batch; empty list = current user's last 2 days |
| DELETE /compute/cancel/{rid}/{job_id} | `cancel_job` | ✅ | scancel + post-cancel state report |

## filesystem

| IRI endpoint | Tool | Status | Notes |
|---|---|---|---|
| GET /filesystem/ls | `fs_ls` | ✅ | |
| GET /filesystem/stat | `fs_stat` | ✅ | |
| GET /filesystem/file | — | 🔜 | IRI generic file read; our `fs_view` covers this use-case; add as alias |
| GET /filesystem/view | `fs_view` | ✅ | 200KB cap; text only |
| GET /filesystem/head | `fs_head` | ✅ | |
| GET /filesystem/tail | `fs_tail` | ✅ | Primary way to read job output |
| POST /filesystem/mkdir | `fs_mkdir` | ✅ | |
| POST /filesystem/upload | `fs_upload` | ✅ | Text content via MCP (IRI uses multipart; binary deferred) |
| GET /filesystem/download | `fs_download` | ✅ | Base64-encoded content; 5 MB cap matching IRI spec; suggests scp for larger files |
| GET /filesystem/checksum | `fs_checksum` | ✅ | `sha256sum` |
| POST /filesystem/mv | `fs_mv` | ✅ | `mv`; docstring notes it is destructive |
| POST /filesystem/cp | `fs_cp` | ✅ | `cp -r` |
| DELETE /filesystem/rm | — | ❌ | Deliberately omitted (destructive); agent can use escape hatch with user confirmation |
| PUT /filesystem/chmod | `fs_chmod` | ✅ | `chmod` |
| PUT /filesystem/chown | `fs_chown` | ✅ | `chown`; group-only changes work for normal users |
| POST /filesystem/symlink | `fs_symlink` | ✅ | `ln -s` |
| POST /filesystem/compress | `fs_compress` | ✅ | `tar`; supports gzip/bzip2/xz/none + match_pattern via find |
| POST /filesystem/extract | `fs_extract` | ✅ | `tar -x` |

## task

| IRI endpoint | Tool | Status | Notes |
|---|---|---|---|
| GET /task/{task_id} | — | ❌ | IRI's async-task model queues REST ops; our SSH execution is synchronous, so `submit_job` returns `job_id` directly (see deviation). Revisit only if we add long-running server-side operations |
| DELETE /task/{task_id} | — | ❌ | Same |
| GET /task | — | ❌ | Same |

---

## Known deviations from the IRI/PSI-J schemas

Verified against the ALCF IRI spec (fetched 2026-06-12 from api.alcf.anl.gov/openapi.json).

### JobAttributes

| Field | IRI | Ours | Action |
|---|---|---|---|
| `duration` | **integer seconds** | HH:MM:SS string | 🔜 Accept both; convert string→seconds before rendering sbatch, accept int as-is |
| `account` | `account` | `project_name` | 🔜 Rename field to `account` |
| `reservation_id` | present | absent | 🔜 Add; maps to `--reservation` sbatch flag |

### ResourceSpec

| Field | IRI | Ours | Action |
|---|---|---|---|
| `node_count` | present | present ✅ | — |
| `processes_per_node` | present | present ✅ | — |
| `process_count` | present (total processes) | absent | 🔜 Add; alternative to `processes_per_node × node_count` |
| `cpu_cores_per_process` | present | present ✅ | — |
| `gpu_cores_per_process` | present (PSI/J standard) | absent | 🔜 Add as alias/fallback; AI4S uses `gpus_per_node` |
| `gpus_per_node` | absent (AI4S extension) | present | Keep — maps to `--gpus-per-node`; document as extension |
| `exclusive_node_use` | present | absent | 🔜 Add; maps to `--exclusive` |
| `memory` | present (bytes) | absent | 🔜 Add; maps to `--mem` (convert bytes → MB for sbatch) |

### JobSpec

| Field | IRI | Ours | Action |
|---|---|---|---|
| `executable` | present | present ✅ | — |
| `arguments` | present | present ✅ | — |
| `directory` | present | present ✅ | — |
| `name` | present | present ✅ | — |
| `environment` | present | present ✅ | — |
| `stdout_path` | present | present ✅ | — |
| `stderr_path` | present | present ✅ | — |
| `resources` | present | present ✅ | — |
| `attributes` | present | present ✅ | — |
| `inherit_environment` | present | absent | 🔜 Add; default true for sbatch |
| `stdin_path` | present | absent | 🔜 Add; maps to `--input` |
| `pre_launch` | present (script before job) | absent | 🔜 Add; prepend to sbatch script body |
| `post_launch` | present (script after job) | absent | 🔜 Add; append to sbatch script body |
| `launcher` | present (e.g. `srun`, `mpirun`) | absent | 🔜 Add; prepend to `executable` in script |
| `container` | present (Container: image + mounts) | present ✅ | Singularity 4.3.7 on AI4S; `--nv` added when GPUs requested; launcher placed outside singularity exec |

### JobState

IRI values are **lowercase**: `new`, `queued`, `held`, `active`, `completed`, `failed`, `canceled`.
Ours are uppercase: `QUEUED`, `ACTIVE`, `COMPLETED`, `FAILED`, `CANCELED`, `UNKNOWN`.
🔜 Align to lowercase. Also add `new` (job submitted, not yet queued) and `held` states.

### JobStatus / Job response shape

IRI's `JobStatus` schema: `{state, time (epoch float), message, exit_code, meta_data}`.
IRI's `Job` schema (returned by getJob/getJobs): `{id, status: JobStatus, job_spec: JobSpec-Output}`.

Ours returns a flat `JobStatus` with richer Slurm fields (`native_state`, `name`, `partition`,
`elapsed`, `start_time`, `end_time`, `nodes`, `workdir`, `reason`).

🔜 Align response shape: return `Job` wrapper from `get_job_status`/`get_job_statuses`. Map our
rich fields into `meta_data`. Use epoch float for `time` (use `start_time` or `end_time`).

### submit_job return value

IRI returns `TaskSubmitResponse {task_id, task_uri}` because ALCF queues REST operations
as async tasks. Our SSH execution is synchronous — sbatch completes before we return —
so we return `{job_id, script_path}` directly. No task polling needed.

This is an intentional deviation. Document it clearly to callers.

### resource_id

Accepted and validated in all compute/filesystem tools but there is a single resource: `ai4s`.
