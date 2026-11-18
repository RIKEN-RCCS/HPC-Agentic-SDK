---
name: rccs-cloud-monitoring-jobs
description: Use when the user asks about the status, progress, output, history, or failure of jobs on R-CCS Cloud, or about queue and node availability. Also use this any time you (the agent) need to check on or wait for a job you submitted, even without a fresh user request.
user-invocable: true
---

# Monitoring jobs on R-CCS Cloud

Every tool call in this skill uses `facility="rccs-cloud"`.

## Status checks (same tools and semantics everywhere)

Use these tools even when you're checking in on your own initiative — don't
fall back to `run_command_on_cluster` with raw `squeue`/`sacct` just
because there's no new user message prompting it; the tools below return
the same information normalized, plus any facility-specific lag/quirk
handling noted below.

- **One job**: `get_job_status(facility="rccs-cloud", job_id=...)` — `state`
  is normalized (`queued`/`active`/`completed`/`failed`/`canceled`/`held`/
  `unknown`); `meta_data.native_state` is the scheduler's own. A queued
  job's `message` explains the wait.
- **My recent jobs**: `get_job_statuses(facility="rccs-cloud", job_ids=[])`
  for roughly the last two days, or pass specific IDs.
- **Cluster availability**: `get_resources(facility="rccs-cloud")` —
  per-partition allocated/idle/other/total node counts. Idle nodes can
  start jobs immediately.
- **Reading a job's output**: the file is `slurm-<job_id>.out` inside the
  directory the job ran in. **Get that directory from the job's own status
  record** (`meta_data.workdir`) rather than assuming `$HOME` — a job whose
  spec set `directory` writes its output there, not in the home directory.
  Then read it with `fs_tail(facility="rccs-cloud", path=...)` for a running
  job, or `fs_view` once it has finished.

> **sacct lag** (handled for you now): this cluster's `sacct` trails
> `sbatch` by a second or two, so `get_job_status` fired *immediately*
> after `submit_job` used to report the job as not found. `get_statuses`
> now falls back to `scontrol` for any id sacct doesn't yet know, which
> closes that window — a just-submitted job reports `queued` right away.
> No wait-and-retry needed; if you *do* still see "not found", treat it as
> a real unknown job id rather than a timing artifact.

## R-CCS Cloud failure modes and triage

- **Wrong architecture binary** → "Exec format error". x86_64 binaries
  sent to fx700, qc-gh200, or ng-dgx fail immediately; recompile for the
  target arch.
- **Missing/wrong system module** → command not found or link errors.
  Check `module load system/<partition>` is the first thing in
  `executable`.
- **OOM** → `native_state` OUT_OF_MEMORY; reduce ranks, set
  `resources.memory`, or move to a larger-memory partition (genoa-m).
- **Time limit** → `native_state` TIMEOUT; raise `duration` (ai-h100l-pu
  caps at 30 min).
- **GPU not allocated** → `nvidia-smi`/`rocm-smi` finds no devices. Set
  `resources.gpus` on partitions that need `--gpus=<n>` (not on
  superchips).
- **Wrong-partition module** → wrong ABI/segfaults. Match the
  `system/<partition>` module to the partition the job ran on.

The exact submitted script is kept in `~/agent/jobs/` —
`fs_view(facility="rccs-cloud", path=...)` it when debugging.

## Live job inspection

For an ACTIVE job on a GPU partition:
`run_command_on_cluster(facility="rccs-cloud", command="srun --overlap --jobid <id> nvidia-smi")` (NVIDIA)
`run_command_on_cluster(facility="rccs-cloud", command="srun --overlap --jobid <id> rocm-smi")` (AMD ROCm)

## Cancelling and updating

- `cancel_job(facility="rccs-cloud", job_id=...)` — **confirm with the user
  before calling this.**
- `update_job(facility="rccs-cloud", job_id=..., spec={...})` — pass a
  JobSpec containing only what should change, e.g.
  `{"attributes": {"duration": "02:00:00"}}`. Only fields a scheduler can
  change after submission are applied (job name, wall time, partition,
  account, reservation, node count); anything else you set is reported back
  as not applied. Only affects jobs still queued or running.

## Polling until done, from a notebook

Interactively, just call `get_job_status` again after a pause. If you're
writing a reproducible notebook instead (see `rccs-cloud-reproducing`), use
`hpc_agent_core.client`'s `wait_for_job(job_id, facility="rccs-cloud")`
rather than a hand-rolled polling loop.

Don't guess facility-specific failure modes beyond what's noted above — use
`search_docs(facility="rccs-cloud", query=...)` on the `hpc-docs` server.
