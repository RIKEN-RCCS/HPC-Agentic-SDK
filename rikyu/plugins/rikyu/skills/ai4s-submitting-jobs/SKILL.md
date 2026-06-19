---
name: ai4s-submitting-jobs
description: Use when the user wants to run, submit, or launch a job (training, computation, benchmark) on the AI4S supercomputer / rikyu cluster. Covers partition selection, JobSpec construction, submission, and interactive sessions.
---

# Submitting jobs on the AI4S supercomputer

## Workflow

1. **Pick the partition first** — on AI4S the partition fixes the resource share per node. Use `get_facility` for the table. Rules of thumb:
   - 1 GPU → `1n1gpu` (36 CPUs, 400GB), 2 GPUs → `1n2gpu`, full node → `1n4gpu`
   - Multi-node → `2n4gpu` or `4n4gpu` (always 4 GPUs/node)
   - `4n4gpu-p` only for jobs needing >96h wall time
2. **Stage any needed files** with `fs_upload` / `fs_mkdir` (paths are relative to the home directory unless absolute).
3. **Submit with a JobSpec** via `submit_job`. Show the user the spec (or describe it) before submitting unless they asked to just run it. Example:
   ```json
   {
     "name": "train-vit",
     "executable": "module load nvhpc && srun python train.py",
     "directory": "/home/<user>/experiments/vit",
     "resources": {"node_count": 1, "gpus_per_node": 2, "processes_per_node": 2},
     "attributes": {"duration": "12:00:00", "queue_name": "1n2gpu"}
   }
   ```
   The rendered sbatch script is kept on the cluster under `~/.rikyu/jobs/` — `fs_view` it if the user wants to inspect what was submitted.
4. **Verify**: `get_job_status` right after submission. `QUEUED` with a `reason` explains any wait; stdout lands in `<workdir>/slurm-<job_id>.out`.

## AI4S conventions

- **Time limits**: default 12h if duration omitted at the Slurm level; max 96h (except `4n4gpu-p`). Format `HH:MM:SS` or `D-HH:MM:SS`.
- **Modules** (put `module load …` at the start of `executable`): `nvhpc` standard; `nvhpc-hpcx` for multi-node MPI over InfiniBand; `nvhpc-nompi` when the user manages MPI; bare `cuda/13.2` or `cuda/11.8` for just the toolkit.
- **Architecture is aarch64** (Grace CPUs, GB200 GPUs). x86_64 binaries, containers, and Python wheels will not run — check before suggesting pip installs of compiled packages.
- **Node-local scratch**: `$USER_SCRATCH_DIR` is ~7TB node-local NVMe, auto-deleted when the job ends. Stage datasets/checkpoints there for I/O-heavy work and `cp` results back to `$SLURM_SUBMIT_DIR` before the script exits.
- **Interactive sessions**: `salloc`/`srun --pty` hold allocations open — use `run_command_on_cluster` only for short non-interactive checks; prefer batch jobs.

## Don't

- Don't run computation on the login node — submit a job.
- Don't guess AI4S-specific details — use `search_docs` from the rikyu-docs server.
- Don't `cancel_job` without confirming with the user.
