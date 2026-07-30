# Fugaku Job Scheduler & Storage Guide

A plain-language guide to running jobs on RIKEN's Fugaku supercomputer via
its PJM scheduler ("Job Operation Software"), compiled from RIKEN's official
Fugaku user documentation (the "user-guide-use" and "user-guide-lang" Sphinx
guides — job execution, MPI, layered storage, access, and compiler
sections), cross-checked where possible against live commands run on a real
Fugaku login node during this port (account groups, `pjstat --help`,
`pjacl --rg small`/`large`, storage layout). Time-sensitive numbers (queue
limits, module versions) can drift — prefer a live command
(`pjacl --rg <name>`, `pjstat --limit`, `module avail`) over a number in
this guide when precision matters.

## 1. What makes Fugaku different from a typical Slurm cluster

- **Scheduler**: Fujitsu's PJM, not Slurm or PBS. Commands are `pjsub`
  (submit), `pjstat` (status), `pjdel` (cancel), `pjhold`/`pjrls` (hold/
  release), `pjalter` (change a queued job), `pjacl` (see a resource
  group's limits for your account).
- **No GPUs.** Every compute node is a single A64FX (Fujitsu/Arm,
  SVE-capable) CPU — there is nothing to request a GPU for.
- **Cross-architecture compilation.** Login nodes are Intel x86; compute
  nodes are A64FX/Arm. A binary built with a plain login-node `gcc`/`clang`
  will not run in a batch job — you need a cross compiler (see §6).
- **Mandatory project group.** Every submission needs `#PJM -g <groupname>`.
  The generic `fugaku` group every account belongs to cannot submit jobs —
  run `id` to see your real project groups (e.g. `ra000009`).
- **Layered, partly ephemeral storage.** A fast first-layer cache sits in
  front of persistent Lustre (FEFS); anything left only in the cache
  disappears when the job ends (see §5) — this is the single biggest
  surprise for anyone coming from a normal cluster.
- **No custom stdout/stderr paths.** Job output always lands at
  `<jobname>.<jobid>.out` / `.err` in the directory you submitted from —
  there is no `-o`/`-e` equivalent.

## 2. Anatomy of a job script

```bash
#!/bin/bash
#PJM -L "node=1"                    # number of nodes
#PJM -L "rscgrp=small"               # resource group (queue)
#PJM -L "elapse=60:00"               # wall time limit (mm:ss or hh:mm:ss)
#PJM -g groupname                    # project group — mandatory
#PJM -x PJM_LLIO_GFSCACHE=/vol000N   # declare any second-layer volume used
#PJM -S                              # optional: write a statistics file

export OMP_NUM_THREADS=12
./a.out
```

Submit with `pjsub ./sample.sh`. A successful submission prints:

```
[INFO] PJM 0000 pjsub Job 9714 submitted.
```

Omitting `-g`, or naming a group your account can't submit under, fails
immediately:

```
[ERR.] PJM 0071 pjsub Group not authorized to submit a job: group(59999)
```

`pjsub` also checks the directory it's invoked from. **"Data area" here
means specifically a group data volume, `/vol0n0m/data/<groupname>/`** —
your home directory (`/home/<username>`, or anything under it, including
`~/agent/jobs/`) is a *different* area type and does **not** qualify, even
though it also happens to live under `/vol0004`. Submitting from home
without acknowledging this fails:

```
The current directory is not a data area. (directory: /vol000N/groupname/username)
Specify --no-check-directory option if you want to submit jobs outside the data area.
```

RIKEN's own docs describe this same combination — submitting from a home
directory, with the check disabled — as the expected way to run a job
outside a group data volume. This plugin's `submit_job` already passes
`--no-check-directory` automatically, so you don't need to add it yourself.

## 3. Resource groups (queues)

The three ordinary groups named in RIKEN's docs:

| Group | Role | Typical node range | Typical elapse max |
|---|---|---|---|
| `small` | default batch group | 1–384 | 72:00:00 |
| `large` | large batch group | 385–12,288 | 24:00:00 |
| `int` | interactive (`pjsub --interact`'s default group) | 1–12 | varies by project (documented default 6h; some projects see more) |

Four low-priority **"spot" variants** (`spot-small`, `spot-large`,
`spot-int`, `spot-middle`) run for free on otherwise-idle nodes, are
excluded from fee-based projects, and are capped at a few hours unless the
node stays uncontested.

**If the project group is `trial`** (the default "Startup Project" every
new Fugaku account is issued), only the four `spot-*` groups are usable —
`small`/`large`/`int` are rejected under it. Check `id` for the account's
actual project groups before assuming `small` is available; a `trial`-only
account needs `spot-small`/`spot-int` instead.

These ranges are illustrative, not authoritative for your account — always
check the real numbers with:

```console
$ pjacl --rg small
```

which prints your account's actual min/max/default for `node=`, `elapse=`,
and every other `-L`/`--mpi`/`--llio` field on that group. `pjstat --limit`
shows your live concurrent-job and node/core-use quotas.

The full, current production list of every resource group (with exact
node-count and time-limit tables) lives on the Fugaku website's "Resource
group configuration" page — RIKEN's own docs point there rather than
listing it inline, since it changes independently of the user guide.

## 4. Node shape, MPI, and job models

`-L "node=..."` accepts a plain count or a 1D/2D/3D shape matching the Tofu
interconnect's torus:

```
-L "node=4"          # 4 nodes, any shape
-L "node=2x2x2"       # 8 nodes, explicit 3D shape
-L "node=2x2x2:torus" # same shape, forced Tofu-unit (torus) allocation
```

Allocation mode is an optional suffix: `:torus` (Tofu-unit allocation — 12
nodes/unit below 385 nodes, 48 nodes/unit above), `:mesh` (contiguous, but
node-granular), or `:noncont` (non-contiguous, the default for resource
groups of 384 nodes or fewer). Resource groups larger than 384 nodes only
support `:torus`.

MPI ranks launch with `mpiexec` **inside** the job script — it is not a
`pjsub` option:

```bash
#PJM -L  "node=2x3x2"                # 12 nodes
#PJM -L  "rscgrp=small"
#PJM -L  "elapse=01:00:00"
#PJM --mpi "max-proc-per-node=4"     # MPI ranks per node — set at submit time
#PJM -g groupname
export OMP_NUM_THREADS=12
mpiexec -n 48 ./a.out                # -n is the total rank count
```

A node has 4 CMGs (Core Memory Groups — NUMA-like domains); the docs'
rule of thumb is 4 MPI ranks per node with the remaining cores split across
OpenMP threads per rank. `--mpi "shape=..."` sets a static process shape
(defaults to the `-L node` shape if omitted); `--mpi "proc=N"` caps the
total process count.

Beyond a plain ("normal") job, PJM also supports **bulk jobs** (many
near-identical sub-jobs under one job ID), **step jobs** (sequential
dependent steps), **workflow jobs**, and **master-worker jobs** — these
show up in `pjstat`'s `MD` column as `BU`/`ST`/`MW` (`NM` is normal). This
guide's tooling only targets normal jobs; use `run_command_on_cluster` with
the raw `pjsub --bulk`/`--step` flags if you need one of the others.

## 5. Storage: the layered-storage gotcha

Fugaku's storage is **layered**: a fast, LLIO-managed first-layer cache
(node-local SSD-backed) transparently proxies persistent **second-layer**
storage (FEFS, a Lustre-based parallel filesystem). Reads/writes through
the cache are much faster than direct FEFS access — but **anything placed
only in the first layer disappears when the job ends**, unless it's been
explicitly written through to (or copied onto) second-layer storage first.
This is the single most common surprise for anyone porting code from
another cluster.

| Tier | Path / variable | Scope | Lifetime |
|---|---|---|---|
| Node-local temp | `$PJM_LOCALTMP` | one node | job start → job end |
| Shared temp | `$PJM_SHAREDTMP` | all nodes in the job | job start → job end |
| First-layer cache | `/vol000x/` (matches `PJM_LLIO_GFSCACHE`) | all nodes in the job | for the job's elapse limit; LRU-evicted when full |
| Home (second-layer/FEFS) | `/home/<username>/` | global | persistent, 20 GiB/user |
| Group data (second-layer/FEFS) | `/vol0n0m/data/<groupname>/` | global, per-project | persistent, 5 TiB/group |
| Group share (second-layer/FEFS) | `/vol0n0m/share/<groupname>/` | global, cross-group via ACL | persistent |
| 2ndfs (direct FEFS, bypasses cache) | `/2ndfs/<groupname>/` | global | persistent, 5 TiB/group |

Any job that touches a second-layer volume outside `$HOME` (including
Spack, which lives under `/vol0004`) must declare it:

```
#PJM -x PJM_LLIO_GFSCACHE=/vol0004
```

Omitting this for a job outside `/home` produces a hard `pjsub` error.
`llio_transfer <path>` distributes read-only "common files" (executables,
shared libraries, input data) across the job's assigned storage-I/O nodes
to avoid a metadata-server bottleneck when thousands of ranks open the same
file at once. Fugaku does **not** back up user data.

## 6. Software environment

Module system: the **Environment Modules** package (not Lmod):

```console
$ module avail                     # list available modulefiles
$ module list                      # list loaded modulefiles
$ module load lang                 # load the default language environment
$ module switch lang/tcsds-1.2.43  # swap versions
$ module purge                     # unload everything
```

**Spack** is also available as a separate package manager (e.g.
`/vol0004/apps/oss/spack/share/spack/setup-env.sh`), mainly for OSS
libraries.

Compiler suites:

- **Fujitsu compiler** (Technical Computing Suite, `module load lang/tcsds-*`)
  — the native/default toolchain, with MPI wrappers `mpifccpx`/`mpiFCCpx`/
  `mpifrtpx`.
- **GCC** — cross-compile on the login node via
  `/vol0004/apps/oss/gcc-arm-*/setup-env.sh`, or native on a compute node
  via Spack.
- **LLVM/Clang** — `module load LLVM/llvmorg-*`, MPI-wrapped as
  `mpiclang`/`mpiclang++`/`mpiflang`.

**Cross-compilation is mandatory unless you build on a compute node.**
Compute nodes are A64FX/Arm; ordinary login nodes are Intel x86, so a plain
`gcc`/`clang` invoked on a login node targets the *login node's* CPU, not
the compute nodes. Build with one of the cross toolchains above from the
login node, or hold an interactive job and build natively on a compute node
(slower iteration, but avoids the cross-compilation step entirely). A
separate Arm-native login node (`ssh arm1`) exists purely for this kind of
native Arm building — it has no `pjsub`/`pjstat`.

## 7. Interactive jobs

```console
$ pjsub --interact -g groupname -L "node=1" -L "rscgrp=int" -L "elapse=1:00:00" --sparam "wait-time=600"
[INFO] PJM 0000 pjsub Job 405918 submitted.
[INFO] PJM 0081 .connected.
[INFO] PJM 0082 pjsub Interactive job 405918 started.
$ ./a.out
$ exit
```

`--sparam "wait-time=N"` (seconds, 0–36000 or `unlimited`) controls how
long `pjsub` waits for resources before giving up; give it at least 60s to
avoid an immediate timeout. Several flags are silently ignored on
interactive jobs (`--at`, `-e`/`-o`, `-j`, `--bulk`/`--step`, `-m e`/`-m r`,
`--restart`, `-p`, `-w`).

## 8. Monitoring and managing jobs

`pjstat` (no arguments) lists your own queued/running jobs:

```
JOB_ID  JOB_NAME  MD  ST   USER   START_DATE      ELAPSE_LIM  NODE_REQUIRE  VNODE  CORE  V_MEM
238     job.sh    NM  RUN  user1  11/17 09:01:41  0001:00:00  12:2x3x2      -      -     -
```

`ST` (status) codes:

| Code | Meaning | Code | Meaning |
|---|---|---|---|
| ACC | accepted, not yet running | RNP | prologue running |
| QUE | queued | RUN | executing |
| HLD | held | RNA | resources acquired |
| SPD/SPP | suspended | RNE | epilogue running |
| CCL | canceled | RNO | terminating |
| ERR | job-management error | RSM | resuming |
| RJT | submission rejected | EXT | finished |

Note that `pjstat`'s live table has **no exit-code column** — a `EXT`
(finished) job just means the scheduler is done with it, not that your
program succeeded. Check the job's `<name>.<id>.out`/`.err` file to
confirm real success, or use the job's stats file (`#PJM -S`) if you
enabled one.

`pjstat --history [day=N]` shows finished jobs (REJECT/EXIT/CANCEL), up to
90 days retained. `pjdel <jobid>` cancels a job (accepts ranges and bulk/
step sub-job IDs like `1362939[3]`). `pjalter` can change a still-queued or
held job's resource request (most commonly the elapse time); once a job is
running, cancel and resubmit instead.

## 9. Accounting and quotas

Every submission needs a project group (`-g`, see §2). There is no
CPU-hour "budget" ledger exposed through the scheduler — instead:

- `pjstat --limit` — your live LIMIT vs ALLOC for concurrent submissions
  and node/core use, per-user and per-group.
- `pjacl --rg <name>` — the min/max/default resource values currently
  configured for a resource group under your account.

Run `id` to see which project groups your account belongs to (the shared
`fugaku` group is not one you can submit jobs under).

## 10. Other things worth knowing

- **Power capping**: a job's statistics report a `POWER CAPPING DATE`; if a
  job's power draw exceeds an operator-set threshold, its CPU clock is
  forcibly reduced.
- **Minimum-elapse-time submission** (`elapse=min-max`) lets a
  checkpoint-restart-aware job (e.g. using VeloC) keep running free of
  charge past `min`, until either `max` or preemption by a later job.
- **Job allocation operation**: Fugaku periodically moves a queued job to a
  different resource group to relieve congestion — this can silently
  change which per-user caps apply to it.
- **PJM exit codes**: every job gets a numeric code surfaced via a stats
  file (0 = success, 11 = elapse exceeded, 12 = out of memory, 20 = node
  down, ...), useful for automated failure triage.
