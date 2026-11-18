---
name: rikyu-submitting-jobs
description: Use when the user wants to run, submit, or launch a job on RIKYU (RIKEN AI4S / GB200). Covers partition/queue selection, JobSpec construction, submission, and known gotchas specific to this facility.
user-invocable: true
---

# Submitting jobs on RIKYU (RIKEN AI4S / GB200)

Every tool call in this skill uses `facility="rikyu"`.

## Workflow

1. **Pick a GPU count first** — RIKYU has a single `gpu` partition; you
   don't choose a partition per GPU count, you request the total GPUs for
   the job and Slurm places it. Use `get_facility(facility="rikyu")` for
   the exact table, but the rule: only **1, 2, 3, 4, 8, 12, or 16** GPUs
   are accepted (1-4 fit on one node; 8/12/16 span 2/3/4 nodes at 4
   GPUs/node). Each GPU brings 36 CPU cores and ~400GB combined memory —
   ask for more GPUs to get more of both, don't try to raise `--mem`
   independently. `submit_job` rejects any other count with a clear error
   before it ever reaches Slurm.
2. **Stage any needed files** with `fs_upload(facility="rikyu", ...)` /
   `fs_mkdir(facility="rikyu", ...)` (paths are relative to the home
   directory unless absolute).
3. **Submit with a JobSpec** via `submit_job(facility="rikyu", spec=...)`.
   Example (2-GPU job, single node — leave `node_count` at its default so
   Slurm derives placement from `gpus`):
   ```json
   {
     "name": "train-vit",
     "executable": "module load nvhpc-hpcx && mpirun -np 2 python train.py",
     "directory": "/home/<user>/experiments/vit",
     "resources": {"gpus": 2, "processes_per_node": 2},
     "attributes": {"duration": "12:00:00", "queue_name": "gpu"}
   }
   ```
   Leave `attributes.queue_name` blank if you like — RIKYU's only
   partition, `gpu`, is filled in automatically.
4. **Verify**: `get_job_status(facility="rikyu", job_id=...)` right after
   submission. `queued` with a `message` explains any wait. Once it runs, read
   `<workdir>/slurm-<job_id>.out` with `fs_tail` — take `workdir` from the
   status record rather than assuming `$HOME`.

## MPI launch: use mpirun, not srun

Verified live: `srun` fails to launch MPI ranks on RIKYU — `MPI_Init`
aborts with an internal-runtime failure, even though `srun --mpi=list`
shows `pmi2`/`pmix` plugins registered. Launch MPI programs with `mpirun`
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

## NCCL / GPU collectives — quick fixes

Launch every NCCL or GPU-MPI job with ranks NUMA-bound — NCCL pairs each
GPU with its own NIC from rank affinity data:

```sh
mpirun -n <np> --bind-to numa --map-by numa --mca fcoll individual ./app
```

- **NCCL collective is seconds instead of ~sub-ms, result is correct:**
  ranks are unbound or `--bind-to core`. NCCL mispairs GPU↔NIC; the
  collective silently runs ~60x slow on one shared rail. Fix: `--bind-to
  numa --map-by numa`.
- **`"Duplicate GPU detected"` / `ncclInvalidUsage` from
  `ncclCommInitRank`:** more than one rank per GPU in one communicator
  (MPS or not). On NCCL ≥ 2.30, enable multi-rank-per-GPU — verified
  working at 2 ranks/GPU on RIKYU (NCCL 2.31.2 via
  `nvhpc-hpcx-cuda13/26.9`):

  ```sh
  export NCCL_MULTI_RANK_GPU_ENABLE=1   # NCCL >= 2.30, off by default
  export NCCL_MAX_CTAS=4                # cap collective SM use (defaults fit ~2 ranks/GPU; retune for more)
  export NCCL_NVLS_ENABLE=0             # NVLS is unavailable to duplicate-GPU ranks
  ```

  If it hangs (SM residency deadlock): `NCCL_NET_GDR_LEVEL=LOC` —
  diagnostics only, costs performance. On NCCL ≤ 2.29 use the fallback:
  one communicator per GPU — reduce co-tenants into that rank, collective
  over one rank per GPU, broadcast back.
- **Inter-node CUDA sends die with "cannot find remote protocol … from
  cuda/GPU" / `ucp_ep_create failed`:** a per-rank `UCX_NET_DEVICES=mlx5_<i>:1`
  is set (a GB200 tuning-guide recipe). Unset it; NUMA binding covers NCCL's
  NIC selection.

MPI-IO, MPS-launch, GPU-slot and `processes_per_node` gotchas: see the MPI
launch section above.

## RIKYU conventions

- **Time limits**: max 96h regardless of GPU count; confirm the current
  default with `get_facility` if the user omits `duration`. Format
  `HH:MM:SS` or `D-HH:MM:SS`.
- **Modules** (put `module load …` at the start of `executable`): `nvhpc`
  standard; `nvhpc-hpcx` (or `nvhpc-hpcx-cuda13`) for multi-node MPI over
  InfiniBand; `nvhpc-nompi` when the user manages MPI; `nvhpc-byo-compiler`
  to use the system GCC instead.
- **Spack** provides prebuilt applications (not compilers) —
  `. /shared/software/spack-1.2.0/share/spack/setup-env.sh && spack load
  <package>` before running, e.g. `quantum-espresso`, `gromacs`, `lammps`.
  Loading a Spack package does not request GPUs by itself — the JobSpec's
  `gpus` still has to ask for them.
- **Architecture is aarch64** (Grace CPUs, B200 GPUs). x86_64 binaries,
  containers, and Python wheels will not run — check before suggesting pip
  installs of compiled packages.
- **Node-local scratch**: `/tmp` on the compute node, 1.5TB per requested
  GPU, xfs, auto-deleted when the job ends. Stage datasets/checkpoints
  there for I/O-heavy work and copy results back to `/home/<user>` or the
  group area (`/data1/<group>`) before the script exits.
- **Interactive sessions**: `salloc`/`srun --pty` hold allocations open —
  use `run_command_on_cluster` only for short non-interactive checks;
  prefer batch jobs.

## RIKYU-specific don'ts

- Don't launch MPI ranks with `srun` — `MPI_Init` fails; use `mpirun` instead.
- Don't submit an MPI job without setting `resources.processes_per_node` —
  `mpirun` will fail with "not enough slots" even though the job runs fine.

## Always set the project account

Put `"account": "<project>"` in `attributes` on every job. RIKYU rejects a
job from a multi-project user that omits it:

> `[AI4S] You belong to multiple projects, so the project to be charged
> must be specified explicitly.`

It is optional only for someone in exactly one project, and harmless there,
so set it unconditionally instead of deciding. `get_projects(facility="rikyu")`
lists the user's projects (the `rkp*` groups); if they have several and
haven't said which to charge, ask rather than picking one — it is a billing
decision at 300 yen/GPU-hour. `RIKYU_ACCOUNT` or `defaults.account` in
`~/.hpc-agent/rikyu.json` supplies it automatically when set.

## Universal rules (apply on every facility, not just this one)

- `submit_job(facility="rikyu", spec=spec)` — **show the user the spec
  (or a plain-language description of it) before submitting, unless
  they've explicitly said to just run it.** No exceptions for this call.
- The returned `{"job_id": ..., "script_path": ...}` — the rendered script
  is kept on the cluster; `fs_view(facility="rikyu", path=script_path)`
  to inspect exactly what was submitted.
- If a partition/queue/GPU choice isn't given or obvious, check
  `get_resources(facility="rikyu")` (live occupancy) and
  `get_facility(facility="rikyu")` (static limits) — don't guess.
- Don't run heavy computation on the login node — submit a job instead.
- Stage anything the cluster needs (source trees, inputs, uploads, run
  directories) under `~/agent/work/<descriptive-name>/`, never in the
  home-directory root. `~/agent/` is the agent's visible scratch area —
  `~/agent/jobs` already holds every submitted script — and the home
  root stays the user's own.
- Create a requested `spec.directory` with `fs_mkdir` **before** submission.
  Schedulers enter that directory before the script body and `pre_launch`
  runs, so a `mkdir` in `pre_launch` is too late.
- Don't guess facility-specific details not covered by the notes above —
  use `search_docs(facility="rikyu", query=...)` on the `hpc-docs`
  server. It searches a bundled guide, not a live site — never invent a URL
  to send the user to.
- Don't call `cancel_job` without confirming with the user first.
