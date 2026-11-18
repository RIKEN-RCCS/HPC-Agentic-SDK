HBW2 is a **CPU-first** RIKEN R-CCS supercomputer, Slurm-scheduled,
reached via shared login nodes `hokusai1`–`hokusai4` (`hokusai.riken.jp`).

### Subsystems

- **MPC** — the workhorse: 312 nodes, 112 Intel Xeon cores (2×56), ~112 GiB.
- **LMC** — 2 nodes, ~2.7 TiB memory each; single-host large-memory jobs.
- **GPU** — 4-node server, NVIDIA H100; mainly postprocessing, secondary.

### Partitions

| partition | subsystem | max wall | notes |
|---|---|---|---|
| `mpc` (default) | MPC | ~24 h | everyday CPU/MPI |
| `mpc_l` | MPC | ~72 h | longer CPU runs |
| `lmc` | LMC | ~24 h | very large memory |
| `gpu` | GPU | ~72 h | GPU batch |
| `gpu_i` | GPU | ~24 h | interactive GPU |

Defaults if unspecified: 1 h wall; per-core memory share 1 GiB (MPC),
30 GiB (LMC), 4 GiB (GPU). **Requesting more memory can raise billed
cores.**

### Storage

- `/home/<user>` — code/scripts, ~4 TB, persistent.
- `/data/<projectID>` — datasets/shared results; opt-in per project, charged.
- `/tmp_work` — shared scratch, auto-purged after ~1 week.
- node-local disk — fast per-job scratch, wiped at job end.

Shared filesystem is Lustre. Ask the tools for live usage/quota.

### Software

Environment modules. **Intel oneAPI is primary** (`module load intel` →
Intel compilers + Intel MPI; only the LLVM compilers `icx`/`icpx`/`ifx`
are installed, not the classic `icc`/`icpc`/`ifort`). Open MPI is an
alternative that **conflicts** with Intel MPI — load one only. Launch
with `srun`. Singularity for containers. Major apps: Gaussian, GROMACS,
AMBER, NAMD, GAMESS, ADF, ROOT, VMD, GaussView — confirm versions with
`module avail` live.

There is **no python/conda module**: the system Python is bare 3.6 with
no third-party packages. Compute nodes have no direct internet route, so
bring pure-Python dependencies along (upload and use via `PYTHONPATH`),
or install into home on the login node first.

### GPU dialect

Request with a job-total GPU count (`resources.gpus`); one GPU reserves
~28 CPU cores; container flag `--nv` (single vendor, NVIDIA H100).

### Accounting

Every job is billed to a project (`--account`); RIKEN IDs start `RB`, HPCI
`HP`. Fair-share priority governs queue order and the balance recovers
gradually — read it live with `get_projects(facility="{{SLUG}}")`.
