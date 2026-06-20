---
name: hokusai-submitting-jobs
description: Use when the user wants to run, submit, or launch a job (simulation, computation, benchmark, MPI/OpenMP program) on HOKUSAI BigWaterfall2 (HBW2). Covers partition selection, JobSpec construction, accounts, submission, and interactive sessions.
---

# Submitting jobs on HOKUSAI BigWaterfall2 (HBW2)

HBW2 is a CPU-first system. Most work runs on the Massively Parallel Computer
(MPC); the GPU server is a small, optional resource for postprocessing.

## Workflow

0. **Search docs first** — `search_docs` (hokusai-docs) with the user's
   question or the specific resource detail you need (partition limits, module
   names, account format, wall-time rules). Do not skip this or rely solely on
   the inline facts below — they are orientation aids, not the authoritative
   source. If `search_docs` is unavailable or returns nothing useful, continue
   with the inline facts and note that docs were unavailable.

1. **Pick the partition** — `get_facility` has the full table. Rules of thumb:
   - General CPU work (≤24h) → `mpc` (default; up to 64 nodes, 112 cores/node, 112 GiB).
   - Longer CPU work (≤72h, ≤8 nodes) → `mpc_l`.
   - Large memory (up to ~2.7 TiB/node) → `lmc` (2 nodes).
   - GPU postprocessing → `gpu` (1 node, 4× H100). Only if the job actually needs a GPU.
2. **Set the account** — HBW2 requires `attributes.account` (a project ID like
   `RB999999`). If omitted, the configured default (`~/.hokusai/config.json`)
   is used. Run `listcpu -p <project>` (via `run_command_on_cluster`) to check
   remaining core-time; jobs are rejected when it runs out.
3. **Stage any needed files** with `fs_upload` / `fs_mkdir` (paths are relative
   to the home directory unless absolute).
4. **Submit with a JobSpec** via `submit_job`. Show the user the spec (or
   describe it) before submitting unless they asked to just run it. Describe CPU
   work with `processes_per_node` (MPI ranks) and `cpu_cores_per_process`
   (threads per rank). Examples:

   Pure-MPI on one MPC node (20 ranks):
   ```json
   {
     "name": "mpi-run",
     "executable": "module load intel && srun ./a.out",
     "directory": "/home/<user>/work",
     "resources": {"node_count": 1, "processes_per_node": 20},
     "attributes": {"duration": "1:00:00", "queue_name": "mpc", "account": "RB999999"}
   }
   ```

   Hybrid MPI+OpenMP across 2 nodes (2 ranks/node × 10 threads):
   ```json
   {
     "name": "hybrid-run",
     "executable": "module load intel && srun --cpus-per-task=$SLURM_CPUS_PER_TASK ./a.out",
     "resources": {"node_count": 2, "processes_per_node": 2, "cpu_cores_per_process": 10},
     "environment": {"OMP_NUM_THREADS": "10"},
     "attributes": {"duration": "1:30:00", "queue_name": "mpc", "account": "RB999999"}
   }
   ```
   The rendered sbatch script is kept on the cluster under `~/.hokusai/jobs/` —
   `fs_view` it if the user wants to inspect what was submitted.
5. **Verify**: `get_job_status` right after submission. `QUEUED` with a `reason`
   explains any wait; stdout lands in `<workdir>/slurm-<job_id>.out`.

## HBW2 conventions

- **Architecture is x86_64 (Intel Xeon)** — use the Intel oneAPI compilers
  (`module load intel`, then `ifort`/`icc`/`mpiifort`/`ifx`/`icx`) and Intel MKL
  (`-qmkl=sequential|parallel|cluster`). `gcc/13.2.0` and `openmpi/4.1.6` are
  also available (openmpi conflicts with intelmpi — load only one).
- **Threads**: always set `OMP_NUM_THREADS` (use `$SLURM_CPUS_PER_TASK`) for
  OpenMP/auto-parallel code, or it may run with an unintended thread count.
- **Time limits**: default 1h if `duration` omitted; max 24h (`mpc`, `lmc`,
  `gpu_i`) or 72h (`mpc_l`, `gpu`). Format `HH:MM:SS`, `MM`, or `D-HH:MM:SS`.
- **Memory**: default per core is 1 GiB (MPC), 30 GiB (LMC), 4 GiB (GPU). Asking
  for more memory can raise the number of cores billed. Set `resources.memory`
  (bytes) only when needed.
- **GPUs** (rare): set `resources.gpus` (→ `--gpus`) and `queue_name: "gpu"`.
  One GPU allocates 28 CPU cores. Containers add `--nv` automatically.
- **Scratch**: `/tmp_work` is shared temporary space, auto-deleted after files
  age past one week. Node-local disk is also available for I/O-heavy work.
- **Outbound network from compute nodes** goes through the front-end Squid
  proxy: `export https_proxy=$SLURM_SUBMIT_HOST:3128`.
- **Step/array jobs**: dependencies via `--dependency=afterok:<id>` and arrays
  via `--array` — pass these through `attributes.custom_attributes` if needed.
- **Interactive sessions**: `srun --partition=<p> --account=<proj> --pty $SHELL`
  hold an allocation open — use `run_command_on_cluster` only for short
  non-interactive checks; prefer batch jobs.

## Don't

- Don't run computation on the front-end node — submit a job.
- Don't forget the account — jobs without a valid project won't run.
- Don't guess HBW2-specific details — use `search_docs` from the hokusai-docs server.
- Don't `cancel_job` without confirming with the user.
