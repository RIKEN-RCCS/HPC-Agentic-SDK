---
name: hokusai-submitting-jobs
description: Submit batch jobs to HOKUSAI BigWaterfall2 (HBW2). Use when the user wants to run a computation, an MPI or hybrid job, a GPU job, or a container on HBW2. Covers describing a job in resource terms, choosing a partition, threads, GPUs, and containers.
---

# Submitting jobs on HOKUSAI (HBW2)

You describe a job in **resource terms** and the plugin assembles and submits
the Slurm batch script — you never write sbatch flags by hand. Always call
`search_docs` first for anything machine-specific you're unsure about.

## The resource model (JobSpec)

- `executable` — the command line (may be a full shell line, e.g.
  `module load intel && srun ./app`).
- `launcher` — set to `srun` for MPI. Under Slurm, `srun` inherits the job's
  allocation, so you do **not** pass process counts on the launch line.
- `resources.node_count`, `resources.processes_per_node` (MPI ranks/node),
  `resources.cpu_cores_per_process` (threads/rank), `resources.memory`
  (bytes/node), `resources.gpus` (job-total GPU count).
- `attributes.queue_name` (partition), `attributes.duration` (HH:MM:SS or
  seconds), `attributes.account` (project to bill).
- `environment` — env vars; **set `OMP_NUM_THREADS`** to match
  `cpu_cores_per_process` for threaded code, or it runs far slower.

## Defaults applied for you

If omitted: partition → `mpc`, account → your configured `defaults.account`,
duration → 1 hour. **An account is mandatory** — if none is set anywhere the
submission errors telling you to name a project.

## Choosing a partition

| partition | use for | max wall |
|---|---|---|
| `mpc` (default) | everyday CPU / MPI | ~24 h |
| `mpc_l` | longer CPU runs | ~72 h |
| `lmc` | very-large-memory (2.7 TiB nodes) | ~24 h |
| `gpu` | GPU batch (NVIDIA H100) | ~72 h |
| `gpu_i` | interactive GPU | ~24 h |

Call `get_resources` to see where a job will start soonest; call
`get_facility` for full static limits. Think CPU + MPI first — GPU is
secondary on HBW2.

## MPI / toolchain

Intel oneAPI is the default: `module load intel` brings the Intel compilers
and Intel MPI together. Open MPI is available but **conflicts with Intel
MPI** — load one only (`module purge` before switching). Launch with `srun`
regardless of flavor.

## GPUs

Request GPUs with `resources.gpus` (a job-total count). One GPU also reserves
~28 CPU cores. Containers get NVIDIA passthrough (`--nv`) automatically when
the job requests GPUs.

## Containers

Set `container.image` to a `.sif` path or `docker://` URI to run inside
Singularity; `launcher='srun'` stays outside the container so MPI works.

## Internet from compute nodes

Compute nodes have no direct internet route. A job that must fetch something
reaches the web through the front-end proxy at
`http://$SLURM_SUBMIT_HOST:3128` — set `http_proxy`/`https_proxy` to it in
`environment`.

## Before submitting

Show the user the spec (or `render_job_script`'s output) and a one-line
explanation, then call `submit_job` — unless they asked to just run it.
`submit_job` returns `{job_id, script_path}`; the script lands under
`~/agent/jobs/`.
