---
name: rccs-cloud-submitting-jobs
description: Use when the user wants to run, submit, or launch a job on the R-CCS Cloud. Covers partition selection, module loading, JobSpec construction, submission, and interactive sessions.
---

# Submitting jobs on the R-CCS Cloud

The R-CCS Cloud is a heterogeneous testbed with many partition families. The
two most important choices before writing any script are: **which partition**
(hardware family) and **which modules to load** (they differ per partition).

## Workflow

0. **Search docs first** — `search_docs` (rccs-cloud-docs) with the user's
   question or the specific resource detail you need (partition specs, module
   commands, GPU flag rules). Do not skip this or rely solely on the inline
   facts below — they are orientation aids, not the authoritative source.
   If `search_docs` is unavailable or returns nothing useful, continue with
   the inline facts and note that docs were unavailable.

1. **Pick the partition** — `get_facility` has the full table. Rules of thumb:
   - General x86_64 CPU work → `genoa` (default; 16 nodes, 768 GB) or `genoa-m` (1 node, 3 TB)
   - Fujitsu A64FX (ARM) work → `fx700` (31 nodes; requires cross-compilation from r340)
   - NVIDIA GPU (CUDA/nvhpc) → `a100`, `ai-l40s`, `qc-a100`, `qc-gh200`, `ng-dgx-m[0-3]`
   - AMD GPU (ROCm) → `mi100`, `qc-mi250`, `fs-mi300a`, `fs-mi300x`
   - Intel GPU (oneAPI) → `qc-pvc`
   - Cross-compilation for fx700 (no GPU, multi-user) → `r340`

2. **Know the module for your partition** — every partition requires its own
   `system/<partition>` module loaded first. Put the module load at the start
   of `executable`. The render_script also emits `source /etc/profile`
   automatically before anything else — do not add it manually.

   | Partition | Module command |
   |-----------|---------------|
   | fx700 | `module load system/fx700 FJSVstclanga` |
   | genoa, genoa-m | `module load system/genoa mpi/openmpi-x86_64` |
   | a100 | `module load system/a100 nvhpc` |
   | b300 | `module load system/b300 nvhpc` |
   | mi100 | `module load system/mi100 rocm` |
   | ai-h100l-pu | `module load system/ai-h100l nvhpc` |
   | ai-h200-brc | `module load system/ai-h200-brc nvhpc` |
   | ai-l40s | `module load system/ai-l40s nvhpc` |
   | qc-a100 | `module load system/qc-a100 nvhpc` |
   | qc-gh200 | `module load system/qc-gh200 nvhpc` |
   | qc-mi250 | `module load system/qc-mi250 rocm` |
   | fs-mi300a | `module load system/fs-mi300a rocm` |
   | fs-mi300x | `module load system/fs-mi300x rocm` |
   | qc-pvc | `module load system/qc-pvc` or `source /opt/intel/oneapi/setvars.sh` |
   | ng-dgx-m[0-3] | `module load system/ng-dgx nvhpc` |
   | r340 | (none required) |

3. **Stage any needed files** with `fs_upload` / `fs_mkdir` (paths are relative
   to the home directory unless absolute).

4. **Submit with a JobSpec** via `submit_job`. Show the user the spec (or
   describe it) before submitting unless they asked to just run it.

   CPU job on genoa:
   ```json
   {
     "name": "my-cpu-job",
     "executable": "module load system/genoa mpi/openmpi-x86_64 && srun ./a.out",
     "directory": "/home/<user>/work",
     "resources": {"node_count": 2, "processes_per_node": 4},
     "attributes": {"duration": "01:00:00", "queue_name": "genoa"}
   }
   ```

   NVIDIA GPU job on ai-l40s (needs `--gpus=<n>`):
   ```json
   {
     "name": "my-gpu-job",
     "executable": "module load system/ai-l40s nvhpc && srun ./app",
     "resources": {"node_count": 1, "gpus": 2, "processes_per_node": 2},
     "attributes": {"duration": "02:00:00", "queue_name": "ai-l40s"}
   }
   ```

   A64FX job on fx700 (cross-compiled; ARM binary):
   ```json
   {
     "name": "my-fx700-job",
     "executable": "module load system/fx700 FJSVstclanga && srun ./a.out",
     "resources": {"node_count": 4, "processes_per_node": 48},
     "attributes": {"duration": "02:00:00", "queue_name": "fx700"}
   }
   ```

5. **Verify**: `get_job_status` right after submission. `QUEUED` with a `reason`
   explains any wait; stdout lands in `<workdir>/slurm-<job_id>.out`.

## R-CCS Cloud conventions

- **GPU flag**: Most GPU partitions use `resources.gpus` → `--gpus=<n>`.
  Exception: `qc-gh200` and `ng-dgx-m[0-3]` are unified CPU+GPU superchips;
  omit `gpus` for those.
- **Architecture matters**: `fx700` is A64FX (aarch64-like); `qc-gh200` and
  `ng-dgx` are NVIDIA Grace (aarch64). x86_64 binaries will not run on any
  of those. Use r340 to cross-compile for fx700.
- **OS difference**: `ng-dgx-m[0-3]` runs Ubuntu; all others run Rocky Linux.
  A binary or Python wheel built for Rocky may not work on ng-dgx without rebuild.
- **Network**: Only InfiniBand-connected partitions (fx700, a100, qc-*) are
  suited for tightly-coupled multi-node MPI. Ethernet-only partitions have high
  latency; prefer single-node or loosely-coupled work there.
- **Source /etc/profile is automatic**: render_script always emits it; you do
  not need to add it to executable.
- **Submitted scripts** land in `~/.rccs-cloud/jobs/` — `fs_view` them to debug.

## Don't

- Don't guess module names — use `search_docs` or `run_command_on_cluster("module avail")`.
- Don't load a system module from the wrong partition.
- Don't run computation on the login node — submit a job.
- Don't `cancel_job` without confirming with the user.
