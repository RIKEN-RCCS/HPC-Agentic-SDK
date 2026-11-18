---
name: rikyu-monitoring-jobs
description: Use when the user asks about the status, progress, output, history, or failure of jobs on RIKYU (RIKEN AI4S / GB200), or about queue and node availability. Also use this any time you (the agent) need to check on or wait for a job you submitted, even without a fresh user request.
user-invocable: true
---

# Monitoring jobs on RIKYU (RIKEN AI4S / GB200)

Every tool call in this skill uses `facility="rikyu"`.

## Status checks (same tools and semantics everywhere)

Use these tools even when you're checking in on your own initiative — don't
fall back to `run_command_on_cluster` with raw `squeue`/`sacct` just
because there's no new user message prompting it; the tools below return
the same information normalized, plus any facility-specific lag/quirk
handling noted below.

- **One job**: `get_job_status(facility="rikyu", job_id=...)` — `state`
  is normalized (`queued`/`active`/`completed`/`failed`/`canceled`/`held`/
  `unknown`); `meta_data.native_state` is the scheduler's own. A queued
  job's `message` explains the wait.
- **My recent jobs**: `get_job_statuses(facility="rikyu", job_ids=[])`
  for roughly the last two days, or pass specific IDs.
- **Cluster availability**: `get_resources(facility="rikyu")` —
  per-partition allocated/idle/other/total node counts. Idle nodes can
  start jobs immediately.
- **Reading a job's output**: the file is `slurm-<job_id>.out` inside the
  directory the job ran in. **Get that directory from the job's own status
  record** (`meta_data.workdir`) rather than assuming `$HOME` — a job whose
  spec set `directory` writes its output there, not in the home directory.
  Then read it with `fs_tail(facility="rikyu", path=...)` for a running
  job, or `fs_view` once it has finished.

## RIKYU failure modes and triage

- **x86_64 binary on aarch64 nodes** → "Exec format error" in output.
- **OOM** → `native_state` OUT_OF_MEMORY; the fix is requesting more GPUs
  (each one brings 36 more CPU cores and ~400GB more memory as a fixed
  bundle — you can't raise memory independently of GPU count).
- **Time limit** → `native_state` TIMEOUT; raise `duration` (max 96h —
  there's no longer-running exception).
- **Lost scratch output** → results written to `/tmp` on the compute node
  but not copied back to `/home/<user>` or `/data1/<group>` before the job
  ended are unrecoverable.

The exact script that was submitted is kept in `~/agent/jobs/` —
`fs_view(facility="rikyu", path=...)` it when debugging.

## Live GPU utilization

For an ACTIVE job, check GPU usage on its node with:
`run_command_on_cluster(facility="rikyu", command="srun --overlap --jobid <id> nvidia-smi")`

Low utilization usually means a dataloader/CPU bottleneck or the job is
still in setup.

## Cancelling and updating

- `cancel_job(facility="rikyu", job_id=...)` — **confirm with the user
  before calling this.**
- `update_job(facility="rikyu", job_id=..., spec={...})` — pass a
  JobSpec containing only what should change, e.g.
  `{"attributes": {"duration": "02:00:00"}}`. Only fields a scheduler can
  change after submission are applied (job name, wall time, partition,
  account, reservation, node count); anything else you set is reported back
  as not applied. Only affects jobs still queued or running.

## Polling until done, from a notebook

Interactively, just call `get_job_status` again after a pause. If you're
writing a reproducible notebook instead (see `rikyu-reproducing`), use
`hpc_agent_core.client`'s `wait_for_job(job_id, facility="rikyu")`
rather than a hand-rolled polling loop.

Don't guess facility-specific failure modes beyond what's noted above — use
`search_docs(facility="rikyu", query=...)` on the `hpc-docs` server.
