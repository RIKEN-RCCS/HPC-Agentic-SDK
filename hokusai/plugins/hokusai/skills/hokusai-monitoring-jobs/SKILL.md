---
name: hokusai-monitoring-jobs
description: Track and troubleshoot jobs on HOKUSAI BigWaterfall2 (HBW2). Use when the user asks about a job's status, why a job is waiting, wants to cancel a job, read its console output, or diagnose a failed job.
---

# Monitoring jobs on HOKUSAI (HBW2)

HBW2 has full Slurm accounting, so status and recent history come from the
scheduler live.

## Status

- `get_job_status(job_id)` — one job's normalized state (queued / active /
  completed / failed / canceled) plus scheduler detail (partition, nodes,
  elapsed, exit code) in `meta_data`.
- `get_job_statuses([...])` — several jobs at once; with an **empty list**,
  your recent jobs (last ~2 days).
- For a queued job, `status.message` carries the wait reason. HBW2 orders
  jobs by **fair-share priority**, so a job can wait because your project's
  recent usage is high, not because the cluster is full — check
  `get_projects` for your fair-share standing and `get_resources` for live
  occupancy.

## Console output

`read_job_output(job_id)` reads `slurm-<jobid>.out` from the directory the
job was launched from. Pass `tail_lines=N` for just the tail of a long or
still-running job.

## Canceling

`cancel_job(job_id)` sends scancel and reports the resulting state.

## Modifying

`update_job(job_id, hold=True|False, time_limit="HH:MM:SS")` holds/releases a
pending job or changes its wall-time limit (subject to partition maxima).

## Diagnosing a failure

When a job misbehaves it's usually one of:

- **No project / core-time exhausted** — check `get_projects`; the project's
  new jobs stop starting when its allowance is spent.
- **Out of memory** (native state `OUT_OF_MEMORY`) — raise the memory share
  or move to `lmc`.
- **Hit wall time** (`TIMEOUT`) — raise `duration` or use `mpc_l`.
- **Threads unset** — performance collapse; set `OMP_NUM_THREADS`.
- **Conflicting MPI modules** — Intel MPI and Open MPI loaded together; load
  one only.

Read the job's `read_job_output` and its `status.meta_data.native_state` to
point at which.
