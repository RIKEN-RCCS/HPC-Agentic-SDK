# IRI Facility API coverage — Fugaku

Endpoint-by-endpoint record for `server/fugaku_mcp/hpc_server.py`. See
[hpc-agent-core's own `IRI_CHECKLIST.md`](https://github.com/william-dawson/hpc-agent-core/blob/main/IRI_CHECKLIST.md)
for how each IRI capability group maps onto core's primitives; this file
only records Fugaku-specific verdicts.

## Facility

| IRI endpoint | Tool | Status | Notes |
|---|---|---|---|
| GET /facility | `get_facility` | implemented | Static data from `data/fugaku_config.json` (resource groups, storage tiers, modules, login) |

## Status

| IRI endpoint | Tool | Status | Notes |
|---|---|---|---|
| GET /status/resources | `get_resources` | partial | Returns raw `pjstat --rsc` / `pjshowrsc` output, not a parsed structure — both commands returned only a header row with no occupancy data for every account/flag combination tried during this port; fabricating a parser for a shape never actually observed would be worse than being honest about it. `get_facility`'s static resource-group limits and `pjacl --rg <name>` (via `run_command_on_cluster`) are the reliable alternatives. |
| GET /status/resources/{resource_id} | `get_resource` | partial | Same as above. |
| incidents/events | — | deferred | No public incident feed in the reviewed docs. |

## Account

| IRI endpoint | Tool | Status | Notes |
|---|---|---|---|
| GET /account/projects | — | deferred | PJM has no per-account project-listing command found in the docs beyond `id` (Unix group membership) and `pjacl`/`pjstat --limit` (quota introspection, not a project directory). `run_command_on_cluster("id")` is the documented workaround — see the guide and skills. |
| allocations | — | deferred | No CPU-hour/allocation ledger command found; only concurrent-job/node/core quotas via `pjstat --limit`. |

## Compute

| IRI endpoint | Tool | Status | Notes |
|---|---|---|---|
| POST /compute/job/{resource_id} | `submit_job` | implemented | JobSpec → PJM script under `~/agent/jobs`, submitted by `pjsub`. Rejects GPU requests and custom stdout/stderr paths (PJM supports neither). |
| PUT /compute/job/{rid}/{job_id} | `update_job` | partial | Elapse-time change only, via `pjalter -L "elapse=..."`; other fields (resource group, node count, project group) rejected — matches what `pjalter` reliably changes on a still-queued job. |
| GET /compute/status/{rid}/{job_id} | `get_job_status` | implemented | `pjstat <id>`; finished-job fallback via `pjstat --history day=90`. A completed (`EXT`) job's `message` notes that pjstat exposes no application exit code — callers must check the job's output file. |
| POST /compute/status/{rid} | `get_job_statuses` | implemented | Batch lookup; empty list returns the live queue merged with recent history. |
| DELETE /compute/cancel/{rid}/{job_id} | `cancel_job` | implemented | `pjdel`, then re-queries status. |

## Filesystem

Implemented using the shared agent pattern over shell commands plus
remotemanager transfer: `fs_ls`, `fs_stat`, `fs_view`, `fs_head`, `fs_tail`,
`fs_mkdir`, `fs_upload`, `fs_download`, `fs_checksum`, `fs_cp`, `fs_mv`,
`fs_chmod`, `fs_chown`, `fs_symlink`, `fs_compress`, and `fs_extract`. `rm`
is intentionally omitted as a destructive tool.

## Known deviations

- `submit_job` returns `{job_id, script_path, submission_output}` directly
  instead of an async task.
- `fs_upload`/`fs_download` use local file paths and rsync/scp rather than
  routing file bytes through MCP payloads.
- Fugaku has no GPUs; any tool implying GPU capability is not exposed.
- `update_job` supports only elapse-time changes.
- `get_resources`/`get_resource` return raw scheduler text rather than a
  parsed occupancy structure — see "Status" above.

## Extensions (not part of the IRI API)

- `run_command_on_cluster` — arbitrary shell command on the login node.
  Documented as the way to reach `id` (project groups), `pjacl --rg <name>`
  (resource-group limits), `pjstat --limit` (quotas), and `module avail`
  (software), none of which have a dedicated structured tool.
