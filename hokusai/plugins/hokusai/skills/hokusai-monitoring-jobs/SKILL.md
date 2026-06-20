---
name: hokusai-monitoring-jobs
description: Use when the user asks about the status, progress, output, history, or failure of jobs on HOKUSAI BigWaterfall2 (HBW2), or about queue and node availability.
---

# Monitoring jobs on HOKUSAI BigWaterfall2 (HBW2)

If the user asks about scheduler policies, partition limits, or storage paths
(rather than a specific live job), call `search_docs` (hokusai-docs) first.
If `search_docs` is unavailable or returns nothing useful, use the inline facts
below and note that docs were unavailable.

## Status checks

- **One job**: `get_job_status` — `state` is normalized (QUEUED/ACTIVE/COMPLETED/FAILED/CANCELED); `native_state` is Slurm's (PD/R/CG/CD/CA/F/NF/TO…). A QUEUED job's `reason` field says why it waits (`Resources`, `Priority`, …). HBW2 orders jobs by per-project fair-share priority.
- **My recent jobs**: `get_job_statuses` with an empty list (last 2 days), or pass specific IDs.
- **Cluster availability**: `get_resources` — per-partition allocated/idle/other/total node counts. Idle nodes can start jobs immediately.
- **Core-time budget**: `run_command_on_cluster("listcpu -p <project>")` — jobs are rejected once a project's allocated core-time is used up.

## Job output and failure triage

1. Stdout/stderr default to `<workdir>/slurm-<job_id>.out` (workdir is in the status record). Read with `fs_tail` (or `fs_head`/`fs_view`).
2. Common HBW2 failure modes:
   - **Missing account / no core-time** → job rejected or never starts; check `listcpu -p <project>` and that `--account` is set.
   - **OOM** → `native_state` OUT_OF_MEMORY; raise `resources.memory`, reduce ranks/threads per node, or move large-memory work to the `lmc` partition.
   - **Time limit** → `native_state` TIMEOUT; raise `duration` (max 24h on `mpc`, 72h on `mpc_l`).
   - **Wrong thread/rank count** → performance collapse when `OMP_NUM_THREADS` wasn't set; check the script and the `--cpus-per-task`/`OMP_NUM_THREADS` pairing.
   - **Module conflict** → e.g. loading `openmpi` while `intelmpi` is loaded; `module purge` first.
3. The exact script that was submitted is kept in `~/.hokusai/jobs/` — `fs_view` it when debugging.

## Live job inspection

For an ACTIVE job, peek at its node with:
`run_command_on_cluster("squeue --jobs=<id> --long")` for the node list, then
`run_command_on_cluster("srun --overlap --jobid <id> <command>")` for a quick
check on the allocated node (e.g. `top -bn1`, or `nvidia-smi` for a GPU job).
