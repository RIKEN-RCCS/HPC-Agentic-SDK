---
name: rccs-cloud-monitoring-jobs
description: Use when the user asks about the status, progress, output, history, or failure of jobs on the R-CCS Cloud, or about queue and node availability.
---

# Monitoring jobs on the R-CCS Cloud

If the user asks about scheduler policies, partition limits, module names, or
storage paths (rather than a specific live job), call `search_docs`
(rccs-cloud-docs) first. If `search_docs` is unavailable or returns nothing
useful, use the inline facts below and note that docs were unavailable.

## Status checks

- **One job**: `get_job_status` — `state` is normalized (QUEUED/ACTIVE/COMPLETED/FAILED/CANCELED); `native_state` is Slurm's. A QUEUED job's `reason` field says why it waits (`Resources`, `Priority`, …).
- **My recent jobs**: `get_job_statuses` with an empty list (last 2 days), or pass specific IDs.
- **Cluster availability**: `get_resources` — per-partition allocated/idle/other/total node counts. Idle nodes can start jobs immediately.

## Job output and failure triage

1. Stdout/stderr default to `<workdir>/slurm-<job_id>.out` (workdir is in the status record). Read with `fs_tail` (or `fs_head`/`fs_view`).
2. Common R-CCS Cloud failure modes:
   - **Wrong architecture binary** → "Exec format error" in output. x86_64 binaries submitted to fx700, qc-gh200, or ng-dgx will fail immediately; recompile for the target arch.
   - **Missing or wrong system module** → command not found, linking errors, or silent wrong-library use. Check that `module load system/<partition>` is the first line of executable.
   - **OOM** → `native_state` OUT_OF_MEMORY; reduce ranks, request a larger-memory partition, or set `resources.memory`.
   - **Time limit** → `native_state` TIMEOUT; raise `duration`.
   - **GPU not allocated** → `nvidia-smi`/`rocm-smi` not found or returns no devices. Check that `resources.gpus` is set for partitions that require `--gpus=<n>`.
   - **Module from wrong partition loaded** → wrong ABI, missing libraries, segfaults. Ensure the `system/<partition>` module matches the partition the job ran on.
3. The exact script that was submitted is kept in `~/.rccs-cloud/jobs/` — `fs_view` it when debugging.

## Live job inspection

For an ACTIVE job on a GPU partition:
`run_command_on_cluster("srun --overlap --jobid <id> nvidia-smi")` (NVIDIA)
`run_command_on_cluster("srun --overlap --jobid <id> rocm-smi")` (AMD ROCm)
