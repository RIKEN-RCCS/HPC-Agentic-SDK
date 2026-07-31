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
     "executable": "module load nvhpc-hpcx && mpirun -np 2 python train.py",
     "directory": "/home/<user>/experiments/vit",
     "resources": {"gpus": 2, "processes_per_node": 2},
     "attributes": {"duration": "12:00:00", "queue_name": "gpu"}
   }
   ```
   The rendered sbatch script is kept on the cluster under `~/agent/jobs/` — `fs_view` it if the user wants to inspect what was submitted.
4. **Verify**: `get_job_status` right after submission. `QUEUED` with a `reason` explains any wait; stdout lands in `<workdir>/slurm-<job_id>.out`.

## MPI launch: use mpirun, not srun

Verified live: `srun` fails to launch MPI ranks on RIKYU — `MPI_Init` aborts
with an internal-runtime failure, even though `srun --mpi=list` shows
`pmi2`/`pmix` plugins registered. Launch MPI programs with `mpirun`
instead, after loading an MPI-capable module (`nvhpc-hpcx` or
`nvhpc-hpcx-cuda13`, not `nvhpc-nompi`):
`module load nvhpc-hpcx && mpirun -np <n> ./a.out`.

**Set `resources.processes_per_node` to match your rank count** — `mpirun`
reads available task slots from the Slurm allocation, and a job that only
requests GPUs without also setting `processes_per_node` gets just 1 slot,
so `mpirun -np 2` (or more) fails with "not enough slots" before it even
starts. This is unrelated to the `srun` issue above; both single-node and
real multi-node `mpirun` launches work correctly once slots are sized
right — verified live with a real 2-node, 8-rank job (`gpus: 8,
processes_per_node: 4`), no hostfile or extra setup needed. (`srun` itself
is still fine for non-MPI use — interactive `salloc`/`srun --pty`, or
attaching to a running job with `srun --overlap --jobid <id>` for
diagnostics like `nvidia-smi`; the failure is specifically MPI rank
bootstrap.)

## Rikyu conventions

- **Time limits**: max 96h regardless of GPU count; confirm the current default with `get_facility` if the user omits `duration`. Format `HH:MM:SS` or `D-HH:MM:SS`.
- **Modules** (put `module load …` at the start of `executable`): `nvhpc` standard; `nvhpc-hpcx` (or `nvhpc-hpcx-cuda13`) for multi-node MPI over InfiniBand; `nvhpc-nompi` when the user manages MPI; `nvhpc-byo-compiler` to use the system GCC instead.
- **Spack** provides prebuilt applications (not compilers) — `. /shared/software/spack-1.2.0/share/spack/setup-env.sh && spack load <package>` before running, e.g. `quantum-espresso`, `gromacs`, `lammps`. Loading a Spack package does not request GPUs by itself — the JobSpec's `gpus` still has to ask for them.
- **Architecture is aarch64** (Grace CPUs, B200 GPUs). x86_64 binaries, containers, and Python wheels will not run — check before suggesting pip installs of compiled packages.
- **Node-local scratch**: `/tmp` on the compute node, 1.5TB per requested GPU, xfs, auto-deleted when the job ends. Stage datasets/checkpoints there for I/O-heavy work and copy results back to `/home/<user>` or the group area (`/data1/<group>`) before the script exits.
- **Interactive sessions**: `salloc`/`srun --pty` hold allocations open — use `run_command_on_cluster` only for short non-interactive checks; prefer batch jobs.

## Don't

- Don't launch MPI ranks with `srun` — `MPI_Init` fails; use `mpirun` instead.
- Don't submit an MPI job without setting `resources.processes_per_node` —
  `mpirun` will fail with "not enough slots" even though the job runs fine.
- Don't run computation on the login node — submit a job.
- Don't guess Rikyu-specific details — use `search_docs` from the rikyu-docs server. Note it searches a bundled guide, not a live site — never tell the user to go check a URL for more detail.
- Don't `cancel_job` without confirming with the user.
