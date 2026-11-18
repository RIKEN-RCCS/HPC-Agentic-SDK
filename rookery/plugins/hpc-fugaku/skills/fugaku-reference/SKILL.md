---
name: fugaku-reference
description: Use to answer questions about Fugaku itself — hardware, partitions, storage, software, policies, or where to get help. Ground answers in the bundled guide and live tool output rather than prior knowledge.
---

# Fugaku reference

**Do not answer questions about this machine from memory.** Ground every
answer in the bundled guide or live tool output. The orientation facts at
the bottom of this skill are a fallback for when the tools are
unavailable — not the authoritative source.

## Workflow

1. `search_docs(facility="fugaku", query=...)` on the `hpc-docs` server,
   with the user's question. Cite the section breadcrumb it returns (e.g.
   "Running jobs"), not a URL.
2. If results look incomplete,
   `list_doc_sections(facility="fugaku")` shows the full table of
   contents and `read_doc_section(facility="fugaku", breadcrumb=...)`
   reads one section in full.
3. **For anything that changes over time — queue occupancy, node counts,
   installed software versions, your project's balance — check live state
   instead**, since the guide deliberately doesn't freeze these:
   `get_facility(facility="fugaku")` for static facts,
   `get_resources(facility="fugaku")` for occupancy,
   `get_projects(facility="fugaku")` for accounts, or
   `run_command_on_cluster(facility="fugaku", command="module avail")`.
4. If the guide doesn't cover it and no tool answers it, say so plainly
   rather than guessing.

**Search results carry no "Source:" URL unless this facility registered
one, and most don't. That's deliberate — never invent a URL to send the
user to.**

## Facility-specific reference

Fugaku is RIKEN R-CCS's flagship: **158,976 nodes of A64FX (Arm SVE),
48 compute cores each, no GPUs anywhere in the system**, scheduled by
Fujitsu's PJM rather than Slurm.

### Orientation facts (fallback only — prefer the tools)

- **Architecture**: A64FX, Armv8.2-A + SVE 512-bit. x86_64 binaries,
  containers and wheels will not run. Cross-compilation is the norm — see
  the `fugaku-build` skill, which covers the four verified toolchains.
- **Scheduler**: PJM. `pjsub` submits, `pjstat` queries, `pjdel` cancels,
  `pjalter` changes a queued job's elapse limit. There is no `sacct`,
  `squeue`, or `sacctmgr`; nevertheless, `get_projects` lists the current
  user's PJM groups through `id -Gn`, and `get_project_allocations` reports
  a group's Fugaku Points from `accountj_pt` when that group has point
  accounting. PJM exposes no separately verified per-user point share.
- **Resource groups** (the PJM equivalent of a partition): `small`
  (1–384 nodes, ≤72h), `large` (385+ nodes, ≤24h), `int` (interactive),
  `f-pt` (priority, **consumes Fugaku Points**), `spot-*` (low priority).
  Which ones an account may use depends on its project — confirm with
  `pjacl --rg <name>` rather than assuming.
- **Project group is mandatory** on every job, and the shared `fugaku`
  group cannot submit. A `trial` (Startup Project) group can only use
  `spot-*` groups.
- **Storage is layered**: `$HOME` on the first layer; second-layer volumes
  (`/vol####`) must be declared per job via `PJM_LLIO_GFSCACHE`. Spack
  lives on second-layer storage too, so jobs using it need the declaration.
- **Output**: `<name>.<job_id>.out`/`.err` in the submission directory, and
  for MPI jobs the per-rank output lands under `output.<jobid>/` in the
  working directory instead — see `fugaku-monitoring-jobs`.

### Working on the login nodes

- `run_command_on_cluster` sessions **drop on commands that run more than
  a few minutes** ("could not communicate with process"). The remote process
  usually keeps running, but its foreground output is lost. Start anything
  long (builds, large `tar`/`rsync`, `du` surveys) as
  `nohup … > ~/agent/<name>.txt 2>&1 < /dev/null &` and follow the log with
  `fs_tail`.
- Successive calls can land on **different x86 login hosts** (fn01sv01,
  fn01sv02, …). `ps`/`pgrep` on one host cannot see a process started on
  another, so use log files, not process listings, as the progress signal.
- A full `du` over a large project tree can run for most of an hour.
  Survey per directory, in the background, and prefer `accountd -E` for
  totals.
- There are two kinds of login node. The x86 nodes (RHEL 8, internet,
  `pjsub`, cross compilers) are where everything is done. `arm1` is
  aarch64 but runs glibc 2.17, has no internet and no `pjsub`. It is not a
  native-build host for the site's RHEL 8 software.

### Getting help

Point users at RIKEN R-CCS's Fugaku support desk; this plugin cites no
documentation URL, since there's no confirmed-stable public page to send
people to.

## Keeping the guide fresh

The docs index is built from this facility's bundled guide
(`facilities/<dir>/data/`), an original hand-written write-up — never
re-scraped from a live site. If it goes stale, edit the guide and rebuild:
`python -m hpc_mcp.ingest fugaku` (it falls back to a BM25-only index
when no embedding key is configured), then commit the regenerated
`docs_index/`.
