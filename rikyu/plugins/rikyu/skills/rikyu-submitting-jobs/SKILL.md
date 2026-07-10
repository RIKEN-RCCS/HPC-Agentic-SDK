---
name: rikyu-submitting-jobs
description: Use when the user wants to run, submit, or launch a job (training, computation, benchmark) on the Rikyu supercomputer. Covers partition selection, JobSpec construction, submission, and interactive sessions.
---

# Submitting jobs on the Rikyu supercomputer

## Workflow

1. **Pick a GPU count first** — Rikyu has a single `gpu` partition; you don't choose a partition per GPU count, you request the total GPUs for the job and Slurm places it. Use `get_facility` for the exact table, but the rule: only **1, 2, 3, 4, 8, 12, or 16** GPUs are accepted (1-4 fit on one node; 8/12/16 span 2/3/4 nodes at 4 GPUs/node). Each GPU brings 36 CPU cores and ~400GB combined memory — ask for more GPUs to get more of both, don't try to raise `--mem` independently.
2. **Stage any needed files** with `fs_upload` / `fs_mkdir` (paths are relative to the home directory unless absolute).
3. **Submit with a JobSpec** via `submit_job`. Show the user the spec (or describe it) before submitting unless they asked to just run it. Example (2-GPU job, single node — leave `node_count` at its default so Slurm derives placement from `gpus`):
   ```json
   {
     "name": "train-vit",
     "executable": "module load nvhpc && srun python train.py",
     "directory": "/home/<user>/experiments/vit",
     "resources": {"gpus": 2, "processes_per_node": 2},
     "attributes": {"duration": "12:00:00", "queue_name": "gpu"}
   }
   ```
   The rendered sbatch script is kept on the cluster under `~/.rikyu/jobs/` — `fs_view` it if the user wants to inspect what was submitted.
4. **Verify**: `get_job_status` right after submission. `QUEUED` with a `reason` explains any wait; stdout lands in `<workdir>/slurm-<job_id>.out`.

## Rikyu conventions

- **Time limits**: max 96h regardless of GPU count; confirm the current default with `get_facility` if the user omits `duration`. Format `HH:MM:SS` or `D-HH:MM:SS`.
- **Modules** (put `module load …` at the start of `executable`): `nvhpc` standard; `nvhpc-hpcx` (or `nvhpc-hpcx-cuda13`) for multi-node MPI over InfiniBand; `nvhpc-nompi` when the user manages MPI; `nvhpc-byo-compiler` to use the system GCC instead.
- **Spack** provides prebuilt applications (not compilers) — `. /shared/software/spack-1.2.0/share/spack/setup-env.sh && spack load <package>` before running, e.g. `quantum-espresso`, `gromacs`, `lammps`. Loading a Spack package does not request GPUs by itself — the JobSpec's `gpus` still has to ask for them.
- **Architecture is aarch64** (Grace CPUs, B200 GPUs). x86_64 binaries, containers, and Python wheels will not run — check before suggesting pip installs of compiled packages.
- **Node-local scratch**: `/tmp` on the compute node, 1.5TB per requested GPU, xfs, auto-deleted when the job ends. Stage datasets/checkpoints there for I/O-heavy work and copy results back to `/home/<user>` or the group area (`/data1/<group>`) before the script exits.
- **Interactive sessions**: `salloc`/`srun --pty` hold allocations open — use `run_command_on_cluster` only for short non-interactive checks; prefer batch jobs.

## Don't

- Don't run computation on the login node — submit a job.
- Don't guess Rikyu-specific details — use `search_docs` from the rikyu-docs server. Note it searches a bundled guide, not a live site — never tell the user to go check a URL for more detail.
- Don't `cancel_job` without confirming with the user.
