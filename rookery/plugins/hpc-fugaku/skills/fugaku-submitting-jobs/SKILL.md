---
name: fugaku-submitting-jobs
description: Use when the user wants to run, submit, or launch a job on Fugaku. Covers partition/queue selection, JobSpec construction, submission, and known gotchas specific to this facility.
user-invocable: true
---

# Submitting jobs on Fugaku

Every tool call in this skill uses `facility="fugaku"`.

Fugaku is **A64FX (Arm SVE) and has no GPUs** — never set `resources.gpus`
or `resources.gpu_cores_per_process`; both are rejected outright.

## Workflow

1. **Choose a PJM resource group** for `attributes.queue_name` — there is
   no default, deliberately, because which groups an account may use
   differs per project. `small` (1–384 nodes, up to 72h), `large` (385+
   nodes, up to 24h), `int` (interactive), `f-pt` (priority, see below), or
   a `spot-*` low-priority variant. Confirm the real min/max/default for
   this account with
   `run_command_on_cluster(facility="fugaku", command="pjacl --rg small")`.
2. **Every job needs a project group.** Set `attributes.account`
   explicitly, or rely on `defaults.group` in the config file (or
   `FUGAKU_GROUP`) — `submit_job` raises a clear error if neither
   is set. The shared `fugaku` group **cannot submit jobs**. If the
   resolved group is `trial` (the "Startup Project" every new account
   gets), only the `spot-*` resource groups work — `small`/`large`/`int`
   are rejected. Check `run_command_on_cluster(facility="fugaku",
   command="id")` for the account's real project groups before assuming
   `small` is available.
3. **Set `resources.node_count`.** For MPI work also set
   `resources.processes_per_node` (renders as PJM's
   `--mpi "max-proc-per-node=N"`) or `resources.process_count` for a total
   rank count. An `mpiexec -n <N>` launcher is added automatically whenever
   more than one task is requested — don't add it yourself unless you need
   non-default `mpiexec` flags (set `launcher` explicitly to override).
4. **Declare second-layer storage.** If the job touches anything outside
   `$HOME` — a group data volume, or Spack — set
   `attributes.custom_attributes["gfscache_volume"]` (e.g. `"/vol0004"`)
   or rely on the configured default. Without it `pjsub` rejects the job.

   **Declare exactly one volume.** A comma-separated value such as
   `/vol0002,/vol0004` is accepted by `pjsub` at submission, queues
   normally, and then fails the pre-execution gate check minutes later:
   state `ERR`, `REASON : GATE CHECK`, **no output file and no exit code**.
   That silent, delayed failure is why it is worth catching — `submit_job`
   now rejects a comma-containing value up front.

   Verified live across eight jobs, varying one thing at a time: every job
   carrying the comma value failed (at 5 *and* 10 minute elapse limits, so
   wall time is irrelevant), and every job with a single volume or none
   ran to completion (at 5, 6, 9 and 10 minutes). The `small-s5` sub-group
   that appears in `pjstat -s` is a red herring — successful jobs run in
   it too.

   The correct syntax for declaring **more than one** volume is not
   documented in the bundled guide or in `pjsub --help`; both only ever
   show a single `/vol000N`. Ask RIKEN rather than guessing a separator.
5. **Leave `stdout_path`/`stderr_path` unset** — PJM has no flag for
   redirecting them. Output always lands at `<name>.<job_id>.out`/`.err` in
   the submission directory. Set `spec.directory` if you want it elsewhere.

## Jobs run from the group data area, not `$HOME`

Point `directory` at something under `/vol0n0m/data/<groupname>/` for
every job. Home (`/home/<user>`) is a 20 GiB per-user area meant for
code and scripts; the group data area carries ~5 TiB per group and is
the intended job-execution space. Large outputs (matrix files, result
archives) can exhaust the home quota mid-run. `pjsub`'s submit-time
directory check also prefers the data area — the plugin passes
`--no-check-directory` automatically, so running from home *works*.
That is not the same as right.

Read the concrete path live instead of guessing the volume number:
`accountd -E` on the login node lists the account's project groups,
their `/vol0X0X/data/<group>/` paths, and quota usage.

## Disk and inode pressure on the group volume

Group data volumes are shared by every member, and a busy project can sit
close to its limit. Writes then fail with `Disk quota exceeded` (EDQUOT)
from jobs and from login-node `rsync`/`tar` alike, **even when `lfs quota`
on the volume shows no user, group or project limit**; the enforced limit
is not visible there. The **file count** can be the binding limit long
before space is: removing a modest number of files can restore writes when
freeing space alone would not.

- Check `accountd -E` (space **and** file counts) before a large build,
  a Spack install or a big result set. Treat inodes as the scarce resource.
- Keep build stages, Spack/pip/conda caches and unpacked source trees
  **off** the group data volume: put them in a job's compute-node `/tmp`
  (see below) or another filesystem, and archive results to a few large
  files instead of keeping many small ones.
- Deleting is the user's call: show exact paths and get confirmation, and
  start with obvious low-risk targets (caches, your own failed scratch).

## Temporary storage inside a job

- `$PJM_LOCALTMP` (`/local`) and `$PJM_SHAREDTMP` (`/share`) have **zero
  capacity unless the job requests an LLIO size**. Writes fail with "No
  space left on device". The bundled guide lists them as normal tiers; they
  are empty by default. The request syntax is likely `#PJM --llio
  localtmp-size=<N>Gi` / `sharedtmp-size=<N>Gi` (`custom_attributes.llio`
  is accepted by `submit_job`), but it has not been verified to work here.
  Test it with a small job before relying on it.
- Compute-node `/tmp` is usable scratch (tens to hundreds of GB free), but
  it is **NFS shared per node group and survives the job**, and different
  jobs land on different node groups. Clean up **in the same job** that
  wrote the files; a later cleanup job usually lands elsewhere. Set
  `TMPDIR=/tmp` for tools (configure, Spack) that need a working temp dir.

## Put multi-node I/O on `/2ndfs`

For multi-node runs where several nodes write files and then read them
back during the run (checkpoints, intermediate databases), put the run
directory on `/2ndfs/<group>/...` (direct FEFS, no LLIO cache) rather than
on the cached `/vol000N` path. On the cached path such runs have hung
intermittently at the read-back and paid much slower write-then-read round
trips. The same runs on `/2ndfs` did neither. The cause has not been
established, so if a multi-node run stalls on I/O, `/2ndfs` is the first
thing to try. Executables, environments and read-only
inputs can stay on the group volume, and the job still needs
`gfscache_volume` for them.

## Typed submission with a self-launching driver

If `executable` is a script or driver that calls `mpiexec` itself, set
`launcher="env"`. Otherwise the auto-added `mpiexec -n N` wraps your
driver and starts N copies of it. The launcher is prefixed to `executable`,
so shell setup such as `source env.sh` belongs in `pre_launch`, not at the
front of `executable`.

## The standard A64FX layout

4 ranks per node (`processes_per_node: 4`) with 12 OpenMP threads per rank
(`OMP_NUM_THREADS=12` in `environment`), fully using the 48 cores per node.

## f-pt costs Fugaku Points

**`f-pt` is a priority queue that consumes Fugaku Points — it is not
free.** Confirm with the user before using it, and check the selected
project's remaining balance with `get_project_allocations(facility="fugaku",
project_id="<group>")`. Use it only for deliberate fast-turnaround
validation; revert to `small` for production runs.

Use `small` with a short `elapse` for validation jobs. The two can differ
by days: `f-pt` jobs usually start within minutes, while `small` can queue
for a long time when the machine is busy. Check the estimated start
(`pjstat` / `get_job_status`) of a queued `small` job. If it is far off,
tell the user and let them decide whether to spend points.

## Universal rules (apply on every facility, not just this one)

- `submit_job(facility="fugaku", spec=spec)` — **show the user the spec
  (or a plain-language description of it) before submitting, unless
  they've explicitly said to just run it.** No exceptions for this call.
- The returned `{"job_id": ..., "script_path": ...}` — the rendered script
  is kept on the cluster; `fs_view(facility="fugaku", path=script_path)`
  to inspect exactly what was submitted.
- If a partition/queue/GPU choice isn't given or obvious, check
  `get_resources(facility="fugaku")` (live occupancy) and
  `get_facility(facility="fugaku")` (static limits) — don't guess.
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
  use `search_docs(facility="fugaku", query=...)` on the `hpc-docs`
  server. It searches a bundled guide, not a live site — never invent a URL
  to send the user to.
- Don't call `cancel_job` without confirming with the user first.
