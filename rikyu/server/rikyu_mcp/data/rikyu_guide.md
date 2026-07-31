# RIKYU Orientation Guide

RIKYU is a RIKEN Center for Computational Science (R-CCS) supercomputer
built for AI-accelerated scientific discovery. It is currently in Early
Access Phase 2 (running through the end of September 2026) — expect the
software stack and policies to still be settling, and re-verify anything
here that seems to have changed before trusting it blindly.

## System shape

400 compute nodes, each an NVIDIA GB200 NVL4: two Grace CPUs and four B200
GPUs per node, wired together with cache-coherent NVLink-C2C, so a CPU can
address GPU memory and vice versa without an explicit copy. That coherency
is the reason job memory limits below are described as a combined CPU+GPU
figure rather than two separate numbers.

There are 1,600 GPUs in the machine total. Nodes are wired in a two-layer
Fat Tree (6 spine switches, 17 leaf switches, InfiniBand XDR). Nodes under
the same leaf switch talk to each other faster than nodes that have to
cross a spine switch — for large multi-node jobs where placement matters,
keep this in mind, though the scheduler does not currently expose a way to
request leaf-local placement explicitly.

## Getting in

Two ways to reach the machine: the Open OnDemand web portal, or SSH
directly to `login.rikyu.r-ccs.riken.jp`. SSH access requires registering a
public key first, which is done through Open OnDemand (launch its "SSH
Public Key" app) — there is no separate email-an-admin process. Generate an
Ed25519, NIST P-521 ECDSA, or 2048-bit-or-larger RSA key pair before you
start; RIKYU doesn't hand you one.

Accounts go through the RIKYU Account Application System (RAAS), and are
currently limited to ARiSE users, accepted SPReAD1000 projects, and RIKEN
members. If you're carrying over an account from Early Access Phase 1, you
still need to file a fresh application — old accounts don't roll forward,
and Phase 1 data does not migrate itself, so move anything you need before
your Phase 1 access lapses.

## Slurm

RIKYU has exactly one partition, `gpu`, covering all 400 nodes — there's no
separate CPU-only or debug partition to choose between. Request GPUs with
`--gpus=N`, not `--gres=gpu:N`; RIKYU uses the job-total-count dialect. You
do not need to (and normally should not) set `--nodes` yourself — Slurm
derives the node count from the GPU count automatically, at 4 GPUs per
node. `--account` is not part of the job scripts this system expects,
unlike some other RIKEN machines — leave it out unless told otherwise.

Standard `sbatch`/`squeue`/`salloc`/`srun`/`scancel`/`sinfo` all work as
expected. Slurm accounting (`sacct`) is available on RIKYU, so job history
beyond what's currently queued or running is queryable, not just the live
queue.

**Launch MPI programs with `mpirun`, not `srun`.** Verified live: `srun`
fails MPI programs at `MPI_Init` with an internal-runtime error, even
though `srun --mpi=list` shows `pmi2`/`pmix` plugins registered. `mpirun`
(from an MPI-capable module — `nvhpc-hpcx`/`nvhpc-hpcx-cuda13`, not
`nvhpc-nompi`) works correctly, both single-node and real multi-node,
*as long as the job's Slurm allocation gives it enough task slots* — set
`resources.processes_per_node` to your rank count, or `mpirun` fails with
"not enough slots" even though nothing else is wrong. `srun` itself is
still fine outside MPI (interactive `salloc`/`srun --pty`, or
`srun --overlap --jobid <id>` to attach to a running job for diagnostics)
— the failure is specifically MPI rank bootstrap.

## Job resource limits

Only seven GPU counts are accepted per job: 1, 2, 3, 4, 8, 12, or 16 — there
is no arbitrary N. Everything else about a job's resource ceiling follows
from that count at a fixed rate of 4 GPUs per node:

- 1–4 GPUs fit on a single node (36 CPU cores and 400 GB combined
  memory per GPU requested, up to a max of 144 cores / 1,600 GB at 4 GPUs).
- 8, 12, and 16 GPUs span 2, 3, and 4 nodes respectively, each node capped
  at 144 CPU cores and roughly 1,600 GB combined memory.

The "combined memory" figure is CPU DRAM plus usable GPU HBM added
together, reflecting the NVLink-C2C coherency mentioned above — it is not a
number you'd see on a machine where CPU and GPU memory are separate pools.

Every job, regardless of size, is capped at a 96-hour wall time — there is
no separate short-queue/long-queue split with different limits.

## Storage

Three tiers, each with a different purpose:

- **Home** (`/home/USERNAME`, 5 GB, Lustre, SSD-backed): your own small
  files, dotfiles, and configuration only. 5 GB is genuinely small — do not
  stage datasets, checkpoints, or build artifacts here; use the group area
  for anything beyond a trivial size, and check quota live
  (`lfs quota -h -p ...`) before assuming there's room for something new.
- **Group** (`/data1/GROUPNAME`, 1 TB per group, Lustre, HDD-backed):
  shared work files for everyone in your Unix group. Find your group name
  from `id` — it's the entry starting with `rkp`. Both home and group are
  visible from both login and compute nodes, so this — not home — is where
  inputs, outputs, datasets, and anything that needs to survive past one job
  should actually live.
- **Scratch** (`/tmp`, 1.5 TB per requested GPU, xfs, node-local NVMe): only
  visible to the job actually running on that node, and wiped the moment
  the job ends. Good for intermediate files during a run; never for
  anything you need afterward. Copy results to home or group storage before
  the job exits.

Capacity increases for home or group storage go through a support ticket,
not a self-service command.

## Software: modules and Spack

Compiler/MPI environments are Lmod modules, all variants of the NVIDIA HPC
SDK: `nvhpc` (the standard choice, includes MPI), `nvhpc-nompi` (bring your
own MPI), `nvhpc-hpcx` / `nvhpc-hpcx-cuda13` (HPC-X MPI over InfiniBand,
the latter pinned to CUDA 13), and `nvhpc-byo-compiler` (use the system GCC
or your own compiler instead of NVIDIA's). Run `module purge` before
loading what you need, to avoid stale environment leftovers from a previous
module load in the same shell.

Applications and libraries (cp2k, GROMACS, Quantum ESPRESSO, LAMMPS,
PETSc, and dozens more scientific/Python packages) are managed with Spack,
not modules. The system-provided ("public instance") Spack environment is
loaded with `. /shared/software/spack-1.2.0/share/spack/setup-env.sh`
(bash/zsh) or the `.csh` equivalent for csh/tcsh — this line has to be
repeated inside any batch script that uses Spack software, since a job
script doesn't inherit your interactive shell's sourced environment.
`spack load <package>` then puts it on `PATH`. Loading a GPU-enabled
package does *not* by itself reserve GPUs — you still need `#SBATCH
--gpus=N` in the job script for the hardware to actually be allocated.

A handful of packages (currently petsc, lammps, quantum-espresso, gromacs,
kokkos) are built with GPU support, and quantum-espresso and gromacs
specifically are also built against `hpcx-mpi` for InfiniBand-native MPI.
When more than one build of the same package exists (different compiler,
MPI, or GPU variant), Spack disambiguates by hash — `spack find -lx
<name>` shows the short hash for each candidate, and `spack load /<hash>`
picks one unambiguously. The list of what's pre-built can change as the
system evolves; treat the package names above as a starting point and
confirm against `spack find -x` before assuming something is or isn't
available.

Users who need software outside the public instance (a different version,
custom build flags, or a package the system doesn't provide) build their
own "private instance" of Spack under their home directory, optionally
chained to the public instance's `install_tree` via `upstreams.yaml` so
shared dependencies don't have to rebuild from scratch. Never build
anything heavy on a login node — use an interactive job (`salloc`/`srun`)
or submit a build as its own batch job.

## Common failure modes

- **`spack: command not found`** — the Spack `setup-env.sh` line was never
  sourced in this shell (or this job script). Re-source it.
- **`matches multiple packages` from `spack load`** — more than one build
  of that name is installed; disambiguate with a hash from `spack find -lx
  <name>`, e.g. `spack load /5rny4xu`.
- **An MPI job aborts immediately in `MPI_Init`** — it was launched with
  `srun`. Use `mpirun` instead (see "Slurm" above); this is unrelated to
  the implementation-mismatch failure below.
- **`mpirun` fails with "not enough slots available"** — the job didn't set
  `resources.processes_per_node` to match its rank count, so Slurm only
  gave it one task slot. Set it explicitly.
- **An MPI job won't start, or errors during communication** — the MPI
  implementation the application was built against doesn't match what's
  actually being launched at runtime. Confirm what an application was built
  with via `spack spec /<hash>` (look for `^hpcx-mpi` in the dependency
  tree) before assuming the MPI stack itself is broken.
- **Software works interactively but not inside a batch job** — the job
  script forgot to re-source Spack's `setup-env.sh`; sourcing it once in an
  interactive login shell does not carry into `sbatch` scripts.
- **A GPU job runs but the application can't see any GPU** — the Slurm
  request is missing `--gpus=N`; loading GPU-enabled software through Spack
  does not itself allocate hardware.

## Billing

Usage is metered per GPU-hour (300 yen/GPU-hour as of Early Access Phase 2,
billed in arrears as a lump sum after the phase ends — this rate is a
policy detail, not a technical one, so confirm it hasn't changed before
relying on it for planning). Current usage is visible through the billing
system linked from Open OnDemand, not from a command-line tool.
