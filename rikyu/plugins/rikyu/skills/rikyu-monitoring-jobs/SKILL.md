---
name: rikyu-monitoring-jobs
description: Use when the user asks about the status, progress, output, history, or failure of jobs on the Rikyu supercomputer, or about queue and node availability.
---

# Monitoring jobs on the Rikyu supercomputer

## Status checks

- **One job**: `get_job_status` — `state` is normalized (QUEUED/ACTIVE/COMPLETED/FAILED/CANCELED); `native_state` is Slurm's. A QUEUED job's `reason` field says why it waits (`Resources`, `Priority`, …).
- **My recent jobs**: `get_job_statuses` with an empty list (last 2 days), or pass specific IDs.
- **Cluster availability**: `get_resources` — per-partition allocated/idle/other/total node counts. Idle nodes can start jobs immediately.

## Job output and failure triage

1. Stdout/stderr default to `<workdir>/slurm-<job_id>.out` (workdir is in the status record). Read with `fs_tail` (or `fs_head`/`fs_view`).
2. Common Rikyu failure modes:
   - **x86_64 binary on aarch64 nodes** → "Exec format error" in output.
   - **OOM** → `native_state` OUT_OF_MEMORY; the fix is requesting more GPUs (each one brings 36 more CPU cores and ~400GB more memory as a fixed bundle — you can't raise memory independently of GPU count).
   - **Time limit** → `native_state` TIMEOUT; raise `duration` (max 96h — there's no longer-running exception).
   - **Lost scratch output** → results written to `/tmp` on the compute node but not copied back to `/home/<user>` or `/data1/<group>` before the job ended are unrecoverable.
3. The exact script that was submitted is kept in `~/.rikyu/jobs/` — `fs_view` it when debugging.

## Live GPU utilization

For an ACTIVE job, check GPU usage on its node with:
`run_command_on_cluster("srun --overlap --jobid <id> nvidia-smi")`

Low utilization usually means a dataloader/CPU bottleneck or the job is still in setup.
