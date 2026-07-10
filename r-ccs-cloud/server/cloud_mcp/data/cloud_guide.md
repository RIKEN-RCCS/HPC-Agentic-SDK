# R-CCS Cloud

An original, plain-language guide to driving the RIKEN R-CCS Cloud through the
agent. It covers the stable facts that shape how a job is described — hardware,
the Slurm dialect, modules, storage, and common failure modes. It deliberately
omits anything you can read live (current queue occupancy, `module avail`
output, disk usage) and generic HPC background.

## Orientation

The R-CCS Cloud is a heterogeneous research testbed managed by RIKEN R-CCS. It
is a Slurm cluster: jobs go through `sbatch`, and interactive sessions are
possible with `srun --pty`. Roughly twenty partitions span several CPU
architectures and three GPU vendors.

The single most important idea: **the partition you choose determines
everything else** — the CPU/GPU hardware, the system module you must load, the
GPU request flag, and even the operating system. There is no one "normal" way
to run here; every job starts with a partition decision.

## Login

SSH to `login.cloud.r-ccs.riken.jp`. Authentication is key-based; the agent's
SSH layer cannot answer a password prompt, so set up key auth (ideally behind a
`~/.ssh/config` alias) before configuring the plugin.

## Partitions and hardware

Partitions fall into five groups. Node counts and exact specs are in the
facility data (`get_facility`); the shape below is what matters when writing a
script.

### CPU-only

- **fx700** — Fujitsu A64FX, an Arm (aarch64) processor with SVE and HBM2, 32 GB,
  InfiniBand EDR. x86_64 binaries will not run; cross-compile on r340.
- **genoa** — AMD EPYC 9684X, x86_64, 768 GB, Ethernet. The general-purpose
  default partition.
- **genoa-m** — a single large-memory EPYC node, 3 TB.
- **r340** — a small multi-user Intel Xeon (x86_64) node used as the
  cross-compilation environment for fx700. No system module required.

### NVIDIA GPU

- **a100** (A100 ×8, IB), **qc-a100** (A100 ×8, 4 TB, IB), **qc-h100** (H100 ×4,
  IB — *under repair*), **b300** (B300 ×8), **ai-h200-brc** (H200 ×8),
  **ai-l40s** (L40S ×8), **ai-h100l** / **ai-h100l-pu** (H100 NVL ×1).
- **qc-gh200** — NVIDIA Grace (aarch64) + GH200, a unified CPU+GPU superchip, IB.
- **ng-dgx-m0..m3** — NVIDIA Grace (aarch64) + GB10 Blackwell superchips, running
  **Ubuntu** (all other partitions run Rocky Linux). The two nodes in each pair
  are linked at 200 Gbps; pairs connect to each other at 10 Gbps Ethernet.

### AMD GPU

- **mi100** (MI100 ×8), **qc-mi250** (MI250 ×8, IB), **fs-mi300x** (MI300X ×8, IB),
  **fs-mi300a** (MI300A ×4 — an APU where CPU and GPU share one 512 GB HBM pool),
  **qc-mi210** (MI210 ×1 — *GPU setup in progress*).

### Intel GPU

- **qc-pvc** — Intel Data Center GPU Max 1550 ("Ponte Vecchio") ×8, IB.

### Architectures at a glance

x86_64 everywhere **except**: `fx700` (A64FX/aarch64) and `qc-gh200` + `ng-dgx-m*`
(NVIDIA Grace/aarch64). A binary built for one architecture will not run on
another.

## Module loading

Every partition ships its own `system/<partition>` module that sets up the
compilers, libraries, and paths for that hardware. **Load it first, and never
load a system module belonging to a different partition** — a mismatched module
silently links the wrong libraries or fails at runtime.

| Partition | Module command |
|-----------|----------------|
| fx700 | `module load system/fx700 FJSVstclanga` |
| genoa, genoa-m | `module load system/genoa mpi/openmpi-x86_64` |
| a100 | `module load system/a100 nvhpc` |
| b300 | `module load system/b300 nvhpc` |
| ai-h100l, ai-h100l-pu | `module load system/ai-h100l nvhpc` |
| ai-h200-brc | `module load system/ai-h200-brc nvhpc` |
| ai-l40s | `module load system/ai-l40s nvhpc` |
| qc-a100 | `module load system/qc-a100 nvhpc` |
| qc-h100 | `module load system/qc-h100 nvhpc` |
| qc-gh200 | `module load system/qc-gh200 nvhpc` |
| mi100 | `module load system/mi100 rocm` |
| qc-mi210 | `module load system/qc-mi210 rocm` |
| qc-mi250 | `module load system/qc-mi250 rocm` |
| fs-mi300a | `module load system/fs-mi300a rocm` |
| fs-mi300x | `module load system/fs-mi300x rocm` |
| qc-pvc | `module load system/qc-pvc` (or `source /opt/intel/oneapi/setvars.sh`) |
| ng-dgx-m[0-3] | `module load system/ng-dgx nvhpc` |
| r340 | (none required) |

Put the module load at the start of the job's command, e.g.
`module load system/genoa mpi/openmpi-x86_64 && srun ./app`. After a system
module is loaded, `module avail` shows the rest of the software for that
partition.

## Job submission

The scheduler is Slurm. A JobSpec is rendered into an sbatch script and
submitted; the script is kept under `~/agent/jobs/` on the cluster so you can
inspect exactly what ran.

### The mandatory preamble

Every batch script must run `source /etc/profile` before any `module` command —
that is what makes `module` available, and a batch script's `#!/bin/bash` is not
a login shell that would source it automatically. **The plugin emits
`source /etc/profile` for you**, immediately after the `#SBATCH` header, so do
not add it to the executable yourself.

### GPU allocation

GPUs are requested with `--gpus=<n>` (a job-total count), and `--nodes` is always
stated explicitly. Set `resources.gpus` in the JobSpec to request them.

The unified CPU+GPU superchip partitions — **qc-gh200** and **ng-dgx-m[0-3]** —
take no GPU flag at all; the GPU is always present. Leave `resources.gpus` unset
for those; the plugin will not emit a GPU flag.

### Checking on work

Use the agent's status tools rather than memorizing commands: recent jobs, a
single job's normalized state and queue reason, and live per-partition node
occupancy are all available. Job stdout defaults to
`<workdir>/slurm-<job_id>.out`.

## Storage

Home directories live under `/home/<user>` and are shared across login and
compute nodes. Agent-created files (job scripts, staged uploads) are biased into
`~/agent/` so they are easy to find rather than scattered across `$HOME`.

## Special cases and restrictions

- **ai-h100l** is reserved for the "High Performance Big Data Research Team" and
  the "Data Management Platform Development Unit". General users should use
  **ai-h100l-pu**, which is the same hardware but capped at a **30-minute**
  walltime.
- **qc-h100** is under repair, and **qc-mi210**'s GPUs are still being set up —
  check live state before relying on either.
- **ng-dgx-m[0-3]** runs **Ubuntu**; every other partition runs **Rocky Linux**.
  A binary or Python wheel built on Rocky may not work on ng-dgx without a
  rebuild, and vice versa.
- **fs-mi300a** is an APU: CPU and GPU share a single 512 GB HBM pool, so there
  is no separate host-memory budget to reason about.
- **Networking**: only InfiniBand partitions suit tightly-coupled multi-node MPI.
  Ethernet-only partitions (genoa, genoa-m, b300, the ai-* family, mi100, r340,
  ng-dgx-m*) work for multi-node jobs but with much higher latency — prefer
  single-node or loosely-coupled work there.

## Common failure modes

- **"Exec format error"** — an x86_64 binary was sent to an aarch64 partition
  (fx700, qc-gh200, ng-dgx). Rebuild for the target architecture (cross-compile
  fx700 code on r340).
- **"module: command not found"** — `/etc/profile` was not sourced. The plugin
  emits it automatically; if you see this, check the executable didn't override
  the environment.
- **Command not found / link errors after loading a module** — the wrong
  `system/<partition>` module for the partition the job landed on. Match the
  module to the partition.
- **`native_state` OUT_OF_MEMORY** — reduce ranks, request `resources.memory`, or
  move to a larger-memory partition (genoa-m).
- **`native_state` TIMEOUT** — raise the job's `duration` (and remember
  ai-h100l-pu caps at 30 minutes).
- **GPU tools report no devices** — `resources.gpus` was not set on a partition
  that needs `--gpus=<n>`, or it was set on a superchip partition where it
  shouldn't be.
- **Accounts** — no `--account` is required; jobs without one use your default
  Slurm account.
