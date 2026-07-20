---
name: rccs-cloud-monitoring-jobs
description: Use when the user asks about the status, progress, output, history, or failure of jobs on the R-CCS Cloud, or about queue and node availability. Also use this any time you (the agent) need to check on or wait for a job you submitted, even without a fresh user request — e.g. polling a running job until it completes.
---

# Monitoring jobs on the R-CCS Cloud

If the user asks about scheduler policies, partition limits, module names, or
storage paths (rather than a specific live job), call `search_docs`
(rccs-cloud-docs) first. If it's unavailable or unhelpful, use the inline facts
below and note that docs were unavailable.

## Status checks

Use these tools even when you're checking in on your own — don't fall back to
`run_command_on_cluster("squeue ...")` / raw `sacct` just because there's no
new user message prompting it; they return the same info un-normalized and
without the sacct-lag handling below.

- **One job**: `get_job_status` — `state` is normalized (queued/active/completed/
  failed/canceled); `meta_data.native_state` is Slurm's. A queued job's
  `message` says why it waits (`Resources`, `Priority`, …).
- **My recent jobs**: `get_job_statuses` with an empty list (last ~2 days), or
  pass specific IDs.
- **Cluster availability**: `get_resources` — per-partition allocated/idle/
  other/total node counts. Idle nodes can start jobs immediately.

> **sacct lag**: this cluster's `sacct` trails `sbatch` by a second or two, so
> `get_job_status` fired *immediately* after `submit_job` can briefly report the
> job as not found. It's transient — wait a few seconds and query again (or use
> `get_job_statuses([id])`, which returns an empty list rather than erroring).

## Job output and failure triage

1. Stdout/stderr default to `<workdir>/slurm-<job_id>.out` (workdir is in the
   status record's `meta_data`). Read with `fs_tail` (or `fs_head`/`fs_view`).
2. Common R-CCS Cloud failure modes:
   - **Wrong architecture binary** → "Exec format error". x86_64 binaries sent
     to fx700, qc-gh200, or ng-dgx fail immediately; recompile for the target arch.
   - **Missing/wrong system module** → command not found or link errors. Check
     `module load system/<partition>` is the first thing in `executable`.
   - **OOM** → `native_state` OUT_OF_MEMORY; reduce ranks, set `resources.memory`,
     or move to a larger-memory partition (genoa-m).
   - **Time limit** → `native_state` TIMEOUT; raise `duration` (ai-h100l-pu caps at 30 min).
   - **GPU not allocated** → `nvidia-smi`/`rocm-smi` finds no devices. Set
     `resources.gpus` on partitions that need `--gpus=<n>` (not on superchips).
   - **Wrong-partition module** → wrong ABI/segfaults. Match the `system/<partition>`
     module to the partition the job ran on.
3. The exact submitted script is kept in `~/agent/jobs/` — `fs_view` it when debugging.

## Live job inspection

For an ACTIVE job on a GPU partition:
`run_command_on_cluster("srun --overlap --jobid <id> nvidia-smi")` (NVIDIA)
`run_command_on_cluster("srun --overlap --jobid <id> rocm-smi")` (AMD ROCm)
