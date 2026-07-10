# IRI Facility API coverage — HOKUSAI (HBW2)

Which [IRI Facility API](https://api.alcf.anl.gov/openapi.json) endpoints this
plugin implements, defers, or extends, and why. This is machine-specific: an
endpoint sensible on HBW2 may not apply elsewhere, so it stays here rather
than in `hpc-agent-core`. Tools live in `server/hokusai_mcp/hpc_server.py`.

## Implemented

| IRI endpoint | Tool | Notes |
|---|---|---|
| `GET /facility` | `get_facility` | Static facts from `data/hokusai_config.json`. |
| `GET /resources` | `get_resources` | Live per-partition occupancy via `sinfo`. |
| `GET /resources/{id}` | `get_resource` | One partition by name. |
| `GET /projects` | `get_projects` | `sacctmgr` associations + `sshare` fair-share. HBW2 has real accounting. |
| `GET /projects/{id}` | `get_project` | One account by ID. |
| `POST /compute/jobs` | `submit_job` | Applies HBW2 defaults (partition `mpc`, configured account) first. |
| `GET /compute/jobs/{id}` | `get_job_status` | Via `sacct`. |
| `GET /compute/jobs` | `get_job_statuses` | Batch; empty list → recent jobs (last ~2 days). |
| `DELETE /compute/jobs/{id}` | `cancel_job` | `scancel`, then re-read state. |
| `PATCH /compute/jobs/{id}` | `update_job` | `scontrol` hold/release and time-limit change (a pragmatic subset of a full attribute patch). |
| `GET /storage` (listing/metadata) | `fs_ls`, `fs_stat` | |
| `GET /storage` (content) | `fs_view`, `fs_head`, `fs_tail`, `fs_download` | |
| `PUT /storage` | `fs_upload`, `fs_mkdir` | Checksum-verified transfers. |
| storage mutations | `fs_cp`, `fs_mv`, `fs_chmod`, `fs_chown`, `fs_symlink` | |
| `POST /storage` checksum | `fs_checksum` | sha256 / md5. |
| compression | `fs_compress`, `fs_extract` | IRI `CompressionType` (none/gzip/bzip2/xz). |

## Extensions (no IRI counterpart)

| Tool | Why |
|---|---|
| `get_drained_nodes` | Drained/down nodes + reasons — explains capacity gaps a bare resource list doesn't. |
| `render_job_script` | Preview the sbatch script before submitting — supports the "show before you run" rule. |
| `read_job_output` | Read a job's `slurm-<id>.out` console log; the guide highlights this as a key troubleshooting step. |
| `run_command_on_cluster` | Escape hatch for arbitrary login-node commands. Show the command to the user first; never run heavy compute on the login node. |

## Deferred / not applicable

- **Multiple facilities** (`GET /facilities`) — this plugin serves exactly one
  machine; the marketplace lists it.
- **Reservations as first-class endpoints** — reservations are supported only
  as a `JobAttributes.reservation_id` passed through to `--reservation`, not
  as their own create/list tools (no evidence HBW2 exposes user-facing
  reservation management through the agent).
- **A `Scheduler` selector** — HBW2 is single-scheduler (Slurm only), so
  `JobAttributes.scheduler` is left unused.
- **Storage allocation management** (`/data/<projectID>` provisioning) — done
  through the HBW2 portal and charged per project, not via the scheduler API;
  out of scope for the agent.
