---
name: hokusai-reference
description: Use to answer questions about HOKUSAI BigWaterfall2 (HBW2) itself — hardware, partitions, storage, software, policies, or where to get help. Ground answers in the bundled guide and live tool output rather than prior knowledge.
---

# HOKUSAI BigWaterfall2 (HBW2) reference

**Do not answer questions about this machine from memory.** Ground every
answer in the bundled guide or live tool output. The orientation facts at
the bottom of this skill are a fallback for when the tools are
unavailable — not the authoritative source.

## Workflow

1. `search_docs(facility="hokusai", query=...)` on the `hpc-docs` server,
   with the user's question. Cite the section breadcrumb it returns (e.g.
   "Running jobs"), not a URL.
2. If results look incomplete,
   `list_doc_sections(facility="hokusai")` shows the full table of
   contents and `read_doc_section(facility="hokusai", breadcrumb=...)`
   reads one section in full.
3. **For anything that changes over time — queue occupancy, node counts,
   installed software versions, your project's balance — check live state
   instead**, since the guide deliberately doesn't freeze these:
   `get_facility(facility="hokusai")` for static facts,
   `get_resources(facility="hokusai")` for occupancy,
   `get_projects(facility="hokusai")` for accounts, or
   `run_command_on_cluster(facility="hokusai", command="module avail")`.
4. If the guide doesn't cover it and no tool answers it, say so plainly
   rather than guessing.

**Search results carry no "Source:" URL unless this facility registered
one, and most don't. That's deliberate — never invent a URL to send the
user to.**

## Facility-specific reference

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
gradually — read it live with `get_projects(facility="hokusai")`.

## Keeping the guide fresh

The docs index is built from this facility's bundled guide
(`facilities/<dir>/data/`), an original hand-written write-up — never
re-scraped from a live site. If it goes stale, edit the guide and rebuild:
`python -m hpc_mcp.ingest hokusai` (it falls back to a BM25-only index
when no embedding key is configured), then commit the regenerated
`docs_index/`.
