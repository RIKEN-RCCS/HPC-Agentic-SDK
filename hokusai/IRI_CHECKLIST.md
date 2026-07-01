# IRI Facility API coverage checklist

Tracks how far `hokusai-hpc` covers the [IRI Facility API](https://api.alcf.anl.gov/)
(ALCF implementation, spec at api.alcf.anl.gov/openapi.json — not committed; fetch
it when needed, see AGENTS.md). Each IRI endpoint maps to an MCP
tool executed on HBW2 over SSH via remotemanager — there is no REST service;
we emulate the API's shape and semantics.

**The ✅/🔜/❌ verdicts below are specific to HBW2.** They are not inherited from
the machine this plugin was ported from — each was re-decided against what HBW2
can actually do. The same endpoint can be implementable on one machine and not
another (e.g. the `project_allocations` endpoints are deferred on AI4S, which has
no allocation accounting, but implementable on HBW2 via `listcpu`). When porting
to a new machine, re-decide every row from scratch.

Legend: ✅ implemented · 🔜 planned next · ❌ deferred (with reason)

## facility

| IRI endpoint | Tool | Status | Notes |
|---|---|---|---|
| GET /facility | `get_facility` | ✅ | Static data from `data/hokusai_config.json` |
| GET /facility/sites | — | ❌ | Single-site deployment; fold into `get_facility` if ever needed |
| GET /facility/sites/{site_id} | — | ❌ | Same |

## status

| IRI endpoint | Tool | Status | Notes |
|---|---|---|---|
| GET /status/resources | `get_resources` | ✅ | One resource (`hokusai`) with per-partition node summary from sinfo |
| GET /status/resources/{resource_id} | `get_resource` | ✅ | Per-partition node counts + drained nodes with reasons (`sinfo -R`) |
| GET /status/incidents | — | ❌ | No incident data source on HBW2; closest signal is drained nodes / maintenance reservations (`scontrol show reservation`) |
| GET /status/incidents/{id} | — | ❌ | Same |
| GET /status/events | — | ❌ | Same |
| GET /status/events/{id} | — | ❌ | Same |

## account

| IRI endpoint | Tool | Status | Notes |
|---|---|---|---|
| GET /account/capabilities | — | ❌ | No equivalent concept exposed on HBW2 |
| GET /account/capabilities/{id} | — | ❌ | Same |
| GET /account/projects | `get_projects` | ✅ | `sacctmgr show associations user=$USER` |
| GET /account/projects/{id} | `get_project` | ✅ | Filter over `get_projects` |
| GET .../project_allocations | — | 🔜 | **Re-decided for HBW2 (was ❌ on AI4S).** HBW2 exposes per-project core-time budgets via `listcpu -p <project>` (per-subsystem Used/Limit hours + expiry) — implementable. Verify live `listcpu` output before writing the parser. |
| GET .../project_allocations/{id} | — | 🔜 | Same `listcpu` source, single allocation (per subsystem: mpc/lmc/gpu) |
| GET .../user_allocations | — | 🔜 | `listcpu -p <project>` also lists per-user usage rows |
| GET .../user_allocations/{id} | — | 🔜 | Same |

## compute

| IRI endpoint | Tool | Status | Notes |
|---|---|---|---|
| POST /compute/job/{resource_id} | `submit_job` | ✅ | JobSpec → sbatch script (kept in `~/.hokusai/jobs/`); returns `{job_id, script_path}` — see deviation note below |
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
| POST /filesystem/upload | `fs_upload` | ⚠️ deviation | **Deliberately diverges from the IRI multipart shape.** `fs_upload(path, local_path)` transfers local→remote via rsync (scp fallback if rsync < 3.0) and returns metadata `{remote_path, bytes, sha256, verified, transport}`. No size limit. IRI's multipart body would route file bytes through the MCP tool input. |
| GET /filesystem/download | `fs_download` | ⚠️ deviation | **Deliberately diverges from the IRI base64 shape.** `fs_download(path, local_path=None)` transfers remote→local via rsync (scp fallback if rsync < 3.0) and returns metadata `{local_path, bytes, sha256, verified, transport}`. No size limit. IRI returns base64 in the response body; routing bytes through the model context fails past ~12 KB (0.9 tokens/byte × 10k-token tool cap). |
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
| `gpu_cores_per_process` | present (PSI/J standard) | absent | ✅ Added as fallback; HBW2 uses `gpus` |
| `gpus` | absent (HBW2 extension) | present | Keep — maps to `--gpus` (GPU server only); GPUs are optional on this CPU-first machine |
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
| `container` | present (Container: image + mounts) | present ✅ | Singularity on HBW2; `--nv` added when GPUs requested; launcher placed outside singularity exec |

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

Accepted and validated in all compute/filesystem tools but there is a single resource: `hokusai`.
