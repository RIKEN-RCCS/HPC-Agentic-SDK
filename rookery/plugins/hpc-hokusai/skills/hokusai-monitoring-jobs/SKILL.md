---
name: hokusai-monitoring-jobs
description: Use when the user asks about the status, progress, output, history, or failure of jobs on HOKUSAI BigWaterfall2 (HBW2), or about queue and node availability. Also use this any time you (the agent) need to check on or wait for a job you submitted, even without a fresh user request.
user-invocable: true
---

# Monitoring jobs on HOKUSAI BigWaterfall2 (HBW2)

Every tool call in this skill uses `facility="hokusai"`.

## Status checks (same tools and semantics everywhere)

Use these tools even when you're checking in on your own initiative — don't
fall back to `run_command_on_cluster` with raw `squeue`/`sacct` just
because there's no new user message prompting it; the tools below return
the same information normalized, plus any facility-specific lag/quirk
handling noted below.

- **One job**: `get_job_status(facility="hokusai", job_id=...)` — `state`
  is normalized (`queued`/`active`/`completed`/`failed`/`canceled`/`held`/
  `unknown`); `meta_data.native_state` is the scheduler's own. A queued
  job's `message` explains the wait.
- **My recent jobs**: `get_job_statuses(facility="hokusai", job_ids=[])`
  for roughly the last two days, or pass specific IDs.
- **Cluster availability**: `get_resources(facility="hokusai")` —
  per-partition allocated/idle/other/total node counts. Idle nodes can
  start jobs immediately.
- **Reading a job's output**: the file is `slurm-<job_id>.out` inside the
  directory the job ran in. **Get that directory from the job's own status
  record** (`meta_data.workdir`) rather than assuming `$HOME` — a job whose
  spec set `directory` writes its output there, not in the home directory.
  Then read it with `fs_tail(facility="hokusai", path=...)` for a running
  job, or `fs_view` once it has finished.

## Fair-share is why a job waits

HBW2 orders jobs by **fair-share priority**, so a job can sit queued
because your project's recent usage is high, not because the cluster is
full. When a job is waiting, check both:

- `get_projects(facility="hokusai")` — your fair-share standing and raw
  usage per account (read live; it moves continuously).
- `get_resources(facility="hokusai")` — live partition occupancy.

## HBW2 failure modes and triage

- **No project / core-time exhausted** — check
  `get_projects(facility="hokusai")`; a project's new jobs stop starting
  once its allowance is spent.
- **Out of memory** (`native_state` OUT_OF_MEMORY) — raise the memory
  share, or move to the `lmc` partition (2.7 TiB nodes).
- **Hit wall time** (`native_state` TIMEOUT) — raise `duration`, or move
  from `mpc` (~24 h) to `mpc_l` (~72 h).
- **Threads unset** — not an error, a silent performance collapse: set
  `OMP_NUM_THREADS` to match `resources.cpu_cores_per_process`.
- **Conflicting MPI modules** — Intel MPI and Open MPI loaded together.
  Load one only; `module purge` before switching.
- **Exit 127, `error while loading shared libraries`** — the run job is
  missing a `module load` that the build used (MKL, Intel MPI); job shells
  start with a clean environment, so repeat the module loads at runtime.

Read the job's output and its `status.meta_data.native_state` together to
tell which of these it is. The exact submitted script is kept in
`~/agent/jobs/` — `fs_view(facility="hokusai", path=...)` it when
debugging.

## Cancelling and updating

- `cancel_job(facility="hokusai", job_id=...)` — **confirm with the user
  before calling this.**
- `update_job(facility="hokusai", job_id=..., spec={...})` — pass a
  JobSpec containing only what should change, e.g.
  `{"attributes": {"duration": "02:00:00"}}`. Only fields a scheduler can
  change after submission are applied (job name, wall time, partition,
  account, reservation, node count); anything else you set is reported back
  as not applied. Only affects jobs still queued or running.

## Polling until done, from a notebook

Interactively, just call `get_job_status` again after a pause. If you're
writing a reproducible notebook instead (see `hokusai-reproducing`), use
`hpc_agent_core.client`'s `wait_for_job(job_id, facility="hokusai")`
rather than a hand-rolled polling loop.

Don't guess facility-specific failure modes beyond what's noted above — use
`search_docs(facility="hokusai", query=...)` on the `hpc-docs` server.
