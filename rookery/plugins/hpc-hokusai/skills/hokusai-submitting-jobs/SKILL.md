---
name: hokusai-submitting-jobs
description: Use when the user wants to run, submit, or launch a job on HOKUSAI BigWaterfall2 (HBW2). Covers partition/queue selection, JobSpec construction, submission, and known gotchas specific to this facility.
user-invocable: true
---

# Submitting jobs on HOKUSAI BigWaterfall2 (HBW2)

Every tool call in this skill uses `facility="hokusai"`.

HBW2 is **CPU-first** — think CPU + MPI before reaching for GPUs. Describe
a job in resource terms and let the plugin assemble the sbatch script; you
never write sbatch flags by hand.

## Defaults applied for you

If omitted: partition → `mpc`, account → your configured `defaults.account`,
duration → 1 hour. **An account is mandatory on every HBW2 job** — if none
is set anywhere, `submit_job` errors telling you to name a project rather
than letting sbatch reject it. Call `get_projects(facility="hokusai")` to
see which accounts you may charge, and `hokusai-configuring` to set a
default.

## Choosing a partition

| partition | use for | max wall |
|---|---|---|
| `mpc` (default) | everyday CPU / MPI | ~24 h |
| `mpc_l` | longer CPU runs | ~72 h |
| `lmc` | very-large-memory (2.7 TiB nodes) | ~24 h |
| `gpu` | GPU batch (NVIDIA H100) | ~72 h |
| `gpu_i` | interactive GPU | ~24 h |

Call `get_resources(facility="hokusai")` to see where a job will start
soonest; `get_facility(facility="hokusai")` for full static limits.

## The resource model

- `executable` — the command line (may be a full shell line, e.g.
  `module load intel && srun ./app`).
- `launcher` — set to `srun` for MPI. Under Slurm, `srun` inherits the
  job's allocation, so you do **not** pass process counts on the launch
  line.
- `resources.node_count`, `resources.processes_per_node` (MPI ranks/node),
  `resources.cpu_cores_per_process` (threads/rank), `resources.memory`
  (bytes/node), `resources.gpus` (job-total GPU count).
- `attributes.queue_name` (partition), `attributes.duration` (HH:MM:SS or
  seconds), `attributes.account` (project to bill).
- `environment` — env vars; **set `OMP_NUM_THREADS`** to match
  `cpu_cores_per_process` for threaded code, or it runs far slower.

## MPI / toolchain

Intel oneAPI is the default: `module load intel` brings the Intel compilers
and Intel MPI together. Open MPI is available but **conflicts with Intel
MPI** — load one only (`module purge` before switching). Launch with `srun`
regardless of flavor (unlike RIKYU and R-CCS Cloud, `srun` is the correct
MPI launcher here).

The installed oneAPI ships **only the LLVM compilers** (`icx`/`icpx`/`ifx`
and the `mpiicx`/`mpiicpx`/`mpiifx` wrappers). The classic wrappers
(`mpiicc`/`mpiicpc`/`mpiifort`) are also on `PATH`, but their backing
compilers (`icc`/`icpc`/`ifort`) are **not installed** — a toolchain or
build system that names them fails at configure time. New build recipes
should use the `mpi*fx` wrapper names.

Job shells start with a clean environment: a binary built under
`module load intel` needs the **same `module load` in the job that runs
it**, or it fails at launch with exit 127 and an
`error while loading shared libraries` message (MKL, Intel MPI).

## GPUs

Request GPUs with `resources.gpus` (a job-total count). One GPU also
reserves ~28 CPU cores. Containers get NVIDIA passthrough (`--nv`)
automatically when the job requests GPUs.

## Containers

Set `container.image` to a `.sif` path or `docker://` URI to run inside
Singularity; `launcher="srun"` stays outside the container so MPI works.

## Internet from compute nodes

Compute nodes have no direct internet route. A job that must fetch
something reaches the web through the front-end proxy at
`http://$SLURM_SUBMIT_HOST:3128` — set `http_proxy`/`https_proxy` to it in
`environment`.

## Universal rules (apply on every facility, not just this one)

- `submit_job(facility="hokusai", spec=spec)` — **show the user the spec
  (or a plain-language description of it) before submitting, unless
  they've explicitly said to just run it.** No exceptions for this call.
- The returned `{"job_id": ..., "script_path": ...}` — the rendered script
  is kept on the cluster; `fs_view(facility="hokusai", path=script_path)`
  to inspect exactly what was submitted.
- If a partition/queue/GPU choice isn't given or obvious, check
  `get_resources(facility="hokusai")` (live occupancy) and
  `get_facility(facility="hokusai")` (static limits) — don't guess.
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
  use `search_docs(facility="hokusai", query=...)` on the `hpc-docs`
  server. It searches a bundled guide, not a live site — never invent a URL
  to send the user to.
- Don't call `cancel_job` without confirming with the user first.
