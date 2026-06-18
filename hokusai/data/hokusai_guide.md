# HOKUSAI BigWaterfall2 (HBW2)

An original, plain-language orientation to the HOKUSAI BigWaterfall2 (HBW2)
system, written for users who drive it through HokusaiAgent. It records the
site-specific facts that shape how you ask for work — not general HPC/Linux
background, and not a command reference. Stable facts (partition names, node
shapes, paths) are stated here so the agent can size a job without a round-trip;
genuinely changing values (queue occupancy, your budget balance, exact installed
versions) are left to the live system, which the agent queries on demand.

## What HBW2 is

HBW2 is a CPU-first supercomputer at RIKEN, scheduled with Slurm and reached
through shared front-end login nodes. Three subsystems:

- **MPC (Massively Parallel Computer)** — the workhorse: 312 standard nodes, each
  with 112 Intel Xeon cores (two 56-core sockets) and ~112 GiB of memory. Most
  work runs here.
- **LMC (Large Memory)** — 2 nodes with ~2.7 TiB of memory each, for jobs that
  need very large memory on a single host.
- **GPU** — a small 4-node server with NVIDIA H100 GPUs, mainly for
  postprocessing. Secondary; most HBW2 work is CPU/MPI.

The practical consequence for working with the agent: think CPU and MPI first,
describe jobs in nodes/processes/threads, and reach for GPUs only when a workload
genuinely needs one.

## Getting on the system

You connect over SSH to `hokusai.riken.jp`, load-balanced across login nodes
`hokusai1`–`hokusai4`. Authentication is by SSH key only — no password prompts —
so register your public key through the web portal (https://hokusai.riken.jp/hbw2/)
before your first login. The portal also lists current application versions and
hosts the official manuals.

Login nodes are for editing, building, staging files, and submitting. They are
shared and lightly resourced, so anything heavier than a quick check belongs in a
job — have the agent submit it rather than running it on the front end.

## Projects and your compute budget

Every job is billed to a project and you must name one when you submit (the
scheduler flag is `--account`). Project IDs are short codes: RIKEN projects begin
`RB` (e.g. `RB99999`); HPCI projects derive from an `HP` code. The agent can hold
a default project and let you override it per job.

Each project has a finite core-time allowance, spent as jobs run and recovering
gradually under a fair-share policy — so steady use through the year beats bursts,
and when the allowance is exhausted the project's new jobs stop starting. The
remaining balance changes continuously; ask the agent to read it live rather than
assuming it.

## Choosing where a job runs

A partition selects the subsystem and bounds wall time. The defaults if you don't
say otherwise: 1 hour of wall time, and a per-core memory share of 1 GiB on MPC,
30 GiB on LMC, 4 GiB on GPU (asking for more memory can raise the number of cores
you are billed for).

| partition | use for | cores/node | memory/node | max wall time |
|---|---|---|---|---|
| `mpc` (default) | everyday CPU / MPI work | 112 | ~112 GiB | ~24 h |
| `mpc_l` | longer CPU runs | 112 | ~112 GiB | ~72 h |
| `lmc` | very-large-memory jobs | 96 | ~2.7 TiB | ~24 h |
| `gpu` | GPU batch work | 112 | large | ~72 h |
| `gpu_i` | interactive GPU sessions | 112 | large | ~24 h |

How many nodes each partition has and how busy it is right now both change over
time — let the agent read current state (`get_facility` / live status) and tell
you where a job will start soonest, rather than planning around remembered counts.
For a GPU job, request GPUs explicitly (one GPU also reserves roughly 28 CPU
cores); the agent handles the GPU-specific scheduling details.

## Storage

Four places to keep data, each with a purpose:

- `/home/<user>` — code, scripts, small files; ~4 TB quota.
- `/data/<projectID>` — larger datasets and shared project results; requested
  through the portal and charged, so it is opt-in per project.
- `/tmp_work` — shared scratch; its contents are cleaned up automatically once
  they age past about a week, so copy anything you want to keep back to home or
  project storage before a job ends.
- node-local disk — fast storage that exists only for a job's duration; stage
  inputs onto it for I/O-heavy stages and copy results back out before the job
  releases the node, because it is wiped when the job ends.

The shared filesystem is Lustre; the agent can report your current usage and quota
on request.

## Software, compilers, and MPI

Software is provided through environment modules. Because versions change, have
the agent list what is installed live rather than relying on a frozen list — but a
few stable conventions matter when building and launching:

- **Intel oneAPI is the primary toolchain.** Loading the `intel` module brings in
  the Intel compilers and **Intel MPI** together; this is the recommended default
  for building and running MPI code on the Xeon nodes.
- **Launch MPI work with `srun`.** Under Slurm, `srun` inherits the job's
  allocation, so you don't pass process counts on the launch line — the resources
  you requested for the job determine them. This is true regardless of MPI flavor.
- **Open MPI is available as an alternative**, but its module **conflicts with
  Intel MPI** — load one or the other, not both (unload/`module purge` first if
  switching). Choosing Open MPI changes which module you load, not how you launch:
  it is still `srun` under Slurm.
- **Threaded code must be told its thread count** (match it to the cores you
  reserve per process), or it may run with the wrong number and far slower.

Major preinstalled applications include Gaussian, GROMACS, AMBER, NAMD, GAMESS,
ADF, ROOT, VMD, and GaussView — but confirm availability and version live, since
the catalogue evolves.

## Running work through the agent

You describe a job in resource terms — how many nodes, how many processes (MPI
ranks) per node, how many threads per process, how much memory and wall time, and
which project to charge — and the agent assembles and submits the batch job, then
returns an identifier to track. You do not write batch scripts or recall scheduler
flags yourself. Most jobs are pure-CPU MPI or a hybrid of MPI across nodes with
threads within each node.

One operational detail: compute nodes have no direct internet route. Outbound
connections are relayed through a proxy on the front end (the
`$SLURM_SUBMIT_HOST` on port 3128), which the agent sets up when a running job
needs to fetch something.

## Bringing your own environment with containers

Singularity is available when you want to carry a specific software stack onto the
machine. Pull a ready-made image from a public registry or build your own, then
have the agent run your program inside it; for GPU jobs the agent enables
container GPU access automatically.

## Following jobs and untangling failures

After submission, a job's queue position, state, and history come from the
scheduler — ask the agent and it reports back in plain language, including why a
waiting job is waiting (HBW2 orders jobs by fair-share priority). A job's console
output is written to a file named `slurm-<jobid>.out` in the directory it was
launched from, which the agent can read and summarize.

When a job misbehaves, the cause is usually one of a few:

- No project was named, or the project's core-time is exhausted.
- It ran out of memory — move to a bigger memory share or the `lmc` partition.
- It hit its wall-time limit — raise the limit or use `mpc_l` for longer runs.
- Its thread count was left unset, so performance collapsed.
- Conflicting MPI modules (Intel MPI and Open MPI) were loaded together.

The agent can inspect the failed job's record and output to point at which it was.

## Staying current

HBW2 evolves — partitions, installed software, limits, and policies change. The
authoritative sources are the portal and the live state of the machine, which the
agent can query whenever a precise, current answer matters. For anything not
covered here — especially accounts, allocations, and policy — fall back to those
or to RIKEN R-CCS support.
