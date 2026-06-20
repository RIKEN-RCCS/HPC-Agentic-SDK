# R-CCS Cloud — User Guide

## Overview

The R-CCS Cloud is a heterogeneous HPC cluster managed by RIKEN R-CCS. It is a
Slurm shop: all jobs are submitted via `sbatch`; interactive use is possible with
`srun --pty`. The cluster exposes many partitions covering a wide range of CPU
architectures and GPU vendors. **Modules are partition-specific** — the correct
`system/<partition>` module must be loaded in every job script, and modules from
one partition must never be used on another.

## Login

SSH destination: `login.cloud.r-ccs.riken.jp`

## Partitions and Hardware

The cluster has ~20 partitions. They fall into four families by GPU vendor (plus
CPU-only). Choose the right partition before writing your script — the module
commands, GPU specification flags, and even the OS differ by partition.

### CPU-only partitions

| Partition | Nodes | CPU | Memory | Network | Notes |
|-----------|------:|-----|-------:|---------|-------|
| fx700 | 31 | Fujitsu A64FX | 32 GB | InfiniBand EDR 100 Gbps | |
| genoa | 16 | AMD EPYC 9684X | 768 GB | Ethernet 1 Gbps | |
| genoa-m | 1 | AMD EPYC 9684X × 2 | 3,072 GB | Ethernet 1 Gbps | Large-memory node |
| r340 | 1 | Intel Xeon E-2134 | 64 GB | Ethernet 1 Gbps | Multi-user; cross-compilation env for FX700 |

**fx700 note:** The A64FX is a Fujitsu Arm-based processor. Binaries compiled for
x86_64 will not run here. Use r340 as the cross-compilation environment when
targeting fx700 from an x86 workstation.

### NVIDIA GPU partitions

| Partition | Nodes | CPU | GPU | Memory | Network | Notes |
|-----------|------:|-----|-----|-------:|---------|-------|
| a100 | 2 | AMD EPYC 7763 × 2 | A100 × 8 | 2,048 GB | InfiniBand HDR 200 Gbps × 8 | |
| b300 | 1 | Intel Xeon 6767P × 2 | B300 SXM6 × 8 | 2,048 GB | Ethernet 1 Gbps | Needs `--gpus=<n>` |
| ai-h100l | 2 | Intel Xeon Gold 5515+ × 2 | H100 NVL × 1 | 256 GB | Ethernet 1 Gbps | Restricted — see below |
| ai-h100l-pu | 2 | Intel Xeon Gold 5515+ × 2 | H100 NVL × 1 | 256 GB | Ethernet 1 Gbps | Open to all users; max 30 min walltime |
| ai-h200-brc | 1 | Intel Xeon Platinum 8592+ × 2 | H200 × 8 | 1,536 GB | Ethernet 1 Gbps | Needs `--gpus=<n>`; IB NDR 200 Gbps in preparation |
| ai-l40s | 7 | AMD EPYC 9554 × 2 | L40S × 8 | 1,536 GB | Ethernet 1 Gbps | Needs `--gpus=<n>`; IB NDR 200 Gbps in preparation |
| qc-a100 | 2 | AMD EPYC 7713 × 2 | A100 × 8 | 4,096 GB | InfiniBand HDR 200 Gbps | Needs `--gpus=<n>` |
| qc-h100 | 1 | AMD EPYC 9534 × 2 | H100 × 4 | 1,536 GB | InfiniBand HDR 200 Gbps | Currently under repair |
| qc-gh200 | 8 | NVIDIA Grace (aarch64) | GH200 superchip | 512 GB | InfiniBand HDR 200 Gbps | Unified CPU+GPU; no `--gpus` flag needed |

**ng-dgx partitions (Ubuntu OS — see below):**

| Partition | Nodes | Hardware | Memory | Network |
|-----------|------:|----------|-------:|---------|
| ng-dgx-m0 | 2 | NVIDIA GB10 Grace Blackwell Superchip | 128 GB | Ethernet 10 Gbps |
| ng-dgx-m1 | 2 | NVIDIA GB10 Grace Blackwell Superchip | 128 GB | Ethernet 10 Gbps |
| ng-dgx-m2 | 2 | NVIDIA GB10 Grace Blackwell Superchip | 128 GB | Ethernet 10 Gbps |
| ng-dgx-m3 | 2 | NVIDIA GB10 Grace Blackwell Superchip | 128 GB | Ethernet 10 Gbps |

The two nodes within each ng-dgx-m[0–3] pair are connected at 200 Gbps to each
other. Across pairs, connectivity is 10 Gbps Ethernet. Like qc-gh200, the GB10 is
a unified Grace+Blackwell superchip — no `--gpus` flag is needed.

### AMD GPU partitions

| Partition | Nodes | CPU | GPU | Memory | Network | Notes |
|-----------|------:|-----|-----|-------:|---------|-------|
| mi100 | 1 | AMD EPYC 7713 × 2 | MI100 × 8 | 1,024 GB | Ethernet 1 Gbps | |
| qc-mi210 | 2 | AMD EPYC 9554 × 2 | MI210 × 1 | 1,536 GB | InfiniBand HDR 200 Gbps | GPU setup in progress |
| qc-mi250 | 4 | AMD EPYC 7713 × 2 | MI250 × 8 | 1,024 GB | InfiniBand HDR 200 Gbps | |
| fs-mi300a | 1 | — | MI300A × 4 | 512 GB | InfiniBand HDR 200 Gbps | APU: CPU and GPU share memory |
| fs-mi300x | 1 | AMD EPYC 9534 × 2 | MI300X × 8 | 1,536 GB | InfiniBand HDR 200 Gbps | |

### Intel GPU partitions

| Partition | Nodes | CPU | GPU | Memory | Network |
|-----------|------:|-----|-----|-------:|---------|
| qc-pvc | 2 | Intel Xeon Platinum 8470 × 2 | Data Center GPU Max 1550 × 8 | 2,048 GB | InfiniBand HDR 200 Gbps |

## Module Loading

**This is the most important setup step.** Every partition has its own
`system/<partition>` module that configures paths, libraries, and compiler
wrappers for that hardware. You must load it at the start of every job script,
right after `source /etc/profile`. Loading a system module from a different
partition will silently produce wrong results or runtime errors.

The required module commands per partition are:

| Partition | Module command |
|-----------|---------------|
| fx700 | `module load system/fx700 FJSVstclanga` |
| a100 | `module load system/a100 nvhpc` |
| b300 | `module load system/b300 nvhpc` |
| mi100 | `module load system/mi100 rocm` |
| genoa, genoa-m | `module load system/genoa mpi/openmpi-x86_64` |
| ai-h100l, ai-h100l-pu | `module load system/ai-h100l nvhpc` |
| ai-h200-brc | `module load system/ai-h200-brc nvhpc` |
| ai-l40s | `module load system/ai-l40s nvhpc` |
| qc-a100 | `module load system/qc-a100 nvhpc` |
| qc-h100 | `module load system/qc-h100 nvhpc` |
| qc-gh200 | `module load system/qc-gh200 nvhpc` |
| qc-mi210 | `module load system/qc-mi210 rocm` |
| qc-mi250 | `module load system/qc-mi250 rocm` |
| qc-pvc | `module load system/qc-pvc` or `source /opt/intel/oneapi/setvars.sh` |
| fs-mi300a | `module load system/fs-mi300a rocm` |
| fs-mi300x | `module load system/fs-mi300x rocm` |
| ng-dgx-m[0–3] | `module load system/ng-dgx nvhpc` |
| r340 | No system module required |

After loading the system module, run `module avail` to see what additional
software is available for that partition.

## Job Submission

The scheduler is Slurm. Submit jobs with `sbatch`; check status with `squeue`.

### Mandatory job script preamble

Every batch script must begin with:

```bash
#!/bin/bash
source /etc/profile
module load system/<partition> <toolkit>
```

`source /etc/profile` initialises the module system. Omitting it means `module`
commands will not work.

### Minimal job script template

```bash
#!/bin/bash
#SBATCH --job-name=myjob
#SBATCH -p <partition>
#SBATCH -N 1
#SBATCH -t 01:00:00

source /etc/profile
module load system/<partition> <toolkit>

srun ./myapp
```

### GPU allocation flags

Most GPU partitions require you to explicitly request GPUs:

```bash
#SBATCH --gpus=<number>    # e.g. --gpus=4
```

Partitions that **require** `--gpus=<n>`: `b300`, `ai-h200-brc`, `ai-l40s`,
`qc-a100`.

Partitions where `--gpus` is **not** needed (unified CPU+GPU superchips):
`qc-gh200`, `ng-dgx-m[0–3]`.

The `a100`, `mi100`, `qc-mi250`, and similar partitions follow standard Slurm
GPU resource conventions — confirm with `sinfo -p <partition>` if unsure.

### Submitting and checking status

```bash
sbatch ./job.sh          # submit
squeue -u $USER          # your running/queued jobs
scancel <job_id>         # cancel a job
```

## Special Cases and Restrictions

### OS differences: Rocky vs Ubuntu

All partitions run **Rocky Linux** except `ng-dgx-m[0–3]`, which run **Ubuntu**.
This affects:
- System library versions and paths
- Available package managers and pre-installed software
- Python environment setup

Do not assume a binary or environment prepared on a Rocky node will work on
`ng-dgx` without testing, or vice versa.

### Restricted partitions

- **ai-h100l**: reserved exclusively for the "High Performance Big Data Research
  Team" and "Data Management Platform Development Unit". Use `ai-h100l-pu`
  instead if you have general access.
- **ai-h100l-pu**: same physical nodes as ai-h100l, open to all users, but jobs
  are limited to a maximum walltime of **30 minutes**.

### Partitions currently unavailable

- **qc-h100**: under repair as of the last guide update. Check `sinfo -p qc-h100`
  for current status.
- **qc-mi210**: GPU configuration in progress. Not suitable for GPU workloads yet.

### r340: cross-compilation for FX700

The r340 node is a standard x86_64 Intel Xeon machine. It is available to
multiple users simultaneously and is intended as a cross-compilation environment
for code targeting the Fujitsu A64FX (fx700 partition). No system module is
required on r340.

### fs-mi300a: unified CPU+GPU memory

The MI300A is an APU where CPU and GPU share a single pool of HBM memory. There
is no discrete host CPU memory — the 512 GB is the combined pool. This is
different from all other AMD GPU partitions and affects how you allocate and
transfer data.

### InfiniBand vs Ethernet partitions

Only partitions with InfiniBand are suited for tightly-coupled multi-node MPI
jobs. Ethernet-only partitions (`genoa`, `genoa-m`, `b300`, `ai-*`, `mi100`,
`r340`, `ng-dgx-m[0–3]`) may be used for multi-node work but will see much
higher communication latency. Prefer single-node jobs or loosely-coupled
workflows on Ethernet-only partitions.
