---
name: fugaku-monitoring-jobs
description: Check PJM job status, output, and queue/quota info on Fugaku.
---

# Monitor Fugaku jobs

- Call `get_job_status` for one job ID, or `get_job_statuses([])` for the
  current user's live queue merged with recent (up to 90-day) history.
- PJM's `ST` codes map as: `ACC`/`QUE` → queued, `HLD`/`SPD`/`SPP` → held,
  `RNP`/`RUN`/`RNA`/`RNE`/`RNO`/`RSM` → active, `EXT` → completed, `CCL` →
  canceled, `ERR`/`RJT` → failed.
- **`EXT` (completed) only means the scheduler finished the job** — PJM's
  live status table has no exit-code column. Always read the job's
  `<name>.<job_id>.out`/`.err` file (`fs_tail`/`fs_view` under
  `~/agent/jobs/`) to confirm the program actually succeeded.
- For quota/limit questions, use
  `run_command_on_cluster("pjstat --limit")` (concurrent-job and node/core
  quotas) or `run_command_on_cluster("pjacl --rg <name>")` (a resource
  group's node/elapse limits for this account).
- `get_resources` returns raw `pjstat --rsc`/`pjshowrsc` output — these
  commands did not return usable per-partition occupancy data during this
  port's live testing, so treat that field as best-effort text, not
  structured data; the resource-group node/time limits in `get_facility`
  are the more reliable static reference.
- To cancel, call `cancel_job`; to change a still-queued job's wall time,
  call `update_job` with `time_limit` (uses `pjalter`).
